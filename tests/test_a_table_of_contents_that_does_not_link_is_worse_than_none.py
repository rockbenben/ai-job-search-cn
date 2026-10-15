# -*- coding: utf-8 -*-
"""目录里的锚点必须真的跳得到 —— 坏链接的目录比没有目录更糟。

2026-10-14 给 `CONTRIBUTING.md` 加上 12 条目录时，这条就派上用场了。加之前先说过
「目录有没有用取决于锚点准不准」：它列了 12 个章节，如果其中三条的 `#` 目标算错了，
读者点一下落在页首，等于骗他一次 —— 而**页面上看不出哪条是坏的**，因为目录长得
和能用的目录一模一样。

## 判据

按 GitHub 的算法从标题推出锚点（小写 → 去掉不是字母/数字/CJK/空格/连字符的字符 →
空格变连字符），再比对目录里每一条 `](#…)`。

## 这条自己差点空转

第一版校验器用 `re.match` 去匹配 `- [标题](#锚点)` 这种**行首带 `- ` 的列表项**，
匹配到 0 条，然后打印「dead links: 0」—— 一条没查、报告全绿。
和同一天那次变异脚本忘了写盘是同一个形状：**仪器测了个空，却报出最好的结果。**
所以下面那条控制用例专门钉住「扫描器真的扫到了东西」。

（`## 为什么：…` / `## 代价：…` 那些论据小节不进目录，是有意的：它们是某条规矩的
展开，不是独立条目。）
"""

from __future__ import annotations

import re
import unicodedata
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRIB = ROOT / "CONTRIBUTING.md"

HEADING = re.compile(r"^(#{1,6})\s+(.*)")
TOC_LINK = re.compile(r"\[[^\]]+\]\(#([^)]+)\)")


def slug(heading: str) -> str:
    """GitHub 从标题推锚点的算法（够用的那一版）。"""
    s = heading.strip().lstrip("#").strip().replace("*", "").replace("`", "")
    keep = [c if c in " -_" or unicodedata.category(c)[0] in ("L", "N") else ""
            for c in s.lower()]
    return "".join(keep).replace(" ", "-")


def toc_links() -> list:
    return [(n, m.group(1)) for n, l in enumerate(_lines(), 1)
            if (m := TOC_LINK.search(l))]


def _lines() -> list:
    return CONTRIB.read_text(encoding="utf-8").splitlines()


def anchors() -> dict:
    out = {}
    for l in _lines():
        if m := HEADING.match(l):
            out.setdefault(slug(m.group(2)), m.group(2))
    return out


class TheTableOfContentsResolves(unittest.TestCase):
    def test_every_anchor_points_at_a_real_heading(self):
        have, bad = anchors(), []
        for n, target in toc_links():
            if target not in have:
                bad.append(f"CONTRIBUTING.md:{n}  #{target}")
        self.assertEqual(bad, [],
                         "目录里这些锚点跳不到任何标题：\n  " + "\n  ".join(bad)
                         + "\n标题里的全角括号、** 和 ` 都不进锚点，"
                           "而目录里那份是照抄标题的 —— 改标题就得同步改这一条")

    def test_the_scanner_actually_finds_the_toc(self):
        """控制用例：扫不到东西的守卫恒绿 —— 而它绿着的样子和「都跳得通」一样。

        第一版用 `re.match` 匹配行首带 `- ` 的列表项，命中 0 条就报了 0 死链。
        """
        links = toc_links()
        self.assertGreaterEqual(len(links), 12,
                                f"只扫到 {len(links)} 条目录链接 —— 目录被删了或换了写法？")

    def test_every_rule_section_is_reachable_from_the_toc(self):
        """规矩不许只活在正文里 —— 目录漏掉它，读者就找不到它。"""
        linked = {t for _, t in toc_links()}
        missing = [h for a, h in anchors().items()
                   if a not in linked and h.startswith("## ")
                   and not h.startswith("## 目录")]
        self.assertEqual(missing, [],
                         "这些 `## ` 小节不在目录里：" + "; ".join(missing))


if __name__ == "__main__":
    unittest.main()