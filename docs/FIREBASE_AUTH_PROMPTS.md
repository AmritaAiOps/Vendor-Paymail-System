# Firebase Auth: build prompts

Prompts to add Firebase Authentication, in the same format as the phase prompts in the build-prompts doc.

**Before you start.** The project dropped login on purpose: `docs/CONTRACT.md` says "No login", migration `d5e6b626650d` removed the `who` / `uploaded_by` columns, and the old JWT Phase 8A was never built. That means adding Firebase changes the contract, so both people have to agree to it first (Prompt 1). The contract test counts 22 endpoints and 10 functions, so it will fail until the contract is updated.

**How it works:** the browser signs in with the Firebase JS SDK and sends the ID token as `Authorization: Bearer <token>`. The backend checks the token with `firebase-admin`, which only needs the project ID, so there's no service-account secret. Roles come from env lists (`ADMIN_EMAILS`, `ALLOWED_EMAIL_DOMAIN`), so no custom-claims script is needed. You don't need `POST /api/auth/login` because Firebase handles login; you only add `GET /api/auth/me`.

---

## Before you start (Firebase console, done by hand)

1. Create a Firebase project. Under Authentication → Sign-in method, turn on **Email/Password** (and Google if your company uses Google Workspace).
2. Add the users yourself under Authentication → Users. The app has no sign-up screen.
3. Under Project settings → General → Your apps, add a Web app and copy its config (`apiKey`, `authDomain`, `projectId`, `appId`). This config is public, not a secret.
4. Under Authentication → Settings → Authorized domains, add your production host.

---

## Prompt 1: Contract change (both people agree, then one person commits it)

```
Phase 9-0: Contract change for Firebase login. SHARED: both people agree before this is committed.

We are replacing "No login" with Firebase Authentication. Update docs/CONTRACT.md, app/schemas.py, app/routers/__init__.py and the contract test in ONE commit:

1. Conventions: replace the "No login" bullet with: "Login is Firebase Authentication. The frontend signs in with the Firebase JS SDK and sends the Firebase ID token as `Authorization: Bearer <token>` on every /api request. The backend verifies it with firebase-admin (project FIREBASE_PROJECT_ID). Every endpoint except GET /api/health needs a valid token from a verified email that is in ALLOWED_EMAIL_DOMAIN or ADMIN_EMAILS (401 no/bad/expired token, 403 not allowed). Admin = email in ADMIN_EMAILS. Admin-only: POST /api/scheduler/run-now, POST /api/email-history/rebuild-xlsx, PUT /api/settings (403 for non-admin)."
2. Folder ownership: add backend/app/auth and backend/app/routers/auth.py to Person A. Mirror it in .github/CODEOWNERS.
3. Endpoint table (b): add `GET | /api/auth/me | A | none | MeOut` (MeOut = {email: str, is_admin: bool}). Add "(admin)" to the three admin rows and remove "No admin check: there is no login" from run-now. Add MeOut to schemas.py.
4. Function table (c): add `app.auth | require_viewer | (authorization) -> Me` and `app.auth | require_admin | (user) -> Me`, owner A, caller A+B. Use the exact signatures the stubs will have.
5. Stubs: create backend/app/auth/__init__.py with require_viewer and require_admin as pass-through stubs (# STUB(contract)), returning a fixed admin Me. Create routers/auth.py with a stub GET /api/auth/me (STUB dependency, X-Stub header). Register it in main.py, and in that same edit attach Depends(require_viewer) to every router except health, in the include_router loop, so no route file has to change for that. Attach Depends(require_admin) to the three admin routes, each in its owner's file.
6. Update the counts in tests/contract/test_contract.py (endpoints 22 -> 23, functions 10 -> 12). Run the contract test.
7. .env.example: under the A block add FIREBASE_PROJECT_ID=, ALLOWED_EMAIL_DOMAIN=, ADMIN_EMAILS= (comma-separated). Under the B block add VITE_FIREBASE_API_KEY=, VITE_FIREBASE_AUTH_DOMAIN=, VITE_FIREBASE_PROJECT_ID=, VITE_FIREBASE_APP_ID=.

Don't change any other route signature. End with "Contract impact:" listing exactly what changed.
```

## Prompt 2: Backend (Person A, branch track-a/engine)

