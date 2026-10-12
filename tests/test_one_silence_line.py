# -*- coding: utf-8 -*-
"""「多少天没动静算该催」全仓库只能有一个数 —— 而 `/job-gmail-sync` 用的是 30。

`followups.QUIET_DAYS` 的注释 2026-08-13 就记过这件事：

> 实测同一件事有三个数：这里 10、投后统计写死 14、`job-gmail-sync.md` 写 30。
> 三处各说各的，用户看面板说「该催了」、看统计说「还在等」。
> 要改就改这里，别在别处另写一个。

它还宣称自己是「**全仓库唯一的定义**」。**那是个愿望，不是事实**：统计那处的
14 改了，`job-gmail-sync.md` 那个 30 又活了十天。

实测活动用户 2026-08-23，85 笔投递：

    安静 10-29 天   75 笔    ← 面板 / /job-outcome / /job-html-report / 自检都说该催
    安静 ≥30 天      0 笔    ← /job-gmail-sync 只在这一档才说「该跟进了」

也就是说那一步的「该跟进了」对他**整条流水线是空的**，而同一时刻别的每一处都在
说这 75 个该催了 —— 同一件事，两个屏幕上相反的话。

## 教训不是再喊一次「唯一」

喊过了，没用。要让别处**引不到数**：文档里写「按静默线（`followups.QUIET_DAYS`）」
并注明「别在这里另定一个数」，像 `job-html-report.md` 那条一样。
这份测试扫所有工作流，出现第二个数就红。

## 顺带：引号里要么放原话，要么别用引号

`MAX_FOLLOWUPS = 2` 的注释用「」括了一句 `outcome.md` 的话，而那句话在
`job-outcome.md` 里**一个字都搜不到** —— 它是转述。意思没错，但读的人无从
回去核这个 2 还成不成立（2026-08-23 就有人搜了一遍，落空）。
"""
import csv
import datetime as dt
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import followups as fu  # noqa: E402

FU = (ROOT / "tools" / "followups.py").read_text(encoding="utf-8")
GMAIL = (ROOT / "workflows" / "job-gmail-sync.md").read_text(encoding="utf-8")
OUTCOME = (ROOT / "workflows" / "job-outcome.md").read_text(encoding="utf-8")

#: 「超过/满 N 天」这类**规定性**写法。
#:
#: 关键词和数字之间什么都可能夹：加粗星号、全半角括号、逗号冒号。
#: **变异实测**：只允许 `\s*\*{0,2}` 时，把「超过静默线」改成
#: 「超过静默线（21 天」照样绿 —— 一个括号就漏了。
_DAYS = re.compile(r"(?:超过|满|安静满|静默线)[\s*（(，,：:、]{0,4}(\d+)\s*天")
#: 上下文里要真的在说沉默/跟进，否则「满 14 天」可能说的是归档。
#:
#: **按整行看，不要开一个字符窗口。** 变异实测：用 ±40 字的窗口时，
#: 把「超过静默线」改回「超过 30 天」照样绿 —— 那一行的「该跟进了」
#: 正好落在窗口外面。一行就是一句规定，它是天然的单位。
_CTX = re.compile(r"没动静|安静|静默|跟进|该催|催一次|失联|没回音")
#: 叙述历史或实测的行不算规定 —— 记录「原来写的是 30」时必须能写出那个 30。
_PAST = re.compile(r"实测|原来|曾经|代价|此前|当时")

#: 两侧都是汉字的那个空格。中文行内本来就没有空格，它只可能来自折行 ——
#: 注释里的引文跨行、被引文件里的原句不跨行，不抹平就永远对不上。
_CJK_GAP = re.compile(r"(?<=[一-鿿，。；：、（）「」*])"
                      r" +(?=[一-鿿，。；：、（）「」*])")


def _unquote(s: str) -> str:
    """剥掉行首的引用标记。注释里成段的说明常是引用块，`>` 会夹进句子中间
    （拉平之后会得到「投后统计写死 14、 > job-gmail-sync 写 30」），断言就永远落空。"""
    return re.sub(r"^\s*>\s?", "", s, flags=re.M)


