# -*- coding: utf-8 -*-
"""八字排盘引擎：真太阳时校正 → 四柱 → 五行 → 十神 → 强弱 → 喜用神（扶抑派）
→ 调候参考（月令寒热） → 大运流年。

排盘流派通过 variant 参数切换（校验不通过且 AI 复核不可用时的兜底重算轮次）：
  use_true_solar: 是否按出生地经度+均时差校正真太阳时
  zi_mode: 'late' 晚子时 / 'early' 早子时
  flip_yong: 喜用神取法调换
校验未通过时优先走 AI 复核定稿（recalibrate.apply_ai_adjustment + rescore）。
"""
import math
from datetime import datetime, timedelta
from lunar_python import Solar, Lunar

from . import tables as T

POSITIONS = ["年柱", "月柱", "日柱", "时柱"]

# 干支力量权重（合计100）
WEIGHT = {"年干": 8, "月干": 8, "时干": 8,
          "年支": 13, "月支": 36, "日支": 14, "时支": 13}

VARIANTS = [
    {"round": 1, "use_true_solar": True,  "zi_mode": "late",  "flip_yong": False,
     "note": "按出生地经度与真太阳时校正起盘"},
    {"round": 2, "use_true_solar": False, "zi_mode": "late",  "flip_yong": False,
     "note": "校验未过，改按钟表时间重排，复核节气月令"},
    {"round": 3, "use_true_solar": False, "zi_mode": "early", "flip_yong": False,
     "note": "校验未过，按子时早晚之别重新起盘"},
]
VARIANT_R3_ALT = {"round": 3, "use_true_solar": False, "zi_mode": "early", "flip_yong": True,
                  "note": "校验未过，五行强弱重判、喜用另取后重排"}


def equation_of_time_minutes(doy):
    b = 2 * math.pi * (doy - 81) / 364.0
    return 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)


def true_solar_adjust(y, m, d, hh, mi, lng, tz_offset):
    doy = datetime(y, m, d).timetuple().tm_yday
    minutes = 4 * (lng - 15 * tz_offset) + equation_of_time_minutes(doy)
    return (datetime(y, m, d, hh, mi) + timedelta(minutes=minutes)), round(minutes, 1)


def _solar_terms(lunar):
    try:
        prev = lunar.getPrevJieQi(True)
        nxt = lunar.getNextJieQi(True)
        return {"prev_jie": prev.getName(), "prev_jie_date": prev.getSolar().toYmd(),
                "next_jie": nxt.getName()}
    except Exception:
        return None


def advice_for(element):
    return {
        "color": [T.ELEMENT_COLOR[element]],
        "direction": [T.ELEMENT_DIRECTION[element]],
        "number": [T.ELEMENT_NUMBER[element]],
        "industry": T.ELEMENT_INDUSTRY[element],
    }


