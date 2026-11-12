# -*- coding: utf-8 -*-
"""催进度那张形态表按平台分，而一个猎聘的猎头岗同时命中两行。

原来那四行是**并列**的：

    BOSS 直聘            即时聊天框
    猎聘 / 智联 / 前程    站内私信
    邮件（猎头多走这条）   有主题行
    内推 / 认识的人       私聊

一个猎聘的猎头岗既是「猎聘」也是「猎头」，**表里没有先后，执行者只能猜**。
实测活动用户 2026-08-23：该催的 75 条里 **38 条**（过半）落在这个二义上。

发送侧早就把这件事分好了（`_cli.send_hint`：猎头一律先按「找得到人」走，
其余按平台），而催这一侧还停在只按平台。同一个仓库两套模型，
而它们说的是同一批投递的同一件事。

所以把第一行改成**分流**（是不是猎头代招），其余三行退到「直招」那一层。
判据不必新写：`followups.agency_map` 已经把这一列算好了，
`followups.py` 的分组用的就是它。

判不出来时（`agency_map` 给 `None`，实测多在浏览器抓的那几家）**不猜** ——
按平台走并说一句，同这个仓库里那条「没判过 ≠ 判过是『不是』」。

## 2026-08-25：借了顺序，没借结论

这张表后来又拆过一次，理由记在 `test_the_follow_up_goes_where_the_greeting_went`。
一句话：上面说的「两侧同源」当时只兑现了一半 —— 猎头先行是借来了，而发送侧
那一侧的**结论**（`has_chat_box("猎聘", True) is True`，也就是「有聊天框」）
没借，表里仍然写着猎头走邮件。本文件下面那条 `test_the_send_side_uses_the_same_model`
自己就断言着 `True`，**它一直在证明表是错的，只是没人去读那个断言**。

所以这份守卫里两处跟着改：表头锚点（`| 平台 |` → `| 你手上有什么 |`），
以及「先按这一行」那个措辞（分流仍在，只是不再用那四个字表达）。
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402
import followups as F  # noqa: E402

OUTCOME = (ROOT / "workflows" / "job-outcome.md").read_text(encoding="utf-8")


def _table() -> str:
    # 表头 2026-08-25 从「| 平台 |」改成「| 你手上有什么 |」—— 分的本来就不是
    # 平台，是**你现在够得着他的那条路**（见本文件抬头）。
    i = OUTCOME.index("| 你手上有什么 | 形态 | 长度 |")
    m = re.search(r"^\d+\. ", OUTCOME[i:], re.M)
    return OUTCOME[i:i + (m.start() if m else 2500)]


class TheAgencyRowComesFirst(unittest.TestCase):
    def test_the_first_row_is_the_split(self):
        rows = [ln for ln in _table().splitlines()
                if ln.strip().startswith("|") and "---" not in ln]
        self.assertGreaterEqual(len(rows), 5, "表被改短了")
        self.assertIn("猎头", rows[1], "第一行不再是「是不是猎头」这个分流")
        self.assertIn("猎头", rows[2], "猎头那一档该是两行（有联系方式 / 只有会话）")

    def test_it_says_it_wins(self):
        """并列的一行和「先看是不是猎头」是两回事。

        措辞 2026-08-25 从「先按这一行」换成了「先看是不是猎头」——
        猎头拆成两行之后，「这一行」指不到唯一的一行了。判的是**分流还在**，
        不是那四个字还在。
        """
        self.assertRegex(_table(), r"分流仍然是「先看是不是猎头」")

    def test_the_platform_rows_are_scoped_to_direct_hire(self):
        """不标「直招」的话，那两行仍然会去抢猎头岗。"""
        seg = _table()
        for p in ("BOSS 直聘", "猎聘 / 智联 / 前程"):
            with self.subTest(platform=p):
                i = seg.index(p)
                self.assertIn("直招", seg[i:i + 30], f"{p} 那一行没限定在直招")

    def test_the_old_parallel_email_row_is_gone(self):
        """「邮件（猎头多走这条）」作为**并列**的一行正是二义的来源。"""
        self.assertNotIn("| 邮件（猎头多走这条）", _table())

    def test_the_ambiguity_is_written_down(self):
        """这一行看着像多余的表头，理由必须挨着写。"""
        seg = _table()
        self.assertRegex(seg, r"不是并列的第五种渠道")
        self.assertIn("容易落在这个二义上", seg)

    def test_unjudged_does_not_guess(self):
        seg = _table()
        self.assertRegex(seg, r"判不出是不是猎头|没判出是猎头还是直招")
        self.assertRegex(seg, r"\*\*不猜\*\*|不猜")

    def test_the_other_rows_survive(self):
        """BOSS 的「2-3 句」和内推那一行答的是别的问题，不许被这次改动带掉。"""
        seg = _table()
        self.assertIn("2-3 句", seg)
        self.assertIn("内推 / 认识的人", seg)


class TheJudgementIsNotReinvented(unittest.TestCase):
    def test_the_doc_points_at_the_existing_column(self):
        self.assertIn("agency_map", _table(), "没说清这一列已经算好了")

    def test_that_column_really_exists(self):
        self.assertTrue(hasattr(F, "agency_map"))

    def test_the_send_side_uses_the_same_model(self):
        """两侧同源 —— **顺序和结论都要同源**。

        原来这条只验了顺序（猎头先行）就算数，而下面这三个断言其实一直在说
        「猎头 = 有聊天框」；表里却写着猎头走邮件。同源了一半，
        比不同源更难发现：断言全绿。
        """
        self.assertIs(_cli.has_chat_box("猎聘", True), True)
        self.assertIs(_cli.has_chat_box("猎聘", False), False)
        self.assertIsNone(_cli.has_chat_box("猎聘", None))
        seg = _table()
        self.assertIn("send_hint", seg, "没指向发送侧那份判据")
        # 结论也要对上：猎头那一档必须有「聊天框」这一支。
        self.assertRegex(seg, r"猎头，只有平台会话")

    def test_the_grouping_in_the_tool_already_splits_this_way(self):
        """`followups.py` 的分组就是按猎头/直招分的 —— 文档跟它对齐，
        而不是反过来让用户在终端看到一种分法、在文档里读到另一种。"""
        src = (ROOT / "tools" / "followups.py").read_text(encoding="utf-8")
        self.assertIn("猎头代招 —— 催顾问", src)
        self.assertIn("企业直招 —— 催 HR", src)


if __name__ == "__main__":
    unittest.main()
