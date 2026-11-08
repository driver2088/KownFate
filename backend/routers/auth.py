# -*- coding: utf-8 -*-
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import database as db, security
from .deps import get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])

NAME_RE = re.compile(r"^[\w一-龥]{2,20}$")


class RegisterIn(BaseModel):
    username: str
    password: str


@router.post("/register")
def register(body: RegisterIn):
    username = body.username.strip()
    if not NAME_RE.match(username):
        raise HTTPException(400, "用户名需为 2-20 个文字、字母、数字或下划线")
    if len(body.password) < 6:
        raise HTTPException(400, "密码至少 6 位")
    if db.get_user(username):
        raise HTTPException(409, "该用户名已被占用")
    uid = db.create_user(username, security.hash_password(body.password))
    return {"token": security.make_token(uid, username),
            "user": {"id": uid, "username": username}}


@router.post("/login")
def login(body: RegisterIn):
    user = db.get_user(body.username.strip())
    if not user or not security.verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "用户名或密码不正确")
    return {"token": security.make_token(user["id"], user["username"]),
            "user": {"id": user["id"], "username": user["username"]}}


@router.get("/me")
def me(user=Depends(get_current_user)):
    row = db.get_user_by_id(user["id"])
    if not row:
        raise HTTPException(401, "用户不存在")
    final = db.get_final_chart(user["id"])
    return {"user": {"id": row["id"], "username": row["username"]},
            "has_final_chart": bool(final)}
