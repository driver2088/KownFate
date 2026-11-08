# -*- coding: utf-8 -*-
"""依据命盘生成命格断语（性格/事业/感情/大运）与五道校验题。"""
from . import tables as T


def _dominant_group(chart):
    gs = chart["group_score"]
    return max(gs.items(), key=lambda kv: kv[1])[0]


def fortune(chart):
    dm = chart["day_master"]
    strength = chart["strength"]
    xy = chart["xiyong"]
    pillars = chart["pillars"]
    gender = chart["input"]["gender"]

    top_group = _dominant_group(chart)
    # 主导十神（取力量最大的类中实际存在的十神）
    names = {"比劫": ["比肩", "劫财"], "食伤": ["食神", "伤官"], "财星": ["正财", "偏财"],
             "官杀": ["正官", "七杀"], "印星": ["正印", "偏印"]}[top_group]
    present = set()
    for p in pillars:
        if p["gan_shishen"] != "日主":
            present.add(p["gan_shishen"])
        present.update(p["hide_shishen"])
    top_ss = next((n for n in names if n in present), names[0])

    # ---------- 性格 ----------
    trait = T.SHISHEN_TRAIT[top_ss]
    strength_tone = {
        "身强": "你主意正、行动快，决定的事十头牛拉不回；精力旺盛，但也容易忽略旁人感受。",
        "身弱": "你思虑周详、行事谨慎，重要决定喜欢先听听别人意见；韧性强，压力大了需要人托底。",
        "中和": "你能进能退，该拿主意时不含糊，该借力时不逞强，弹性是你最大的性格资本。",
    }[strength["level"]]
    personality = f"{T.STEM_IMAGERY[dm['gan']]}命局以{top_ss}（{T.GROUP_MEANING[top_group]}）为纲：{trait}。{strength_tone}"

    # ---------- 事业 ----------
    career_by_group = {
        "官杀": "官杀有力，你适合有职有权的赛道：管理岗、体制内、大平台晋升路线能兑现你的执行力；名字越响，责任越重。",
        "食伤": "食伤吐秀，技术与表达是你的立身之本：创作、研发、演说、手艺类专业路线远胜于纯行政；管住嘴、亮出活。",
        "财星": "财星得用，你对数字与机会敏感，适合生意、销售、投资与资源整合类工作；先学会管钱，钱才会跟你走。",
        "印星": "印星护身，学问与名誉是你的靠山：教育、研究、医药、文化等领域容易出成绩，贵人在前辈师长之中。",
        "比劫": "比劫重重，合伙竞争皆多：单干或结盟都能成事，但账目必须清、合同必须严，兄弟情归兄弟情，生意归生意。",
    }
    career = (career_by_group[top_group] +
              f"喜用为{xy['yong_shen']}（{xy['yong_shen_shishen']}），往{xy['advice']['direction'][0]}发展、"
              f"从事{T.ELEMENT_INDUSTRY[xy['yong_shen']]}相关行业，更容易事半功倍。")

    # ---------- 感情 ----------
    spouse_p = pillars[2]["hide_shishen"][0]
    base = T.SPOUSE_PALACE.get(spouse_p, "夫妻宫平和，缘分细水长流。")
    if gender in ("男", "male"):
        wealth_s = chart["group_score"]["财星"]
        extra = ("财星（妻星）在你命局中力量不弱，异性缘不缺，关键是定性——认准了就深扎下去。"
                 if wealth_s >= 8 else
                 "财星（妻星）在原局偏弱，缘分来得不算早，别急着将就；事业立住之后，良缘自然靠近。")
    else:
        officer_s = chart["group_score"]["官杀"]
        extra = ("官杀（夫星）显著，你欣赏有本事、能压得住场的人，感情中宁缺毋滥。"
                 if officer_s >= 8 else
                 "官杀（夫星）在原局偏弱，与其等待被安排，不如主动扩大圈子；务实可靠的对象更旺你。")
    romance = f"日支{pillars[2]['zhi']}为夫妻宫：{base} {extra}"
    if chart["taohua"]:
        romance += f"逢{chart['taohua']}（桃花）之年，人缘感情之事明显活跃。"

    # ---------- 大运总览 ----------
    dayun = chart["dayun"]
    def dy_line(d):
        return f"{d['ganzhi']}运（{d['start_age']}岁起，{d['start_year']}—{d['end_year']}）：{d['luck']}"
    head = f"{chart['qiyun']['age']}岁起运。"
    lines = "；".join(dy_line(d) for d in dayun[:6])
    good = [d for d in dayun if d["luck"] == "吉"]
    advice = ("整体来看，" + (f"喜用得力之运在 {'、'.join(str(d['start_year'])+'年前后' for d in good[:2])}，宜乘势而上；"
                              if good else "行运四平八稳，进退回旋皆在自己；") +
              "逢忌神之年以学习、沉淀、守成为主。")
    dayun_overview = head + lines + "。" + advice

    return {
        "top_group": top_group, "top_ss": top_ss,
        "personality": personality, "career": career,
        "romance": romance, "dayun": dayun_overview,
    }


