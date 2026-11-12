# -*- coding: utf-8 -*-
"""标题写着「哪类岗回复率高」，而它全文一次都没提过猎头和直招。

实测 2026-08-24：`job-html-report.md` 里 `猎头` 0 命中、`直招` 0 命中。
它按**平台**分组（猎聘 / BOSS / 智联 / 前程），那是「从哪儿抓到的」，
不是「谁在招」。

## 这条教训总览页已经付过一次

`build_dashboard.no_reply_advice` 的说明逐字写着：

> 「投了 N 个 0 回音，去审简历」这句话的分量，完全取决于 N 里有多少是猎头代招。
> 简历投给猎头是先进他的库，推不推、什么时候推由他定，岗位可能早就关了 ——
> **那批的沉默是渠道的事，怪不到简历头上**。
>
> 实测：54 个已决出结果里 **32 个是猎头代招**，直招只有 22 个。此前这一条不分
> 渠道，把 54 个囫囵算一起然后说「回头审简历」—— **59% 的样本根本不构成简历
> 的证据，而按它去改简历是照着错的诊断动刀**。

面板修了，报表没修。而报表才是他专门去看「问题出在哪」的那份东西。

## 他现在的构成

    猎头代招 44 · 企业直招 36 · 判不出 5   （共 85 条）

一个整体「回复率 0%」印出来，读者只能得出那个被修掉的结论。

## 判不出的单独一档

`via_headhunter` 返回 `None` 时不许并进「直招」—— **没判过不是「不是猎头」**。
（同 `_cli.addressee_problem` 那条：库里没判过，凭什么说他写反了。）
"""
import csv
import json
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402

