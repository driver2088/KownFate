# -*- coding: utf-8 -*-
"""依据命盘生成命格断语（性格/父母/事业/感情/大运）与五道校验题。

校验题结构：第 1-2 题为性格与事业/感情（择一），第 3-5 题为关键大运流年判断。
"""
from datetime import datetime

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

    # ---------- 父母（印星为母、财星为父，月柱为父母宫） ----------
    seal_s = chart["group_score"]["印星"]
    fatherwealth_s = chart["group_score"]["财星"]
    mother = ("印星得力：母亲（或抚养你的长辈）在家中说话有分量，升学择业等大事历来由她把关，年长后仍会听她的。"
              if seal_s >= 8 else
              "印星平和：母亲挂念你却不大包大揽，多是放手让你自己撞，缘分会在你历事之后越发显出深来。"
              if seal_s > 0 else
              "印星不现于命局：与母亲缘分早带一分分离之象——或她操劳、或你离家早，越是想念，越聚少离多。")
    father = ("财星显著：父亲务实、掌得住钱与主张，对你的影响少在言语、多在安排，是行动派不是谈心派。"
              if fatherwealth_s >= 8 else
              "财星弱而有：父亲不善表达、话不多，你俩交流有限，谈到钱上才显出他的存在感。"
              if fatherwealth_s > 0 else
              "财星不现原局：与父亲缘分偏淡，或成长中他缺席，或始终没谈到一处去，不必强求热络。")
    palace = ("日支冲月支，父母宫受冲：你注定早离家自立，逢聚必吵、分开反倒惦记，常来少住是相处上策。"
              if T.is_clash(pillars[2]["zhi"], pillars[1]["zhi"]) else
              "月令父母宫安稳：家能给你托底，也易裹挟你的选择——大事问过父母，主意仍拿在自己手里。")
    parents = mother + father + palace

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
        "romance": romance, "parents": parents, "dayun": dayun_overview,
    }


SCENE_PLACE = {"比劫": "朋友合伙、同侪竞争", "食伤": "创作输出、公开表达",
               "财星": "钱货两讫、资源交换", "官杀": "被管束、扛责任", "印星": "读书求学、被前辈提携"}


def _decide_line(level):
    return {"身强": "拍板就干、不回头", "身弱": "谋定后动、爱听建议", "中和": "看人下菜、张弛有度"}[level]


def _current_dayun(chart):
    this_year = datetime.now().year
    done = [d for d in chart["dayun"] if d["start_year"] <= this_year]
    return done[-1] if done else (chart["dayun"][0] if chart["dayun"] else None)


_DAYUN_CLAIM = {
    "吉": ("顺遂上升", "做事多有回响，机会抓住的比放掉的多，是积累成果的一段"),
    "凶": ("吃力磨人", "明显感觉阻力变大，事业、财务或人际在这段里经历过一段紧绷期"),
    "平": ("稳中蓄势", "说不上大起大落，但这几年你在默默换赛道或打底子，外人未必看得出来"),
}


def _dayun_claim_text(d, chart):
    ss = d["gan_shishen"]
    tone, body = _DAYUN_CLAIM[d["luck"]]
    extra = {
        "正官": "尤其职务、名分、约束类的事成为这段的主线", "七杀": "尤其压力、竞争、变动类的事反复找上门",
        "正财": "尤其收入、家庭、务实经营的话题占据中心", "偏财": "尤其机会、进出账、人际资源起伏明显",
        "食神": "表达、创作、口福与技术输出成为这段的日常", "伤官": "变动、不服管、想自己干念头强烈",
        "正印": "学习、证书、长辈与平台资源是你的依靠", "偏印": "冷门知识、独处思考、计划多变更常见",
        "比肩": "同侪合作与竞争交织，靠自己扛的成分多", "劫财": "合伙、借贷、竞争场面增多，钱上更要留神",
    }.get(ss, "")
    return (f"{d['start_year']}年至{d['end_year']}年行{d['ganzhi']}大运（天干{ss}）：这十年你的整体基调是"
            f"{body}，{extra}。")


