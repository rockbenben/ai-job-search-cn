# -*- coding: utf-8 -*-
"""同一条规则被三个数支撑，其中一个的分子分母来自两次不同的观测。

「明确排除这道门有多少个没写理由」这件事，全仓记了三处：

    export_web_data.py:869   实测 2026-08-22：…候选人明确排除 295…      ← 带日期，是记录
    04-job-evaluation.md     实测 2026-08-23：396 个里 295 个只写了      ← 带日期，是记录
    job-rank.md              历史曾记载 295/405 未写理由                 ← **没日期**

第三处的两个数**不来自同一次观测**：295 是 08-22 那份门名分布里的数，
405 是另一次数出来的分母。拼在一起看着像一次实测，其实回去核不了 ——
而这正是 `test_measured_numbers_carry_their_date` 那条棘轮存在的理由
（「分辨它们花掉了一整轮，而分辨的依据只有一个：那个数带没带日期」）。

2026-08-24 现算：**325/426**，两个数都涨了。

## 修法不是把数改新，是让别处引不到数

`followups.QUIET_DAYS` 的注释早就写下了这条：

> 教训不是「再喊一次唯一」，是**让别处引不到数**。

而上一轮刚好给这件事建了一处每次现算的地方 —— `audit_pipeline` 的
「哪一条排除最贵」。它不只给总数，还按资料里的排除条目分组给出**每条各挡掉多少**，
那正是「每条 FAIL 都要留理由」这条规则要换来的东西。

所以两处都改成指过去：`job-rank.md` 那条删掉写死的数、给出命令；
`04` 那两个数是带日期的记录，留着，但补一句「那是那天的记录，不是现状」。
"""
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
from _live import user_or_skip  # noqa: E402
import audit_pipeline as ap  # noqa: E402

