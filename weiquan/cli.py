"""命令行入口:python -m weiquan <命令>。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from . import __version__, agent, llm, rules
from . import db as dbmod
from .llm import LLMError

BANNER = (
    "⚠️  当前为离线模式(未配置 LLM_API_KEY):类目、时效、例外、证据与文书由本地规则给出。\n"
    "   填入 LLM_API_KEY 后,主张顺序、话术与风险由模型撰写(天数与日期仍以本地为准)。\n"
)


def render(r):
    mode = "模型" if r["mode"] == "model" else "离线模式"
    lines = ["⚖️  维权助手  [%s]" % mode, "", "📌 " + r["verdict"], ""]

    lines.append("🧾 识别到的类目")
    if r["categories"]:
        for c in r["categories"]:
            lines.append("  · %s(依据 %s)" % (c["name"], c["basis"]))
            for x in c["rights"]:
                lines.append("      - " + x)
    else:
        lines.append("  · 未识别,补一句争议原话")
    lines.append("")

    lines.append("⏳ 时效")
    if r["timeline"]["sign"]:
        lines.append("  签收日 %s,今天第 %d 天" % (r["timeline"]["sign"], r["timeline"]["days"]))
    for n in r["deadlines"]:
        lines.append("  · " + n)
    lines.append("")

    if r["exceptions"]:
        lines.append("🚧 例外与扣减")
        for e in r["exceptions"]:
            lines.append("  · [%s] %s:%s" % (e["type"], e["name"], e["why"]))
        lines.append("")

    if r["promises"]:
        lines.append("📢 商家承诺")
        for p in r["promises"]:
            lines.append("  · %s(原话「%s」)" % (p["claim"], p["quote"]))
            lines.append("      义务:%s;边界:%s" % (p["obligation"], p["limit"]))
        lines.append("")

    lines.append("📎 证据体检")
    for e in r["evidence"]["provided"]:
        lines.append("  ✅ %s" % e["name"])
    for e in r["evidence"]["missing"]:
        lines.append("  ❌ %s —— %s(%s)" % (e["name"], e["why"], e["how"]))
    lines.append("")

    if r["advice"]:
        lines.append("🧭 主张顺序")
        for i, a in enumerate(r["advice"], 1):
            lines.append("  %d. %s" % (i, a))
        lines.append("")
    if r["talking_points"]:
        lines.append("💬 可以直接发的话")
        for t in r["talking_points"]:
            lines.append("  · " + t)
        lines.append("")
    if r["risks"]:
        lines.append("🚩 可能被拒的理由")
        for x in r["risks"]:
            lines.append("  · " + x)
        lines.append("")

    lines.append("📄 给商家的第一段")
    for x in r["letters"]["merchant"].splitlines():
        lines.append("  " + x)
    lines.append("")
    lines.append("📮 12315 / 平台投诉正文")
    for x in r["letters"]["platform"].splitlines():
        lines.append("  " + x)
    return "\n".join(lines)


def _read_text(args):
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            return f.read()
    if args.text:
        return args.text
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""


def cmd_check(args):
    text = _read_text(args)
    if not text.strip():
        print("❌ 没有内容:用 --text、--file,或管道输入。", file=sys.stderr)
        sys.exit(2)
    sign = rules.parse_date(args.sign) if args.sign else None
    if sign and sign > date.today():
        print("❌ 签收日期 %s 晚于今天,请确认后再算时效。" % sign, file=sys.stderr)
        sys.exit(2)
    ev = [x.strip() for x in (args.evidence or "").split(",") if x.strip()]
    db = dbmod.Database(args.db) if args.db else dbmod.Database()
    r = agent.handle(text, sign=sign, evidence=ev, config=llm.config_from_args(args),
                     db=db, force_mock=args.mock, save=args.save)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return
    print(render(r))
    if r.get("saved_id"):
        print("\n已入库(#%d),`python -m weiquan history` 可回看。" % r["saved_id"])


def cmd_rights(args):
    cats = rules.load("categories.json")["categories"]
    if args.json:
        print(json.dumps(cats, ensure_ascii=False, indent=2))
        return
    print("📚 六类常见维权路径")
    for c in cats:
        print("\n【%s】%s" % (c["name"], c["basis"]))
        print("  触发词:" + "、".join(c["keywords"][:6]))
        for r in c["rights"]:
            print("  · " + r)
        for n in c["notes"]:
            print("  ⚠ " + n)


def cmd_evidence(args):
    items = rules.load("evidence.json")["evidence"]
    print("📎 证据清单(%d 项,越靠前越关键)" % len(items))
    for e in items:
        print("  □ %s —— %s" % (e["name"], e["why"]))
        print("      怎么留:%s" % e["how"])


def cmd_history(args):
    rows = dbmod.Database(args.db).latest(args.limit)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if not rows:
        print("还没有记录。`python -m weiquan check --text \"...\" --save` 存一条。")
        return
    print("🗂 维权记录")
    for r in rows:
        print("  #%d  %s  签收 %s(第 %s 天)  缺证据 %s  %s"
              % (r["id"], r["category"] or "—", r["sign"] or "—", r["days"] if r["days"] is not None else "—",
                 r["missing"], r["created_at"]))


def cmd_web(args):
    from . import web
    web.serve(host=args.host, port=args.port, db_path=args.db, force_mock=args.mock)


def build_parser():
    p = argparse.ArgumentParser(prog="weiquan", description="维权 · 消费纠纷助手:算时效、挑路径、写文书。")
    p.add_argument("--version", action="version", version="weiquan %s" % __version__)
    p.add_argument("--mock", action="store_true", help="强制离线模式")
    p.add_argument("--json", action="store_true", help="输出原始 JSON")
    p.add_argument("--model", help="覆盖 LLM_MODEL")
    p.add_argument("--base-url", help="覆盖 LLM_BASE_URL")
    p.add_argument("--api-key", help="覆盖 LLM_API_KEY")
    p.add_argument("--db", help="SQLite 路径")
    sub = p.add_subparsers(dest="command", required=True)

    ap = sub.add_parser("check", help="分析一单纠纷")
    ap.add_argument("--text", help="纠纷描述原话")
    ap.add_argument("--file", help="从文件读")
    ap.add_argument("--sign", help="签收日期,如 2026-11-18")
    ap.add_argument("--evidence", help="已有证据,逗号分隔:订单,签收,商品页")
    ap.add_argument("--save", action="store_true", help="存入库")
    ap.set_defaults(func=cmd_check)

    rp = sub.add_parser("rights", help="六类维权路径")
    rp.set_defaults(func=cmd_rights)

    ep = sub.add_parser("evidence", help="证据清单")
    ep.set_defaults(func=cmd_evidence)

    hp = sub.add_parser("history", help="历史记录")
    hp.add_argument("--limit", type=int, default=10)
    hp.set_defaults(func=cmd_history)

    wp = sub.add_parser("web", help="启动 Web 界面")
    wp.add_argument("--host", default="127.0.0.1")
    wp.add_argument("--port", type=int, default=8000)
    wp.add_argument("--mock", action="store_true", default=argparse.SUPPRESS)
    wp.set_defaults(func=cmd_web)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not args.mock and args.command == "check" and not llm.config_from_args(args).get("api_key"):
        print(BANNER, file=sys.stderr)
    try:
        args.func(args)
    except LLMError as e:
        print("❌ %s" % e, file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
