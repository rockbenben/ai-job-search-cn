# -*- coding: utf-8 -*-
"""零起点的「下一步」给的是脊梁那条命令，不是它的分解。

## 判据

`AGENTS.md`「一次跑到头：只有三条命令」：

    /job-setup → /job-auto →（你自己发）→ /job-outcome

紧跟着一句：**「别把这条脊梁说成四步……多教一步的代价不是多敲一次，
是让人以为不敲就会漏东西。」**

而 2026-08-30 之前，自检与面板在「资料好了、一个岗都还没抓」时印的是
`/job-scrape`。它抓完确实会自动评分，但**不出材料** —— 敲完手上是一排
没材料的岗，还得再敲一条才走得到能发的那一步。

## 「补货」那条由用户裁定点名

2026-08-29（`AGENTS.md`「跟进归用户，工具不催」）：

> **终端与面板的「下一步」都不提投递与回音**，状态照常按流水线判：
> 有材料没发 → 先发；没有 → `/job-auto` 接着抓。

而那一支原来写的是「投出去了，在等回复。下一步：跑 `/job-scrape` 补充名单」
—— **前半句正是裁定不许提的，后半句给的命令也不是裁定点名的那条**。
同一个文件上面那支已经写对了（「名单见底了再去 `/job-auto` 补货」）：
两支相邻，答案不同。

## 部分态不在此列

「有岗没评」→ `/job-rank`、「评了没材料」→ `/job-apply` 照旧。
那是**恢复**，不是新用户的路 —— 脊梁管的是零起点那一步。
"""
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
from _srcscan import code_of  # noqa: E402
import build_dashboard as bd  # noqa: E402

AGENTS = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

#: 段落分隔。写成常量是因为这份文件由补丁脚本改过 ——
#: 字面反斜杠在 shell heredoc 里会被吃掉（见 `docs/finding-gaps.md`
#: 「第十把：把 markdown 渲染出来看」末段）。这里原来写的是
#: CONTRIBUTING「改脚本」，而全仓没有那一节 —— 指针从一开始就没落点。
NL = chr(10)


class TheDoctrineIsStillWrittenDown(unittest.TestCase):
    """判据没了，下面几条就只是三个人的口味之争。"""

    def test_the_spine_is_three_commands(self):
        i = AGENTS.index("## 一次跑到头")
        seg = AGENTS[i:i + 1200]
        self.assertIn("/job-auto", seg)
        self.assertIn("别把这条脊梁说成四步", seg)

    def test_the_restock_ruling_names_the_command(self):
        self.assertIn("没有 → `/job-auto` 接着抓", AGENTS)


