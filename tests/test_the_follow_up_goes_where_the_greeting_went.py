# -*- coding: utf-8 -*-
"""开场白发进了聊天框，而催的那条按规则要写成一封带主题行的信 —— 粘回同一个框。

`_cli.has_chat_box` 对**猎头代招一律返回「有聊天框」**（它的判据 1：猎头本人
可联系，平台不影响），`send_hint` 据此给这批岗印的是：

> 粘到和猎头顾问的对话框，直接发

也就是说，开场白是发进会话里的。而 `job-outcome.md` Step 2b 那张形态表原来
只有一行管猎头：「猎头有自己的联系方式（邮件 / 微信居多），**有主题行**，
复用这次投递的那句抬头 | **60-120 字**」。**同一个岗，发的时候是聊天框，
催的时候变成一封信。** 而那张表自己下一行就写着：60-120 字在聊天框里
「是一堵墙，多数人不会读完」。

实测活动用户 2026-08-25：

    85 笔投递里「猎头 + 有聊天框」        44 笔（52%）
    `followups.py` 当天该催的猎头代招      38 个（抬头标着「性价比最高，先做」）

## 根子：把「回音走哪儿」当成了「催的时候发哪儿」

`job-gmail-sync.md` 那张渠道表的列头是「**回音一般走哪儿**」，说的是顾问
**回你**的时候用什么（猎头「邮件 / 微信居多」）。而催的时候要用的是
**你现在够得着他的那条路**。**该催的按定义就是还没回过的那批** ——
没回过的人，多半没给过你邮箱或微信。

## 借了顺序，没借结论

`test_the_followup_table_has_a_precedence` 那条守卫里一直写着
`assertIs(_cli.has_chat_box("猎聘", True), True)` —— **它一直在证明表是错的，
只是那个断言从没被读出这层意思**：当时对齐的只是「猎头先行」这个顺序，
发送侧的**结论**没跟过来。同源了一半，比不同源更难发现，因为断言全绿。
"""
import csv
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402
import tracker as tk  # noqa: E402

