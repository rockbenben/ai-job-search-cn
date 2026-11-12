# -*- coding: utf-8 -*-
"""总分带着一个四维之外的调整项，而它只有 6% 记成了字段。

资料里的裁定可以在四维之外直接改综合分。本活动用户 `candidate.md` 的专业清单
那条写着「综合分 −5（**记为「专业减分」**）」——**约定本来就有**。

实测（2026-08-26）：四维齐全的 661 个岗里，总分对不上加权和的 129 个。
记成字段的 **8** 个、只写在散文依据里的 67 个、一个字没提的 54 个
（后者 46 个正好落在 −5/−4.x 这个签名上，就是同一条专业减分）。

## 没照做不是执行者马虎

约定写在**用户资料**里，而执行者照抄的是 `job-rank.md` 那份 `rank_breakdown`
schema —— 那里原来没有这个字段。**同一个形状本会话撞过第二次了**：
`--annual-floor` 的取值规则写在一处、可复制的例子写在另一处，两处不是一个数，
执行者复制的是例子。规则与被复制的样板分家，样板赢。

## 代价

**没有任何工具能查出哪些岗带了减分。** 这条裁定 2026-08-14 改过一次
（上午按硬门、同日本人放宽为减分），当时全库翻案 11 个。下次再改还是只能
grep 散文 —— 而散文写法实测至少三种：「专业减分 −5」「综合分已减 5」
「专业清单不含 X，减 5」。

## 这里钉两件事

复算必须把 04 允许的每种算法都试过（**尤其是薪资缺失时的权重分摊** ——
少了它，那一类会被当成算错，而它是文档里明写的），以及 `调整` 真的被算进去。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import audit_pipeline as ap  # noqa: E402

SRC = (ROOT / "tools" / "audit_pipeline.py").read_text(encoding="utf-8")
RANK = (ROOT / "workflows" / "job-rank.md").read_text(encoding="utf-8")
FRAMEWORK = (ROOT / "workflows" / "reference"
             / "04-job-evaluation.md").read_text(encoding="utf-8")

#: 加权和**正好是整数** 64.0 = 50×.30 + 60×.25 + 70×.20 + 80×.25。
#: 挑整数不是讲究：第一版用了一组和为 62.05 的数，却在注释里写 62.0，
#: 于是「差 0.5 仍算对上」那条用例自己就差了 0.55 —— 测试红了，代码是对的。
DIMS = {"技能与经验": 50, "薪资与职级": 60, "强度与公司性质": 70, "发展与风险": 80}


def _job(score, dims=None, day="2026-08-26", **extra):
    b = dict(dims or DIMS)
    b.update(extra)
    return {"k": {"title": "蓝湾智投科技", "rank_score": score,
                  "rank_date": day, "rank_breakdown": b}}


class ASumThatAddsUpIsLeftAlone(unittest.TestCase):
    def test_the_plain_weighted_sum(self):
        self.assertEqual(ap.check_score_reconciles(_job(64), {}), [])

    def test_rounding_within_half_a_point(self):
        for s in (63.5, 64, 64.5):
            with self.subTest(score=s):
                self.assertEqual(ap.check_score_reconciles(_job(s), {}), [])

    def test_the_salary_weight_is_redistributed_when_it_is_unknown(self):
        """04「权重」那一节的括注：薪资维为信息缺失时，把它的权重按比例
        分摊到其余三维。少了这一支，这一类会被当成算错 —— 而它是明写的。"""
        dims = {**DIMS, "薪资与职级": 0}
        want = (50 * .30 + 70 * .20 + 80 * .25) / .75
        self.assertEqual(ap.check_score_reconciles(_job(round(want), dims), {}), [])

    def test_a_recorded_adjustment_is_counted(self):
        """带了 `调整` 就该对上 —— 这正是这条检查要换来的东西。"""
        self.assertEqual(
            ap.check_score_reconciles(_job(59, 调整={"专业减分": -5}), {}), [])

    def test_several_adjustments_add_up(self):
        self.assertEqual(
            ap.check_score_reconciles(
                _job(61, 调整={"专业减分": -5, "内推加分": 2}), {}), [])


class ASumThatDoesNotIsReported(unittest.TestCase):
    def test_an_unexplained_gap_fires(self):
        got = ap.check_score_reconciles(_job(57), {})
        self.assertTrue(got, "写 57、四维算 64，差 7 分却一个字没交代")
        self.assertIn("总分", got[0][1])

    def test_prose_alone_is_not_enough(self):
        """**只写在依据里不算数** —— 那正是 67 个岗的现状，也正是问题本身。"""
        got = ap.check_score_reconciles(
            _job(57, 依据="专业清单不含历史学，综合分已减 5"), {})
        self.assertTrue(got, "散文里交代过就放行的话，这条检查什么也换不来")

    def test_it_says_what_to_write_and_where(self):
        msg = ap.check_score_reconciles(_job(57), {})[0][2]
        self.assertIn("调整", msg)
        self.assertIn("job-rank.md", msg, "没指出那份 schema 在哪")
        self.assertIn("/job-apply", msg, "没给该敲的那条命令")

    def test_it_reports_the_recent_batch_not_just_the_backlog(self):
        """一条永远红着的自检会被当噪音略过。存量之外要给趋势。"""
        jobs = {}
        jobs.update({f"old{i}": _job(57, day="2026-01-01")["k"] for i in range(4)})
        jobs.update({f"new{i}": _job(57, day="2026-08-26")["k"] for i in range(2)})
        msg = ap.check_score_reconciles(jobs, {})[0][2]
        self.assertIn("最近一批", msg)
        self.assertIn("2026-08-26", msg)
        self.assertIn("2 个", msg, "最近一批数错了")


class ItDoesNotGuess(unittest.TestCase):
    def test_a_missing_dimension_is_skipped(self):
        dims = {k: v for k, v in DIMS.items() if k != "发展与风险"}
        self.assertEqual(ap.check_score_reconciles(_job(64, dims), {}), [],
                         "四维不齐就复算不了 —— 不许把缺的当 0")

    def test_a_missing_score_is_skipped(self):
        j = {"k": {"title": "x", "rank_breakdown": dict(DIMS)}}
        self.assertEqual(ap.check_score_reconciles(j, {}), [])

    def test_junk_does_not_crash_it(self):
        j = {"k": {"title": "x", "rank_score": "很高",
                   "rank_breakdown": {**DIMS, "调整": "减了点"}}}
        self.assertEqual(ap.check_score_reconciles(j, {}), [])

    def test_a_non_numeric_adjustment_is_ignored_not_crashed(self):
        got = ap.check_score_reconciles(_job(57, 调整={"专业减分": "五分"}), {})
        self.assertTrue(got, "调整里是句话不是数，等于没记 —— 该照报")


class TheWeightsMatchTheFramework(unittest.TestCase):
    def test_they_are_30_25_20_25(self):
        self.assertEqual(ap._DIM_WEIGHTS,
                         {"技能与经验": .30, "薪资与职级": .25,
                          "强度与公司性质": .20, "发展与风险": .25})

    def test_they_sum_to_one(self):
        self.assertAlmostEqual(sum(ap._DIM_WEIGHTS.values()), 1.0)

    def test_the_framework_still_says_four_not_five(self):
        """地点是 Pass/Fail，不计权重。它一旦进了权重表，每个分都会错。"""
        self.assertIn("所以是四维，不是五维", FRAMEWORK)

    def test_the_redistribution_rule_is_still_in_the_framework(self):
        self.assertIn("把它的权重按比例分摊到其余三维", FRAMEWORK)


class TheSchemaNowCarriesTheField(unittest.TestCase):
    """约定原来只写在用户资料里，而执行者照抄的是这份 schema。"""

    def test_the_schema_shows_the_adjustment_line(self):
        i = RANK.index('"rank_breakdown": {')
        self.assertIn("调整", RANK[i:i + 500], "schema 里还是没有这个字段")

    def test_the_rule_says_prose_is_not_enough(self):
        self.assertIn("别只写在依据里", RANK)

    def test_the_incident_is_on_record(self):
        self.assertIn("调整", RANK)


class ItIsRegistered(unittest.TestCase):
    def test_the_check_is_in_the_list(self):
        uses = [ln for ln in SRC.splitlines()
                if "check_score_reconciles" in ln
                and not ln.lstrip().startswith("def ")]
        self.assertTrue(uses, "写了检查却没挂进清单")
        self.assertTrue(any("(" in ln and "," in ln for ln in uses), uses)


if __name__ == "__main__":
    unittest.main()
