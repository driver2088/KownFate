# -*- coding: utf-8 -*-
"""八字排盘引擎：真太阳时校正 → 四柱 → 五行 → 十神 → 强弱 → 喜用神 → 大运流年。

排盘流派通过 variant 参数切换（用于命主校验不通过时的重算轮次）：
  use_true_solar: 是否按出生地经度+均时差校正真太阳时
  zi_mode: 'late' 晚子时（23点后不换日柱） / 'early' 早子时（23点即换次日）
  flip_yong: 喜用神取法调换（第三轮兜底，前两轮命主仍否定且四柱无变化时启用）
"""
import math
from datetime import datetime, timedelta
from lunar_python import Solar

from . import tables as T

POSITIONS = ["年柱", "月柱", "日柱", "时柱"]

# 干支力量权重（合计100）
WEIGHT = {"年干": 8, "月干": 8, "时干": 8,
          "年支": 13, "月支": 36, "日支": 14, "时支": 13}

VARIANTS = [
    {"round": 1, "use_true_solar": True,  "zi_mode": "late",  "flip_yong": False,
     "note": "按出生地经度与真太阳时校正起盘"},
    {"round": 2, "use_true_solar": False, "zi_mode": "late",  "flip_yong": False,
     "note": "命主存疑，改按钟表时间重排，复核节气月令"},
    {"round": 3, "use_true_solar": False, "zi_mode": "early", "flip_yong": False,
     "note": "改用早子时换日法重排，子时出生日柱随时柱顺延"},
]
VARIANT_R3_ALT = {"round": 3, "use_true_solar": False, "zi_mode": "early", "flip_yong": True,
                  "note": "沿用原局，五行强弱边界重判，喜用神换柱取用"}


def equation_of_time_minutes(doy):
    """均时差近似公式（分钟），误差约 ±0.5 分钟。"""
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


