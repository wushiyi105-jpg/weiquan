"""编排:时效、例外、证据、文书全在本地;模型只写主张顺序、话术与风险。

模型输出里不允许出现天数、日期、金额 —— 这些由本地算,剥掉模型写的,
避免「还剩 3 天」被模型改成「还剩 7 天」这类要命错误。
"""

from __future__ import annotations

import re

from . import llm, mock, rules

JSON_ONLY = "只输出 JSON,不要输出解释或多余文字。"
NUM_RE = re.compile(
    r"(20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}[日号]?)|(\d{1,2}月\d{1,2}[日号])|"
    r"(\d+(?:\.\d+)?\s*个?\s*(?:天|日|工作日|小时))|((?:¥|￥)?\s*\d+(?:\.\d+)?\s*(?:元|块|%))"
)


def _use_model(config, force_mock):
    if force_mock:
        return False
    return bool({**llm.default_config(), **(config or {})}.get("api_key"))


def _cfg(config):
    return {**llm.default_config(), **(config or {})}


def strip_numbers(text: str) -> str:
    """去掉模型写的期限与金额,只留定性表述。"""
    return NUM_RE.sub("相应期限", text)


def verdict(result):
    cats = result["categories"]
    if not cats:
        return "没有识别到明确的维权类目,先补一句「不想要/坏了/货不对板/不发货」。"
    head = "、".join(c["name"] for c in cats)
    parts = ["最可能的路径:%s。" % head]
    if result["timeline"]["deadlines"]:
        live = [d for d in result["timeline"]["deadlines"] if d["remain"] >= 0]
        dead = result["timeline"]["expired"]
        if live:
            parts.append("仍在窗口内:%s。" % "、".join("%s(剩 %d 天)" % (d["name"], d["remain"]) for d in live))
        if dead:
            parts.append("已过期:%s,改走质量/承诺路径。" % "、".join(d["name"] for d in dead))
    if result["promises"]:
        parts.append("商家有明示承诺「%s」,优先按承诺主张。" % result["promises"][0]["quote"])
    if result["evidence"]["missing"]:
        parts.append("还缺 %d 项证据,先补齐再发投诉。" % len(result["evidence"]["missing"]))
    return " ".join(parts)


def _model_advice(result, config):
    cats = "\n".join("- %s(%s):%s" % (c["name"], c["basis"], "；".join(c["rights"])) for c in result["categories"])
    proms = "\n".join("- %s,原话「%s」,边界:%s" % (p["claim"], p["quote"], p["limit"]) for p in result["promises"])
    exs = "\n".join("- [%s] %s:%s" % (e["type"], e["name"], e["why"]) for e in result["exceptions"])
    miss = "、".join(e["name"] for e in result["evidence"]["missing"])
    raw = llm.chat([{
        "role": "system",
        "content": ("你是消费维权顾问。只根据给定的类目、承诺、例外和证据缺口给建议;"
                    "不要写任何天数、日期、金额或比例,这些由系统另行给出;不要编造法条。"),
    }, {
        "role": "user",
        "content": (
            f"用户原话:{result['text']}\n\n识别类目:\n{cats}\n\n商家承诺:\n{proms or '无'}\n"
            f"例外与扣减:\n{exs or '无'}\n\n缺证据:{miss or '无'}\n\n"
            f"{JSON_ONLY}\n输出格式:"
            '{"advice":["按顺序该做的 3-5 步,每步一句话"],'
            '"talking_points":["给商家/平台的原话,可直接复制"],'
            '"risks":["可能被拒的理由与应对"]}'
        ),
    }], config=_cfg(config), temperature=0.3, max_tokens=2200)
    data = llm.extract_json(raw)
    return {
        "advice": [strip_numbers(str(x)) for x in data.get("advice", [])][:6],
        "talking_points": [strip_numbers(str(x)) for x in data.get("talking_points", [])][:6],
        "risks": [strip_numbers(str(x)) for x in data.get("risks", [])][:6],
    }


def handle(text, sign=None, evidence=None, config=None, db=None, force_mock=False, save=False):
    result = rules.analyze(text, sign=sign, evidence=evidence)
    result["text"] = text
    if _use_model(config, force_mock):
        layers = _model_advice(result, config)
        mode = "model"
    else:
        layers = mock.offline(result)
        mode = "offline"
    result.update({"verdict": verdict(result), "advice": layers["advice"],
                   "talking_points": layers["talking_points"], "risks": layers["risks"],
                   "mode": mode, "saved_id": None})
    if db is not None and save:
        result["saved_id"] = db.save(result)
    return result
