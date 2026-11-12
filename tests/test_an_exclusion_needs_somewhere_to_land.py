# -*- coding: utf-8 -*-
"""「英语口语不行」是事实，「要求英语面试的岗不投」是结论 —— 模板只给了事实一个位置。

`04-job-evaluation.md` 的硬门表原来写着：这道门判的是「JD 命中
`profile/candidate.md`「明确排除」**一节**里列出的任何一条」。

而实测活动用户 2026-08-24，把 110 条写清了理由的排除按理由分一分：

    29 条（26%）  英语口语 / 英语流利 / 英语面试 / 英文母语水平
     1 条         年龄超出上限
    ~46 条        行业背景硬要求、职能背景硬要求（这些确实在「明确排除」一节里）
     其余         营销职能、生物医药 等，同样在那一节

**那 29 条引的东西根本不在「明确排除」一节里** —— 它写在身份栏的「语言」那一行。
执行时之所以判对了，是因为本人后来自己在那条后面补了一句「按硬门处理」。

## 照模板填，那句话不会长出来

`profile.example/candidate.md` 的「语言」那行只收**事实**（「附熟练度，如……
无法口语沟通」），`## 明确排除` 只有两行占位符；`/job-setup` Section 1 也只问
「会哪些语言（各到什么水平）」。**事实有地方写，结论没有。** 换一个人照这份
问卷填完，要求英语面试的岗照样满分排进「值得投」—— 而他早在第一轮就说过口语不行。

这不是英语独有：不会粤语的护士投广州、不能出差的顾问、不接受大小周的开发，
形状完全一样 —— 一句能力/偏好的事实，缺一个「所以这类岗不投」的落点。

## 三处一起改

- **模板**：`## 明确排除` 写明是这类结论的**唯一落点**，并给出「写成什么样的岗
  不投、别写成我不会什么」的正反例；「语言」那行加一句指过去。
- **问卷**：Section 1 的语言题追问一句「这类岗要不要直接不投」，答「不投」落进
  `## 明确排除`，答「看情况」落进 `## 求职偏好` 按减分处理。
- **判据**：04 那道门读的是「凡写了按硬门处理的」，不是「凡在那一节的」——
  存量资料还是散的，收紧字面会把那 29 条判丢。
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TPL = (ROOT / "profile.example" / "candidate.md").read_text(encoding="utf-8")
EVAL = (ROOT / "workflows" / "reference"
        / "04-job-evaluation.md").read_text(encoding="utf-8")
SETUP = (ROOT / "workflows" / "job-setup.md").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*>\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


class TheTemplateGivesTheConclusionAHome(unittest.TestCase):
    def _seg(self) -> str:
        # 锚在行首那个标题上 —— 「## 明确排除」这五个字在上面的注释里
        # 也出现过（那正是这次加的指路），按裸串取会取到那一处。
        i = TPL.index(chr(10) + "## 明确排除" + chr(10))
        return flat(TPL[i:i + 1400])

    def test_it_says_this_is_the_only_landing_place(self):
        self.assertRegex(self._seg(), r"\*\*唯一落点\*\*")

    def test_it_separates_fact_from_conclusion(self):
        """两者要分开写 —— 事实换个岗位可能只是减分，结论是一票否决。"""
        seg = self._seg()
        self.assertRegex(seg, r"前面那些节写的是事实")
        self.assertRegex(seg, r"这一节写的是\*\*结论\*\*：命中即 FAIL")

    def test_it_shows_the_right_and_wrong_shape(self):
        """只说「写结论」不够 —— 得给一对正反例，否则照样写成「我不会什么」。"""
        seg = self._seg()
        self.assertIn("要求英语面试、英语口语沟通或日常英文会议的岗", seg)
        self.assertRegex(seg, r"❌ 英语口语不行")
        self.assertRegex(seg, r"这是事实，写在上面「语言」那行")

    def test_it_asks_for_the_parenthesis(self):
        """门名括号里那几个字是这道门唯一有用的信息。"""
        self.assertIn("候选人明确排除（英语口语沟通）", self._seg())

    def test_it_says_this_gate_is_the_one_he_can_change(self):
        seg = self._seg()
        self.assertRegex(seg, r"唯一你自己能改的")
        self.assertIn("/job-rank --all", seg)


class TheLanguageLinePointsAtIt(unittest.TestCase):
    def _seg(self) -> str:
        i = TPL.index("- **语言：**")
        return flat(TPL[i:i + 900])

    def test_it_says_this_line_is_facts_only(self):
        self.assertRegex(self._seg(), r"这一行只写\*\*事实\*\*")

    def test_it_routes_the_conclusion_to_the_right_section(self):
        seg = self._seg()
        self.assertIn("「## 明确排除」", seg)
        self.assertRegex(seg, r"硬门读的是那一节，不是这一行")

    def test_it_records_what_happens_without_the_pointer(self):
        """不写代价，下一个人会把这段注释当啰嗦删掉。"""
        seg = self._seg()
        self.assertRegex(seg, r"事实写在这儿，后果无处可写，那道门就永远不响")

    def test_it_carries_the_measurement(self):
        seg = self._seg()
        self.assertIn("2026-08-24", seg)
        self.assertRegex(seg, r"29 条（26%）")


class TheQuestionnaireAsksTheFollowUp(unittest.TestCase):
    def _seg(self) -> str:
        i = SETUP.index("- 会哪些语言（各到什么水平）")
        return flat(SETUP[i:i + 900])

    def test_it_asks_whether_to_exclude(self):
        self.assertRegex(self._seg(), r"这类岗要不要直接不投")

    def test_it_names_the_trigger(self):
        """不给触发条件，执行者要么每次都问、要么一次都不问。"""
        self.assertRegex(self._seg(), r"「不行 / 只能读写 / 不会说」")

    def test_both_answers_have_a_destination(self):
        seg = self._seg()
        self.assertRegex(seg, r"答「不投」→ 按 Section 7 的写法落进 `## 明确排除`")
        self.assertRegex(seg, r"答「看情况」→ 不写排除，记进 `## 求职偏好`")

    def test_it_says_how_to_word_it(self):
        seg = self._seg()
        self.assertRegex(seg, r"写成\*\*什么样的岗不投\*\*")
        self.assertRegex(seg, r"不要写成「英语口语不行」")

    def test_it_states_the_cost_of_skipping_it(self):
        seg = self._seg()
        self.assertRegex(seg, r"要求英语面试的岗照样满分排进「值得投」")


class TheGateReadsWiderThanOneSection(unittest.TestCase):
    """存量资料是散的 —— 判据收紧到「那一节」会把 26% 判丢。"""

    def _seg(self) -> str:
        i = EVAL.index("### 「明确排除」：他自己说了不要的")
        return flat(EVAL[i:i + 2200])

    def test_the_table_row_no_longer_says_one_section_only(self):
        row = next(l for l in EVAL.splitlines() if l.startswith("| **候选人自己划的排除项**"))
        self.assertIn("任何", row)
        self.assertNotIn("「明确排除」一节里列出的任何一条", row,
                         "又收回「只读那一节」了 —— 写在语言/能力边界那几节的会判丢")

    def test_the_section_says_do_not_read_only_that_section(self):
        seg = self._seg()
        self.assertRegex(seg, r"\*\*但别只读那一节。\*\*")
        self.assertRegex(seg, r"任何\*\*写着「按硬门处理」「这类岗不投」的条目")

    def test_it_names_where_else_they_live(self):
        self.assertRegex(self._seg(), r"语言、明确的能力边界、补充确认")

    def test_it_carries_the_measurement(self):
        seg = self._seg()
        self.assertIn("语言", seg)
        self.assertRegex(seg, r"英语口语.*按硬门处理|按硬门处理")

    def test_it_explains_why_the_literal_reading_still_worked(self):
        """不解释这个，读的人会以为规则本来就没问题。"""
        self.assertRegex(self._seg(), r"照这里的字面读反而会漏掉它")

    def test_it_says_the_template_already_fixed_the_new_case(self):
        seg = self._seg()
        self.assertRegex(seg, r"新用户照模板填不会再散")
        self.assertRegex(seg, r"\*\*存量资料还是散的\*\*")

    def test_the_reason_must_name_its_section(self):
        """出处不同意味着能不能改不同 —— 这才是写出处的用处。"""
        seg = self._seg()
        self.assertRegex(seg, r"还要写清是资料哪一节说的")
        self.assertRegex(seg, r"「能力边界」里的一条得先真的补上那个能力")


class TheOlderRulesAreIntact(unittest.TestCase):
    """这道门原有的三条不能被这次改动挤掉。"""

    def test_the_parenthesis_rule_survives(self):
        self.assertIn("命中时必须写清是哪一条排除，不能只写「明确排除」四个字", EVAL)

    def test_the_evidence_bar_survives(self):
        self.assertRegex(flat(EVAL), r"JD 正文能确认命中才 FAIL；只是「看着像」→ FLAG")

    def test_the_boilerplate_escape_survives(self):
        """纯中文岗末尾挂一句「英语六级以上」—— 那是套话，不是要求。"""
        self.assertRegex(flat(EVAL), r"命中处疑似模板话时，「拿不准」那档赢")

    def test_the_seven_gates_are_still_seven(self):
        import sys
        sys.path.insert(0, str(ROOT / "tools"))
        import _cli
        self.assertEqual(len(_cli.GATES), 7)
        self.assertIn("候选人明确排除", _cli.GATES)

    def test_no_eighth_gate_was_invented_for_language(self):
        """英语不是第八道门 —— 它要么是他自己的排除，要么是打分维度。"""
        import sys
        sys.path.insert(0, str(ROOT / "tools"))
        import _cli
        for bad in ("英语", "语言", "年龄"):
            self.assertNotIn(bad, _cli.GATES)
            self.assertEqual(_cli.gate_of(bad), "",
                             f"「{bad}」被认成正规门名了 —— 04 说过不要新起一道门")


class TheTemplateStaysTheOneSourceOfSectionNames(unittest.TestCase):
    """AGENTS.md：往 candidate.md 里写东西，小节名一律以模板为准。"""

    def test_the_sections_this_change_names_all_exist(self):
        for sec in ("## 明确排除", "## 求职偏好", "- **语言：**"):
            self.assertIn(sec, TPL, f"模板里没有 {sec} —— 引导会把数据写去无处")

    def test_setup_still_maps_section_7_to_it(self):
        self.assertRegex(SETUP, r"Section 7 .*`## 明确排除`")


if __name__ == "__main__":
    unittest.main()
