# -*- coding: utf-8 -*-
"""表格行不许掉出表格 —— 源码里看着是表，渲染出来是一堵竖线。

## 这一类只有渲染出来才看得见

2026-08-21 通读 `job-auto.md` 时撞上：「停手条件」那张表有 9 条，
中间插了一段 `> ⚠️ …` 的块引用。GFM 规则下，**块引用后面紧跟的 `|…|` 行
会被当成块引用那一段的延续吸进去**——实测渲染的结果是：

    表格数 1 · 行数 3      ← 表头 + 前 2 条
    另外 7 条在一个 <p> 里，带着字面的竖线

也就是说「用户喊停」「达到 `--target`」「循环跑满 20 轮」这几条最要紧的
停手条件，在 GitHub 上根本不是表格行，而是灰底块引用尾巴上的一段乱码样的字。
**源码里逐行看全都对**，`grep` 也永远抓不到——它不是缺字、不是错字，
是块结构。

同一次扫描在 `cdp-portals.md` 里抓到第二处，形状不同：额度表的后 3 行
被 2026-08-20 插进来的两个 `###` 小节冲散了，成了**没有表头的孤儿行**。

## 判据为什么不 import markdown

本仓库对外声明「只用 Python 标准库」（`test_python_dependency_is_stated_honestly`
盯着），CI 的干净 clone 里也没有 `markdown`。所以这里按 GFM 的块规则自己走一遍：
一行 `|…|` 只有在**表头 + 分隔行**开启的连续块里才算表格行，
中间隔了空行、块引用、段落，后面的行就都掉出去了。

发现那两处用的是真渲染（本机装了 `markdown`），落地成判据用的是这份复刻——
两者在这两处上的结论一致，`test_the_detector_finds_the_known_shapes` 把
两种已知形状钉成了内建变异。

**块引用里的表格（`> | a | b |`）不在管辖范围**：它整行不以 `|` 开头，
这里一律跳过。漏报可以，误报会逼着人去改本来是对的东西。
"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(Path(__file__).resolve().parent))
import md  # noqa: E402  围栏的规范走法，别再手写奇偶开关

#: 不进版本库的目录。**这里不复用 `test_docs_track_the_framework._all_docs`**——
#: 它的 SKIP 里带着 `workflows`（它服务的是「新人会读的那几份」那条判据）。
#: 第一版就是拿它当枚举器写的，于是**两处发现所在的目录一份都没扫到**，
#: 变异验证时判据在真文件上不亮才发现（2026-08-21）。
#: 借尺子之前先看它量的是哪一段。
SKIP = {".git", "node_modules", "__pycache__", ".pytest_cache",
        "dist", "users", ".private", ".superpowers"}
#: **2026-10-14 把 `docs` 从这里拿掉。** 它原来在名单里，而 `docs/tool-entries.md`
#: 里那张 13 行的工具表被两段引用块从中间劈开 —— 后 7 行渲染时没有表头，
#: 「四列都是量出来的」那句保证对它们不再生效。**正是这条守卫要抓的形状，
#: 却因为整个目录没被扫而一直绿着。** 本文件自己的注释写着「借尺子之前先看
#: 它量的是哪一段」，这里就是那次没看的后果。

#: 扫到的份数下限。**这一条才是「悄悄扫窄了」的解药**：
#: 判据全绿有两种可能——真没问题，或者根本没扫到东西。下限把后者变成红。
FLOOR = 60

#: 分隔行：`|---|---|`、`|:--|--:|` 都算
DELIM = re.compile(r"^\|[\s:|-]*-[\s:|-]*\|$")


def shipped_docs() -> list:
    return sorted(p for p in ROOT.rglob("*.md")
                  if not (set(p.relative_to(ROOT).parts[:-1]) & SKIP))


def orphan_rows(text: str) -> list:
    """返回 (行号, 该行) —— 长得像表格行、但不在任何表格里的行。

    **围栏走 `md.fenced_lines`，不数奇偶。** 这里原来是 `in_fence = not in_fence`
    ——正是 `tests/md.py` 存在的理由，它的模块说明第一句就写着「数 ``` 的个数
    是错的：一个 ```` 包裹、内含单行 ``` 的合法片段会数出奇数个」。
    这个判据扫的是全部 60 多份出货 markdown：任何一份里出现加长或嵌套围栏，
    开关就翻反，**那之后整份文件的判定全部颠倒**——围栏里的假表格行被报红，
    围栏外的真孤儿行被静默跳过。同一份改动刚在另外两处修掉了这个写法
    （`build_dashboard.unwrap_soft_wraps`、`test_workflow_prose_is_chinese._walk`）。
    """
    out, in_table = [], False
    lines = text.splitlines()
    fenced = {n for n, _, _ in md.fenced_lines(text)}
    for i, raw in enumerate(lines):
        s = raw.strip()
        if i + 1 in fenced or s.startswith("```") or s.startswith("~~~"):
            in_table = False          # 围栏行与围栏内的行都不参与表格判断
            continue
        if not (s.startswith("|") and s.endswith("|") and len(s) > 2):
            in_table = False          # 空行、段落、块引用 —— 表格到此为止
            continue
        if in_table:
            continue                  # 已经在表里，正常的一行
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if DELIM.match(nxt):
            in_table = True           # 这是表头，下一行是分隔行 —— 开表
            continue
        out.append((i + 1, s))
    return out


class TableRowsStayInTheirTable(unittest.TestCase):

    def test_no_shipped_doc_has_orphan_rows(self):
        docs = shipped_docs()
        self.assertGreaterEqual(
            len(docs), FLOOR,
            f"只扫到 {len(docs)} 份 markdown —— 枚举被改窄了，全绿是假的")
        bad = []
        for p in docs:
            for n, s in orphan_rows(p.read_text(encoding="utf-8")):
                bad.append(f"{p.relative_to(ROOT).as_posix()}:{n}: {s[:60]}")
        self.assertEqual(
            bad, [],
            "这些行在源码里长得像表格行，渲染出来是一段带竖线的散文 —— "
            "中间多半隔了块引用、空行或小标题：\n  " + "\n  ".join(bad))

    def test_the_detector_finds_the_known_shapes(self):
        """内建变异：当天实测撞到的两种形状都必须被认出来。"""
        quote_split = (
            "| 条件 | 处理 |\n|---|---|\n| A | 停 |\n"
            "> 一段解释，没有空行隔开\n"
            "| 用户喊停 | 随时 |\n")
        blank_split = (
            "| 条件 | 处理 |\n|---|---|\n| A | 停 |\n\n"
            "| 用户喊停 | 随时 |\n")
        orphan = "一段正文。\n| 每家每天轮数 | ≤2 |\n"
        for name, t in (("块引用截断", quote_split),
                        ("空行截断", blank_split),
                        ("没有表头的孤儿行", orphan)):
            with self.subTest(shape=name):
                self.assertTrue(orphan_rows(t), f"这种形状没被认出来：{name}")

    def test_a_healthy_table_is_not_flagged(self):
        """反向：正常的表、围栏里的竖线、块引用里的表都不许误报。"""
        ok = (
            "| 条件 | 处理 |\n|---|---|\n| A | 停 |\n| B | 继续 |\n\n"
            "```bash\n| 这是围栏里的 |\ngrep x | wc -l\n```\n\n"
            "> | 块引用里的表 | 不管 |\n> |---|---|\n")
        self.assertEqual(orphan_rows(ok), [],
                         "正常写法被误报了，判据会逼人去改对的东西")


if __name__ == "__main__":
    unittest.main()
