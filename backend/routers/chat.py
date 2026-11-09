# -*- coding: utf-8 -*-
"""AI 大事答疑：命格注入系统信息，每次咨询限 3 轮，全程存档，支持流式输出。"""
import json

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import ai, config, database as db
from ..bazi import interpret
from .deps import get_current_user

router = APIRouter(prefix="/api/chat", tags=["chat"])

SYSTEM_TEMPLATE = """你是「知天命」网站的命理答疑先生，法号知微。网站口号：早知命早改命。
你精通子平八字（五行、十神、强弱、喜用神、大运流年），为命主解答事业抉择、婚恋时机、财运节奏、流年趋避等人生大事。

推演准则：
0. 一切推算以子平命理为宗：以日主为主、月令为纲，扶抑看强弱定喜忌（身弱取印比生扶、身强取克泄耗为用），同时兼参调候取向（月令寒暖燥湿宜取何神调候）；两派取用有出入时，内部权衡定盘、不可只执一端——但门派与推演策略只作你的立论根基，答语中不要向命主复述"扶抑/调候"等门径术语，直取用神、五行与应期而言。
1. 一切结论以【命主八字命格】为依据，援引五行十神生克要简短明白，不许全盘复述命盘。
2. 命格附有历轮校验反馈的，被命主判定"不符合"的断语不要再复述为事实，应在新取向（扶抑/调候取舍）下给出修正后的判断。
3. 语气温和笃定，文白相间；不做绝对宿命论断，不恐吓，不给医疗、法律、投资标的的确定性指令，重在"何时宜进、何时宜守、如何借力"。
4. 本次咨询总共 {total} 轮，这是第 {no} 轮（剩余 {left} 轮，含本轮）。请在有限轮次内给出可执行要点，结尾以一句话温和提醒剩余轮次。
5. 使用简体中文，300-600 字，可分点。

{summary}"""


class ChatIn(BaseModel):
    conversation_id: int | None = None
    text: str


def _chart_for_user(uid):
    row = db.get_final_chart(uid)
    if not row:
        raise HTTPException(400, "请先完成八字排盘与命格校验")
    return row


def _prepare(body: ChatIn, user):
    """校验并组装（会话、消息、system）。返回 (conv_id, messages, system, used)。"""
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

    messages = [{"role": m["role"], "content": m["content"]} for m in db.get_messages(conv_id)]
    messages.append({"role": "user", "content": text})

    summary = interpret.summary_text(json.loads(chart_row["chart_json"]),
                                     json.loads(chart_row["fortune_json"]))
    system = SYSTEM_TEMPLATE.format(total=config.MAX_CHAT_ROUNDS, no=used + 1,
                                    left=config.MAX_CHAT_ROUNDS - used, summary=summary)
    return conv_id, text, messages, system, used


@router.post("/send")
def send(body: ChatIn, user=Depends(get_current_user)):
    conv_id, text, messages, system, used = _prepare(body, user)
    client = ai.get_client()
    if client is None:
        raise HTTPException(503, "AI 先生暂未就位：请在 .env 中配置 ANTHROPIC_API_KEY 后重启服务。")

    try:  # AI 成功后才落库，避免失败请求占用轮次
        resp = client.messages.create(
            model=config.CLAUDE_MODEL, max_tokens=config.CLAUDE_MAX_TOKENS,
            system=system, messages=messages)
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
        status, msg = ai.http_status_for(e)
        raise HTTPException(status, msg)

    reply = "".join(b.text for b in resp.content if b.type == "text").strip()
    if not reply:
        reply = "天机沉吟半晌未语——请换个问法再试一次。"
    db.add_message(conv_id, "user", text)
    db.add_message(conv_id, "assistant", reply)

    rounds_used = db.count_user_messages(conv_id)
    return {"conversation_id": conv_id, "reply": reply,
            "rounds_used": rounds_used,
            "rounds_left": config.MAX_CHAT_ROUNDS - rounds_used,
            "closed": rounds_used >= config.MAX_CHAT_ROUNDS}


def _sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/stream")
def stream(body: ChatIn, user=Depends(get_current_user)):
    """SSE 流式答疑：event 为 meta/delta/done/error。"""
    conv_id, text, messages, system, used = _prepare(body, user)
    client = ai.get_client()
    if client is None:
        raise HTTPException(503, "AI 先生暂未就位：请在 .env 中配置 ANTHROPIC_API_KEY 后重启服务。")

    def gen():
        yield _sse("meta", {"conversation_id": conv_id, "round": used + 1,
                           "rounds_left": config.MAX_CHAT_ROUNDS - used})
        buf = []
        try:
            with client.messages.stream(
                    model=config.CLAUDE_MODEL, max_tokens=config.CLAUDE_MAX_TOKENS,
                    system=system, messages=messages) as s:
                for chunk in s.text_stream:
                    buf.append(chunk)
                    yield _sse("delta", {"text": chunk})
            reply = "".join(buf).strip()
            if not reply:
                reply = "天机沉吟半晌未语——请换个问法再试一次。"
            db.add_message(conv_id, "user", text)
            db.add_message(conv_id, "assistant", reply)
            rounds_used = db.count_user_messages(conv_id)
            yield _sse("done", {"reply": reply, "rounds_used": rounds_used,
                                "rounds_left": config.MAX_CHAT_ROUNDS - rounds_used,
                                "closed": rounds_used >= config.MAX_CHAT_ROUNDS})
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
            status, msg = ai.http_status_for(e)
            yield _sse("error", {"status": status, "message": msg})
        except Exception:
            yield _sse("error", {"status": 500, "message": "答疑中断，本轮未计入轮次，请重试"})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no",
                                      "Connection": "keep-alive"})


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
