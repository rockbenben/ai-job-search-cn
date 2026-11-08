# -*- coding: utf-8 -*-
"""一轮 `/job-auto` 跑完，收尾要说的是他**现在动得了**的那几件事。

自检有 50 多条，全量印在收尾里是有害的，不只是啰嗦：绝大多数报的是**存量或
结构问题**，一轮 auto 动不了它们。实测活动用户 2026-08-25，那条开场白检查
（它自己的 docstring 里有完整的账）——

    踩线           102 份
    ├ 已经投出去了   72 份   ← 改也来不及
    ├ 你标了不投     13 份
    ├ 岗位已下线      3 份
    └ **还发得出去**  11 份   ← 只有这一档能动

**一个基本动不了的数被印成待办，读的人多半整条忽略**，然后那 11 份跟着被忽略。

## 判据是行为，不是名单

`--actionable` 留下的是**调用过 `sendable_state` 的那几条检查** —— 一条检查问过
「这几份还发得出去吗」，就说明它认得出哪些还来得及补。

另立一张「哪几条算 actionable」的名单是第二个住址，会和 `CHECKS` 分叉
（拼错一个名字就静默少跑一条，而少跑是看不见的）。这个仓库反复栽在这上面。
新加的检查只要调了 `sendable_state`，自动就进这一档 —— 不用改两个地方。
"""
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
from _live import user_or_skip  # noqa: E402
import audit_pipeline as ap  # noqa: E402

AUTO = (ROOT / "workflows" / "job-auto.md").read_text(encoding="utf-8")
SRC = (ROOT / "tools" / "audit_pipeline.py").read_text(encoding="utf-8")


def run_with(checks, **kw):
    """拿几条构造的检查跑一次 `run()`，不碰真实数据。两个类都要用。"""
    saved_checks, saved_load = ap.CHECKS[:], ap.load
    try:
        ap.CHECKS[:] = checks
        ap.load = lambda user: ({}, {})
        return ap.run("nobody", **kw)
    finally:
        ap.CHECKS[:] = saved_checks
        ap.load = saved_load