_LN_CLAIM = {
    "clash": lambda p: (f"{p['year']}年（{p['ganzhi']}，约{p['age']}岁）岁运冲动你的日支或月令，"
                        f"那一年工作、住所或感情里多半起过一次明显的变动，甚至动过推倒重来的念头。"),
    "neg2": lambda p: (f"{p['year']}年（{p['ganzhi']}，约{p['age']}岁）忌神当头，那一年阻力格外大——"
                       f"事情推进吃力，财务或人际上有过一段紧绷期。"),
    "pos2": lambda p: (f"{p['year']}年（{p['ganzhi']}，约{p['age']}岁）喜用得力，那一年你做成过一件"
                       f"至今仍有回响的事：职位、置业、一段关系的确立，或一笔像样的进账。"),
    "pos1": lambda p: (f"{p['year']}年（{p['ganzhi']}，约{p['age']}岁）前后机会明显变多，你有过一段"
                       f"做事格外顺手的日子，也留下过一个当时没接住、如今想起仍会咂摸的机会。"),
    "other": lambda p: (f"{p['year']}年（{p['ganzhi']}，约{p['age']}岁）在你命局里是个换挡的年份——"
                        f"它之前和之后，你的生活轨迹明显换了方向。"),
}


def _ln_trait(p):
    if p.get("clash") and p["score"] <= 0:
        return "clash"
    if p["score"] <= -2:
        return "neg2"
    if p["score"] >= 2:
        return "pos2"
    if p["score"] >= 1:
        return "pos1"
    return "other"


def _liunian_statements(chart):
    """五题正体：全部取成年后已发生的流年，凭记忆可核对。"""
    past = chart.get("past_years") or []
    order = {"clash": 0, "pos2": 1, "neg2": 2, "pos1": 3, "other": 4}
    ranked = sorted(past, key=lambda p: (-(abs(p["score"]) + (2 if p.get("clash") else 0)), -p["year"]))
    picked, used = [], set()
    for trait in order:  # 先按类型各取一年，保证题面多样
        cand = next((p for p in ranked if _ln_trait(p) == trait and p["year"] not in used
                     and all(abs(p["year"] - q) >= 2 for q in used)), None)
        if cand:
            picked.append((trait, cand)); used.add(cand["year"])
    for p in ranked:     # 不足五题再以信号最强年份补齐
        if len(picked) >= 5:
            break
        if p["year"] not in used:
            picked.append((_ln_trait(p), p)); used.add(p["year"])
    return [{"category": "流年", "text": _LN_CLAIM[trait](p)} for trait, p in picked[:5]]


def _classic_statements(chart):
    """后备题面（命主太年轻、可核对流年不足五事时补位）：性格、事业或感情、大运。"""
    f = fortune(chart)
    strength = chart["strength"]
    s = [{"category": "性格", "text":
        f"命局显示你{strength['detail']}——做决断时，你多半是'{_decide_line(strength['level'])}'这一挂的。"}]
    career_force = f["top_group"] in ("官杀", "财星", "食伤")
    if career_force:
        s.append({"category": "事业", "text":
            f"论事业：{f['career'].split('喜用为')[0].rstrip('；')}回头看你走过的路，"
            f"你在{SCENE_PLACE.get(f['top_group'], '职场')}这类场景里的表现，应与这条判断大致相符。"})
    else:
        s.append({"category": "感情", "text":
            f"你的感情模式：{f['romance'].split(' ')[0]}——这一点，身边的亲密关系应该最有发言权。"})
    d_cur = _current_dayun(chart)
    if d_cur and d_cur["start_year"] <= datetime.now().year - 3:
        s.append({"category": "大运", "text": _dayun_claim_text(d_cur, chart)})
    elif len(chart["dayun"]) >= 2:
        d = chart["dayun"][1]
        s.append({"category": "大运", "text":
            f"{d['start_year']}年起进入{d['ganzhi']}大运后，你的人生节奏相较学生时代有一次明显换挡。"})
    up = chart.get("verify_year_upheaval")
    sm = chart.get("verify_year_smooth")
    if up:
        s.append({"category": "流年", "text":
            f"{up['year']}年（{up['ganzhi']}，约{up['age']}岁）前后，你经历过一次旁人看来不大、"
            f"你自己却记到今天的事。"})
    if sm:
        s.append({"category": "流年", "text":
            f"{sm['year']}年（{sm['ganzhi']}，约{sm['age']}岁）喜用得力，"
            f"你做成过一件到现在仍有影响的事。"})
    if len(s) < 5:
        adv = chart["xiyong"]["advice"]
        s.append({"category": "际遇", "text":
            f"总体上你在逢{'、'.join(adv['direction'])}之方、{'、'.join(adv['color'])}色系年份节奏更顺，"
            f"回头验证应有体会。"})
    if len(s) < 5:
        fut = [x for x in chart["liunian_all"] if x["score"] >= 1]
        nxt = fut[0]["year"] if fut else datetime.now().year + 1
        s.append({"category": "流年", "text":
            f"{nxt}年前后会有一个值得主动争取的窗口——你以往抓住机会的手感，届时再用一次。"})
    return s