```
Phase 9A: Firebase auth, backend. PERSON A | ENGINE. Your folders: auth, routers/auth.py, config.py, tests. Don't change any route signature. Do this after Phase 9-0 is committed.

1. config.py: FIREBASE_PROJECT_ID, ALLOWED_EMAIL_DOMAIN (lower-cased, no "@"), ADMIN_EMAILS (set of lower-cased, stripped emails). Env only, never in app_settings.
2. backend/app/auth: replace the stub bodies.
   - require_viewer: read the Bearer token with FastAPI's HTTPBearer(auto_error=False). Verify it with firebase_admin.auth.verify_id_token (initialize the app once with options={"projectId": FIREBASE_PROJECT_ID}, no service account; use clock_skew_seconds=10). Return 401 with WWW-Authenticate: Bearer for a missing, malformed, expired or wrong-project token. Return 403 if email_verified is false, or the email is neither in ADMIN_EMAILS nor in ALLOWED_EMAIL_DOMAIN. Return Me(email, is_admin).
   - require_admin: depends on require_viewer, 403 unless is_admin.
   - If FIREBASE_PROJECT_ID is empty, fail closed: every protected route returns 503 "auth not configured". Never fall back to open access.
3. GET /api/auth/me: real implementation returning MeOut. Remove its STUB / X-Stub.
4. requirements.txt (A block): firebase-admin, pinned.
5. Tests, with no network (mock firebase_admin.auth.verify_id_token):
   - no token, garbage token, expired token (verify raises ExpiredIdTokenError), wrong project (InvalidIdTokenError) -> 401
   - unverified email, outside domain -> 403
   - viewer gets 403 on all three admin routes; admin gets through
   - /api/health stays open
   - /api/auth/me returns the right email and is_admin
   - in tests/conftest.py, override require_viewer/require_admin through app.dependency_overrides for the existing test suite so the old tests stay green without tokens.
6. Run the full suite and the contract test.

Ponytail notes: use firebase-admin's verify_id_token, never decode JWTs by hand. No user table: Firebase is the user store and env lists are the roles. Don't cut anything on token checks. Mark every shortcut with a "ponytail:" comment.
End with "Contract impact:".
```

## Prompt 3: Frontend (Person B, branch track-b/delivery)

```
Phase 9B: Firebase login screen. PERSON B | DELIVERY. Your folders: frontend. Person A's /api/auth/me may still be a stub; build against the contract shape (MeOut).

1. Add the `firebase` npm package. In src/firebase.ts, call initializeApp with the four VITE_FIREBASE_* env vars and export getAuth(app). Nothing else goes in this file.
2. Login screen: email + password through signInWithEmailAndPassword, plus a "Forgot password" link using sendPasswordResetEmail. No sign-up screen (admins create users in the Firebase console). Show Firebase errors in plain words (wrong password, user not found, too many attempts). Labelled inputs, keyboard-usable.
3. Session: Firebase keeps the user signed in (default persistence). Use onAuthStateChanged as the single source of the signed-in state. After sign-in, call GET /api/auth/me. On 403, show "Your account is not allowed to use this app" and sign out.
4. API client (src/api/client.ts): before every request, `await auth.currentUser?.getIdToken()` (the SDK refreshes it itself) and set Authorization: Bearer <token>. On 401, sign out and go to the login screen. Don't store the token yourself anywhere.
5. Role-aware UI: hide Run now, Rebuild history file and Settings edits when me.is_admin is false. This is for comfort only; the server enforces roles.
6. A Sign out button in the header (signOut).
7. Every route except /login goes behind a guard that waits for the first onAuthStateChanged callback (show a loader, not a flash of the login page).

Ponytail notes: no auth library on top of the Firebase SDK, no hand-rolled token storage or refresh, no context-provider tower: one small hook (useAuth) is enough.
End with "Contract impact:".
```

## Prompt 4: Merge check (after both tracks merge)

```
Firebase auth merge check:
1. grep: no "# STUB(contract)" and no X-Stub left in auth or routers/auth.py.
2. With a real Firebase project and two test users (one in ADMIN_EMAILS, one only in the domain): sign in as each through the UI. Confirm the viewer can't see admin actions and gets 403 from curl on the three admin routes; the admin can use them. A request without a token gets 401, and /api/health is open.
3. Wait over an hour (or force-refresh the token) and confirm the UI keeps working, which shows the SDK token refresh is wired up.
4. Contract test and full suite green. Docker: FIREBASE_PROJECT_ID is passed to the app container, and the VITE_* vars are passed at frontend build time.
```

---

## Left out on purpose

- **Who did what in `audit_log`.** The `who` column was dropped earlier. If you want each change logged with the user's email again, Person A adds a migration that restores `audit_log.who` and passes `me.email` into it.
- **Firebase custom claims for roles.** The `ADMIN_EMAILS` env list does the same job without a separate admin script. It's worth switching only if the admin list starts changing often.