def statements(chart):
    """生成五道命主校验题：性格×2、事业、感情、应期。"""
    dm = chart["day_master"]
    f = fortune(chart)
    xy = chart["xiyong"]
    strength = chart["strength"]
    pillars = chart["pillars"]

    s = []
    s.append({"category": "性格", "text":
        f"命局显示你{strength['detail']}——做决断时，你多半是'{_decide_line(strength['level'])}'这一挂的。"})
    s.append({"category": "性格", "text":
        f"{T.STEM_IMAGERY[dm['gan']].split('，')[0]}，熟悉你的人评价你'{T.SHISHEN_TRAIT[f['top_ss']].split('，')[0]}'，"
        f"并且你确实在{SCENE_PLACE.get(f['top_group'], '日常')}这类场合中体现得最明显。"})
    s.append({"category": "事业", "text":
        f"论事业，{f['career'].split('；')[0]}；你自问是否更吃'技术/专业表达'这一套，而非纯粹的行政服从？"
        if f["top_group"] == "食伤" else
        f"论事业，{f['career'].split('；')[0]}。回头看你走过的路，是否与这条判断大致相符？"})
    spouse_hint = f["romance"].split(" ")[0]
    s.append({"category": "感情", "text":
        f"你的感情模式：{spouse_hint}——这一点，身边的亲密关系应该最有发言权。"})

    # 应期题
    up = chart.get("verify_year_upheaval")
    sm = chart.get("verify_year_smooth")
    if up and up.get("clash"):
        s.append({"category": "应期", "text":
            f"{up['year']}年（{up['ganzhi']}）岁运与你夫妻宫或月令相冲，那一年你工作、住所或感情"
            f"多半发生过一次明显的变动或波折。"})
    elif up:
        s.append({"category": "应期", "text":
            f"{up['year']}年（{up['ganzhi']}）岁运冲撞你的忌神方位，那一年明显诸事费力、压力上身，"
            f"甚至有过一次想推倒重来的念头。"})
    elif sm:
        s.append({"category": "应期", "text":
            f"{sm['year']}年（{sm['ganzhi']}）喜用得力，那一年你顺风顺水，做成过一件到现在仍有影响的事。"})
    else:
        s.append({"category": "应期", "text":
            f"逢{'、'.join(str(x['year']) for x in chart['key_years'][:2])}这类喜用流年，"
            f"你会明显感觉机会变多、做事更容易有回响。"})

    return [{"id": i + 1, **item} for i, item in enumerate(s)]


SCENE_PLACE = {"比劫": "朋友合伙、同侪竞争", "食伤": "创作输出、公开表达",
               "财星": "钱货两讫、资源交换", "官杀": "被管束、扛责任", "印星": "读书求学、被前辈提携"}

def _decide_line(level):
    return {"身强": "拍板就干、不回头", "身弱": "谋定后动、爱听建议", "中和": "看人下菜、张弛有度"}[level]


def summary_text(chart, f=None):
    """把命盘压成给 AI 答疑用的中文摘要。"""
    f = f or fortune(chart)
    xy = chart["xiyong"]
    p = chart["pillars"]
    pillars_str = " ".join(f"{x['position'][:1]}柱{x['ganzhi']}" for x in p)
    ji = "、".join(xy["ji_shen"])
    xi = "、".join(xy["xi_shen"]) or "同用神"
    dayun_now = ""
    this_year = __import__("datetime").datetime.now().year
    for d in chart["dayun"]:
        if d["start_year"] <= this_year < d["end_year"]:
            dayun_now = f"现行大运：{d['ganzhi']}（{d['start_year']}—{d['end_year']}，{d['luck']}）。"
    key = "；".join(f"{k['year']}年{k['ganzhi']}：{'、'.join(k['notes']) or ('吉' if k['score']>0 else '平')}"
                    for k in chart["key_years"][:4])
    return f"""【命主八字命格（已确认）】
生辰：{chart['input']['date']} {chart['input']['time']}，出生地：{chart['input']['city']}，性别：{chart['input'].get('gender','')}
四柱：{pillars_str}；日主{chart['day_master']['gan']}（{chart['day_master']['element']}，{chart['day_master']['yinyang']}）
五行数量：{chart['wuxing_count']}
日主强弱：{xy['level']}（生扶力量约{xy['support_pct']}%）
喜用神：用神 {xy['yong_shen']}（{xy['yong_shen_shishen']}），喜神 {xi}，忌神 {ji}
事业利方：{xy['advice']['industry']}；利方位：{'、'.join(xy['advice']['direction'])}；利色：{'、'.join(xy['advice']['color'])}
性格：{f['personality']}
事业：{f['career']}
感情：{f['romance']}
大运：{dayun_now}{f['dayun']}
关键流年：{key}"""
