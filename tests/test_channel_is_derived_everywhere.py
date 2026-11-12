# -*- coding: utf-8 -*-
"""`channel` 那一列历来是空的 —— 每个读它的地方都要从 `source` 反推。

实测活动用户 85 条投递：**`channel` 列 85 行全空**。而「哪个网站回复率高」是国内
求职里最要紧的问题之一，答案一直在表里 —— `source` 存的就是原始链接
（判据只有一份：`tracker.channel_of`）。

三个消费方读这一列。2026-08-22 查下来：

    /job-html-report   写了「取不到就从 source 推」   ✓
    /job-outcome       写了                           ✓
    /job-notion-sync   **没写** —— 照原样倒，看板上那一列就是一片空白

**同一个人在三个界面上会看到三种说法。** 这和 `/job-cv` 漏掉链接查找是同一个
形状：一条规矩加在 N 个消费方里的 N-1 个上，剩下那个照旧。
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _consumers() -> list:
    """读 `channel` 那一列、要显示平台名的工作流 —— **从正文推导**。

    这里原来是手写的三个文件名，注释还写着「加新的消费方时也要加进这张表」
    —— 那是一道人工步骤，而这个仓库的手写名单**反复漏**：`JD_READERS` 漏两条、
    `GUARDS` 漏两条（其中一条是主线命令 `/job-auto`）、`WRITERS` 漏三条、
    `MUST_APPEAR` 只覆盖 21 条里的 10 条。2026-09-02 一并换成推导。

    改的时候推导出的正好还是那三个（没有现存缺口）—— 换的是**门的形式**：
    从「记得加名字」变成「读了 channel 就自动进门」。

    引用块不算：那是记事，不是这条命令真在读。
    """
    out = []
    for wf in sorted((ROOT / "workflows").glob("job-*.md")):
        body = "\n".join(l for l in wf.read_text(encoding="utf-8").splitlines()
                         if not l.lstrip().startswith(">"))
        if re.search(r"`channel`|channel[ ]*那一列|渠道.{0,4}列", body):
            out.append(wf.name)
    return out


class EveryConsumerDerivesIt(unittest.TestCase):
    def test_the_scan_finds_consumers(self):
        """控制用例：推导得出几条，否则下面那条对着空气跑。"""
        got = _consumers()
        self.assertGreaterEqual(len(got), 3, f"只推导出 {got} —— 判据八成失效了")

    def test_each_one_names_the_single_source(self):
        for name in _consumers():
            t = (ROOT / "workflows" / name).read_text(encoding="utf-8")
            with self.subTest(cmd=name):
                self.assertIn("channel_of", t,
                              f"{name} 读 channel 却没指向反推的正本")
                self.assertIn("source", t, f"{name} 没说从哪个字段推")

    def test_the_single_source_still_exists(self):
        """判据的前提。`channel_of` 没了，上面那条就成了空指针。"""
        tk = (ROOT / "tools" / "tracker.py").read_text(encoding="utf-8")
        self.assertIn("def channel_of", tk)
        self.assertIn("source", tk, "反推不再读 source 了")

    def test_the_derivation_is_not_narrower_than_the_literal(self):
        """**推导不许比字面窄。**

        原来这条查的是「手写名单漏没漏」；名单换成推导之后，会漏的换成了
        **判据本身**：把那个正则收紧一点，读 `channel` 的文件就悄悄少几个，
        而上面那条照样绿 —— 这个仓库给这个形状起过名字：
        「写了、跑着、绿着，但看不见」。

        所以拿最朴素的字面（文里出现 `` `channel` ``）当下界对一遍。
        """
        literal = sorted(
            f.name for f in (ROOT / "workflows").glob("job-*.md")
            if "`channel`" in "\n".join(
                l for l in f.read_text(encoding="utf-8").splitlines()
                if not l.lstrip().startswith(">")))
        missing = [n for n in literal if n not in _consumers()]
        self.assertEqual(
            missing, [],
            f"这些工作流正文里有 `channel`，而推导没把它们算进消费方：{missing}")


class TheBoardDoesNotInviteReadingTheGuess(unittest.TestCase):
    """`Fit` 是评之前按标题给的猜测，`Verdict` 是读过正文的结论。

    实测全库对账：**fit 说 202 个高匹配、判词说 128 个可投，单岗错位 204 个**
    （`query_yield.is_high` 那段注释）。看板上两列并排，很容易照 `Fit` 排序 ——
    那是在用一个评之前的猜测挑岗。
    """

    def test_the_caveat_is_next_to_the_field(self):
        t = (ROOT / "workflows" / "job-notion-sync.md").read_text(encoding="utf-8")
        self.assertRegex(t, r"评之前按标题给的猜测|不是结论|粗略标记",
                         "看板没说清 Fit 是猜测")
        self.assertRegex(t, r"有\s*`Verdict`\s*时.+?为准",
                         "没说清两列冲突时信哪个")

    def test_the_measured_mismatch_is_recorded(self):
        t = (ROOT / "workflows" / "job-notion-sync.md").read_text(encoding="utf-8")
        self.assertRegex(t, r"错位|query_yield\.is_high", "没记下两者错位")


if __name__ == "__main__":
    unittest.main()
