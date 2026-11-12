# -*- coding: utf-8 -*-
"""开场白那五条铁律，规则写了，此前没有任何东西在验它。

`06-outreach-templates.md` 渠道 1 用一整张表列了「这 200 字里不许出现的五类」，
每类都配了实际写过的反例。可那是**给执行者看的散文**：写的时候凭记忆遵守，
写完没人回头查。实测活动用户 2026-08-25，当时 264 份已出的开场白中
**49 处踩线、涉及 37 份（16%）**：

    开场铺垫 17 · 到岗时间 5 · 先谈钱 4 · 给短处加的引子 2

**对照组就在同一个自检块里。** 字数那条有一行自检（「开场白 NNN 字，≤200 ✓」），
236 份里 0 份超 200。同一个执行者、同一份模板，
差别只在有没有一行要他逐条报一遍。所以这次两头都补：

- **写的时候**：自检块加一行，逐类写「无」或写出那一句并说明为什么留。
- **写完之后**：`audit_pipeline` 加一条检查，扫全部 `outreach.md` 按类报数。

两条都要。只有自检没有审计，漏了没人知道；只有审计没有自检，每次都返工。

判「留意」不判「要修」：改法是重写那句话，没有 `--apply`
（同 `check_company_claims_have_a_source`、`check_maybe_tier_has_questions`）。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402
import audit_pipeline as A  # noqa: E402

TPL = (ROOT / "workflows" / "reference"
       / "06-outreach-templates.md").read_text(encoding="utf-8")

#: 那张表的五个行名。**改表就要改这里** —— 手工名单漏一条，那一类就没人验它
#: （同 `test_the_stage_axis_is_covered` 那张表的用法）。
FIVE = ("开场铺垫", "钱", "到岗时间", "看不见的短处", "给短处加的引子")


class TheTableStillHasFiveRows(unittest.TestCase):
    def test_each_row_is_still_there(self):
        seg = TPL[TPL.index("### 铁律：这 200 字里不许出现的五类"):][:2600]
        for w in FIVE:
            with self.subTest(rule=w):
                self.assertIn(w, seg, f"「{w}」那一行不见了")

    def test_they_only_bind_channel_one(self):
        """邮件、网申自评、求职信里谈条件讲缺口是正常的。
        这句要留着——没有它，检查范围会被扩到全部渠道，然后满屏假阳性。"""
        self.assertIn("五条只管渠道 1", TPL)


class TheSelfCheckAsksForThem(unittest.TestCase):
    """写的时候那一道。"""

    def _seg(self):
        i = TPL.index("## 自检（不属于要发出去的内容")
        return TPL[i:i + 1200]

    def test_the_line_exists(self):
        self.assertIn("五类禁语逐条查过", self._seg(), "自检块里没这一行")

    def test_it_names_all_five(self):
        seg = self._seg()
        for w in FIVE:
            with self.subTest(rule=w):
                self.assertIn(w, seg, f"自检行漏了「{w}」")

    def test_a_bare_tick_is_not_enough(self):
        """只打个勾等于没查。要么写「无」，要么写出那一句。"""
        self.assertRegex(self._seg(), r"逐类写「无」|写出那一句")

    def test_the_only_legal_keep_is_named(self):
        """一眼可见的差距本来就允许写。不点明这一条，
        执行者要么把它当违规删掉，要么拿它当挡箭牌留下任何东西。"""
        self.assertIn("一眼可见", self._seg())

    def test_the_evidence_for_this_line_is_written_down(self):
        """五类禁语自检需有明确的执行机制说明，确保规则可执行。"""
        seg = TPL[TPL.index("字数必须实际统计后填写"):][:1800]
        self.assertRegex(seg, r"自检|五类禁语", "没写自检机制")


class ThereIsExactlyOneWordList(unittest.TestCase):
    """判据只许有一份。**这一条是本文件自己犯过的错换来的。**

    2026-08-23 加审计那一版，我在 `audit_pipeline` 新写了一套正则词表 ——
    而 `export_web_data` 早就有一份 `GREETING_BANS`（面板复制按钮旁那条提示
    用的就是它）。两份词表不一样，于是同一件事报两个数：

        开场铺垫    面板那份 32 份    审计那份 17 份

    面板说这段话没问题、审计说有，用户没有办法判断该信谁。**词表就是判据，
    判据分叉就是两套标准。** 现在正本在 `_cli`，两处都从那儿取。

    顺带并出两笔：
    - 并集比任何一份都全（`看到这个` / `留意到贵` 只有面板那份有，
      `期望 45-60k` 那条数字规则只有审计那份有）。
    - 审计白捡了字数上限那一条 —— `greeting_problems` 一起查，我那份没有。
    """

    def test_the_table_lives_in_cli(self):
        self.assertTrue(hasattr(_cli, "GREETING_BANS"))
        self.assertEqual(_cli.GREETING_MAX, 200)

    def test_the_export_forwards(self):
        import export_web_data as X
        self.assertIs(X.GREETING_BANS, _cli.GREETING_BANS)
        self.assertIs(X.greeting_problems, _cli.greeting_problems)

    def test_the_audit_has_no_table_of_its_own(self):
        src = (ROOT / "tools" / "audit_pipeline.py").read_text(encoding="utf-8")
        self.assertNotIn("_GREETING_BANS", src, "审计又自己列了一份词表")
        # **窗口切到函数结束，不切固定长度。** 原来是 `src[i:i+3000]`，
        # 而说明里加一段就把判据那行挤出窗口（2026-08-25 加分档说明时撞上）。
        i = src.index("def check_greeting_keeps_the_five_rules(")
        j = src.index(chr(10) + "def ", i + 10)
        self.assertIn("_cli.greeting_hits", src[i:j], "没用共用的判据")

    def test_the_union_kept_both_halves(self):
        """两份各有对方没有的词。合表时任何一边被丢掉都是退步。"""
        for w in ("看到这个", "留意到贵", "非常荣幸"):     # 只有面板那份有
            with self.subTest(w=w):
                self.assertTrue(_cli.greeting_hits(f"您好，{w}的岗。"), w)
        for w in ("说句实话", "可立即", "学习能力强"):      # 只有审计那份有
            with self.subTest(w=w):
                self.assertTrue(_cli.greeting_hits(f"您好，{w}。"), w)

    def test_the_number_rule_needs_a_unit(self):
        """「期望 45-60k」要抓，「期望能在三年内…」不能抓 ——
        这类检查误报一次就会被整条忽略。"""
        self.assertTrue(_cli.greeting_hits("已离职，期望 45-60k。"))
        self.assertEqual(_cli.greeting_hits("期望能在三年内做成这件事"), [])


class TheGreetingIsReadTheSameWayEverywhere(unittest.TestCase):
    """切出来的那段话，两处也得一样。"""

    def test_the_audit_strips_the_self_check_tail(self):
        """尾巴上挂着 `（字数：199）` 和 `> 字数校验：…`。不剥的话字数那条
        把它们也算进去 —— 实测 3 份合规的被误报成超 200 字（207/208/232），
        而它们自己写着 199/200/183。"""
        g = A._greeting_of("""
