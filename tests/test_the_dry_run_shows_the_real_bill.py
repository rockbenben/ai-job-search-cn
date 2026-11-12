# -*- coding: utf-8 -*-
"""两处都在推荐 `fetch_details --recheck --apply`，而它的账单没人说。

`audit_pipeline`（「结论自称读过 JD」那条）和 `applied_jds` 都在给用户印这条命令。
而 **`workflows/` 里此前没有任何一处解释这个工具** —— 唯一提过它的 `.md` 是
`.private/RELEASE-PREP.md`，那不在流程里。被推荐的命令没人解释要花多少，
那不是建议，是把账单藏起来。

## 试运行自己也报错了

实测活动用户 2026-08-24：

    --missing    待抓  23 个   约 1 分钟，今天抓得完
    --recheck    待抓 727 个   其中 704 个是待复核的既有判定

而 `--recheck` 的试运行印的是「约 24.2 分钟」，真跑 `--apply` 时 `run()` 会按
`remaining_today` 砍到今天剩下的额度（日上限 60 次/家），**这一批要跨 13 天**。
差两个数量级，而砍这一刀的提示只在 `--apply` 之后才印。
**试运行的用处就是先看账单，它报错了等于没试。**

> **2026-08-26：那个日上限删了**，本人裁定「没有固定额度的，你应该等撞到才算
> 到了额度，我们当前应该是控制单渠道每次访问的间隙时间」。于是「条数 × 间隔」
> 重新变成诚实的估计 —— 这个文件要守的那件事没变（**试运行报的必须是真账单**），
> 变的只是真账单怎么算。下面那个类跟着改了名。

## 另外两件按 `--apply` 之前要知道的

- `--recheck` 抓完不等于修完：那 704 个是「判过但没读过正文」的既有判定，
  正文补回来之后**要人工重审**。工具自己在队列那行就这么说了。
- 有一批它够不着（实测 394 个，浏览器渠道）—— 那些只能在下次抓取的同一次访问里取。
"""
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import portal_budget as pb  # noqa: E402

