"""投递状态记在页面上：只改一个字段，判断留给命令行。

## 这一步为什么从命令行搬过来

求职里最高频的动作是「我投了」「约面了」。按 `/job-outcome` 自己的定义，它做的事就是
**改台账 status 一列、追一条带日期的备注**——正落在 `serve.py` 那条边界之内：
「所有操作都是改一个字段，不需要判断力」。可 serve.py 此前只接了「不投 / 放回」，
于是最常做的那件事仍然要回命令行敲 `/job-outcome 公司名`、再答一串问题。

serve.py 当初存在的理由就是这句：「页面上一个动作，人要在两个地方各做一遍」。

## 三条边界，坏了都不显眼

1. **状态机只有一份。** 能点哪几个按钮由 `tracker.NEXT` 算好带给页面。TS 里另写
   一套的分叉样子是：页面画出一个按钮，服务端拒绝它——而两边看起来都没错。
2. **走不到的状态一律拒。** 不校验的话，一个构造的请求能把没投过的岗直接标成
   `hired`，而台账是 `/job-setup` 校准和 `/job-html-report` 统计的输入。
3. **撤销不许删别人的行。** 页面建的行才允许删，靠 `notes` 里的来源标记认。
   用户手写的记录被一次误点删掉，是这里最坏的结果。
"""

import ast
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_dashboard as bd  # noqa: E402
import tracker as tk  # noqa: E402

JOB = {"company": "某游戏公司", "title": "AI应用产品经理", "url": "https://x/1"}


def fresh() -> Path:
    return Path(tempfile.mkdtemp()) / "job_search_tracker.csv"


def rows_of(p: Path) -> list:
    return bd.load_tracker(p)


def match(p: Path, job=JOB):
    return bd.match_tracker(job, job["url"], rows_of(p))


