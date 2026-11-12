# -*- coding: utf-8 -*-
"""催 38 个猎头之前，没有任何地方说过「先看一眼邮箱」。

`followups.py` 把该催的清单切成两组，而**猎头那一组恰好就是邮件够得着的那半边**。
`job-gmail-sync.md` 开头那张渠道表自己写着：

    BOSS 直聘        站内聊天框，全程不发邮件      完全看不见
    猎聘 · 猎头代招   邮件 / 微信居多              看得见
    猎聘 · 企业直招   站内信为主                  多半看不见

实测活动用户 2026-08-23：该催的 75 个里 **38 个是猎头**，正好过半。而
`/job-gmail-sync` 在整个仓库里只出现在面板的命令总览和几处交叉引用里 ——
**没有任何一处说过它该在催进度之前跑。**

代价不是「多跑一条命令」：对面已经回过邮件、而你没记，这时候再发一条
「想问下进度」，在顾问那儿是减分的；而且那封回信里往往就有你要问的答案
（岗位还在不在、用人方什么反馈 —— 正是同一份文档让你去问的那两条）。

没有 Gmail 读取能力时照常催，但要说一句「邮件那一路没查过」——
同这个仓库那条「『没查』和『查过没有』是两件事」。
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import followups as F  # noqa: E402

OUTCOME = (ROOT / "workflows" / "job-outcome.md").read_text(encoding="utf-8")
GMAIL = (ROOT / "workflows" / "job-gmail-sync.md").read_text(encoding="utf-8")


def _seg() -> str:
    """**只切猎头那一块。**

    原来一路切到「该催哪几个」，中间后来长出了姊妹条
    （「直招那批，催之前先看一眼投递记录页」，它自带一张两行的小表）——
    于是「这一段里不许有表格」那条把**别人的**表当成了抄件。
    那条断言防的是把 `job-gmail-sync.md` 的渠道表抄过来，
    不是禁止这一节出现任何表格。
    """
    i = OUTCOME.index("**猎头那批，催之前先看一眼邮箱。**")
    for anchor in ("**直招那批，催之前先看一眼投递记录页。**",
                   "**该催哪几个 —— 用工具算"):
        j = OUTCOME.find(anchor, i)
        if j != -1:
            return OUTCOME[i:j]
    raise AssertionError("找不到猎头那一块的结尾")


class TheSyncComesFirst(unittest.TestCase):
    def test_the_step_exists(self):
        self.assertIn("**猎头那批，催之前先看一眼邮箱。**", OUTCOME,
                      "催进度那一支仍然直接开始起草")

    def test_it_is_before_the_list(self):
        """摆在算清单之后就晚了 —— 那时候名单已经出来了。"""
        self.assertLess(OUTCOME.index("**猎头那批，催之前先看一眼邮箱。**"),
                        OUTCOME.index("**该催哪几个 —— 用工具算"))

    def test_it_gives_both_commands_in_order(self):
        seg = _seg()
        self.assertIn("/job-gmail-sync", seg)
        self.assertIn("python tools/followups.py --all", seg)
        self.assertLess(seg.index("/job-gmail-sync"),
                        seg.index("python tools/followups.py"),
                        "两条命令的先后写反了")

    def test_it_says_why_the_two_groups_differ(self):
        """不写清「猎头那组才是邮件够得着的」，读者会以为这一步对谁都一样。"""
        seg = " ".join(_seg().split())
        self.assertIn("猎头那一组恰好就是邮件够得着的那半边", seg)
        self.assertIn("全程不发邮件", seg, "没引 BOSS 那一行做对照")

    def test_it_carries_the_measured_split(self):
        seg = " ".join(_seg().split())
        self.assertIn("猎头那一组恰好就是邮件够得着的那半边", seg)

    def test_it_names_the_real_cost(self):
        """「多跑一条命令」不足以让人照做。要说清催错了会怎样。"""
        seg = " ".join(_seg().split())
        self.assertRegex(seg, r"在顾问那儿是减分的")
        self.assertRegex(seg, r"那封回信里往往就有你要问的答案")

    def test_it_degrades_without_gmail(self):
        """没有 Gmail 能力时不许卡住 —— 同能力对照表那条规矩。"""
        seg = " ".join(_seg().split())
        self.assertIn("照常往下催", seg)
        self.assertIn("邮件那一路没查过", seg, "跳过了却不说，就成了「查过没有」")

    def test_it_says_direct_hire_is_unaffected(self):
        """直招那 37 个本来就多半不走邮件 —— 不写清会让人以为这一步是全局前置。"""
        self.assertRegex(" ".join(_seg().split()), r"直招那一组不受影响")

    def test_it_does_not_copy_the_channel_table(self):
        """那张表的正本在 `job-gmail-sync.md`。抄过来两处就会各长各的。"""
        seg = _seg()
        # **引用要挨着那句主张。** 只验「文件名出现过」的话，这一段末尾
        # 还有一处「没有 Gmail 读取能力（见 …）」，删掉这处照样绿（变异实测）。
        i = seg.index("猎头那一组恰好就是邮件够得着的那半边")
        self.assertIn("job-gmail-sync.md", seg[i:i + 200],
                      "那句主张旁边没指出处")
        rows = re.findall(r"^\s*\|", seg, re.M)
        self.assertEqual(rows, [], "把渠道表抄过来了")


class TheChannelTableItStandsOnIsIntact(unittest.TestCase):
    """这一步借的是那张表的判据。表变了，理由就空了。"""

    def test_the_table_still_says_headhunters_use_email(self):
        i = GMAIL.index("| 渠道 | 回音一般走哪儿 |")
        seg = GMAIL[i:i + 700]
        self.assertRegex(seg, r"猎头代招.*看得见")

    def test_the_table_still_says_boss_never_does(self):
        i = GMAIL.index("| 渠道 | 回音一般走哪儿 |")
        seg = GMAIL[i:i + 700]
        self.assertRegex(seg, r"BOSS 直聘.*全程不发邮件")

    def test_the_sync_still_states_its_precondition(self):
        """没有 Gmail 能力时怎么办，正本在那边 Step 0。"""
        self.assertIn("## Step 0：前置条件", GMAIL)
        i = GMAIL.index("## Step 0：前置条件")
        self.assertRegex(GMAIL[i:i + 400], r"不可用 → 告知用户如何连接")

    def test_the_sync_still_admits_what_it_cannot_see(self):
        """这一步能成立，恰恰因为那边诚实地说了自己看不见什么。"""
        self.assertIn("## 先说清楚它看不见什么", GMAIL)


class TheGroupingThatMakesThisWorkStillExists(unittest.TestCase):
    def test_followups_still_splits_by_agency(self):
        src = (ROOT / "tools" / "followups.py").read_text(encoding="utf-8")
        self.assertIn("猎头代招 —— 催顾问", src)
        self.assertIn("企业直招 —— 催 HR", src)

    def test_the_judge_is_still_there(self):
        self.assertTrue(hasattr(F, "agency_map"))


class TheRestOfTheBranchIsUntouched(unittest.TestCase):
    def test_the_tool_is_still_the_one_that_decides_who_to_chase(self):
        """原有的规矩：该催哪几个用工具算，不要手算。"""
        self.assertIn("**该催哪几个 —— 用工具算，不要手算。**", OUTCOME)

    def test_the_two_thresholds_are_still_distinguished(self):
        """10 天催、30 天判失联 —— 两个数服务于两个时刻，别被这一步搅混。"""
        self.assertRegex(OUTCOME, r"默认的 10 天\*\*故意\*\*早于")

    def test_the_max_two_followups_rule_survives(self):
        self.assertIn("少于**两次**", OUTCOME)

    def test_the_agency_questions_survive(self):
        """上一轮加的那两问 —— 而它们正是邮件里常常已经答了的。"""
        self.assertIn("这个岗现在还在招吗", OUTCOME)
        self.assertIn("用人方那边有没有给到反馈", OUTCOME)


class TheToolDoesNotDecideItIsTimeToChase(unittest.TestCase):
    """催不催是用户的判断 —— 工具不按天数替他提议。

    2026-08-29 用户裁定（`AGENTS.md`「跟进归用户，工具不催」，原话）：

    > **任何地方都不要把「催一遍」印成下一步。** ……
    > `/job-outcome followup` 这条命令保留，他想催的时候敲得到。
    > **撤的是「工具替他决定该催了」**，不是这个能力。

    那次改的是 `doctor.py` 与 `build_dashboard.py`（终端与面板的「下一步」），
    钉它的守卫扫的也是那两个工具 —— **一条都不扫 `workflows/`**。
    于是 `/job-outcome` 自己那一支活了下来：裸命令列完在跑投递表之后，
    「安静满 10 天、且跟进次数少于两次」就自动加一句
    「这几个已经没动静了——要不要我起草一条跟进？」。

    那正是「工具替他决定该催了」。2026-09-02 通读时发现，同 `JD_READERS` /
    `GUARDS` / `WRITERS` 那三次一个形状：**规则立在总纲，落在某一面的那处漏了。**

    分界照裁定走：**数据照列**（安静几天、跟过几次是统计，用户自己看得出），
    **动作不替他决定**（不主动提议起草），而 `followup` 参数照旧。
    """

    def _step1(self) -> str:
        i = OUTCOME.index("## Step 1")
        return OUTCOME[i:OUTCOME.index("## Step 2", i)]

    def _body(self, seg: str) -> str:
        return "\n".join(l for l in seg.splitlines()
                         if not l.lstrip().startswith(">"))

    def test_the_columns_are_still_there(self):
        """控制用例：统计那两列**不许**跟着一起撤 —— 撤的是动作，不是数据。"""
        b = self._body(self._step1())
        for col in ("安静了几天", "已发过几次跟进"):
            with self.subTest(col=col):
                self.assertIn(col, b, f"「{col}」这一列没了 —— 撤过头了")

    def test_it_does_not_offer_to_draft_one(self):
        b = self._body(self._step1())
        self.assertNotIn(
            "就在表下面加一句", b,
            "`/job-outcome` 裸命令又会自动提议起草跟进了 —— "
            "那是工具替用户决定该催了（`AGENTS.md`「跟进归用户，工具不催」）")
        self.assertRegex(
            b, r"不要在表下面加一句|不主动提议",
            "撤了那句提议，却没写明「不要加」—— 下一轮会被当成漏写补回去")

    def test_the_explicit_entry_survives(self):
        """`/job-outcome followup` 是保留的 —— 撤的是提议，不是能力。"""
        self.assertIn("followup", OUTCOME, "跟进那条路整个没了")
        i = OUTCOME.index("## Step 2b")
        seg = self._body(OUTCOME[i:i + 400])
        self.assertIn("`followup` 参数", seg,
                      "Step 2b 没说清它现在只从 `followup` 参数进")


if __name__ == "__main__":
    unittest.main()