class TheJudgeIsBehaviourNotAList(unittest.TestCase):
    def test_there_is_no_second_registry(self):
        """没有第二张名单 —— 有的话它会和 `CHECKS` 分叉。"""
        self.assertNotRegex(SRC, r"ACTIONABLE_CHECKS\s*=",
                            "另立了一张 actionable 名单 —— 那就是第二个住址")

    #: 用第二个信号的检查数上限。**只许往下走，往上要先说服自己。**
    #:
    #: 这一档存在的全部理由是「别把还来得及的那几条淹掉」——全量 60 多条里
    #: 绝大多数是存量或结构问题。第二个信号很好加（喊一声就进来了），
    #: 加多了这一档就退化成全量，那时它等于没有。
    ROUND_SCOPED_CAP = 6

    def test_the_second_signal_stays_rare(self):
        """用它的检查不许多。

        判据是**用它的检查条数**，不是名单 —— 名单会和 `CHECKS` 分叉（同这一档
        自己的判据）。今天 4 个：漏一条通道、漏一整家、JD 读了没落库、
        抓完没刷词表。"""
        # **数「几条检查」，不是「喊了几声」。** 一条检查可以在两个分支里
        # 各喊一次（漏一整家那条就是：漏了家一支、跑得不均一支），按调用点
        # 数会把它算成两条 —— 第一版就是这么写的，当场把 4 条数成 9 个。
        import ast as _ast
        tree = _ast.parse(SRC)
        got = 0
        for fn in tree.body:
            if not isinstance(fn, _ast.FunctionDef):
                continue
            if any(isinstance(c, _ast.Call)
                   and isinstance(c.func, _ast.Attribute)
                   and c.func.attr == "note_round_scoped"
                   for c in _ast.walk(fn)):
                got += 1
        self.assertGreaterEqual(got, 1, "一个都没有？那这个信号是死的")
        self.assertLessEqual(
            got, self.ROUND_SCOPED_CAP,
            f"用第二个信号的检查涨到了 {got} 条 —— 收尾那一档正在退化成全量。"
            "每加一条都要问：它报的真是这一轮的事吗？"
            "补法现在还做得了吗？做不了就该留在全量里。")

    def test_it_also_counts_the_round_scoped_signal(self):
        """第二个信号：**这一轮本身漏了活**。

        「调过 `sendable_state`」是个代理判据，有一整类发现它表达不了 ——
        `check_the_blocked_lane_handed_over`（猎聘 CLI 撞限流那天，闸门放行的
        浏览器那条 0 次查询，而那家占语料的大头）就是这一类。它进不了收尾
        那一档，于是同一个错犯了两次、两次都靠人当场发现。

        新信号同样是**运行时喊一声**，不是名单。
        """
        import _cli

        def quiet(seen, details):
            return [("warn", "不喊的那条", "存量，收尾不该印")]

        def shouts(seen, details):
            _cli.note_round_scoped()
            return [("warn", "喊了的那条", "这一轮漏了一整条渠道")]

        got = run_with([("安静", quiet), ("喊了", shouts)],
                       actionable=True)
        self.assertEqual([r[1] for r in got], ["喊了的那条"],
                         "第二个信号没起作用，或者把不喊的也放进来了")

        # 不加 `--actionable` 时两条都在 —— 这个信号只管收尾那一档。
        both = run_with([("安静", quiet), ("喊了", shouts)])
        self.assertEqual(len(both), 2)

    def test_shouting_without_reporting_anything_is_harmless(self):
        """喊了却什么也没报的检查，收尾里不该多出一行。

        `run()` 按调用次数判、不看返回值 —— 所以喊的时机写在`note_round_scoped`
        的说明里：**只在真报出东西那一支喊**。这条钉住「即便喊错了地方，
        空手也不会变成一行字」。"""
        import _cli

        def shouts_nothing(seen, details):
            _cli.note_round_scoped()
            return []

        self.assertEqual(
            run_with([("空喊", shouts_nothing)], actionable=True), [])

    def test_the_second_signal_is_not_a_list_either(self):
        self.assertIn("_ROUND_SCOPED_CALLS", SRC)
        seg = SRC[SRC.index("def run(user: str"):]
        seg = seg[:seg.index("def main(")]
        self.assertIn("_ROUND_SCOPED_CALLS[0] == before_round", seg,
                      "收尾那一档没在数第二个信号")

    def test_it_counts_calls_to_the_shared_judge(self):
        self.assertIn("_SENDABLE_CALLS", SRC)
        seg = SRC[SRC.index("def run(user: str"):]
        seg = seg[:seg.index("def main(")]
        self.assertIn("_SENDABLE_CALLS[0] == before", seg,
                      "run() 没按「这条检查问没问过」筛")

    def test_the_counter_moves(self):
        before = ap._SENDABLE_CALLS[0]
        ap.sendable_state("nobody", {})
        self.assertEqual(ap._SENDABLE_CALLS[0], before + 1)

    def test_a_check_that_never_asks_is_dropped(self):
        """没问过的检查报的是存量 —— 收尾里不该出现。"""
        calls = []
        got = run_with([
            ("只报存量的", lambda s, d: calls.append("A") or [("warn", "存量", "x")]),
            ("会问还能不能发的", lambda s, d: (ap.sendable_state("nobody", s),
                                            calls.append("B"),
                                            [("warn", "还能发", "y")])[-1]),
        ], actionable=True)
        self.assertEqual(calls, ["A", "B"], "两条都要真的跑过，只是报的时候筛")
        self.assertEqual([r[1] for r in got], ["还能发"])

    def test_without_the_flag_everything_still_reports(self):
        got = run_with([("只报存量的", lambda s, d: [("warn", "存量", "x")])])
        self.assertEqual([r[1] for r in got], ["存量"])


