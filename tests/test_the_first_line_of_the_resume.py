# -*- coding: utf-8 -*-
"""简历「个人优势」第一条只是自我描述，没指向任何能核验的东西。

姓名与目标岗位那一行之后，**第一个被读到的句子就是「个人优势」第一条** ——
国内 HR 扫简历以秒计，这是整份简历第二贵的位置。

`05-cv-templates.md` 把「个人优势」定为唯一按岗微调的段落、也允许「调整排序」，
但从没说过第一条该放什么；`job-resume.md` 的六项检查查章节顺序、查措辞、
查市场词，唯独不查它。

## 判据被自己的数据推翻过一次 —— 那一次要记下来

第一版判据是「第一条里要有数字」。实测活动用户 2026-08-25，13 份简历：

    指向作品名或成绩数   8 份   ← 第一条是作品名那一类（没有数字）
    纯自我描述          3 份
    **只有工龄**        2 份   ← 第一条是「N 年某行业转型 AI 产品」那一类（有数字）

**带数字的那两份恰恰是最弱的**，没数字的那条反而最硬。「十年」证明的是
**转过岗**，而那正是读的人会拿来减分的东西 —— 把它举到第一句，
等于自己先说了那个减分项。

判据因此换成：**指不指得到一件对方能自己点开的东西**（作品名或成绩数）。

## 作品名从资料里现抽，不硬编码

本仓库行业无关（`AGENTS.md`）。硬编码某一个作品名，换个用户整条失效。
"""
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import audit_pipeline as ap  # noqa: E402

TPL = (ROOT / "workflows" / "reference"
       / "05-cv-templates.md").read_text(encoding="utf-8")