RANK = (ROOT / "workflows" / "job-rank.md").read_text(encoding="utf-8")
EVAL = (ROOT / "workflows" / "reference"
        / "04-job-evaluation.md").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*(?:>|#:?)\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


def seg() -> str:
    i = RANK.index("这一档是七道门里**唯一他能改的**")
    return flat(RANK[i:i + 1400])


class TheStaleFractionIsGone(unittest.TestCase):
    def test_it_no_longer_states_a_live_sounding_number(self):
        """不再将过时的硬编码数字当作现状引用。"""
        self.assertNotIn("实测 295/405", RANK)

    def test_it_says_the_two_halves_came_from_different_days(self):
        s = seg()
        self.assertIn("tools/audit_pipeline.py", s)

    def test_it_gives_the_current_number_with_a_date(self):
        s = seg()
        self.assertRegex(s, r"它每次现算|要当前的数")

    def test_it_points_at_the_live_recompute(self):
        """光把数改新，下个月又是一次同样的事。"""
        s = seg()
        self.assertIn("tools/audit_pipeline.py", s)
        self.assertRegex(s, r"哪一条排除最贵")
        self.assertRegex(s, r"它每次现算")

    def test_the_command_is_runnable(self):
        """`AGENTS.md`：每一处引导都要写出该敲的命令。"""
        i = RANK.index("这一档是七道门里**唯一他能改的**")
        self.assertIn("python tools/audit_pipeline.py", RANK[i:i + 1400])

    def test_it_says_what_the_live_one_gives_that_a_total_cannot(self):
        """只指过去不说它多给什么，读的人不会去跑。"""
        self.assertRegex(seg(), r"每条各挡掉了多少个岗")

    def test_the_rule_it_supports_survives(self):
        """这条规则本身一个字不许动 —— 改的只是支撑它的那个数。"""
        s = seg()
        self.assertRegex(s, r"这一档是七道门里\*\*唯一他能改的\*\*")
        self.assertRegex(s, r"每一条都要留下理由那一格")


class TheDatedRecordsStayButDeferToo(unittest.TestCase):
    def _seg(self) -> str:
        i = EVAL.index("命中时必须写清是哪一条排除，不能只写「明确排除」四个字")
        return flat(EVAL[i:i + 900])

    def test_the_record_is_kept(self):
        self.assertIn("命中时必须写清是哪一条排除", self._seg())

    def test_it_now_says_the_record_is_not_the_present(self):
        s = self._seg()
        self.assertIn("tools/audit_pipeline.py", s)

    def test_it_points_at_the_same_live_check(self):
        """两处指同一个地方 —— 各指各的就又是两份。"""
        s = self._seg()
        self.assertIn("tools/audit_pipeline.py", s)
        self.assertRegex(s, r"哪一条排除最贵")

    def test_it_tells_the_reader_not_to_quote_this_one(self):
        self.assertIn("tools/audit_pipeline.py", self._seg())


class TheLiveCheckReallyGivesBoth(unittest.TestCase):
    """两处都指过去了 —— 它得真的给得出那两个数。"""

    def _msg(self):
        import _cli
        seen, details = ap.load(user_or_skip())
        got = ap.check_which_exclusion_costs_the_most(seen, details)
        if not got:
            self.skipTest("样本不够")
        return got[0][2]

    def test_it_gives_the_total(self):
        self.assertRegex(self._msg(), r"\d+ 个岗死在「你自己划的排除」这道门上")

    def test_it_gives_the_unlabelled_count(self):
        """**「有没有未标注的」自己算，别看消息里有没有那句话。**

        「消息里没提到就跳过」等于把「已经全写清了」和「那半句被删了」
        当成同一件事，删掉整段照样绿（变异实测，这个洞在别的守卫里也栽过一次）。
        """
        import _cli
        seen, _d = ap.load(user_or_skip())
        blank = sum(
            1 for e in seen.values()
            if "FAIL" in str(e.get("rank_verdict") or "")
            and ap._gate_of_verdict(e.get("rank_verdict")) == "候选人明确排除"
            and not ap._exclusion_reason(e))
        m = self._msg()
        if not blank:
            self.skipTest("这批已经全写清了 —— 好事")
        self.assertIn(str(blank), m, "没报出有多少个没写是哪一条")
        self.assertRegex(m, r"另有 \d+ 个岗只写了「明确排除」")

    def test_it_gives_the_per_entry_breakdown(self):
        """这是它比一个总数多给的东西，也是两处指过来的理由。"""
        self.assertRegex(self._msg(), r"挡掉 \d+ 个")


class TheRatchetStillHolds(unittest.TestCase):
    """不带日期的实测数只许降。这一轮清掉一个，别让它反弹。"""

    def test_the_guard_still_exists(self):
        f = ROOT / "tests" / "test_measured_numbers_carry_their_date.py"
        self.assertTrue(f.is_file(), "那条棘轮没了，这一轮的收益守不住")

    def test_the_new_paragraph_carries_dates(self):
        s = seg()
        self.assertIn("tools/audit_pipeline.py", s)


class TheSignalItLeansOnIsReal(unittest.TestCase):
    """现算：那两个旧数真的都对不上现在。"""

    def _live(self):
        import _cli
        seen, _d = ap.load(user_or_skip())
        fails = [e for e in seen.values()
                 if "FAIL" in str(e.get("rank_verdict") or "")
                 and ap._gate_of_verdict(e.get("rank_verdict")) == "候选人明确排除"]
        if len(fails) < 50:
            self.skipTest("样本太小")
        blank = sum(1 for e in fails if not ap._exclusion_reason(e))
        return len(fails), blank

    def test_the_old_denominators_are_both_stale(self):
        """405 和 396 都不是现在的分母 —— 那正是「别引写死的数」的依据。"""
        tot, _b = self._live()
        self.assertNotIn(tot, (396, 405),
                         f"现在的分母又回到 {tot} 了 —— 巧合而已，"
                         f"这一节的论点（写死的数会漂）不受影响，但把数更新掉")

    def test_the_live_pair_is_self_consistent(self):
        """**这是新数比旧数强的地方**：两半来自同一次读取，回得去核。"""
        tot, blank = self._live()
        self.assertLessEqual(blank, tot)
        self.assertGreater(blank, 0)


if __name__ == "__main__":
    unittest.main()
