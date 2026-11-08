# -*- coding: utf-8 -*-
"""知天命 · 早知命早改命 —— FastAPI 主应用。"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import cities, config, database as db
from .routers import auth, chart, chat

app = FastAPI(title="知天命", description="早知命早改命 · AI 八字命理")


@app.on_event("startup")
def _startup():
    db.init()


@app.get("/api/health")
def health():
    return {"ok": True, "name": "知天命", "slogan": "早知命早改命",
            "ai_ready": bool(config.ANTHROPIC_API_KEY),
            "model": config.CLAUDE_MODEL}


@app.get("/api/cities")
def api_cities():
    return {"groups": cities.grouped()}


app.include_router(auth.router)
app.include_router(chart.router)
app.include_router(chat.router)

app.mount("/", StaticFiles(directory=str(config.FRONTEND_DIR), html=True), name="frontend")
