# -*- coding: utf-8 -*-
"""一件「每天都要做」的事，只写在一份偶尔跑一次的报告里。

`job-resume.md` 的「2.6 在线简历」讲的是国内招聘里**反过来的那一路**：HR 在简历库
里搜人、主动联系。那张表的第一行就是「最近刷新/活跃时间」，并且自己写着那是
**这张表里唯一一件每天都要做的事**——搜索结果基本按它排序。

**而 `/job-resume` 是偶尔跑一次的审核报告。** 实测活动用户 2026-08-23：
`users/<u>/reports/` 底下只有一份 `resume-audit-2026-08-01.md`（22 天前），
这期间投出去 85 个、回音 0 个（tracker 里 84 条还挂在 `applied`）。

日常真正跑的是 `/job-auto`，而它整份流程**一次都没提过在线简历**——
从抓、评到出材料全在「你主动投出去」那一路上。零回音那句诊断（`doctor.py`）
也只给到「简历或投递方式」两种可能，第三种（**在库里根本搜不到**）没人说。

修在 auto 的收尾：那正是**他要登平台发材料**的那一刻，刷新是顺手的事。
只在真出了材料时做（没材料就没有那一趟），逐项核对仍归 2.6。

**2026-09-01 改：从「只提醒」变成「代做」。** 本人裁定（原话「你能不能每次
auto 手动帮我刷新」「那你应该有个专门用于刷新建立的命令，每天刷新一次。
该命令是单独的，auto也会包括它」）。原来那条不代做的理由是「平台在登录态
后面」，而浏览器驱动的就是用户自己那个已登录的 Chrome —— 理由本身过期了。
边界只挪了这一格，新判据是**刷新只推时间戳、不改任何东西**；
改内容 / 改设置 / 花钱 / 替他投出去的仍然一个都不代做。
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTO = (ROOT / "workflows" / "job-auto.md").read_text(encoding="utf-8")
RESUME = (ROOT / "workflows" / "job-resume.md").read_text(encoding="utf-8")


def _closing() -> str:
    i = AUTO.index("### 总账末尾：")
    m = re.search(r"^## ", AUTO[i:], re.M)
    return AUTO[i:i + (m.start() if m else 2000)]


class TheClosingReportSaysIt(unittest.TestCase):
    def test_the_line_exists(self):
        self.assertRegex(_closing(), r"在线简历刷[新了]",
                         "auto 跑完仍然只字不提在线简历")

    def test_it_is_in_the_closing_not_every_round(self):
        """每轮都说就是噪音 —— 它挂在总账那一节下面。"""
        i = AUTO.index("结束时给一份总账")
        self.assertLess(i, AUTO.index("### 总账末尾："), "这一节跑到总账前面去了")
        self.assertGreater(AUTO.index("### 总账末尾："),
                           AUTO.index("## 每轮都要报一行"))

    def test_it_only_fires_when_materials_were_made(self):
        """没材料可发就没有那一趟登平台的事。"""
        self.assertRegex(_closing(), r"只在这一轮真出了材料时[说做]")
        self.assertRegex(_closing(), r"说了是噪音|没材料可发就没有那一趟")

    def test_it_says_why_this_works(self):
        """光说「去刷新」没有说服力 —— 要说清搜索结果按什么排。"""
        self.assertRegex(_closing(), r"最近活跃|按.{0,4}活跃.{0,4}排序")
        self.assertRegex(_closing(), r"HR 主动搜|翻不到几页")

    def test_it_carries_the_measured_cost(self):
        """规则说明每天要做的事只写在偶尔跑的报告里等于没写。"""
        seg = _closing()
        self.assertIn("一件每天要做的事只写在一份偶尔跑一次的报告里", seg)

    def test_it_states_the_general_defect(self):
        """这不是「顺便提一嘴」，是一类缺陷 —— 说清了下次才认得出来。"""
        self.assertRegex(_closing(), r"每天要做的事只写在一份偶尔跑一次的报告里")

    def test_it_now_runs_the_refresh_command(self):
        """2026-09-01 本人裁定：auto 收尾要真去刷，不是提醒他刷。"""
        seg = _closing()
        self.assertIn("/job-refresh", seg, "收尾没有去调那条刷新命令")
        # 引号里引它（讲这条规则怎么变的）可以；**加粗当成现行规则**不行。
        self.assertNotIn("**只提醒，不代做**", seg,
                         "还把「只提醒，不代做」当现行规则 —— 那条已被本人推翻")

    def test_it_still_pins_where_the_line_now_is(self):
        """**代做的边界只挪了一格。** 不写死这句，下一版就会顺手去点
        「同步至在线简历」「简历代投」那类按钮 —— 那些会改内容、会替他投出去。
        """
        seg = _closing()
        self.assertRegex(seg, r"只推一个时间戳|不改任何东西",
                         "没写清为什么唯独刷新可以代做")
        self.assertRegex(seg, r"改内容.*改设置.*花钱|花钱.*替他投出去",
                         "没写清哪几类仍然不代做")

    def test_it_does_not_copy_the_button_table(self):
        """那张「长得像刷新但不是」的表在 job-refresh.md 里。
        抄过来两处就会各长各的 —— 这个仓库交过学费的那一课。"""
        seg = _closing()
        self.assertIn("别抄过来", seg)
        self.assertNotIn("| 长得像 |", seg)

    def test_it_does_not_copy_the_whole_checklist(self):
        """公开范围、求职状态那几项归 2.6。抄过来就会两处分叉 ——
        这个仓库里那条「一条规则贴在两个地方就等着它们各长各的」。"""
        seg = _closing()
        for item in ("简历公开范围", "简历完整度", "屏蔽现任公司"):
            with self.subTest(item=item):
                self.assertNotIn(item, seg, f"把 2.6 的「{item}」抄过来了")
        rows = re.findall(r"^\s*\|", seg, re.M)
        self.assertEqual(rows, [], "这一节自己又画了一张核对表")

    def test_it_hands_the_rest_back(self):
        """**要的是那句交接，不是随便一处提名。** `/job-resume` 在这一节里出现两次：
        一次是解释它为什么不够（偶尔跑一次），一次才是交接。只验「出现过」的话，
        删掉交接那句照样绿 —— 变异实测漏过一次。"""
        seg = _closing()
        self.assertRegex(seg, r"仍然走 `/job-resume`",
                         "没把逐项核对交回 /job-resume")
        self.assertIn("逐条核", seg, "没说清交回去的是哪一部分")


class ThePremiseStillHolds(unittest.TestCase):
    """这一句借的是 2.6 的判据。2.6 那半没了，它就成了无源之水。"""

    def test_section_two_six_still_exists(self):
        self.assertIn("### 2.6 在线简历", RESUME)

    def test_the_refresh_row_still_says_daily(self):
        i = RESUME.index("### 2.6 在线简历")
        seg = RESUME[i:i + 3000]
        self.assertIn("最近刷新/活跃时间", seg)
        self.assertIn("每天都要做", seg,
                      "2.6 不再把刷新叫「每天都要做的事」—— auto 那一句的前提没了")

    def test_the_tool_still_refuses_to_touch_the_platform(self):
        """2.6 仍然把手缩着 —— 只是「刷新」那一行被明确摘了出去。
        缩到只剩一句「都不能改」会和 auto 收尾直接打架；
        写成「一项例外都没有」也一样 —— 两边分叉正是这条测试要挡的。"""
        i = RESUME.index("### 2.6 在线简历")
        seg = RESUME[i:i + 3000]
        self.assertIn("没有一项是这个工具能替你改的", seg)
        self.assertRegex(seg, r"除了「刷新」那一行|刷新.{0,6}例外",
                         "2.6 没把刷新摘出去 —— 和 auto 收尾自相矛盾")
        self.assertIn("/job-refresh", seg, "2.6 没指向那条单独的命令")

    def test_auto_still_reports_the_four_numbers(self):
        """原来那份总账答的是另一件事，不许被这次加的挤掉。"""
        i = AUTO.index("结束时给一份总账")
        seg = AUTO[i:i + 200]
        for n in ("评了多少", "可投多少", "出了多少份材料", "队列还剩多少", "为什么停"):
            with self.subTest(n=n):
                self.assertIn(n, seg)


class TheOutboundOnlyBlindSpotIsRealElsewhere(unittest.TestCase):
    """零回音那句诊断只给两种可能，第三种（搜不到）不在里面 ——
    这条不要求改它（措辞归 doctor），只盯着别有人把 auto 这一句删掉之后
    整个仓库又回到「只有主动投」那一种模型。"""


    def test_at_least_one_daily_surface_names_the_inbound_path(self):
        """`/job-auto` 是他每天跑的那条。它和 2.6 之外，没有第三处说过这一路。"""
        self.assertTrue(
            any("在线简历" in (ROOT / "workflows" / f"{c}.md").read_text(encoding="utf-8")
                for c in ("job-auto", "job-resume")),
            "没有任何一条日常命令提过「HR 反过来搜你」这一路")


if __name__ == "__main__":
    unittest.main()
