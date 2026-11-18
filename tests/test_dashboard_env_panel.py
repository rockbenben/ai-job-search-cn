"""面板的环境面板：小白用户看它来判断「为什么没出 PDF」「BOSS 怎么没搜到」。

三条容易搞错、且错了不会报错的行为：

1. **可选项不能算进「缺」**。pdftotext / CDP skill / Bun 不装完全能正常用；把它们
   算进「缺 N 项」会让新用户以为出了大问题，然后去装一堆不需要的东西。
2. **只有必需项缺失或有静默失败风险时才默认展开**。可选项没装每次都弹开就是噪音。
3. **中文字体必须单独警告**。它是唯一「缺了不报错、PDF 照样出、ATS 校验也过、
   但渲染是豆腐块」的依赖——只列进表格里跟别的项并排，用户不会意识到严重性。

另外：环境探测失败不得让整个面板生成不出来（面板的主要价值是流水线视图）。
"""

import html
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))
import build_dashboard as bd  # noqa: E402
import doctor  # noqa: E402

SEEN = {"u1": {"url": "https://x/1", "title": "岗A", "company": "甲公司",
               "status": "ranked", "rank_score": 80, "rank_verdict": "强匹配"}}


class BothPanelsAgreeOnWhatCounts(unittest.TestCase):
    """「可选」这条规则**两个面板必须同一个判断**。

    单页版一直守着它（可选项不算进「缺 N 项」）；网页版守不住，因为
    `export_web_data` 把 `optional` 字段**整个丢了**——导出的 envItems 只有
    name/ok/detail/unlocks。于是一台没装 Bun 的机器上，网页版会说
    「还差 Bun（可选）」并每次默认展开，催人去装一个他不需要的东西。

    这是「算好了、导出了、却在半路掉了一个字段」那一类：两边都不报错。
    与 `resumeInsight` 漏在手写白名单里、`envItems` 的 label/name 对不上是同一族。
    """

    def test_the_rule_is_one_function(self):
        self.assertTrue(callable(bd.is_optional), "is_optional 没了")
        self.assertTrue(bd.is_optional({"optional": True, "label": "随便"}),
                        "显式标记没认")
        self.assertFalse(bd.is_optional({"optional": False, "label": "Bun（可选）"}),
                         "显式标记为假时不该再去嗅字面")
        self.assertTrue(bd.is_optional({"label": "Bun（可选）"}),
                        "老数据没有 optional 字段时，该退回嗅 label")
        self.assertFalse(bd.is_optional({"label": "Typst"}))
        # 网页版那边的字段叫 name 不叫 label
        self.assertTrue(bd.is_optional({"name": "pdftotext（可选）"}),
                        "认不出网页版的 name 字段")

    def test_the_exporter_carries_it_to_the_web_panel(self):
        src = (REPO_ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
        # **先剥注释。** 那行上面的说明里就写着 `is_optional` 四个字——不剥的话，
        # 把调用换成另抄一份判断，这条照样绿（突变当场抓到）。
        # 断言要挂在会执行的东西上，不是挂在解释它的散文上。
        src = re.sub(r"^\s*#.*$", "", src, flags=re.M)
        i = src.index('"envItems"')
        seg = src[i:i + 700]
        self.assertIn('"optional"', seg,
                      "导出的 envItems 不带 optional —— 网页版只能按 ok===false 数，"
                      "没装 Bun 的人会被催着去装一个不需要的东西")
        self.assertIn("is_optional", seg,
                      "导出器另写了一套可选判断 —— 两个面板迟早说不到一起")

    def test_the_web_panel_only_shows_up_when_something_required_is_missing(self):
        """该装的都装好了就整块不出现——「都装好了 7 / 7」是一句永远为真的话，
        占着一行和一个点击目标。想主动查有 `python tools/doctor.py`。"""
        app = (REPO_ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
        code = re.sub(r"\{/\*.*?\*/\}", "", app, flags=re.S)
        code = re.sub(r"^\s*//.*$", "", code, flags=re.M)
        m = re.search(r"const need = (.+?);", code)
        self.assertIsNotNone(m, "找不到 need")
        self.assertIn("optional", m.group(1),
                      f"「还差几项」没排除可选：{m.group(1).strip()!r}")
        # 2026-08-24 换写法：这一块从正文里的折叠改成了那一排按钮里的一颗，
        # 「有才出现」的判据也从 `{need.length > 0 && (` 挪到了 `show:`。
        # 守的那件事一个字没变。
        i = code.index('key: "env"')
        self.assertRegex(
            code[i:i + 300], r"show: need\.length > 0",
            "环境这一档不是「有必需项缺失才出现」——它会在什么都不缺时常驻，"
            "说一句永远为真的「都装好了」")

    def test_the_all_good_branch_is_gone(self):
        """块只在缺东西时渲染，所以「都装好了」那一支是死代码。
        留着死分支，下一个人会以为它还会出现。"""
        app = (REPO_ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
        code = re.sub(r"\{/\*.*?\*/\}", "", app, flags=re.S)
        code = re.sub(r"^\s*//.*$", "", code, flags=re.M)
        self.assertNotIn('"都装好了"', code,
                         "「都装好了」还留在渲染里 —— 那一支永远走不到")


class SilentFailuresGetTheirOwnWarning(unittest.TestCase):
    """中文字体是唯一「缺了不报错」的依赖，它不能只当表里的一行。

    缺了它：Typst 不报错、PDF 照样生成、招聘系统的文本层校验也过，但打开是一页
    豆腐块。和别的项并排列在格子里，用户不会意识到严重性。

    **这条规则原来只有单页版守着**（它渲染一个 `env-silent` 块）。两套面板合并时
    差点连规则一起删掉——所以搬过来的时候要连守卫一起搬，不是只搬功能。

    根因还是老一套：`doctor.py` 一直在标 `silent_fail`，而导出器把这个字段丢了，
    网页版拿不到、也就守不住（`optional` 当初一模一样）。
    """

    def test_doctor_still_marks_it(self):
        """整条链的源头。标记没了，下面两条就都成了空转。"""
        items = doctor.probe_env()
        silent = [e for e in items if e.get("silent_fail")]
        self.assertTrue(silent, "doctor 不再标 silent_fail —— 静默失败这件事没人说了")
        self.assertTrue(any("字体" in e["label"] for e in silent),
                        f"标了 silent_fail 的不是中文字体：{[e['label'] for e in silent]}")

    def test_the_exporter_carries_it(self):
        src = (REPO_ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
        src = re.sub(r"^\s*#.*$", "", src, flags=re.M)
        i = src.index('"envItems"')
        seg = src[i:i + 900]
        self.assertIn('"silentFail"', seg,
                      "导出的 envItems 不带 silentFail —— 网页版没法单独警告")
        self.assertIn('"fix"', seg, "不带 fix —— 用户看到「缺了」却不知道怎么装")

    def test_the_web_panel_renders_a_separate_warning(self):
        app = (REPO_ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
        code = re.sub(r"\{/\*.*?\*/\}", "", app, flags=re.S)
        self.assertIn("env-silent", code, "网页版没有单独的静默失败警告块")
        self.assertIn("silentFail", code, "警告块没按 silentFail 筛")
        self.assertIn("不会报错", code,
                      "警告里没说清「缺了不报错」——那正是它要提醒的唯一一件事")


class WhatTheWebPanelMustStillSay(unittest.TestCase):
    """单页版删掉时，这几条规则跟着搬过来 —— **不是跟着删掉**。

    原来它们是靠渲染单页版 HTML 再断言的（`bd.render` + `envbox`）。渲染器没了，
    那批断言当然全红；但红的是**测法**，规则一条都没过时。逐条搬到网页版这侧：

    | 原来验什么 | 现在怎么验 |
    |---|---|
    | 只缺可选项时不算「缺东西」 | 整块不渲染（`need` 排除 optional），见上面那个类 |
    | 缺必需项要点名 + 说影响 | 标题写「还差 X」，格子里给 unlocks |
    | 缺了要给装法 | 格子里 `e.ok === false && e.fix` |
    | 面板要指回命令行 | 底下那句 `python tools/doctor.py` |
    | 中文字体单独警告 | 上面 `SilentFailuresGetTheirOwnWarning` |
    """

    @classmethod
    def setUpClass(cls):
        src = (REPO_ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
        src = re.sub(r"\{/\*.*?\*/\}", "", src, flags=re.S)
        cls.code = re.sub(r"^\s*//.*$", "", src, flags=re.M)
        i = cls.code.index('key: "env"')
        cls.block = cls.code[i:cls.code.index("</Modal>", i)]

    def test_missing_required_items_are_named(self):
        self.assertIn("还差", self.block, "缺必需项时不点名是哪几个")
        self.assertIn("need.map", self.block,
                      "点的名是从 need 来的吗 —— 用 missing 会把可选项也念出来")

    def test_each_item_says_what_it_unlocks(self):
        """只说「缺了 Typst」，用户不知道该不该管。要说它挡住了什么。"""
        self.assertIn("e.unlocks", self.block, "格子里没说这一项是干什么用的")

    def test_a_missing_item_gets_install_instructions(self):
        """缺了不给装法，等于只说「你缺东西」不说怎么办。
        装好了还挂个安装链接则是噪音——所以只给缺的那几项。"""
        self.assertIn("e.fix", self.block, "缺项没给装法")
        self.assertRegex(self.block, r"e\.ok === false && e\.fix",
                         "装法没限定在缺的那几项上")

    def test_it_points_back_at_the_command_line(self):
        """面板和命令行互相指路，用户在哪一边都能找到另一边。
        这一块只在缺东西时出现，装完想再查一遍就只剩这条路。"""
        self.assertIn("tools/doctor.py", self.block,
                      "面板不指回命令行 —— 装完之后没有任何地方能再查一遍")


if __name__ == "__main__":
    unittest.main()
