# -*- coding: utf-8 -*-
"""「必须改：无」——那份报告是他在「投了没回音」之后被指过来读的。

「下一步」在零回音时把人送去 `/job-resume`，理由是会话自检那句
「企业直招那批也全没回音，问题多半在简历**或投递方式**上」——**它自己就是两可的**
（面板那侧 `_why_silent` 同样只给到「再回头审一遍简历」，不点名是哪一边）。

而同一页的四格（`outcomeStats.appliedFit`）已经把这个两可解开了：
实测活动用户 2026-08-23，投出去的 78 个里 **49 个是「专业能力够、
但这个岗要的行业经验你没做过」，真正对得上的只有 17 个**。
面板据此明写着「不是简历写得不好，是投的地方不对」。

**可 `/job-resume` 读不到这一格。** Step 2.5 只引用 `resume_insight`
（行业对口的岗要什么词），不看投后那一栏。后果实测过：2026-08-01 那份审核
结论是「必须改：无」，此后三周照原样又投了几十个，仍然 0 回音 ——
**审出「没问题」而不说清那不等于「一切正常」，用户就会照原样接着投。**

两处补：
- Step 2.5 读 `appliedFit`，按那一格是不是多数给出「简历这侧能改的有限」。
- Step 3 定死：「必须改」为空时，报告开头必须说清简历这一侧的结论**不解释**
  那个沉默，并指回真正的去处。
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESUME = (ROOT / "workflows" / "job-resume.md").read_text(encoding="utf-8")
#: 那句两可的话在 **doctor** 里（`build_dashboard._why_silent` 只给到
#: 「再回头审一遍简历」，不点名是哪一边）。第一版把它记到了 `_why_silent` 头上，
#: 被这条测试当场抓出来 —— 出处写错，读的人就找不到那句话。
DOCTOR = (ROOT / "tools" / "doctor.py").read_text(encoding="utf-8")
DASH = (ROOT / "tools" / "build_dashboard.py").read_text(encoding="utf-8")


def _section(head: str) -> str:
    i = RESUME.index(head)
    m = re.search(r"^#{2,4}\s", RESUME[i + len(head):], re.M)
    return RESUME[i:i + len(head) + (m.start() if m else 3000)]


class TheAuditReadsThePostApplicationEvidence(unittest.TestCase):
    def _seg(self):
        return _section("### 2.5 市场对得上吗")

    def test_it_names_the_field(self):
        self.assertIn("outcomeStats.appliedFit", self._seg(),
                      "审核仍然不看投后那一栏")

    def test_it_branches_on_whether_that_quadrant_dominates(self):
        """占多数 → 简历这侧能改的有限；不占 → 沉默确实指向材料本身。
        只报个数而不分流，等于把判断又推回给执行者。"""
        seg = self._seg()
        self.assertRegex(seg, r"能改的有限")
        self.assertRegex(seg, r"指向材料本身|按下面的报告逐条改")


    def test_it_keeps_the_measured_cost(self):
        seg = self._seg()
        self.assertRegex(seg, r"必须改：无|63%")

    def test_it_does_not_guess_when_the_data_is_missing(self):
        """读不到就如实说 —— 同这份文档别处那条「没查和查过没有是两件事」。"""
        self.assertRegex(self._seg(), r"如实说没读|别猜")

    def test_the_original_half_survives(self):
        """`resume_insight` 那半（该补哪些词）不许被挤掉，它答的是另一个问题。"""
        seg = self._seg()
        self.assertIn("resume_insight", seg)
        self.assertRegex(seg, r"这是\*\*改简历\*\*|一天的事")


class AnEmptyMustFixSectionStillOwesAnAnswer(unittest.TestCase):
    def _seg(self):
        i = RESUME.index("**空的小节直接不写**")
        return RESUME[i:i + 1200]

    def test_the_rule_exists(self):
        """**两句都要在。** 那一段里「「必须改」为空时」出现两次
        （一次是禁令、一次是要求），只验一次的话删掉禁令照样绿 ——
        变异实测漏过一次。"""
        seg = self._seg()
        self.assertEqual(seg.count("「必须改」为空时"), 2,
                         "「不能只剩一句没问题」的禁令或「必须指回去处」的要求少了一条")

    def test_it_forbids_the_bare_all_clear(self):
        seg = self._seg()
        self.assertRegex(seg, r"不能只剩一句「没问题」|画等号")

    def test_it_requires_pointing_somewhere(self):
        """光说「简历没问题」是把人留在原地。要指回真正的去处。"""
        self.assertRegex(self._seg(), r"指回真正的去处|真正的去处")

    def test_it_carries_the_evidence(self):
        """规则不带证据就会被当成洁癖删掉。"""
        self.assertRegex(self._seg(), r"不解释.{0,4}那个沉默|真正的去处|投递策略")

    def test_the_no_empty_placeholder_rule_survives(self):
        """原来那条（空小节不写「（无）」）管的是另一件事，不许被覆盖。"""
        self.assertIn("不要留「（无）」", self._seg())


class TheTwoSidesStillDisagreeByDesign(unittest.TestCase):
    """「下一步」是两可的、四格是明确的 —— 这一条盯着别有人把两边改成一边倒。"""


    def test_the_panel_still_resolves_it(self):
        os_tsx = (ROOT / "web" / "src" / "components"
                  / "OutcomeStats.tsx").read_text(encoding="utf-8")
        self.assertIn("不是简历写得不好，是投的地方不对", os_tsx,
                      "四格那句结论没了，2.5 就没有可引用的对象")

    def test_the_field_is_actually_exported(self):
        """文档让读的字段必须真的在快照里 —— 指一个不存在的字段等于没写。"""
        src = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
        self.assertIn('"appliedFit"', src, "导出侧没有这个字段")


if __name__ == "__main__":
    unittest.main()
