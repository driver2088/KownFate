# -*- coding: utf-8 -*-
"""面向海外用户：以邮箱为账号注册登录，昵称可选。"""
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import database as db, security
from .deps import get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def _norm_email(raw):
    email = (raw or "").strip().lower()
    if not EMAIL_RE.match(email) or len(email) > 80:
        raise HTTPException(400, "请填写有效的邮箱地址")
    return email


class RegisterIn(BaseModel):
    email: str
    password: str
    nickname: str | None = None


@router.post("/register")
def register(body: RegisterIn):
    email = _norm_email(body.email)
    if len(body.password) < 6:
        raise HTTPException(400, "密码至少 6 位")
    nickname = (body.nickname or "").strip()[:20] or email.split("@")[0]
    if db.get_user(email):
        raise HTTPException(409, "该邮箱已注册，请直接登录")
    uid = db.create_user(email, nickname, security.hash_password(body.password))
    return {"token": security.make_token(uid, email),
            "user": {"id": uid, "email": email, "nickname": nickname}}


@router.post("/login")
def login(body: RegisterIn):
    email = _norm_email(body.email)
    user = db.get_user(email)
    if not user or not security.verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "邮箱或密码不正确")
    return {"token": security.make_token(user["id"], user["email"]),
            "user": {"id": user["id"], "email": user["email"],
                     "nickname": user["nickname"] or email.split("@")[0]}}


@router.get("/me")
def me(user=Depends(get_current_user)):
    row = db.get_user_by_id(user["id"])
    if not row:
        raise HTTPException(401, "用户不存在")
    final = db.get_final_chart(user["id"])
    return {"user": {"id": row["id"], "email": row["email"],
                     "nickname": row["nickname"] or row["email"].split("@")[0]},
            "has_final_chart": bool(final)}