def compute(birth, gender, variant):
    """birth: {date, time, city, lng, tz}"""
    y, m, d = (int(x) for x in birth["date"].split("-"))
    hh, mi = (int(x) for x in birth["time"].split(":")) if birth["time"] else (12, 0)

    adjust_note = None
    if birth.get("calendar") == "lunar":
        ly, lmo, ld = y, m, d
        sol = Lunar.fromYmdHms(y, -m if birth.get("leap") else m, d, hh, mi, 0).getSolar()
        y, m, d = sol.getYear(), sol.getMonth(), sol.getDay()
        adjust_note = (f"农历{ly}年{'闰' if birth.get('leap') else ''}{lmo}月{ld}日"
                       f" → 公历{y:04d}-{m:02d}-{d:02d}")

    clock = datetime(y, m, d, hh, mi)

    if variant.get("use_true_solar"):
        dt, adj = true_solar_adjust(y, m, d, hh, mi, birth["lng"], birth["tz"])
        y, m, d, hh, mi = dt.year, dt.month, dt.day, dt.hour, dt.minute
        ts_note = f"真太阳时校正 {adj:+.1f} 分钟"
        adjust_note = f"{adjust_note}；{ts_note}" if adjust_note else ts_note

    if variant.get("zi_mode") == "early" and hh >= 23:
        nd = datetime(y, m, d) + timedelta(days=1)
        y, m, d = nd.year, nd.month, nd.day
        adjust_note = (adjust_note + "；" if adjust_note else "") + "早子时换日"

    solar = Solar.fromYmdHms(y, m, d, hh, mi, 0)
    lunar = solar.getLunar()
    ec = lunar.getEightChar()
    ganzhis = [ec.getYear(), ec.getMonth(), ec.getDay(), ec.getTime()]
    na_yins = [ec.getYearNaYin(), ec.getMonthNaYin(), ec.getDayNaYin(), ec.getTimeNaYin()]
    hides = [ec.getYearHideGan(), ec.getMonthHideGan(), ec.getDayHideGan(), ec.getTimeHideGan()]

    dm_gan = ganzhis[2][0]
    dm_element = T.STEM_ELEMENT[dm_gan]
    dm_yinyang = "阳" if dm_gan in T.STEM_YANG else "阴"

    pillars = []
    for i, gz in enumerate(ganzhis):
        gan, zhi = gz[0], gz[1]
        pillars.append({
            "position": POSITIONS[i], "ganzhi": gz, "gan": gan, "zhi": zhi,
            "gan_element": T.STEM_ELEMENT[gan], "zhi_element": T.BRANCH_ELEMENT[zhi],
            "gan_shishen": "日主" if i == 2 else T.shishen(dm_gan, gan),
            "hide_gan": hides[i],
            "hide_shishen": [T.shishen(dm_gan, hg) for hg in hides[i]],
            "nayin": na_yins[i],
        })

    wuxing_count = {e: 0 for e in T.ELEMENTS}
    for gz in ganzhis:
        wuxing_count[T.STEM_ELEMENT[gz[0]]] += 1
        wuxing_count[T.BRANCH_ELEMENT[gz[1]]] += 1

    group_score = {g: 0.0 for g in ["比劫", "食伤", "财星", "官杀", "印星"]}
    support_score = 0.0
    resource_e = T.generator_of(dm_element)

    def add_item(element, weight, other_gan):
        nonlocal support_score
        ss = T.shishen(dm_gan, other_gan)
        group_score[T.SHISHEN_GROUP[ss]] += weight
        if element == dm_element or element == resource_e:
            support_score += weight

    stem_map = {"年干": ganzhis[0][0], "月干": ganzhis[1][0], "时干": ganzhis[3][0]}
    branch_map = {"年支": ganzhis[0][1], "月支": ganzhis[1][1],
                  "日支": ganzhis[2][1], "时支": ganzhis[3][1]}
    for pos, w in WEIGHT.items():
        if pos in stem_map:
            add_item(T.STEM_ELEMENT[stem_map[pos]], w, stem_map[pos])
        else:
            hid = T.HIDDEN[branch_map[pos]]
            for g, s in zip(hid, T.HIDDEN_SHARE[len(hid)]):
                add_item(T.STEM_ELEMENT[g], w * s, g)

    support_pct = round(support_score, 1)

    if support_pct >= 55:
        level, level_detail = "身强", "日主得令得助，元气充沛，能任财官"
    elif support_pct <= 45:
        level, level_detail = "身弱", "日主耗泄较多，宜借印比生扶，稳中求进"
    else:
        level, level_detail = "中和", "生扶与克泄大致均衡，随运而动，进退皆宜"

    drain_cand = [("食伤", T.GENERATES[dm_element], group_score["食伤"]),
                  ("财星", T.CONTROLLED[dm_element], group_score["财星"]),
                  ("官杀", T.controller_of(dm_element), group_score["官杀"])]
    boost_cand = [("印星", resource_e, group_score["印星"]),
                  ("比劫", dm_element, group_score["比劫"])]

    if level == "身弱":
        ranked = sorted(boost_cand, key=lambda x: -x[2])
        idx = 1 if variant.get("flip_yong") else 0
        yong_group, yong_e = ranked[idx][0], ranked[idx][1]
        xi_e = ranked[1 - idx][1]
        ji_elements = list({c[1] for c in drain_cand})
    else:
        ranked = sorted(drain_cand, key=lambda x: -x[2])
        idx = 1 if variant.get("flip_yong") else 0
        yong_group, yong_e = ranked[idx][0], ranked[idx][1]
        drain_elements = [c[1] for c in drain_cand]
        gen_of_yong = T.generator_of(yong_e)
        xi_e = gen_of_yong if gen_of_yong in drain_elements else \
            next((c[1] for c in ranked if c[0] != yong_group), yong_e)
        ji_elements = [resource_e, dm_element]

    present_ss = set()
    for p in pillars:
        if p["gan_shishen"] != "日主":
            present_ss.add(p["gan_shishen"])
        present_ss.update(p["hide_shishen"])
    yong_shishen_names = {"印星": ["正印", "偏印"], "比劫": ["比肩", "劫财"],
                          "食伤": ["食神", "伤官"], "财星": ["正财", "偏财"],
                          "官杀": ["正官", "七杀"]}[yong_group]
    yong_ss = next((s for s in yong_shishen_names if s in present_ss), yong_shishen_names[0])

    xiyong = {
        "yong_shen": yong_e, "yong_shen_shishen": yong_ss, "yong_shen_group": yong_group,
        "xi_shen": [xi_e] if xi_e != yong_e else [],
        "ji_shen": ji_elements,
        "level": level, "support_pct": support_pct, "detail": level_detail,
        "school": "扶抑", "adjusted_by": None, "reason": None,
        "advice": advice_for(yong_e),
    }

    gender_code = 1 if gender in ("男", "male") else 0
    yun = ec.getYun(gender_code)
    dayun_raw = [{"ganzhi": d.getGanZhi(),
                  "gan_shishen": T.shishen(dm_gan, d.getGanZhi()[0]),
                  "start_year": d.getStartYear(), "end_year": d.getEndYear(),
                  "start_age": d.getStartAge()}
                 for d in yun.getDaYun()[1:] if d.getGanZhi()]

    this_year = datetime.now().year
    liunian_raw = [{"year": yr, "ganzhi": T.ganzhi_of_year(yr),
                    "gan_shishen": T.shishen(dm_gan, T.ganzhi_of_year(yr)[0])}
                   for yr in range(this_year, this_year + 11)]
    birth_year = int(birth["date"][:4])
    past_raw = [{"year": yr, "ganzhi": T.ganzhi_of_year(yr),
                 "age": yr - birth_year}
                for yr in range(max(this_year - 25, birth_year + 18), this_year)]

    chart = {
        "input": dict(birth, gender=gender),
        "variant": variant,
        "clock_time": clock.strftime("%Y-%m-%d %H:%M"),
        "plot_time": f"{y:04d}-{m:02d}-{d:02d} {hh:02d}:{mi:02d}",
        "adjust_note": adjust_note,
        "lunar": f"{lunar.getYearInGanZhi()}年{lunar.getMonthInChinese()}月{lunar.getDayInChinese()}日 "
                 f"({lunar.toString()})",
        "solar_terms": _solar_terms(lunar),
        "pillars": pillars,
        "day_master": {"gan": dm_gan, "element": dm_element, "yinyang": dm_yinyang},
        "wuxing_count": wuxing_count,
        "group_score": {k: round(v, 1) for k, v in group_score.items()},
        "strength": {"level": level, "support_pct": support_pct, "detail": level_detail},
        "xiyong": xiyong,
        "tiaohou": tiaohou(month_branch=pillars[1]["zhi"]),
        "dayun_raw": dayun_raw,
        "liunian_raw": liunian_raw,
        "past_raw": past_raw,
        "qiyun": {"age": yun.getStartYear(), "date": yun.getStartSolar().toYmd()},
        "taohua": T.TAOHUA.get(pillars[0]["zhi"], T.TAOHUA.get(pillars[2]["zhi"], "")),
        "verify_history": [],
    }
    return rescore(chart)


