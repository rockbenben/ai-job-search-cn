#!/usr/bin/env python3
"""把两份库的键收成一代：有链接的岗一律用 `stable_id(url, 职位名)` 当键。

## 为什么要它

职位库的键换过三代——裸 URL → `<url>#<职位名>` → `stable_id(url, 职位名)`，
而**旧键从来没迁过**。实测活动用户 2026-10-12：热库 993 条里 647 条是旧键，
存档 3163 条里 3040 条是旧键。

后果落在查重上。`job-scrape.md` Step 4 原来教的写法是并两边的键：

```python
seen_keys = set(seen) | set(_cli.archived(user))     # ← 两个名字都在，判据是错的
```

新入库的岗算的是 `stable_id`，存档里 96% 的条目挂着旧键——**这两串永远碰不上**。
把存档 3156 条各当成「下一轮又搜到了」模拟一遍：那两行只命中 **116 条（3.7%）**，
剩下 3040 条会被当新岗插回热库，而存档里那份原样留着。
这就是「同一个岗热库和存档各有一份」的来路，也是 2026-10-12 手工删掉那 58 个的来路。
两份还会各自演化：一个记 55「可以考虑」、一个记「硬门 FAIL」，谁也不知道该信哪个。

键本该只是「记路的」，岗的身份在条目的 `url` + `title` 里。把键收成一代之后，
`_cli.seen_index()`（按链接+职位名从**字段**算）和按键比对给出同一个答案，
以后谁来查重都不会再因为钥匙的代次漏掉半份库。

## 只做一件事：换键

- **一个字段都不改**——值原样搬，条目数不变。整个没有链接的条目算不出新键，
  维持原键（实测活动用户 2026-10-12：存档 3163 条里 7 条是这种，热库一条都没有）；
- **不合并、不删除**：两边同时在场由 `audit_pipeline`「同一个岗热库和存档各有一份」
  报出来给人裁决，这里不替他决定哪份新；
- **撞车就停**：两条不同的岗算出同一个新键时拒绝写盘并列出它们——
  那正是查重该抓的事，不能在这里用覆盖把它咽下去。

`user_state.json`（面板上「不投 / 已下线」那层叠加）与库共用键空间，所以跟着一起换：
只换库不换它，实测活动用户 2026-10-12 那 48 条标记里 42 条当场变孤儿，
面板上那些岗的按钮回到没点的样子。

## 用法

    python tools/rekey.py            # 试运行：列出会改哪些，不写盘
    python tools/rekey.py --apply    # 真的改

跑完的下一步是 `/job-scrape`——它现在按 `_cli.seen_index()` 查重。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import _cli  # noqa: E402

#: 三份文件里同属一个键空间的两份库 + 一层叠加
OVERLAY = "user_state.json"


def plan(rows: dict) -> tuple[dict, list]:
    """`{旧键: 那条岗}` → `({旧键: 新键}, [撞车的 (新键, 旧键A, 旧键B)])`。

    纯函数，好测。新键由 `_cli.job_key` 算——没链接的给 `None`，那种维持原键。
    撞车时**两条都不许占那个键**：宁可整份拒绝写盘，回头由人裁决。
    """
    mapping: dict[str, str] = {}
    taken: dict[str, str] = {}
    collisions: list[tuple[str, str, str]] = []
    for k, e in rows.items():
        nk = _cli.job_key(e) or k
        if nk in taken and taken[nk] != k:
            collisions.append((nk, taken[nk], k))
            continue
        taken[nk] = k
        if nk != k:
            mapping[k] = nk
    for nk, k1, k2 in collisions:
        mapping.pop(k1, None)            # 撞车的那两条都不许占那个键
    return mapping, collisions


def apply_rekey(rows: dict, mapping: dict) -> None:
    """就地换键：值一件不动，条目顺序按原样重放。

    **就地**是因为 `_cli.seen_of` 给的是原字典的引用（两代格式都认，见那里）——
    改它，`{"seen": …}` 与早期「整个文件就是 seen」两种形状都自然跟着走。
    这里不判格式、也不给外层字典重新赋值那个 `seen` 键：那种写法正是
    `tests/test_one_file_one_tolerance.py` 逐行扫的东西，
    而它扫到的一律是读不了老格式的地方。
    """
    if not mapping:
        return
    items = [(mapping.get(k, k), v) for k, v in rows.items()]
    rows.clear()
    rows.update(items)


def plan_overlay(ustate: dict, maps: list[dict]) -> tuple[dict, list]:
    """叠加层跟着换键。`maps` 是热库与存档的映射，一个旧键只会在其中一边。

    两边都没有的键**原样留着**：那可能是归档之前留下的孤儿，不在这里处理，
    也不在这里编一个新键给它。
    """
    merged: dict[str, str] = {}
    for m in maps:
        merged.update(m)
    mapping, collisions = {}, []
    #: 不换键的那些先占住自己的键——别的条目映射过来就是撞车
    taken: dict[str, str] = {k: k for k in ustate if k not in merged or merged[k] == k}
    for k in ustate:
        nk = merged.get(k)
        if not nk or nk == k:
            continue
        if nk in taken:
            collisions.append((nk, taken[nk], k))
            continue
        taken[nk] = k
        mapping[k] = nk
    return mapping, collisions


def _load(path: Path) -> tuple[dict, dict, object]:
    """`(整份 JSON, seen, 版本戳)`；文件不存在给空的。"""
    if not path.is_file():
        return {}, {}, None
    data, stamp = _cli.load_json_stamped(path)
    return data, _cli.seen_of(data), stamp


def run(user: str, apply: bool, root: Path = None) -> dict:
    base = _cli.store_dir(user, root)
    sj, arc = base / "seen_jobs.json", base / "archive.json"
    if not sj.is_file():
        raise SystemExit(_cli.no_store(sj))

    stores, collisions = [], []
    for path in (sj, arc):
        data, rows, stamp = _load(path)
        _cli.stop_on_unreadable_rows(rows, path)
        mapping, coll = plan(rows)
        collisions += [(path.name, *c) for c in coll]
        stores.append({"name": path.name, "path": path, "data": data,
                       "rows": rows, "stamp": stamp, "mapping": mapping})

    ost = _cli.user_state_path(sj)
    orows = _cli.load_user_state(sj)
    omapping, ocoll = plan_overlay(orows, [s["mapping"] for s in stores])
    collisions += [(OVERLAY, *c) for c in ocoll]
    if collisions:
        return {"collisions": collisions, "stores": [], "overlay": None}

    if apply:
        for s in stores:
            if not s["mapping"]:
                continue
            apply_rekey(s["rows"], s["mapping"])
            _cli.atomic_write(s["path"],
                              json.dumps(s["data"], ensure_ascii=False, indent=1),
                              expect=s["stamp"])
        if omapping:
            new = {omapping.get(k, k): v for k, v in orows.items()}
            _cli.atomic_write(ost, json.dumps(new, ensure_ascii=False, indent=1))

    tokens = [{_cli.job_token(e.get("url"), e.get("title"))
               for e in s["rows"].values()
               if isinstance(e, dict) and e.get("url")} for s in stores]
    return {"collisions": [], "stores": stores,
            "overlay": {"total": len(orows), "moved": len(omapping)},
            "overlap": len(tokens[0] & tokens[1])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="把两份库的键收成一代（链接+职位名派生）；不改任何值")
    ap.add_argument("--apply", action="store_true", help=_cli.help_apply())
    ap.add_argument("--user", help=_cli.HELP_USER)
    a = ap.parse_args(argv)
    user = _cli.pick_user(a.user or "", root=ROOT)
    r = run(user, a.apply)

    if r["collisions"]:
        print("✗ 有两条不同的岗算出同一个键，拒绝写盘：")
        for f, nk, k1, k2 in r["collisions"][:10]:
            print(f"  {f}  新键 {nk}\n    {k1[:60]}\n    {k2[:60]}")
        print("  这就是「同一个岗存了两份」。这里不代删——哪份新要看评分日期和有没有材料。")
        print("  逐个看：/job-apply <职位链接>")
        return 1

    total = sum(len(s["rows"]) for s in r["stores"])
    moved = sum(len(s["mapping"]) for s in r["stores"])
    for s in r["stores"]:
        print(f"  {s['name']:<18} 共 {len(s['rows'])} 条 · 换键 {len(s['mapping'])}"
              f" · 原样 {len(s['rows']) - len(s['mapping'])}")
    print(f"{'已' if a.apply else '会'}换键 {moved} 条（共 {total} 条），值一个不改；"
          f"面板上那 {r['overlay']['total']} 条标记跟着换 {r['overlay']['moved']} 条。")
    print(f"同一个岗热库和存档各有一份：{r['overlap']} 个。")
    if r["overlap"]:
        print("  这里不代删。逐个看：/job-apply <职位链接>，"
              "完整清单跑 python tools/audit_pipeline.py。")
    if not a.apply:
        print(_cli.DRY_RUN_NOTE)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli.run_cli(main))
