# -*- coding: utf-8 -*-
"""把评分里不需要判断的三样算好写回：薪资维、综合分、结论。

    python tools/score.py            # 只看，不写盘
    python tools/score.py --apply    # 写回 seen_jobs.json

## 它替执行者做什么

`04-job-evaluation.md` 的四维里，执行者该拿主意的只有三维（技能与经验、
强度与公司性质、发展与风险）加上七道硬门与依据。剩下的三样是确定性函数，
交给它算 —— 判据、口径、四个取值全在 `tools/scoring.py`。

**这不是「多一道检查」，是把这件事从手里拿走。** 实测活动用户 2026-08-29，
四维齐全、有分数的 728 个岗里薪资维错 89 个（12%）、综合分错 85 个（12%）、
判词错 6 个（1%）—— 一个确定性函数手算几百遍，错这些是必然的。
此前的补救全是事后的：`audit_pipeline` 报出来、人再手工订正。

## 它不碰什么

- **深评的三个判断维**（技能与经验、强度与公司性质、发展与风险）：那是人的活。
  深评的**薪资维**照算 —— 加 `--deep`，见上面 `plan` 的说明；它会连
  `evaluation.md` 一起改，所以 `writeback --apply` 不会把旧数顶回来。
- **有意没有分数的**：硬门 FAIL、预筛结案、已下线 —— 判词不是从分数档来的。
- **四维不全的**：算不了，如实跳过并报数。

## 依据里那句话跟着改

数改了、解释不改，两边就自相矛盾（面板上显示的正是那段解释）。所以顺手把
「……给 NN」里的数换掉，并在末尾附一条带日期的订正注脚。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import _cli  # noqa: E402
import scoring  # noqa: E402



#: 评估文件里随薪资维一起动的那几处。**都要对得上才动手** ——
#: 只改一半比不改更坏：表里写 55、下面「综合得分」还是旧的，读的人不知道信哪个。
#:
#: ⚠️ **存档里有两代格式，四条正则都要认全。** 第一版只按新的那代写，
#: 91 个岗里 71 个整份匹配不上（实测 2026-08-29）—— 而它们没有一个是真的
#: 不同步：值对不上的 0 个。**判据太窄和存档不同步长得一模一样**，
#: 都表现为「跳过、不动手」，区别只有去数一遍才知道。
#: 两代的差别：分数带不带 `/100`、「综合得分」带不带 `**`、结论是 `##` 还是
#: `###`、表里有没有那一行「综合」。
_EV_PAY = re.compile(
    r"^(\|\s*薪资与职级\s*\|\s*)(\d+)(\s*(?:/\s*100\s*)?\|\s*)(.*?)(\s*\|\s*)$", re.M)
#: 这一行**可有可无**（老格式没有），有就跟着改。
_EV_TOTAL = re.compile(
    r"^(\|\s*\*{0,2}综合\*{0,2}\s*\|\s*\*{0,2})(\d+)(\s*(?:/\s*100\s*)?\*{0,2}\s*\|)", re.M)
_EV_SCORE = re.compile(r"^(\*{0,2}综合得分：\s*)(\d+)(\s*/\s*100)", re.M)
#: `\s*$` 在 `re.M` 下会连后面的空行一起吃掉 —— 第一版实测每改一份就少一个
#: 空行，标题和正文黏在一起。只吃行内空白。
_EV_VERDICT = re.compile(r"^(#{2,3}[ \t]*结论：)([^\n]+?)[ \t]*$", re.M)
#: 还有一代把分数写进结论里：`### 结论：值得投（72）`。比的时候要剥掉，
#: 改的时候要把它一起改 —— 剥了不还回去，那个数就永远停在旧值上。
_EV_VSCORE = re.compile(r"^(.+?)（(\d+)）$")


def patch_evaluation(text, old, new):
    """把评估文件里那四处改成新值。对不上返回 None（一个字都不动）。

    `old` = (旧薪资维, 旧综合分, 旧结论)，`new` = (新薪资维, 新综合分, 新结论, 新说明)。

    **先验后改。** 四处的旧值都要和库里对得上，才说明这份文件和库是同步的；
    对不上说明有人手改过其中一边 —— 那要人来看，不是工具静默覆盖
    （`job-auto.md`「存档是事实源，工具不单边篡改」）。
    """
    mp, ms, mv = (_EV_PAY.search(text), _EV_SCORE.search(text),
                  _EV_VERDICT.search(text))
    mt = _EV_TOTAL.search(text)          # 老格式没有这一行
    if not (mp and ms and mv):
        return None
    vm = _EV_VSCORE.match(mv.group(2).strip())
    v_word = vm.group(1) if vm else mv.group(2).strip()
    if (int(mp.group(2)) != old[0] or int(ms.group(2)) != old[1]
            or v_word != old[2]
            or (vm and int(vm.group(2)) != old[1])
            or (mt and int(mt.group(2)) != old[1])):
        return None
    v_new = f"{new[2]}（{new[1]}）" if vm else new[2]
    out = _EV_PAY.sub(lambda m: f"{m.group(1)}{new[0]}{m.group(3)}{new[3]}{m.group(5)}",
                      text, count=1)
    if mt:
        out = _EV_TOTAL.sub(lambda m: f"{m.group(1)}{new[1]}{m.group(3)}", out, count=1)
    out = _EV_SCORE.sub(lambda m: f"{m.group(1)}{new[1]}{m.group(3)}", out, count=1)
    out = _EV_VERDICT.sub(lambda m: f"{m.group(1)}{v_new}", out, count=1)
    return out


def _bounds(user: str):
    """底线与期望区间 —— 从 `candidate.md` 现读，读不出就不干活。

    「没查」和「查过没有」是两件事：读不出时**一条都不改**，并说清原因。
    """
    import audit_pipeline as ap
    ap._USER[:] = [user]
    return ap._annual_floor(), ap._annual_expect()


def plan(user: str, deep: bool = False) -> tuple[list, dict]:
    """算出要改哪些。返回 `(改动列表, 计数)`，不写盘。

    `deep=True` 换成盯**深评**那一批，而且只动薪资那一维（连带综合分与结论）。

    ## 为什么深评的薪资维也能机械算

    这一维按 04 就是一张四行的查表，输入只有薪资串、薪数和资料里的
    底线/期望 —— **深评并不会让它变成判断**。原来整块跳过深评，理由是
    「正本在 evaluation.md，库里单边改会被 writeback 顶回去」；那个理由
    对的是**做法**，不是**范围**：连评估文件一起改就没有这个问题。

    实测代价（2026-08-29）：101 个岗的薪资维不是那四个数里的任何一个
    （52 / 62 / 72 / 45 / 50 / 66 这种自由数），其中 89 个是深评。
    自检每个都报一行「补它：/job-apply <职位链接>」—— 一个查表结果，
    要用户敲 89 次命令。

    深评的三个判断维一个不碰（那才是人的活），粗筛那道 `snap_coarse`
    也不施加 —— 深评读过 JD，它给 65 是有依据的。
    """
    p = ROOT / "users" / user / "job_scraper" / "seen_jobs.json"
    store = json.loads(p.read_text(encoding="utf-8"))
    seen = _cli.seen_of(store)          # 老库形态在这里也要容忍
    floor, expect = _bounds(user)
    if floor is None or expect is None:
        return [], {"读不出底线或期望区间": 1}
    # **有 `evaluation.md` 的一律不碰。** `来源` 那一栏说的是「这个分怎么来的」，
    # 而深评落盘之后 `来源` 未必跟着改 —— 实测 7 个岗 `来源` 写着粗筛、
    # 却已经有一份深评文件。改了它们，`writeback --apply` 会从文件顶回来，
    # 中间那段时间面板上是另一个数。存档是事实源，工具不单边篡改。
    import build_dashboard as bd
    _apps = ROOT / "users" / user / "documents" / "applications"
    docs = {_cli.norm_url(a["url"]): _apps / a["dir"] / "evaluation.md"
            for a in bd.find_applications(_apps)
            if a.get("url") and a.get("dir")}
    out, skip = [], {"深评": 0, "粗筛": 0, "有深评文件": 0, "无分数/已出局": 0,
                     "要判断的三维不全": 0, "薪资信息缺失": 0,
                     "评估文件和库对不上": 0, "深评但没找到评估文件": 0}
    for key, v in seen.items():
        if not isinstance(v, dict):
            continue
        b = v.get("rank_breakdown") or {}
        if not b:
            continue
        if scoring.is_triage(b) is deep:
            # 不加 --deep 时跳的是深评那批（粗筛才是这一趟要算的），反过来同理；
            # 原来这行把两个名字写反了，终端印的是「跳过：粗筛 371」而那 371 个全是深评
            skip["粗筛" if deep else "深评"] += 1
            continue
        doc = docs.get(_cli.norm_url(v.get("url") or ""))
        if doc and not deep:
            skip["有深评文件"] += 1
            continue
        if scoring.is_scoreless(v):
            skip["无分数/已出局"] += 1
            continue
        # **薪资那一维允许缺席** —— 它正是这个工具要算的东西。
        # 第一版把它一起算进「四维齐全」的前置检查里，于是按文档留空的记录
        # 全被跳过（实测 2026-08-29：当轮 5 条新粗筛一条没算着，
        # 报「四维不全」）。**工具和它自己的说明书打架**：`job-rank.md` 的
        # schema 里刚写完「薪资那一维可以留空」。
        judged = {k: b.get(k) for k in scoring.DIM_WEIGHTS if k != "薪资与职级"}
        if any(not isinstance(x, (int, float)) for x in judged.values()):
            skip["要判断的三维不全"] += 1
            continue
        pay = scoring.pay_dim(v, floor, expect)
        if pay is None and not isinstance(b.get("薪资与职级"), (int, float)):
            # 面议/未标，而记录里也没有旧值：按 04 这一维标「信息缺失」、
            # 25% 权重摊回其余三维 —— 那是另一条算式，不在这个工具的职责里。
            skip["薪资信息缺失"] += 1
            continue
        dims = dict(judged, **{"薪资与职级": b.get("薪资与职级")})
        new = dict(dims)
        if pay is not None:
            new["薪资与职级"] = pay
        if not deep:
            # 粗筛连 JD 都没读，强度/发展只许取四档；深评读过，65 是有依据的。
            for k in ("强度与公司性质", "发展与风险"):
                new[k] = scoring.snap_coarse(new[k])
        score = scoring.composite(new, scoring.adjust_of(b))
        verdict = scoring.verdict_of(score, new["技能与经验"])
        pre = "粗筛：" if _cli.is_triage(v.get("rank_verdict")) else ""
        if (new == dims and score == v.get("rank_score")
                and pre + verdict == (v.get("rank_verdict") or "")):
            continue
        row = {"key": key, "entry": v, "dims": new, "score": score,
               "verdict": pre + verdict, "doc": None, "text": None,
               "old": (dict(dims), v["rank_score"], v.get("rank_verdict"))}
        if deep and not (doc and doc.is_file()):
            # **深评没找到评估文件就不写。**
            #
            # 「按链接找不到」不等于「没有存档」—— 2026-08-29 当场栽了一次：
            # 同一个岗在猎聘挂了两处（`/a/…449` 与 `/a/…451`，相邻的号），
            # 评估目录的「职位链接」写的是 449，而 451 那条也在库里、也是深评。
            # 451 找不到文件 → 只写了库 → 文件 73、库 74，正是整块跳过深评
            # 要防的那种脱节。
            #
            # 所以判据是**能不能连文件一起改**，不是「有没有文件」。
            # 找不到就跳过并报数，让人来看。
            skip["深评但没找到评估文件"] += 1
            continue
        if doc and doc.is_file():
            # 评估文件在，就必须连它一起改 —— 只改库那一边，`writeback --apply`
            # 会把旧数顶回来（这正是原来整块跳过深评的理由）。
            txt = doc.read_text(encoding="utf-8")
            got = patch_evaluation(
                txt,
                (dims["薪资与职级"], v["rank_score"],
                 _cli.strip_triage(v.get("rank_verdict"))),
                (new["薪资与职级"], score, verdict,
                 scoring.pay_note(v, floor, expect) or ""))
            if got is None:
                skip["评估文件和库对不上"] += 1
                continue
            row["doc"], row["text"] = doc, got
        out.append(row)
    return out, skip


def apply(user: str, rows: list, today: str) -> None:
    p = ROOT / "users" / user / "job_scraper" / "seen_jobs.json"
    store = json.loads(p.read_text(encoding="utf-8"))
    seen = _cli.seen_of(store)
    for r in rows:
        v = seen[r["key"]]
        b = v["rank_breakdown"]
        old_dims, old_score, old_v = r["old"]
        b.update(r["dims"])
        why = scoring.rewrite_pay_said(b.get("依据") or "",
                                       r["dims"]["薪资与职级"])
        moved = "、".join(f"{k} {old_dims[k]}→{r['dims'][k]}"
                          for k in scoring.DIM_WEIGHTS if old_dims[k] != r["dims"][k])
        b["依据"] = why + (
            f"\n\n⚠️ {today} `score.py` 现算订正：{moved or '维度未变'}；"
            f"综合分 {old_score} → {r['score']}，"
            f"结论 {_cli.strip_triage(old_v) or '—'} → "
            f"{_cli.strip_triage(r['verdict'])}。"
            f"这三样（薪资维 / 综合分 / 结论）是确定性函数，由工具现算，不手填。")
        v["rank_score"] = r["score"]
        v["rank_verdict"] = r["verdict"]
        if r.get("doc") is not None:
            _cli.atomic_write(r["doc"], r["text"])
    _cli.atomic_write(p, json.dumps(store, ensure_ascii=False, indent=1),
                      encoding="utf-8")


def main(argv=None) -> int:
    ap_ = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap_.add_argument("--apply", action="store_true", help=_cli.help_apply())
    ap_.add_argument("--deep", action="store_true",
                     help="改深评那一批的薪资维（连评估文件一起改）")
    ap_.add_argument("--user", default="", help=_cli.HELP_USER)
    ap_.add_argument("--today", default="")
    a = ap_.parse_args(argv)
    # **在任何一条早退之前就验。** 这几个工具都有「只报不写」的那条路，
    # 验证挪到写盘那一步的话，敲错日期的人会先拿到一份看着正常的输出
    # （实测 2026-09-01：`applied_jds --today 不是日期` 退出码 0）。
    _today = _cli.parse_today(a.today)
    user = _cli.pick_user(a.user or "", root=ROOT)
    rows, skip = plan(user, deep=a.deep)
    if skip.get("读不出底线或期望区间"):
        print("`candidate.md` 的「可接受底线」「期望区间」读不出年包数 —— "
              "一条都没改。补一行「（年包 N 万）」再跑")
        return 1
    print(f"评分里算得出来的那三样现算（用户：{user}"
          + ("，深评那一批" if a.deep else "") + "）")
    print(f"  要改 {len(rows)} 个；跳过：" +
          "、".join(f"{k} {n}" for k, n in skip.items() if n))
    flip = [r for r in rows
            if _cli.strip_triage(r["old"][2]) != _cli.strip_triage(r["verdict"])]
    for r in rows[:12]:
        o = r["old"]
        print(f"  {str(o[1]):>3}→{r['score']:<3} "
              f"{_cli.strip_triage(o[2]) or '—':<8}→ "
              f"{_cli.strip_triage(r['verdict']):<8}"
              f"{(r['entry'].get('title') or '')[:30]}")
    if len(rows) > 12:
        print(f"  …另有 {len(rows) - 12} 个")
    if flip:
        print(f"  其中 {len(flip)} 个换了档 —— 可投/不可投会跟着变")
    if not a.apply:
        print(chr(10) + _cli.DRY_RUN_NOTE)
        return 0
    if rows:
        apply(user, rows, (_today or dt.date.today()).isoformat())
    print(f"\n已写回 {len(rows)} 个")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