def flat(s: str) -> str:
    """比对用的归一：剥掉强调标记、拉平折行、抹掉汉字之间的空格。

    `**` 也要剥：原文那句是 `**每次投递最多跟进两次。** 第二次跟进…`，
    强调落在哪半句是排版决定，回去搜这句话的人也不会连星号一起搜。
    """
    return _CJK_GAP.sub("", " ".join(_unquote(s).replace("**", "").split()))


def flat_marks(s: str) -> str:
    """同上，但**保留** `**` —— 断言里要钉「这句是加粗的」时用它。"""
    return _CJK_GAP.sub("", " ".join(_unquote(s).split()))


#: 「投完 N 天跟进」这类**节奏**写法 —— 和上面那条 `_DAYS` 不是同一个形状
#: （它没有「超过/满/静默线」这些触发词），所以旧扫描器一个都抓不到。
_CADENCE = re.compile(r"投完\s*(\d+)\s*[-~到至]\s*(\d+)\s*天|投完\s*(\d+)\s*天")


def prescriptive_day_counts() -> list:
    """所有**规定**沉默天数的地方 → [(文件, 行号, 天数)]。

    **`workflows/` 和 `tools/` 都要扫。** 这个函数原来只扫 `workflows/`，
    而给用户看的那句话恰恰是 Python 生成的 —— 实测 2026-08-24，
    `tools/` 里有 **6 处**硬写着「投完 3-5 天跟进是常规动作」
    （`build_dashboard.py` 5 处 + `doctor.py` 1 处），这条规矩一处都没拦到。

    代价不是「多一个数」，是那句话**只在越过静默线之后才显示**：

        投出去 85 个，76 个已经过了 10 天，一个回音都没有。下一步：
            /job-outcome followup     # 先催一遍（投完 3-5 天跟进是常规动作）

    读的人只会得出一个结论：那我早该催了，你怎么等到第 10 天才说。
    """
    out = []
    files = (sorted((ROOT / "workflows").rglob("*.md"))
             + sorted((ROOT / "tools").glob("*.py")))
    for f in files:
        out += [(f.name, i, n) for i, n
                in scan_lines(f.read_text(encoding="utf-8",
                                          errors="replace").splitlines())]
    return out


#: 「这是在讲历史」往前看几行。**别把它开大**：开到几十行等于给整段注释
#: 发豁免，扫描器就再也抓不到写在史料后面的新规定了（变异实测：改成 40
#: 时全部断言照绿，所以下面 `TheHistoryWindowStaysNarrow` 直接喂数据验它）。
PAST_WINDOW = 3


def scan_lines(lines: list) -> list:
    """一份文件的行 → [(行号, 天数)]。**接受行数组，好让测试直接喂数据。**"""
    out = []
    for i, ln in enumerate(lines, 1):
            # **「这是在讲历史」要往前看两行。** 判据本来是逐行的 —— markdown 里
            # 一句话通常就是一行，够用；而 Python 注释是**折行**的：
            # `followups.py` 那段写着「实测代价：…按 30 天判『该跟进了』，
            # 而活动用户 85 笔投递里 75 笔安静了 10-29 天、**0 笔满 30 天**」，
            # 「实测」在上一行，「满 30 天」在下一行 —— 逐行看就把一段史料
            # 报成了「另定了一个数」（2026-08-24 扩到 tools/ 时当场撞上）。
        if any(_PAST.search(x) for x in lines[max(0, i - PAST_WINDOW):i]):
            continue
        if _CTX.search(ln):
            for m in _DAYS.finditer(ln):
                out.append((i, int(m.group(1))))
        # 节奏写法不需要 `_CTX`：「投完 N 天」本身就在说跟进。
        for m in _CADENCE.finditer(ln):
            for g in m.groups():
                if g:
                    out.append((i, int(g)))
    return out


