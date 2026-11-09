# -*- coding: utf-8 -*-
"""公共依赖：登录态解析。"""
from fastapi import Depends, HTTPException, Request

from .. import security


def get_current_user(request: Request):
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(401, "请先登录")
    payload = security.decode_token(header[7:])
    if not payload:
        raise HTTPException(401, "登录已过期，请重新登录")
    return {"id": int(payload["sub"]), "email": payload["name"]}
