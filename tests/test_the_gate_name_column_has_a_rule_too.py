# -*- coding: utf-8 -*-
"""硬门表的**判定格**那一列有规矩管着，**门名**那一列一条都没有。

`04-job-evaluation.md` 早就为判定格写了一整节：

> ### 判定格只许用这几种写法 —— 自造的词面板认不出

同一张表的门名那一列，规则一条也没有。而它同样是被机器读的：
`_cli.gate_of()` 认不出的门名返回空串，这一行就对**所有按门名做的检查**
同时隐形 —— 漏判统计（`gatesNotJudged`）、面板的「哪道门挡得最多」
（`gate_fail_tally`）、审计的逐门核对。

实测 2026-08-23：**19 个岗**判了硬门却用了七道之外的名字 ——
技术栈 7、地点 4、英语 4、语言 2、行业经验 1、专业 1。

## 规则原来只长在报错文案里

判据本来是有的，但它**只**写在 `audit_pipeline.py` 那句 warn 的 f-string 里：

> 地点、英语这类若资料里写了，应写成「候选人明确排除（跨城搬迁）」；
> 技术栈、行业经验本来就是要打分的维度，不该当门用。

而写评估的人读的是 `04`。**规则长在检查者身上、不长在写的人读的地方** ——
于是他照自己的理解起名，审计再逐条抓，来回一整轮。

## 地点那一处是自相矛盾，不只是缺规则

第 4.1 节的标题就是「**地点 —— 是 Pass/Fail 的门**」，正文还写着「当门合理」。
照着读，写一行叫「地点」的门是**框架自己教的**。而硬门表里没有这道门、
`_cli.GATES` 也不认。缺的是那一句映射：**4.1 说的是怎么判，不是行叫什么名。**

没有把它升成第八道门：「七道」这个数散在 24 个文件里，而
`候选人明确排除（跨城搬迁）` 本来就是它的正确归属 —— 活动用户的资料里
原话就是「好岗位可以为通勤让步。**跨城市搬迁才是硬门**」，它确实是他自己划的。
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402

EVAL = (ROOT / "workflows" / "reference"
        / "04-job-evaluation.md").read_text(encoding="utf-8")
AUDIT = (ROOT / "tools" / "audit_pipeline.py").read_text(encoding="utf-8")


def rule() -> str:
    """新加的那一块（门名规则），到硬门表为止。

    **先剥掉行首的 `> `。** 整块是 markdown 引用，句子跨行时拉平会在中间
    夹进一个 `>`（`→ 归 > **「候选人明确排除」**`）—— 第一版就栽在这儿。
    """
    i = EVAL.index("门名也只许用下表这七个")
    seg = EVAL[i:EVAL.index("| 门槛 | FAIL 的判据 | 注意 |", i)]
    return re.sub(r"^\s*>\s?", "", seg, flags=re.M)


class TheGateNameColumnIsGoverned(unittest.TestCase):
    def test_the_rule_exists_in_the_framework(self):
        self.assertIn("门名也只许用下表这七个", EVAL,
                      "门名那一列仍然没有规矩 —— 规则还只在审计的报错文案里")

    def test_it_sits_with_the_table_it_governs(self):
        """规则要挨着它管的东西。放到文末等于没写。"""
        self.assertLess(EVAL.index("门名也只许用下表这七个"),
                        EVAL.index("| 门槛 | FAIL 的判据 | 注意 |"))

    def test_it_says_what_goes_wrong(self):
        """「不许自造」不给后果，就会被当成措辞洁癖。"""
        seg = " ".join(rule().split())
        self.assertRegex(seg, r"`_cli\.gate_of\(\)` 认不出就返回空串")
        self.assertRegex(seg, r"同时隐形")

    def test_it_carries_the_measured_number(self):
        seg = " ".join(rule().split())
        self.assertIn("七道之外的名字", seg)

    def test_it_gives_both_landing_rules(self):
        """两类去处不同：一类归明确排除，一类根本不是门。少一类就白写。"""
        seg = " ".join(rule().split())
        self.assertRegex(seg, r"归 \*\*「候选人明确排除」\*\*")
        self.assertRegex(seg, r"本来就是第 1 维要打的分")

    def test_the_parenthesis_is_required(self):
        """光写「明确排除」四个字，那一档就还是个黑盒。"""
        seg = " ".join(rule().split())
        self.assertIn("括号是必须的", seg)
        self.assertIn("只写了「明确排除」四个字", seg)

    def test_it_leans_on_the_veto_criterion(self):
        """「技术栈不该当门」不是口味问题，它违反本文档自己的判据。"""
        self.assertIn("只有当一个条件既是二值的、又有确凿证据时，才配当一票否决",
                      "".join(rule().split()).replace("*", ""))

    def test_it_keeps_the_certificate_exception(self):
        """JD 写「必须持证」时确实是门 —— 一刀切会把真门也扫掉。"""
        seg = " ".join(rule().split())
        self.assertIn("执业资格/证照/职称", seg)
        self.assertRegex(seg, r"必须持有 / 无 X 不予考虑")

    def test_it_names_both_places_to_change(self):
        """只改一处正是这 19 个岗现在的样子。"""
        seg = " ".join(rule().split())
        self.assertIn("`tools/_cli.py` 的 `GATES`", seg)
        self.assertRegex(seg, r"只改一处的后果")

    def test_the_sibling_rule_it_pairs_with_survives(self):
        """它是「判定格那一节」的姊妹条。那一节没了，这条就没有参照。"""
        self.assertIn("### 判定格只许用这几种写法 —— 自造的词面板认不出", EVAL)

    def test_the_row_presence_rule_survives(self):
        """「每道都要有那一行」管的是有没有，这条管叫什么。两条都要在。"""
        self.assertIn("七道门每道都要有那一行——判不了写「未知」，不是不写", EVAL)


class TheLocationSectionNoLongerContradicts(unittest.TestCase):
    def _s41(self) -> str:
        i = EVAL.index("#### 4.1 地点 —— 是 Pass/Fail 的门")
        return EVAL[i:EVAL.index("#### 4.2", i)]

    def test_it_says_there_is_no_gate_called_location(self):
        self.assertIn("硬门表里没有一道叫「地点」的门", self._s41())

    def test_it_names_the_row_the_verdict_lands_in(self):
        self.assertIn("`候选人明确排除（跨城搬迁）`", self._s41())

    def test_it_separates_judging_from_naming(self):
        """这才是原来缺的那一句 —— 4.1 说的是怎么判，不是行叫什么名。"""
        self.assertRegex(" ".join(self._s41().split()),
                         r"这一节说的是\*\*怎么判\*\*")

    def test_the_three_outcomes_survive(self):
        """搬迁 FAIL / 远程 PASS / 出差外派 FLAG —— 判定本身一条都不能少。"""
        seg = self._s41()
        for w in ("跨城市搬迁", "远程 / 混合办公", "频繁出差 / 外派"):
            with self.subTest(w=w):
                self.assertIn(w, seg)

    def test_it_is_still_called_a_gate_here(self):
        """没有把它降级 —— 它确实是二值的、确实该当门，只是行名归明确排除。"""
        self.assertIn("是二值问题，当门合理", self._s41())


class TheSevenAreStillSeven(unittest.TestCase):
    """本轮**没有**新增第八道门。真加了的话上面几条的理由全要重写。"""

    def test_cli_still_knows_exactly_seven(self):
        self.assertEqual(len(_cli.GATES), 7, f"门数变了：{list(_cli.GATES)}")

    def test_location_is_not_one_of_them(self):
        self.assertEqual(_cli.gate_of("地点"), "",
                         "「地点」成了正规门名 —— 那 24 处「七道」要一起改")

    def test_the_exclusion_gate_absorbs_it(self):
        """归位的前提：带括号的写法真的能被认出来。"""
        self.assertEqual(_cli.gate_of("候选人明确排除（跨城搬迁）"),
                         "候选人明确排除")

    def test_every_canonical_name_resolves_to_itself(self):
        for name in _cli.GATES:
            with self.subTest(gate=name):
                self.assertEqual(_cli.gate_of(name), name)


class TheAuditPointsAtTheFrameworkNow(unittest.TestCase):
    """规则搬了家，检查者要指过去，不能两边各留一份自己长。"""

    def _msg(self) -> str:
        """**按那条 return 的结尾切，不要取固定长度。**
        取 1400 字会溢进后面的函数，而 `/job-rank --all` 在那儿也出现 ——
        把这一处删掉，断言照样绿（变异实测）。"""
        i = AUDIT.index("硬性条件：门名没按七道正规名写")
        end = AUDIT.index('（两处都要）。")]', i)
        return AUDIT[i:end]

    def test_it_cites_the_framework(self):
        self.assertIn("判据见 04-job-evaluation.md 第一步"
                      "「门名也只许用下表这七个」", self._msg())

    def test_it_still_reports_the_instances(self):
        """指过去不等于不报 —— 它仍然要说清是哪几个岗。"""
        seg = self._msg()
        self.assertIn("门名却不是七道里的任何一道", seg)
        self.assertIn("/job-rank --all", seg)

    def test_the_reason_for_moving_it_is_recorded(self):
        seg = " ".join(self._msg().split())
        self.assertRegex(seg, r"规则要长在写的人读的地方")

    def test_the_check_still_uses_gate_of(self):
        """整条论证建立在「认不出就返回空串」上。换了判法这条要重写。"""
        i = AUDIT.index("def check_gate_is_one_of_the_seven")
        self.assertIn("gate_of", AUDIT[i:i + 1500])


if __name__ == "__main__":
    unittest.main()
