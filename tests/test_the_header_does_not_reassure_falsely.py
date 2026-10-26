# -*- coding: utf-8 -*-
"""折叠标题上那一行，多数时候是用户唯一会读的字。它不许说反话。

两处实测（活动用户 2026-08-23）：

**一、「上次审于 2026-08-01」——而简历 08-12 改过。**

那份报告审的是一个已经不存在的版本；现在这份**从没被审过**。而它的结论是
「这份简历现在可以直接投，没有必须处理的问题」——读的人会照着它去投。
`audit.stale` 与 `resumeChangedOn` **早就算出来、也导出了**，
`BaseResume` 展开后也确实说了这句话 —— 可折叠标题只印日期。
**把矛盾藏在一次点击后面，等于让他先信一遍。**

同一个标题里 `pdfStale` 早就有位置。而两者的分量不同：
PDF 旧了只是导出没跟上，审核旧了是**结论不作数**。

**二、「3 / 4 个在用」——那第 4 个是猎聘，占库里 85%。**

`enabled=false`、`blocked=false`、`canScrape=true`：当初是封控期间关掉的
（`Portals.tsx` 那段注释记着「勾是关的、又封着」），封控早解了，开关还留在关上。
它供了 2232/2638 个岗、9 个可投里的 8 个。

这一枚**不是催他打开**（那是他的决定），是让那个决定看得见代价 ——
仓库里同一条原则写在排除清单那一档上：「每一条排除都有价格，
而他设的时候看不见价格」。所以用中性色，不用告警色：
一个用户的选择不该长期报警。

而**既关着又封着时不说「你关着」**：那会盖住「封着」，
而后者才是要他做点什么的那一个。
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "src" / "theme" / "cockpit.css").read_text(encoding="utf-8")
BR = (ROOT / "web" / "src" / "components"
      / "BaseResume.tsx").read_text(encoding="utf-8")


def _resume_header():
    #: **不要拿 `APP.index("你的简历")` 定位** —— 那个词先出现在别处
    #: （实测三处，第一处离渲染点 600 字符）。锚在真正的渲染点上：
    #: 那一段唯一的标志是 `key: "baseresume"`。这个坑本仓库栽过六次。
    i = APP.index('key: "baseresume"')
    return APP[i:i + 2200]


class TheResumeHeaderSaysTheAuditIsStale(unittest.TestCase):
    def test_the_header_reads_the_flag(self):
        self.assertIn("audit.stale", _resume_header(),
                      "标题只印日期，不说那份报告已经不作数")

    def test_it_still_prints_the_date(self):
        """**不许把日期换掉。** 「上次审于哪天」本身是有用的。"""
        self.assertIn("上次审于", _resume_header())

    def test_it_says_what_happened_not_just_that_it_is_old(self):
        """「旧了」是状态，「之后改过没再审」是原因 —— 后者才指得出动作。"""
        self.assertRegex(_resume_header(), r"之后改过|改过没再审")

    def test_the_warning_is_also_a_chip(self):
        """**note 被首屏高度优化挡掉了，审核过期不能跟着消失。**

        `deskbtn-note` 只在 `alarm || chips` 时渲染，而「你的简历」通常没有告警；
        当前活动用户的 `audit.stale=true`、`pdfStale=false`，首屏却只显示
        「你的简历」四个字。用已有 chip 槽位把警告留回首屏；完整日期仍在弹窗。
        """
        header = _resume_header()
        self.assertIn("audit?.stale", header,
                      "chip 没读审核过期标记")
        self.assertIn("简历改过没再审", header,
                      "审核过期没有出现在 chip 上")

    def test_both_stale_are_not_hidden_behind_each_other(self):
        """PDF 旧 + 审核旧同时为真时，chip 不能只说 PDF。

        PDF 旧是导出没跟上；审核旧是结论不作数。前者更具体，但不能因此
        把后者藏起来。
        """
        self.assertIn("PDF 是旧的 · 改过没再审", _resume_header())

    def test_the_body_still_carries_the_full_notice(self):
        """标题那半句是提要，展开后那句（含改动日期）不许被顺手删掉。"""
        self.assertIn("audit.stale", BR)
        self.assertIn("resumeChangedOn", BR)

    def test_never_audited_is_still_its_own_case(self):
        """「还没审过」和「审过但过期了」是两件事，不能合并。"""
        self.assertIn("还没审过", _resume_header())


def _portal_header():
    """「招聘网站」那颗按钮那一段。

    **2026-08-24 换了容器**：这几枚标记原来挂在折叠标题上，中间在抽屉外那颗
    固定按钮上待过一版，现在挂在那一排文字按钮里的「招聘网站」上
    （用户否掉了抽屉）。**它们守的三件事一个字没变**，锚点仍是那个 key。
    """
    i = APP.index('key: "portals"')
    return APP[i:i + 4200]


class ThePortalHeaderNamesWhatIsOff(unittest.TestCase):
    def test_the_chip_exists(self):
        self.assertIn('tone: "off"', _portal_header(),
                      "标题说不出关掉的是哪一家")

    def test_it_only_fires_when_the_portal_could_still_scrape(self):
        """既关着又封着时不说「你关着」——那会盖住「封着」，
        而后者才是要他做点什么的那一个。"""
        seg = _portal_header()
        i = seg.index('tone: "off"')
        cond = seg[max(0, i - 400):i]
        for w in ("!p.enabled", "!p.blocked", "p.canScrape"):
            with self.subTest(w=w):
                self.assertIn(w, cond, f"判据里少了 {w}")

    def test_it_shows_the_price(self):
        """只说「猎聘关着」是个状态。要说出这个决定花了多少。"""
        seg = _portal_header()
        i = seg.index('tone: "off"')
        self.assertRegex(seg[i:i + 900], r"占库里 \$\{pct\}%",
                         "没把它占多大份额说出来")

    def test_a_tiny_portal_does_not_get_a_percentage(self):
        """占比很小的时候那个数只是噪音。"""
        seg = _portal_header()
        i = seg.index('tone: "off"')
        self.assertRegex(seg[i:i + 900], r"pct >= 10", "没有「小到不必说」的门槛")

    def test_the_word_order_matches_the_sibling_chips(self):
        """旁边两枚是「猎聘 被拦住了」「猎聘 在限流冷却」——名字在前、动词在后。
        价格挂最后，不许插在名字和动词之间。"""
        seg = _portal_header()[_portal_header().index('tone: "off"'):][:900]
        # **两支都要验。** 三元的另一支（占比不足 10% 时）也拼这句话，
        # 只验一支的话，改坏其中一支照样绿 —— 变异实测漏过一次。
        self.assertEqual(len(re.findall(r"\$\{p\.name\} 你关着", seg)), 2,
                         "有一支的语序不对")
        self.assertNotRegex(seg, r"你关着 \$\{p\.name\}", "名字被挪到动词后面了")


class TheChipColoursSayWhoIsResponsible(unittest.TestCase):
    """2026-08-24 换了 class 名（`.portal-label-*` → `.deskbtn-alarm[data-tone]`），
    「谁该负责」要看得出来这条规矩没变。

    **但颜色从三种减到两种了（2026-08-27）。** 原来第三种是 `wait`
    （「等它自己好」），配给 CLI 限流那种封控 —— 而 2026-08-26 裁定封控不再
    自动到期之后，它要用户换网络出口，和「去过验证」一样是待办。
    两枚的差别改由**文案**承担（「被拦住了」/「被限流了，换个网络再试」），
    `wait` 的色、类型成员、CSS 规则一起撤了。

    剩下的分界仍然是这个类要守的那一条：**平台拦你（要你处理）**
    与**你自己关的（陈述，不是待办）**，两者不许同色。
    """

    OFF = '.deskbtn-alarm[data-tone="off"]'

    def test_a_user_choice_does_not_use_the_alarm_colour(self):
        """平台拦你 = 告警；你自己关的 = 陈述。一个用户的选择不该长期报警。"""
        # **切到那条规则的右花括号**，不数字符 —— 200 字会读到隔壁
        # `.deskbtn-chip` 的 `--caution`，报一个不存在的问题。
        i = CSS.index(self.OFF)
        seg = CSS[i:CSS.index("}", i)]
        self.assertNotIn("--caution", seg)
        self.assertNotIn("--lock", seg)

    def test_the_two_tones_are_distinct(self):
        """要你处理 / 你自己关的 —— 一个颜色说不出两件事。"""
        import re as _re
        got = {}
        for tone in ("", '[data-tone="off"]'):
            sel = ".deskbtn-alarm" + tone
            i = CSS.index(sel + " {")
            m = _re.search(r"color:\s*var\((--[a-z-]+)\)", CSS[i:i + 200])
            self.assertIsNotNone(m, f"{sel} 没有颜色")
            got[tone or "alarm"] = m.group(1)
        self.assertEqual(len(set(got.values())), 2,
                         f"两枚标记颜色没分开：{got}")

    def test_the_retired_tone_left_no_rule_behind(self):
        """`wait` 撤了，CSS 里不许再留它的规则 —— 那会变成一条死样式，
        而下一个人会拿它去标别的东西。"""
        self.assertNotIn('.deskbtn-alarm[data-tone="wait"] {', CSS,
                         "wait 那条样式规则还在，但没有任何 chip 会用它")

    # 「这一块用到的 CSS 变量都定义了没」**不在这儿查** ——
    # `test_css_and_cjk_text.EveryCssVarIsDefined` 全库扫一遍，
    # 整份样式表里没有未定义的变量，这一块自然也没有。
    #
    # 这里原来抄了一份按块扫的，而且抄的是**正本已经修掉的那个写法**：
    # 用 `(?m)^\s*--x\s*:` 找定义，一行里写多个变量时只认得第一个
    # （`--ink:#17212b; --ink2:…; --ink3:…;` 会把后两个判成没定义，
    # 实测一次误报 13 个）。抄件不会跟着正本一起被修 —— 2026-08-31 删。


if __name__ == "__main__":
    unittest.main()
