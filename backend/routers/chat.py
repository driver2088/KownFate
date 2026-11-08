# -*- coding: utf-8 -*-
"""AI 大事答疑：命格注入系统信息，每次咨询限 3 轮，全程存档。"""
import json

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import config, database as db
from ..bazi import interpret
from .deps import get_current_user

router = APIRouter(prefix="/api/chat", tags=["chat"])

_client = None


def _client_or_503():
    global _client
    if _client is None:
        if not config.ANTHROPIC_API_KEY:
            raise HTTPException(503,
                "AI 先生暂未就位：请在 .env 中配置 ANTHROPIC_API_KEY 后重启服务。")
        kwargs = {"api_key": config.ANTHROPIC_API_KEY}
        if config.ANTHROPIC_BASE_URL:
            kwargs["base_url"] = config.ANTHROPIC_BASE_URL
        _client = anthropic.Anthropic(**kwargs)
    return _client


SYSTEM_TEMPLATE = """你是「知天命」网站的命理答疑先生，法号知微。网站口号：早知命早改命。
你精通子平八字（五行、十神、强弱、喜用神、大运流年），为命主解答事业抉择、婚恋时机、财运节奏、流年趋避等人生大事。

作答要求：
1. 一切结论以【命主八字命格】为依据，援引五行十神生克要简短明白，不许全盘复述命盘。
2. 语气温和笃定，文白相间；不做绝对宿命论断，不恐吓，不给医疗、法律、投资标的的确定性指令，重在"何时宜进、何时宜守、如何借力"。
3. 本次咨询总共 {total} 轮，这是第 {no} 轮（剩余 {left} 轮，含本轮）。请在有限轮次内给出可执行要点，结尾以一句话温和提醒剩余轮次。
4. 使用简体中文，300-600 字，可分点。

{summary}"""


class ChatIn(BaseModel):
    conversation_id: int | None = None
    text: str


def _chart_for_user(uid):
    row = db.get_final_chart(uid)
    if not row:
        raise HTTPException(400, "请先完成八字排盘与命格校验")
    return row


@router.post("/send")
def send(body: ChatIn, user=Depends(get_current_user)):
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "问题不能为空")
    if len(text) > 600:
        raise HTTPException(400, "单次提问请控制在 600 字以内")

    chart_row = _chart_for_user(user["id"])

    if body.conversation_id:
        conv = db.get_conversation(body.conversation_id, user["id"])
        if not conv:
            raise HTTPException(404, "对话不存在")
        conv_id = conv["id"]
    else:
        conv_id = db.create_conversation(user["id"], chart_row["id"], text[:30])

    used = db.count_user_messages(conv_id)
    if used >= config.MAX_CHAT_ROUNDS:
        raise HTTPException(400, f"本次咨询限 {config.MAX_CHAT_ROUNDS} 轮，已用完；请开启新的咨询。")

    history = db.get_messages(conv_id)
    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": text})

    summary = interpret.summary_text(json.loads(chart_row["chart_json"]),
                                     json.loads(chart_row["fortune_json"]))
    system = SYSTEM_TEMPLATE.format(total=config.MAX_CHAT_ROUNDS, no=used + 1,
                                    left=config.MAX_CHAT_ROUNDS - used, summary=summary)

    try:  # AI 成功后才落库，避免失败请求占用轮次
        resp = _client_or_503().messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=config.CLAUDE_MAX_TOKENS,
            system=system,
            messages=messages,
        )
    except anthropic.APIStatusError as e:
        status = getattr(e, "status_code", 0)
        if status == 429:
            raise HTTPException(429, "AI 先生正被众多缘主问询，请稍后再试")
        if status == 401:
            raise HTTPException(502, "ANTHROPIC_API_KEY 无效，请检查 .env 配置")
        raise HTTPException(502, f"AI 服务暂时不可用（{status}），缘主稍后再试")
    except anthropic.APIConnectionError:
        raise HTTPException(502, "无法连接 AI 服务，请检查网络后重试")

    reply = "".join(b.text for b in resp.content if b.type == "text").strip()
    if not reply:
        reply = "天机沉吟半晌未语——请换个问法再试一次。"
    db.add_message(conv_id, "user", text)
    db.add_message(conv_id, "assistant", reply)

    rounds_used = db.count_user_messages(conv_id)
    return {
        "conversation_id": conv_id,
        "reply": reply,
        "rounds_used": rounds_used,
        "rounds_left": config.MAX_CHAT_ROUNDS - rounds_used,
        "closed": rounds_used >= config.MAX_CHAT_ROUNDS,
    }


@router.get("/conversations")
def conversations(user=Depends(get_current_user)):
    out = []
    for c in db.list_conversations(user["id"]):
        msgs = db.get_messages(c["id"])
        out.append({
            "id": c["id"], "title": c["title"], "chart_id": c["chart_id"],
            "created_at": c["created_at"],
            "rounds_used": sum(1 for m in msgs if m["role"] == "user"),
            "preview": next((m["content"] for m in msgs if m["role"] == "user"), ""),
        })
    return {"conversations": out, "max_rounds": config.MAX_CHAT_ROUNDS}


@router.get("/conversations/{conv_id}")
def conversation_detail(conv_id: int, user=Depends(get_current_user)):
    conv = db.get_conversation(conv_id, user["id"])
    if not conv:
        raise HTTPException(404, "对话不存在")
    msgs = db.get_messages(conv_id)
    return {"id": conv["id"], "title": conv["title"], "chart_id": conv["chart_id"],
            "max_rounds": config.MAX_CHAT_ROUNDS,
            "rounds_used": sum(1 for m in msgs if m["role"] == "user"),
            "messages": [{"role": m["role"], "content": m["content"], "created_at": m["created_at"]}
                         for m in msgs]}