class TheRealLookupIsExercisedAtLeastOnce(unittest.TestCase):
    """`_job_and_row` **不打桩**地跑一次 —— 别的测试都把它换成了 lambda。

    ## 为什么专门补这一条

    本文件其余用例都这么写（有意的隔离，把 `apply_status` 和磁盘布局分开）：

        serve._job_and_row = lambda job_id: (JOB, p, match(p))

    好处是 `apply_status` 的状态机测得干净；代价是**那个真函数一行都没跑过**。
    2026-08-21 用 `sys.monitoring` 量 `tools/` 的行覆盖率才看出来：
    `_job_and_row` 的函数体（读 `seen_jobs.json` → `_cli.seen_of` → 拼台账路径
    → `match_tracker`）在整套 1787 条测试里命中数为 0。

    它是**每个状态按钮的第一步**。而同一天刚在 `doctor.py` 修掉的 bug 正是这一类：
    有人把 `_cli.seen_of(data)` 改回 `data["seen"]`，老格式的库就整个查不到岗，
    点按钮只会说「职位列表里找不到这个岗了」——**而没有任何测试会红**。

    所以这条只做一件事：给一个真实的 `seen_jobs.json`（**用老格式**，那是更容易被
    改坏的一支），真调一次 `apply_status`，看它认不认得出这个岗、台账写没写对。
    """

    def _sandbox(self, store: dict):
        """造一个临时仓库根，把 serve 的 ROOT / 活动用户指过去。"""
        import json

        import export_web_data as ex
        import serve

        tmp = Path(tempfile.mkdtemp())
        js = tmp / "users" / "试用" / "job_scraper"
        js.mkdir(parents=True)
        (js / "seen_jobs.json").write_text(
            json.dumps(store, ensure_ascii=False), encoding="utf-8")
        saved = (serve.ROOT, serve.active_user)
        serve.ROOT = tmp
        serve.active_user = lambda: "试用"
        # **`job_id` 不是 URL**，是 `stable_id(url, title)`——`find_entry` 特意不按
        # URL 匹配（51job 实测同一个 URL 下挂着两个职位）。第一版这条测试传了 URL，
        # 于是两种格式都「找不到这个岗」——**红的是用例，不是代码**。
        return serve, tmp, saved, ex.stable_id(JOB["url"], JOB["title"])

    def test_it_finds_the_job_in_both_store_generations(self):
        rows = {
            "老格式（顶层直接是岗位字典）": {JOB["url"]: dict(JOB, status="ranked")},
            "新格式（包在 seen 里）": {"seen": {JOB["url"]: dict(JOB, status="ranked")}},
        }
        for label, store in rows.items():
            with self.subTest(格式=label):
                serve, tmp, saved, jid = self._sandbox(store)
                try:
                    job, path, row = serve._job_and_row(jid)
                    self.assertIsNotNone(
                        job, f"{label}：真查一次却找不到这个岗 —— 点按钮会说「找不到」")
                    self.assertEqual(job["company"], JOB["company"])
                    self.assertEqual(
                        path, tmp / "users" / "试用" / "job_search_tracker.csv",
                        "台账路径没按活动用户解析")
                    self.assertIsNone(row, "还没投过，台账里不该已经有行")

                    # 「找不到」那一支也走一次：三个 None，而不是抛。
                    # 四个写接口都靠它判「刷新一下页面再试」，抛出去就是 500。
                    self.assertEqual(serve._job_and_row("查无此 id"),
                                     (None, None, None))
                finally:
                    serve.ROOT, serve.active_user = saved

    def test_a_real_apply_status_writes_the_tracker_row(self):
        """整条链走一遍：查岗 → 写台账 → 撤销。**一处桩都不打。**"""
        serve, tmp, saved, jid = self._sandbox({JOB["url"]: dict(JOB, status="ranked")})
        try:
            r = serve.apply_status(jid, "applied")
            self.assertTrue(r["ok"], r)
            csv = tmp / "users" / "试用" / "job_search_tracker.csv"
            self.assertTrue(csv.is_file(), "台账没被创建")
            text = csv.read_text(encoding="utf-8")
            self.assertIn("applied", text)
            self.assertIn(JOB["company"], text)
            self.assertIn(JOB["url"], text, "没记来源链接，后面对不回是哪个岗")

            back = serve.undo_status(jid, r["prev"])
            self.assertTrue(back["ok"], back)
        finally:
            serve.ROOT, serve.active_user = saved