def tiaohou(month_branch):
    """调候参考（月令寒暖燥湿粗取，细论依穷通宝鉴参日主天干）。"""
    table = {
        "寅": (["火"], "温暖"), "卯": (["火"], "温暖"),
        "辰": (["火", "木"], "湿寒"),
        "巳": (["水"], "炎热"), "午": (["水"], "炎热"),
        "未": (["水", "木"], "燥热"),
        "申": (["火"], "转凉"), "酉": (["火"], "肃杀"),
        "戌": (["水"], "干燥"),
        "亥": (["火"], "寒冷"), "子": (["火"], "严寒"),
        "丑": (["火", "木"], "湿寒"),
    }
    els, climate = table[month_branch]
    return {"elements": els, "climate": climate,
            "note": f"{month_branch}月{climate}，调候先取{'、'.join(els)}；细论须参日主天干（穷通宝鉴）"}


def rescore(chart):
    """依据当前 strength/xiyong 复评大运、流年、校验应期。AI 复核后同样调用。"""
    dm_gan = chart["day_master"]["gan"]
    xy = chart["xiyong"]
    fav = {xy["yong_shen"]} | set(xy["xi_shen"])
    ji = set(xy["ji_shen"])
    dm_branch = chart["pillars"][2]["zhi"]
    month_branch = chart["pillars"][1]["zhi"]
    taohua = chart["taohua"]
    this_year = datetime.now().year

    def elem_score(gz):
        s = 0
        for e in (T.STEM_ELEMENT[gz[0]], T.BRANCH_ELEMENT[gz[1]]):
            if e in fav:
                s += 1
            elif e in ji:
                s -= 1
        return s

    dayun = []
    for d in chart["dayun_raw"]:
        s = elem_score(d["ganzhi"])
        luck = "吉" if s >= 1 else ("凶" if s <= -1 else "平")
        dayun.append(dict(d, luck=luck, score=s))

    liunian = []
    for ln in chart["liunian_raw"]:
        gz = ln["ganzhi"]
        s = elem_score(gz)
        sb = gz[1]
        notes = []
        if T.is_clash(sb, dm_branch):
            notes.append("流年冲日支（夫妻宫），感情居所易有变动")
        if T.is_clash(sb, month_branch):
            notes.append("流年冲月令，事业环境面临调整")
        if sb == taohua:
            notes.append("咸池桃花入命，人缘感情之事抬头")
        if s >= 1:
            notes.append("岁运补助喜用，宜进取")
        elif s <= -1:
            notes.append("岁运冲忌，宜守成谨慎")
        liunian.append(dict(ln, score=s, notes=notes))

    past = []
    for pa in chart["past_raw"]:
        gz = pa["ganzhi"]
        s = elem_score(gz)
        clash = T.is_clash(gz[1], dm_branch) or T.is_clash(gz[1], month_branch)
        past.append(dict(pa, score=s, clash=clash))

    upheaval = next((c for c in past if c["clash"] and c["score"] <= 0), None)
    if not upheaval:
        upheaval = next((c for c in past if c["score"] <= -2), None)
    smooth = next((c for c in reversed(past) if c["score"] >= 2), None)

    chart["dayun"] = dayun
    chart["liunian_all"] = liunian
    chart["past_years"] = past
    chart["key_years"] = [x for x in liunian if x["score"] != 0 or x["notes"]][:6]
    chart["verify_year_upheaval"] = upheaval
    chart["verify_year_smooth"] = smooth
    return chart


