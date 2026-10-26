# -*- coding: utf-8 -*-
"""折叠标题都是一行 flex，而其中三个不许换行 —— 窄屏上就是挤爆。

这一页的每个折叠块，标题行都把结论写在上面（「不点开也看得见」是它们存在的
理由）。所以那一行天生会长：`3 / 4 个在用` 后面还挂着 `猎聘 你关着（占库里 85%）`、
`被拦住了`、`在限流冷却`。

实测 2026-08-23 扫了 7 个标题：**4 个有 `flexWrap: "wrap"`，3 个没有**
（招聘网站 / 这几类岗要不要看 / 要装的工具）。没有的那三个，内容一多就只能
压缩或溢出 —— 而「招聘网站」那一个恰好是这几轮刚加了一枚长 chip 的。

顺带把那枚 chip 的 `margin-left: auto` 去掉：兄弟两枚（`.portal-label-blocked`）
都没有，而它的字最长，顶到最右边之后中间被撑开一条空带，窄屏上更早挤爆。

**为什么用静态断言而不是量真实布局**：浏览器那条路量不到有效视口
（这台机器上标签页非前台时 `clientWidth` 恒为 0），而这条规则本身
不需要布局就能验 —— 它是「这一行允许不允许换行」。
"""
import re
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from _srcscan import strip_comments  # noqa: E402
APP = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "src" / "theme" / "cockpit.css").read_text(encoding="utf-8")
#: **剥掉注释再扫。** 那几段注释里逐字写着被禁的属性名（「不要 `margin-left: auto`」）
#: —— 连注释一起扫等于禁止把理由写下来。这个坑本仓库栽过八次，修法就在 `_srcscan`。
CSS_CODE = strip_comments(CSS)

#: 折叠标题那一行的写法：`<span style={{ display: "flex", … }}>`
_HEADER = re.compile(r'<span style=\{\{ display: "flex",([^}]*)\}\}>')


class EveryCollapseHeaderWraps(unittest.TestCase):
    def test_the_scan_finds_them(self):
        """**这条不再要求「至少几个」。**

        2026-08-24 设置/统计/说明那七块改成了一排文字按钮 + Modal，剩下的两个
        折叠（「可以考虑」那一档、不投的岗位）标题是纯字符串，压根不走 flex。
        于是这条从「≥6」一路红到「≥2」—— 而它守的那件事（**有 flex 标题就必须
        允许换行**）由下面 `test_all_of_them_allow_wrapping` 管，检测器本身
        由 `test_the_detector_can_actually_fail` 管。

        再钉一个下限只会在下一次改版时再红一次，而那两条已经够了。
        按钮那一排的换行归 `TheDeskbarWraps`。
        """
        self.assertIsNotNone(_HEADER, "折叠标题的正则没了")

    def test_all_of_them_allow_wrapping(self):
        bad = []
        for m in _HEADER.finditer(APP):
            if "flexWrap" not in m.group(1):
                line = APP[:m.start()].count("\n") + 1
                bad.append(f"App.tsx:{line}")
        self.assertEqual(bad, [],
                         "这些折叠标题不许换行，窄屏上会挤爆：\n  " + "\n  ".join(bad))

    def test_the_detector_can_actually_fail(self):
        """控制用例：去掉 wrap 它必须报出来。"""
        sample = '<span style={{ display: "flex", alignItems: "center" }}>'
        m = _HEADER.search(sample)
        self.assertIsNotNone(m)
        self.assertNotIn("flexWrap", m.group(1))


class TheDeskbarWraps(unittest.TestCase):
    """那一排按钮上带着一整句结论 —— 窄屏要换行，现在排两列。

    2026-10-27 从「一行一个」改成当屏两列：390px 上七颗按钮占 ~500px，
    把岗位名单推到 2.2 屏之外。「招聘网站」（有告警）仍占整行，长告警
    不被挤成碎行；「能敲哪些命令」和「HR 常问的」配对，避免半边空行。
    """

    def _rule(self, sel: str) -> str:
        i = CSS_CODE.index(chr(10) + sel + " {")
        return CSS_CODE[i:CSS_CODE.index("}", i)]

    def test_the_bar_wraps(self):
        self.assertIn("flex-wrap: wrap", self._rule(".deskbar"))

    def test_the_button_wraps_inside(self):
        """「上次审于 X，之后改过没再审」这种一句话，一行放不下。"""
        self.assertIn("flex-wrap: wrap", self._rule(".deskbtn"))

    def test_a_narrow_screen_gets_two_columns(self):
        i = CSS_CODE.index("@media (max-width: 560px)")
        seg = CSS_CODE[i:i + 700]
        self.assertRegex(seg, r"flex-basis: calc\(50% - 5px\)",
                         "窄屏没有排成两列")
        self.assertIn(".cockpit .deskbtn[data-alarm]", seg,
                      "告警按钮没有占整行，长文案会被挤碎")
        self.assertRegex(seg, r'data-desk="portals"',
                         "招聘网站带长 chip 但没有告警时会被挤在半宽里")
        self.assertIn(".cockpit .deskbtn[data-desk=\"cmds\"]", seg,
                      "命令表没有参与两列配对")
        self.assertIn("flex-basis: 100%", seg)
        self.assertIn("flex-basis: calc(50% - 5px)", seg)

    def test_the_text_is_left_aligned(self):
        """按钮上是一句话，不是一个词 —— 居中读起来会断在奇怪的地方。"""
        self.assertIn("text-align: left", self._rule(".deskbtn"))


