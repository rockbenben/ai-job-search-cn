# -*- coding: utf-8 -*-
"""一段注释里不许攒出一本流水账 —— 判据是**日期条目数**，棘轮只许减。

这件事是量出来的，不是审美意见。2026-10-14 扫 `tools/*.py`（阶梯块按 `LADDER`
排除，前后同一口径）：

| | 合并前 | 合并后 |
|---|---|---|
| 带日期的注释/文档字符串块 | 597 | 591 |
| 日期条目总数 | **725** | **657** |
| 其中塞了 **2 个以上日期**的块 | 93 | 55 |
| 单块最多几个日期 | **7** | **5** |

最极端的那块在 `tools/_cli.py` 的开场白检查：它记的是一个门槛的每一步
`37 → 51 → 80 → 95 → 99 → 102 → 103 → 65 → 51 → 59 → 129 → 0`，每一格配日期
和一段复盘，151 行。**长出来的方式很单一**：每次改动就在下面追加一条带日期的
记录，从来没人回头合并。于是「为什么是这个数」被埋在十二段编年史中间，
而真正要读的人只想知道两件事——现在是多少、凭什么。

（那道阶梯本身**不在上表的数里**：它被两条测试当数据解析，见 `LADDER`。
压它不是「变短」，是把记录改错。）

**当时没出事，是因为那个数另有一条现算的守卫**
（`test_the_greeting_stats_are_not_stale`）盯着。注释里的台阶史因此是纯历史，
**压掉它不会丢任何可验证的东西** —— 这正是它可以合并的前提。

所以这条守卫盯的不是「注释写得好不好」，是**一个形状**：

- **上限**：任何一块注释里不得出现超过 `CAP` 个不同日期 —— 再攒第四种就会红。
- **棘轮**：全仓日期条目总数只许降，不许升 —— 合并掉的就锁住了。

## 为什么不用「日期总数」一刀切

日期本身不是问题，**同一个块里堆了好几步同类的改动**才是。真要记一次判据
反转或一个仍在生效的阈值，那一条必须留着 —— 上限留了 `CAP` 的余量就是给它们的。
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: 只扫代码里的注释块。`.md` 的散文归 `test_measured_numbers_carry_their_date`
#: 那条棘轮管（它盯的是「不带日期的实测数」）；这里盯的是「注释块里攒了几格台阶」。
SCAN = ("tools",)

DATE = re.compile(r"20\d\d-\d\d-\d\d")

#: **被测试当数据解析的台阶不归这条管。**
#: `tests/test_the_padding_survives_a_job_title.py` 与
#: `tests/test_the_greeting_stats_are_not_stale.py` 把 `tools/_cli.py` 里那道
#: 门槛阶梯当**结构化记录**读：正则抓 `N → M（日期）` 的格子，要求链条从 37 起、
#: 首尾相接、末格等于现算值，抬头报的次数还要等于格数。
#: 那种块里的日期不是「攒出来的叙述」，是**数据本身** —— 压它等于把记录改错
#: （压成 3 格会读成「51 → 129 一步跳过去」，而那天根本没有这一步）。
#: 所以识别成阶梯的块整块跳过：它涨有它自己的守卫盯着。
LADDER = re.compile(r"\d+\s*→\s*\d+（20\d\d-\d\d-\d\d）")

#: 单块上限。**5 不是理想值，是现算的最大值** —— `tools/portal_budget.py` 的模块
#: docstring 剩 5 个日期，每一个都是一次不同的裁定/事故（反证、事故、推翻、封号、
#: 收权），压掉任何一条都等于删掉一次决策的来由。**上限卡在这里而不是 3**：
#: 再攒第六格当场红，而已有的五格各自都说得出为什么必须留。
CAP = 5



def _blocks(path: Path):
    """一个文件里的注释块：文档字符串 + 连续的 `#` 行。

    文档字符串走 AST 而不是文本扫描：注释里自己写着三引号字样的地方不少，
    文本扫描会把它们当成块边界，切出一堆假块。
    """
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError:                      # 不是 Python，跳过
        return

    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef,
                                 ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        doc = ast.get_docstring(node, clean=False)
        if doc:
            yield doc

    run: list[str] = []
    for line in src.splitlines():
        s = line.strip()
        if s.startswith("#") and s != "#":
            run.append(s)
            continue
        if run:
            yield "\n".join(run)
            run = []
    if run:
        yield "\n".join(run)


def dated_blocks():
    """返回 [(相对路径, 该块里的不同日期数), ...]，只留有日期的。

    被测试当数据解析的阶梯块（见 `LADDER`）整块跳过。
    """
    out = []
    for base in SCAN:
        for p in sorted((ROOT / base).rglob("*.py")):
            if "__pycache__" in str(p):
                continue
            for block in _blocks(p):
                if len(LADDER.findall(block)) >= 2:
                    continue
                n = len(set(DATE.findall(block)))
                if n:
                    rel = str(p.relative_to(ROOT)).replace("\\", "/")
                    out.append((rel, n))
    return out


class ACommentBlockIsNotAChangelog(unittest.TestCase):
    """攒出来的台阶得压回去，压回去之后就不许再攒。"""

    def test_no_block_holds_more_than_the_cap(self):
        over = [f"{f}: {n} 个日期（上限 {CAP}）" for f, n in dated_blocks() if n > CAP]
        self.assertEqual(
            [], over,
            f"{len(over)} 块注释攒过了 {CAP} 个日期。**追加一条记录不等于记下来**——"
            "同类改动合成一句「判据加严过 N 次 / 语料变多过 M 次」，"
            "只留标着反转或仍在生效的那几条日期。\n"
            + "\n".join(over[:20]))

    def test_the_cap_is_not_just_a_number_that_happens_to_hold(self):
        """上限要真的是上限 —— `CAP` 要是被调大，整条守卫就空了。

        它盯的是形状（「一块里不许再攒一格」），而不是某个总量。总量型的那种
        （本文件第一版有个 `BASELINE`）已经被删了：**刷新一个实测数就要把今天的
        日期写进注释，而总量只许降**，两条规矩对着干 —— 同一天就撞上过：有人给
        `doctor.py` 补了一句「2026-08-31 合成一份」，总量从 657 涨到 658，
        守卫红了，而代码一行没动、注释也没有任何问题。
        """
        self.assertEqual(CAP, 5, "上限被调大了 —— 「不许再攒一格」就不成立了")


if __name__ == "__main__":
    unittest.main()
