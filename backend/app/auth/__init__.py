"""Firebase login: every /api route except health depends on require_viewer (main.py); admin routes on require_admin.
Owner: Person A. Firebase is the user store; ADMIN_EMAILS / ALLOWED_EMAIL_DOMAIN (env) are the roles."""
import functools

import firebase_admin
from fastapi import HTTPException, Request
from fastapi.security.utils import get_authorization_scheme_param
from firebase_admin import auth, credentials
from google.auth.credentials import AnonymousCredentials

from app import config
from app.schemas import MeOut

_UNAUTHORIZED = {"WWW-Authenticate": "Bearer"}


class _NoCredential(credentials.Base):
    """verify_id_token only needs Google's public certs, but the SDK wants a credential object: give it an empty one."""
    def get_credential(self):
        return AnonymousCredentials()


@functools.cache
def _firebase_app() -> firebase_admin.App:
    return firebase_admin.initialize_app(_NoCredential(), {"projectId": config.FIREBASE_PROJECT_ID}, name="paymail")


def require_viewer(request: Request) -> MeOut:
    """401 for a missing, malformed, expired or wrong-project token; 403 for an unverified or not-allowed email.
    503 if FIREBASE_PROJECT_ID isn't set: fail closed, never open."""
    if not config.FIREBASE_PROJECT_ID:
        raise HTTPException(503, "auth not configured")
    scheme, token = get_authorization_scheme_param(request.headers.get("Authorization"))  # same parsing as HTTPBearer
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "Not signed in", headers=_UNAUTHORIZED)
    try:
        claims = auth.verify_id_token(token, app=_firebase_app(), clock_skew_seconds=10)
    except auth.CertificateFetchError:
        raise HTTPException(503, "Could not reach Firebase to check the sign-in")
    except (ValueError, auth.InvalidIdTokenError):  # Expired/Revoked are InvalidIdTokenError subclasses
        raise HTTPException(401, "Sign-in expired or invalid", headers=_UNAUTHORIZED)
    email = (claims.get("email") or "").strip().lower()
    is_admin = email in config.ADMIN_EMAILS
    in_domain = bool(config.ALLOWED_EMAIL_DOMAIN) and email.endswith("@" + config.ALLOWED_EMAIL_DOMAIN)
    if not email or not claims.get("email_verified") or not (is_admin or in_domain):
        raise HTTPException(403, "Your account is not allowed to use this app")
    return MeOut(email=email, is_admin=is_admin)


def require_admin(request: Request) -> MeOut:
    # ponytail: verifies the token a second time on the three admin routes (local signature check, certs cached);
    # stash the result on request.state if that ever shows up in profiles.
    me = require_viewer(request)
    if not me.is_admin:
        raise HTTPException(403, "Admins only")
    return me