class TheJudgeHasOneHome(unittest.TestCase):
    """「这一份还发得出去吗」的正本在 `_cli`，别的地方只许引用。

    它原来住在 `audit_pipeline` 里（更早之前是内联在一条检查的函数体里）。
    第三个调用方来的时候搬的家：`writeback` 只想报「还能改的有几个」，
    却要为此 import 整个自检（50 多条检查、几千行）—— 那种代价会把人推向
    「我自己写一份得了」，而这个仓库的词表就是那样分叉过一次的
    （同一类一边数出 32 份、一边 17 份）。
    """

    def test_the_definition_is_in_cli(self):
        import _cli
        self.assertTrue(callable(_cli.sendable_state))

    def test_the_audit_only_forwards(self):
        self.assertIs(ap.sendable_state, __import__("_cli").sendable_state)
        self.assertIs(ap._SENDABLE_CALLS, __import__("_cli")._SENDABLE_CALLS)

    def test_nobody_re_implements_it(self):
        """别的工具里不许再出现一份自己算的「已投/不投/下线」四分法。"""
        import _cli
        home = pathlib.Path(_cli.__file__).name
        for f in sorted((ROOT / "tools").glob("*.py")):
            if f.name == home:
                continue
            src = f.read_text(encoding="utf-8")
            with self.subTest(f=f.name):
                self.assertNotIn("def sendable_state(", src,
                                 f"{f.name} 里又写了一份 —— 正本在 _cli")

    def test_the_five_states_are_exhaustive(self):
        """五种状态要盖全 —— 「不知道」单列，不许乐观地算进「还能发」。"""
        import _cli
        where = _cli.sendable_state("nobody", {})
        self.assertEqual(where("https://example.com/x"), "对不上职位库")


class EveryUserOfItNamesTheLiveOnes(unittest.TestCase):
    """用了这个判定，就得把「还能动的那几个」单独说出来。

    只印总数的话读的人做不了任何事，而且给出的命令多半指向一个已经投出去的岗
    —— 实测 `writeback` 那条：抽样 5 个里 2 个已投、1 个标了不投。
    **他敲一次、发现没意义，下次整条就不看了。**
    """

    def test_writeback_names_them(self):
        src = (ROOT / "tools" / "writeback.py").read_text(encoding="utf-8")
        i = src.index("if stale_basis:")
        seg = src[i:i + 1800]
        self.assertIn("_cli.sendable_state", seg, "没分「还能动的」那一格")
        self.assertIn("还没投、现在改还有意义的", seg)
        self.assertIn("/job-apply {live[0][1]}", seg,
                      "命令还是指着名单第一个 —— 那个多半已经投出去了")

    def test_writeback_says_so_when_none_are_live(self):
        src = (ROOT / "tools" / "writeback.py").read_text(encoding="utf-8")
        i = src.index("if stale_basis:")
        self.assertIn("改它没有意义", src[i:i + 1800],
                      "一个都动不了时要直说，别给一条白敲的命令")