class EveryWorkflowUsesTheSameLine(unittest.TestCase):
    def test_the_scanner_finds_something(self):
        """控制用例：扫不到就是空跑，说出来，别假绿。"""
        self.assertTrue(prescriptive_day_counts(),
                        "一处沉默天数都没扫到 —— 多半是写法变了，"
                        "回去看 `_DAYS` / `_CTX`，别让它退化成空跑")

    def test_no_workflow_states_a_different_number(self):
        bad = [h for h in prescriptive_day_counts() if h[2] != fu.QUIET_DAYS]
        self.assertEqual(
            bad, [],
            f"这些地方另定了一个沉默天数（正本 `followups.QUIET_DAYS` "
            f"= {fu.QUIET_DAYS}）：{bad}")

    def test_a_gloss_next_to_the_citation_matches(self):
        """引用正本时顺手写出的那个数（`（followups.QUIET_DAYS，10 天）`）也要对。

        上面那条扫的是**另定一个数**的地方。这种写法不是另定 —— 它明说「按静默线
        判，别在这里另定一个数」，只是顺手把当前值写在括号里。所以扫描器按设计
        不管它。

        **可它照样会飘。** 实测 2026-08-31：把两份工作流里的「10 天」一起改成
        「17 天」（代码不动），**全量 6800 条一条都不红**。而读的人拿走的就是括号
        里那个数 —— 执行者照 `job-html-report.md` 判「还在等」用 17，
        `followups.QUIET_DAYS` 还是 10，两个屏幕上又是相反的话。

        这与 `test_shared_thresholds_agree` 那几条同源：**文档与代码之间那道缝，
        两边的守卫都以为对方管着。**
        """
        import re as _re

        glosses = []
        for f in sorted((ROOT / "workflows").rglob("*.md")):
            t = f.read_text(encoding="utf-8")
            for m in _re.finditer(
                    r"followups\.QUIET_DAYS`?\s*[，,]\s*(\d{1,3})\s*天", t):
                glosses.append((f.name, t[:m.start()].count(chr(10)) + 1,
                                int(m.group(1))))
        self.assertTrue(glosses,
                        "一处这种写法都没扫到 —— 抽取式坏了，这条会永远绿")
        bad = [g for g in glosses if g[2] != fu.QUIET_DAYS]
        self.assertEqual(
            bad, [],
            f"引用旁边顺手写的那个数和 `followups.QUIET_DAYS` "
            f"（= {fu.QUIET_DAYS}）对不上：{bad}")

    def test_history_may_still_name_the_old_number(self):
        """记录「原来写的是 30」不该被这条规则拦住 —— 那是证据，不是规定。"""
        self.assertIn("原来写的是 30 天", GMAIL)
        self.assertNotIn(("job-gmail-sync.md", 0, 30),
                         [(a, 0, c) for a, _, c in prescriptive_day_counts()])


class TheHistoryWindowStaysNarrow(unittest.TestCase):
    """史料豁免必须窄。开大了，扫描器对写在史料后面的新规定就全瞎了。

    变异实测 2026-08-24：把 3 改成 40，上面每一条断言照样绿 ——
    因为真实文件里没有「史料后面隔 4 行又立一条规矩」这种排布。
    所以这一组**直接喂构造的行**，不靠库里碰巧有没有那种排布。
    """

    def test_a_wrapped_history_note_is_exempt(self):
        """`followups.py` 那段就是这个形状：「实测」在上一行，天数在下一行。"""
        got = scan_lines(["#: > 实测代价（2026-08-23）：那一步按 30 天判「该跟进了」，",
                          "#: > 而 85 笔投递里 75 笔安静了 10-29 天、0 笔满 30 天。"])
        self.assertEqual(got, [], f"史料被当成规定了：{got}")

    def test_a_rule_after_the_window_is_still_caught(self):
        """**这条才是 N10 那个变异要抓的。** 隔开之后它就是一条新规定。"""
        lines = ["# 实测：原来写的是 30 天。"] + ["#"] * PAST_WINDOW             + ["# 超过 21 天没动静就该催。"]
        got = scan_lines(lines)
        self.assertTrue(got, "史料豁免盖住了后面那条真规定 —— 窗口开太大了")
        self.assertEqual([n for _, n in got], [21])

    def test_the_window_is_small(self):
        self.assertLessEqual(PAST_WINDOW, 5)

    def test_the_reason_is_recorded(self):
        src = (ROOT / "tests" / "test_one_silence_line.py").read_text(
            encoding="utf-8")
        i = src.index("PAST_WINDOW = ")
        self.assertRegex(flat(src[max(0, i - 500):i]), r"别把它开大")




