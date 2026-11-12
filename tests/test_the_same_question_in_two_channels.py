# -*- coding: utf-8 -*-
"""「你最大的优势是什么」在国内会被问两遍 —— 判据不能只管一遍。

一遍在简历上（他自己写的「个人优势」第一条），一遍在聊天框里（HR 直接打字问，
答案是 `profile/hr-answers.md` 里定过稿的那条）。**同一批人，同一天，两处都看。**

那份文件开头写着它存在的全部理由：「同一个问题在打招呼、HR 初面、背调三处说法
对不上，是面试官最容易抓的点」。而判据此前只扫简历。

实测活动用户 2026-08-25：简历第一条刚改成指向作品与 stars，聊天框那条的第一小句
还是「复合型背景、既懂业务又懂技术」—— 复合型人才那句套话，
成绩数全排在破折号后面。
"""
from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
ap = importlib.import_module("audit_pipeline")

PROFILE_TABLE = (
    "## 作品与项目的分层\n\n"
    "| 线 | 起始 | 项目 | 只能主张 |\n|---|---|---|---|\n"
    "| 独立开源产品 | 2023 | 某某工具箱、另一个盒子 | 产品成绩 |\n"
)


class TheChatBoxAnswerIsJudgedToo(unittest.TestCase):

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.addCleanup(self._td.cleanup)

    def _run(self, pitch: str | None, *, resume_first: str = "开源了某某工具箱",
             profile: str = PROFILE_TABLE) -> list:
        user = "_t_two"
        base = self.tmp / "users" / user
        (base / "profile").mkdir(parents=True, exist_ok=True)
        (base / "profile" / "candidate.md").write_text(profile, encoding="utf-8")
        if pitch is not None:
            (base / "profile" / "hr-answers.md").write_text(
                "# x\n\n## 看机会的原因是什么\n\n因为想换。\n\n"
                "## 你最大的优势是什么\n\n" + pitch + "\n\n"
                "## 什么时候能到岗\n\n随时。\n", encoding="utf-8")
        (base / "resume").mkdir(parents=True, exist_ok=True)
        (base / "resume" / "main.typ").write_text(
            '#section("个人优势")\n- ' + resume_first + "\n- 第二条\n",
            encoding="utf-8")
        old_root, old_user = ap.ROOT, list(ap._USER)
        try:
            ap.ROOT = self.tmp
            ap._USER[:] = [user]
            return ap.check_the_lead_advantage_points_at_something({}, {})
        finally:
            ap.ROOT, ap._USER[:] = old_root, old_user

    # ---------- 判据本身 ----------

    def test_the_cliche_is_caught(self):
        """**这就是那句。** 复合型人才那套话，成绩数全在破折号后面。"""
        got = self._run("「复合型背景、既懂业务又懂技术」——"
                        "开源项目累计 3 千+ stars、2 万+ 注册用户。")
        self.assertEqual(len(got), 1)
        self.assertIn("聊天框", got[0][1])
        self.assertIn("复合型背景", got[0][2])

    def test_the_metric_up_front_passes(self):
        """成绩数提到破折号前面就过。"""
        self.assertEqual(
            self._run("开源作品累计 1 万+ stars，做出来的东西别人能装下来用——"
                      "前面十年品牌市场的底子用在让工具真被用起来这一环。"), [])

    def test_a_work_name_up_front_passes(self):
        self.assertEqual(self._run("某某工具箱是我做的，社区里有人在用。"), [])

    def test_tenure_up_front_is_still_not_evidence(self):
        """**工龄那条对两个渠道一样成立。**

        「10 年某某经验转型 AI」在聊天框里同样什么都不证明 —— 它证明的是转过岗，
        而那正是对方会拿来减分的东西。
        """
        got = self._run("10 年品牌市场转型 AI 产品——开源作品累计 1 万+ stars。")
        self.assertEqual(len(got), 1)
        self.assertIn("聊天框", got[0][1])

    # ---------- 切「第一小句」 ----------

    def test_it_cuts_at_the_dash(self):
        self.assertEqual(
            ap._chat_pitch_of("甲乙丙丁——某某工具箱"), "甲乙丙丁",
            "破折号后面那半不算 —— HR 在聊天框里先读到的是前面那半")

    def test_it_cuts_at_a_full_stop(self):
        self.assertEqual(ap._chat_pitch_of("甲乙丙丁。某某工具箱"), "甲乙丙丁")

    def test_the_quotes_come_off(self):
        """他习惯给总括那句加书名号／引号，别把引号算进内容。"""
        self.assertEqual(ap._chat_pitch_of("「甲乙丙丁」——某某工具箱"), "甲乙丙丁")

    def test_comments_are_not_the_answer(self):
        """那份文件里到处是 `<!-- -->` 说明。**别把说明当成他的答案。**

        这个仓库栽过三次「注释满足断言」——判据被它自己的说明喂饱了。
        """
        got = self._run("<!-- 这里要写作品名，比如某某工具箱 -->\n\n"
                        "比纯技术更懂业务、比业务更懂技术。")
        self.assertEqual(len(got), 1, "说明里的作品名被当成答案了")

    # ---------- 不判的情形 ----------

    def test_no_file_is_not_a_finding(self):
        """还没定稿就不是问题 —— 那是 `/job-interview` 那一条在管的事。"""
        self.assertEqual(self._run(None), [])

    def test_a_placeholder_is_not_a_finding(self):
        """模板发的 `[YOUR_PITCH]` 不是他写的话，别报。"""
        self.assertEqual(self._run("[YOUR_PITCH]"), [])

    def test_no_advantage_section_at_all(self):
        user = "_t_two"
        base = self.tmp / "users" / user
        (base / "profile").mkdir(parents=True, exist_ok=True)
        (base / "profile" / "hr-answers.md").write_text(
            "# x\n\n## 什么时候能到岗\n\n随时。\n", encoding="utf-8")
        old_root, old_user = ap.ROOT, list(ap._USER)
        try:
            ap.ROOT, ap._USER[:] = self.tmp, [user]
            self.assertEqual(ap._chat_pitch(user), "")
        finally:
            ap.ROOT, ap._USER[:] = old_root, old_user

    # ---------- 两个渠道各报各的 ----------

    def test_each_channel_gets_its_own_command(self):
        """**一条引导对应一条命令**（`AGENTS.md`）。

        两处都坏时要出两条消息、各带各的命令 —— 合成一条就得在一句话里给两条
        命令，那正是那条规矩要省掉的选择。
        """
        got = self._run("比纯技术更懂业务、比业务更懂技术。",
                        resume_first="独立开发者，全程一人跑通")
        self.assertEqual(len(got), 2, "两个渠道都坏，要各报一条")
        cmds = [m.rsplit("跑 ", 1)[-1].split("，")[0].split("。")[0] for _, _, m in got]
        self.assertEqual(sorted(set(cmds)), ["/job-dashboard", "/job-resume"])
        # **标题也要数进去。** 用户读到的是「标题 + 正文」，把第二条命令塞进标题
        # 一样是在一句引导里给两条命令 —— 只数正文时那个变异活了下来（实测）。
        for _, title, m in got:
            self.assertEqual((title + m).count("/job-"), 1,
                             f"一条引导里给了不止一条命令：{title} / {m}")

    def test_the_names_come_from_the_profile_here_too(self):
        """**不硬编码。** 聊天框那半用的是同一份作品名，换个用户跟着走。"""
        # **简历那半也要跟着换。** 只换聊天框那句的话，简历第一条还指着旧作品名，
        # 于是简历那条警告先响了 —— 测的就不是这件事了（第一版栽在这儿）。
        self.assertEqual(
            self._run("盒中盒是我做的，社区里有人在用。",
                      resume_first="开源了盒中盒",
                      profile=PROFILE_TABLE.replace("某某工具箱、另一个盒子", "盒中盒")),
            [])
        got = self._run("盒中盒是我做的，社区里有人在用。")
        self.assertEqual(len(got), 1, "资料里没这个作品，却还是放过了")


