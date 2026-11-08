# -*- coding: utf-8 -*-
"""口令散列与 JWT。"""
import time
import jwt
import bcrypt

from . import config


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), hashed.encode())
    except ValueError:
        return False


def make_token(user_id: int, username: str) -> str:
    now = int(time.time())
    payload = {"sub": str(user_id), "name": username, "iat": now,
               "exp": now + config.TOKEN_TTL_HOURS * 3600}
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALG)


def decode_token(token: str):
    try:
        return jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALG])
    except jwt.PyJWTError:
        return None
