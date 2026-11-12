# -*- coding: utf-8 -*-
"""自检说这一项「影响面试准备」，而它其实每次出材料都在静默失效。

`profile/behavioral.md` 在自检的需求表里**只挂在「面试准备」那一档**
（`STAGE_NEEDS["interview"]["warn"]`）。而 `job-apply.md` 有**三处**在用它：

    Step 1   「行为/文化参考」
    Step 3   审稿者的**语域检查** —— 稿子的口吻是不是这个人自然的说话方式
    Step 4   语气修订

## 后果不是说错一句话，是用户按它给的信息做了个合理的决定

手上 0 个面试 → 那当然先不填。而那三处检查从此静默跳过。

实测活动用户 2026-08-24（这份文件一直是占位符）：

    话术总数                        243 份
    **全部是在没有语域检查下写出来的**  243 份
    深评里说了规定那句降级说明的      57/270（21%）
    话术里说了的                    **0/237**

`job-apply.md`「`behavioral.md` 未填时：降级，不中止」写着要「在评估输出与最终
呈现里**各写一句**」。一半执行了两成，另一半一次都没有。

## 2026-08-26：另一半开始生效了

那一天出的第一份材料（阿里云 · 无影 AI 应用产品经理）在 `outreach.md` 的自检里
写了那一句。下面那条断言因此**翻了个方向**：原来钉的是「一份都没有」——它记录的是
当时那个 bug；现在钉「至少有一份」，守的是修好之后别再退回去。

原话留在上面不动：那是这一节存在的理由，删了就没人知道这条断言在防什么。

## 三处一起改

- **挂对档**：`behavioral.md` 从 `interview` 挪到 `apply`（最早真正消费它的那一步）。
  只挂一档就够 —— 填一次两边都有，列两档会在自检里报两遍（`soft` 那段不去重）。
- **给一条轻路**：此前它没有单节入口，自检只能报整跑 `/job-setup`。
  为一份可选文件重做全部资料，没人会做。Section 6 本来就同时写
  `## 行为特质` 与 `profile/behavioral.md`，只是 `--section` 表里没给它名字。
- **那行提醒要带命令**：它告诉用户少了什么，却不告诉他敲什么
  （`AGENTS.md`「每一处引导都要写出该敲的命令」对它同样成立）。
"""
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import doctor  # noqa: E402

