"""离线模式:不调模型也能给出主张顺序、话术与风险,结构与模型模式完全一致。"""

from __future__ import annotations


def offline(result):
    cats = result["categories"]
    tl = result["timeline"]
    advice = []

    if cats:
        first = cats[0]
        advice.append("先按「%s」发起售后,依据 %s。" % (first["name"], first["basis"]))
    else:
        advice.append("先把争议说清楚:商品哪里不符、你要求退货还是换货/赔偿。")
    if tl["deadlines"]:
        live = [d for d in tl["deadlines"] if d["remain"] >= 0]
        if live:
            advice.append("时效还在,先在平台内发起,保留申请时间戳,别先私下寄回。")
        else:
            advice.append("法定窗口已过,改走质量问题或商家承诺路径,并说明此前已多次主张。")
    if result["promises"]:
        advice.append("把商家承诺截图一并提交:「%s」,承诺优于法定时按承诺。" % result["promises"][0]["quote"])
    if result["evidence"]["missing"]:
        advice.append("先补证据再谈:缺 %s。" % "、".join(e["name"] for e in result["evidence"]["missing"][:3]))
    advice.append("商家拒绝就升级:平台介入 → 12315(附投诉正文)→ 必要时诉讼。")

    points = []
    for c in cats[:2]:
        points.append("根据%s,%s,请按此处理。" % (c["basis"], c["rights"][0]))
    if result["promises"]:
        points.append("你们页面写着「%s」,请按承诺履行,我已截图。" % result["promises"][0]["quote"])
    points.append("请在今天内给出处理方案和退货地址,逾期我向平台与 12315 投诉。")
    points.append("后续沟通请走平台文字,电话内容我会录音。")

    risks = []
    for e in result["exceptions"]:
        risks.append("[%s] %s:%s" % (e["type"], e["name"], e["why"]))
    for d in tl["expired"]:
        risks.append("「%s」已超期,只提这一条会被直接驳回。" % d["name"])
    if result["evidence"]["missing"]:
        risks.append("证据缺口:%s,缺一项就可能被判「无法证明」。" % "、".join(e["name"] for e in result["evidence"]["missing"][:3]))
    if not risks:
        risks.append("商家常用「已拆封影响二次销售」拒退,回应:拆封查验不等于使用,瑕疵由商家举证。")
    return {"advice": advice[:6], "talking_points": points[:6], "risks": risks[:6]}