class TheDocsSayTheSameThing(unittest.TestCase):
    """教程里那句「答完第一轮就能去 X」要和自检说的是同一条命令。

    2026-08-30 把零起点那条改成 `/job-auto` 时**只改了工具**。
    次日通读发现 README 还写着「答完第一轮就能去 `/job-scrape` 搜岗，
    第二轮够 `/job-rank` 排序」—— 而同一时刻自检说的是「下一步：跑 `/job-auto`」。

    那句话本身要讲的是**分档填资料**（填到哪一档就能做到哪一步），
    这个意思是对的；错的是它给三档各配了一条命令，
    正是 `AGENTS.md`「别把这条脊梁说成四步」点名的那件事。

    改法不是删掉分档，是**把档位和命令分开说**：
    三档仍然列出来，而跑的都是同一条 `/job-auto`。
    """

    README = (ROOT / "README.md").read_text(encoding="utf-8")

    def _staged(self) -> str:
        i = self.README.index("`/job-setup` 不必一次答完")
        return self.README[i:self.README.index(NL + NL, i)]

    def test_the_staged_sentence_names_the_spine(self):
        self.assertIn("/job-auto", self._staged(), "分档那句没提脊梁那条命令")

    def test_it_does_not_hand_out_one_command_per_stage(self):
        seg = self._staged()
        for cmd in ("/job-scrape", "/job-rank", "/job-apply"):
            with self.subTest(cmd=cmd):
                self.assertNotIn(cmd, seg,
                                 "又把某一档配上了 " + cmd + " —— 那是脊梁的分解")

    def test_the_setup_closing_names_the_spine_too(self):
        """**源头也要说同一条。** 这条守卫原来只钉 README —— 那是**摘要**。

        2026-09-02 实测：`job-setup.md` 的 Step 4 收尾与「设计原则」最后一条
        都还写着「下一步：`/job-scrape`」，而同一时刻 `doctor.py` 印的是
        「资料好了，还没搜过职位。下一步：跑 /job-auto」。

        位置最要紧：**那是新用户建完档最后读到的字**，自检那句要等下一次
        开会话才出现。改了工具、改了摘要，唯独没改原文。

        判据只看**收尾那一段**（Step 4 起）：全文别处提 `/job-scrape` 是正常的
        —— 四轮的停点仍然按档说话，`AGENTS.md`「资料没填完是分档的」
        原样引用并认可那几句。
        """
        t = (ROOT / "workflows" / "job-setup.md").read_text(encoding="utf-8")
        seg = t[t.index("## Step 4：确认，并给出下一步"):]
        self.assertIn("/job-auto", seg, "建完档的收尾没指向脊梁那条命令")
        # 收尾的命令块里不许再出现分解那几条
        i = seg.index("**下一步：**")
        blk = seg[i:i + 200]
        for cmd in ("/job-scrape", "/job-rank", "/job-apply"):
            with self.subTest(cmd=cmd):
                self.assertNotIn(
                    cmd, blk,
                    f"建完档给的下一步是 {cmd} —— 那是脊梁的分解，"
                    "自检同一状态印的是 /job-auto")

    def test_the_round_stops_are_left_alone(self):
        """**收窄不能把四轮的停点一起改掉。**

        `AGENTS.md`「资料没填完是分档的」把「够排序了 —— 跑 `/job-rank`
        就能看到带理由的排序名单」当成**守卫必须放行的邀请**原样引用。
        把它也改成 `/job-auto` 会和总纲打架，而且第一轮那档的资料
        本来就还不够 `/job-auto` 的 `rank` 门。
        """
        t = (ROOT / "workflows" / "job-setup.md").read_text(encoding="utf-8")
        head = t[:t.index("## Step 4：确认，并给出下一步")]
        # **锚到停点那一行本身。** 只查「head 里有没有 /job-rank」太松 ——
        # 那一段别处也提它（「缺任何一项，`/job-rank` 要么瞎猜」），
        # 于是把停点整句换掉，断言照样绿（变异当场照出来）。
        stop = [l for l in head.splitlines() if "够排序了" in l]
        self.assertTrue(stop, "第二轮那句「够排序了」的停点没了")
        self.assertIn(
            "/job-rank", stop[0],
            f"第二轮的停点不再点名 /job-rank：{stop[0].strip()[:60]} —— "
            "`AGENTS.md`「资料没填完是分档的」原样引用的就是这一句")

    def test_the_stages_are_still_there(self):
        """收窄不能把「分档填资料」这个真意思一起删掉。"""
        seg = self._staged()
        for w in ("搜岗", "排序打分", "出投递材料"):
            with self.subTest(w=w):
                self.assertIn(w, seg)


class ZeroStateGivesTheSpine(unittest.TestCase):

    @staticmethod
    def _counts(**kw):
        base = {"scraped": 0, "ranked": 0, "materials": 0, "applied": 0,
                "interviewing": 0}
        base.update(kw)
        return base

    def test_the_panel_says_job_auto(self):
        got = bd.next_step(self._counts(), True)
        self.assertEqual(got[1], "/job-auto",
                         f"零起点指的还是分解那条：{got}")

    def test_the_doctor_says_job_auto(self):
        seg = code_of("tools/doctor.py", "def next_step(")
        i = seg.index('if st.get("scraped", 0) == 0:')
        j = seg.index('if st.get("ranked", 0) == 0:')
        self.assertIn("/job-auto", seg[i:j], "零起点那一支指的还是分解那条")
        self.assertNotIn("/job-scrape", seg[i:j])

    def test_partial_states_still_name_their_own_command(self):
        """恢复态不受这条影响 —— 收窄错了会把两件事一起弄坏。"""
        self.assertEqual(
            bd.next_step(self._counts(scraped=5), True)[1], "/job-rank")


