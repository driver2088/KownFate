# -*- coding: utf-8 -*-
"""排盘 → 校验 → 重算（最多三轮）→ 定案 的命格流程。"""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import cities, database as db
from ..bazi import engine, interpret
from ..config import MAX_VERIFY_ROUNDS
from .deps import get_current_user

router = APIRouter(prefix="/api/chart", tags=["chart"])


class ChartIn(BaseModel):
    date: str        # YYYY-MM-DD
    time: str        # HH:MM
    city: str
    gender: str      # 男 / 女


class FeedbackIn(BaseModel):
    answers: list[bool]   # 与 statements 顺序一致，True=符合


def _birth_from(body: ChartIn):
    try:
        y, m, d = (int(x) for x in body.date.split("-"))
        info = cities.lookup(body.city)
    except (ValueError, IndexError):
        raise HTTPException(400, "出生日期或出生地不合法")
    if body.time:
        try:
            hh, mi = (int(x) for x in body.time.split(":"))
            assert 0 <= hh < 24 and 0 <= mi < 60
        except (ValueError, AssertionError):
            raise HTTPException(400, "出生时间不合法")
    if body.gender not in ("男", "女"):
        raise HTTPException(400, "性别须为 男/女")
    from datetime import date as _date
    if not (1900 <= y <= _date.today().year):
        raise HTTPException(400, "暂不支持该年份")
    return {"date": body.date, "time": body.time, "city": body.city,
            "lng": info["lng"], "tz": info["tz"]}


def _payload(row):
    return {
        "chart_id": row["id"],
        "round": row["round"],
        "status": row["status"],
        "reject_rate": row["reject_rate"],
        "variant_note": json.loads(row["variant_json"]).get("note", ""),
        "chart": json.loads(row["chart_json"]),
        "fortune": json.loads(row["fortune_json"]),
        "statements": json.loads(row["statements_json"]),
    }


def _build(birth, gender, variant):
    chart = engine.compute(birth, gender, variant)
    f = interpret.fortune(chart)
    stmts = interpret.statements(chart)
    return chart, f, stmts


@router.post("/start")
def start(body: ChartIn, user=Depends(get_current_user)):
    birth = _birth_from(body)
    variant = engine.VARIANTS[0]
    chart, f, stmts = _build(birth, body.gender, variant)
    cid = db.save_chart(user["id"], 1, birth, variant, chart, f, stmts)
    row = db.get_chart(cid)
    return {"done": False, **_payload(row)}


@router.post("/{chart_id}/feedback")
def feedback(chart_id: int, body: FeedbackIn, user=Depends(get_current_user)):
    row = db.get_chart(chart_id)
    if not row or row["user_id"] != user["id"]:
        raise HTTPException(404, "命盘不存在")
    if row["status"] != "pending":
        raise HTTPException(400, "该轮命盘已定案")

    stmts = json.loads(row["statements_json"])
    if len(body.answers) != len(stmts):
        raise HTTPException(400, "答案数量与题目数不符")

    reject = sum(1 for a in body.answers if not a)
    reject_rate = reject / len(body.answers)
    round_no = row["round"]

    # 过半以上认可 或 已到最后一轮 → 定案
    if reject_rate <= 0.5 or round_no >= MAX_VERIFY_ROUNDS:
        db.update_chart_feedback(chart_id, body.answers, reject_rate, "confirmed", is_final=True)
        final = db.get_chart(chart_id)
        return {"done": True, "reject_rate": reject_rate, **_payload(final)}

    # 重算下一轮
    prev_chart = json.loads(row["chart_json"])
    birth = json.loads(row["input_json"])
    gender = prev_chart["input"]["gender"]
    next_round = round_no + 1
    variant = engine.VARIANTS[next_round - 1]
    if next_round == MAX_VERIFY_ROUNDS:
        sig_prev = engine.pillars_sig(prev_chart)
        trial = engine.compute(birth, gender, variant)
        if engine.pillars_sig(trial) == sig_prev:
            variant = engine.VARIANT_R3_ALT  # 四柱未变则换取用方法
    chart, f, stmts = _build(birth, gender, variant)
    new_id = db.save_chart(user["id"], next_round, birth, variant, chart, f, stmts)

    # 当前轮答案归档（仍标 rejected）
    db.update_chart_feedback(chart_id, body.answers, reject_rate, "rejected", is_final=False)
    new_row = db.get_chart(new_id)
    return {"done": False, "reject_rate": reject_rate,
            "recomputed_reason": f"否定率 {reject_rate:.0%} 超过 50%，{variant['note']}",
            **_payload(new_row)}


@router.get("/current")
def current(user=Depends(get_current_user)):
    row = db.get_final_chart(user["id"])
    if not row:
        return {"none": True}
    return {"none": False, **_payload(row)}


@router.get("/archive")
def archive(user=Depends(get_current_user)):
    rows = db.list_user_charts(user["id"])
    out = []
    for r in rows:
        out.append({"chart_id": r["id"], "round": r["round"], "status": r["status"],
                    "is_final": bool(r["is_final"]), "reject_rate": r["reject_rate"],
                    "variant_note": json.loads(r["variant_json"]).get("note", ""),
                    "created_at": r["created_at"]})
    final = db.get_final_chart(user["id"])
    return {"charts": out, "final_chart_id": final["id"] if final else None}


@router.get("/{chart_id}")
def detail(chart_id: int, user=Depends(get_current_user)):
    row = db.get_chart(chart_id)
    if not row or row["user_id"] != user["id"]:
        raise HTTPException(404, "命盘不存在")
    return _payload(row)
