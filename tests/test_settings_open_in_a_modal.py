# -*- coding: utf-8 -*-
"""设置、统计、说明：七段折叠 → 一排文字按钮 + Modal。

这七块原来是正文里的七段折叠（招聘网站、岗位类型、要装的工具、你的简历、
市场怎么读你的简历、投出去的那些、能敲哪些命令）。收起来也各占一行加外边距，
叠起来把名单挤下去；而它们回答的都不是「我今天该投谁」。

中间试过一版**侧边抽屉**，用户 2026-08-24 直接否掉：**改成能看懂的文字按钮，
点一下开 Modal**。这个文件盯的就是换过去之后那几件不能丢的事。

## 不能丢的第一件：按钮上那句结论

折叠标题上那几句是逐条推敲过的，每一句背后都有一次事故：

    「上次审于 X，之后改过没再审」   不是「上次审于 X」——后者读起来是安心，
                                  而报告审的可能是一个已经不存在的版本
    「有回音 0%」 vs 「还没有」       `?? 0` 会把「还没到时候」印成 0%
    「记状态在这一页点就行」          页脚那句「只显示」早就不是真的了

换成按钮不能把它们丢掉，否则这一排就是七个没有信息的词。

## 不能丢的第二件：招聘网站那三枚标记

它们是 2026-08-21 那次事故的修法（猎聘 CLI 封了 9 小时，面板上一个字看不到）。
三枚三种意思，**不能并成一句**：

    被拦住了     要你去做点什么
    在限流冷却   等它自己好
    你关着       你自己的决定 —— 不是待办，是让那个决定看得见代价

## 不能丢的第三件：还没建过档的人看得到命令表

折叠时代靠 `defaultActiveKey={activeUser ? [] : ["cmds"]}`。按钮的前提是
「你已经知道自己在看什么」，所以这类用户改成**内联摊开** —— 为它自动弹一个
Modal 比不弹更糟。
"""
import pathlib
import re
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _srcscan import strip_comments  # noqa: E402
from jsx import FIRSTRUN, desk_entry  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "src" / "theme" / "cockpit.css").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*//:?\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


def rule(sel: str) -> str:
    i = CSS.index(chr(10) + sel + " {")
    return CSS[i:CSS.index("}", i)]


def desks() -> str:
    i = APP.index("  const desks: {")
    return APP[i:APP.index("  ].filter((d) => d.show);", i)]


#: 剥注释走**共享那份**（`tests/_srcscan.py`），不在这里另写一个。
#:
#: 这里 2026-08-27 一度自己写了一份，理由是「断言在源码原文上比字符串，
#: 注释里的字会造成假绿/假红」—— 理由没错，而 `_srcscan` 的模块 docstring
#: 开头写的就是同一件事，还记着「2026-08-22 一天之内在同一个坑里栽了七次，
#: 所以收成一处」。**又写一份，正是那句话要防的。**
#:
#: 它比我那版还稳：行尾 `//` **故意不剥**（会误伤 `https://`），只剥整行。


class TheDrawerIsGone(unittest.TestCase):
    def test_no_drawer_is_imported(self):
        self.assertNotIn("Drawer", APP, "抽屉又回来了 —— 用户 2026-08-24 否过")

    def test_no_fixed_pin_is_left(self):
        self.assertNotIn("settings-pin", APP + CSS,
                         "抽屉时代那颗固定按钮还留着")

    def test_a_modal_replaced_it(self):
        self.assertIn("ConfigProvider, Modal }", APP)
        self.assertIn('className="desk-modal"', APP)


