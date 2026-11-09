# -*- coding: utf-8 -*-
"""命格校验相关的 AI 服务。

1. choose_statements(chart)：AI 出题——从大运表与流年信号池中挑选
   5 个已发生、信号清晰、可核对的时段写断言（大运 1~2 条、流年补足）；
   返回 None 时由调用方回退 interpret.statements 的本地模板出题。
2. recalibrate(...)：校验未通过时的 AI 复核——把校验结果连同命盘交给
   大模型，要求它依据子平命理重新核定强弱与喜用神。三轮复核主旨递进：
   第 1 轮以扶抑为主，调候参校；第 2 轮改以调候为主，扶抑参校；
   第 3 轮综合两派，就命主历轮反馈折衡定盘。
   返回合法 JSON 则用于 engine.apply_ai_adjustment 重排岁运；
   失败/未配置密钥返回 None，由调用方回退到流派重排（VARIANTS）。
"""
import json
import re
from datetime import datetime

from .. import ai, config
from . import interpret, tables as T

FOCUS = {
    1: ("本轮以扶抑为主：重审月令提纲、通根透干与干支配置，日主强弱与喜忌以扶抑为纲"
        "（身弱取印比、身强取克泄耗）；调候仅作参校，除非命主反馈明显指向寒暖燥湿之应，"
        "不轻易改从调候取用。", "扶抑为主"),
    2: ("本轮以调候为主：首辨月令寒暖燥湿，依穷通宝鉴就日主天干细取调候之字为用神；"
        "扶抑强弱退居参校。若调候之神与扶抑取用相左，以调候定盘，并交代扶抑上如何照应。",
        "调候为主"),
    3: ("本轮为终审：扶抑、调候两条思路各自完整推演一遍，比较何者与命主历轮校验反馈"
        "更为自洽，取最能圆摄全部反馈者定盘；两派皆难尽善时取折中之局，并明言出入所在。",
        "综合判断"),
}


def _system_for(round_no):
    focus, label = FOCUS.get(round_no, FOCUS[3])
    return f"""你是子平命理大家，受托复核一份八字命格的推算。
原推断经用户以自身经历校验后有多条不符。
你的任务：复核原局，重新核定日主强弱与喜用神。
{focus}
通则：
1. 四柱干支是既定事实，不得改动，只重判强弱与喜忌；
2. 命主的"不符合"反馈是最重要的实测依据，被否定的断语所依托的用神/大运判断应优先重审；
3. 最终取用必须与本轮主旨相符，并在 reason 中点明"{label}"的取舍脉络；
4. 扶抑与调候结论有出入时，按本轮主旨定取舍并说明。
只输出一个 JSON 对象，不要其他文字，字段：
{{"level": "身强|身弱|中和", "yong_shen": "五行之一", "yong_shishen": "十神之一",
 "xi_shen": ["五行", ...], "ji_shen": ["五行", ...],
 "detail": "一句话新强弱断语", "reason": "复核思路要点（80字内）",
 "tiaohou_note": "调候角度的取舍说明（50字内）"}}"""


def focus_label(round_no):
    return FOCUS.get(round_no, FOCUS[3])[1]


CHOOSE_SYSTEM = """你是子平命理大家，正在为命主出「命格校验」题。
给定其四柱、喜忌、大运表与流年信号（score 由岁运干支对喜忌计分推得，冲=岁支冲日支或月支）。
任务：从**已经发生**的大运与流年中，挑选信号最清晰、命主最易判断的 5 个时段，各写一条断言。
要求：
1. 大运断言 1~2 条（讲十年基调），流年断言补足其余（单年事件感更强）；
2. 每条必须绑定具体年份或大运起止，写出该段干支与命主当时岁数；
3. 依十神象义落到实事：官杀主职务与压力、财星主钱与家庭、食伤主表达技术、印主学业长辈平台、比劫主同侪竞争合伙；
4. 吉凶直言，不许两头堵：喜用得力之年断顺境与成就，忌神相冲之年断阻力、变动、紧绷；
5. 禁止巴纳姆泛语（"有过起伏""遇到抉择"这类无法核对的措辞）；
6. 只依据给定信号选时段，不得虚构年份、不得改动四柱。
只输出一个 JSON 对象，不要其他文字：
{"items": [{"category": "大运|流年", "text": "断语"}, ...]}，items 恰 5 条、按时间先后排列。"""