OUT = (ROOT / "workflows" / "job-outcome.md").read_text(encoding="utf-8")
GM = (ROOT / "workflows" / "job-gmail-sync.md").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*(?:>|#:?)\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


def table() -> str:
    i = OUT.index("| 你手上有什么 | 形态 | 长度 |")
    m = re.search(r"^\d+\. ", OUT[i:], re.M)
    return OUT[i:i + (m.start() if m else 3200)]


def rows() -> list:
    return [ln.strip() for ln in table().splitlines()
            if ln.strip().startswith("|") and "---" not in ln][1:]


class TheTableAsksTheRightQuestion(unittest.TestCase):
    def test_the_header_is_not_the_platform(self):
        """**分的本来就不是平台。** 表头写「平台」，人就会照平台填。"""
        self.assertIn("| 你手上有什么 | 形态 | 长度 |", OUT)
        self.assertNotIn("| 平台 | 形态 | 长度 |", OUT)

    def test_it_says_so_in_words(self):
        i = OUT.index("**先问一句：这条跟进要发进哪儿？**")
        s = flat(OUT[i:i + 200])
        self.assertRegex(s, r"不是「这个岗在哪个平台」")
        self.assertRegex(s, r"\*\*你手上真有的那条联系方式\*\*")


class TheAgencyTierIsSplitByChannel(unittest.TestCase):
    def _agency(self):
        return [r for r in rows() if "猎头" in r]

    def test_there_are_two_agency_rows(self):
        self.assertEqual(len(self._agency()), 2,
                         "猎头那一档该是两行：有联系方式 / 只有会话")

    def test_the_chat_row_is_short(self):
        """**这是修掉的那一处。** 60-120 字粘进聊天框就是一堵墙。"""
        r = next(r for r in self._agency() if "只有平台会话" in r)
        self.assertIn("2-3 句", r)
        self.assertIn("没有主题行", r)

    def test_the_chat_row_is_the_common_case(self):
        """不说这句，执行者会默认走上面那行 —— 而那行才是少数。"""
        r = next(r for r in self._agency() if "只有平台会话" in r)
        self.assertRegex(flat(r), r"从没回过 —— 该催的多半是这一档")

    def test_the_mail_row_survives_but_is_conditional(self):
        """有邮箱/微信时那条路是对的 —— 别把它一起删了。"""
        r = next(r for r in self._agency() if "邮箱" in r)
        self.assertIn("60-120 字", r)
        self.assertIn("主题行", r)
        self.assertRegex(flat(r), r"他回过一次，后来断了")


class TheReasonIsRecorded(unittest.TestCase):
    def test_it_names_the_send_side_judge(self):
        s = flat(table())
        self.assertIn("_cli.has_chat_box", s)
        self.assertIn("send_hint", s)

    def test_it_quotes_what_the_send_side_prints(self):
        self.assertRegex(flat(table()), r"粘到和猎头顾问的对话框")

    def test_the_send_side_really_prints_that(self):
        self.assertEqual(_cli.send_hint("猎聘", True), "粘到和猎头顾问的对话框，直接发")

    def test_the_send_side_really_says_chat(self):
        self.assertIs(_cli.has_chat_box("猎聘", True), True)

    def test_it_points_at_the_self_contradiction(self):
        """表自己下一行就写着 60-120 字在聊天框里是一堵墙。"""
        self.assertRegex(flat(table()), r"\*\*表自己下一行就写着\*\*")
        self.assertIn("是一堵墙，多数人不会读完", table())

    def test_it_carries_the_measurement(self):
        s = table()
        self.assertIn("猎头岗位是在平台聊天框直接沟通的", s)

    def test_it_names_the_root_cause(self):
        s = flat(table())
        self.assertRegex(s, r"「\*\*回音一般走哪儿\*\*」")
        self.assertRegex(s, r"该催的按定义就是还没回过的那批")

    def test_the_column_it_quotes_really_says_that(self):
        row = next(l for l in GM.splitlines() if l.startswith("| 渠道 |"))
        self.assertIn("回音一般走哪儿", row)

    def test_the_agency_row_it_quotes_really_says_that(self):
        row = next(l for l in GM.splitlines() if l.startswith("| 猎聘 · 猎头代招"))
        self.assertIn("邮件 / 微信居多", row)


class TheTwoQuestionsStillFit(unittest.TestCase):
    """长度规则和内容规则在这一档撞上了 —— 不说清，执行者会砍掉一个问题。"""

    def test_it_says_they_fit(self):
        s = flat(table())
        self.assertRegex(s, r"2-3 句放得下上面第 3 点要的那两问")
        self.assertRegex(s, r"\*\*那两问就是那 2-3 句\*\*")

    def test_it_says_what_to_cut_instead(self):
        self.assertRegex(flat(table()), r"\*\*该砍的是铺垫，不是问题\*\*")

    def test_those_two_questions_still_exist(self):
        s = flat(OUT)
        self.assertRegex(s, r"加「这个岗现在还在招吗」和「用人方那边有没有给到反馈」")

    def test_the_direct_hire_side_still_gets_neither(self):
        """HR 答不了第二问 —— 那条区分不许被这次改动带掉。"""
        self.assertRegex(flat(OUT), r"HR 答不了第二问 —— \*\*他自己就是用人方\*\*")


class TheNeighbouringRulesSurvive(unittest.TestCase):
    def test_the_platform_rows_are_still_scoped_to_direct_hire(self):
        for p in ("BOSS 直聘", "猎聘 / 智联 / 前程"):
            with self.subTest(platform=p):
                r = next(r for r in rows() if r.startswith(f"| **{p}**")
                         or r.startswith(f"| {p}"))
                self.assertIn("直招", r)

    def test_the_referral_row_survives(self):
        self.assertTrue(any("内推 / 认识的人" in r for r in rows()))

    def test_unjudged_still_does_not_guess(self):
        s = flat(table())
        self.assertRegex(s, r"判不出是不是猎头时")
        self.assertRegex(s, r"\*\*不猜\*\*")

    def test_the_precedence_note_survives(self):
        self.assertRegex(flat(table()), r"分流仍然是「先看是不是猎头」")

    def test_the_sync_before_nudge_rule_survives(self):
        """先同步再催 —— 正是它保证了「该催的」多半真没回过。"""
        s = flat(OUT)
        self.assertRegex(s, r"所以顺序是\*\*先同步再催\*\*")


class TheSignalItLeansOnIsReal(unittest.TestCase):
    """现算：他这批投递真的过半是「猎头 + 有聊天框」。"""

    def _split(self):
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        u = ROOT / "users" / _cli.pick_user("", root=ROOT)
        f, t = u / "job_scraper" / "seen_jobs.json", u / "job_search_tracker.csv"
        if not (f.is_file() and t.is_file()):
            self.skipTest("还没有职位库或投递记录")
        seen = _cli.seen_of(_cli.load_json_stamped(f)[0])
        byurl = {e.get("url"): e for e in seen.values()
                 if isinstance(e, dict) and e.get("url")}
        rows_ = list(csv.DictReader(t.open(encoding="utf-8-sig")))
        if len(rows_) < 20:
            self.skipTest("投递太少")
        n_chat_agency = 0
        for r in rows_:
            e = byurl.get((r.get("source") or "").strip()) or {}
            hh = _cli.via_headhunter(e) if e else None
            if hh is True and _cli.has_chat_box(tk.channel_of(r), hh) is True:
                n_chat_agency += 1
        return n_chat_agency, len(rows_)

    def test_the_chat_agency_group_is_the_majority(self):
        """**支点。** 它占比很小时，这一条改的是边角。"""
        n, total = self._split()
        self.assertGreater(n, total * 0.3,
                           f"「猎头 + 有聊天框」只有 {n}/{total} —— 这一节的论点要重看")

    def test_the_old_rule_would_have_hit_every_one_of_them(self):
        """旧表对猎头**没有分支** —— 命中的就是全部，不是一部分。"""
        for hh_portal in ("猎聘", "BOSS 直聘", "智联招聘", ""):
            with self.subTest(portal=hh_portal):
                self.assertIs(_cli.has_chat_box(hh_portal, True), True)


if __name__ == "__main__":
    unittest.main()