class TheRiskiestSliceSaysWhatAlreadyHappened(unittest.TestCase):
    """「可投 + 有材料 + 依据不在库里」这一条，别把已经发生的说成可能发生。

    它原来的措辞是「用户随时可能复制开场白发出去，而没有任何人能再看一眼依据」
    —— 未来时。2026-08-30 现算一遍：26 个里 **23 个已经发出去了**。
    我原以为这条的判据（「可投 + 有材料」）意味着命中的都还没投，
    算了一次才知道它不排已投的。

    这个差别不是措辞：「可能会发生」读起来是个可以往后放的风险，
    「已经发生了 23 次」是个已经付掉的代价 —— 后者才说得清这条为什么要盯。
    而**还能动的只有那 3 个**，那 3 个才是收尾该指的。
    """

    def _seg(self) -> str:
        i = SRC.index("def check_material_ready_without_a_stored_jd(")
        return SRC[i:SRC.index("#: 「JD 未要求", i)]

    def test_it_no_longer_says_it_might_happen(self):
        """**只看真正印出去的那一段**，不看解释它的注释。

        那句原话留在注释里是有用的（记着这次错在哪）—— 拿全函数去 assertNotIn
        会把「记录一次错误」和「再犯一次」当成同一件事。
        """
        seg = self._seg()
        # **切最后那个 `return [(`**：函数里还有一个早退的 `return []`，
        # 从它切起会把整段注释也划进来 —— 第一版就是这么误伤的。
        out = seg[seg.rindex('return [("warn"'):]
        self.assertNotIn("随时可能复制开场白发出去", out,
                         "又把已经发生 23 次的事说成「可能会发生」了")
        self.assertIn("随时可能复制开场白发出去", seg,
                      "那次错的原话被顺手删了 —— 下一个人会照原样再写一遍")

    def test_it_splits_historical_from_still_fixable(self):
        seg = self._seg()
        self.assertIn("_n_gone", seg)
        message = seg[seg.index("_still = ("):seg.index('return [("warn"')]
        # live_tail 也会排除已下线和不投记录，不能把差集一律称为已投。
        self.assertIn("已不在待投范围", message)
        self.assertIn("现在可以补存正文", message)

    def test_the_split_is_computed_not_assumed(self):
        """那个数是现算的 —— 我上一版就是「按定义」推出来的，推错了。"""
        self.assertIn("_cli.live_tail", self._seg())

    def test_no_markdown_reaches_the_terminal(self):
        """这句话直接上终端。第一版带着 `**` 就印出去了。"""
        seg = self._seg()
        i = seg.index("_still = (")
        self.assertNotIn("**", seg[i:seg.index("return [", i)])


#: **只在 `main()` 的函数体里找。** `TheClosingAddsThemUp` 那几条原来在
#: 整份源码上 `index()`，而 2026-08-30 有人在一条检查的 docstring 里
#: 逐字引了那句「下面这几条去重后是 N 个岗……一次补完」——
#: `index()` 先撞上引文，三条当场红，而被守的那句话一个字没动。
#:
#: 这个仓库记规则的办法就是把原话引出来再说它错在哪，所以**定位器要躲开
#: 引文**，不是反过来禁止引用（同一条豁免在 `test_docs_accuracy`、
#: `test_the_round_does_the_rerun_itself` 里都写过）。
#:
#: ⚠️ **只换这一个类。** 第一版整份文件替换，把另外 15 处正当的全库扫描
#: 也换掉了，18 条测试当场红。
MAIN = SRC[SRC.index("def main(argv=None) -> int:"):]


