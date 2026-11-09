# -*- coding: utf-8 -*-
"""排盘 → 校验 → 重拟（最多三轮）→ 定案 的命格流程。

校验共 5 题（由 AI 从已发生的大运与流年中择题写断言，AI 不可用时回退本地模板），5 题至少 4 题符合才定案；
未通过优先请 AI 依子平复核喜用并重评岁运——推演主旨逐轮递变：一轮扶抑为主（定式排盘）、
二轮调候为主、三轮综合两派；AI 不可用时回退流派重排。
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import cities, database as db
from ..bazi import engine, interpret, recalibrate
from ..config import MAX_VERIFY_ROUNDS
from .deps import get_current_user

PASS_AGREE = 4  # 5 题至少算准 4 题
_LM_NAMES = ["正月", "二月", "三月", "四月", "五月", "六月",
             "七月", "八月", "九月", "十月", "冬月", "腊月"]


def _lm(m: int) -> str:
    return _LM_NAMES[m - 1] if 1 <= m <= 12 else f"{m}月"

router = APIRouter(prefix="/api/chart", tags=["chart"])


class ChartIn(BaseModel):
    date: str        # YYYY-MM-DD（公历或农历，视 calendar）
    time: str        # HH:MM
    city: str
    gender: str      # 男 / 女
    calendar: str = "solar"   # solar 公历 | lunar 农历
    leap: bool = False        # 农历闰月


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
    if body.calendar not in ("solar", "lunar"):
        raise HTTPException(400, "历法须为 公历/农历")
    from datetime import date as _date
    if not (1900 <= y <= _date.today().year):
        raise HTTPException(400, "暂不支持该年份")
    birth = {"date": body.date, "time": body.time, "city": body.city,
             "lng": info["lng"], "tz": info["tz"]}
    if body.calendar == "lunar":
        birth["calendar"] = "lunar"
        birth["leap"] = bool(body.leap)
        if not (1 <= m <= 12 and 1 <= d <= 30):
            raise HTTPException(400, "农历日期不合法（月 1-12，日 1-30）")
        from lunar_python import Lunar
        try:
            lm = -m if body.leap else m
            solar = Lunar.fromYmdHms(y, lm, d, 12, 0, 0).getSolar()
            back = solar.getLunar()   # 回转校验：闰月是否存在、日是否越界
            if back.getMonth() != lm or back.getDay() != d:
                raise HTTPException(400, f"农历{y}年{'闰' if body.leap else ''}{_lm(m)}{d}日不存在，请核对")
        except HTTPException:
            raise
        except Exception as e:
            msg = str(e)
            import re as _re
            mlen = _re.search(r"only (\d+) days", msg)
            if mlen:
                raise HTTPException(400, f"农历{y}年{'闰' if body.leap else ''}{_lm(m)}只有 {mlen.group(1)} 天，无{d}日")
            if "wrong lunar year" in msg:
                raise HTTPException(400, f"农历{y}年没有闰{_lm(m)}，请取消闰月或改正月份")
            raise HTTPException(400, f"农历日期不合法：{msg}")
    return birth


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


def _pick_statements(chart):
    """出题：优先由 AI 从大运流年挑 5 段清晰可判的时段写断言；
    AI 不可用或输出不合契约时回退本地模板出题。"""
    stmts = recalibrate.choose_statements(chart)
    if stmts and len(stmts) == 5:
        return stmts
    return interpret.statements(chart)[:5]


def _build(birth, gender, variant):
    chart = engine.compute(birth, gender, variant)
    f = interpret.fortune(chart)
    stmts = _pick_statements(chart)
    return chart, f, stmts


@router.post("/start")
def start(body: ChartIn, user=Depends(get_current_user)):
    birth = _birth_from(body)
    variant = engine.VARIANTS[0]
    chart, f, stmts = _build(birth, body.gender, variant)
    if len(stmts) != 5:
        stmts = stmts[:5]
    cid = db.save_chart(user["id"], 1, birth, variant, chart, f, stmts)
    row = db.get_chart(cid)
    return {"done": False, **_payload(row)}


@router.post("/{chart_id}/feedback")
def feedback(chart_id: int, body: FeedbackIn, user=Depends(get_current_user)):
    row = db.get_chart(chart_id)
    if not row or row["user_id"] != user["id"]:
        raise HTTPException(404, "命盘不存在")
    if row["status"] != "pending":
        raise HTTPException(400, "该轮校验结果已提交过")

    stmts = json.loads(row["statements_json"])
    if len(body.answers) != len(stmts):
        raise HTTPException(400, "答案数量与题目数不符")

    total = len(body.answers)
    agree = sum(1 for a in body.answers if a)
    reject_rate = (total - agree) / total
    round_no = row["round"]

    prev_chart = json.loads(row["chart_json"])
    birth = json.loads(row["input_json"])
    gender = prev_chart["input"]["gender"]

    history = list(prev_chart.get("verify_history") or [])
    history.append({
        "round": round_no, "agree": f"{agree}/{total}",
        "agree_n": agree,
        "rejected": [st["text"][:60] for st, a in zip(stmts, body.answers) if not a],
    })

    # 4/5 算准 → 定案（校验履历并入命盘，供 AI 答疑引用）
    if agree >= PASS_AGREE:
        final_chart = dict(prev_chart, verify_history=history)
        db.set_chart_json(chart_id, final_chart)
        db.update_chart_feedback(chart_id, body.answers, reject_rate, "confirmed", is_final=True)
        final = db.get_chart(chart_id)
        return {"done": True, "agree": agree, "reject_rate": reject_rate, **_payload(final)}

    # 三轮打磨仍未达标 → 不定案、不存档，请命主核对生辰后重排
    if round_no >= MAX_VERIFY_ROUNDS:
        final_chart = dict(prev_chart, verify_history=history)
        db.set_chart_json(chart_id, final_chart)
        db.update_chart_feedback(chart_id, body.answers, reject_rate, "failed", is_final=False)
        return {
            "done": False, "failed": True, "agree": agree, "reject_rate": reject_rate,
            "message": (f"三轮命格校验均未通过（本轮仅算准 {agree}/{total} 题），本次不予定案存档。\n"
                        f"命不立则盘不成——多半是出生日期、出生时间（请精确到分钟与子时早晚）"
                        f"或出生地填报有偏差。请核对修正后重新提交排盘，我们再走一轮。"),
        }

    # —— 重拟下一轮 ——
    next_round = round_no + 1
    calib = recalibrate.recalibrate(prev_chart, stmts, body.answers, round_no, next_round)
    if calib:
        chart = engine.apply_ai_adjustment(prev_chart, calib)
        chart["verify_history"] = history
        variant = {"round": next_round, "ai_adjust": True,
                   "note": f"校验未过，AI 依子平复核重定喜用，重取用神为{chart['xiyong']['yong_shen']}",
                   "focus": calib["school"], "reason": calib.get("reason", "")}
        method = "ai"
        f = interpret.fortune(chart)
        stmts_new = _pick_statements(chart)   # 喜用已变，题面随新盘重择
    else:
        variant = engine.VARIANTS[min(next_round, MAX_VERIFY_ROUNDS) - 1]
        if next_round == MAX_VERIFY_ROUNDS:
            sig_prev = engine.pillars_sig(prev_chart)
            trial = engine.compute(birth, gender, variant)
            if engine.pillars_sig(trial) == sig_prev:
                variant = engine.VARIANT_R3_ALT  # 四柱未变则换取用方法
        chart, f, stmts_new = _build(birth, gender, variant)
        chart["verify_history"] = history
        method = "variant"
    new_id = db.save_chart(user["id"], next_round, birth, variant, chart, f, stmts_new)
    db.update_chart_feedback(chart_id, body.answers, reject_rate, "rejected", is_final=False)

    new_row = db.get_chart(new_id)
    return {"done": False, "agree": agree, "reject_rate": reject_rate, "method": method,
            "recomputed_reason": f"仅算准 {agree}/{total} 题（需 {PASS_AGREE} 题及以上），{variant['note']}",
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