class UnblockingASiteActuallyWorks(unittest.TestCase):
    """面板上那个「解除冷却」按钮的服务端 —— 此前只在别人的 docstring 里被提过。

    `apply_unblock` 在整套测试里命中数为 0（2026-08-21 行覆盖率实测）。
    它是撞了风控之后**唯一**能自助恢复的入口：按不动，用户就只能去命令行敲
    `portal_budget.py --clear`，而那正是这个面板存在的理由要免掉的。
    """

    def test_it_clears_the_cooldown_and_refuses_when_there_is_none(self):
        import serve

        tmp = Path(tempfile.mkdtemp())
        (tmp / "users" / "试用" / "job_scraper").mkdir(parents=True)
        saved = (serve.ROOT, serve.active_user)
        serve.ROOT = tmp
        serve.active_user = lambda: "试用"
        sys.path.insert(0, str(ROOT / "tools"))
        import portal_budget as pb
        pb_saved = pb.ROOT
        pb.ROOT = tmp
        try:
            no = serve.apply_unblock("猎聘")
            self.assertFalse(no["ok"], "没被封也说解封成功了")
            self.assertIn("没有被封", no["error"])

            import datetime as dt
            # **封控时刻要跟着真实时钟走。** `apply_unblock` 内部取的是
            # `dt.datetime.now()`，而这里原来写死 2026-08-21 12:00 ——
            # 冷却 24 小时后到期，也就是说这条判据**在 2026-08-22 12:00 变红**，
            # 而且红的理由与它要守的东西无关（按钮没坏，是夹具过期了）。
            # 写死的时刻配上真实时钟，是一颗定时炸弹：写的那天绿，隔天中午红。
            now = dt.datetime.now()
            data = pb.load("试用")
            pb.block(data, "猎聘", "测试", now)
            pb.save("试用", data)

            yes = serve.apply_unblock("猎聘")
            self.assertTrue(yes["ok"], f"封着却解不开：{yes}")
            # **要从盘上重新读**——这一条守的是「按钮真的写下去了」，
            # 不是「函数返回了 ok」。而且要走 `block_state`，别直接读字段：
            #
            # 原来这里读的是 `blocked_until`。2026-08-21 封控改成按通道存之后
            # 那个字段恒为空，`assertFalse` 就**永远成立**——判据当场变成摆设，
            # 而它守的正是面板上那个「我处理好了」按钮。实测：把
            # `apply_unblock` 里的 `pb.save()` 整行删掉，全套 1906 条依然全绿。
            # 按钮静默空转，没有任何东西会发现。
            self.assertFalse(
                pb.block_state(pb.load("试用"), "猎聘",
                               now + dt.timedelta(hours=1))["blocked"],
                "说解开了，盘上还封着——按钮可能根本没写下去")
        finally:
            serve.ROOT, serve.active_user = saved
            pb.ROOT = pb_saved

    def test_a_concurrent_write_is_refused(self):
        """读→写这一小段里另一边记过账，不能拿旧快照整份盖回去。

        `fetch_details` 每抓一份 JD 就往同一个文件里记一次动作。用户在面板上
        点「继续抓」时，那一趟完全可能正好落一笔——盖掉它意味着这一趟已经
        发出的请求从账上消失，下一次的间隔判断看不见它们；反过来，他那份
        旧快照把这里刚解开的冷却写回封着（见 `fetch_details._commit_budget`）。
        """
        import datetime as dt

        import _cli
        import portal_budget as pb
        import serve

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        (tmp / "users" / "试用" / "job_scraper").mkdir(parents=True)
        saved = (serve.ROOT, serve.active_user, pb.ROOT)
        self.addCleanup(lambda: (setattr(serve, "ROOT", saved[0]),
                                 setattr(serve, "active_user", saved[1]),
                                 setattr(pb, "ROOT", saved[2])))
        serve.ROOT, serve.active_user, pb.ROOT = tmp, lambda: "试用", tmp

        now = dt.datetime.now()
        data = pb.load("试用")
        pb.block(data, "猎聘", "测试", now)
        pb.save("试用", data)

        orig_clear = pb.clear

        def clear_then_other_writes(data, name, now):
            out = orig_clear(data, name, now)
            other = pb.load("试用")
            pb.note(other, "BOSS", 1, now, kind="navigate")
            pb.save("试用", other)
            return out

        pb.clear = clear_then_other_writes
        self.addCleanup(setattr, pb, "clear", orig_clear)
        with self.assertRaises(_cli.StaleWrite):
            serve.apply_unblock("猎聘")


