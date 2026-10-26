# -*- coding: utf-8 -*-
"""首屏 1061px 全是铺垫，而「可以投的岗位」只有 6 个。

用户 2026-08-24 的原话：

> dashboard 应该主要出现职位吧，其他非必要信息是不是都可以收进 modal。
> 你看看当前的状态，要保持首屏的简易，让新用户也能轻松使用。

浏览器里量的（视口 1271px）：

    rail          100 → 322   222px   五格等高，每格挂两行说明 + 命令
    三条提醒       336 → 474   122px
    下一步         489 → 695   206px   ← 一堵 8 行的墙
    deskbar       707 → 910   203px   七颗按钮各带一句结论，排成两行
    mat-gap       933 → 1049  116px
    「可以投的岗位」1061                ← 900px 的笔记本上整个名单在首屏之外

## 那堵墙是逐轮加出来的

「下一步」那段话不是一次写成的：催一遍 → 猎头/直招拆分 → 会话打招呼 →
季节 → 手上备好的别等 → 排最久的那几个 → 旺季补新的 → 你把某个渠道关掉了。
**每一条单看都该说，叠起来就是墙。**

## 砍的是位置，不是内容

    下一步    只留第一句（现状）+ 那条命令；其余点「为什么」原地展开
    rail      每格留命令（一行），两行散文进 `title`
    deskbar   那句结论只留给要你处理的那几颗
    顺序      「下一步」提到三条提醒**之前** —— 这一页存在的理由就是那一句

量到的：**1061 → 771px**，「下一步」从 489 提到 282。四行职位进了首屏。

## rail 上的命令不许跟着散文一起收走

`test_pipeline_counts` 那条守的就是它，理由是实测来的：用户问
「可以投的不多了，怎么让你继续抓取」时，五格就在他眼前，而**每一格该敲什么
从来没写在格子上**。所以这一版留命令、收散文 —— 命令一行 ≈ 22px。
"""
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from jsx import FIRSTRUN, desk_entry  # noqa: E402
APP = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "src" / "theme" / "cockpit.css").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*(?:>|#:?|//:?|\*)\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


class TheHooksStayAboveTheEarlyReturn(unittest.TestCase):
    """**这一条最贵。** 违反它构建是绿的，页面是白的。"""

    def test_the_split_hook_runs_unconditionally(self):
        self.assertLess(APP.index("const [nsHead, nsWhy] = useMemo("),
                        APP.index("  if (snap === null) {"),
                        "hook 排在提前 return 后面 —— 页面会整个白屏")

    def test_the_open_state_hook_too(self):
        self.assertLess(APP.index("const [nsOpen, setNsOpen] = useState("),
                        APP.index("  if (snap === null) {"))

    def test_the_incident_is_recorded(self):
        i = APP.index("const [nsHead, nsWhy] = useMemo(")
        seg = flat(APP[max(0, i - 900):i])
        self.assertRegex(seg, r"必须留在下面那个提前 `return` 之前")
        self.assertRegex(seg, r"页面整个空白")
        self.assertRegex(seg, r"而构建是绿的")


class TheNextStepIsOneLine(unittest.TestCase):
    def test_it_splits_at_the_first_sentence(self):
        i = APP.index("const [nsHead, nsWhy] = useMemo(")
        body = APP[i:i + 500]
        self.assertIn('t.indexOf("。")', body)

    def test_an_over_long_first_sentence_is_left_alone(self):
        """宁可长一次，也不要把一句话拦腰截断。"""
        i = APP.index("const [nsHead, nsWhy] = useMemo(")
        self.assertIn("i + 1 > 60", APP[i:i + 500])

    def test_no_full_stop_means_no_split(self):
        i = APP.index("const [nsHead, nsWhy] = useMemo(")
        self.assertIn("if (i < 0", APP[i:i + 500])

    def test_only_the_head_is_on_the_first_screen(self):
        self.assertIn('<span className="nextstep-text">{nsHead}</span>', APP)

    def test_the_command_stays_visible(self):
        """动作在命令上 —— 收掉理由不能把它一起收走。

        命令前多了一小句「发完记一笔」，说明这条 `/job-outcome` 是发完之后
        才敲的；窗口跟着包住这一段，但命令本身仍然必须在这块里。
        """
        i = APP.index('<span className="nextstep-text">{nsHead}</span>')
        seg = APP[i:i + 1200]
        self.assertIn("<Cmd>{nextStep.command}</Cmd>", seg)

    def test_the_rest_is_reachable(self):
        self.assertIn('{nsWhy && nsOpen && <p className="nextstep-why">{nsWhy}</p>}',
                      APP)

    def test_it_starts_collapsed(self):
        self.assertIn("const [nsOpen, setNsOpen] = useState(false);", APP)

    def test_the_toggle_says_both_directions(self):
        i = APP.index('className="nextstep-more"')
        self.assertRegex(APP[i:i + 300], r'nsOpen \? "收起" : "为什么"')

    def test_it_is_not_a_modal(self):
        """它和「下一步」是同一件事 —— 弹窗会把它变成「另一页」。"""
        i = APP.index("{/* ── 下一步：")
        seg = flat(APP[i:i + 1200])
        self.assertRegex(seg, r"不做成 Modal")

    def test_the_reason_is_recorded(self):
        i = APP.index("{/* ── 下一步：")
        seg = flat(APP[i:i + 1200])
        self.assertRegex(seg, r"206px、8 行")
        self.assertRegex(seg, r"砍的是位置，不是内容")
        self.assertIn("2026-08-24", seg)

    def test_the_toggle_is_not_dressed_as_an_action(self):
        """旁边那颗才是要他敲的东西 —— 两个长得一样会分掉注意力。"""
        i = CSS.index(".nextstep-more {")
        self.assertIn("background: none", CSS[i:i + 300])


class TheNextStepComesFirst(unittest.TestCase):
    def test_it_sits_above_the_warnings(self):
        """他原来要先读三段警告才看到那一句。"""
        self.assertLess(APP.index('<div className="nextstep">'),
                        APP.index("{pipeline.some((s) => (s.waiting ?? 0) > 0)"))

    def test_the_warnings_are_all_still_there(self):
        """一条都没删 —— 只是排到它后面。"""
        n = APP.count('className="parked-note"')
        self.assertGreaterEqual(n, 3, f"提醒少了，现在只有 {n} 条")

    def test_the_reorder_is_explained(self):
        i = APP.index("{/* **「下一步」排在那几条提醒之前。**")
        seg = flat(APP[i:i + 500])
        self.assertRegex(seg, r"这一页存在的理由就是那一句")
        self.assertRegex(seg, r"提醒一条没删")


class TheRailKeepsItsCommands(unittest.TestCase):
    """散文可以收，命令不行 —— 那是 `test_pipeline_counts` 用实测换来的。"""

    def test_every_cell_still_renders_its_command(self):
        i = APP.index('{s.cmd && (')
        self.assertIn("<Cmd>{s.cmd}</Cmd>", APP[i:i + 300])

    def test_the_prose_moved_to_the_title(self):
        """收起来不等于删掉。"""
        self.assertIn("title={s.does || undefined}", APP)

    def test_the_prose_is_no_longer_inline(self):
        self.assertNotIn('<span className="rail-does">', APP)

    def test_the_lesson_it_must_not_break_is_quoted(self):
        i = APP.index("{/* **每一格都留着「该敲什么」")
        seg = flat(APP[i:i + 900])
        self.assertRegex(seg, r"怎么让你继续抓取")
        self.assertRegex(seg, r"从来没写在格子上")

    def test_the_equal_height_trap_is_recorded(self):
        """一格 96px 把五格都撑到 220 —— 下一个人会想再塞点东西进去。"""
        i = APP.index("{/* **每一格都留着「该敲什么」")
        seg = flat(APP[i:i + 900])
        self.assertRegex(seg, r"五格是等高\s*栅格")
        self.assertRegex(seg, r"每一格都撑到 220px")


class TheDeskbarOnlyShoutsWhenItMatters(unittest.TestCase):
    def test_the_note_is_gated_on_the_alarm(self):
        self.assertIn('{d.note && (d.alarm || (d.chips ?? []).length > 0) && (',
                      APP)

    def test_it_reuses_the_existing_alarm_judgement(self):
        """`d.alarm || d.chips` 本来就在决定整颗按钮点不点亮 —— 别另判一次。"""
        i = APP.index('{d.note && (d.alarm || (d.chips ?? []).length > 0) && (')
        seg = flat(APP[max(0, i - 700):i])
        self.assertRegex(seg, r"判据不新写")

    def test_nothing_is_lost_in_the_modal(self):
        i = APP.index('{d.note && (d.alarm || (d.chips ?? []).length > 0) && (')
        seg = flat(APP[max(0, i - 700):i])
        self.assertRegex(seg, r"点开\s*弹窗里一个字都没少")

    def test_the_bar_still_sits_above_the_list(self):
        """告警靠它露头 —— 这条是既有的，别被这一轮挪没了。"""
        self.assertLess(APP.index('className="deskbar"'),
                        APP.index('key: "shelf"'))


class TheNewUserScreenIsNotAWallOfDeadLinks(unittest.TestCase):
    """用户那句还有一半：**「让新用户也能轻松使用」**。

    拿一份空快照渲染（2026-08-24，只在临时目录里起了个静态服务，
    没碰他的数据）：五格全是 0，却各挂一条命令 —— `/job-rank`、`/job-apply`、
    `/job-outcome`、`/job-interview` **一条都敲不动**（没资料、没岗），
    而正确答案只有一条 `/job-setup`，就在下面那句「下一步」里。
    再往下是 20 条命令的全集，从 220px 一直铺到页面底部。

    `AGENTS.md`：「一条引导对应**一条**命令。给两条以上，用户就要先做一次
    选择 —— 那正是引导要替他省掉的那一步。」
    """

    def test_a_cell_with_nothing_in_it_gives_no_command(self):
        self.assertIn("{s.cmd && (shown > 0 || nudged) && (", APP)

    def test_the_two_signals_are_the_existing_ones(self):
        """`shown` 和 `nudged` 都是这一段本来就有的 —— 不新造判据。"""
        i = APP.index("{s.cmd && (shown > 0 || nudged) && (")
        head = APP[:i]
        self.assertIn("const actionable = Boolean(key) && shown > 0;", head)
        self.assertIn("const nudged =", head)

    def test_a_populated_cell_still_carries_it(self):
        """有数据的用户五格照旧写着该敲什么 —— `test_pipeline_counts` 守的那条。"""
        i = APP.index("{s.cmd && (shown > 0 || nudged) && (")
        self.assertIn("<Cmd>{s.cmd}</Cmd>", APP[i:i + 300])

    def test_the_reason_is_recorded(self):
        i = APP.index("{/* **还敲不动的格子不给命令。**")
        seg = flat(APP[i:i + 1100])
        self.assertRegex(seg, r"一条都敲不动")
        self.assertRegex(seg, r"一条引导对应\*\*一条\*\*命令")
        self.assertIn("2026-08-24", seg)

    def test_the_first_run_book_is_spine_only(self):
        i = APP.index(FIRSTRUN)
        self.assertIn("spineOnly", APP[i:i + 1200])

    def test_the_full_set_is_still_reachable(self):
        """只剩三条不等于把另外 17 条藏了 —— 那颗按钮对他也开着。"""
        self.assertNotIn("activeUser", desk_entry(APP, "cmds"))

    def test_the_component_defaults_to_the_full_set(self):
        """`spineOnly` 要是可选的 —— 别让别的调用点跟着变。"""
        book = (ROOT / "web" / "src" / "components"
                / "CommandBook.tsx").read_text(encoding="utf-8")
        self.assertIn("spineOnly = false", book)
        self.assertIn("{!spineOnly && groups.map((g) => (", book)


class NothingWasQuietlyDeleted(unittest.TestCase):
    """这一轮只动位置。每一块都要还在。"""

    def test_the_five_step_rail_survives(self):
        self.assertIn('className="rail"', APP)

    def test_the_material_gap_survives(self):
        """两块 `mat-gap`（卡住的岗 / 材料缺口），两块都要在。"""
        self.assertEqual(APP.count('className="mat-gap"'), 2)

    def test_the_first_run_command_book_survives(self):
        """新用户那份摊开的命令表 —— 用户明确提到「让新用户也能轻松使用」。"""
        self.assertIn(FIRSTRUN, APP)
        self.assertIn("<CommandBook", APP[APP.index(FIRSTRUN):][:1200])

    def test_the_job_list_is_still_the_last_block(self):
        """比**最后**那一块 `mat-gap`（有两块，`index()` 只会给第一块）。"""
        self.assertLess(APP.rindex('className="mat-gap"'),
                        APP.index('<h2>可以投的岗位</h2>'))


if __name__ == "__main__":
    unittest.main()