def apply_ai_adjustment(chart, calib):
    """把 AI 复核给出的强弱/喜用写回命盘并重评岁运。
    calib: {level, yong_shen, yong_shishen, xi_shen:[], ji_shen:[], reason, tiaohou_note, school}"""
    import copy
    c = copy.deepcopy(chart)
    yong_e = calib["yong_shen"]
    if yong_e not in T.ELEMENTS:
        raise ValueError(f"AI 返回用神五行不合法: {yong_e}")
    ss = calib.get("yong_shishen") or "用神"
    xy = {
        "yong_shen": yong_e, "yong_shen_shishen": ss,
        "yong_shen_group": T.SHISHEN_GROUP.get(ss, ""),
        "xi_shen": [e for e in calib.get("xi_shen", []) if e in T.ELEMENTS],
        "ji_shen": [e for e in calib.get("ji_shen", []) if e in T.ELEMENTS],
        "level": calib["level"], "support_pct": c["strength"]["support_pct"],
        "detail": calib.get("detail", f"AI 复核改判{calib['level']}（{calib.get('school', '复核取用')}）"),
        "school": calib.get("school") or "AI 复核取用", "adjusted_by": "ai",
        "reason": calib.get("reason", ""),
        "advice": advice_for(yong_e),
    }
    c["strength"] = {"level": calib["level"], "support_pct": xy["support_pct"],
                     "detail": xy["detail"], "adjusted_by": "ai"}
    c["xiyong"] = xy
    if calib.get("tiaohou_note"):
        c["tiaohou"] = dict(c.get("tiaohou") or {}, ai_note=calib["tiaohou_note"])
    return rescore(c)


def pillars_sig(chart):
    return "|".join(p["ganzhi"] for p in chart["pillars"])
