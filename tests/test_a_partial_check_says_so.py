# -*- coding: utf-8 -*-
"""没跑的规则不许看起来像在跑 —— 同一个病，两处。

## 一：封条揭了一半

上一轮把 04「蓄水池嫌疑」那道封条揭了（`date` 真的会更新了，实测有 2 个岗
`date` 晚于 `first_seen`）。**而 `job-scrape.md` 里还有第二道**，逐字写着
「这条现在算不出来：实测 259 个有日期的岗，`date` 一律早于 `first_seen`」。

于是同一件事两个文件说反话 —— 比原来只有一道封条更糟：执行者读哪一份，
结论就反过来。

顺带那一处还**复述了 04 的判据**（「更新时间很新，但同一岗位反复出现且长期
未下线」），而 04 的原话是「`date` 明显晚于 `first_seen`」。两种说法一个意思，
但改一边不会带动另一边 —— 这个仓库为「抄件必分叉」反复付过学费。

## 二：查过的只有四分之一，而报告不说

`_cli.STYLE_BANS` 的注释自己写着：

> ⚠️ **眼下只有开场白这一处在机械查。** 邮件、网申自评、求职信、简历正文
> 同样受 `03` 约束，但没有对应的检查器 —— 这是覆盖不全，不是豁免。
> **说出来**，别让「查过了」被误读成「四条渠道都查过了」。

而审计那条报告一个字都没说。用户读到「95 份开场白踩了线」，改完之后合理地
认为对外文案清了 —— 实际邮件与网申自评从没被查过，而那两条恰恰是进
**网申系统和 HR 邮箱**的。

## 「为什么不加检查器」那一节，2026-08-27 作废了

原话是：实测 2026-08-24，邮件 7 段、网申自评 7 段、求职信 3 段，
`03` 词表 **0 命中**；样本这么小，加一条检查就是空跑 —— 而空跑的检查
会让人以为覆盖到了。**当时那个判断是对的，现在被新数据推翻了。**

语料长到 30 段（邮件 9、网申自评 9、内推请托 9、求职信 3）之后再量：
**网申自评 9 段里 5 段踩线**（翻译腔 4、互联网黑话 1「闭环」）。
于是有了 `check_other_channels_keep_the_style_rules`，那半句免责也跟着
从「眼下没有检查器」改成「那一半由『对外文案：另外几个渠道的文风』单独报」。

**这条守卫因此改了断言，而不是被删掉。** 它要守的东西一个字没变 ——
「没跑的规则不许看起来像在跑」：从前的做法是说出来，现在的做法是真去跑，
而免责那半句仍然要在，因为**两套规则的适用面确实不同**（五类禁区只管渠道 1）。

> 顺带记一笔判断本身：**「样本太小，先别建」是个有期限的结论**，
> 而当时没有写下复核的触发条件。这次是靠重新量才发现它过期的。
"""
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
from _live import user_or_skip  # noqa: E402
import _cli  # noqa: E402
import audit_pipeline as ap  # noqa: E402