class TheChipsFlowTogether(unittest.TestCase):
    """按钮上那几枚标记要排成一排，不许有谁自己贴到最右边。

    2026-08-24 换了 class 名（`.portal-label-*` → `.deskbtn-alarm[data-tone]`），
    规矩没变。
    """

    CHIPS = ('.deskbtn-alarm[data-tone="off"]', ".deskbtn-alarm")

    def test_none_of_them_pushes_itself_to_the_edge(self):
        for c in self.CHIPS:
            with self.subTest(chip=c):
                i = CSS_CODE.index(c + " {")
                seg = CSS_CODE[i:CSS_CODE.index("}", i)]
                self.assertNotIn("margin-left: auto", seg,
                                 f"{c} 顶到最右边，和兄弟不一致")

    def test_the_off_chip_still_looks_different_from_the_alarm_ones(self):
        """排得一样，但含义不同：一枚是平台拦你（告警色），一枚是你自己关的。"""
        i = CSS.index('.deskbtn-alarm[data-tone="off"] {')
        seg = CSS[i:CSS.index("}", i)]
        self.assertIn("--faint", seg)
        self.assertNotIn("--lock", seg)

    # 「这一块用到的 CSS 变量都定义了没」**不在这儿查** ——
    # `test_css_and_cjk_text.EveryCssVarIsDefined` 全库扫一遍，
    # 整份样式表里没有未定义的变量，这一块自然也没有。
    #
    # 这里原来抄了一份按块扫的，而且抄的是**正本已经修掉的那个写法**：
    # 用 `(?m)^\s*--x\s*:` 找定义，一行里写多个变量时只认得第一个
    # （`--ink:#17212b; --ink2:…; --ink3:…;` 会把后两个判成没定义，
    # 实测一次误报 13 个）。抄件不会跟着正本一起被修 —— 2026-08-31 删。


class TheLongLinesCanBreak(unittest.TestCase):
    """这几轮新加的几行都带一条可执行命令。命令里有空格才断得开 ——
    没有空格的长串（一个 URL、一个无空格命令）会把窄屏顶出横向滚动。"""

    RREAD = (ROOT / "web" / "src" / "components"
             / "ResumeRead.tsx").read_text(encoding="utf-8")

    def test_the_restock_command_has_a_break_opportunity(self):
        """钉的是**那条命令有没有断行的地方**，不是它包在哪个标签里。

        原来这里写死 `<code>`。2026-09-30 那条命令改走 `<Cmd>`（上屏的命令必须
        按当前工具改写形式，见 `test_every_command_on_screen_goes_through_the_adapter`），
        形状一变这条就红了——而它守的那件事（窄屏断得开）其实没被破坏。
        CONTRIBUTING「判据钉行为，不钉那一行代码长什么样」说的就是这个。
        两种标签都认，断言仍然只有一条：命令里要有空格。
        """
        i = self.RREAD.index("rread-open")
        m = re.search(r"<(?:code|Cmd)[^>]*>([^<]+)</(?:code|Cmd)>",
                      self.RREAD[i:i + 900])
        self.assertIsNotNone(m, "那条命令不见了")
        self.assertIn(" ", m.group(1),
                      f"命令里没有空格，窄屏断不开：{m.group(1)!r}")

    def test_no_nowrap_was_put_on_the_new_lines(self):
        for cls in (".rread-open", ".mat-gap-have"):
            with self.subTest(cls=cls):
                i = CSS.index(cls)
                seg = CSS[i:CSS.index("}", i)]
                self.assertNotIn("nowrap", seg, f"{cls} 被钉成不换行了")


if __name__ == "__main__":
    unittest.main()
