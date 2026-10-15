# -*- coding: utf-8 -*-
"""年限这道门要 FAIL，必须有一个数；平台写「不限」时一律不许 FAIL。

年限是七道硬门里杀伤最大的一道 —— 实测活动用户 2026-08-22，491 个岗死在它上面，
占全部硬门 FAIL 的 43%。而其中：

    42 个的 `workYears` 就是「经验不限」   ← 平台明写没有年限要求
    111 个的字段下限 ≤ 4 年              ← 他两个年限读数里小的那个是 3 年

**加起来 153 个、31% 是错杀的。** 根因是 `job-rank.md` 那张表只写了
「字段比正文严」怎么办（→ FLAG），**反过来那半边一个字没有** —— 于是评估
从正文的「资深」「多年经验」里读出一道门，而招聘方自己在发布表单里勾的是「不限」。

这个文件盯两样：规则里那半边还在，以及审计能把违反它的岗数出来。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import audit_pipeline as A  # noqa: E402
import _cli  # noqa: E402

RANK = (ROOT / "workflows" / "job-rank.md").read_text(encoding="utf-8")


SRC = (ROOT / "tools" / "audit_pipeline.py").read_text(encoding="utf-8")


class TheCumulativeNumberNeedsABatchNumber(unittest.TestCase):
    """「21 个」读起来像存量，而最近一批 21 个里错了 10 个。

    这是本仓库自己的判据（`batch_note` 上面那段）：全库累计数只会随产量涨，
    改好了也降不下来 —— 唯一能回答「规则生效了没有」的是「最近一批还犯不犯」。

    这条检查此前只报累计数。实测 2026-08-31 接上之后：

        2026-08-19   33 个中  1 个是误判
        2026-08-24    7 个中  7 个是误判
        2026-08-27   21 个中 10 个是误判   ← 最近一批

    全库那个 21 读起来像「历史遗留」，而**近一半的新判定还在犯**。
    两句话给读的人的动作完全不同。

    分组用职位库自己的 `rank_date`，不是文件时间（同一课这个仓库记过：mtime
    会被重新归档、批量改权限、同步工具推到今天）。
    """

    def _rows(self, day, n_all, n_wrong):
        """造一批「判了工作年限不满足」的岗：`n_wrong` 个平台下限他够。"""
        seen = {}
        for k in range(n_all):
            seen[f"u{k}"] = {
                "url": f"https://x.com/{k}", "title": f"岗{k}",
                "company": "c", "rank_date": day,
                "rank_verdict": "硬门 FAIL：工作年限",
                "workYears": "3年以上" if k < n_wrong else "10年以上",
            }
        # 年限读数写死，不去读活动用户的资料 —— 这条测的是「批次数印没印」，
        # 不是「那份资料里写的几年」。
        old = A._candidate_years
        A._candidate_years = lambda: (13, 3)
        try:
            return A.check_years_gate_vs_platform_field(seen, {})
        finally:
            A._candidate_years = old

    def test_the_message_carries_the_latest_batch(self):
        """**要算，还要真印出去。**

        隔壁那条同族守卫记着这一脚：只断言 `batch_note(` 出现过是空转 ——
        把拼报文那半句删掉，赋值那行还在，断言照样绿，而用户再也看不到那个数。
        所以这里**喂构造数据、读返回的那句话**，不看源码长什么样。"""
        rows = self._rows("2026-08-27", 10, 6)
        msg = " ".join(r[2] for r in rows)
        self.assertIn("最近一批（2026-08-27，10 份）里 6 份", msg,
                      "只报累计数 —— 改好了也降不下来，看不出规则灵没灵")

    def test_the_denominator_is_everyone_judged_by_that_gate(self):
        """分母是**那天判过这道门的全部**，不是「那天错了几个」。

        只喂错的那批进去，比例永远是 10/10，那个数就说不了任何事 ——
        这里 10 个里只有 6 个是误判，分母必须还是 10。"""
        rows = self._rows("2026-08-27", 10, 6)
        msg = " ".join(r[2] for r in rows)
        self.assertNotIn("10 份）里 10 份", msg,
                         "分母只喂了误判的那批 —— 比例恒为 100%")

    def test_too_small_a_batch_says_nothing(self):
        """批次太小时不给这个数（`batch_note` 的 `min_size`）——
        「2/2 都犯」读起来像个结论，统计上什么也说不了。"""
        rows = self._rows("2026-08-27", 3, 2)
        msg = " ".join(r[2] for r in rows)
        self.assertNotIn("最近一批", msg)


class TheRuleIsWrittenDown(unittest.TestCase):
    def test_no_number_no_gate(self):
        """「资深」「多年经验」不是门 —— 没有数字就不许 FAIL。"""
        self.assertRegex(RANK, r"没有数字就不是门|必须有一个数",
                         "job-rank 里没写「年限门要 FAIL 必须有一个数」")

    def test_the_platform_saying_unlimited_wins(self):
        self.assertRegex(RANK, r"`workYears`\s*写「不限」时一律不 FAIL|写「不限」时一律不 FAIL",
                         "没写明平台字段「不限」时不许 FAIL")

    def test_the_smaller_reading_decides(self):
        """两个年限读数里小的那个都够，就绝不 FAIL。"""
        self.assertIn("小的那个都够", RANK, "没写明按小的那个读数兜底")


class TheAuditCatchesIt(unittest.TestCase):
    @staticmethod
    def _run(rows, years_line="工作年限说明：总工作年限 13 年，方向约 3 年。"):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            prof = root / "users" / "张三" / "profile"
            prof.mkdir(parents=True)
            (prof / "candidate.md").write_text(years_line, encoding="utf-8")
            saved_root, saved_user = A.ROOT, list(A._USER)
            try:
                A.ROOT = root
                A._USER[:] = ["张三"]
                return A.check_years_gate_vs_platform_field(
                    {str(i): r for i, r in enumerate(rows)}, {})
            finally:
                A.ROOT, A._USER[:] = saved_root, saved_user

    FAIL = {"rank_verdict": "硬门 FAIL (工作年限)", "title": "某岗"}

    def test_unlimited_experience_is_an_error_not_a_warning(self):
        """平台说没有这道门却按它杀了岗 —— 这是**逻辑矛盾**，一个就算错。"""
        out = self._run([{**self.FAIL, "workYears": "经验不限"}])
        self.assertTrue(out, "一个都没报")
        self.assertEqual(out[0][0], "error", f"矛盾被降级成了提醒：{out[0]}")
        self.assertIn("经验不限", out[0][2])

    def test_a_job_he_clears_is_reported(self):
        """字段下限 3 年、他方向年限 3 年 —— 加 1 年容差够了，不该 FAIL。"""
        out = self._run([{**self.FAIL, "workYears": "3-5年"}])
        self.assertTrue(any("年限够" in t for _, t, _ in out), f"没报出来：{out}")

    def test_a_job_he_really_does_not_clear_is_left_alone(self):
        """要求 10 年以上：按方向年限不够、按总年限够 —— 要读 JD 才判得了。
        **这里不判，也不许计进那个数**，否则审计自己在制造假阳性。
        """
        out = self._run([{**self.FAIL, "workYears": "10年以上"}])
        self.assertEqual(out, [], f"把判不了的也报了：{out}")

    def test_a_passing_job_is_not_touched(self):
        """没判 FAIL 的岗不进这张表。"""
        self.assertEqual(self._run([{"rank_verdict": "值得投", "workYears": "经验不限"}]), [])

    def test_unreadable_years_says_it_did_not_check(self):
        """候选人年限读不出来时，第二档要说「没查」——不是默默当作没有。"""
        out = self._run([{**self.FAIL, "workYears": "3-5年"}], years_line="（没写年限）")
        self.assertTrue(any("没查" in t + m for _, t, m in out),
                        f"读不出年限却没说没查：{out}")

    def test_it_is_registered(self):
        """写了不挂进 CHECKS 就永远不会跑。"""
        self.assertTrue(any(fn is A.check_years_gate_vs_platform_field
                            or getattr(fn, "__name__", "") ==
                            "check_years_gate_vs_platform_field"
                            for _, fn in A.CHECKS), "新检查没进 CHECKS")


class JudgingWithNoEvidenceIsCaught(unittest.TestCase):
    """判不了就别判死 —— 正文没抓到、卡片字段也空，还是把岗杀了。

    规则在 `job-rank.md`：「没抓到正文 → FLAG，判不了就别判死」+「只在**卡片或
    JD 的字段**够判时才判」。两句合起来 = 两处都没依据时不许 FAIL。
    实测 2026-08-22：1094 个硬门 FAIL 里 18 个是这样（年限 14、学历 4）。
    """

    FAIL = {"rank_verdict": "硬门 FAIL (工作年限)", "title": "某岗", "url": "u1"}

    def test_no_body_no_field_is_an_error(self):
        out = A.check_gate_fail_without_evidence({"a": self.FAIL}, {})
        self.assertTrue(out and out[0][0] == "error", f"没报出来：{out}")

    def test_the_card_field_alone_is_enough_evidence(self):
        """`workYears` 是卡片字段，够判 —— 有它就不算「判不了」。"""
        self.assertEqual(A.check_gate_fail_without_evidence(
            {"a": {**self.FAIL, "workYears": "10年以上"}}, {}), [])

    def test_a_real_jd_body_is_enough_evidence(self):
        self.assertEqual(A.check_gate_fail_without_evidence(
            {"a": self.FAIL}, {"u1": {"description": "岗" * 200}}), [])

    def test_gates_judged_from_the_title_are_out_of_scope(self):
        """明确排除靠岗位名就判得了，岗位名也是卡片字段 —— 算进来全是假阳性。"""
        self.assertEqual(A.check_gate_fail_without_evidence(
            {"a": {**self.FAIL, "rank_verdict": "硬门 FAIL (候选人明确排除)"}}, {}), [])


class BothYearTiersGetRepaired(unittest.TestCase):
    """报两档、只修一档，等于把 111 个可证明错判的岗留在不投里。

    `check_years_gate_vs_platform_field` 报两档：平台写「经验不限」的（error），
    和平台下限低到「他两个年限读数里小的那个 + 1 年容差」都够的（warn）。
    **分档是报告时的信心分级**（前者不需要读 `candidate.md`，后者需要），
    **不是「该不该修」的分级** —— 后者的判据一样硬，那条检查自己写着
    「小的那个都够，就没有任何一种读法能判 FAIL」。

    > 顺带记一个静默失效：`_USER` 原本只在 `run()` 里设，而 `--requeue-unfounded`
    > 不经过 `run` —— 于是 `_candidate_years()` 读不到用户、第二档整个跳过，
    > 命令还打印「没有这一类的岗，不用动」，**看着像已经修干净了**。
    """

    def _requeue_covers(self, entry, years_line="工作年限说明：总工作年限 13 年，方向约 3 年。"):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            u = root / "users" / "张三"
            (u / "job_scraper").mkdir(parents=True)
            (u / "profile").mkdir(parents=True)
            (u / "profile" / "candidate.md").write_text(years_line, encoding="utf-8")
            (u / "job_scraper" / "seen_jobs.json").write_text(
                json.dumps({"seen": {"k": entry}}), encoding="utf-8")
            saved = A.ROOT, list(A._USER)
            try:
                A.ROOT = root
                A._USER[:] = []          # 模拟不经过 run() 的那条入口
                return A.requeue_unfounded_gate_fails("张三", apply=False)
            finally:
                A.ROOT, A._USER[:] = saved[0], saved[1]

    FAIL = {"rank_verdict": "硬门 FAIL (工作年限)", "title": "某岗", "url": "u1"}

    def test_the_unlimited_tier_is_covered(self):
        self.assertTrue(self._requeue_covers({**self.FAIL, "workYears": "经验不限"}))

    def test_the_low_floor_tier_is_covered_too(self):
        """这一档原来漏了 —— 111 个岗。"""
        self.assertTrue(self._requeue_covers({**self.FAIL, "workYears": "3-5年"}),
                        "平台下限 3 年、他方向年限 3 年，却没被放回队列")

    def test_a_genuinely_high_bar_is_left_alone(self):
        """要求 10 年以上：按哪个口径算要读 JD —— 不判，也不许顺手放回。"""
        self.assertFalse(self._requeue_covers({**self.FAIL, "workYears": "10年以上"}))

    def test_a_deep_evaluation_is_never_thrown_away(self):
        """这条修复治的是**粗筛**按卡片字段判错的那批。

        深评读了职位正文，比粗筛强 —— 抹掉等于丢掉真做过的工作。而且盘上还留着
        一份 `evaluation.md`，导出侧照它出判词、与 `status` 无关：放回队列的结果是
        `status` 是 `new`、页面上却照样有这个岗，流水线计数对不上
        （实测 `test_pipeline_counts` 抓到 3 个）。
        """
        self.assertFalse(
            self._requeue_covers({**self.FAIL, "workYears": "经验不限",
                                  "evaluated": True}),
            "把一份深评结论当成粗筛错判抹掉了")

    def test_it_skips_the_tier_when_years_are_unreadable(self):
        """读不出他的年限就整档跳过 —— 不猜一个 floor 出来。"""
        self.assertFalse(
            self._requeue_covers({**self.FAIL, "workYears": "3-5年"},
                                 years_line="（没写年限）"))


if __name__ == "__main__":
    unittest.main()
