# -*- coding: utf-8 -*-
"""`/job-html-report` 拿「行业」切了四刀，而那一列 0/85 —— 一刀都切不动。

命令的标题就是「投后分析报表：**哪类岗回复率高**、卡在哪一环」，而「哪类岗」
落在台账的 `sector` 列上。这一列贯穿整份报表：Step 2 的汇总、横向条形图、
表格里的一列、还有一个下拉筛选。

**它永远是空的。** `tools/tracker.py` 的 `set_status` 明写着
「sector / role_type / channel 留空——**不猜**」，而它是台账唯一的写入方；
除了用户自己往 CSV 里手填，没有第二条路。实测活动用户 2026-08-23：
85 行里 `sector` 非空 **0** 行。四处同时变成一片空白。

## 办法就在隔壁那一条里

同一段的「按渠道」写着「取不到就从 `source` 的链接推（`tracker.channel_of`）」——
**读时推导，不写回台账**。行业照做：按 `source` 回查 `seen_jobs.json` 的
`compIndustry`，实测 85 行能补出 **62** 行、29 个行业。

「不写回」这一半必须写清楚，否则下一版会顺手去改 `set_status` ——
那正是它那条注释拦着的事（台账是给人回看的，填一个「大概是这个行业」进去，
下次校准就按它算了）。读时推导只影响这一张报表，不落盘，两条不冲突。

## 顺带修了同一张图的第二个数

图表那一节写的是「每个行业的**公司数**」，Step 2 数的是**记录数** ——
同一张图，两个数。实测 30 个行业里 5 个两数不同，合计 **85 条 vs 77 家**：
这张图的合计会比同一页上的「投递总数」少 8。隔壁「按渠道」写的是「判据同上」，
行业这一条跟着改成引用。
"""
import csv
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import tracker  # noqa: E402

DOC = (ROOT / "workflows" / "job-html-report.md").read_text(encoding="utf-8")
TRK = (ROOT / "tools" / "tracker.py").read_text(encoding="utf-8")
EX = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")


