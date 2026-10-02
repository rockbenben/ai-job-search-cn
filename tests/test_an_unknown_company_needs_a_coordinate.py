# -*- coding: utf-8 -*-
"""简历上四家公司 HR 一家都没听过，而单位那一栏只有「名字 · 城市」。

`05-cv-templates.md` 把简历结构管得很细 —— 章节顺序、期望年包分渠道写不写、
页数上限、`@` 转义、项目符号写法。**但没有一条管「单位」那一栏里写什么。**

国内 HR 首轮扫简历只有几秒，公司背景是最先被扫到的几样之一。大厂名字自带坐标；
不知名的公司，读的人看到的只是一串没有信息的字 —— 而「没有坐标」在快速筛选里
往往被当成「小、弱」。

实测活动用户 2026-08-23，`resume/main.typ` 的四段工作经历，`单位` 一栏
**四段全是「某某有限公司 · 上海」的形状** —— 名字加城市，没有别的。
而那四家没有一家是行业里叫得出名号的（其中两段还是同一家自有公司）。
每段的要点写得再实，读的人先看到的是那一行。

## 全仓扫过：这条规则不存在

`不知名` / `公司简介` / `时间连续` 在简历规则里 **0 命中**
（`公司简介` 的两处在抓取那一侧，说的是职位库的字段）。
`/job-resume` 的六项检查里也没有 —— 2.5「市场对得上吗」管的是 JD 关键词与
投后四格，不是这个。

## 没有顺手改「自有公司要不要点明」

那是**已经定过的**：活动用户的资料里对自有公司那一段已经给了披露口径，
照常写任职、不另行说明；要不要点明它是**面试口径**的事
（`07-interview-prep.md` 自我介绍那条 + 离职原因）。
这一条只管「读的人有没有坐标」，不碰披露口径。
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CV = (ROOT / "workflows" / "reference"
      / "05-cv-templates.md").read_text(encoding="utf-8")
JR = (ROOT / "workflows" / "job-resume.md").read_text(encoding="utf-8")
WS = (ROOT / "workflows" / "reference"
      / "03-writing-style.md").read_text(encoding="utf-8")


def rule() -> str:
    i = CV.index("### 公司名后面加不加一句：看行业内的人认不认得它")
    return CV[i:CV.index("### 期望年包写不写", i)]


class TheRuleExists(unittest.TestCase):
    def test_it_is_in_the_cv_reference(self):
        self.assertIn("### 公司名后面加不加一句：看行业内的人认不认得它", CV,
                      "简历规则里仍然没有一条管「单位」那一栏")

    def test_it_sits_in_the_structure_section(self):
        """它是结构规则。放到「已知陷阱」里没人会照着做。"""
        self.assertLess(CV.index("## 简历结构"),
                        CV.index("### 公司名后面加不加一句"))
        self.assertLess(CV.index("### 公司名后面加不加一句"),
                        CV.index("## 页数：按内容量定"))

    def test_the_criterion_is_recognisability_not_size(self):
        """判据是「认不认得」，不是「大不大」—— 小而有名的一样自带坐标。"""
        seg = " ".join(rule().split())
        self.assertRegex(seg, r"这家公司的名字，行业内的人一眼认得吗")

    def test_both_branches_are_given(self):
        rows = [ln for ln in rule().splitlines()
                if ln.strip().startswith("|") and "---" not in ln
                and "单位` 那一栏怎么写" not in ln]
        self.assertEqual(len(rows), 2, f"不是两行：{rows}")
        self.assertIn("只写名字 + 城市", rows[0])
        self.assertIn("行业 + 一个可核的规模数", rows[1])

    def test_the_known_branch_says_do_not_add(self):
        """两边都加等于没有判据，还白占一行。"""
        self.assertIn("再加解释是浪费一行", rule())

    def test_it_gives_concrete_shapes(self):
        """「加一句坐标」太虚，给三种真能照抄的形态。"""
        seg = rule()
        for ex in ("跨境电商，年 GMV", "SaaS，员工", "服务过"):
            with self.subTest(ex=ex):
                self.assertIn(ex, seg)

    def test_it_says_where_it_goes(self):
        """写成新段落就变成公司介绍了，那是另一回事。"""
        seg = " ".join(rule().split())
        self.assertIn("`entry` 的 `单位` 参数", seg)
        self.assertRegex(seg, r"跟在同一行\*\*，不另起段落")

    def test_it_refuses_made_up_numbers(self):
        """这一条最容易被执行成「随便编一句让它好看」。"""
        seg = " ".join(rule().split())
        self.assertRegex(seg, r"数要能核，编不出来就留空")
        self.assertIn("03-writing-style.md", seg, "没引那条既有铁律")

    def test_the_writing_rule_it_cites_exists(self):
        self.assertIn("不用没有证据支撑的评价词", WS)

    def test_it_says_who_it_matters_most_for(self):
        """一条规则不说清什么时候最要紧，就会被当成可有可无的润色。"""
        self.assertRegex(" ".join(rule().split()),
                         r"对「一家都不认得」的人最要紧")

    def test_the_template_can_carry_it(self):
        """规则要能落地：`entry` 的 `单位` 得是个自由字符串。"""
        tpl = (ROOT / "resume" / "template.typ").read_text(encoding="utf-8")
        self.assertRegex(tpl, r"#let entry\([^)]*单位: \"\"")


class TheAuditChecksIt(unittest.TestCase):
    """规则写了没有东西验它 —— 这个仓库点名过的一类缺陷。"""

    def _s23(self) -> str:
        i = JR.index("### 2.3 结构与页数")
        return JR[i:JR.index("### 2.4", i)]

    def test_the_check_is_there(self):
        self.assertIn("行业内的人认不认得", self._s23(),
                      "六项检查里仍然没有这一项")

    def test_it_points_at_the_rule(self):
        seg = self._s23()
        self.assertIn("05-cv-templates.md", seg)
        self.assertIn("公司名后面加不加一句", seg)

    def test_it_must_report_the_all_unknown_case(self):
        """一家都不认得、一条坐标都没有 —— 那正是最该报的情形。"""
        self.assertRegex(" ".join(self._s23().split()),
                         r"全是不认得的公司、一条坐标都没有时这一项必报")

    def test_it_says_why(self):
        self.assertRegex(" ".join(self._s23().split()),
                         r"HR 首轮几秒钟扫的就是这一栏")

    def test_it_does_not_ask_to_pad_known_companies(self):
        self.assertIn("认得的公司不要为了「统一」去加", self._s23())

    def test_the_existing_checks_survive(self):
        seg = self._s23()
        self.assertIn("章节顺序是否符合基线", seg)
        self.assertIn("typst compile", seg)
        self.assertIn("**不得**建议删掉诚实标注的缺口说明", seg)

    def test_it_sits_under_the_structure_check(self):
        """2.3 本来就是「对照 `05-cv-templates.md`」那一项 —— 挂在这儿才对。"""
        self.assertIn("对照 `05-cv-templates.md`", self._s23())


class TheDisclosureDecisionIsUntouched(unittest.TestCase):
    """自有公司在简历上怎么写，是**已经定过的**。这次不碰它。"""

    def test_the_rule_does_not_mention_disclosure(self):
        for w in ("自有公司", "披露", "离职原因"):
            with self.subTest(w=w):
                self.assertNotIn(w, rule(),
                                 f"这一条扯上了「{w}」—— 那是面试口径，不归它管")

    def test_the_interview_side_still_owns_it(self):
        prep = (ROOT / "workflows" / "reference"
                / "07-interview-prep.md").read_text(encoding="utf-8")
        self.assertIn("自有公司/自由职业/非科班/空窗期", prep)


if __name__ == "__main__":
    unittest.main()