class TheClosingAddsThemUp(unittest.TestCase):
    """六条各报一个数，读的人加不出总数 —— 收尾要说去重后是多少。

    实测 2026-08-30：六条合计**提及 113 次**，而**去重后只有 101 个岗**
    （12 个被两条同时点到）。「加起来」这件事只有收尾这一层做得了：
    每条检查只看得见自己那一批。

    而**总数不给命令等于没说**（`AGENTS.md`「每一处引导都要写出该敲的命令」）。
    给的是 `/job-apply 全部`：它走同一套批量，有材料的只补缺的那一节
    （判据在 `job-apply.md` 那张补漏表），不重跑深评。
    """

    def test_the_shared_tail_records_who_it_named(self):
        import _cli
        _cli.LIVE_SEEN.clear()
        _cli.live_tail("nobody", {}, [("u", "A")])
        self.assertEqual(_cli.LIVE_SEEN, set(),
                         "空库里一个都不该点名")

    def test_the_closing_prints_a_deduped_total(self):
        self.assertIn("这几条去重后是", MAIN)
        self.assertIn("_cli.LIVE_SEEN", MAIN)

    def test_the_total_names_one_command(self):
        i = MAIN.index("这几条去重后是")
        self.assertIn("/job-apply 全部", MAIN[i:i + 500])

    def test_the_total_comes_before_the_details(self):
        """**要动手的那句排在最前，解释排在后面。**

        它原来收在最后 —— 也就是 41 行明细之后，而这一整档的价值就在那一句。
        同一个毛病在单条消息里刚修过两次（那串按批次的枚举、按 26 个规模写的
        补法），这次是在**报告这一级**：先说该敲什么，再说为什么。
        """
        i_head = MAIN.index('print(f"流水线审计（用户：{user}）')
        i_total = MAIN.index("下面这几条去重后是")
        i_rows = MAIN.index('for lvl, kind, detail in found:', i_head)
        self.assertLess(i_total, i_rows,
                        "总数那句又落到明细后面了 —— 读到它要先翻 40 行")
        self.assertLess(i_head, i_total)

    def test_it_only_shows_in_the_closing_tier(self):
        """全量自检里不印 —— 那一档报的是存量，加起来没有行动含义。"""
        i = MAIN.index("这几条去重后是")
        self.assertIn("if a.actionable", MAIN[max(0, i - 900):i])

    def test_the_dedup_is_not_computed_twice(self):
        """去重靠 `_cli` 顺手收集 —— 让六条各自返回一个集合，
        等于把同一件事写六遍，而那六条的返回值形状本来就各不相同。

        ⚠️ **钉行为，不钉那一行代码长什么样。** 原来查的是
        `"LIVE_SEEN.update" in src` —— 记账 2026-08-31 搬进 `note_live`
        （改用 `add`，好让手写尾巴的两条检查也能调），这条当场红。
        判据钉实现位置，重构本身就成了违规。
        """
        import _cli
        keep = set(_cli.LIVE_SEEN)
        try:
            _cli.LIVE_SEEN.clear()
            _cli.note_live(["https://x.com/a", "https://x.com/a"])
            self.assertEqual(len(_cli.LIVE_SEEN), 1, "同一个岗记了两遍")
        finally:
            _cli.LIVE_SEEN.clear()
            _cli.LIVE_SEEN.update(keep)