def compute(birth, gender, variant):
    """birth: {date:'YYYY-MM-DD', time:'HH:MM', city, lng, tz}"""
    y, m, d = (int(x) for x in birth["date"].split("-"))
    hh, mi = (int(x) for x in birth["time"].split(":")) if birth["time"] else (12, 0)
    clock = datetime(y, m, d, hh, mi)

    adjust_note = None
    if variant.get("use_true_solar"):
        dt, adj = true_solar_adjust(y, m, d, hh, mi, birth["lng"], birth["tz"])
        y, m, d, hh, mi = dt.year, dt.month, dt.day, dt.hour, dt.minute
        adjust_note = f"真太阳时校正 {adj:+.1f} 分钟"

    # 早子时法：23:00 之后视为次日
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

    # ---------- 四柱结构 ----------
    pillars = []
    for i, gz in enumerate(ganzhis):
        gan, zhi = gz[0], gz[1]
        pos = POSITIONS[i]
        pillars.append({
            "position": pos,
            "ganzhi": gz,
            "gan": gan, "zhi": zhi,
            "gan_element": T.STEM_ELEMENT[gan],
            "zhi_element": T.BRANCH_ELEMENT[zhi],
            "gan_shishen": "日主" if i == 2 else T.shishen(dm_gan, gan),
            "hide_gan": hides[i],
            "hide_shishen": [T.shishen(dm_gan, hg) for hg in hides[i]],
            "nayin": na_yins[i],
        })

    # ---------- 五行数量（干支本气计） ----------
    wuxing_count = {e: 0 for e in T.ELEMENTS}
    for gz in ganzhis:
        wuxing_count[T.STEM_ELEMENT[gz[0]]] += 1
        wuxing_count[T.BRANCH_ELEMENT[gz[1]]] += 1

    # ---------- 十神力量（加权） ----------
    group_score = {g: 0.0 for g in ["比劫", "食伤", "财星", "官杀", "印星"]}
    support_score = 0.0  # 生扶日主的力量（印比）
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
            gan = stem_map[pos]
            add_item(T.STEM_ELEMENT[gan], w, gan)
        else:
            hid = T.HIDDEN[branch_map[pos]]
            shares = T.HIDDEN_SHARE[len(hid)]
            for g, s in zip(hid, shares):
                add_item(T.STEM_ELEMENT[g], w * s, g)

    support_pct = round(support_score, 1)

    # ---------- 身强身弱 ----------
    if support_pct >= 55:
        level = "身强"
        level_detail = "日主得令得助，元气充沛，能任财官"
    elif support_pct <= 45:
        level = "身弱"
        level_detail = "日主耗泄较多，宜借印比生扶，稳中求进"
    else:
        level = "中和"
        level_detail = "生扶与克泄大致均衡，随运而动，进退皆宜"

    # ---------- 喜用神 / 忌神 ----------
    drain = {"食伤": T.GENERATES[dm_element],
             "财星": T.CONTROLLED[dm_element],
             "官杀": T.controller_of(dm_element)}
    boost = {"印星": resource_e, "比劫": dm_element}

    def pick(pool):
        ranked = sorted(pool.items(), key=lambda kv: -kv[1])
        return ranked

    drain_cand = [("食伤", T.GENERATES[dm_element], group_score["食伤"]),
                  ("财星", T.CONTROLLED[dm_element], group_score["财星"]),
                  ("官杀", T.controller_of(dm_element), group_score["官杀"])]
    boost_cand = [("印星", resource_e, group_score["印星"]),
                  ("比劫", dm_element, group_score["比劫"])]

    if level == "身弱":
        ranked = sorted(boost_cand, key=lambda x: -x[2])
        idx = 1 if variant.get("flip_yong") and len(ranked) > 1 else 0
        yong_group, yong_e = ranked[idx][0], ranked[idx][1]
        xi_e = ranked[1 - idx][1]
        ji_elements = list({c[1] for c in drain_cand})
    else:
        ranked = sorted(drain_cand, key=lambda x: -x[2])
        idx = 1 if variant.get("flip_yong") and len(ranked) > 1 else 0
        yong_group, yong_e = ranked[idx][0], ranked[idx][1]
        drain_elements = [c[1] for c in drain_cand]
        gen_of_yong = T.generator_of(yong_e)
        xi_e = gen_of_yong if gen_of_yong in drain_elements else \
            next((c[1] for c in ranked if c[0] != yong_group), yong_e)
        ji_elements = [resource_e, dm_element]  # 身强忌生扶：印星、比劫

    # 用神对应的十神名（分阴阳）
    yong_shishen_names = {
        "印星": [ss for ss in ("正印", "偏印")],
        "比劫": ["比肩", "劫财"],
        "食伤": ["食神", "伤官"],
        "财星": ["正财", "偏财"],
        "官杀": ["正官", "七杀"],
    }[yong_group]

    # 精确取柱中实际存在的用神十神
    present_ss = set()
    for p in pillars:
        if p["gan_shishen"] != "日主":
            present_ss.add(p["gan_shishen"])
        present_ss.update(p["hide_shishen"])
    yong_ss = next((s for s in yong_shishen_names if s in present_ss), yong_shishen_names[0])

    xiyong = {
        "yong_shen": yong_e,
        "yong_shen_shishen": yong_ss,
        "yong_shen_group": yong_group,
        "xi_shen": [xi_e] if xi_e != yong_e else [],
        "ji_shen": ji_elements,
        "level": level,
        "support_pct": support_pct,
        "detail": level_detail,
        "advice": {
            "color": [T.ELEMENT_COLOR[e] for e in [yong_e, xi_e] if e],
            "direction": [T.ELEMENT_DIRECTION[e] for e in [yong_e, xi_e] if e],
            "number": [T.ELEMENT_NUMBER[e] for e in [yong_e]],
            "industry": T.ELEMENT_INDUSTRY[yong_e],
        },
    }

    # ---------- 大运 ----------
    gender_code = 1 if gender in ("男", "male") else 0
    yun = ec.getYun(gender_code)
    start_solar = yun.getStartSolar()
    dayun = []
    for d_obj in yun.getDaYun()[1:]:
        gz = d_obj.getGanZhi()
        if not gz:
            continue
        dg, dz = gz[0], gz[1]
        de, ze = T.STEM_ELEMENT[dg], T.BRANCH_ELEMENT[dz]
        s = 0
        for e in (de, ze):
            if e == yong_e or e == xi_e:
                s += 1
            elif e in xiyong["ji_shen"]:
                s -= 1
        luck = "吉" if s >= 1 else ("凶" if s <= -1 else "平")
        dayun.append({
            "ganzhi": gz,
            "gan_shishen": T.shishen(dm_gan, dg),
            "start_year": d_obj.getStartYear(),
            "end_year": d_obj.getEndYear(),
            "start_age": d_obj.getStartAge(),
            "luck": luck,
            "score": s,
        })

    # ---------- 关键流年（今起十年） ----------
    this_year = datetime.now().year
    liunian = []
    dm_branch = ganzhis[2][1]
    month_branch = ganzhis[1][1]
    year_branch = ganzhis[0][1]
    taohua = T.TAOHUA[year_branch] if year_branch in T.TAOHUA else T.TAOHUA.get(dm_branch, "")
    for yr in range(this_year, this_year + 11):
        gz = T.ganzhi_of_year(yr)
        sg, sb = gz[0], gz[1]
        se, be = T.STEM_ELEMENT[sg], T.BRANCH_ELEMENT[sb]
        s = sum(1 if e in (yong_e, xi_e) else (-1 if e in xiyong["ji_shen"] else 0) for e in (se, be))
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
        liunian.append({"year": yr, "ganzhi": gz, "score": s, "notes": notes,
                        "gan_shishen": T.shishen(dm_gan, sg)})
    key_years = [x for x in liunian if x["score"] != 0 or x["notes"]][:6]

    # ---------- 校验用：可验证的过去流年 ----------
    past_candidates = []
    for yr in range(this_year - 6, this_year):
        gz = T.ganzhi_of_year(yr)
        sb = gz[1]
        se, be = T.STEM_ELEMENT[gz[0]], T.BRANCH_ELEMENT[sb]
        s = sum(1 if e in (yong_e, xi_e) else (-1 if e in xiyong["ji_shen"] else 0) for e in (se, be))
        clash = T.is_clash(sb, dm_branch) or T.is_clash(sb, month_branch)
        past_candidates.append({"year": yr, "ganzhi": gz, "score": s, "clash": clash})
    upheaval = next((c for c in past_candidates if c["clash"] and c["score"] <= 0), None)
    if not upheaval:
        upheaval = next((c for c in past_candidates if c["score"] <= -2), None)
    smooth = next((c for c in reversed(past_candidates) if c["score"] >= 2), None)

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
        "dayun": dayun,
        "qiyun": {"age": yun.getStartYear(), "date": start_solar.toYmd()},
        "liunian_all": liunian,
        "key_years": key_years,
        "verify_year_upheaval": upheaval,
        "verify_year_smooth": smooth,
        "taohua": taohua,
    }
    return chart


def pillars_sig(chart):
    """四柱指纹，用于判断重算是否改变原局。"""
    return "|".join(p["ganzhi"] for p in chart["pillars"])
