"""计算自动流程目标进度。每次从当前总览重新计算，可在中断后恢复。"""
import argparse
import json
from pathlib import Path

import _cli
from build_dashboard import is_parked
from export_web_data import is_strong

ROOT = Path(__file__).resolve().parents[1]


def progress(jobs, target, prefs=None):
    prefs = prefs or {}
    eligible = [j for j in jobs if not is_parked(j) and not j.get("applied")
                and is_strong(j.get("verdict") or "")
                and not any(prefs.get(tag) is False for tag in j.get("prefTags") or [])]
    # 只有评估和开场白均已落盘才算交付，深评降档后自然退出目标集合。
    ready = [j for j in eligible if j.get("evaluated")
             and any(((j.get("materials") or {}).get(field) or "").strip()
                     for field in ("greeting", "emailBody", "wangshen"))]
    remaining = max(0, target - len(ready))
    return {"target": target, "ready": len(ready), "eligible": len(eligible),
            "remaining": remaining, "stop_search": len(eligible) >= target,
            "complete": remaining == 0,
            "pending": [j["id"] for j in eligible if j not in ready]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=int)
    parser.add_argument("--user", default="", help=_cli.HELP_USER)
    args = parser.parse_args(argv)
    user = _cli.pick_user(args.user, root=ROOT)
    if args.target is None or args.target <= 0:
        parser.error("请提供大于零的 --target 目标数量")
    data = json.loads((_cli.dashboard_dir(user, ROOT) / "data.json").read_text(encoding="utf-8"))
    if data.get("activeUser") != user:
        raise SystemExit("总览用户不一致，请运行 python tools/export_web_data.py 后重试")
    prefs_file = ROOT / "users" / user / "job_scraper/prefs.json"
    prefs = json.loads(prefs_file.read_text(encoding="utf-8")) if prefs_file.is_file() else {}
    print(json.dumps(progress(data["jobs"], args.target, prefs), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