def statements(chart):
    """五道校验题：采用 5 个可核对的关键流年判断；流年池不足时以性情/大运断语补位。"""
    items = _liunian_statements(chart)
    if len(items) < 5:
        items = items + _classic_statements(chart)[:5 - len(items)]
    return [{"id": i + 1, **item} for i, item in enumerate(items[:5])]


def verify_feedback_text(statements, answers):
    """把校验结果压成给 AI 看的文字（题号+题干摘要+符合/不符）。"""
    lines = []
    by_id = {st["id"]: st for st in statements}
    for a in answers:
        st = by_id.get(a["statement_id"])
        if not st:
            continue
        mark = "符合" if a["agree"] else "不符合"
        lines.append(f"第{a['statement_id']}题（{st['category']}）{mark}：{st['text']}")
    return "\n".join(lines)


def summary_text(chart, f=None):
    """把命盘压成给 AI 答疑用的中文摘要。"""
    f = f or fortune(chart)
    xy = chart["xiyong"]
    p = chart["pillars"]
    pillars_str = " ".join(f"{x['position'][:1]}柱{x['ganzhi']}" for x in p)
    ji = "、".join(xy["ji_shen"])
    xi = "、".join(xy["xi_shen"]) or "同用神"
    dayun_now = ""
    this_year = datetime.now().year
    for d in chart["dayun"]:
        if d["start_year"] <= this_year < d["end_year"]:
            dayun_now = f"现行大运：{d['ganzhi']}（{d['start_year']}—{d['end_year']}，{d['luck']}）。"
    key = "；".join(f"{k['year']}年{k['ganzhi']}：{'、'.join(k['notes']) or ('吉' if k['score']>0 else '平')}"
                    for k in chart["key_years"][:4])
    th = chart.get("tiaohou") or {}
    th_line = f"调候参考：{th.get('note', '')}" + (f"（AI复核：{th['ai_note']}）" if th.get("ai_note") else "")
    if xy.get("adjusted_by") == "ai":
        school_line = f"喜用取用经过 AI 复核（{xy.get('school','')}），复核理由：{xy.get('reason','')}"
    else:
        school_line = f"喜用取用以扶抑为主（{xy.get('school','扶抑')}），并与调候互参"
    history = ""
    if chart.get("verify_history"):
        h_lines = []
        for h in chart["verify_history"]:
            rejected = "；".join(h.get("rejected", [])) or "无"
            h_lines.append(f"第{h['round']}轮校验：{h['agree']}/5 符合，被判不符合的断语——{rejected}")
        history = "\n【历轮命主校验反馈】\n" + "\n".join(h_lines)
    cal = "农历输入" + ("（闰月）" if chart["input"].get("leap") else "") \
        if chart["input"].get("calendar") == "lunar" else "公历输入"
    return f"""【命主八字命格（已确认）】
生辰：{chart['input']['date']} {chart['input']['time']}（{cal}），出生地：{chart['input']['city']}，性别：{chart['input'].get('gender','')}
农历：{chart['lunar']}
四柱：{pillars_str}；日主{chart['day_master']['gan']}（{chart['day_master']['element']}，{chart['day_master']['yinyang']}）
五行数量：{chart['wuxing_count']}
日主强弱：{xy['level']}（生扶力量约{xy['support_pct']}%）
喜用神：用神 {xy['yong_shen']}（{xy['yong_shen_shishen']}），喜神 {xi}，忌神 {ji}。{school_line}
{th_line}
事业利方：{xy['advice']['industry']}；利方位：{'、'.join(xy['advice']['direction'])}；利色：{'、'.join(xy['advice']['color'])}
性格：{f['personality']}
事业：{f['career']}
感情：{f['romance']}
父母：{f['parents']}
大运：{dayun_now}{f['dayun']}
关键流年：{key}{history}"""