class TheChainGoesForwardOneStepAtATime(unittest.TestCase):
    """界面上不该摆一个八选一的下拉框——从「已投递」直接跳到「入职了」不是
    正常路径，摆出来只会让人点错。所以按当前状态给下一步。"""

    def test_not_applied_yet_offers_only_one_thing(self):
        self.assertEqual([s["label"] for s in tk.next_steps("")], ["我投了"])

    def test_each_state_offers_what_can_actually_happen_next(self):
        got = {s: [x["value"] for x in tk.next_steps(s)]
               for s in ("applied", "interview", "offer")}
        self.assertEqual(got, {
            "applied": ["interview", "rejected", "no response"],
            "interview": ["offer", "rejected"],
            "offer": ["hired", "offer declined"],
        })

    def test_your_own_decisions_are_final(self):
        """**终态分两种，这一条管「你自己做的决定」那一种。**

        已结案再改就不是「记一笔」而是修订，那该走 `/job-outcome` —— 原话如此。
        入职了、我拒了、我撤了：这三件是**你做的**，对方推翻不了，
        后面再动就是改历史。"""
        for s in ("hired", "offer declined", "withdrawn"):
            with self.subTest(s):
                self.assertEqual(tk.next_steps(s), [])

    def test_the_soft_endings_still_have_no_button(self):
        """**试过给它们加按钮，撤回了（2026-08-23）。**

        动机是真的：拒信多是同一天群发的模板，隔几天某个岗位重启或另一个部门
        单独捞人；「没下文」更是用户按 10 天线自己猜的（85 笔里 76 笔够线，
        面板一路在劝他点它），点完那一行就永远冻住。

        撤回有两条独立的理由，任一条都够：

        1. **那不是「记一笔」，是一个判断。** `job-outcome.md` Step 2 写着
           拒信后来邀约有三种读法，而那条正文自己写着「别替他判第一种」——
           一个按钮会把它塌成第一种。
        2. **`undo` 会连带丢掉拒绝原因**（`test_terminal_states_cannot_be_left`
           的 docstring 早就点名了这个前提）。

        去处改在页面上说（`build_dashboard.job_next_step`），不是加按钮。"""
        for s_ in ("rejected", "no response"):
            with self.subTest(s_):
                self.assertEqual(tk.next_steps(s_), [])

    def test_the_reason_for_that_is_written_next_to_the_table(self):
        """一张「这两个没有出口」的表看着像漏了。理由要挨着它写，
        否则下一个人（包括下一轮的我）会再加一次。"""
        src = (ROOT / "tools" / "tracker.py").read_text(encoding="utf-8")
        i = src.index("NEXT: dict[str, list[tuple[str, str]]] = {")
        seg = " ".join(src[i:i + 1800].split())
        self.assertIn("故意没有出口 —— 试过加，撤回了", seg)
        self.assertRegex(seg, r"别替他判第一种")
        self.assertRegex(seg, r"undo` 会连带丢掉拒绝原因|连带丢掉拒绝原因")

    def test_a_revived_row_leaves_the_terminal_set(self):
        """复活之后要真的重新进入在跑的那批 —— 否则催进度和邮件同步还当它结案了。"""
        self.assertIn("rejected", tk.FINAL_STATUSES)
        self.assertNotIn("interview", tk.FINAL_STATUSES)

    def test_case_and_spacing_do_not_break_it(self):
        """台账是人手工编辑的，大小写和空格都见过。"""
        self.assertTrue(tk.next_steps("  Applied "))