RESUME = (ROOT / "workflows" / "job-resume.md").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*(?:>|#:?)\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


class TheJudgeIsAboutEvidenceNotDigits(unittest.TestCase):
    """**这条判据的全部要害**：工龄是数字，却不是证据。"""

    def _run(self, tmp, first, profile="Notewell（1.2K stars）\nSome Open Toolkit\n"):
        base = tmp / "users" / "_t_cv"
        (base / "profile").mkdir(parents=True, exist_ok=True)
        (base / "profile" / "candidate.md").write_text(
            "## 作品与项目的分层\n" + profile, encoding="utf-8")
        (base / "resume").mkdir(parents=True, exist_ok=True)
        (base / "resume" / "main.typ").write_text(
            '#section("个人优势")\n- ' + first + "\n- 第二条\n", encoding="utf-8")
        old_root, old_user = ap.ROOT, list(ap._USER)
        try:
            ap.ROOT = tmp
            ap._USER[:] = ["_t_cv"]
            return ap.check_the_lead_advantage_points_at_something({}, {})
        finally:
            ap.ROOT = old_root
            ap._USER[:] = old_user

    def setUp(self):
        import tempfile
        self.tmp = pathlib.Path(tempfile.mkdtemp())

    def test_a_work_name_passes(self):
        self.assertEqual(self._run(self.tmp, "开源多组 Some Open Toolkit，重度使用 AI 编码工具"), [])

    def test_a_metric_passes(self):
        self.assertEqual(self._run(self.tmp, "自研工具做到 5 万+ 注册用户"), [])

    def test_stars_pass(self):
        self.assertEqual(self._run(self.tmp, "全部开源作品累计 1 万+ stars"), [])

    def test_pure_self_description_is_caught(self):
        got = self._run(self.tmp, "独立开发者：从场景识别、方案设计到上线维护，产品全程一人跑通")
        self.assertEqual(len(got), 1)
        self.assertIn("只是自我描述", got[0][1])

    def test_tenure_alone_is_caught(self):
        """**判据的要害。** 「十年」是数字，不是证据 —— 第一版判据在这儿栽过。"""
        got = self._run(self.tmp, "十年品牌市场与 BD（带过团队、做过 0→1 品牌）转型 AI 产品")
        self.assertEqual(len(got), 1, "带「十年」就算过关的话，这条判据等于没有")

    def test_arabic_tenure_is_caught_too(self):
        """**「10 年」和「十年」是同一件事。**

        变异检验逮到：只测「十年」时，把「年」加进成绩正则那个变异活了下来 ——
        因为中文数字本来就不匹配 `\\d`。而这位用户的另一份简历写的正是
        「10 年品牌市场与 BD……转型 AI 产品」，带阿拉伯数字。
        """
        got = self._run(self.tmp, "业务 × AI 双栖：10 年品牌市场与 BD 转型 AI 产品")
        self.assertEqual(len(got), 1, "「10 年」被当成成绩数了 —— 工龄不是证据")

    def test_a_spec_word_inside_parentheses_is_not_a_work_name(self):
        """括号里那串是规格说明，不是作品名。

        「Hotkey Chain（75+ 动作、可视化编辑器、18 语言）、Clockwork」——
        先按顿号切再剥括号的话，「可视化编辑器」会变成一个「作品名」，
        于是一句什么都没指的话就能蒙混过关（变异检验逮到）。
        """
        got = self._run(
            self.tmp, "做过可视化编辑器，全程一人跑通",
            profile="| 线 | 起始 | 项目 | 只能主张 |\n|---|---|---|---|\n"
                    "| 有设计深度 | 2025 | 某某链条（75+ 动作、可视化编辑器、18 语言）、"
                    "某某钟表 | 系统设计能力 |\n")
        self.assertEqual(len(got), 1,
                         "括号里的规格词被当成作品名了 —— 那一格会漏放一大批")

    def test_the_real_work_names_in_that_row_still_pass(self):
        """对照：同一行里真正的作品名要认得，别剥过头。"""
        got = self._run(
            self.tmp, "开源了某某链条，社区在用",
            profile="| 线 | 起始 | 项目 | 只能主张 |\n|---|---|---|---|\n"
                    "| 有设计深度 | 2025 | 某某链条（75+ 动作、可视化编辑器、18 语言）、"
                    "某某钟表 | 系统设计能力 |\n")
        self.assertEqual(got, [])

    def test_tenure_plus_a_work_name_passes(self):
        """工龄本身不是罪 —— 只要那一句同时指得到东西。"""
        self.assertEqual(
            self._run(self.tmp, "十年品牌市场转型 AI 产品，代表作 Notewell"), [])

    def test_the_names_come_from_the_profile(self):
        """**不硬编码，而且中文名也要认。**

        这是个做中文求职的工具，中文产品名是常态不是例外。第一版只扫拉丁大写词，
        「某某工具箱」整个抽不到 —— 判据当场把一份合格的简历判成不合格。
        """
        got = self._run(
            self.tmp, "开源了某某工具箱，社区在用",
            profile="| 线 | 起始 | 项目 | 只能主张 |\n|---|---|---|---|\n"
                    "| 独立开源产品 | 2023 | 某某工具箱、另一个盒子 | 产品成绩 |\n")
        self.assertEqual(got, [], "资料里写了的作品名，判据要认得")

    def test_a_name_not_in_the_profile_does_not_pass(self):
        """简历里随便写个拉丁词不该蒙混过关 —— 判据只认资料里有的。"""
        got = self._run(self.tmp, "精通 Kubernetes 与 Terraform，全程一人跑通",
                        profile="Notewell（1.2K stars）\n")
        self.assertEqual(len(got), 1)

    def test_no_profile_is_silent(self):
        """资料都没有就别评判 —— 那是 /job-setup 的事。"""
        import tempfile
        tmp = pathlib.Path(tempfile.mkdtemp())
        base = tmp / "users" / "_t_cv" / "resume"
        base.mkdir(parents=True)
        (base / "main.typ").write_text('#section("个人优势")\n- 自我描述一句\n',
                                       encoding="utf-8")
        old_root, old_user = ap.ROOT, list(ap._USER)
        try:
            ap.ROOT = tmp
            ap._USER[:] = ["_t_cv"]
            got = ap.check_the_lead_advantage_points_at_something({}, {})
        finally:
            ap.ROOT = old_root
            ap._USER[:] = old_user
        self.assertEqual(len(got), 1, "没资料时判据退化成「都不过」是可以的，"
                                      "但不许崩")

    def test_a_resume_without_the_section_is_skipped(self):
        import tempfile
        tmp = pathlib.Path(tempfile.mkdtemp())
        base = tmp / "users" / "_t_cv"
        (base / "profile").mkdir(parents=True)
        (base / "profile" / "candidate.md").write_text("Notewell\n", encoding="utf-8")
        (base / "resume").mkdir(parents=True)
        (base / "resume" / "main.typ").write_text("#section(\"技能\")\n- 一条\n",
                                                  encoding="utf-8")
        old_root, old_user = ap.ROOT, list(ap._USER)
        try:
            ap.ROOT = tmp
            ap._USER[:] = ["_t_cv"]
            self.assertEqual(ap.check_the_lead_advantage_points_at_something({}, {}), [])
        finally:
            ap.ROOT = old_root
            ap._USER[:] = old_user

    def test_the_template_itself_is_not_judged(self):
        """`template.typ` 是骨架，里面的「第一条」是占位符。"""
        base = self.tmp / "users" / "_t_cv"
        (base / "profile").mkdir(parents=True, exist_ok=True)
        (base / "profile" / "candidate.md").write_text("Notewell\n", encoding="utf-8")
        (base / "resume").mkdir(parents=True, exist_ok=True)
        (base / "resume" / "template.typ").write_text(
            '#section("个人优势")\n- 第一条\n', encoding="utf-8")
        old_root, old_user = ap.ROOT, list(ap._USER)
        try:
            ap.ROOT = self.tmp
            ap._USER[:] = ["_t_cv"]
            self.assertEqual(ap.check_the_lead_advantage_points_at_something({}, {}), [])
        finally:
            ap.ROOT = old_root
            ap._USER[:] = old_user

    def test_no_active_user_is_silent(self):
        old = list(ap._USER)
        try:
            ap._USER[:] = []
            self.assertEqual(ap.check_the_lead_advantage_points_at_something({}, {}), [])
        finally:
            ap._USER[:] = old

    def test_it_is_registered(self):
        self.assertIn(ap.check_the_lead_advantage_points_at_something,
                      [f for _n, f in ap.CHECKS])

    def test_the_message_says_tenure_does_not_count(self):
        """不说这一句，读的人会拿「十年」去顶。"""
        got = self._run(self.tmp, "独立开发者，全程一人跑通")
        self.assertIn("工龄不算", got[0][2])

    def test_the_message_gives_a_command(self):
        got = self._run(self.tmp, "独立开发者，全程一人跑通")
        self.assertIn("/job-resume", got[0][2])

    def test_the_overturned_first_judge_is_recorded(self):
        """**判据被自己的数据推翻过** —— 不写下来，下一个人会再写一次「有没有数字」。"""
        doc = flat(ap.check_the_lead_advantage_points_at_something.__doc__ or "")
        self.assertIn("工龄", doc)
        self.assertIn("2026-08-25", doc)
        src = (ROOT / "tools" / "audit_pipeline.py").read_text(encoding="utf-8")
        i = src.index("_LEAD_METRIC = ")
        seg = flat(src[max(0, i - 700):i])
        self.assertIn("带数字的那两份恰恰是最弱的", seg)


class TheSpecSaysIt(unittest.TestCase):

    def test_the_section_exists(self):
        self.assertIn("### 「个人优势」第一条：要指得到一件对方能自己点开的东西", TPL)

    def test_it_says_why_that_line_is_expensive(self):
        i = TPL.index("### 「个人优势」第一条")
        seg = flat(TPL[i:i + 1800])
        self.assertIn("整份简历第二贵的位置", seg)

    def test_it_warns_that_tenure_backfires(self):
        i = TPL.index("### 「个人优势」第一条")
        seg = flat(TPL[i:i + 1800])
        self.assertIn("它证明的是**转过岗**".replace("**", ""), seg.replace("**", ""))

    def test_it_records_the_overturned_judge(self):
        i = TPL.index("### 「个人优势」第一条")
        seg = flat(TPL[i:i + 2200])
        self.assertIn("判据当场被自己的数据推翻", seg)
        self.assertIn("13 份简历", seg)

    def test_it_names_the_mechanical_check(self):
        i = TPL.index("### 「个人优势」第一条")
        seg = TPL[i:i + 2200]
        self.assertIn("check_the_lead_advantage_points_at_something", seg)

    def test_it_says_names_are_not_hardcoded(self):
        i = TPL.index("### 「个人优势」第一条")
        seg = flat(TPL[i:i + 2200])
        self.assertIn("不硬编码", seg)

    def test_it_does_not_claim_to_judge_ordering(self):
        """排序按什么排是判断不是机械题 —— 这一条别越界。"""
        i = TPL.index("### 「个人优势」第一条")
        seg = flat(TPL[i:i + 2400])
        self.assertIn("这一条不管排序该按什么排", seg)

    def test_the_section_order_rule_survives(self):
        """别把隔壁那条「章节顺序定一次」挤掉了。"""
        self.assertIn("### 章节顺序按行业定**一次**，之后不再动", TPL)

    def test_the_audit_step_asks_for_it(self):
        self.assertIn("「个人优势」第一条指不指得到一件对方能自己点开的东西", RESUME)


if __name__ == "__main__":
    unittest.main()
