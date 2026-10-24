#!/usr/bin/env python3
"""把出局已久的岗从热库挪进存档，让全部计算量永远卡在热库规模。

## 为什么要它

实测（2026-08-19）：职位库 2610 个岗里 **87% 是死数据**——硬性条件没过、分不够、
已下线、标掉的，永远不会再投，却每次导出都被重算、每次写回都被整份重写。
按 261 个/天的增速，半年后库 5 万个、一次重导出 36 秒。

归档把闸门装在增长曲线上：**热库规模 ≈ 活数据 + 两周内的出局岗**，恒定不涨。
增量导出、换 SQLite 这些更贵的方案因此大概率永远不需要。

## 什么会被归档（每一条都要同时满足）

1. **判词出局**（`export_web_data.is_out_verdict`：硬门 FAIL / 不满足硬性条件 /
   跳过 / 不建议）或已下线；用户手动标「不投」的另算（见下）
2. **判定已超过 14 天**——出局两周后职位多半已下线，翻案是罕见事件
3. **没投过**（对着台账逐条 match，用的是面板同一个 `match_tracker`）
4. **没有材料目录**（出过深评/话术的岗是花过工时的，留在热库）

用户手动标「不投」的留 **30 天**再归——那是他表过态的，放回概率高一点。

## 两个最容易做坏的口子（对应 2026-08-19 用户当面问的两件事）

**① 去重怎么办？** 归档的键**必须**仍参与抓取去重，否则下一轮 `/job-scrape`
把它们当新岗抓回来、重新评一遍——归档就成了「花钱重评一遍死数据」的机器。
`/job-scrape` Step 4 与 `query_yield` 都要读热+冷两份（词表的 `found_by` 历史
也在冷库里，丢了它，挖空的词又会被推荐成「最值钱的格子」）。

**② 还没投的、要重新判定的怎么办？** 三层保护：

- **判据只碰出局岗**：待评（new）、可投、可以考虑、已投、有材料的**永远不归档**；
- **归档不是删除**：`archive.json` 与热库同 schema、字段一件不丢（含分数、判词、
  依据、当时的用户决定），grep 得到、随时搬得回；
- **`--revive` 一条命令全部拉回**：改了硬性条件（薪资底线、排除规则）需要全库
  重判时，先 `--revive` 再 `/job-rank --all`——重评机器照常工作，下一轮归档
  会把仍然死的再送回去。翻案走「放回」也一样：岗在冷库就先 revive。

## 用法

    python tools/archive.py            # 试运行：列出会归档哪些，不写盘
    python tools/archive.py --apply    # 真的归档
    python tools/archive.py --revive   # 把存档整个拉回热库（重判前用）

`/job-auto` 收尾自动跑一次 `--apply`——判据机械、无判断输入，归机器。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import _cli  # noqa: E402
from build_dashboard import find_applications, load_tracker, match_tracker  # noqa: E402
from export_web_data import is_out_verdict  # noqa: E402

#: 出局多少天后才归档。太短会把「刚判完、用户还没来得及翻案」的岗埋掉；
#: 太长热库就白白扛着死数据。两周是「职位多半已下线」的经验值。
DEAD_DAYS = 14
#: 用户手动标「不投」的多留多久。他表过态的，放回概率比规则杀的高。
DECISION_DAYS = 30


def paths(user: str) -> tuple[Path, Path]:
    base = ROOT / "users" / user / "job_scraper"
    return base / "seen_jobs.json", base / "archive.json"


def _age_days(entry: dict, overlay: dict, today: _dt.date) -> int | None:
    """出局判定距今几天。取**最晚**的那个日期——宁可少归一轮，不可早埋。"""
    dates = [overlay.get("date"), entry.get("skip_date"), entry.get("expired_date"),
             entry.get("rank_date"), entry.get("first_seen")]
    known = []
    for d in dates:
        try:
            known.append(_dt.date.fromisoformat(str(d)))
        except (TypeError, ValueError):
            continue
    if not known:
        return None
    return (today - max(known)).days


def pick(seen: dict, ustate: dict, applied_keys: set, material_urls: set,
         today: _dt.date) -> dict[str, str]:
    """挑出该归档的：`{键: 原因}`。纯函数，好测。"""
    out = {}
    for k, e in seen.items():
        st = _cli.decided_status(e, ustate.get(k))
        vd = str(e.get("rank_verdict") or "")
        user_decided = bool(ustate.get(k, {}).get("decision")) or st == "skipped"
        dead = st == "expired" or user_decided or is_out_verdict(vd)
        if not dead:
            continue                      # 待评 / 可投 / 可以考虑 永远不归档
        if k in applied_keys:
            continue                      # 投过的岗是台账与面板「已投递」的数据源
        if _cli.norm_url(e.get("url")) in material_urls:
            continue                      # 出过材料的花过工时，留在热库
        age = _age_days(e, ustate.get(k, {}), today)
        if age is None:
            continue                      # 连日期都没有的不动，宁可留着
        limit = DECISION_DAYS if user_decided else DEAD_DAYS
        if age < limit:
            continue
        why = ("你标了不投" if user_decided else
               "已下线" if st == "expired" else "判词出局")
        out[k] = f"{why} · {age} 天前"
    return out


def collect_applied_keys(user: str, seen: dict) -> set:
    """投过的岗的键。**用面板同一个 `match_tracker`**，不另写匹配规则。"""
    path = ROOT / "users" / user / "job_search_tracker.csv"
    rows = load_tracker(path)
    if not rows:
        return set()
    hit = set()
    for k, e in seen.items():
        job = {"company": e.get("company") or "", "title": e.get("title") or "",
               "url": e.get("url") or ""}
        if match_tracker(job, job["url"], rows):
            hit.add(k)
    return hit


def collect_material_urls(user: str) -> set:
    apps = ROOT / "users" / user / "documents" / "applications"
    if not apps.is_dir():
        return set()
    # **归一。** 这张表要和职位库的 `url` 对，而两边来源不同：这边是
    # markdown 里写的链接，那边是抓取器存的。协议不一样时对不上，
    # 后果是「出过材料的岗被归档」—— 而这条规则的全部意思就是
    # 「花过工时的留在热库」（`_cli.norm_url` 的 docstring 记了四次同类学费）。
    return {_cli.norm_url(a.get("url")) for a in find_applications(apps)
            if a.get("url")}


def _forget_overlay_keys(path: Path, keys) -> None:
    """把已归档的岗从叠加层删掉。**读回最新版本再删，不拿扫描时的快照覆盖。**

    归档扫盘要几秒，这期间用户可能在面板上点了「不投」。原来用扫描时那份
    `ustate` + 当时的戳写回：撞上就整条 `StaleWrite`，而此时热库与存档
    **已经写完了** —— `run_cli` 会补一句「你的数据一个字没动」，那是假话。

    现在按「删哪几个键」而不是「整份是什么」来写：每次重读、只 pop 这几个，
    别人新加的决定原样保留。连撞三次就抛，由 `run` 接住并如实报出。
    """
    keys = set(keys)
    for _ in range(3):
        if not path.is_file():
            return
        try:
            raw, stamp = _cli.load_json_stamped(path)
        except (ValueError, OSError, SystemExit):
            # 叠加层坏了不该让归档失败：用户决定已经折进存档条目里了。
            return
        if not isinstance(raw, dict):
            return
        hit = keys & set(raw)
        if not hit:
            return
        for k in hit:
            raw.pop(k, None)
        try:
            _cli.atomic_write(path, json.dumps(raw, ensure_ascii=False, indent=1),
                              expect=stamp)
            return
        except _cli.StaleWrite:
            continue
    raise _cli.StaleWrite(
        f"{path.name} 在归档期间被连着改了三次，已归档的那几条用户决定没清掉")


def run(user: str, apply: bool, today: _dt.date) -> dict:
    sj, arc = paths(user)
    if not sj.is_file():
        raise SystemExit(_cli.no_store(sj))
    data, stamp = _cli.load_json_stamped(sj)
    seen = _cli.seen_of(data)
    _cli.stop_on_unreadable_rows(seen, sj)
    us = _cli.user_state_path(sj)
    if us.is_file():
        try:
            raw_us, _us_stamp = _cli.load_json_stamped(us)
            ustate = ({k: v if isinstance(v, dict) else {}
                       for k, v in raw_us.items()} if isinstance(raw_us, dict)
                      else {})
        except (ValueError, OSError, SystemExit):
            ustate = {}
    else:
        ustate = {}
    chosen = pick(seen, ustate, collect_applied_keys(user, seen),
                  collect_material_urls(user), today)
    overlay_stale = ""
    if apply and chosen:
        old = json.loads(arc.read_text(encoding="utf-8")) if arc.is_file() else {"seen": {}}
        cold = _cli.seen_of(old)
        for k, why in chosen.items():
            e = seen.pop(k)
            e["archived_date"] = today.isoformat()
            # 用户决定折进条目里带走，叠加层里那条删掉——存档要自包含，
            # 不能留一半在另一个文件里等着变孤儿。
            row = ustate.pop(k, None)
            if row:
                e["status"] = row.get("decision") or e.get("status")
                if row.get("reason"):
                    e["skip_reason"] = row["reason"]
            cold[k] = e
        # 归档计数记在热库顶层，导出免费读到——不用每次去啃越长越大的冷库
        data["archived"] = {"count": len(cold), "date": today.isoformat()}
        _cli.atomic_write(arc, json.dumps(old, ensure_ascii=False, indent=1))
        _cli.atomic_write(sj, json.dumps(data, ensure_ascii=False, indent=1),
                          expect=stamp)
        try:
            _forget_overlay_keys(us, chosen)
        except _cli.StaleWrite as exc:
            # 热库与存档已经落盘了，这里**不能**让整条命令报「没写」。
            # 那几条叠加层记录对应的岗已经不在热库，留着也不会被再次归档；
            # 如实说清，下一轮不会再碰它们。
            overlay_stale = str(exc)
    return {"chosen": chosen, "hot": len(seen),
            "cold": (len(_cli.seen_of(json.loads(arc.read_text(encoding="utf-8"))))
                     if arc.is_file() else 0),
            "overlay_stale": overlay_stale}


def revive(user: str, apply: bool = False) -> dict:
    """把存档整个拉回热库。改了硬性条件要全库重判之前跑这一步。

    **整个拉回，不做挑选**——挑选逻辑就是评估本身，`/job-rank --all` 才是干这个的。
    拉回后仍然死的，下一轮归档会再送回去；一来一回的代价是几 MB 的搬运，
    换来的是这里零判断、零维护。

    ## `apply=False` 时只数，不搬

    这个工具 `--apply` 那面旗子的 help 写着「真的写盘。**不加就是试运行**」——
    那是对整条命令的承诺。而 2026-08-30 之前 `--revive` 这一支根本不看它：
    敲一次就把整份存档（实测 1074 个岗）搬回热库并写盘、删掉存档文件。

    仓库里七个工具都印 `_cli.DRY_RUN_NOTE`（「试运行，没有写盘」那句），
    肌肉记忆是现成的；**唯独这一条会当场动手**，而它动的量最大。
    """
    sj, arc = paths(user)
    if not arc.is_file():
        return {"revived": 0}
    data, stamp = _cli.load_json_stamped(sj)
    seen = _cli.seen_of(data)
    _cli.stop_on_unreadable_rows(seen, sj)
    cold = json.loads(arc.read_text(encoding="utf-8")).get("seen", {})
    before = len(seen)
    for k, e in cold.items():
        seen.setdefault(k, e)             # 热库已有同键的以热库为准——它更新
    if not apply:
        return {"revived": len(seen) - before, "dry": True}
    data["archived"] = {"count": 0, "date": _dt.date.today().isoformat()}
    _cli.atomic_write(sj, json.dumps(data, ensure_ascii=False, indent=1), expect=stamp)
    arc.unlink()
    return {"revived": len(cold)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="出局已久的岗收进存档；--revive 整个拉回")
    ap.add_argument("--apply", action="store_true", help=_cli.help_apply())
    ap.add_argument("--revive", action="store_true", help="把存档整个拉回热库（重判前用）")
    ap.add_argument("--user", help=_cli.HELP_USER)
    ap.add_argument("--today", help="判龄用的日期（测试用），默认今天")
    a = ap.parse_args(argv)
    # pick_user：全新 clone 上没有 `.active_user`，裸读是一坨 traceback——
    # 新用户第一次撞见的不该是栈回溯（_cli.pick_user 的 docstring 记着这条约束）
    user = _cli.pick_user(a.user or "", root=ROOT)
    if a.revive:
        r = revive(user, apply=a.apply)
        if r.get("dry"):
            print(f"会拉回 {r['revived']} 个岗到热库。")
            print(_cli.DRY_RUN_NOTE)
            return 0
        print(f"拉回 {r['revived']} 个。要重新评它们：/job-rank --all")
        return 0
    today = _cli.parse_today(a.today) or _dt.date.today()
    r = run(user, a.apply, today)
    n = len(r["chosen"])
    if not n:
        print(f"没有可归档的（热库 {r['hot']} 个 · 存档 {r['cold']} 个）")
        return 0
    verb = "已归档" if a.apply else "会归档（试运行，加 --apply 生效）"
    print(f"{verb} {n} 个 · 热库剩 {r['hot']} 个 · 存档共 {r['cold']} 个")
    for k, why in list(r["chosen"].items())[:10]:
        print(f"  {why:<18} {(seen_title(k))}")
    if n > 10:
        print(f"  …… 另有 {n - 10} 个")
    if r.get("overlay_stale"):
        # 热库和存档已经写完了，这不是「没写」——只说明叠加层里那几行
        # 用户决定没清掉。它们对应的岗已不在热库，不会再被归档。
        print(f"  ⚠ {r['overlay_stale']}。岗位已经归档，不影响存档；"
              f"叠加层里那几行可以手动删，或在下一轮归档时随热库一起清掉。",
              file=sys.stderr)
    print("存档在 job_scraper/archive.json，不是删除；要重新判定先 --revive")
    return 0


def seen_title(key: str) -> str:
    return key.split("#", 1)[1] if "#" in key else key[-40:]


if __name__ == "__main__":
    raise SystemExit(_cli.run_cli(main))