class WritingOnlyTouchesTheOneCell(unittest.TestCase):
    """`/job-outcome` 的原话：never restructure the CSV, reorder rows, or touch other rows。"""

    def test_first_mark_creates_the_row(self):
        p = fresh()
        r = tk.set_status(p, None, JOB, "applied", "2026-08-02")
        self.assertTrue(r["ok"])
        self.assertIsNone(r["prev"], "新建行的 prev 必须是 None——撤销靠它判断要删行")
        rows = rows_of(p)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "applied")
        self.assertEqual(rows[0]["company"], "某游戏公司")
        self.assertEqual(rows[0]["source"], JOB["url"])
        self.assertIn(tk.MARK, rows[0]["notes"])

    def test_it_does_not_guess_the_columns_it_cannot_know(self):
        """行业、岗位类型、渠道**留空**。台账是给人回看的，也是 `/job-setup` 校准的
        输入——填一个「大概是这个行业」进去，下次校准就按它算了。"""
        p = fresh()
        tk.set_status(p, None, JOB, "applied", "2026-08-02")
        row = rows_of(p)[0]
        for col in ("sector", "role_type", "channel", "contact_person", "fit_rating"):
            with self.subTest(col):
                self.assertEqual(row[col], "", f"{col} 被猜了一个值出来")

    def test_other_rows_are_untouched(self):
        p = fresh()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            "date,company,sector,role,role_type,channel,status,contact_person,"
            "fit_rating,notes,cv_file,cover_letter_file,source\n"
            "2026-01-01,别家,金融,风控产品,,BOSS,interview,王五,4,自己记的,,,https://y/9\n",
            encoding="utf-8")
        before = rows_of(p)[0]
        tk.set_status(p, None, JOB, "applied", "2026-08-02")
        after = [r for r in rows_of(p) if r["company"] == "别家"][0]
        self.assertEqual(after, before, "改一个岗把别人那行也动了")

    def test_the_column_order_of_an_existing_file_is_kept(self):
        """已有台账的列序原样写回——重排会让用户在 Excel 里认不出自己的表。"""
        p = fresh()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("company,role,status,notes,source\n某游戏公司,AI应用产品经理,applied,,https://x/1\n",
                     encoding="utf-8")
        tk.set_status(p, match(p), JOB, "interview", "2026-08-02")
        head = p.read_text(encoding="utf-8-sig").splitlines()[0]
        self.assertEqual(head, "company,role,status,notes,source")

    def test_the_note_says_what_happened_and_when(self):
        p = fresh()
        tk.set_status(p, None, JOB, "applied", "2026-08-02")
        tk.set_status(p, match(p), JOB, "interview", "2026-08-05")
        notes = rows_of(p)[0]["notes"]
        self.assertIn("2026-08-02", notes)
        self.assertIn("2026-08-05", notes)
        # 这一条原来断言的是 `assertIn("interview", notes)`——**把 bug 钉成了
        # 正确行为**。实测打开台账读到的就是「改为 interview」：`status` 一列
        # 用英文码是对的（统计要它），但备注是给人读的。
        self.assertIn(tk.LABEL["interview"], notes,
                      f"备注没说人话：{notes}")

    def test_a_stale_row_is_reported_not_silently_appended(self):
        """调用方那份 row 来自它自己那次读盘。盘上已经没有那一行时必须报错——
        静默追加一行会让「改状态」变成「多出一个岗」。"""
        p = fresh()
        tk.set_status(p, None, JOB, "applied", "2026-08-02")
        stale = match(p)
        p.write_text("company,role,status,notes,source\n", encoding="utf-8")
        r = tk.set_status(p, stale, JOB, "interview", "2026-08-05")
        self.assertFalse(r["ok"])
        self.assertEqual(len(rows_of(p)), 0, "找不到还硬加了一行")


class UndoPutsItBack(unittest.TestCase):

    def test_undo_of_a_change_restores_the_previous_status(self):
        p = fresh()
        tk.set_status(p, None, JOB, "applied", "2026-08-02")
        r = tk.set_status(p, match(p), JOB, "interview", "2026-08-05")
        tk.undo(p, match(p), r["prev"], "2026-08-05")
        self.assertEqual(rows_of(p)[0]["status"], "applied")

    def test_undo_of_the_first_mark_removes_the_row(self):
        """第一次点「我投了」之前台账里根本没有这一行，撤销就该让它消失——
        留一个 status 为空的行，那个岗会卡在既不是待投、也不是已投的鬼状态。"""
        p = fresh()
        r = tk.set_status(p, None, JOB, "applied", "2026-08-02")
        out = tk.undo(p, match(p), r["prev"], "2026-08-02")
        self.assertTrue(out["ok"])
        self.assertTrue(out["deleted"])
        self.assertEqual(rows_of(p), [])

    def test_undo_says_which_job_it_undid(self):
        """终端上那行日志按 `title`/`company` 印。

        实测跑一遍往返，终端上是三行「撤销：None」——`undo` 只回
        `{ok, deleted}`，没人带上是哪个岗。同一个服务里「记状态」印的是
        「记状态：某游戏公司」，撤销就该对得上。
        """
        import serve

        p = fresh()
        original = serve._job_and_row
        serve._job_and_row = lambda job_id: (JOB, p, match(p))
        try:
            r = serve.apply_status("任意 id", "applied")
            out = serve.undo_status("任意 id", r["prev"])
            self.assertTrue(out["ok"], out)
            self.assertTrue(
                out.get("title") or out.get("company"),
                f"撤销没说是哪个岗，终端会印「撤销：None」：{out}")
        finally:
            serve._job_and_row = original

    def test_a_hand_written_row_is_never_deleted(self):
        """没有来源标记 = 不是页面建的。宁可撤不掉，也不能删用户自己写的记录。"""
        p = fresh()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("company,role,status,notes,source\n"
                     "某游戏公司,AI应用产品经理,applied,我自己记的,https://x/1\n",
                     encoding="utf-8")
        out = tk.undo(p, match(p), None, "2026-08-02")
        self.assertFalse(out["ok"])
        self.assertIn("/job-outcome", out["error"], "拒绝了但没告诉他该怎么改")
        self.assertEqual(len(rows_of(p)), 1, "把用户手写的行删了")