class SellableWithoutMaterialsAsksBeforeItAssumes(unittest.TestCase):
    """「可投档却没材料」：命中的是不是真还没投 —— **算，不推。**

    这条的选岗条件已经排掉了快照里的 `applied` / `skipped` / `expired`，
    看着像「命中的按定义都还没投」。**那种推理这个仓库刚栽过一次**：
    `check_material_ready_without_a_stored_jd` 的条件也长这样，
    算了一遍才发现 26 个里 **23 个已经发出去了** —— 投递记录在
    `job_search_tracker.csv` 里，不在快照那几个布尔上。

    所以这里也算。顺带它就进了收尾那一档（`--actionable` 的判据是
    「这条检查问没问过还发得出去」），而一轮 `/job-auto` 跑完还留着
    「可投却没材料」的岗，正是那一轮漏了活的直接证据。

    ⚠️ 真实数据里这条现在是 **0**（好事），所以只能拿构造数据验。
    """

    def _run(self, jobs, applied_urls=()):
        import json
        import tempfile
        import audit_pipeline as ap
        import _cli
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            u = root / "users" / "某人"
            (u / "job_scraper").mkdir(parents=True)
            (root / "web" / "public").mkdir(parents=True)
            (root / ".active_user").write_text("某人", encoding="utf-8")
            (root / "web" / "public" / "data.json").write_text(
                json.dumps({"activeUser": "某人", "jobs": jobs},
                           ensure_ascii=False), encoding="utf-8")
            # 没有 `url` 的岗也要能构造出来 —— 「对不上职位库」那一支正是靠它验的。
            store = {"seen": {j["url"]: {"url": j["url"], "status": "ranked"}
                              for j in jobs if j.get("url")}}
            (u / "job_scraper" / "seen_jobs.json").write_text(
                json.dumps(store, ensure_ascii=False), encoding="utf-8")
            (u / "job_search_tracker.csv").write_text(
                chr(10).join(["source,company"]
                             + [f"{x},甲" for x in applied_urls]) + chr(10),
                encoding="utf-8")
            old_ap, old_cli = ap.ROOT, _cli.ROOT
            ap.ROOT = _cli.ROOT = root
            ap._USER[:] = ["某人"]
            try:
                out = ap.check_sellable_without_materials(_cli.seen_of(store), {})
            finally:
                ap.ROOT, _cli.ROOT = old_ap, old_cli
        return out[0][2] if out else ""

    JOBS = [{"url": "https://x/1", "company": "甲", "score": 72, "verdict": "值得投"},
            {"url": "https://x/2", "company": "乙", "score": 70, "verdict": "值得投"}]

    def test_it_gives_the_command_when_they_can_still_be_made(self):
        self.assertIn("补它：/job-apply", self._run(self.JOBS))

    def test_it_drops_the_command_when_none_can(self):
        """全都已投时，「却一份材料都没有……补它」整句就错了。"""
        msg = self._run(self.JOBS, applied_urls=("https://x/1", "https://x/2"))
        self.assertNotIn("补它：/job-apply", msg)

    def test_a_dead_row_carries_the_filter_mark(self):
        """带上 `_cli.NO_LIVE`，收尾那一档才滤得掉整行。"""
        import _cli
        msg = self._run(self.JOBS, applied_urls=("https://x/1", "https://x/2"))
        self.assertIn(_cli.NO_LIVE, msg)

    def test_it_says_they_are_actually_out(self):
        """不是「没材料」，是「已经出局了而快照没标上」—— 两件事别混。"""
        msg = self._run(self.JOBS, applied_urls=("https://x/1",))
        self.assertIn("其实已经出局了", msg)

    def test_unknown_is_not_counted_as_sent(self):
        """**「对不上职位库」不算「已经投了」。**

        第一版拿 `live_tail` 的二分来分（是不是「还能发」），于是
        「不知道」被算进了「已经出局」那一半，消息里当场出现一句假话。
        `sendable_state` 自己的说明第一条就是「不知道就说不知道，
        别乐观地算进去」—— 反过来也一样，别悲观地算进去。

        对着不知道的岗收掉唯一的下一步，等于替他判了死。
        """
        no_url = [{"company": "甲", "score": 72, "verdict": "值得投"}]
        msg = self._run(no_url)
        self.assertIn("补它：/job-apply", msg, "对不上库就把命令收了")
        self.assertNotIn("已经出局", msg, "把「不知道」说成了「已经出局」")

    def test_it_computes_instead_of_assuming(self):
        seg = SRC[SRC.index("def check_sellable_without_materials("):]
        seg = seg[:seg.index(chr(10) + "def ")]
        self.assertIn("_cli.sendable_state", seg, "又按「定义」推了一次")