class TheScannerReachesThePythonPlane(unittest.TestCase):
    def test_it_scans_tools_too(self):
        """给用户看的那句话是 Python 生成的 —— 只扫文档等于扫不到正主。"""
        import inspect
        src = inspect.getsource(prescriptive_day_counts)
        self.assertIn('"tools"', src)

    def test_a_cadence_number_would_be_caught_now(self):
        """控制用例：把那句话原样喂进扫描器的正则，它必须认出来。"""
        self.assertTrue(_CADENCE.search("先催一遍（投完 3-5 天跟进是常规动作）"))
        self.assertTrue(_CADENCE.search("投完 7 天再跟进"))

    def test_it_does_not_fire_on_ordinary_prose(self):
        """误报一次这条就会被整条关掉。"""
        self.assertFalse(_CADENCE.search("投完之后记一笔"))
        self.assertFalse(_CADENCE.search("这个岗挂了 3 天"))


class TheGmailStepDefersInsteadOfRestating(unittest.TestCase):
    def _step9(self) -> str:
        i = GMAIL.index("## Step 9：查一遍失联的")
        return GMAIL[i:GMAIL.index("\n---", i)]

    def test_it_names_the_source(self):
        self.assertIn("`followups.QUIET_DAYS`", self._step9())

    def test_it_forbids_a_second_number(self):
        """只改数字治不了病 —— 下一个人照样会在这儿写一个新的。"""
        self.assertIn("**别在这里另定一个数**", self._step9())

    def test_it_points_at_the_sibling_that_got_it_right(self):
        self.assertIn("job-html-report.md", self._step9())

    def test_it_records_what_it_cost(self):
        seg = flat_marks(self._step9())
        self.assertRegex(seg, r"75 笔安静了 10-29 天")
        self.assertRegex(seg, r"\*\*0 笔满 30 天\*\*")
        self.assertIn("2026-08-23", seg)

    def test_the_step_still_does_its_own_job(self):
        """这一步的既有边界不能被这次改动带走。"""
        seg = self._step9()
        self.assertIn("绝不为「失联」写任何东西", seg)
        self.assertIn("该跟进了", seg)


class TheSingleSourceAdmitsItWasNotSingle(unittest.TestCase):
    def _seg(self) -> str:
        i = FU.index("QUIET_DAYS = 10")
        return flat_marks(FU[max(0, i - 1800):i].replace("#:", " "))

    def test_it_still_claims_to_be_the_one_definition(self):
        self.assertIn("**这是全仓库唯一的定义**", self._seg())

    def test_but_it_now_says_that_was_a_wish(self):
        seg = self._seg()
        self.assertRegex(seg, r"「唯一」这个词当时是个愿望，不是事实")
        self.assertRegex(seg, r"那个 30 又活了十天")

    def test_it_gives_the_mechanism_not_another_slogan(self):
        """再喊一次「唯一」没用 —— 要说清怎么让别处引不到数。"""
        seg = self._seg()
        self.assertRegex(seg, r"\*\*让别处引不到数\*\*")
        self.assertIn("test_one_silence_line.py", seg)

    def test_the_original_three_numbers_record_survives(self):
        seg = self._seg()
        self.assertRegex(seg, r"这里 10、投后统计写死 14、 ?`job-gmail-sync\.md` 写 30")


