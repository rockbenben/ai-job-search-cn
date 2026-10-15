# -*- coding: utf-8 -*-
"""工作流里 `某文件.md`「某节」式的引用，目标文件里必须真有那一节。

## 为什么

`workflows/` 是 AI 的执行手册，跨文件小节引用是**活的跳转**：`/job-apply` 执行到
「见 `06-outreach-templates.md` 的「渠道 4」」时会真的去找那一节。目标标题
改名后引用不会自己报错——AI 找不到就凭记忆补，两份文档各说各话。

实测第一次跑就抓到 4 处失联：

    apply.md      → 06「渠道 4：正式求职信（场景触发）」     标题后来加了「，非默认」
    interview.md  → 04「雇主匿名——按未知打，不按坏打」       标题中间插了长括注
    setup.md      → 05「章节顺序按行业定一次」                标题里是「定**一次**」（排版符）
    07-interview-prep.md → 04「沟通阶段该问什么」             那一节实际叫「投递前：先沟通还是先投简历」

第 3 处是检查器的教训：**标题里的 `**` 是排版不是内容**，比对前要剥掉，
否则会逼着所有引用把排版符也抄上。

## 判据

引用文本在目标文件里满足其一即算解析成功：

1. 出现在某个标题行里（剥掉 `*` 后子串匹配）——引用一节；
2. 以 `**词**` 粗体或 `「词」` 引号形式出现在正文——引用一个**命名概念**
   （「判词天花板」「差一口气」这类不是标题但有名字的东西）。

宽判据是刻意的：这里抓的是**失联的指针**，不是排版风格。
"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: 引用形如 `xxx.md`「标题」，中间容许「里/的/中」连接词
REF = re.compile(r"`?([\w\-./]+\.md)`?\s*(?:里|的|中)?\s*[「『]([^」』\n]{2,40})[」』]")


def docs() -> dict:
    out = {}
    # `docs/tool-entries.md` 是 2026-09-29 Task 10 从 AGENTS.md 搬出去的那一节。
    # `docs/finding-gaps.md` 是 2026-10-14 从 `CONTRIBUTING.md` 里"怎么先找到还没被
    # 守住的地方"那一节（连它底下 8 个小节）整节搬出去的。搬出去的节要是没人扫，
    # 「某文件的『某节』」这类指针就在新家失联也没人知道，
    # 而指向它的引用（workflows/job-auto.md 就有一条）也会被 `target not in d`
    # 那一行直接放过 —— 搬家把一道判据搬成空转。
    for p in (list((ROOT / "workflows").rglob("*.md"))
              + [ROOT / "AGENTS.md", ROOT / "CLAUDE.md",
                 ROOT / "docs" / "tool-entries.md",
                 ROOT / "docs" / "finding-gaps.md"]
              + sorted((ROOT / "docs" / "why").glob("*.md"))):
        out[p.name] = (p.relative_to(ROOT).as_posix(), p.read_text(encoding="utf-8"))
    return out


def resolves(section: str, target_text: str) -> bool:
    plain = section.replace("*", "")
    for line in target_text.splitlines():
        if line.startswith("#") and plain in line.replace("*", ""):
            return True
    return f"**{plain}**" in target_text or f"「{plain}」" in target_text


class CrossFileSectionRefsResolve(unittest.TestCase):

    def test_every_reference_points_at_something_real(self):
        d = docs()
        bad = []
        for name, (rel, t) in d.items():
            for m in REF.finditer(t):
                target = Path(m.group(1)).name
                if target not in d:
                    continue          # 指向 README 等仓库文档的另有 docs 测试管
                if not resolves(m.group(2), d[target][1]):
                    ln = t[:m.start()].count("\n") + 1
                    bad.append(f"{rel}:{ln} → {target}「{m.group(2)}」")
        self.assertEqual(
            bad, [],
            "这些跨文件引用在目标文件里找不到对应小节——多半是那边的标题改了名：\n  "
            + "\n  ".join(bad)
            + "\n改法：把引用改成目标文件现在的标题（或它包含的稳定短语），"
            "不要反过来为了迁就引用改标题。")

    def test_the_scan_actually_finds_references(self):
        """控制用例：引用正则一改就可能扫空，空扫永远绿。"""
        d = docs()
        n = sum(1 for _, (_, t) in d.items()
                for m in REF.finditer(t) if Path(m.group(1)).name in d)
        self.assertGreater(n, 30, f"只扫到 {n} 条跨文件引用，像是正则失效了")

    def test_bold_markers_in_headings_do_not_break_matching(self):
        """`### 章节顺序按行业定**一次**` 必须能被「章节顺序按行业定一次」引用到。"""
        self.assertTrue(resolves("章节顺序按行业定一次",
                                 "### 章节顺序按行业定**一次**，之后不再动\n"))

    def test_a_renamed_section_is_caught(self):
        self.assertFalse(resolves("沟通阶段该问什么",
                                  "## 投递前：先沟通还是先投简历\n**问什么**：…\n"))


if __name__ == "__main__":
    unittest.main()