class TheSpecSaysItCoversBothChannels(unittest.TestCase):
    """正本要写清它管两个渠道 —— 否则下一个人只按简历那半理解它。"""

    def test_the_spec_names_the_second_channel(self):
        t = (ROOT / "workflows" / "reference" / "05-cv-templates.md").read_text(
            encoding="utf-8")
        i = t.index("「个人优势」第一条")
        seg = t[i:t.index("\n### ", i + 10)]
        self.assertIn("hr-answers.md", seg, "正本没提聊天框那一份")
        # 同上的坑：`两处` 在下一段「两处的第一句要指向同一件事」里还有一份。
        # 这里钉的是**说清范围**的那两句本身。
        self.assertIn("不只管简历", seg, "正本没写清这一条也管聊天框")
        self.assertIn("被问两遍", seg, "正本没写清同一个问题会被问两遍")

    def test_the_docstring_names_it_too(self):
        src = (ROOT / "tools" / "audit_pipeline.py").read_text(encoding="utf-8")
        i = src.index("def check_the_lead_advantage_points_at_something(")
        doc = src[i:src.index('"""', src.index('"""', i) + 3)]
        self.assertIn("hr-answers.md", doc)
        # **钉那一节的标题，不是「两个渠道」四个字。** 那四个字在下面
        # 「## 两个渠道各报各的」里还有一份，只查词的话，把这一节整个换掉
        # 也照样绿（实测 2026-08-25 那个变异活了下来）。
        self.assertIn("## 同一个问题有两个渠道", doc, "讲两个渠道的那一节没了")


if __name__ == "__main__":
    unittest.main()