class OneStateMachineNotTwo(unittest.TestCase):
    """能点哪几个按钮由 Python 算好带给页面。TS 里另写一套的分叉样子是：
    页面画出一个按钮，服务端拒绝它——而两边看起来都没错。"""

    def test_the_web_side_never_hard_codes_the_statuses(self):
        src = "\n".join(
            p.read_text(encoding="utf-8")
            for p in sorted((ROOT / "web" / "src").rglob("*.ts*")))
        # 注释与类型声明里出现是允许的（那是解释），赋值/字面量里出现才是抄了一份
        code = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
        code = re.sub(r"^\s*//.*$", "", code, flags=re.M)
        for s in ("no response", "offer declined"):
            with self.subTest(s):
                self.assertNotIn(f'"{s}"', code,
                                 f"TS 里写死了状态 {s!r} —— 状态机该只有 tracker.NEXT 一份")

    def test_the_exporter_hands_the_steps_to_the_page(self):
        src = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
        self.assertIn("next_steps(", src, "导出器没把下一步带给页面")

    def test_jobs_with_no_tracker_row_still_get_their_step(self):
        """没投过的岗也有下一步（「我投了」），而那恰恰是最需要能点一下的那批。
        这句要写在 `continue` 之前——写后面就一个按钮都没有。"""
        src = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
        i, j = src.index('j["nextStatuses"]'), src.index("if not r:\n            continue")
        self.assertLess(i, j, "nextStatuses 落在 `if not r: continue` 后面了——"
                              "没投过的岗一个按钮都没有")


