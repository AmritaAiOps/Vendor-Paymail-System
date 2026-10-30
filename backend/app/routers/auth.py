from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.routers import stub

router = APIRouter(prefix="/auth", tags=["auth"])


class Login(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: Login):
    return stub({"username": body.username})


@router.post("/logout", status_code=204)
def logout():
    return Response(status_code=204, headers={"X-Stub": "true"})


@router.get("/me")
def me():
    return stub({"username": "admin"})
