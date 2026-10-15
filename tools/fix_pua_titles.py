# -*- coding: utf-8 -*-
"""职位标题里被字体混淆的薪资，用同一条记录自己的 `salary` 换回来。

    python tools/fix_pua_titles.py            # 只看，不写盘
    python tools/fix_pua_titles.py --apply    # 写回 seen_jobs.json

## 那不是乱码，是**字体混淆**

页面用自定义字体把数字映射到 Unicode **私用区**（U+E000–U+F8FF）。截图上
肉眼是 `30-50K`，文本里却是 `\\ue037\\ue031-\\ue039\\ue031K`。抓取时连映射
一起抄了下来，于是标题在库里长这样：

    示例产品经理（示例方向 × 示例策略） \\ue037\\ue031-\\ue039\\ue031K·\\ue032\\ue035薪

实测活动用户 2026-10-14：**1628 条里 75 条**中招（面板 1354 个岗里 74 个），
全部在 `title` 字段。`cdp-portals.md` 里记着 BOSS 那一路的同一现象。

## 为什么不照着映射解，而要用 `salary`

`cdp-portals.md` 写得很清楚：**那个映射每轮都不一样，不可硬编码**
（2026-10-13 那轮是 `U+E03n → n-1`）。硬编码一份，下一轮抓回来就又错了。

而猎聘走 JSON API——**薪资本来就是结构化字段**，同一条记录里的 `salary`
已经是对的（`30-50K*15薪`）。所以这里一个映射都不用写：直接用同记录的
`salary` 替换标题末尾那段 PUA，**天然免疫「每轮都变」**。

逐条验过（2026-10-14）：按那一轮的映射解混淆后，**75 条全部**以本记录
自己的 `salary` 结尾，一条不差 —— 即 PUA 段与 `salary` 是同一件事。

## 它还顺手改一处文件名（不做这一半，这 54 个岗会丢掉 JD 正文）

`jd_store` 的详情文件是**按 `stable_id(url, title)` 命名的**，而导出器找它也是按同一个
函数现算（`export_web_data.py` 的 `details_dir / f"{stable_id(...)}.json"`）。
改标题 → id 变 → 找不到文件。实测 2026-10-14：75 条里有 **54 条**本来有
`details/<id>.json`，改完就全都对不上了。

所以写回盘之后要把这些文件改名。**改名之前先核内容**：文件里带自己的 `url`，
与条目对不上的一律不动 —— 按名搬文件最容易搬错的就是这个。实测这 54 条
逐条对得上（0 条不符）。

（`details/` 里本来就有 1819 个「无人引用」的孤儿文件，那是既有的，
与本次无关：改前 1819，改后 1873，正好差这 54。）

## 它不碰什么

- **没有 `salary` 的不猜。** 按本仓库一贯口径：解不通就如实跳过并报数，
  不输出半信半疑的文字。
- **PUA 不在末尾的一律不碰。** 职位名中间出现私用区字符多半是别的东西，
  按位切会削掉职位名本身——宁可漏修。
- **标题里 PUA 之前的内容一个字不动。** 只换尾部那一段。
- **内容里的 url 与条目对不上的详情文件，不改名。** 不拿「看着像」当证据。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402

#: 私用区、薪资骨架、**以及切点判据本身**，正本都在 `_cli` —— 这里只引，不另抄一份。
#: 第一版把前两个常量在本文件里又定义了一遍，`test_one_value_one_home.py` 当场报出
#: 「同一个值住在两个模块里，没人钉住它们相等」。导出侧的兜底用的是同一份。
#:
#: **切点判据（`salary_split`）是同一个教训的第二轮**：当时搬走了常量，却把用它们的
#: 那套切法留在这里，于是 `_cli.plain_title` 与本文件各判一次「哪里该切」。算法比
#: 常量更容易漂 —— 改了切点，导出侧显示的标题与这个工具写回库的标题就会分叉，而两边
#: 都不报错。所以 `salary_tail` 现在只是正本的一层壳。
#:
#: 正本那边的注释记着两条踩过的坑：判据写成「认得几个货币单位」会把**日薪**
#: （`…元/天`）判成「切错地方」而跳过；职位名自己带数字（`【99校招】`、`8000+`），
#: 所以切点只能取 PUA 之前最近的空格，骨架里必须容得下小数点（形如 `3.5-4.5K`）。
PUA = _cli.PUA_RE


def salary_tail(title: str) -> tuple[str, str] | None:
    """`(该保留的头, 该换掉的尾)`。判据在 `_cli.salary_split`（正本）。"""
    return _cli.salary_split(title)


def plan(user: str):
    p = ROOT / "users" / user / "job_scraper" / "seen_jobs.json"
    seen = _cli.seen_of(json.loads(p.read_text(encoding="utf-8")))
    rows, skip = [], {"没有 salary（不猜）": 0, "PUA 不在末尾（不切）": 0}
    for key, v in seen.items():
        if not isinstance(v, dict):
            continue
        title = str(v.get("title") or "")
        if not PUA.search(title):
            continue
        salary = str(v.get("salary") or "").strip()
        if not salary:
            skip["没有 salary（不猜）"] += 1
            continue
        parts = salary_tail(title)
        if not parts:
            skip["PUA 不在末尾（不切）"] += 1
            continue
        head, _tail = parts
        new = head + salary
        if new != title:
            rows.append({"key": key, "entry": v, "old": title, "new": new})
    return rows, skip


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true", help=_cli.help_apply())
    ap.add_argument("--user", default="", help=_cli.HELP_USER)
    a = ap.parse_args(argv)
    user = _cli.pick_user(a.user or "", root=ROOT)
    rows, skip = plan(user)
    print(f"标题里带私用区字符的，换回本记录的 salary（用户：{user}）")
    print(f"  要改 {len(rows)} 个；跳过："
          + "、".join(f"{k} {n}" for k, n in skip.items() if n))
    for r in rows[:8]:
        print(f"  {r['old'][:34]:<36} → {r['new'][-30:]}")
    if len(rows) > 8:
        print(f"  …另有 {len(rows) - 8} 个")
    if not a.apply:
        print(chr(10) + _cli.DRY_RUN_NOTE)
        return 0
    p = ROOT / "users" / user / "job_scraper" / "seen_jobs.json"
    store = json.loads(p.read_text(encoding="utf-8"))
    seen = _cli.seen_of(store)
    for r in rows:
        seen[r["key"]]["title"] = r["new"]
    _cli.atomic_write(p, json.dumps(store, ensure_ascii=False, indent=1))
    print(f"\n已写回 {len(rows)} 个")

    renamed, skipped = rename_details(user, rows)
    print(f"详情文件改名 {renamed} 个"
          + (f"；跳过 {skipped} 个（内容里的 url 与条目对不上）" if skipped else ""))
    return 0


def rename_details(user: str, rows) -> tuple[int, int]:
    """`details/<id>.json` 是按 id 命名的，标题一改 id 就变。把它们改名跟上。

    **先核内容再改名**：文件里带着自己的 `url`，与条目对不上的一律不动。
    对得上才说明搬对了 —— 按名字猜正是最容易搬错的方式。
    """
    details = ROOT / "users" / user / "job_scraper" / "details"
    if not details.is_dir():
        return 0, 0
    done, skipped = 0, 0
    for r in rows:
        url = r["entry"].get("url") or r["key"]
        old_id = _cli.stable_id(url, r["old"])
        new_id = _cli.stable_id(url, r["new"])
        if old_id == new_id:
            continue
        src, dst = details / f"{old_id}.json", details / f"{new_id}.json"
        if not src.is_file() or dst.exists():
            continue
        try:
            body = json.loads(src.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        inside = body.get("url") or body.get("职位链接") or ""
        if _cli.norm_url(str(inside)) != _cli.norm_url(str(url)):
            skipped += 1
            continue
        src.rename(dst)
        done += 1
    return done, skipped


if __name__ == "__main__":
    raise SystemExit(_cli.run_cli(main))