class EveryBlockIsAButton(unittest.TestCase):
    KEYS = ("portals", "jobprefs", "env", "baseresume", "resume",
            "ostats", "cmds")

    def test_all_seven_are_in_the_bar(self):
        d = desks()
        for k in self.KEYS:
            with self.subTest(k=k):
                self.assertIn(f'key: "{k}"', d, f"{k} 不在那一排里")

    def test_none_of_them_is_still_a_collapse(self):
        for k in self.KEYS:
            with self.subTest(k=k):
                self.assertNotIn(f'key: "{k}",\n', APP.replace(desks(), ""),
                                 f"{k} 还留着一份折叠")

    def test_the_job_lists_stay_collapses(self):
        """名单不是设置，别一起关进弹窗 —— 那会把主页面掏空。"""
        for k in ("maybe", "shelf"):
            with self.subTest(k=k):
                self.assertIn(f'key: "{k}"', APP)
                self.assertNotIn(f'key: "{k}"', desks())

    def test_each_button_opens_its_modal(self):
        self.assertIn("onClick={() => setDesk(d.key)}", APP)
        self.assertIn("open={desk !== null}", APP)
        self.assertIn("onCancel={() => setDesk(null)}", APP)

    def test_the_modal_is_destroyed_on_close(self):
        """里面几块有自己的 busy/err 局部状态，留在树上会带到下一次。"""
        self.assertIn("destroyOnHidden", APP)

    def test_the_buttons_are_real_buttons(self):
        i = APP.index('className="deskbtn"')
        self.assertIn("<button", APP[i - 200:i])
        self.assertIn("aria-haspopup", APP[i:i + 300])
        self.assertIn(".deskbtn:focus-visible", CSS, "键盘焦点看不见")


class EveryButtonCarriesItsConclusion(unittest.TestCase):
    """七个没有信息的词换不来七段折叠。"""

    def test_the_resume_audit_caveat_survives(self):
        d = desks()
        self.assertIn("，之后改过没再审", d)
        self.assertIn("还没审过", d)

    def test_the_reply_rate_still_goes_through_say_rate(self):
        """`?? 0` 会把「还没到时候」印成 0% —— 判据在 `sayRate`。"""
        self.assertIn("sayRate(snap.outcomeStats.repliedRate)", desks())

    def test_the_command_line_says_what_is_clickable(self):
        d = desks()
        self.assertIn("记状态在这一页点就行，要动脑子的才回命令行", d)
        self.assertIn("这一页只显示，干活都在命令行", d)

    def test_the_portal_count_is_there(self):
        self.assertRegex(desks(), r"个在用")

    def test_the_env_note_mentions_the_optional_ones(self):
        self.assertIn("个可选的没装，不影响正常使用", desks())

    def test_the_blocker_headline_survives(self):
        self.assertIn("挡你最多的是", desks())


class TheBlockReasonIsPlain(unittest.TestCase):
    """封控原因里的 `CLI` / `RATE_LIMITED` 是内部码，不能原样念给用户。"""

    def test_it_translates_the_raw_reason(self):
        src = (ROOT / "web/src/components/Portals.tsx").read_text(encoding="utf-8")
        self.assertIn("export function blockWhyText", src)
        self.assertIn("export function blockStreakText", src,
                      "限流历史没有做出口→网络的翻译")
        self.assertIn("平台限流了", src, "封控原因没有翻成人话")
        self.assertIn("why: blockWhyText", src,
                      "告警行仍在用未翻译的 why")
        self.assertIn("有一种抓取方式被拦住了", src,
                      "告警标题还在用「通道」")