def _year_signals_block(chart):
    dy = [f"  {d['start_year']}-{d['end_year']} {d['ganzhi']}运（天干{d['gan_shishen']}，断{d['luck']}）"
          for d in chart["dayun"] if d["start_year"] <= datetime.now().year]
    past = [p for p in (chart.get("past_years") or []) if abs(p["score"]) >= 1 or p.get("clash")]
    py = [f"  {p['year']} {p['ganzhi']}（{p['age']}岁）score={p['score']}{'，冲' if p.get('clash') else ''}"
          for p in past[-30:]]
    return "已行大运：\n" + "\n".join(dy) + "\n近年流年信号（有信号者）：\n" + "\n".join(py)


def choose_statements(chart):
    """AI 从大运流年中选 5 段清晰可判的时段写断言；不合法/不可用时返回 None。"""
    client = ai.get_client()
    if client is None:
        return None
    birth_year = int(chart["input"]["date"][:4])
    this_year = datetime.now().year
    user_prompt = f"""当前 {this_year} 年。命主 {chart['input']['gender']}，生于 {chart['plot_time']}。
{interpret.summary_text(chart)}

{_year_signals_block(chart)}

请挑选并出题，只输出 JSON。"""
    try:
        resp = client.messages.create(
            model=config.CLAUDE_MODEL, max_tokens=8000,
            system=CHOOSE_SYSTEM, messages=[{"role": "user", "content": user_prompt}])
        text = "".join(b.text for b in resp.content if b.type == "text")
    except Exception:
        return None

    data = _extract_json(text)
    items = (data or {}).get("items")
    if not isinstance(items, list) or len(items) != 5:
        return None
    dy_n = sum(1 for it in items if isinstance(it, dict) and it.get("category") == "大运")
    if not (1 <= dy_n <= 2):          # 大运 1~2 条，其余流年
        return None
    allowed = set(range(birth_year, this_year + 1))
    allowed |= {d["end_year"] for d in chart["dayun"] if d["start_year"] <= this_year}
    seen_years = set()
    for it in items:
        if not isinstance(it, dict) or it.get("category") not in ("大运", "流年"):
            return None
        t = str(it.get("text", "")).strip()
        ys = re.findall(r"\d{4}", t)
        if not (20 <= len(t) <= 160) or not ys:
            return None
        if any(int(y) not in allowed for y in ys):    # 年份必须在真实池内
            return None
        seen_years.update(int(y) for y in ys)
    if len(seen_years) < 4:                            # 至少 4 个不同年份，防复读
        return None
    return [{"id": i + 1, "category": it["category"], "text": it["text"].strip()}
            for i, it in enumerate(items)]


def _extract_json(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _answers_block(statements, answers_bool):
    lines = []
    for i, st in enumerate(statements):
        mark = "符合" if (i < len(answers_bool) and answers_bool[i]) else "不符合"
        lines.append(f"[{st['id']}]（{st['category']}）{mark} —— {st['text']}")
    return "\n".join(lines)


def recalibrate(prev_chart, statements, answers_bool, verify_round, derive_round=None):
    """返回合法 calib dict 或 None。
    verify_round：刚校完的轮次；derive_round：要新排的轮次（决定本轮主旨）。"""
    client = ai.get_client()
    if client is None:
        return None
    xy = prev_chart["xiyong"]
    th = prev_chart.get("tiaohou") or {}
    r = derive_round or verify_round
    label = focus_label(r)
    user_prompt = f"""第 {verify_round} 轮命格校验结果（要求 5 题至少 4 题符合），据此重拟第 {r} 轮命盘，本轮主旨：{label}。
{_answers_block(statements, answers_bool)}

上轮推断：{xy['level']}，取用 {xy['yong_shen']}（{xy['yong_shen_shishen']}），喜 {xy['xi_shen']}，忌 {xy['ji_shen']}（{xy.get('school', '扶抑')}）
调候参考：{th.get('note', '')}
十神力量：{prev_chart['group_score']}
{interpret.summary_text(prev_chart)}

请按本轮主旨复核并重拟强弱与喜用，只输出 JSON。"""
    try:
        resp = client.messages.create(
            model=config.CLAUDE_MODEL, max_tokens=8000,  # 预留 thinking 消耗，防正文被截空
            system=_system_for(r),
            messages=[{"role": "user", "content": user_prompt}])
        text = "".join(b.text for b in resp.content if b.type == "text")
    except Exception:
        return None

    calib = _extract_json(text)
    if not calib:
        return None
    if calib.get("yong_shen") not in T.ELEMENTS:
        return None
    if calib.get("level") not in ("身强", "身弱", "中和"):
        return None
    calib["school"] = f"第{r}轮·{label}"
    return calib
