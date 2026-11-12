# -*- coding: utf-8 -*-
"""开场白里**对公司下了断言**，就必须记下它的出处。

`03-writing-style.md` 铁律 1 是「绝不编造」，而一条没有出处的公司主张
**没有任何办法验证** —— 审稿者验不了，用户两周后自己也想不起来是从哪看的。

## 这条检查的范围是量出来的

第一版查的是「『本次使用的公司事实』那一节空不空」，报 228/236。
那个数**大部分是假阳性**：236 份开场白里，对公司下断言的只有 28 份（11%），
另外 89% 讲的全是他自己的经历怎么对上这个岗 —— 那些主张的出处在
`profile/candidate.md`，不在这一节里，**空着是对的**。

## 顺手证伪的一件事

更要紧的怀疑是「这 236 份开场白是不是都长一个样」（那能直接解释 0/85）。
两两 4-gram Jaccard 相似度**中位 0.06、最高 0.49、超过 0.5 的配对为零**。
它们确实是逐岗写的；共享的片段全是他自己的战绩（「10万+注册用户」），
不是模板套话。**所以不许对用户说「你的开场白发给谁都成立」——那不是真的。**

规则也要跟着窄：`06` 原来那句「这一节不许空着」对 89% 的文件是错的要求。
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import audit_pipeline as A  # noqa: E402

TPL = (ROOT / "workflows" / "reference"
       / "06-outreach-templates.md").read_text(encoding="utf-8")


class TheRuleBranchesByWhoIsReading(unittest.TestCase):
    def test_the_anonymous_case_has_its_own_row(self):
        """公司名隐去时没有公司事实可引 —— 得说清改引什么（58% 的岗是这样）。"""
        self.assertIn("公司名隐去", TPL, "规则没管公司名隐去的岗")
        self.assertRegex(TPL, r"JD 里的一条具体东西|引 JD", "没说清匿名岗改引什么")

    def test_the_headhunter_case_is_called_out(self):
        """对面是顾问不是用人方 —— 讲「贵司」是讲错了人。"""
        seg = TPL[TPL.index("只对这个岗成立的具体东西"):][:1600]
        self.assertIn("猎头代招", seg, "没说猎头代招那一档引什么")

    def test_verification_is_not_relaxed_for_the_named_case(self):
        seg = TPL[TPL.index("只对这个岗成立的具体东西"):][:2400]
        self.assertIn("绝不能抓职位描述正文里的 URL", seg, "核实那一层被顺手放松了")

    def test_the_requirement_is_scoped_to_claims(self):
        """要求份份填等于制造噪音 —— 只有下了断言的才必须填。"""
        self.assertRegex(TPL, r"对公司下了断言.{0,12}才必须填|凡是对公司下了断言",
                         "那一节的要求还是无条件的")
        self.assertRegex(TPL, r"留空是对的", "没说清什么时候留空是对的")

    def test_the_disproved_hypothesis_is_recorded(self):
        """证伪过的怀疑要写下来，确保每份开场白独立针对目标岗位撰写。"""
        self.assertRegex(TPL, r"发给谁都成立|不是模板套话|逐岗写")


class TheAuditOnlyFlagsClaims(unittest.TestCase):
    @staticmethod
    def _run(bodies):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            apps = root / "users" / "张三" / "documents" / "applications"
            for i, b in enumerate(bodies):
                d = apps / f"公司{i}_岗位"
                d.mkdir(parents=True)
                (d / "outreach.md").write_text(b, encoding="utf-8")
            (root / ".active_user").write_text("张三", encoding="utf-8")
            saved = A.ROOT
            try:
                A.ROOT = root
                return A.check_company_claims_have_a_source({}, {})
            finally:
                A.ROOT = saved

    # 长度要过 `_greeting_of` 那道 40 字下限——真实开场白 85-232 字。
    # 夹具短于下限的话这条测试会静默地什么都不测（第一版正好 39 字，栽了一次）。
    CLAIM = ("## 打招呼开场白\n\n"
             "看到贵司刚发布了新一代智能体平台，我做过同类的事：把大模型接进"
             "内部业务系统，落了三条线，其中一条现在每天两千多次调用。"
             "想问下这个岗现在落在哪几个场景。\n")
    OWN = ("## 打招呼开场白\n\n"
           "我做 AI 产品三年，把大模型接进内部业务系统落了三条线，"
           "其中一条现在每天两千多次调用，和这个岗写的智能体落地场景对得上。"
           "想问下这边现在做到哪一步了。\n")
    SOURCED = CLAIM + "\n## 本次使用的公司事实\n\n- 官网发布页写着 X —— 来源：https://x\n"
    PLACEHOLDER = CLAIM + "\n## 本次使用的公司事实\n\n- <已核实的事实> —— 来源：<URL>\n"

    def test_a_claim_without_a_source_is_flagged(self):
        self.assertTrue(self._run([self.CLAIM]), "有主张没出处却没报")

    def test_a_greeting_about_yourself_is_not_flagged(self):
        """89% 是这种。报它们等于制造噪音，然后这条检查就没人看了。"""
        self.assertEqual(self._run([self.OWN]), [], "把只讲自己经历的也报了")

    def test_a_sourced_claim_passes(self):
        self.assertEqual(self._run([self.SOURCED]), [])

    def test_the_skeleton_placeholder_does_not_count_as_a_source(self):
        """骨架里那行 `<…>` 占位说明不是内容 —— 认它等于这条检查永远绿。"""
        self.assertTrue(self._run([self.PLACEHOLDER]), "占位行被当成了真出处")

    def test_it_is_registered(self):
        self.assertTrue(
            any(getattr(fn, "__name__", "") == "check_company_claims_have_a_source"
                for _, fn in A.CHECKS), "新检查没进 CHECKS")


if __name__ == "__main__":
    unittest.main()
