# -*- coding: utf-8 -*-
"""命格校验未通过时的 AI 复核：把校验结果连同命盘交给大模型，
要求它依据子平命理重新核定强弱与喜用神。

三轮复核主旨递进（命主所见即三轮打磨路径）：
  第 1 轮以扶抑为主，调候参校；第 2 轮改以调候为主，扶抑参校；
  第 3 轮综合两派，就命主历轮反馈折衡定盘。

返回合法 JSON 则用于 engine.apply_ai_adjustment 重排岁运；
失败/未配置密钥返回 None，由调用方回退到流派重排（VARIANTS）。
"""
import json
import re

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
