# -*- coding: utf-8 -*-
"""「没写几薪」被当成了「钱不够」——12 个岗，12 个全给了框架明令不许给的那个分。

国内一半的岗只写月薪、不写几薪。实测活动用户 2026-08-24：
**2637 个岗里 1308 个没有 `salaryMonths`**（13薪 225 · 14薪 255 · 15薪 464 ·
16薪 250 · 其余零散）。中位是 15 薪 —— 也就是说按 12 薪折出来的年包，
大概率比真实数低两三成。

`04-job-evaluation.md`「有月薪、但没写「几薪」」那一节对这种情况写得极死：

> **但打分不许用假设值把岗埋掉**：12 薪折算值已 ≥ 底线 → 正常取档；
> 12 薪折算值低于底线、而按 16 薪估**能**过底线 → 这一维给 **55** 并打强制
> 「⚠ 先问几薪」标志，**不给 25**；16 薪都过不了底线的才给 25。

它甚至配了一整节讲为什么（「披露越多，分不能越低」），还带一个实测反例。
**而没有任何东西在验它。**

## 实测（活动用户 2026-08-24）

    落在这一档的深评            12 个
    薪资维给了 25 的            12 个（**全部**）
    挂了「⚠ 先问几薪」标志的     0 个

薪资维 25 → 55 是 30 分 × 25% 权重 = 综合分 **7.5 分**。逐个算下来：
2 个从「可以考虑」翻到「值得投」，另有 2 个正好压在 60 分线上。

## 根因不在执行者，在派活的那份枚举

`job-rank.md` Step 2 派批量评分代理时，精简口径里原来只有
**「期望薪资区间与底线」**——一条裸底线。代理拿着它按 12 薪折出 36 万、
对着他自己那条底线给 25 分，**它是对的，因为它没被告知还有另一档**。

这与同一天修的「年限门」是**同一个形状**：规则写在 `04` 里，而派活的那份枚举
只带过去一半，于是那一半规则在批量打分里从来没生效过。
"""
import pathlib
import re
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import audit_pipeline as ap  # noqa: E402
import prescreen  # noqa: E402
import _cli  # noqa: E402