class TheThreePortalChipsSurvive(unittest.TestCase):
    """2026-08-21 那次事故的修法 —— 三枚三种意思，不能并成一句。

    **意思还是三种，颜色只剩两种了。** 2026-08-26 裁定封控不再自动到期之后，
    「在限流冷却 · 等它自己好」那一枚不成立了：它要用户换网络出口，和「去过
    验证」一样是待办。文案改成「被限流了，换个网络再试」、色从 `wait` 并进 `alarm`
    —— 两枚的差别由**文案**承担，不再由颜色承担（`AGENTS.md`「「等」不是
    下一步」：待办面上不该给「等」留位置）。
    """

    def test_all_three_are_rendered(self):
        d = desks()
        for txt in ("被拦住了", "被限流了，换个网络再试", "你关着"):
            with self.subTest(txt=txt):
                self.assertIn(txt, d)

    def test_the_texts_are_not_just_sitting_in_comments(self):
        """**源码原文里注释也算数 —— 改文案时这会造出假绿。**

        实测 2026-08-27 连栽两次：把旧文案写进「原来是…」那句注释之后，
        `assertIn(旧文案)` 照样绿（匹配到的是注释）；`assertNotIn(已撤的色)`
        照样红（撞上的也是注释）。**判据一律先剥注释再比。**
        """
        d = strip_comments(desks())
        for txt in ("被拦住了", "被限流了，换个网络再试", "你关着"):
            with self.subTest(txt=txt):
                self.assertIn(txt, d, f"「{txt}」只在注释里出现，没真的渲染")

    def test_the_retired_tone_is_gone(self):
        """`wait` 撤了就要撤干净 —— 类型、样式、chip 三处都不许再有。

        留一个没人用的「等着就行」色，下一个人会拿它去标别的东西。
        """
        self.assertNotIn('tone: "wait"', strip_comments(desks()), "还有 chip 在用 wait")
        self.assertNotIn('"alarm" | "wait"', strip_comments(APP), "类型里那个成员还留着")
        self.assertNotIn('data-tone="wait"', strip_comments(CSS), "样式规则成了死的")

    def test_they_have_two_tones(self):
        d = desks()
        for tone in ('"alarm"', '"off"'):
            with self.subTest(tone=tone):
                self.assertIn(f"tone: {tone} as const", d)

    def test_the_off_chip_only_fires_when_it_could_still_scrape(self):
        """既关着又封着时不说「你关着」—— 那会盖住「封着」。"""
        d = desks()
        i = d.index('tone: "off"')
        cond = d[max(0, i - 400):i]
        for w in ("!p.enabled", "!p.blocked", "p.canScrape"):
            with self.subTest(w=w):
                self.assertIn(w, cond)

    def test_the_off_chip_shows_the_price(self):
        self.assertIn("占库里 ${pct}%", desks())
        self.assertIn("pct >= 10", desks())

    def test_the_single_line_alarm_excludes_the_user_choice(self):
        """整颗按钮点不点亮只看「要你做点什么」—— 他自己关的不算待办。"""
        i = APP.index("const settingsAlarm")
        seg = APP[i:i + 500]
        self.assertNotIn("!p.enabled", seg)


class ItDoesNotOpenItselfInYourFace(unittest.TestCase):
    def test_nothing_auto_opens_a_modal(self):
        self.assertNotIn("setDesk(\"portals\")", APP)
        self.assertNotRegex(APP, r"useEffect[^}]*setDesk\(")

    def test_the_decision_is_written_down(self):
        i = APP.index("//: 有网站被平台拦住")
        seg = flat(APP[i:i + 700])
        self.assertRegex(seg, r"只用来点亮按钮上那枚标记")
        self.assertRegex(seg, r"比原来更靠前")


