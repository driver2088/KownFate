# -*- coding: utf-8 -*-
import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
# override=True：本项目的 .env 配置优先于 shell 里继承来的全局变量
# （例如 Claude Code 自身的 ANTHROPIC_BASE_URL 代理设置）
load_dotenv(BASE_DIR / ".env", override=True)

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = os.environ.get("KOWNFATE_DB", str(DATA_DIR / "kownfate.db"))
FRONTEND_DIR = BASE_DIR / "frontend"


def _jwt_secret():
    s = os.environ.get("JWT_SECRET")
    if s:
        return s
    p = DATA_DIR / ".jwt_secret"
    if not p.exists():
        p.write_text(secrets.token_hex(32))
    return p.read_text().strip()


JWT_SECRET = _jwt_secret()
JWT_ALG = "HS256"
TOKEN_TTL_HOURS = int(os.environ.get("TOKEN_TTL_HOURS", "72"))

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL") or None
CLAUDE_MODEL = os.environ.get("KOWNFATE_MODEL", "claude-opus-5-5")
CLAUDE_MAX_TOKENS = int(os.environ.get("KOWNFATE_MAX_TOKENS", "16000"))

MAX_CHAT_ROUNDS = 3   # 每次答疑对话限定轮数
MAX_VERIFY_ROUNDS = 3  # 命格校验最多重算轮数