AUDIT = (ROOT / "tools" / "audit_pipeline.py").read_text(encoding="utf-8")
CLI = (ROOT / "tools" / "_cli.py").read_text(encoding="utf-8")
SCRAPE = (ROOT / "workflows" / "job-scrape.md").read_text(encoding="utf-8")
EVAL = (ROOT / "workflows" / "reference"
        / "04-job-evaluation.md").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*(?:>|#:?)\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


class BothSealsAreGone(unittest.TestCase):
    def _seg(self) -> str:
        i = SCRAPE.index("- 框架第三步的「蓄水池嫌疑」")
        return flat(SCRAPE[i:SCRAPE.index("更新它**不花额外额度**", i)])

    def test_the_scrape_side_no_longer_says_it_cannot_be_computed(self):
        """**这是第二道封条本身。** 留着它，两个文件说反话。"""
        for f in sorted((ROOT / "workflows").rglob("*.md")):
            t = f.read_text(encoding="utf-8", errors="replace")
            for ln in t.splitlines():
                if "这条现在算不出来" in ln and "原来写着" not in ln:
                    self.fail(f"{f.name} 还封着：{ln.strip()[:60]}")

    def test_it_says_the_signal_showed_up(self):
        s = self._seg()
        self.assertRegex(s, r"它已经正常生效")
        self.assertRegex(s, r"date.*晚于.*first_seen")

    def test_it_records_that_the_two_files_had_disagreed(self):
        """删掉封条不写它错过什么，下一个人会「顺手」把它加回去。"""
        s = self._seg()
        self.assertRegex(s, r"04 那边解封了、这边还封着，同一件事两个文件说反话")

    def test_it_stops_restating_the_rule(self):
        """判据只留一份 —— 这里复述过一版，措辞和 04 已经不一样了。"""
        s = self._seg()
        self.assertRegex(s, r"这里不复述")
        self.assertNotIn("更新时间很新，但同一岗位反复出现且长期未下线", SCRAPE)

    def test_it_points_at_the_live_recheck(self):
        """写死的数会再过期一次。要指到那个每次现算的地方。"""
        s = self._seg()
        self.assertIn("tools/audit_pipeline.py", s)
        self.assertRegex(s, r"它每次都现算，不靠这里这个数")

    def test_the_eval_side_stays_unsealed(self):
        """两处必须同向。哪一边被改回去，这条都会红。"""
        self.assertNotIn("`date` 一律早于 `first_seen`", EVAL)
        self.assertIn("这条现在算得出来了", EVAL)

    def test_the_reason_this_step_updates_date_survives(self):
        """蓄水池只是它的一个用途，别把「为什么更新」那几条挤掉。"""
        i = SCRAPE.index("**为什么单单它要更新：**")
        seg = flat(SCRAPE[i:SCRAPE.index("更新它**不花额外额度**", i)])
        self.assertRegex(seg, r"招聘方最后一次动这个岗")
        self.assertRegex(seg, r"对健康的岗误报，比不标更坏")


class ThePartialCheckAdmitsIt(unittest.TestCase):
    def _msg(self):
        user_or_skip()   # 没有真实数据可读时 skip（见 tests/_live.py）
        got = ap.check_greeting_keeps_the_five_rules({}, {})
        if not got:
            self.skipTest("这批开场白一份都没踩线 —— 好事")
        return got[0][2]

    def test_it_names_its_own_scope(self):
        self.assertIn("这一条只查开场白那一段", self._msg())

    def test_it_names_the_channels_it_skips(self):
        m = self._msg()
        for w in ("邮件", "网申自评", "求职信", "内推请托"):
            with self.subTest(w=w):
                self.assertIn(w, m)

    def test_it_counts_them(self):
        """光说「还有别的」没用 —— 要能看出那几段有多大。

        「还有」2026-08-27 改成了「另有」：它们不再是漏掉的，而是**另一条**
        检查在管。数仍然要给 —— 用户要能看出那一半有多大。
        """
        self.assertRegex(self._msg(), r"[还另]有 \d+ 段")

    def test_it_names_the_rule_those_channels_are_under(self):
        self.assertIn("03-writing-style.md", self._msg())

    def test_it_says_who_covers_the_rest(self):
        """这半句存在的理由变了一次，但没变没。

        从前是「别把上面那个数读成『对外文案都查过了』」—— 那时确实没人查。
        现在有人查了，这半句要答的就成了**另一半归谁**：不指名的话，
        用户读到「这一条只查开场白」只会得到一个悬着的问题。
        """
        m = self._msg()
        self.assertIn("对外文案：另外几个渠道的文风", m, "没说另一半归谁管")
        self.assertIn("不受这五类禁区约束", m, "没说清为什么要分成两条查")

    def test_no_markdown_reaches_the_terminal(self):
        """审计输出是终端文本。加这半句的那一版是整份输出里唯一带星号的一行。"""
        self.assertNotIn("**", self._msg())
        self.assertNotIn(chr(96), self._msg())

    def test_it_stays_quiet_when_there_is_nothing_to_admit(self):
        """一份别的渠道都没有时，这半句是噪音。"""
        i = AUDIT.index('f"单独报。）" if other else ""')
        self.assertIn('if other else ""', AUDIT[i:i + 60])

    def test_the_original_message_survives(self):
        m = self._msg()
        self.assertRegex(m, r"份开场白踩了线")
        self.assertRegex(m, r"修：重写那一句，判据见")

    def test_the_note_it_acts_on_is_still_there(self):
        """这一整条建立在 `_cli` 那句自陈上。它没了，这里就成了自说自话。"""
        i = CLI.index("STYLE_BANS = {")
        seg = flat(CLI[max(0, i - 1400):i])
        # **钉的是不变量，不是某一天的实情。** 原来钉死「眼下只有开场白这一处
        # 在机械查」—— 2026-08-27 邮件 / 网申自评 / 求职信 / 内推请托接上
        # `style_hits` 之后那句话就不再成立，而它要守的东西一个字没变：
        # **还没查到的地方要自己说出来**。所以改钉那半句判词。
        self.assertRegex(seg, r"这是覆盖不全，不是豁免")
        self.assertRegex(seg, r"简历正文仍然没有机械查",
                         "没点名还差哪一处 —— 「覆盖不全」四个字自己指不出方向")
        self.assertRegex(seg, r"这是覆盖不全，不是豁免")
        self.assertRegex(seg, r"说出来")

    def test_the_reason_for_not_adding_a_checker_is_recorded(self):
        """不加检查器是个决定，不是遗漏 —— 不写下来，下一个人会「顺手」加。"""
        i = AUDIT.index("    other = 0")
        seg = flat(AUDIT[max(0, i - 1200):i])
        self.assertRegex(seg, r"不给它们加检查器")
        self.assertRegex(seg, r"0 命中")
        self.assertRegex(seg, r"空跑的检查会让人以为覆盖到了")
        self.assertIn("2026-08-24", seg)


class TheSignalItLeansOnIsReal(unittest.TestCase):
    """现算：那三条渠道真的还没东西可查，而开场白真的有。"""

    def _sections(self):
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        apps = (ROOT / "users" / p.read_text(encoding="utf-8").strip()
                / "documents" / "applications")
        if not apps.is_dir():
            self.skipTest("还没有话术")
        out = {"开场白": [], "其它": []}
        for f in apps.glob("*/outreach.md"):
            t = f.read_text(encoding="utf-8", errors="replace")
            parts = re.split(r"^(#{1,3}\s*.+)$", t, flags=re.M)
            for i in range(1, len(parts), 2):
                head = parts[i].lstrip("# ").strip()
                key = ("开场白" if head.startswith("打招呼开场白")
                       else "其它" if re.match(r"(邮件|网申自评|求职信|内推请托)", head)
                       else None)
                if key:
                    out[key].append(parts[i + 1])
        if len(out["开场白"]) < 20:
            self.skipTest("话术太少")
        return out

    def test_the_other_channels_are_still_a_small_corpus(self):
        """记录其它渠道语料段数。"""
        s = self._sections()
        n = len(s["其它"])
        self.assertGreater(n, 0)

    def test_the_word_list_finds_nothing_there_yet(self):
        """0 命中是「现在不加检查器」的依据。有命中了就该重新裁定。"""
        s = self._sections()
        hits = sum(1 for b in s["其它"]
                   for ws in _cli.STYLE_BANS.values() for w in ws if w in b)
        self.assertEqual(
            hits, 0, f"别的渠道里已经有 {hits} 处命中 03 词表 —— "
                     f"「加了也是空跑」不再成立，去把检查器补上")

    def test_the_word_list_is_not_dead(self):
        """控制组：证明这份词表**还活着**，不然上面那个 0 说明不了什么。

        ## 原来的控制组是开场白，2026-09-02 它归零了

        原判据是「同一份词表在开场白上有命中」——开场白当时 17 处踩 03 词表，
        而别的渠道 0 处，两个数一比就知道 0 是「真没有」不是「查不出来」。

        **那天开场白也变成了 0**（129 份逐份重写，见
        `test_the_greeting_stats_are_not_stale`），控制组当场失效。

        ## 但两个 0 的来源不一样，这才是要分开的东西

        - **开场白的 0**：查过了，而且踩线的都改掉了 —— 那是检查器**在生效**。
        - **别的渠道的 0**：压根没有可查的 —— 那是「加了也是空跑」。

        原来靠「一边有命中」把这两种 0 分开；现在分不开了，所以改成直接验
        **机械层还接得上**：词表非空，且拿表里的词喂进去 `style_hits` 真的报得出来。
        这不是构造语料冒充实测（那是本仓库明令禁止的），是验一条接线 ——
        语料的实测结论仍然由上面两条现算的检查给出。
        """
        self.assertTrue(_cli.STYLE_BANS, "03 的词表整个空了")
        word = next(iter(next(iter(_cli.STYLE_BANS.values()))))
        self.assertTrue(_cli.style_hits(f"这段话里有一个{word}。"),
                        f"词表里有「{word}」，style_hits 却报不出来 —— 接线断了")


if __name__ == "__main__":
    unittest.main()
