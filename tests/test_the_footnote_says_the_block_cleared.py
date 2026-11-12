# -*- coding: utf-8 -*-
"""关掉的那一家，行尾只说「你关掉了这家」—— 没说当初拦它的已经解了。

`portal_budget` 的状态行长这样（实测活动用户 2026-08-23）：

    猎聘   可以抓   今天 0/2 轮 · 猎聘 可以动　← 你在总览页关掉了这家

**多数人关掉一家是因为当时撞了风控。** 拦解了平台不会通知，勾就一直关着 ——
而 `/job-auto` 的补货**只看勾选框**。它照常跑两轮、零新增、触发停手条件、
报告写「挖不动了」，**而矿根本没开**。

代价可量：那一家占语料 **85%**（2232/2638），四家里唯一还在产可投岗的也是它
（可投 8，其余三家合计 1）。

## 试过改第一列，撤回了

那一列上写的是**动词**，而读的人在那个位置问的是「这一轮会不会抓它」——
答案是不会。所以第一版把它改成了「关着（额度没问题）」。

**撤回。** `test_the_two_gates_mention_each_other` 钉着一条有理由的裁定：
平台那道门（额度/风控）和他的开关是**两道门，不许合并 —— 合并了就说不清是
哪一层挡的**。改第一列正是合并。而要的那个用户收益不碰它也拿得到：

- 注脚多说一句「当初拦它的已经解了」（只答开关那道门，不进判词列）；
- `job-scrape.md` 开抓前先看一眼（那才是这件事真正咬人的地方；2026-08-25 从 job-auto.md 归位过去）。

措辞偏好不足以推翻一条写了理由的裁定 —— 这一段留在这里，免得下一轮又试一次。
"""
import datetime as dt
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import portal_budget as PB  # noqa: E402
from _srcscan import strip_comments  # noqa: E402

AUTO = (ROOT / "workflows" / "job-auto.md").read_text(encoding="utf-8")
SCRAPE = (ROOT / "workflows" / "job-scrape.md").read_text(encoding="utf-8")
NOW = dt.datetime(2026, 8, 23, 10, 0, 0)


def _line(site, data=None, off=()):
    for ln in PB.status_lines(data or {}, NOW, set(off)):
        if ln.strip().startswith(site):
            return ln
    raise AssertionError(f"没有 {site} 这一行")


