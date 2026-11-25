"""校验本批评分。不加 --apply 就是试运行。"""
import argparse
import json
import re
from pathlib import Path

import _cli
import jd_store
import salary_profile
import scoring

ROOT = Path(__file__).resolve().parents[1]
RANK_FIELDS = ("rank_score", "rank_verdict", "rank_date", "rank_breakdown")


def evidence_text(text):
    return re.sub(r"[\s*`]+", "", str(text or ""))


def exclusion_errors(entry, candidate, detail):
    verdict = str(entry.get("rank_verdict") or "")
    breakdown = entry.get("rank_breakdown") or {}
    if not isinstance(breakdown, dict):
        breakdown = {}
    gates = breakdown.get("硬性条件") or {}
    if not isinstance(gates, dict):
        gates = {}
    failed = any(_cli.gate_of(name) == "候选人明确排除"
                 and str(value).strip().startswith(("FAIL", "不满足", "fail"))
                 for name, value in gates.items())
    if not failed and _cli.gate_in_verdict(verdict)[0] != "候选人明确排除":
        return []
    evidence = breakdown.get("排除依据") or {}
    if not isinstance(evidence, dict):
        evidence = {}
    rule = str(evidence.get("个人条件") or "").strip()
    quote = str(evidence.get("职位原文") or "").strip()
    errors = []
    if not evidence_text(rule) or evidence_text(rule) not in evidence_text(candidate):
        errors.append("排除依据须引用个人资料中实际存在的具体条件")
    body = str(detail.get("description") or "") + "\n" + str(entry.get("title") or "")
    if not evidence_text(quote) or evidence_text(quote) not in evidence_text(body):
        errors.append("排除依据须引用该岗位已存正文或标题中的原文")
    return errors


def rank_errors(entry):
    breakdown = entry.get("rank_breakdown") or {}
    if entry.get("status") != "ranked":
        return []
    if not isinstance(breakdown, dict):
        return ["评分明细须为对象"]
    errors = []
    if "deprioritized" in entry:
        errors.append("已评分岗位还留有待评时的降权标记")
    if scoring.is_scoreless(entry):
        return errors
    if entry.get("eduLevel") in ("硕士", "博士"):
        gates = breakdown.get("硬性条件") or breakdown.get("硬门") or {}
        reviewed = isinstance(gates, dict) and any(
            _cli.gate_of(name) == "学历与院校" and value in ("PASS", "FLAG", "FAIL")
            for name, value in gates.items()
        )
        if not (reviewed or breakdown.get("学历待确认") or breakdown.get("学历已核")):
            errors.append("平台标为硕士或博士，请对照职位正文并记录学历核对结论")
    if scoring.is_triage(breakdown):
        for name in ("强度与公司性质", "发展与风险"):
            if breakdown.get(name) not in scoring.COARSE_LEVELS:
                errors.append(f"粗筛的「{name}」只能取 30、50、70、85")
    return errors


def prepare_rank(current, submitted, floor, expect):
    """只合并评分字段，保留平台字段与用户最新状态。"""
    if current.get("status") not in ("new", "ranked") or current.get("evaluated"):
        raise ValueError("岗位状态已改变或已有深评，请重新读取")
    if ((current.get("url"), current.get("title")) != (submitted.get("url"), submitted.get("title"))
            or submitted.get("status") != "ranked"):
        raise ValueError("提交记录与职位身份不符，或未标为已评分")
    if any(name not in submitted for name in RANK_FIELDS):
        raise ValueError("提交记录缺少必填评分字段")
    breakdown = submitted["rank_breakdown"]
    if not isinstance(breakdown, dict):
        raise ValueError("评分明细须为对象")
    job = dict(current, status="ranked")
    job.update({name: submitted[name] for name in RANK_FIELDS})
    job["rank_breakdown"] = breakdown = dict(breakdown)
    if submitted.get("deadline"):
        job["deadline"] = submitted["deadline"]
    job.pop("deprioritized", None)
    verdict = str(job["rank_verdict"] or "")
    if verdict.startswith(("硬门", "不满足")):
        job["rank_score"] = None
    elif job["rank_score"] is None and _cli.strip_triage(verdict) == "跳过":
        pass  # 预筛结案没有综合分
    else:
        judged = (breakdown.get(name) for name in scoring.DIM_WEIGHTS if name != "薪资与职级")
        if not verdict or verdict.startswith("已下线"):
            raise ValueError("提交记录缺少粗筛结论或不是评分结果")
        if not all(type(value) in (int, float) and 0 <= value <= 100 for value in judged):
            raise ValueError("缺少有效的人工评分，分数须在 0 到 100 之间")
        if not scoring.is_triage(breakdown):
            raise ValueError("这里只写回粗筛，深评从评估文件写回")
        if floor is None or expect is None:
            raise ValueError("求职资料中的年包底线或期望区间无法读取")
        dims, score, verdict = scoring.calculated_score(job, breakdown, floor, expect, coarse=True)
        breakdown.update(dims)
        note = scoring.pay_note(job, floor, expect)
        if note:
            breakdown["薪资口径"] = note
        else:
            breakdown.pop("薪资口径", None)
        job.update(rank_score=score, rank_verdict=f"粗筛：{verdict}")
    return job


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="待写入的本批 JSON，按 seen 或平铺结构保存")
    parser.add_argument("--keys", nargs="+", help="本批写入的岗位 ID")
    parser.add_argument("--user", default="", help=_cli.HELP_USER)
    parser.add_argument("--apply", action="store_true", help="规范化并写回本批粗筛结果，须同时指定 --input")
    args = parser.parse_args(argv)
    user = _cli.pick_user(args.user, root=ROOT)
    if not args.keys:
        parser.error("请用 --keys 指定本批岗位 ID")
    if args.apply and args.input is None:
        parser.error("--apply 需要 --input")
    base = ROOT / "users" / user
    path = base / "job_scraper/seen_jobs.json"
    seen = _cli.seen_of(_cli.read_json(args.input or path))
    candidate = (base / "profile/candidate.md").read_text(encoding="utf-8")
    errors = []
    updates = {}
    if args.apply:
        store, stamp = _cli.load_json_stamped(path)
        live = _cli.seen_of(store)
        decisions = _cli.load_user_state(path, strict=True)
        floor = salary_profile.annual_floor(user, ROOT)
        expect = salary_profile.annual_expect(user, ROOT)
    for key in args.keys:
        entry = seen.get(key)
        if not isinstance(entry, dict):
            errors.append(f"{key}：岗位不存在")
            continue
        if args.apply:
            current = live.get(key)
            if not isinstance(current, dict) or _cli.decided_status(current, decisions.get(key)) not in ("new", "ranked"):
                errors.append(f"{key}：岗位已移走或已标为不投、下线，请重新读取")
                continue
            try:
                entry = prepare_rank(current, entry, floor, expect)
            except ValueError as exc:
                errors.append(f"{key}：{exc}")
                continue
            updates[key] = entry
        detail = jd_store.load(user, entry.get("url") or "", entry.get("title") or "") or {}
        errors.extend(f"{key}：{reason}" for reason in
                      exclusion_errors(entry, candidate, detail) + rank_errors(entry))
    if errors:
        print("\n".join(errors))
        return 1
    if args.apply:
        live.update(updates)
        _cli.atomic_write(path, json.dumps(store, ensure_ascii=False, indent=1), expect=stamp)
        print(f"已校验并写回 {len(updates)} 个岗位")
    else:
        print("本批评分校验通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli.run_cli(main))