class TheModalActuallyAppears(unittest.TestCase):
    """**实测它曾经不出现。**

    2026-08-24 在浏览器里点开（浏览器开着「减少动态效果」）：DOM 里在、标题也对、
    遮罩也上来了，而弹窗本身的 `opacity` 卡在 0，class 停在
    `ant-zoom-appear-prepare`。

    链条是这样的：antd 把 `opacity: 0` 写在进场动画的**起始状态**里，靠动画跑完
    才回到 1；而 `cockpit.css` 在 `prefers-reduced-motion` 下把动画整个关掉，
    rc-motion 就永远等不到 `animationend`，也永远不摘那两个 class。

    试过两条不管用的路，都记在代码注释里：把时长改成 `0.01ms`（短到收不到事件）、
    `theme.token.motion: false`（只挡住了遮罩那一半）。管用的是 antd 自己给的
    `transitionName=""` —— 从源头不进动画流程。
    """

    def test_the_modal_declares_no_transition(self):
        i = APP.index('className="desk-modal"')
        seg = APP[i:i + 1400]
        self.assertIn('transitionName=""', seg)
        self.assertIn('maskTransitionName=""', seg)

    def test_the_reason_is_written_down(self):
        i = APP.index('className="desk-modal"')
        seg = flat(APP[i:i + 1400].replace("/*", "").replace("*/", ""))
        self.assertRegex(seg, r"弹窗\s*\*\*根本不出现\*\*|弹窗\*\*根本不出现\*\*")
        self.assertRegex(seg, r"prefers-reduced-motion")

    def test_reduced_motion_no_longer_nukes_animations(self):
        """`animation: none` 是这个坑的另一半 —— 它让起始帧变成终态。"""
        i = CSS.index("@media (prefers-reduced-motion: reduce)")
        seg = CSS[i:CSS.index("}", CSS.index("{", CSS.index("*,", i)))]
        self.assertNotIn("animation: none", seg,
                         "又把动画整个关掉了 —— antd 的元素会停在 opacity: 0")

    def test_the_css_note_explains_it(self):
        """CSS 那半只留一句提要 + 指路 —— 全文写在 `App.tsx` 那边。
        写长了会把两个相邻的 `@media` 撑开，`BreakpointsStayTogether` 会红
        （2026-08-24 当场红过一次）。"""
        i = CSS.index("减少动态效果")
        seg = " ".join(CSS[i:i + 300].split())
        self.assertIn("opacity: 0", seg)
        self.assertIn("起始状态", seg)
        self.assertIn("desk-modal", seg, "没指去写着全文的那处")


class TheFirstRunUserStillSeesTheCommands(unittest.TestCase):
    def test_it_is_inlined_not_hidden(self):
        self.assertIn(FIRSTRUN, APP)
        i = APP.index(FIRSTRUN)
        self.assertIn("!activeUser", APP[max(0, i - 160):i],
                      "这一块不再只给没建过档的人")
        self.assertIn("<CommandBook", APP[i:i + 1200])

    def test_only_the_spine_is_inlined(self):
        """**2026-08-24：内联的从全集改成脊梁三条。**

        20 条摊给还没建档的人，其中能敲的只有 `/job-setup` 和 `/job-user`
        （实测拿空快照渲染：那张表从 220px 一直铺到页面底部）。
        """
        i = APP.index(FIRSTRUN)
        self.assertIn("spineOnly", APP[i:i + 1200])

    def test_the_button_stays_open_for_them(self):
        """**这条 2026-08-24 反过来了，理由跟着变。**

        原来它挡着没建档的人（`&& !!activeUser`），理由是「否则内联的和
        按钮里的两份会同时出现」。现在内联的只剩脊梁三条 —— 两份不再重复，
        而全集**必须有地方进**，否则那 17 条对他就是不存在的。
        """
        self.assertNotIn("activeUser", desk_entry(APP, "cmds"))

    def test_the_reason_is_written_down(self):
        i = APP.index("还没建过档的人：命令表直接摊开")
        seg = flat(APP[i:i + 500])
        self.assertRegex(seg, r"自动弹一个 Modal 比不弹更糟")


class ThePageGotShorter(unittest.TestCase):
    def test_the_body_still_has_what_matters(self):
        for key in ("nextstep", 'key: "shelf"', "shortlist"):
            with self.subTest(key=key):
                self.assertIn(key, APP)

    def test_the_bar_sits_above_the_lists(self):
        """按钮那一排要在名单之前 —— 告警靠它露头。"""
        self.assertLess(APP.index('className="deskbar"'),
                        APP.index('key: "shelf"'))


if __name__ == "__main__":
    unittest.main()