class AQuoteIsAQuote(unittest.TestCase):
    """注释里用「」括起来的原话，必须能在被引的文件里原样搜到。"""

    def _quoted(self) -> str:
        i = FU.index("MAX_FOLLOWUPS = 2")
        seg = FU[max(0, i - 700):i]
        m = re.search(r"原话：「(.+?)」", seg.replace("#:", " "), re.S)
        self.assertIsNotNone(m, "MAX_FOLLOWUPS 上面找不到那句原话")
        return flat(m.group(1))

    def test_the_quote_is_findable_in_the_cited_file(self):
        q = self._quoted()
        doc = flat(OUTCOME)
        self.assertIn(q, doc,
                      f"这句「原话」在 job-outcome.md 里搜不到：{q!r}")

    def test_the_rule_it_leans_on_still_says_two(self):
        self.assertEqual(fu.MAX_FOLLOWUPS, 2)
        self.assertIn("每次投递最多跟进两次", OUTCOME)

    def test_the_misquote_is_recorded(self):
        i = FU.index("MAX_FOLLOWUPS = 2")
        seg = flat_marks(FU[max(0, i - 700):i].replace("#:", " "))
        self.assertRegex(seg, r"这里原来括的是一句转述，不是原话")
        self.assertRegex(seg, r"引号里要么放原话，要么别用引号")


class TheSignalItLeansOnIsReal(unittest.TestCase):
    """有语料时验一次：两条线真的会把同一批投递分到相反的结论上。"""

    def _rows(self):
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        u = p.read_text(encoding="utf-8").strip()
        f = ROOT / "users" / u / "job_search_tracker.csv"
        if not f.is_file():
            self.skipTest("没有投递记录")
        rows = list(csv.DictReader(f.open(encoding="utf-8-sig")))
        if len(rows) < 20:
            self.skipTest("投递记录太少")
        return rows

    def test_the_two_thresholds_really_disagree_on_this_corpus(self):
        """两条线（静默 10 天 / 满 30 天）之间那一档，语料里得真的有东西落进去。

        ## 2026-10-12：空档有两种，含义相反，这里分开

        实测活动用户 115 笔投递，年龄全在 **40-63 天**——最近一笔也是 40 天前，
        `[10, 30)` 那一档 0 笔。原来的写法直接 `assertGreater(between, 0)`，
        于是「他这阵子没投」和「这一档被吃掉了」报同一句话。

        判据：**有没有比 30 天更年轻的投递**。
        - 没有 → 语料里根本没有能落进这一档的东西，守卫无从验证，跳过（`skipTest`）；
        - 有、却仍然一笔试都没有 → 那一档真的空了，是真问题，照旧红。

        跳过的不是「验不过」，是「没有可验的」。真投出 10-29 天内的第一笔，
        这条自动恢复成原来的断言。
        """
        rows = self._rows()
        today = dt.date.today()
        between = 0
        younger = 0
        for r in rows:
            if (r.get("status") or "").strip() in fu.FINAL_STATUSES:
                continue
            d = fu.parse_date(r.get("date") or "")
            if not d:
                continue
            n = (today - d).days
            if fu.QUIET_DAYS <= n < 30:
                between += 1
            if n < 30:
                younger += 1
        if younger == 0:
            ages = sorted((today - fu.parse_date(r.get("date") or "")).days
                          for r in rows
                          if (r.get("status") or "").strip() not in fu.FINAL_STATUSES
                          and fu.parse_date(r.get("date") or ""))
            self.skipTest(
                f"投递记录里没有比 30 天更年轻的（最小 {ages[0] if ages else '—'} 天），"
                f"「[{fu.QUIET_DAYS}, 30)」那一档无从验证——不是这一档出了问题")
        self.assertGreater(between, 0,
                           f"有 {younger} 笔比 30 天年轻的，却没有一笔落在 "
                           f"[{fu.QUIET_DAYS}, 30) 那一档 —— 两条线中间那一档真的空了，"
                           f"重新量一次（规则本身仍然成立）")


if __name__ == "__main__":
    unittest.main()