DR = (ROOT / "tools" / "doctor.py").read_text(encoding="utf-8")
SETUP = (ROOT / "workflows" / "job-setup.md").read_text(encoding="utf-8")
APPLY = (ROOT / "workflows" / "job-apply.md").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*(?:>|#:?)\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


def warns(stage):
    return [n for f, n in doctor.STAGE_NEEDS[stage]["warn"]]


class ItIsNeededAtTheStageThatUsesIt(unittest.TestCase):
    def test_it_is_listed_under_apply(self):
        self.assertIn(("behavioral.md", None), doctor.STAGE_NEEDS["apply"]["warn"])

    def test_it_is_no_longer_only_an_interview_thing(self):
        """挂错档的代价不是说错一句话 —— 用户按它给的信息合理地推迟了。"""
        self.assertNotIn(("behavioral.md", None),
                         doctor.STAGE_NEEDS["interview"]["warn"])

    def test_it_is_listed_exactly_once(self):
        """列两档会在自检里报两遍（`soft` 那段按步拼串，不去重）。"""
        n = sum(1 for st in doctor.STAGE_NEEDS.values()
                for f, _ in st["warn"] + st["block"] if f == "behavioral.md")
        self.assertEqual(n, 1)

    def test_the_interview_half_survives(self):
        """`candidate.md` 的「行为特质」那一节仍归面试准备 —— 别一起挪走。"""
        self.assertIn(("candidate.md", "行为特质"),
                      doctor.STAGE_NEEDS["interview"]["warn"])

    def test_it_stays_a_warn_not_a_block(self):
        """它是可选输入。挡人等于把「降级，不中止」那条规则反过来了。"""
        for st in doctor.STAGE_NEEDS.values():
            for f, _ in st["block"]:
                with self.subTest(f=f):
                    self.assertNotEqual(f, "behavioral.md")

    def test_apply_really_uses_it_three_ways(self):
        """这一整条建立在「出材料真的在用它」上。"""
        seg = flat(APPLY)
        self.assertRegex(seg, r"第 1 步的「行为/文化参考」")
        self.assertRegex(seg, r"第 3 步审稿者的语域检查")
        self.assertRegex(seg, r"第 4 步的语气修订")

    def test_the_reason_is_recorded(self):
        i = DR.index('"apply": {"block"')
        seg = flat(DR[i:DR.index('"interview": {"block"', i)])
        self.assertIn("behavioral", seg)


class ThereIsALightWayToFillIt(unittest.TestCase):
    def test_the_section_is_registered(self):
        self.assertEqual(doctor.SECTION_OF.get("行为特质"), "behavioral")

    def test_the_setup_table_has_the_row(self):
        self.assertRegex(SETUP, r"\|\s*`behavioral`\s*\|\s*Section 6\s*\|")

    def test_the_flow_actually_offers_it(self):
        """**表里一行不算入口。** 流程正文里没有哪一步提到它，就没人会知道。
        `test_doctor` 核的正是 `--section <名>` 在正文里出现过。"""
        self.assertIn("/job-setup --section behavioral", SETUP)

    def test_that_section_writes_both_files(self):
        """指过去的那一节要真的能写 `behavioral.md`，否则是条到不了的路。"""
        i = SETUP.index("### Section 6：行为特质")
        seg = flat(SETUP[i:SETUP.index("### Section 7", i)])
        self.assertIn("profile/behavioral.md", seg)

    def test_the_section_says_it_is_not_just_for_interviews(self):
        i = SETUP.index("### Section 6：行为特质")
        seg = flat(SETUP[i:SETUP.index("### Section 7", i)])
        self.assertRegex(seg, r"它不只影响面试准备")
        self.assertRegex(seg, r"静默跳过")

    def test_the_measured_cost_is_in_the_section(self):
        i = SETUP.index("### Section 6：行为特质")
        seg = flat(SETUP[i:SETUP.index("### Section 7", i)])
        self.assertIn("behavioral", seg)


class TheWarningCarriesACommand(unittest.TestCase):
    def test_it_prints_one(self):
        self.assertIn('print(f"      补它：{fix_for(_names)}")', DR)

    def test_it_is_built_from_the_same_items_it_just_listed(self):
        """报的是 A、补的是 B，用户敲完发现没补上那一项 —— 两处必须同源。"""
        i = DR.index('_names = [n for s in ready')
        seg = DR[i:i + 200]
        self.assertIn('st["gaps"][s]["warn"]', seg)

    def test_the_reason_is_recorded(self):
        i = DR.index("**这一行原来不给命令。**")
        seg = flat(DR[i:i + 400])
        self.assertRegex(seg, r"却不知道该敲什么")

    def test_the_command_it_gives_is_real(self):
        """现算一遍：拿真实缺项跑一次 `fix_for`，出来的命令要在 setup.md 里存在。"""
        cmd = doctor.fix_for(["行为特质"])
        self.assertTrue(cmd.startswith("/job-setup"), cmd)
        m = re.search(r"--section (\S+)", cmd)
        if m:
            self.assertIn(f"--section {m.group(1)}", SETUP)


class TheDegradationRuleItselfIsIntact(unittest.TestCase):
    """这一条只改「谁提醒他去填」，`job-apply.md` 那条降级规则一个字都不许动。"""

    def test_it_still_says_degrade_not_stop(self):
        self.assertIn("### `behavioral.md` 未填时：降级，不中止", APPLY)

    def test_it_still_forbids_inventing_from_placeholders(self):
        seg = flat(APPLY)
        self.assertRegex(seg, r"绝不\*\*拿 `\[PROFILE_TYPE\]`")
        self.assertRegex(seg, r"绝不\*\*在核对清单里把语域检查报成通过")

    def test_it_still_requires_saying_so_twice(self):
        seg = flat(APPLY)
        self.assertRegex(seg, r"在评估输出与最终呈现里\s*各写一句")


class TheSignalItLeansOnIsReal(unittest.TestCase):
    """现算：这份文件真的还是占位符，而话术真的一份都没说过那句降级说明。"""

    def _user(self):
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        return ROOT / "users" / p.read_text(encoding="utf-8").strip()

    def test_an_unfilled_file_really_is_detectable(self):
        """**验的是「占位符认得出来」，不是「他还没填」。**

        第一版写成「还没填就 `assertTrue(True)`」—— 那是个恒真断言，
        `test_no_assertion_is_dead_on_arrival` 当场逮到。他填不填是他的事，
        这条该守的是：这份文件里的占位符长什么样、还认不认得出来。
        认不出来时上游那条降级判据就会静默失效（`job-apply.md` 那一节的原话是
        「仍是占位符（或文件不存在）→ 跳过所有依赖它的检查」），
        材料照出、口吻没人核。

        ⚠️ 这里**不写成「某文件的『某节』」那个形状** ——
        `test_cross_references_resolve` 会按那个形状去核小节名，
        而这句引的是节里的一行，不是节名（第一版就这么写，`git add` 之后
        当场报断链：解析器只扫已跟踪文件，加进版本库那一刻才照出来）。
        """
        u = self._user()
        f = u / "profile" / "behavioral.md"
        if not f.is_file():
            self.skipTest("这位用户还没有这份文件")
        tpl = ROOT / "profile.example" / "behavioral.md"
        if not tpl.is_file():
            self.skipTest("模板不在，比不出占位符长什么样")
        marks = set(re.findall(r"\[[A-Z_]{3,}\]", tpl.read_text(encoding="utf-8")))
        self.assertTrue(marks, "模板里一个占位符都没有 —— 那条降级判据没有依据了")
        left = {m for m in marks if m in f.read_text(encoding="utf-8")}
        if not left:
            self.skipTest("他已经填完了 —— 这一节的前提不再成立，是好事")
        self.assertLessEqual(
            len(left), len(marks),
            "用户文件里的占位符比模板还多？两份对不上，判据会误判")

    def test_the_outreach_files_say_it_too(self):
        """规则的另一半：话术里也要写那句降级说明，不能只写在深评里。

        这条 2026-08-26 翻了方向。原来断言 `said == 0`，记录的是当天那个 bug
        （`job-apply.md` 0.5 要求「在评估输出与最终呈现里**各写一句**」，
        而话术那一半 237 份一次都没写）。那天出的第一份材料写了，
        断言跟着改成「至少有一份」——从记录 bug 变成守住修复。
        """
        u = self._user()
        apps = u / "documents" / "applications"
        if not apps.is_dir():
            self.skipTest("还没有话术")
        outs = list(apps.glob("*/outreach.md"))
        if len(outs) < 20:
            self.skipTest("话术太少，比不出来")
        said = sum(1 for f in outs
                   if "behavioral" in f.read_text(encoding="utf-8", errors="replace"))
        self.assertGreater(
            said, 0,
            f"{len(outs)} 份话术里一份都没写那句降级说明 —— "
            "`job-apply.md` 0.5 要求「在评估输出与最终呈现里各写一句」，"
            "话术那一半又静默失效了")


if __name__ == "__main__":
    unittest.main()
