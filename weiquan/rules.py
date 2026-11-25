"""维权本地规则:类目识别、时效推算、例外与承诺抽取、证据体检、文书生成。"""

import json
import os
import re
from datetime import date, timedelta

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

DATE_RE = re.compile(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})")
DATE_MD_RE = re.compile(r"(\d{1,2})月(\d{1,2})[日号]")
DAYS_LEFT_RE = re.compile(r"还剩?(\d+)天|还有(\d+)天")


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def parse_date(text, today=None):
    """从文本中抽签收日期,支持 2026-11-18 / 11月18日 / 昨天前天今天。"""
    today = today or date.today()
    m = DATE_RE.search(text or "")
    if m:
        y, mo, d = (int(x) for x in m.groups())
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    m = DATE_MD_RE.search(text or "")
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        for year in (today.year, today.year - 1):
            try:
                cand = date(year, mo, d)
            except ValueError:
                continue
            if cand <= today:
                return cand
        return None
    for word, delta in (("前天", 2), ("昨天", 1), ("今天", 0), ("当日", 0)):
        if word in (text or ""):
            return today - timedelta(days=delta)
    return None


def classify(text):
    cats = load("categories.json")["categories"]
    out = []
    low = (text or "").lower()
    for c in cats:
        hits = [k for k in c["keywords"] if k.lower() in low]
        if hits:
            out.append({"key": c["key"], "name": c["name"], "hits": hits,
                        "basis": c["basis"], "rights": c["rights"], "notes": c["notes"]})
    return out


def timeline(sign, today=None, cats=None):
    """按签收日算各时效节点与剩余天数;过期为正数超期。"""
    today = today or date.today()
    if sign is None:
        return {"sign": None, "days": None, "deadlines": [], "expired": []}
    days = (today - sign).days
    deadlines, expired = [], []
    for c in (cats or []):
        if c["key"] == "no_reason":
            due = sign + timedelta(days=7)
            item = {"key": c["key"], "name": "七天无理由退货", "due": due.isoformat(),
                    "remain": (due - today).days}
            deadlines.append(item)
            if (due - today).days < 0:
                expired.append(item)
        if c["key"] == "three_pack":
            for label, n in (("7 日退货", 7), ("15 日换货", 15)):
                due = sign + timedelta(days=n)
                item = {"key": c["key"], "name": "三包·" + label, "due": due.isoformat(),
                        "remain": (due - today).days}
                deadlines.append(item)
                if (due - today).days < 0:
                    expired.append(item)
    return {"sign": sign.isoformat(), "days": days, "deadlines": deadlines, "expired": expired}


def exceptions(text):
    ex = load("exceptions.json")
    low = (text or "").lower()
    out = []
    for e in ex["exceptions"]:
        hits = [k for k in e["keywords"] if k in low]
        if hits:
            out.append({"type": "例外", "name": e["name"], "why": e["why"], "hits": hits})
    for h in ex["harm_rules"]:
        hits = [k for k in h["keywords"] if k in low]
        if hits:
            out.append({"type": "扣减", "name": h["name"], "why": h["why"], "hits": hits})
    return out


def promises(text):
    out = []
    low = (text or "").lower()
    for p in load("promises.json")["promises"]:
        hits = [k for k in p["patterns"] if k.lower() in low]
        if hits:
            out.append({"claim": p["claim"], "obligation": p["obligation"],
                        "limit": p["limit"], "quote": hits[0]})
    return out


def evidence_check(provided, text=""):
    items = load("evidence.json")["evidence"]
    tokens = {k.strip().lower() for k in (provided or []) if k.strip()}
    low = (text or "").lower()
    have, missing = [], []
    for e in items:
        ok = False
        for tok in tokens:
            if tok == e["key"] or tok in e["name"] or tok in e["keywords"]:
                ok = True
        if any(k in low for k in e["keywords"] if len(k) > 1):
            ok = True
        (have if ok else missing).append({"key": e["key"], "name": e["name"],
                                         "why": e["why"], "how": e["how"]})
    return {"provided": have, "missing": missing}


