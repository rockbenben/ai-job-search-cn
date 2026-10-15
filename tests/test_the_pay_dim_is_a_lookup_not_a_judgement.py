# -*- coding: utf-8 -*-
"""薪资那一维是查表，不是打分——而 32% 的岗上写的是别的数。

`04-job-evaluation.md`「打分口径：比的是够不够」给的是一张四行的查表：
年包**下沿**到顶 90 / 落在期望区间 85 / 低于期望但过底线 55 / 低于底线 25。
输入只有 `salary` + `salaryMonths` + 资料里的两个数，**没有判断余地**——
它是四维里唯一能被机器完整验算的一维。

旁边此前有两条检查，各守一个特例（`check_negotiable_salary_is_not_scored`
守面议不该打分、`check_unknown_months_is_not_a_death_sentence` 守没标薪数
不该被埋），**主表本身没人守**。

实测 2026-08-27：全库 763 个填了薪资维的岗，**247 个（32%）对不上**，
其中 146 个取的是表上根本没有的值（70、72、75、80…… 一整条连续刻度）。
本会话自己也犯了另一种：`20-40K·15薪` 的下沿 30 万低于 45 万底线，
写的却是 55，附一句「门槛低说明定级弹性大」——04 早给这句话起过名字，
叫「折算一个中性值」，那一节的标题就是**别走第三条路**。

薪资维占 25% 权重，一档之差是综合分 7.5 分，足以翻一整档判词。

---

## 2026-10-15：这条查表的**底线那一行**改了口径

下面这三条用例的期望值变了（`20-40K` / `20-35k·14薪` / `25-50k` 全部 25 → 55），
判据是 `profile/candidate.md`「薪资」一节里 2026-10-15 本人的那条裁定。

**旧规则**：只比年包**下沿**；下沿够不着底线就是 25。
**旧理由**：「上沿是给最理想候选人的，拿它打分等于按最好情况算」——
这条理由本身没错，它防的是**按最好情况承诺一个数**。

**为什么现在不成立**：本人在看到 `20-40K·15薪`（年包 30-60 万）被判 25 之后说
「30-60 过了45的线」。他要回答的不是「这个岗承诺给我多少」，
而是「**这个岗能不能给到我的底线**」——而它的区间上沿 60 万确实给得到。
这两个问题答案不同，所以规则也得分开：

- **判「落在期望区间 / 到顶」（85 / 90）→ 仍然只看下沿。**
  上沿再高也不许把下沿远低于期望下限的岗抬进期望区间
  （`test_the_high_edge_cannot_lift_a_job_into_the_expectation_bands` 守着这条）。
- **判「过没过底线」（55 / 25）→ 下沿不过、上沿过了，算 55。**

⚠️ **这一档仍然不是「折算中性值」。** 本文件开头记的那次教训（给一个下沿低于底线
的岗写 55、附一句「门槛低说明定级弹性大」）被推翻的方式很具体：
**不是因为「门槛低所以弹性大」，而是因为上沿那个数本身就过了底线。**
判据仍然是表、仍然只有四个取值、仍然没有判断余地——
变的只是查表时拿哪一端去比底线，而那一条写死在 `candidate.md` 里。

实测影响：全库 **255 个粗筛条目**从 25 变 55；上沿 ≥100 万的 **0 个**，
所以「宽到离谱的区间被抬高」这个担心在真实数据上不成立。
"""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import audit_pipeline as ap  # noqa: E402
import scoring  # noqa: E402

FLOOR, EXPECT = 45.0, (72.0, 96.0)


def dim(salary, months=None):
    return ap._pay_dim_should_be({"salary": salary, "salaryMonths": months},
                                 FLOOR, EXPECT)