FD = (ROOT / "tools" / "fetch_details.py").read_text(encoding="utf-8")
RANK = (ROOT / "workflows" / "job-rank.md").read_text(encoding="utf-8")
AUDIT = (ROOT / "tools" / "audit_pipeline.py").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*[>#]:?\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


class TheDryRunBillIsTheRealBill(unittest.TestCase):
    """试运行印的分钟数必须是真的。

    2026-08-26 之前它是假的（少算一个日上限）。现在没有日上限了，
    真实约束只剩间隔 —— 所以判据钉的是「间隔取自闸门」和「别再假装有上限」。
    """

    def _seg(self) -> str:
        i = FD.index("**试运行报的就是真账单。**")
        return flat(FD[i:FD.index("另有", i)])

    def test_the_estimate_uses_the_gate_interval(self):
        """分钟数按 `INTERVAL_S` 算，而 `INTERVAL_S` 取自闸门 —— 一处定义。"""
        self.assertIn("len(entries) * INTERVAL_S / 60", FD)
        self.assertIn('INTERVAL_S = pb.gap_for("fetch")', FD)

    def test_it_says_what_actually_stops_it(self):
        """既然没有上限，就要说清什么才会停 —— 否则「约 48 分钟」读起来像保证。"""
        self.assertIn("跑到撞上限流为止", FD)
        self.assertIn("RATE_LIMITED", FD)

    def test_it_no_longer_pretends_there_is_a_cap(self):
        for gone in ("remaining_today", "REQUESTS_PER_DAY", "留到明天"):
            with self.subTest(gone=gone):
                self.assertNotIn(f"pb.{gone}", FD)
        self.assertNotIn("entries = entries[:left]", FD,
                         "还在按额度砍批次 —— 那个额度已经不存在了")

    def test_the_reason_is_recorded(self):
        seg = self._seg()
        self.assertIn("2026-08-26", seg)
        self.assertIn("日上限", seg)


class TheWorkflowExplainsTheTool(unittest.TestCase):
    def _seg(self) -> str:
        i = RANK.index("### 回头补 JD")
        return flat(RANK[i:RANK.index("**分批循环", i)])

    def test_the_section_exists(self):
        self.assertIn("### 回头补 JD：`fetch_details.py` 的两种模式", RANK)

    def test_it_says_why_it_was_missing(self):
        seg = self._seg()
        self.assertRegex(seg, r"此前在 `workflows/` 里没有任何落点")
        self.assertRegex(seg, r"那不是建议，是把账单藏起来")

    def test_all_three_modes_are_shown(self):
        seg = self._seg()
        for f in ("--missing", "--recheck", "--urls"):
            with self.subTest(f=f):
                self.assertIn(f, seg)

    def test_the_dry_run_convention_is_stated(self):
        self.assertRegex(self._seg(), r"不加 `--apply` 就是试运行")

    def test_the_two_queues_are_measured(self):
        seg = self._seg()
        self.assertIn("--missing", seg)
        self.assertIn("--recheck", seg)

    def test_it_says_fetching_is_not_fixing(self):
        """抓回正文之后还要人工重审 —— 说成一键修复就是骗人。"""
        seg = self._seg()
        self.assertRegex(seg, r"`--recheck` 抓完不等于修完")
        self.assertRegex(seg, r"人工重审")

    def test_it_says_a_chunk_is_out_of_reach(self):
        seg = self._seg()
        self.assertRegex(seg, r"浏览器渠道的 JD 只能在抓取当次")


class TheAuditPointsAtTheBill(unittest.TestCase):
    def _seg(self) -> str:
        """切的是**那条判词自己**，不是它上面的说明块。

        锚点 2026-08-25 换过一次：原来锚在「` 会把够得着的补回来」上，
        而那句措辞当天被改掉了（改成报出「够得着 193 / 够不着 63」两个数）。
        它现在只活在说明块里被引用 —— 老锚点照样找得到，切出来的却是注释，
        于是这四条一起红。**锚在会变的措辞上，就是在等它变。**

        新锚点是那条 `return`：措辞改多少次，它都在。
        """
        i = AUDIT.index('return [("warn" if wired else "error", "结论自称读过 JD')
        return flat(AUDIT[i:i + 1400])

    def test_it_tells_you_to_dry_run_first(self):
        """**不带 markdown 粗体** —— 这是终端输出，星号会原样上屏
        （第一版就写了 `**`，`test_display_wording` 当场逮到）。"""
        self.assertRegex(self._seg(), r"先跑一次不加 `--apply` 的试运行看账单")

    def test_it_says_how_long_it_takes(self):
        self.assertRegex(self._seg(), r"几十分钟量级")

    def test_it_says_the_judgments_need_review(self):
        self.assertRegex(self._seg(), r"那些判定还要人工重审")

    def test_it_points_at_the_section(self):
        self.assertIn("job-rank.md", self._seg())
        self.assertIn("回头补 JD", self._seg())


class TheSafetyRulesAreIntact(unittest.TestCase):
    """这个文件存在的理由是「撞限流立刻停」—— 别被这次改动碰掉。"""

    def test_the_rate_limit_stop_survives(self):
        self.assertIn("撞风控立刻停手", FD)

    def test_the_budget_injection_hatch_survives(self):
        self.assertIn("_persist = budget is None", FD)

    def test_the_out_of_reach_batch_is_still_announced(self):
        """原来这条守的是「被额度砍掉的要说出来」，额度没了。

        它背后那件事没变：**别让人以为跑一次就补全了**。现在由
        「够不着的那批」承担 —— 那才是真正会被读成「抓完了」的地方。
        """
        self.assertIn("这个工具够不着", FD)
        self.assertIn("--browser-list", FD)


if __name__ == "__main__":
    unittest.main()