class TheFootnoteSaysTheBlockHasCleared(unittest.TestCase):
    def test_it_says_so(self):
        """不说这一句，他没有理由回去把勾打开 —— 他记得的是「这家被拦了」。"""
        self.assertIn("当初拦它的已经解了", _line("猎聘", off={"猎聘"}))

    def test_it_does_not_claim_that_while_still_blocked(self):
        data = {"猎聘": {"blocked_until": (NOW + dt.timedelta(hours=5)).isoformat()}}
        ln = _line("猎聘", data, off={"猎聘"})
        self.assertIn("你在总览页关掉了这家", ln)
        self.assertNotIn("已经解了", ln, "还封着就说拦解了")

    def test_the_verdict_column_is_deliberately_untouched(self):
        """**两道门不合并**（`test_the_two_gates_mention_each_other`）。
        这一条盯着别有人（包括下一轮的我）又去改第一列。"""
        self.assertIn("可以抓", _line("猎聘", off={"猎聘"}),
                      "判词列被开关改掉了 —— 那就是合并了两道门")

    def test_a_ticked_portal_gets_no_footnote(self):
        ln = _line("BOSS")
        self.assertNotIn("关掉了这家", ln)
        self.assertNotIn("已经解了", ln)

    def test_every_portal_still_gets_exactly_one_line(self):
        """每个平台恰好一行平台行 —— 少一家就等于那家的状态没人报。

        2026-08-28 起平台行下面还挂**通道子行**（`    └ `开头），
        所以钉的是「平台行数 == 平台数」，不是「总行数 == 平台数」：
        `job-scrape.md` 那张渠道表是 5 条，而这份输出原来只有 4 行，
        猎聘的第二条通道被压进行尾注脚里，实测漏跑了两次。
        """
        lines = PB.status_lines({}, NOW, {"猎聘"})
        top = [ln for ln in lines if not ln.strip().startswith("└")]
        self.assertEqual(len(top), len(PB.PORTALS))
        for site in PB.PORTALS:
            with self.subTest(site=site):
                self.assertEqual(sum(1 for ln in top
                                     if ln.strip().startswith(site)), 1)

    def test_a_two_lane_portal_shows_both_lanes(self):
        """猎聘那两条通道各要有自己一行，且带上能传给 `--check` 的渠道名。"""
        lines = PB.status_lines({}, NOW)
        sub = [ln for ln in lines if ln.strip().startswith("└")]
        self.assertEqual(len(sub), 2, f"通道子行数不对：{sub}")
        self.assertTrue(any("liepin-search" in ln for ln in sub))
        self.assertTrue(any("liepin-browser" in ln for ln in sub))

    def test_the_rounds_and_why_columns_survive(self):
        """关着的那一行照样要带额度原话 —— 那一栏答的是别的问题。
        （`why` 的措辞随状态变，这里只验它没被吞掉。
        原来还验一栏「今天 N/2 轮」，2026-08-26 轮次概念删了。）"""
        ln = _line("猎聘", off={"猎聘"})
        tail = ln.split("　")[0].split(None, 2)[2].strip()
        self.assertTrue(tail, "额度那一栏被吞掉了")
        self.assertIn("额度", tail)

    def test_the_reason_is_written_down(self):
        """撤回那次尝试的理由要留在原地，否则下一轮会再试一次同一个改法。"""
        src = (ROOT / "tools" / "portal_budget.py").read_text(encoding="utf-8")
        i = src.index("def status_lines(")
        seg = " ".join(src[i:i + 2600].split())
        self.assertIn("撤回了", seg, "没记下那次改第一列的尝试为什么撤回")
        self.assertRegex(seg, r"那等于把两道门合并")
        self.assertRegex(seg, r"占语料 85%")