REP = (ROOT / "workflows" / "job-html-report.md").read_text(encoding="utf-8")
BD = (ROOT / "tools" / "build_dashboard.py").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*(?:>|#:?)\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


def seg() -> str:
    i = REP.index("- **按谁在招：猎头代招 vs 企业直招 vs 判不出。**")
    return flat(REP[i:REP.index("- **按年份/季度：**", i)])


class TheGroupingExists(unittest.TestCase):
    def test_the_bullet_exists(self):
        self.assertIn("- **按谁在招：猎头代招 vs 企业直招 vs 判不出。**", REP)

    def test_it_sits_in_the_stats_step(self):
        """写在别处等于没写 —— 算统计的人读的是 Step 2。"""
        a = REP.index("## Step 2：算汇总统计")
        b = REP.index("- **按谁在招")
        self.assertLess(a, b)
        self.assertLess(b, REP.index("## Step 3"))

    def test_it_uses_the_canonical_judge(self):
        """字段名驼峰/下划线这个仓库吃过亏 —— 别在这儿自己认。"""
        self.assertIn("_cli.via_headhunter", seg())

    def test_the_judge_it_cites_exists(self):
        self.assertTrue(callable(_cli.via_headhunter))

    def test_unknown_is_its_own_bucket(self):
        """没判过不是「不是猎头」。"""
        s = seg()
        self.assertRegex(s, r"`None` 单独一档，别并进「直招」")
        self.assertRegex(s, r"没判过不是「不是猎头」")

    def test_the_data_is_fetched_in_step_one(self):
        """Step 2 要用它，Step 1 得先取回来。"""
        i = REP.index("**`job_scraper/seen_jobs.json`**")
        seg1 = flat(REP[i:i + 500])
        self.assertIn("isHeadhunter", seg1)
        self.assertIn("_cli.via_headhunter", seg1)

    def test_it_does_not_add_a_second_read(self):
        """同一次按 `source` 回查顺手取 —— 再开一次读盘是白花。"""
        i = REP.index("**`job_scraper/seen_jobs.json`**")
        self.assertRegex(flat(REP[i:i + 500]), r"同一次回查顺手取")


class ItChangesHowTheRatesAreRead(unittest.TestCase):
    """**这才是它存在的理由。** 只多画一张图等于什么也没修。"""

    def test_it_says_the_grouping_is_not_just_another_group(self):
        self.assertRegex(seg(), r"这一档不是「又一个分组」，它决定上面那两个率该怎么读")

    def test_it_quotes_the_lesson_the_panel_already_paid_for(self):
        s = seg()
        self.assertRegex(s, r"那批的沉默是渠道的事，怪不到简历头上")
        self.assertRegex(s, r"照着错的诊断动刀")


    def test_it_records_that_the_report_never_mentioned_it(self):
        s = seg()
        self.assertIn("猎头代招", s)
        self.assertIn("企业直招", s)

    def test_it_demands_the_rates_be_recomputed_on_direct_only(self):
        """并排摆出来，而不是把整体那个数换掉 —— 整体数也是真的。"""
        s = seg()
        self.assertRegex(s, r"要在企业直招那一组上再算一遍")
        self.assertRegex(s, r"并排\s*摆出来（整体 / 直招）")

    def test_it_keeps_the_overall_number(self):
        self.assertRegex(seg(), r"整体那个数留着")

    def test_a_small_direct_group_gets_no_rate(self):
        """三倍法则：直招不够 20 个时，一个率印出来就是拿运气当结论。"""
        s = seg()
        self.assertRegex(s, r"`< 20`")
        self.assertRegex(s, r"不要印一个率")

    def test_the_threshold_it_cites_exists(self):
        import build_dashboard as bd
        self.assertEqual(bd.NO_REPLY_ALARM, 20)


class TheChartSitsWhereItIsNeeded(unittest.TestCase):
    def test_the_chart_exists(self):
        self.assertIn("**谁在招**（条形）", REP)

    def test_it_defers_the_judgement_to_step_two(self):
        """图表那一节只说画法 —— 判据复述一遍就是等着它们各长各的
        （那一节自己写着这条）。"""
        i = REP.index("**谁在招**（条形）")
        self.assertIn("判据同上", REP[i:i + 200])

    def test_it_is_next_to_the_funnel(self):
        """漏斗那个整体转化率怎么读，取决于这张图的构成。"""
        i = REP.index("**谁在招**（条形）")
        j = REP.index("**投递漏斗**（横向条形）")
        self.assertLess(i, j)
        self.assertLess(j - i, 300)

    def test_the_charts_are_renumbered(self):
        """插一张图要把后面的序号推下去，不能有两个 4。"""
        i = REP.index("### 图表（内联 SVG）")
        nums = re.findall(r"^(\d+)\. \*\*", REP[i:REP.index("### 表格", i)], re.M)
        self.assertEqual(nums, [str(k) for k in range(1, len(nums) + 1)])

    def test_the_existing_charts_survive(self):
        i = REP.index("### 图表（内联 SVG）")
        s = REP[i:REP.index("### 表格", i)]
        for k in ("状态分布", "按行业", "按渠道", "投递漏斗"):
            with self.subTest(k=k):
                self.assertIn(k, s)


class TheNeighbouringRulesSurvive(unittest.TestCase):
    """这一条是插进 Step 2 中间的。前后两条判据一个字不许动。"""

    def test_the_industry_rule_survives(self):
        self.assertRegex(flat(REP), r"`sector` 实际上永远是空的")

    def test_the_channel_rule_survives(self):
        self.assertRegex(flat(REP), r"这里原来写的是「网申 / 内推 / 其它」")

    def test_the_too_early_rule_survives(self):
        """「还没到该回的时候就别印 0%」比这一条更早，别被挤掉。"""
        s = flat(REP)
        self.assertRegex(s, r"一个回音都没有，而「还在等」的超过总数一半")
        self.assertRegex(s, r"判据是「还在等的占多数」，不是「有一个在等」")

    def test_the_silence_line_is_still_borrowed(self):
        self.assertRegex(flat(REP), r"别在这里另定一个数")


class TheSignalItLeansOnIsReal(unittest.TestCase):
    """现算：他这批投递真的一半是猎头，而直招那组真的够下结论。"""

    def _split(self):
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        u = ROOT / "users" / p.read_text(encoding="utf-8").strip()
        f, t = u / "job_scraper" / "seen_jobs.json", u / "job_search_tracker.csv"
        if not (f.is_file() and t.is_file()):
            self.skipTest("还没有职位库或投递记录")
        seen = json.loads(f.read_text(encoding="utf-8"))["seen"]
        byurl = {(e.get("url") or ""): e for e in seen.values()
                 if isinstance(e, dict)}
        rows = list(csv.DictReader(t.open(encoding="utf-8-sig")))
        if len(rows) < 20:
            self.skipTest("投递太少")
        import collections
        c = collections.Counter()
        for r in rows:
            e = byurl.get((r.get("source") or "").strip()) or {}
            v = _cli.via_headhunter(e) if e else None
            c[True if v is True else (False if v is False else None)] += 1
        return c, len(rows)

    def test_the_agency_share_is_large_enough_to_change_the_reading(self):
        """**这是整条的支点。** 猎头占比很小的时候，整体率就够用了。"""
        c, n = self._split()
        self.assertGreater(
            c[True], n * 0.2,
            f"猎头代招只占 {c[True]}/{n} —— 整体率不再被它带偏，"
            f"这一节的论点要重看")

    def test_the_direct_group_is_big_enough_to_conclude_on(self):
        """够不着 20 时，那一节要求写「还不够下结论」而不是印一个率。"""
        c, _n = self._split()
        import build_dashboard as bd
        if c[False] < bd.NO_REPLY_ALARM:
            self.skipTest(f"直招只有 {c[False]} 个 —— 那一节的小样本分支该生效")
        self.assertGreaterEqual(c[False], bd.NO_REPLY_ALARM)

    def test_the_unknown_bucket_is_not_empty(self):
        """有「判不出」的，那一档才不是纸上规则。一个都没有时跳过。"""
        c, _n = self._split()
        if not c[None]:
            self.skipTest("全都判得出 —— 好事")
        self.assertGreater(c[None], 0)


if __name__ == "__main__":
    unittest.main()