class WhichJobThisFolderIsHasOneAnswer(unittest.TestCase):
    """「这个投递目录对应哪个岗」的正本是 `build_dashboard.find_applications`。

    ## 两份实现，各自不全

    - `find_applications`：`outreach.md` → `posting.md`（标签宽进：原始链接 /
      职位链接 / 链接 / URL，全半角冒号都认，再退到文件头 12 行第一个链接）——
      **它从不看 `evaluation.md`**；
    - 各条检查：自己在 `evaluation.md` 上跑一次 `LINK_LINE` —— 只看那一个文件。

    实测活动用户 2026-08-30，316 份深评：

        链接在两处都有                249 份
        只在 `evaluation.md`（没话术） 37 份
        **只在 `outreach.md`**        24 份   ← 检查那份看不见
        两处都没有 / 彻底没有            6 份

    那 24 个的后果不是报错，是**判不了**：`sendable_state` 对空链接返回
    「对不上职位库」，于是它们既不算「还能发」也说不清是什么。
    实测收尾里因此少报了 4 个还能补的岗（55→59、49→51），
    而「判不了」那一档从 **29 降到 0**。
    """

    def test_the_checks_do_not_search_the_evaluation_themselves(self):
        for fn in ("check_evaluation_sections", "check_maybe_tier_has_questions"):
            with self.subTest(fn=fn):
                i = SRC.index(f"def {fn}(")
                seg = SRC[i:SRC.index(chr(10) + "def ", i)]
                self.assertIn("dir_urls(user)", seg,
                              f"{fn} 没用正本")
                self.assertNotIn("LINK_LINE.search(t)", seg,
                                 f"{fn} 又自己搜了一遍 evaluation.md")

    def test_the_resolver_delegates(self):
        """`dir_urls` 自己也不许另写一套 —— 它只取 `find_applications` 的结果。

        ⚠️ **只看代码体，不看 docstring。** 那段说明里逐字引着「各条检查自己在
        `evaluation.md` 上跑一次 `LINK_LINE`」—— 那是在**记录为什么不这么干**。
        拿整个函数去 `assertNotIn` 会把「解释一次错误」和「再犯一次」当成同一件事，
        同一个毛病本会话已经犯过一次（`test_it_no_longer_says_it_might_happen`）。
        """
        i = SRC.index("def dir_urls(")
        seg = SRC[i:SRC.index(chr(10) + "def ", i)]
        body = seg[seg.index('"""', seg.index('"""') + 3) + 3:]
        self.assertIn("find_applications", body)
        self.assertNotIn("LINK_LINE", body)

    def test_it_resolves_every_folder_on_the_real_data(self):
        """正本对这份真实数据 332 个目录全部解析得出 —— 那是它当正本的理由。"""
        import audit_pipeline as ap
        import _cli
        user = user_or_skip()
        apps = ROOT / "users" / user / "documents" / "applications"
        if not apps.is_dir():
            self.skipTest("没有投递目录")
        urls = ap.dir_urls(user)
        blank = [k for k, v in urls.items() if not v]
        self.assertEqual(blank, [], f"这几个目录接不上职位：{blank[:5]}")


class TheClosingRunsIt(unittest.TestCase):
    def test_job_auto_runs_it(self):
        self.assertIn("audit_pipeline.py --actionable", AUTO)

    def test_it_says_why_not_the_whole_thing(self):
        """不解释的话，下一个人会「顺手」把 --actionable 去掉。"""
        i = AUTO.index("**收尾那条 `audit_pipeline.py --actionable` 在报什么。**")
        seg = " ".join(AUTO[i:i + 900].split())
        self.assertIn("102 份踩线里 72 份已经投出去了", seg)
        self.assertIn("2026-08-25", seg, "实测数要带日期（CONTRIBUTING）")
        self.assertIn("判据是行为不是名单", seg)

    def test_the_flag_is_documented_in_the_help(self):
        import subprocess
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "audit_pipeline.py"),
                            "--help"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=90)
        self.assertIn("--actionable", (r.stdout or "") + (r.stderr or ""))


