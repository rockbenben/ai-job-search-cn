"""写回本批评分前校验具体排除条件及职位原文。"""
import argparse
import json
import re
from pathlib import Path

import _cli
import jd_store

ROOT = Path(__file__).resolve().parents[1]


def evidence_text(text):
    return re.sub(r"[\s*`]+", "", str(text or ""))


def exclusion_errors(entry, candidate, detail):
    verdict = str(entry.get("rank_verdict") or "")
    gates = (entry.get("rank_breakdown") or {}).get("硬性条件") or {}
    failed = any(_cli.gate_of(name) == "候选人明确排除"
                 and str(value).strip().startswith(("FAIL", "不满足", "fail"))
                 for name, value in gates.items())
    if not failed and _cli.gate_in_verdict(verdict)[0] != "候选人明确排除":
        return []
    evidence = (entry.get("rank_breakdown") or {}).get("排除依据") or {}
    rule = str(evidence.get("个人条件") or "").strip()
    quote = str(evidence.get("职位原文") or "").strip()
    errors = []
    if not evidence_text(rule) or evidence_text(rule) not in evidence_text(candidate):
        errors.append("排除依据须引用个人资料中实际存在的具体条件")
    body = str(detail.get("description") or "") + "\n" + str(entry.get("title") or "")
    if not evidence_text(quote) or evidence_text(quote) not in evidence_text(body):
        errors.append("排除依据须引用该岗位已存正文或标题中的原文")
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="待写入的本批 JSON，按 seen 或平铺结构保存")
    parser.add_argument("--keys", nargs="+", help="本批写入的岗位 ID")
    parser.add_argument("--user", default="", help=_cli.HELP_USER)
    args = parser.parse_args(argv)
    user = _cli.pick_user(args.user, root=ROOT)
    if not args.keys:
        parser.error("请用 --keys 指定本批岗位 ID")
    base = ROOT / "users" / user
    seen = _cli.seen_of(json.loads((args.input or base / "job_scraper/seen_jobs.json").read_text(encoding="utf-8")))
    candidate = (base / "profile/candidate.md").read_text(encoding="utf-8")
    errors = []
    for key in args.keys:
        entry = seen.get(key)
        if entry is None:
            errors.append(f"{key}：岗位不存在")
            continue
        detail = jd_store.load(user, entry.get("url") or "", entry.get("title") or "") or {}
        errors.extend(f"{key}：{reason}" for reason in exclusion_errors(entry, candidate, detail))
    print("\n".join(errors) if errors else "本批排除依据校验通过")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
