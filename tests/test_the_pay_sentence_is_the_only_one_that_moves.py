# -*- coding: utf-8 -*-
"""`score.py` 改薪资维时，**只改依据里属于薪资的那一句**。

## 事故

2026-10-12 一轮 `/job-auto`：`tools/score.py --apply` 把三条依据写坏了。
原来的实现是 `SAID.sub(全局替换)` —— 拿「薪资与职级」的新值去换依据里
**每一个**「给 NN」。实测：

    原文  「强度与公司性质这一维给 50……发展与风险这一维给 50……」
    改后  「强度与公司性质这一维给 55……发展与风险这一维给 55……」

那两句话在说强度和发展，给出来的数是薪资的。这一格会过 `plain()` 进
总览页的悬浮提示，是用户真读到的字 —— **用户读到的是一句话在说强度、
给出的数是薪资维的。**

而 `scoring.py` 模块 docstring 自己写着：薪资维之外那三个判断维
「不碰」。那两句恰好改在它承诺不碰的地方。

## 逐库实测有多大

活动用户 51 处「给 NN」：

    锚定在薪资维（该改）        7
    锚定在强度维（不能改）     11
    锚定在发展维（不能改）      9
    没点名维度                  24
      └ 其中所在分句在谈钱       14   （全是「按 16 薪估下沿 NN 万能过，
      │                                  这一维给 55 并挂『⚠ 先问几薪』」）
      └ 所在分句不谈钱           10   （说「专业能力」「业务域」）

**4/5 的匹配不该改。** 原实现 100% 改。

## 为什么第 2 类还要有旁证

04 的薪资维有一条「有月薪、但没写几薪」的 55 分规则，它的解释句
必然落在「没点名维度」那一类里 —— 一律不动等于薪资维改了而解释不改，
`writeback._basis_is_stale` 会永远报下去。谈钱信号（薪/年包/下沿/
上沿/几薪）不会出现在「技能 / 强度 / 发展」的语境里，是那一类里
唯一可靠的旁证。
"""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import scoring  # noqa: E402


class OnlyThePaySentenceMoves(unittest.TestCase):
    """这是事故的形状，逐条钉住。"""

    def test_the_strength_sentence_is_left_alone(self):
        got = scoring.rewrite_pay_said(
            "强度与公司性质这一维给 50，JD 未提及加班。", 55)
        self.assertIn("强度与公司性质这一维给 50", got)

    def test_the_growth_sentence_is_left_alone(self):
        got = scoring.rewrite_pay_said(
            "发展与风险这一维给 30，与 AI 产品主线无关。", 55)
        self.assertIn("发展与风险这一维给 30", got)

    def test_the_skill_sentence_is_left_alone(self):
        got = scoring.rewrite_pay_said("专业能力只能给 25。", 55)
        self.assertIn("专业能力只能给 25", got)

    def test_the_business_domain_sentence_is_left_alone(self):
        """实测 10 处「没点名维度又不谈钱」全是这一类。"""
        got = scoring.rewrite_pay_said(
            "业务域（家电集团的组织知识治理）也只给 35。", 55)
        self.assertIn("也只给 35", got)

    def test_only_the_pay_one_moves(self):
        """同段里三句各说各的 —— 只有薪资那句换数。"""
        text = ("强度与公司性质这一维给 50，JD 未提加班；"
                "薪资与职级这一维给 25，12 薪下沿不够；"
                "发展与风险这一维给 30，与主线无关。")
        got = scoring.rewrite_pay_said(text, 55)
        self.assertIn("强度与公司性质这一维给 50", got)
        self.assertIn("薪资与职级这一维给 55", got)
        self.assertIn("发展与风险这一维给 30", got)


class TheNoMonthsRuleStillGetsFixed(unittest.TestCase):
    """为什么第 2 类（没点名维度）不能一律不动。"""

    def test_the_unanchored_pay_sentence_is_still_rewritten(self):
        """04「有月薪但没写几薪」的 55 分规则，解释句就在这一类里。"""
        text = "按 16 薪估下沿 56 万能过，这一维给 55 并挂「⚠ 先问几薪」。"
        self.assertIn("这一维给 25", scoring.rewrite_pay_said(text, 25))


class TheBlankAndTheOddInputs(unittest.TestCase):
    def test_empty_basis_stays_empty(self):
        self.assertEqual(scoring.rewrite_pay_said("", 55), "")

    def test_no_match_means_no_change(self):
        text = "这条岗没有任何维度分，只有一句叙述。"
        self.assertEqual(scoring.rewrite_pay_said(text, 55), text)

    def test_a_missing_pay_score_is_not_written_into_the_prose(self):
        """薪资维是「信息缺失」时（None），一个数都不许塞进句子。"""
        text = "薪资与职级这一维给 25，年包按 12 薪估不够。"
        self.assertEqual(scoring.rewrite_pay_said(text, None), text)


class TheShippedCodeActuallyCallsIt(unittest.TestCase):
    """守卫盯着检测器，不盯调用点 —— 补上这一条。"""

    def test_score_py_no_longer_substitutes_globally(self):
        src = (ROOT / "tools" / "score.py").read_text(encoding="utf-8")
        self.assertNotIn("scoring.SAID.sub(", src,
                         "score.py 又开始全局替换「给 NN」了 —— 改用 rewrite_pay_said")
        self.assertIn("scoring.rewrite_pay_said(", src)

    def test_the_reason_is_written_next_to_the_code(self):
        """事故经过与实测数要留在原地，不是留在 commit message 里。"""
        src = (ROOT / "tools" / "scoring.py").read_text(encoding="utf-8")
        seg = src[src.index("def rewrite_pay_said"):]
        seg = seg[:seg.index("\ndef ")] if "\ndef " in seg else seg
        self.assertIn("2026-10-12", seg, "实测日期没留在原地")
        for w in ("强度", "发展", "技能"):
            self.assertIn(w, seg, f"事故形状里的「{w}这一维给 NN」没留在原地")


if __name__ == "__main__":
    unittest.main()