class TheTableHasFourRowsAndOnlyFour(unittest.TestCase):
    CASES = [
        # (薪资串, 薪数, 该给几分, 为什么)
        ("80-110K", None, 90, "按 12 薪下沿 96 万，正好顶到期望上沿"),
        ("50-80K", 16, 85, "下沿 80 万落在 72-96 万里"),
        ("60-90K", 15, 85, "下沿 90 万，还在区间内——没到顶就不是 90"),
        ("40-70K", 16, 55, "下沿 64 万，低于期望下沿、高于底线"),
        ("30-60K", 16, 55, "下沿 48 万"),
        ("20-40K", 15, 55, "下沿 30 万低于底线，但上沿 60 万过底线 → 区间跨底线"),
        ("20-35k·14薪", 14, 55, "下沿 28 万、上沿 49 万，上沿过底线"),
        ("35-55k", None, 55, "12 薪下沿 42 万够不着，16 薪 56 万够得着 → 55"),
        ("25-50k", None, 55, "12 薪 30-60 万，上沿过底线 → 55（2026-10-15 新口径）"),
        ("10-20k", 15, 25, "年包 15-30 万，上沿 30 万也够不着 45 万底线 → 才给 25"),
    ]

    def test_each_case_lands_on_its_row(self):
        for salary, months, want, why in self.CASES:
            with self.subTest(salary=salary, why=why):
                self.assertEqual(dim(salary, months), want, why)

    def test_nothing_ever_lands_between_the_rows(self):
        """**这才是当初露出来的那一头。** 70、72、75、80 这些数不该出得来。"""
        allowed = {ap._PAY_TOP, ap._PAY_IN, ap._PAY_OK, ap._MONTHS_LOW}
        for lo in range(5, 200, 3):
            for months in (None, 12, 13, 14, 15, 16):
                got = dim(f"{lo}-{lo * 2}k", months)
                with self.subTest(salary=f"{lo}-{lo*2}k", months=months):
                    self.assertIn(got, allowed, f"{got} 不在那张表上")

    def test_the_high_edge_cannot_lift_a_job_into_the_expectation_bands(self):
        """上沿**抬不进期望区间那一档**，只有「过没过底线」那一步会看它。

        `20-100k·16薪` 的下沿 32 万、上沿 192 万——按下沿它够不着 72 万的期望下沿，
        所以**不是** 85 / 90。

        判据在 `profile/candidate.md`「薪资」一节（2026-10-15 本人裁定）。
        """
        self.assertEqual(dim("20-100k·16薪", 16), scoring.PAY_OK)

    def test_negotiable_is_left_to_the_other_check(self):
        """面议归 `check_negotiable_salary_is_not_scored`，这里返回 None。"""
        for s in ("薪资面议", "面议", "另议", ""):
            with self.subTest(salary=s):
                self.assertIsNone(dim(s))


class TheCheckReadsTheNumbersFromTheProfile(unittest.TestCase):
    """底线与期望**从资料里读**，不写死在工具里。

    读不出就如实说没查——「没查」和「查过没有」是两件事，这条仓库规矩
    在 `_annual_floor` / `_candidate_years` 上已经执行了两次。
    """

    def test_it_says_so_instead_of_guessing(self):
        old = list(ap._USER)
        try:
            ap._USER[:] = ["查无此人"]
            out = ap.check_pay_dim_matches_its_own_number({}, {})
        finally:
            ap._USER[:] = old
        self.assertEqual(len(out), 1)
        self.assertIn("没查", out[0][1])

    def test_the_expected_range_parses_from_the_active_profile(self):
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        user = p.read_text(encoding="utf-8").strip()
        if not (ROOT / "users" / user / "profile" / "candidate.md").is_file():
            self.skipTest("活动用户还没建档")
        old = list(ap._USER)
        try:
            ap._USER[:] = [user]
            got = ap._annual_expect()
        finally:
            ap._USER[:] = old
        self.assertIsNotNone(got, "「期望区间」那一行里读不出年包数")
        self.assertLess(got[0], got[1])
        self.assertGreater(got[0], 0)


class ItIsWiredIntoTheAudit(unittest.TestCase):
    def test_the_check_is_registered(self):
        self.assertIn(ap.check_pay_dim_matches_its_own_number,
                      [fn for _, fn in ap.CHECKS])

    def test_it_does_not_print_markdown(self):
        """终端输出不带标记——同 `check_negotiable_salary_is_not_scored` 那条注释。"""
        fn = ap.check_pay_dim_matches_its_own_number
        # 文档字符串是给读代码的人看的，带标记没问题；印出去的是别的常量。
        for const in fn.__code__.co_consts:
            if not isinstance(const, str) or const == fn.__doc__:
                continue
            if "**" in const:
                self.fail(f"消息里带了 markdown：{const[:60]}")


if __name__ == "__main__":
    unittest.main()