def flat(s: str) -> str:
    """拉平成一行。折行留下的空格夹在汉字中间，`assertIn` 会落空。"""
    s = " ".join(s.split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


def step2_industry() -> str:
    i = DOC.index("- **按行业：**")
    return DOC[i:DOC.index("\n- **按渠道：**", i)]


class TheFallbackExists(unittest.TestCase):
    def test_it_reads_the_job_library(self):
        seg = flat(step2_industry())
        self.assertIn("取不到就从职位库推", seg, "按行业那一条仍然只读 sector")
        self.assertIn("compIndustry", seg)

    def test_it_matches_by_the_source_url(self):
        """台账和职位库之间只有 `source` 这一条线。"""
        self.assertIn("`source` 链接去 `seen_jobs.json`", flat(step2_industry()))

    def test_it_says_read_time_not_write_back(self):
        """这一半漏掉的话，下一版会去改 `set_status` —— 那条注释正拦着这个。"""
        seg = flat(step2_industry())
        self.assertIn("读时推导，不写回台账", seg)
        self.assertIn("不落盘", seg)

    def test_it_names_the_decision_it_must_not_break(self):
        seg = flat(step2_industry())
        self.assertIn("set_status", seg)
        self.assertRegex(seg, r"大概是这个行业")

    def test_the_unmatched_bucket_is_kept(self):
        """丢掉补不出来的那些，这一组的合计就小于投递总数。"""
        seg = flat(step2_industry())
        self.assertIn("未标注行业", seg)
        self.assertRegex(seg, r"合计小于投递总数")

    def test_it_cites_the_precedent_for_showing_the_gap(self):
        self.assertIn("gate_fail_tally", flat(step2_industry()))

    def test_it_carries_the_measurement(self):
        seg = flat(step2_industry())
        self.assertIn("compIndustry", seg)
        self.assertIn("sector", seg)

    def test_it_says_what_breaks_without_it(self):
        """不写清代价，下一版会觉得「不就是一列空的」。"""
        seg = flat(step2_industry())
        self.assertRegex(seg, r"条形图、行业下拉、表格里那一列会\*\*同时\*\*变成一片空白")
        self.assertRegex(seg, r"「哪类岗回复率高」就是本命令标题里的那半句")


class TheSourceItNeedsIsActuallyRead(unittest.TestCase):
    """A 说「去用 B」而 B 够不着 —— 这个仓库反复栽的一类。

    判据落在 Step 2，而「读哪几个文件」是 Step 1 定的。Step 1 不列，
    执行者手里就没有那份数据。
    """

    def _step1(self) -> str:
        i = DOC.index("## Step 1：收数据")
        return DOC[i:DOC.index("**状态归一**", i)]

    def test_step1_lists_it(self):
        self.assertIn("`job_scraper/seen_jobs.json`", self._step1(),
                      "Step 2 要用它，Step 1 却没让人读")

    def test_step1_says_what_it_is_for(self):
        """读它干什么要写清楚 —— 否则下一个人不知道能不能改这一步。

        原来断言的是「只为补行业」。2026-08-24 那一步开始**补两样**
        （行业，和「谁在招」：猎头代招 vs 企业直招，判据见 Step 2 那一节）——
        规则没变，事实变了。所以这里改成「有没有说清读它干什么」，
        并把两样都点名：少了任何一样，Step 2 那边就有一个分组取不到数。
        """
        s = flat(self._step1())
        self.assertRegex(s, r"补两样：行业，和「谁在招」")
        self.assertIn("compIndustry", s)
        self.assertIn("isHeadhunter", s)

    def test_it_tells_you_not_to_read_details_too(self):
        """`details/*.json` 里有同名字段，但无需额外扫描。"""
        seg = flat(self._step1())
        self.assertIn("只读这一个文件", seg)
        self.assertIn("seen_jobs.json", seg)
        self.assertIn("details/", seg)

    def test_it_reconciles_with_the_do_not_pad_rule(self):
        """第 1 条有一句「绝不读 `seen_jobs.json` 充数」，第 3 条正好去读它。

        两条不冲突（一个禁的是拿未投职位当记录，一个只回查一个字段），
        但不写明的话执行者两头撞 —— 要么不敢补行业，要么把未投的岗混进来。
        """
        seg = flat(self._step1())
        self.assertIn("行数只由台账决定，职位库一行都加不进来", seg)
        self.assertRegex(seg, r"不许因此少一行、也不许多一行")

    def test_the_do_not_pad_rule_itself_survives(self):
        seg = flat(self._step1())
        self.assertRegex(seg, r"\*\*绝不\*\*为了「让报表有内容」去读 "
                              r"`seen_jobs\.json` 里的未投职位充数")

    def test_a_missing_library_is_not_an_error(self):
        """投递记录可以是手写的 —— 没抓过岗照样要出得来报表。"""
        seg = flat(self._step1())
        self.assertRegex(seg, r"这个文件不存在（还没抓过岗）")
        self.assertIn("**不报错**", seg)

    def test_the_no_tracker_stop_rule_survives(self):
        """没有投递记录时整条命令就该停 —— 这次改动不能把它带松。"""
        self.assertIn("这是投**后**分析工具，没有投递记录时它没有可分析的对象",
                      DOC)


class TheChartCountsTheSameThing(unittest.TestCase):
    def _chart(self) -> str:
        i = DOC.index("2. **按行业**（横向条形）")
        return DOC[i:DOC.index("\n3. **按渠道**", i)]

    def test_it_no_longer_says_company_count(self):
        # 注释里逐字引了旧写法（「原来写的是…公司数」），整段扫会撞上自己的说明；
        # 只看 ⚠️ 之前那一句。
        head = self._chart().split("⚠️")[0]
        self.assertNotIn("每个行业的公司数", head, "图表这一节还在数公司")

    def test_it_defers_to_step2(self):
        self.assertIn("判据同上", self._chart())

    def test_it_carries_the_divergence(self):
        seg = flat(self._chart())
        self.assertIn("每个行业的**公司数**", seg)
        self.assertIn("记录数", seg)

    def test_it_says_which_metric_wins_and_why(self):
        seg = flat(self._chart())
        self.assertRegex(seg, r"其余每一张图（状态分布 / 按渠道 / 漏斗）数的都是记录")

    def test_it_states_the_rule_for_this_whole_section(self):
        """只修这一条，下一张图照样会复述判据。"""
        self.assertIn("图表这一节只说画法，判据一律回 Step 2 拿",
                      flat(self._chart()))

    def test_the_channel_chart_still_defers(self):
        """它本来就是对的写法 —— 别被这次改动带歪。"""
        self.assertIn("3. **按渠道**（条形）—— 按平台分组（判据同上", DOC)


class ThePrecedentItCopiesIsIntact(unittest.TestCase):
    def test_the_channel_fallback_still_exists(self):
        seg = flat(DOC[DOC.index("- **按渠道：**"):][:400])
        self.assertRegex(seg, r"取不到就从 `source` 的链接推（`tracker\.channel_of`）")

    def test_channel_of_is_real(self):
        self.assertTrue(callable(getattr(tracker, "channel_of", None)))

    def test_set_status_still_refuses_to_guess(self):
        """整条改动建立在「写入方故意留空」上。它没了，前提就没了。"""
        i = TRK.index("def set_status(")
        seg = flat(TRK[i:TRK.index("\ndef ", i + 10)].replace("#", " "))
        self.assertRegex(seg, r"sector / role_type / channel 留空——\*\*不猜\*\*")

    def test_set_status_still_does_not_write_sector(self):
        i = TRK.index("def set_status(")
        body = TRK[i:TRK.index("\ndef ", i + 10)]
        self.assertNotIn('hit["sector"]', body, "写入方开始猜行业了")

    def test_the_unknown_bucket_precedent_survives(self):
        self.assertIn("归到「没说是哪道」", EX)


class TheSignalItLeansOnIsReal(unittest.TestCase):
    """有语料时验一次：那一列真的是空的，而职位库真的补得出来。"""

    def _corpus(self):
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        u = p.read_text(encoding="utf-8").strip()
        t = ROOT / "users" / u / "job_search_tracker.csv"
        s = ROOT / "users" / u / "job_scraper" / "seen_jobs.json"
        if not (t.is_file() and s.is_file()):
            self.skipTest("没有投递记录或没有职位库")
        rows = list(csv.DictReader(t.open(encoding="utf-8-sig")))
        seen = json.loads(s.read_text(encoding="utf-8"))["seen"]
        by = {e.get("url"): e for e in seen.values()
              if isinstance(e, dict) and e.get("url")}
        if len(rows) < 20:
            self.skipTest("投递记录太少，说明不了")
        return rows, by

    def test_the_column_really_is_empty(self):
        rows, _ = self._corpus()
        filled = sum(1 for r in rows if (r.get("sector") or "").strip())
        self.assertEqual(filled, 0,
                         f"{filled} 行有 sector —— 这条兜底的前提变了，重新量一次")

    def test_the_library_really_recovers_most_of_them(self):
        rows, by = self._corpus()
        got = sum(1 for r in rows
                  if (by.get((r.get("source") or "").strip())
                      or {}).get("compIndustry"))
        self.assertGreater(got, len(rows) // 2,
                           f"只补得出 {got}/{len(rows)} —— 兜底不划算了")

    def test_records_and_companies_really_diverge(self):
        """两个数要是从来不差，图表那半条改动就没有依据。"""
        rows, by = self._corpus()
        recs, comps = {}, {}
        for r in rows:
            k = ((by.get((r.get("source") or "").strip()) or {})
                 .get("compIndustry") or "未标注行业")
            recs[k] = recs.get(k, 0) + 1
            comps.setdefault(k, set()).add((r.get("company") or "").strip())
        self.assertNotEqual(sum(recs.values()),
                            sum(len(v) for v in comps.values()),
                            "记录数与公司数完全相同 —— 那一条改动没有依据了")


if __name__ == "__main__":
    unittest.main()