class TheRestockNudgeIsAlsoSpineDeep(unittest.TestCase):
    """「名单见底 → 去补货」那条**面板独有**的提前提醒，给的也得是 `/job-auto`。

    ## 为什么单列一条

    终端自检没有这个分支——它顺着流水线走到底就落到 `/job-auto`。面板有，
    因为 `build_dashboard.SHORTLIST_FLOOR` 那一支的立论是**补货有前置时间，
    晚说不如早说**（见那个常量的 docstring）。分支本身是对的，2026-10-14
    之前错的是它给的命令：`/job-scrape`。

    ## 错在哪

    `/job-scrape` 抓完自动评分，但**不出材料**——敲完他手上是一排没材料的岗，
    还得再敲一条才走得到能发的那一步。这正是本文件开头记的那次修复：
    零起点那一支原来印 `/job-scrape`，2026-08-30 改成 `/job-auto`，
    理由逐字相同。**同一个仓库里对同一件事有两种答案，而窄的那一支
    （面板）没人记得一起改。**

    `test_both_next_steps_agree.py` 顶上把这个形状记成「已经栽过两次」。
    """

    @staticmethod
    def _restock(n_unranked=0):
        counts = {"scraped": 300, "ranked": 120, "materials": 0, "applied": 0,
                  "interviewing": 0, "offers": 0, "replied": 0, "decided": 0,
                  "applied_months": [], "direct_decided": 0, "direct_replied": 0}
        return bd.next_step(counts, True, n_sellable=2, n_unranked=n_unranked)

    def test_it_names_the_command_that_also_makes_materials(self):
        text, cmd = self._restock()
        self.assertEqual(cmd, "/job-auto",
                         f"补货那条又停在半路：{text}")

    def test_it_does_not_send_him_back_to_scrape_alone(self):
        _text, cmd = self._restock()
        self.assertNotIn("/job-scrape", cmd)

    def test_the_unranked_backlog_still_goes_to_rank_first(self):
        """**反向支点：收窄别把这一支也吃了。**

        有「抓到但没评」的积压时，补货的第一步是**把库存评完**，不是再去抓 ——
        否则 `/job-scrape` → `/job-scrape` 死循环（新抓的没评分，`n_sellable`
        永远是 0）。见 `build_dashboard.next_step` 里那段注释。
        """
        text, cmd = self._restock(n_unranked=200)
        self.assertEqual(cmd, "/job-rank", f"有待评积压时不该先去抓：{text}")

    def test_the_sentence_matches_the_number_it_prints(self):
        """**那句话里不许再出现「在跑」。**

        `n_sellable` 含「可以考虑」，而那一档按 `04` 的定义是「先问清楚再决定」——
        是一个待办不是一个动作。叫它「在跑的岗」会把「4 个可以考虑」说成
        「4 个能投的」，而他实际一个都还没决定投不投。
        """
        text, _cmd = self._restock()
        self.assertNotIn("在跑", text, f"那句话和它印出来的数对不上：{text}")


class TheNextStepDoesNotReadTheSilence(unittest.TestCase):
    """2026-08-29 裁定：下一步不提投递与回音。

    国内回音基本走平台站内信，这个工具一条都读不到 —— 据一个读不全的数
    去解读用户的处境，本来就不成立。
    """

    #: 「解读回音」的说法。**「把它们发出去」不在此列** —— 那是裁定认可的动作
    #: （有材料没发 → 先发），禁的是拿沉默去推断状态。
    READS_SILENCE = ("在等回复", "还没有回音", "没有回音", "没人回", "等回音")

    def test_the_terminal_next_step_does_not_interpret_silence(self):
        seg = code_of("tools/doctor.py", "def next_step(")
        hit = [w for w in self.READS_SILENCE if w in seg]
        self.assertEqual(hit, [], f"下一步又在解读回音了：{hit}")

    def test_the_restock_branch_names_job_auto(self):
        seg = code_of("tools/doctor.py", "def next_step(")
        tail = seg[seg.rindex("return ["):]
        self.assertIn("/job-auto", tail, "兜底那一支给的不是裁定点名的命令")
        self.assertNotIn("/job-scrape", tail)


if __name__ == "__main__":
    unittest.main()