AUDIT = (ROOT / "tools" / "audit_pipeline.py").read_text(encoding="utf-8")
RANK = (ROOT / "workflows" / "job-rank.md").read_text(encoding="utf-8")
EVAL = (ROOT / "workflows" / "reference"
        / "04-job-evaluation.md").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*(?:>|#:?)\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


class TheRuleItGuardsIsStillWritten(unittest.TestCase):
    def test_the_framework_section_exists(self):
        self.assertIn("#### 有月薪、但没写「几薪」——按 12 薪算，并且必须说出来", EVAL)

    def test_it_forbids_the_low_score(self):
        i = EVAL.index('#### 有月薪、但没写「几薪」')
        seg = flat(EVAL[i:EVAL.index("只有真的「薪资面议」", i)])
        self.assertRegex(seg, r"这一维给\s*\*\*55\*\*")
        self.assertRegex(seg, r"\*\*不给 25\*\*")
        self.assertRegex(seg, r"⚠ 先问几薪")

    def test_the_two_scores_match_the_framework(self):
        """审计抄的那两个数要和框架一致 —— 抄错就成了另一条规则。"""
        self.assertEqual((ap._MONTHS_MID, ap._MONTHS_LOW), (55, 25))

    def test_every_consumer_reads_the_same_number(self):
        """「按最乐观的薪数能不能过底线」三处在算，三处要是同一个数。

        `prescreen` 拿它淘汰、`scoring` 拿它给薪资维分档、`audit_pipeline`
        拿它报「没标薪数的岗被埋掉」。
        """
        self.assertEqual(
            {ap._OPTIMISTIC_MONTHS, prescreen.OPTIMISTIC_MONTHS,
             _cli.OPTIMISTIC_MONTHS},
            {16})

    def test_nobody_writes_the_number_a_second_time(self):
        """三处都得是别名，不许再出现第二个手写的 16。

        原来这条钉的是「抄件要指回正本」—— 而三处各写一份 16，指得再准
        也还是三份会飘的定义。2026-08-30 收成一处（正本在 `_cli`），
        判据跟着从「指对了没有」换成「还有没有第二份」。
        """
        # 只看**赋值行**（`>=` 那种用法也含 `=`，第一版把它们一起算了进来）。
        assign = re.compile(r"^\s*_?OPTIMISTIC_MONTHS\s*=[^=]")
        for mod in ("audit_pipeline.py", "prescreen.py", "scoring.py"):
            src = (ROOT / "tools" / mod).read_text(encoding="utf-8")
            for line in src.splitlines():
                if assign.match(line):
                    with self.subTest(mod=mod):
                        self.assertIn("_cli.OPTIMISTIC_MONTHS", line,
                                      f"{mod} 又自己写了一个数：{line.strip()}")


class TheBatchScorerIsToldAboutIt(unittest.TestCase):
    """根因这一半：`04` 写了，而派活的枚举只带过去一条裸底线。"""

    def test_the_enumeration_carries_the_rule(self):
        i = RANK.index("期望薪资区间与底线（")
        seg = flat(RANK[i:i + 600])
        self.assertIn("55", seg)
        self.assertIn("先问几薪", seg)
        self.assertRegex(seg, r"不给 25|\*\*不给\*\*\s*25")

    def test_it_says_why_the_agent_gets_it_wrong_otherwise(self):
        """只贴一条规则不够 —— 不说清「代理为什么会判错」，下一个人会把它删掉。"""
        i = RANK.index("期望薪资区间与底线（")
        seg = flat(RANK[i:i + 600])
        self.assertRegex(seg, r"一半的岗只写月薪不写几薪")
        self.assertRegex(seg, r"给薪资维 25 分")

    def test_it_points_at_the_framework_section(self):
        i = RANK.index("期望薪资区间与底线（")
        self.assertIn("有月薪、但没写「几薪」", RANK[i:i + 600])

    def test_the_rest_of_the_enumeration_survived(self):
        """这一格是插在一长串枚举中间的，别把邻居挤掉。"""
        i = RANK.index("期望薪资区间与底线（")
        seg = RANK[i:i + 900]
        self.assertIn("工作强度与公司类型偏好", seg)
        self.assertIn("直接相关与相邻的经验领域", RANK[max(0, i - 200):i])


class TheFloorIsReadFromHisOwnProfile(unittest.TestCase):
    """底线是他自己写的数，不是写死的 —— 换个用户换个数（工具行业无关）。"""

    def test_it_reads_the_number(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = pathlib.Path(t)
            (tmp / "users" / "甲" / "profile").mkdir(parents=True)
            (tmp / "users" / "甲" / "profile" / "candidate.md").write_text(
                "### 薪资\n- **可接受底线：** （年包 **33 万**）\n",
                encoding="utf-8")
            old_root, old_user = ap.ROOT, ap._USER
            ap.ROOT, ap._USER = tmp, ["甲"]
            try:
                self.assertEqual(ap._annual_floor(), 33.0)
            finally:
                ap.ROOT, ap._USER = old_root, old_user

    def test_no_floor_says_so_instead_of_guessing(self):
        """读不出来要说「没查」，不能静默跳过 —— 同这个仓库那条老规矩。"""
        with tempfile.TemporaryDirectory() as t:
            tmp = pathlib.Path(t)
            (tmp / "users" / "甲" / "profile").mkdir(parents=True)
            (tmp / "users" / "甲" / "profile" / "candidate.md").write_text(
                "### 薪资\n- 期望区间那一行\n", encoding="utf-8")
            old_root, old_user = ap.ROOT, ap._USER
            ap.ROOT, ap._USER = tmp, ["甲"]
            try:
                got = ap.check_unknown_months_is_not_a_death_sentence({}, {})
            finally:
                ap.ROOT, ap._USER = old_root, old_user
        self.assertEqual([t for _, t, _ in got], ["读不出薪资底线，这条没查"])

    def test_it_is_not_hard_coded_anywhere(self):
        """**按结构切，不按字符数切。** 第一版取了函数起点后 3000 字，
        一路读进了下一个函数的 docstring（那里有个「45」），当场误报。
        本仓库为「窗口靠数字符」栽过好几次。
        """
        i = AUDIT.index("def check_unknown_months_is_not_a_death_sentence(")
        end = AUDIT.index(chr(10) + "def ", i + 10)
        body = AUDIT[i:end]
        code = body.split('"""')[2] if body.count('"""') >= 2 else body
        self.assertNotIn("45", code, "底线写死了")
        self.assertIn("_annual_floor()", code, "没去读他自己的资料")


class TheCheckFires(unittest.TestCase):
    def _run(self, salary, months, pay_row, flag, floor="40"):
        with tempfile.TemporaryDirectory() as t:
            tmp = pathlib.Path(t)
            (tmp / "users" / "甲" / "profile").mkdir(parents=True)
            (tmp / "users" / "甲" / "profile" / "candidate.md").write_text(
                f"- **可接受底线：** （年包 **{floor} 万**）\n",
                encoding="utf-8")
            d = tmp / "users" / "甲" / "documents" / "applications" / "甲_某岗"
            d.mkdir(parents=True)
            body = ("职位链接：https://example.com/j/1\n\n"
                    "| 维度 | 分数 | 说明 |\n|---|---|---|\n"
                    f"| 薪资与职级 | {pay_row} | 说明 |\n")
            if flag:
                body += "\n⚠ 先问几薪\n"
            (d / "evaluation.md").write_text(body, encoding="utf-8")
            seen = {"k": {"url": "https://example.com/j/1", "salary": salary,
                          "salaryMonths": months}}
            old_root, old_user = ap.ROOT, ap._USER
            ap.ROOT, ap._USER = tmp, ["甲"]
            try:
                return [t for _, t, _ in
                        ap.check_unknown_months_is_not_a_death_sentence(seen, {})]
            finally:
                ap.ROOT, ap._USER = old_root, old_user

    TITLE = "没标薪数的岗被薪资分埋掉了"

    def test_twentyfive_in_the_band_is_reported(self):
        """20-30K：12薪 36 万 < 40 万，16薪 48 万 ≥ 40 万 → 该给 55，给了 25。"""
        self.assertIn(self.TITLE, self._run("20-30K", None, "25/100", False))

    def test_fiftyfive_with_the_flag_is_clean(self):
        self.assertNotIn(self.TITLE, self._run("20-30K", None, "55/100", True))

    def test_fiftyfive_without_the_flag_is_still_reported(self):
        """标志是这条规则的一半：不问「几薪」，55 分只是个数字。"""
        self.assertIn(self.TITLE, self._run("20-30K", None, "55/100", False))

    def test_above_the_floor_at_twelve_is_not_in_the_band(self):
        """50-60k：12薪就有 72 万，根本不在这一档，给什么分都不该报。"""
        self.assertNotIn(self.TITLE, self._run("50-60k", None, "25/100", False))

    def test_below_the_floor_even_at_sixteen_is_allowed_to_be_low(self):
        """10-15k：16薪也只有 24 万 —— 这种才该给 25。"""
        self.assertNotIn(self.TITLE, self._run("10-15k", None, "25/100", False))

    def test_a_stated_month_count_is_not_in_the_band(self):
        """平台写了「·15薪」的岗不适用这条 —— 它没有「未知」可言。"""
        self.assertNotIn(self.TITLE, self._run("20-30K·15薪", 15, "25/100", False))

    def test_the_floor_moves_with_the_profile(self):
        """底线换成 30 万，20-30K 按 12 薪折的 36 万就够了 —— 不再在这一档。"""
        self.assertNotIn(self.TITLE,
                         self._run("20-30K", None, "25/100", False, floor="30"))

    def test_the_finding_names_the_right_command(self):
        """指的得是**一条能把这批改完的**命令，不是让他逐个岗敲。

        原来这里钉的是「逐个跑 `/job-apply <职位链接>`，`/job-rank --all`
        改不到深评」—— 那句话当时是对的：工具确实够不着深评。
        2026-08-29 `score.py --deep` 补上了那一层（连 `evaluation.md` 一起改），
        逐个敲就成了白费力气：实测那一批 89 个，一条命令跑完 87 个。

        **判据没变，还是「别指一条改不到的命令」** —— 变的是哪条能改到。
        """
        i = AUDIT.index('"没标薪数的岗被薪资分埋掉了"')
        seg = AUDIT[i:i + 1200]
        self.assertIn("score.py --deep --apply", seg)
        self.assertNotIn("/job-apply <职位链接>", seg,
                         "又指回逐个敲了 —— 那批现在一条命令能跑完")

    def test_it_stays_a_warn(self):
        i = AUDIT.index('"没标薪数的岗被薪资分埋掉了"')
        self.assertIn('("warn", "没标薪数的岗被薪资分埋掉了"', AUDIT[i - 40:i + 40])


class TheFoldingIsOneImplementation(unittest.TestCase):
    """年包折算走 `ex.annual_package` —— 这个仓库为「一个数两份实现」栽过好几次。"""

    def test_it_does_not_recompute_the_package(self):
        i = AUDIT.index("def _annual_high_12(")
        seg = AUDIT[i:i + 900]
        self.assertIn("ex.annual_package(", seg)

    def test_it_only_answers_when_the_months_are_unknown(self):
        """平台给了可信薪数时这个函数要返回 None，否则整条检查会扫到不该扫的岗。"""
        i = AUDIT.index("def _annual_high_12(")
        seg = AUDIT[i:i + 900]
        self.assertIn('pkg.get("assumed12")', seg)


class TheSignalItLeansOnIsReal(unittest.TestCase):
    """现算一遍：这个库里真的有一半的岗没标薪数。"""

    def _seen(self):
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        import json
        f = (ROOT / "users" / p.read_text(encoding="utf-8").strip()
             / "job_scraper" / "seen_jobs.json")
        if not f.is_file():
            self.skipTest("这位用户还没有职位库")
        return json.loads(f.read_text(encoding="utf-8"))["seen"]

    def test_about_half_the_jobs_have_no_month_count(self):
        seen = self._seen()
        if len(seen) < 200:
            self.skipTest("岗太少，比不出来")
        unknown = sum(1 for e in seen.values()
                      if isinstance(e, dict) and not str(
                          e.get("salaryMonths") or "").strip().isdigit())
        self.assertGreater(
            unknown, len(seen) * 0.2,
            f"只有 {unknown}/{len(seen)} 个岗没标薪数 —— 这一节的前提"
            f"（没标薪数是常态）不成立了")

    def test_the_stated_ones_are_mostly_above_twelve(self):
        """按 12 薪折是**保守**的，不是「差不多」—— 这是那条 55 规则的全部理由。"""
        seen = self._seen()
        got = [int(e["salaryMonths"]) for e in seen.values()
               if isinstance(e, dict)
               and str(e.get("salaryMonths") or "").strip().isdigit()]
        if len(got) < 50:
            self.skipTest("标了薪数的岗太少")
        got.sort()
        self.assertGreater(got[len(got) // 2], 12,
                           "标了薪数的岗中位就是 12 —— 那按 12 薪折不再是保守")


class TheScorerUsesTheSameOptimisticGuess(unittest.TestCase):
    """薪资维与预筛必须是同一个「最乐观」口径：**上沿 × 16**。

    实测（活动用户 2026-11-24 的 /job-auto 收尾）：`scoring.pay_dim` 只拿
    **下沿** × 16 去比，于是「2.5-3.5 万、底线 45 万」被判 25；而 04
    「有月薪、但没写「几薪」」那一节的实测例子（28-35k、45 万）要求给 55。
    预筛 `prescreen.annual_high_wan` 与自检「没标薪数的岗被薪资分埋掉了」
    都按上沿算 —— 同一个口径三处实现，两处对、一处漏。
    """

    FLOOR, EXPECT = 45.0, (72.0, 96.0)

    def _optimistic_high(self, salary):
        import prescreen
        return prescreen.annual_high_wan({"salary": salary, "salaryMonths": None})[0]

    def test_it_agrees_with_the_prescreen_on_the_band(self):
        import scoring as sc
        for salary in ("20-30K", "25-35k", "28-35k", "3.5-5万", "10-15k",
                       "30-45k", "2-3万·13薪"):
            with self.subTest(salary=salary):
                high = self._optimistic_high(salary)
                got = sc.pay_dim({"salary": salary, "salaryMonths": None},
                                 self.FLOOR, self.EXPECT)
                want_ok = high is not None and high >= self.FLOOR
                self.assertEqual(got == sc.PAY_OK, want_ok,
                                 f"{salary}：预筛乐观上沿 {high}，薪资维给了 {got}")

    def test_the_frameworks_own_example_gets_fiftyfive(self):
        """04 的实测例：28-35k、底线 45 万 → 55（下沿差一点，上沿才过）。"""
        import scoring as sc
        self.assertEqual(
            sc.pay_dim({"salary": "28-35k"}, self.FLOOR, self.EXPECT), sc.PAY_OK)

    def test_the_note_says_it_is_the_upper_edge(self):
        """说明那一格跟着同一个数走，别「写着 55、解释的还是下沿」。"""
        import scoring as sc
        n = sc.pay_note({"salary": "28-35k"}, self.FLOOR, self.EXPECT)
        self.assertIn("上沿", n)
        self.assertIn("56", n)   # 月薪上限 3.5 万 × 16 薪 = 56 万


if __name__ == "__main__":
    unittest.main()