def deadline_note(tl, cats):
    """时效提醒,全部在本地算,模型不许改写。"""
    notes = []
    for d in tl["deadlines"]:
        if d["remain"] > 0:
            notes.append("「%s」截止 %s,还剩 %d 天" % (d["name"], d["due"], d["remain"]))
        elif d["remain"] == 0:
            notes.append("「%s」截止今天(%s),今天是最后一天" % (d["name"], d["due"]))
        else:
            notes.append("「%s」已于 %s 到期,超期 %d 天" % (d["name"], d["due"], -d["remain"]))
    if any(c["key"] == "three_pack" for c in cats) and tl["sign"]:
        notes.append("三包从签收/开票日起算,已过 %d 天,保修期内仍可要求维修" % tl["days"])
    if any(c["key"] == "quality" for c in cats):
        notes.append("质量与欺诈类无固定期限,但拖得越久举证越难,建议 48 小时内发起主张")
    return notes


def platform_letter(cats, tl, exs, proms, text):
    """12315/平台投诉正文,本地模板,不交给模型改写金额与日期。"""
    names = "、".join(c["name"] for c in cats) or "商品/服务争议"
    lines = ["投诉事由:%s" % names, ""]
    if tl["sign"]:
        lines.append("签收日期:%s,距今 %d 天。" % (tl["sign"], tl["days"]))
    body = re.sub(r"\s+", " ", (text or "")).strip()
    if body:
        lines.append("事实经过:%s" % body[:220])
    if proms:
        lines.append("商家承诺:%s" % ";".join("%s(原话「%s」)" % (p["claim"], p["quote"]) for p in proms))
    if exs:
        lines.append("需注意:%s" % ";".join(e["name"] for e in exs))
    lines.append("")
    lines.append("诉求:")
    wants = []
    for c in cats:
        wants.append(c["rights"][0])
    lines.append("1. " + "；".join(wants or ["按页面描述履行或退货退款"]))
    lines.append("2. 商家承担因质量问题产生的往返运费")
    lines.append("3. 如认定欺诈,按消保法第五十五条退一赔三")
    lines.append("")
    lines.append("附证据:" + "、".join(["订单与支付记录", "商品页截图", "聊天记录", "开箱影像"][:3]))
    return "\n".join(lines)


def merchant_letter(cats, tl, proms):
    lines = ["您好,关于订单商品,我需要申请售后,请按以下内容处理。", ""]
    if tl["sign"]:
        lines.append("1. 我在 %s 签收,今天为第 %d 天。" % (tl["sign"], tl["days"]))
    for i, c in enumerate(cats, start=1):
        lines.append("%d. 争议类型:%s。依据:%s。" % (i + 1, c["name"], c["basis"]))
    if proms:
        lines.append("%d. 您方页面/客服承诺「%s」,请按承诺履行。" % (len(cats) + 2, proms[0]["quote"]))
    lines.append("")
    lines.append("请在今天内回复处理方案(退货地址/换货流程/补偿金额),逾期我将向平台与 12315 投诉。")
    lines.append("沟通请走平台文字,便于留痕。")
    return "\n".join(lines)


def analyze(text, sign=None, today=None, evidence=None, save_dir=None):
    today = today or date.today()
    cats = classify(text)
    sign = sign or parse_date(text, today)
    tl = timeline(sign, today, cats)
    exs = exceptions(text)
    proms = promises(text)
    ev = evidence_check(evidence, text)
    letters = {"platform": platform_letter(cats, tl, exs, proms, text),
               "merchant": merchant_letter(cats, tl, proms)}
    checkpoints = []
    if not cats:
        checkpoints.append("没识别到明确类目,把「不想要/坏了/货不对板/不发货」等原话补一句")
    if sign is None:
        checkpoints.append("没找到签收日期,七天无理由与三包都从签收起算,补上日期才能判时效")
    if tl["expired"]:
        checkpoints.append("有时效节点已过期,改走质量或欺诈路径,别只提七天无理由")
    if ev["missing"]:
        checkpoints.append("缺证据:%s" % "、".join(e["name"] for e in ev["missing"][:4]))
    if proms:
        checkpoints.append("商家有明示承诺,优先按承诺主张,比法定路径更快")
    return {"categories": cats, "timeline": tl, "deadlines": deadline_note(tl, cats),
            "exceptions": exs, "promises": proms, "evidence": ev,
            "letters": letters, "checkpoints": checkpoints, "sign": tl["sign"]}