class EveryActionableRowSaysWhatToType(unittest.TestCase):
    """收尾印出来的每一条都要写出该敲的命令 —— 指一个文件名不够。

    `AGENTS.md`「每一处引导都要写出该敲的命令」：判据是「读完这句他能不能直接
    动手」。「判据见 06-outreach-templates.md 渠道 1 那张表」不能，
    「补它：一次一个跑 `/job-apply <链接>`」能。
    """

    #: 收尾这一档现在有几条。数字本身不重要，**列在这里是为了新加一条时
    #: 有人来看一眼这条守卫** —— 下面那条断言对每一条都要成立。
    ACTIONABLE = (
        "check_greeting_keeps_the_five_rules",          # 开场白踩了五类禁区
        "check_maybe_tier_has_questions",               # 「可以考虑」没写要问什么
        "check_evaluation_sections",                    # 深评缺小节
        "check_company_claims_have_a_source",           # 说了公司的事没记出处
        "check_outreach_header_says_who_youre_talking_to",  # 抬头没说清跟谁说话
        "check_material_ready_without_a_stored_jd",     # 可投+有材料，而依据不在库里
    )

    def test_every_one_of_them_names_a_command(self):
        """要么自己写出命令，要么走 `_cli.live_tail`（它统一给命令）。

        判据原来是「函数体里有 `/job-apply {`」。那在只有三条、每条各自拼那句话
        时是对的；`live_tail` 提出来之后，命令不再出现在检查自己的函数体里 ——
        **守卫钉的是实现细节，而不是那件事本身**。现在两种写法都认。
        """
        for fn in self.ACTIONABLE:
            with self.subTest(fn=fn):
                i = SRC.index(f"def {fn}(")
                j = SRC.index("\ndef ", SRC.index("return", i))
                seg = SRC[i:j]
                self.assertTrue(
                    "live_tail" in seg or "/job-apply {" in seg,
                    f"{fn} 报了问题却没说该敲什么 —— "
                    f"要么自己写命令，要么调 `_cli.live_tail`")

    def test_the_shared_tail_really_prints_one(self):
        """那条共用的尾巴自己得真的印出命令来 —— 上面那半靠它兜底。"""
        import _cli
        src = pathlib.Path(_cli.__file__).read_text(encoding="utf-8")
        i = src.index("def live_tail(")
        seg = src[i:src.index("\ndef ", i)]
        self.assertIn("{cmd} {live[0][0]}", seg)

    #: 一个**确实出局**的岗（标了不投）。空库不行 —— 那时的答案是
    #: 「对不上职位库」，也就是**判不了**，而不是「出局了」。
    #: 2026-08-30 改 `live_tail` 时这两条桩当场红，红得对。
    OUT_STORE = {"k": {"url": "u", "status": "skipped"}}

    def test_a_dead_row_is_dropped_from_the_closing(self):
        """一行里一个都动不了时，整行不进收尾。

        实测「猎头岗对着顾问说「贵司」」那 9 份全已投 —— 读完什么也做不了，
        而它挤在真有活的那几条中间。判据收到**行**这一级：一条检查可能报两行，
        一行有活、一行没有。
        """
        import _cli
        rows = run_with([
            ("会问、但一个都动不了", lambda s, d: [
                ("warn", "死行",
                 "…" + _cli.live_tail("nobody", self.OUT_STORE, [("u", "A")])[1])]),
            ("会问、且有活", lambda s, d: (_cli.sendable_state("nobody", s),
                                        [("warn", "活行", "有活")])[-1]),
        ], actionable=True)
        self.assertEqual([r[1] for r in rows], ["活行"])

    def test_an_unknown_row_is_not_dropped(self):
        """**判不了 ≠ 动不了。** 对不上职位库的行要留在收尾里。

        `live_tail` 上一版把「对不上职位库」并进了「已经出局」，于是这种行会说
        「这些都已经投出去、标了不投或下线了」（假话），而且被整行滤掉 ——
        对着不知道的岗判死。实测 2026-08-30：「深评缺小节」喂进去的 128 个里
        有 **29 个**是这种，「投前必问」103 个里有 14 个。
        """
        import _cli
        rows = run_with([
            ("会问、但判不了", lambda s, d: [
                ("warn", "判不了的行",
                 "…" + _cli.live_tail("nobody", {}, [("u", "A")])[1])]),
        ], actionable=True)
        self.assertEqual([r[1] for r in rows], ["判不了的行"])
        self.assertIn("判不了还能不能发", rows[0][2])

    def test_the_mark_is_a_constant_not_a_second_copy(self):
        """滤行靠的是 `_cli.NO_LIVE` 这个常量，不是在别处再抄一遍那句中文。"""
        import _cli
        self.assertIn(_cli.NO_LIVE,
                      _cli.live_tail("nobody", self.OUT_STORE, [("u", "A")])[1])
        seg = SRC[SRC.index("def run(user: str"):SRC.index("def main(")]
        self.assertIn("_cli.NO_LIVE", seg)
        self.assertNotIn("已经投出去、标了不投或下线了", seg)


if __name__ == "__main__":
    unittest.main()