## 打招呼开场白

您好，我做过 A。

（字数：199）
""")
        self.assertNotIn("字数", g, "自检尾巴没剥掉")
        self.assertIn("我做过 A", g, "把正文也剥没了")

    def test_it_reuses_the_panel_stripper(self):
        src = (ROOT / "tools" / "audit_pipeline.py").read_text(encoding="utf-8")
        # 按**符号**验，不按整行字面 —— 那一行后来变成了多行 import
        # （又加了 `parse_evaluation`），字面断言当场失效而它要保的东西没变。
        i = src.index("from build_dashboard import")
        self.assertIn("_strip_wordcount", src[i:i + 200], "又自己写了一份剥法")


class TheAuditCatchesWhatSlipsThrough(unittest.TestCase):
    """写完之后那一道。"""

    def _run(self, tmp, *greetings, live=False):
        """`live=True` 时给每份话术配一条「还活着」的职位库记录。

        不配的话它们全落进「对不上职位库」那一格 —— 那正是这个分档要区分的
        东西之一，所以两种夹具都要有。
        """
        apps = tmp / "documents" / "applications"
        seen = {}
        for i, g in enumerate(greetings):
            d = apps / f"示例科技{i}_产品经理"
            d.mkdir(parents=True)
            url = f"https://example.com/job/{i}"
            head = f"- 职位链接：{url}\n" if live else ""
            (d / "outreach.md").write_text(
                f"# 示例\n\n{head}\n## 打招呼开场白（≤200 字）\n\n{g}"
                f"\n\n## 邮件\n\n正文\n", encoding="utf-8")
            if live:
                seen[f"k{i}"] = {"url": url, "status": "ranked",
                                 "title": "产品经理", "company": f"示例科技{i}"}
        return A.check_greeting_keeps_the_five_rules(seen, {})

    def _with_user(self, *greetings, live=False):
        import tempfile
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "users" / "u").mkdir(parents=True)
            with mock.patch.object(A, "ROOT", root), \
                 mock.patch.object(A._cli, "pick_user", lambda *a, **k: "u"):
                return self._run(root / "users" / "u", *greetings, live=live)

    #: 每一类给一个真会被写出来的句子。**类别名从 `_cli.GREETING_BANS` 取**，
    #: 不在这里抄第二份 —— 抄件和正本分叉正是这一族的病根。
    SAMPLES = {
        "开场铺垫": "您好，我想应聘产品经理。我做过 A。",
        "先谈钱": "您好，我做过 A。想问下 98-99k 是按几薪算？",
        "抢答到岗时间": "您好，我做过 A。已离职、随时到岗。",
        "给短处加引子": "您好，我做过 A。先说清楚：这块我没做过。",
        "套话开头": "您好，贵司平台好，深受吸引。",
    }

    def test_the_samples_cover_every_class(self):
        """漏一类，那一类就没人验它。"""
        self.assertEqual(sorted(self.SAMPLES), sorted(_cli.GREETING_BANS),
                         "样例和正本的类别对不上了")

    def test_it_fires_on_each_class(self):
        for label, g in self.SAMPLES.items():
            with self.subTest(rule=label):
                out = self._with_user(g)
                self.assertEqual(len(out), 1, f"「{label}」没被抓到")
                self.assertIn(label, out[0][2])

    def test_a_clean_greeting_is_quiet(self):
        self.assertEqual(self._with_user(
            "您好，这条链路我做了十年，<作品名> 有 <N> 万注册用户。"
            "想问下这个岗前半年主要做哪一块？"), [])

    def test_one_file_counts_once(self):
        """一句话同时踩两类不该让文件数虚高——那一行数的是文件数。"""
        out = self._with_user("您好，我做过 A。已离职、随时到岗，期望 99-100k。")
        self.assertIn("1 份", out[0][2], f"文件数算重了：{out[0][2]}")

    def test_the_class_tally_still_counts_both(self):
        """分档答的是「主要犯哪一类」，两类都要记。"""
        msg = self._with_user(
            "您好，我做过 A。已离职、随时到岗，期望 99-100k。")[0][2]
        self.assertIn("抢答到岗时间 1", msg)
        self.assertIn("先谈钱 1", msg)

    def test_it_only_reads_the_greeting_section(self):
        """邮件正文里谈钱是允许的。扫整份文件会把合规的也报进来。"""
        import tempfile
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            d = root / "users" / "u" / "documents" / "applications" / "示例科技_产品经理"
            d.mkdir(parents=True)
            (d / "outreach.md").write_text(
                "# 示例\n\n## 打招呼开场白（≤200 字）\n\n您好，我做过 A。\n\n"
                "## 邮件\n\n我的期望是 99-100k，已离职随时到岗。\n",
                encoding="utf-8")
            with mock.patch.object(A, "ROOT", root), \
                 mock.patch.object(A._cli, "pick_user", lambda *a, **k: "u"):
                self.assertEqual(A.check_greeting_keeps_the_five_rules({}, {}), [])

    def test_it_is_a_warning(self):
        self.assertEqual(self._with_user("您好，我想应聘产品经理。")[0][0], "warn")

    def test_it_is_registered(self):
        self.assertIn(A.check_greeting_keeps_the_five_rules,
                      [fn for _n, fn in A.CHECKS], "写了没挂上去")

    def test_the_message_splits_what_can_still_be_sent(self):
        """「99 份有问题」听起来像待办 —— **而四分之三根本动不了。**

        这一条原来断言消息里写着「等着发出去」。实测活动用户 2026-08-25：
        99 份踩线里 **72 份已经投出去了**、13 份他标了不投、3 份岗位已下线，
        真正还发得出去的只有 11 份。「等着发出去」这句话是错的，
        错得还很贵：把一个基本动不了的数印成待办，读的人要么去改 99 份，
        要么整条忽略 —— 多半是后者。

        所以现在断言的是**分开报**：总数之外必须给出还能发的那个数。
        """
        msg = self._with_user("您好，我想应聘产品经理。")[0][2]
        self.assertRegex(msg, r"其中还发得出去的只有 \d+ 份")
        self.assertNotIn("等着发出去", msg,
                         "那句话已经被实测推翻了，别写回来")

    def test_it_names_the_ones_that_can_still_be_sent(self):
        """只给个数不够 —— 要能直接去改那几个。"""
        msg = self._with_user("您好，我想应聘产品经理。", live=True)[0][2]
        self.assertRegex(msg, r"其中还发得出去的只有 1 份")
        self.assertIn("就是这几个：", msg)
        self.assertIn("示例科技0", msg)

    def test_a_greeting_with_no_library_row_is_not_called_sendable(self):
        """对不上职位库的不算「还能发」—— 不知道就说不知道，别乐观地算进去。"""
        msg = self._with_user("您好，我想应聘产品经理。", live=False)[0][2]
        self.assertRegex(msg, r"其中还发得出去的只有 0 份")
        self.assertIn("对不上职位库", msg)


if __name__ == "__main__":
    unittest.main()