class TheServerRefusesAStepYouCannotReach(unittest.TestCase):
    """不校验的话，一个构造的请求能把没投过的岗直接标成 hired，
    而台账是 `/job-setup` 校准和 `/job-html-report` 统计的输入。"""

    def test_the_rule_itself_refuses_a_jump(self):
        """先验规则本身。它是纯函数，能直接喂真值——不用去 grep 源码。"""
        self.assertTrue(tk.can_go("", "applied"))
        self.assertTrue(tk.can_go("applied", "interview"))
        self.assertTrue(tk.can_go(" Applied ", "interview"), "大小写空格没归一")
        for now, nxt in [("", "hired"), ("", "interview"), ("applied", "hired"),
                         ("applied", "offer"), ("hired", "interview"),
                         ("rejected", "applied"), ("applied", "乱写的")]:
            with self.subTest(f"{now or '还没投'} -> {nxt}"):
                self.assertFalse(tk.can_go(now, nxt),
                                 f"从「{now or '还没投'}」竟然能直接走到「{nxt}」")

    def test_apply_status_really_refuses_and_writes_nothing(self):
        """**真调 `apply_status`**，不看源码长什么样。

        只验「调用了 can_go」是不够的：`if False and tracker.can_go(...)` 照样
        调用了它，校验却永远放行——突变当场证明那条 AST 检查漏得过去。
        结构检查能说「该有的零件在」，说不了「它真的在把关」。

        `_job_and_row` 要读活动用户和 seen_jobs.json，这里换成一份固定桩，
        测的就只剩下那道闸门本身。
        """
        import serve

        p = fresh()
        original = serve._job_and_row
        serve._job_and_row = lambda job_id: (JOB, p, match(p))
        try:
            bad = serve.apply_status("任意 id", "hired")   # 还没投就想标录用
            self.assertFalse(bad["ok"], "没投过的岗被一步标成了 hired")
            self.assertEqual(rows_of(p), [], "拒绝了，却还是往台账里写了东西")

            good = serve.apply_status("任意 id", "applied")
            self.assertTrue(good["ok"], f"正常的一步被拦了：{good}")
            self.assertEqual(rows_of(p)[0]["status"], "applied")

            skip = serve.apply_status("任意 id", "hired")  # applied 也到不了 hired
            self.assertFalse(skip["ok"])
            self.assertEqual(rows_of(p)[0]["status"], "applied", "被拒了却改了状态")

            # 拒绝的话是**给用户看的**。原来它把两头的状态原样插进去，读出来是
            # 「从「还没投」走不到「hired」」——右边那个是内部码。
            for code in ("hired", "applied"):
                if code in tk.LABEL[code]:      # 「拿到 offer」这类词本就这么说
                    continue
                self.assertNotIn(code, bad["error"] + skip["error"],
                                 f"拒绝提示里漏出内部码「{code}」："
                                 f"{bad['error']} / {skip['error']}")
            self.assertIn(tk.LABEL["hired"], bad["error"],
                          f"拒绝提示没说清拦的是哪一步：{bad['error']}")
        finally:
            serve._job_and_row = original

    def test_serve_actually_calls_it(self):
        """用 **AST** 找调用，不 grep 文本。

        上一版这条搜的是字符串 `tracker.NEXT`，而 `apply_status` 自己的 docstring
        里就写着这四个字——把校验整个删掉，它照样绿。突变当场抓到。
        断言要挂在**会执行的东西**上，不是挂在解释它的散文上。
        """
        tree = ast.parse((ROOT / "tools" / "serve.py").read_text(encoding="utf-8"))
        fn = next((n for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef) and n.name == "apply_status"), None)
        self.assertIsNotNone(fn, "serve.py 里没有 apply_status")
        calls = {ast.unparse(n.func) for n in ast.walk(fn) if isinstance(n, ast.Call)}
        self.assertIn("tracker.can_go", calls,
                      f"apply_status 没调用 tracker.can_go——任何状态都写得进去。"
                      f"它调用的是：{sorted(calls)}")

    def test_the_endpoints_are_wired(self):
        src = (ROOT / "tools" / "serve.py").read_text(encoding="utf-8")
        for p in ("/api/status", "/api/status/undo"):
            with self.subTest(p):
                self.assertIn(f'path == "{p}"', src, f"{p} 没接上")

    def test_undo_does_not_fold_null_into_empty_string(self):
        """`prev` 为 null 表示「那行是页面刚建的」，撤销即删行。折成空串就变成了
        「把状态清空」——空串在台账里是一个合法状态，那个岗会卡在鬼状态。

        **先剥注释再验**：那一处的注释里正好引用了要拦的坏写法，不剥就会命中
        自己的说明文字，测试变成永远红。这个仓库在别处已经栽过好几次了。
        """
        src = (ROOT / "tools" / "serve.py").read_text(encoding="utf-8")
        code = re.sub(r"^\s*#.*$", "", src, flags=re.M)
        # 取到行尾再回退一个 `)`：`[^)]*` 会被 `body.get("prev")` 自己的括号截断，
        # 抓到半截 `body.get("prev"`，于是这条永远红。
        call = re.search(r"undo_status\(job_id,\s*(.*?)\)\s*$", code, re.M)
        self.assertIsNotNone(call, "找不到 undo_status 的调用")
        self.assertEqual(call.group(1).strip(), 'body.get("prev")',
                         "prev 被加工过了 —— null 与空串是两件事，"
                         "折成空串就把「删掉这行」变成了「把状态清空」")


class TheServerActuallyStarts(unittest.TestCase):
    """新增的 import 打错名字、循环引用，都要在这里当场暴露 —— 不然症状是
    「页面打不开」，而所有单元测试都是绿的。"""

    def test_serve_imports_clean(self):
        r = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, r'%s'); import serve" % (ROOT / "tools")],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 0, f"serve.py 导入就炸了：\n{r.stderr}")


if __name__ == "__main__":
    unittest.main()