class TheAutoLoopLooksBeforeItDigs(unittest.TestCase):
    """这一段 2026-08-25 从 `job-auto.md` 归位到 `job-scrape.md` Step 0.4。

    它原来只写在 auto 的补货节里 —— 而单独跑 `/job-scrape` 的人根本看不到它。
    抓取规则收口（只留一处）时搬到正本；auto 的补货节只剩一句
    「整段走 /job-scrape」。下面各条验的内容一字没变，只是对着新家验。
    """

    def _seg(self):
        i = SCRAPE.index("**开抓前先看一眼有没有把大头关掉。**")
        j = SCRAPE.index("### Step 0.43", i)
        return SCRAPE[i:j]

    def test_the_check_exists(self):
        self.assertIn("**开抓前先看一眼有没有把大头关掉。**", SCRAPE)
        self.assertNotIn("补货前先看一眼", AUTO,
                         "auto 里又长回了一份抄件 —— 正本在 job-scrape Step 0.4")

    def test_it_gives_the_command(self):
        self.assertIn("python tools/portal_budget.py", self._seg())

    #: 关着的那家，工具在行尾挂的那个标记。**正本是 `portal_budget.py`
    #: 的 `note_off`**，下面那条测试逐字核过。
    OFF_MARK = "你在总览页关掉了这家"

    def test_it_names_what_to_look_for(self):
        """光说「看一眼」，执行者不知道看哪个字。

        **验命令后面那句注释，不是那串字在别处出现过** ——
        它在下面的散文里还有一份，把注释删掉照样绿（变异实测）。
        """
        self.assertIn(self.OFF_MARK, self._seg(), "命令旁边没说该看哪个字")
        i = self._seg().index("python tools/portal_budget.py")
        self.assertIn(self.OFF_MARK, self._seg()[i:i + 200],
                      "那句话离命令太远，读的人扫不到")

    def test_the_string_it_names_is_the_one_the_tool_prints(self):
        """**这条是补的，它本该早就在。**

        工作流原来让执行者去找「关着（额度没问题）」，而工具从来不印那句 ——
        2026-08-23 试过那个写法、同日改回，落地的是行尾一个
        `← 你在总览页关掉了这家`。而上面那条测试**把错措辞钉在了那儿**：
        它验的是「注释里有那串字」，那串字自己就是错的。

        实测代价（2026-08-24，`/job-auto` 跑到补货那一步）：执行者读了这份输出、
        报「四家额度全清」，整趟一次没提猎聘的勾是关的 —— 而它占语料 85%，
        正是同一段自己预言的「报告写『挖不动了』，而矿根本没开」。

        所以现在两头对着核：工作流说该找哪个字、工具真的印那个字。
        """
        src = (ROOT / "tools" / "portal_budget.py").read_text(encoding="utf-8")
        self.assertIn(f'note_off = "　← {self.OFF_MARK}"', src,
                      "工具改了这个标记，而工作流还在教人找旧的那句")

    def test_it_greps_instead_of_eyeballing(self):
        """那一行有一百多字、标记在行尾 —— 裸眼扫是漏掉的原因。"""
        self.assertRegex(self._seg(), r"grep\s*关掉")

    def test_it_says_what_the_silent_failure_looks_like(self):
        """这才是它值得占一段的理由：不是「少抓一点」，是**结论写反**。"""
        seg = " ".join(self._seg().split())
        self.assertRegex(seg, r"两轮零新增就触发停手条件")
        self.assertRegex(seg, r"而矿根本没开")

    def test_it_carries_the_measured_share(self):
        seg = " ".join(self._seg().split())
        self.assertIn("矿根本没开", seg)

    def test_it_does_not_flip_the_switch_itself(self):
        """勾选框是他的 —— 自动模式尤其不许替他开（同「永远归人」那一节）。"""
        seg = " ".join(self._seg().split())
        self.assertIn("别替他开", seg)
        self.assertRegex(seg, r"他不勾就照常跑")

    def test_the_switch_is_still_the_only_gate(self):
        """原有的规矩：勾选框是唯一开关，不许再冒出第二个 flag。"""
        self.assertIn("勾选框是唯一开关", AUTO)

    def test_the_query_yield_step_survives(self):
        """补货完跑 `query_yield --apply` 答的是另一件事，不许被挤掉。"""
        self.assertIn("python tools/query_yield.py --apply", AUTO)


class TheSwitchSourceIsUnchanged(unittest.TestCase):
    """这一行的判据来自 `switched_off`。它变了，上面全部落空。"""

    def test_switched_off_still_exists(self):
        self.assertTrue(hasattr(PB, "switched_off"))

    def test_the_column_is_not_a_second_judgement(self):
        """状态列只许读传进来的那个集合，不许自己再去读一遍 `portals.json`
        —— 两处各读各的就会出现「报告说关着、面板说开着」。"""
        code = strip_comments((ROOT / "tools" / "portal_budget.py")
                              .read_text(encoding="utf-8"))
        i = code.index("def status_lines(")
        seg = code[i:code.index("\ndef ", i + 10)]
        self.assertNotIn("portals.json", seg)
        self.assertNotIn("switched_off(", seg, "状态列自己又判了一遍")
        self.assertIn("off or ()", seg, "不再用传进来的那个集合")

    def test_the_caller_passes_it(self):
        code = strip_comments((ROOT / "tools" / "portal_budget.py")
                              .read_text(encoding="utf-8"))
        self.assertRegex(code, r"status_lines\([^)]*switched_off\(user\)")


if __name__ == "__main__":
    unittest.main()
