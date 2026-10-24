# -*- coding: utf-8 -*-
"""读一次库、评十几分钟、再整份写回——中间用户点的按钮不能被静默抹掉。

## 这不是假想

2026-08-19 实测复现：

    命令行侧读职位库  →  ……AI 评分十几分钟……  →  整份写回
                          ↑ 用户在总览页点了「不投」，已经落盘

写回后库里变回 `ranked`、`skip_reason` 消失。**没有任何报错**——用户以为标上了，
刷新才发现没有。

## 为什么不是造一把锁

跨进程锁要处理死锁、超时、残留锁文件，每一个都比现在这个问题更难查。
这里选的是**把静默的数据丢失换成大声的报错**：写回时比一次版本戳，
对不上就抛 `StaleWrite` 且不写盘，调用方重读一次再应用。

原子写（`atomic_write`）防的是**写坏**（断电留下半截文件），
这条防的是**写旧**。仓库先前只防住了前一个。
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402


class StaleWritesAreRefused(unittest.TestCase):

    def _tmp(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        p = d / "store.json"
        _cli.atomic_write(p, json.dumps({"seen": {"a": {"status": "ranked"}}}))
        return p

    def test_a_write_based_on_a_stale_read_is_refused(self):
        p = self._tmp()
        mine, stamp = _cli.load_json_stamped(p)          # ① 命令行侧读
        other = json.loads(p.read_text(encoding="utf-8"))
        other["seen"]["a"]["status"] = "skipped"          # ② 面板改了
        _cli.atomic_write(p, json.dumps(other))
        mine["seen"]["a"]["rank_date"] = "2026-08-19"     # ③ 命令行写回旧快照
        with self.assertRaises(_cli.StaleWrite):
            _cli.atomic_write(p, json.dumps(mine), expect=stamp)
        # 用户那一下必须还在
        self.assertEqual(
            json.loads(p.read_text(encoding="utf-8"))["seen"]["a"]["status"], "skipped",
            "陈旧写没被拦住——用户在面板上点的那一下被抹掉了")

    def test_a_fresh_write_still_goes_through(self):
        """守卫不能把正常的写也挡了。"""
        p = self._tmp()
        data, stamp = _cli.load_json_stamped(p)
        data["seen"]["a"]["status"] = "expired"
        _cli.atomic_write(p, json.dumps(data), expect=stamp)
        self.assertEqual(
            json.loads(p.read_text(encoding="utf-8"))["seen"]["a"]["status"], "expired")

    def test_the_error_says_what_to_do(self):
        """**指令按受众分，所以查两个落点，不查消息本身。**

        这条原来断言消息里有「重新读一次」。后来发现那句是写给**读代码的人**的，
        而命令行前面的人需要的是「把这条命令再跑一遍」——`run_cli` 包起来之后
        两句并排出现，自相矛盾（见 `test_a_stale_write_is_not_a_crash.py`）。

        于是消息只留事实，指令分到两处：库调用方看 docstring，命令行用户看
        `run_cli` 的输出。意图没变——报错必须说下一步该做什么——只是问对了人。
        """
        p = self._tmp()
        _, stamp = _cli.load_json_stamped(p)
        _cli.atomic_write(p, json.dumps({"seen": {}}))
        try:
            _cli.atomic_write(p, json.dumps({"seen": {}}), expect=stamp)
            self.fail("没抛 StaleWrite")
        except _cli.StaleWrite as e:
            self.assertIn("被改过了", str(e), "报错没说清发生了什么")
        self.assertIn("重新读一次", _cli.StaleWrite.__doc__ or "",
                      "给库调用方的下一步没了")
        import inspect
        self.assertIn("再跑一遍", inspect.getsource(_cli.run_cli),
                      "给命令行用户的下一步没了")


class TheToolsThatHoldTheStoreUseIt(unittest.TestCase):
    """读到写之间有活要干的工具，必须带上版本戳。"""

    def test_writeback_and_prescreen_pass_the_stamp(self):
        for name in ("writeback.py", "prescreen.py"):
            src = (ROOT / "tools" / name).read_text(encoding="utf-8")
            self.assertIn("load_json_stamped", src, f"{name} 没记版本戳")
            self.assertIn("expect=", src, f"{name} 写回时没带版本戳")

    def test_the_rank_workflow_says_so(self):
        wf = (ROOT / "workflows" / "job-rank.md").read_text(encoding="utf-8")
        self.assertIn("写回前先确认这期间没人动过库", wf)
        self.assertIn("StaleWrite", wf)
        # 重试的正确做法要写出来——直接重试等于把用户那一下再抹一次
        self.assertIn("不要直接重试", wf)


class LongWritersCarryTheStamp(unittest.TestCase):
    """读一次库、中间扫盘/读详情、再写回 —— 这几条都必须带版本戳。

    只覆盖 `writeback` / `prescreen` 是不够的；`jd_store --merge`、`archive`
    的叠加层、`score.apply` 都会在中间做不少事。下面用「读之后立刻模拟一次
    面板写入」的方式，证明它们会在写回那一刻让路，而不是静默覆盖。
    """

    def test_jd_merge_refuses_a_stale_write(self):
        import datetime as _dt
        import jd_store

        with self._tmp_repo() as root:
            import _cli
            p, key = self._job(root, "https://x/jd", "详情岗")
            (p.parent / "details").mkdir()
            (p.parent / "details" / f"{key}.json").write_text(
                json.dumps({"url": "https://x/jd", "title": "详情岗",
                            "location": "上海"}, ensure_ascii=False),
                encoding="utf-8")
            old_root = jd_store.ROOT
            jd_store.ROOT = root
            orig_load = jd_store.load

            def concurrent(user, url, title):
                data = json.loads(p.read_text(encoding="utf-8"))
                data["seen"][key]["status"] = "skipped"
                _cli.atomic_write(p, json.dumps(data, ensure_ascii=False))
                return orig_load(user, url, title)

            jd_store.load = concurrent
            try:
                with self.assertRaises(_cli.StaleWrite):
                    jd_store.merge_into_seen("u", apply=True)
                self.assertEqual(
                    json.loads(p.read_text(encoding="utf-8"))["seen"][key]["status"],
                    "skipped", "jd_store --merge 把中间用户那一下抹掉了")
            finally:
                jd_store.load = orig_load
                jd_store.ROOT = old_root

    def test_archive_overlay_merges_a_concurrent_write(self):
        """热库与存档写完以后，叠加层要按「删哪几个键」合并，不是整份盖回去。

        原来的写法拿扫描时那份 `ustate` + 旧戳写回：撞上就整条失败，而热库
        与存档**已经写完了** —— 用户看到的却是「一个字没动」。
        """
        import archive
        import datetime as _dt

        with self._tmp_repo() as root:
            import _cli
            p, key_b = self._job(root, "https://x/b", "归档岗",
                                 status="expired", date="2020-01-01")
            data = json.loads(p.read_text(encoding="utf-8"))
            keep = _cli.stable_id("https://x/a", "留着的岗")
            data["seen"][keep] = {
                "url": "https://x/a", "title": "留着的岗", "status": "ranked",
                "rank_score": 70, "rank_verdict": "值得投"}
            _cli.atomic_write(p, json.dumps(data, ensure_ascii=False))
            _cli.set_user_decision(p, key_b, "expired", date="2020-01-01")
            us = _cli.user_state_path(p)
            old_root = archive.ROOT
            archive.ROOT = root
            orig = archive.collect_material_urls

            def concurrent(user):
                st = json.loads(us.read_text(encoding="utf-8"))
                st[keep] = {"decision": "skipped", "date": "2026-10-24"}
                _cli.atomic_write(us, json.dumps(st, ensure_ascii=False))
                return set()

            archive.collect_material_urls = concurrent
            try:
                r = archive.run("u", True, _dt.date(2026, 10, 24))
                self.assertFalse(r.get("overlay_stale"), r)
                st = json.loads(us.read_text(encoding="utf-8"))
                self.assertIn(keep, st, "归档把并发写入的叠加层决定抹掉了")
                self.assertNotIn(key_b, st, "已归档的岗还留在叠加层里")
            finally:
                archive.collect_material_urls = orig
                archive.ROOT = old_root

    def test_score_apply_refuses_a_stale_write(self):
        import score

        with self._tmp_repo() as root:
            import _cli
            p, key = self._job(root, "https://x/score", "评分岗")
            data = json.loads(p.read_text(encoding="utf-8"))
            dims = {"技能与经验": 60, "薪资与职级": 60,
                    "强度与公司性质": 60, "发展与风险": 60}
            data["seen"][key]["rank_breakdown"] = dict(dims, 依据="原依据")
            _cli.atomic_write(p, json.dumps(data, ensure_ascii=False))
            rows = [{"key": key, "dims": {**dims, "技能与经验": 61},
                     "score": 61, "verdict": "值得投",
                     "old": (dims, 60, "可以考虑"), "doc": None,
                     "text": None, "entry": data["seen"][key]}]
            old_root = score.ROOT
            score.ROOT = root
            orig = score.scoring.rewrite_pay_said

            def concurrent(basis, pay):
                data = json.loads(p.read_text(encoding="utf-8"))
                data["seen"][key]["status"] = "skipped"
                _cli.atomic_write(p, json.dumps(data, ensure_ascii=False))
                return orig(basis, pay)

            score.scoring.rewrite_pay_said = concurrent
            try:
                with self.assertRaises(_cli.StaleWrite):
                    score.apply("u", rows, "2026-10-24")
                self.assertEqual(
                    json.loads(p.read_text(encoding="utf-8"))["seen"][key]["status"],
                    "skipped", "score.py --apply 把中间用户那一下抹掉了")
            finally:
                score.scoring.rewrite_pay_said = orig
                score.ROOT = old_root

    @staticmethod
    def _tmp_repo():
        import tempfile

        class _T:
            def __enter__(self):
                self._t = tempfile.TemporaryDirectory()
                self.root = Path(self._t.name)
                (self.root / "users" / "u" / "job_scraper").mkdir(parents=True)
                return self.root

            def __exit__(self, *a):
                self._t.cleanup()

        return _T()

    @staticmethod
    def _job(root, url, title, *, status="ranked", date="2026-01-01"):
        p = root / "users" / "u" / "job_scraper" / "seen_jobs.json"
        key = _cli.stable_id(url, title)
        entry = {"url": url, "title": title, "company": "某公司",
                 "status": status, "rank_score": 60,
                 "rank_verdict": "可以考虑"}
        if status == "expired":
            entry["expired_date"] = date
        p.write_text(json.dumps({"seen": {key: entry}}, ensure_ascii=False),
                     encoding="utf-8")
        return p, key


class ThePortalBudgetIsAlsoAStore(unittest.TestCase):
    """风控额度也会被两个进程同时读写，写回要能发现别人先改了。"""

    def test_a_stale_budget_write_is_refused(self):
        import tempfile
        import portal_budget as pb

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "users" / "u" / "job_scraper").mkdir(parents=True)
            old = pb.ROOT
            pb.ROOT = root
            try:
                pb.save("u", {"猎聘": {"actions": []}})
                mine, stamp = pb.load_stamped("u")
                other = {"猎聘": {"actions": [], "blocks": {}}}
                pb.save("u", other)
                with self.assertRaises(_cli.StaleWrite):
                    pb.save("u", mine, expect=stamp)
                self.assertEqual(
                    json.loads((root / "users" / "u" / "job_scraper"
                                / "portal_budget.json").read_text(encoding="utf-8")),
                    other, "额度文件的并发写被静默覆盖了")
            finally:
                pb.ROOT = old


class UserDecisionsLiveOutsideTheJobStore(unittest.TestCase):
    """用户自己下的决定不写职位库——这是根治，`StaleWrite` 只是保险。

    `seen_jobs.json` 里原本塞着三种写入模式完全不同的东西：抓来的事实（只增）、
    判断（批量整份重写）、用户决定（一次一条）。于是「读一次库 → 评十几分钟 →
    整份写回」会把中间用户点的那一下抹掉。

    拆开之后两边根本不写同一个文件，冲突从根上没有了；顺带面板那一下的写入量
    从 3.4 MB 降到几十 KB。

    ⚠️ **叠加层的路径必须跟着职位库走，不能从「仓库根 + 用户名」推。**
    第一版那么写，测试把库指到临时目录后，叠加层仍落在真实仓库里——
    实测在 `users/张三/`、`users/谁/` 下写出了真文件。测试污染真实数据不报错，
    只是悄悄多出几个文件，是最难查的一类。
    """

    def test_the_overlay_sits_next_to_the_store(self):
        import _cli
        p = Path("/tmp/whatever/job_scraper/seen_jobs.json")
        self.assertEqual(_cli.user_state_path(p).parent, p.parent,
                         "叠加层没跟着职位库走——换个 ROOT 就会写错地方")
        self.assertEqual(_cli.user_state_path(p).name, "user_state.json")

    def test_skipping_does_not_touch_the_store(self):
        """点一下「不投」，职位库必须**一个字节都不动**。"""
        import hashlib
        import json as _json
        import shutil
        import sys as _sys
        import tempfile
        _sys.path.insert(0, str(ROOT / "tools"))
        import serve as srv
        import export_web_data as ex
        d = Path(tempfile.mkdtemp())
        sj = d / "users" / "u" / "job_scraper" / "seen_jobs.json"
        sj.parent.mkdir(parents=True)
        url, title = "https://x/1", "岗A"
        sj.write_text(_json.dumps({"seen": {f"{url}#{title}": {
            "url": url, "title": title, "company": "C", "status": "ranked",
            "rank_score": 70, "rank_verdict": "值得投"}}}, ensure_ascii=False),
            encoding="utf-8")
        saved = (srv.active_user, srv.seen_path)
        srv.active_user, srv.seen_path = (lambda: "u"), (lambda user: sj)
        try:
            before = hashlib.md5(sj.read_bytes()).hexdigest()
            r = srv.apply_skip(ex.stable_id(url, title), "不合适")
            self.assertTrue(r.get("ok"), r)
            self.assertEqual(hashlib.md5(sj.read_bytes()).hexdigest(), before,
                             "点「不投」动了职位库——长跑的 /job-rank 会把它盖掉")
            import _cli
            st = _cli.load_user_state(sj)
            self.assertEqual(st[f"{url}#{title}"]["decision"], "skipped")
        finally:
            srv.active_user, srv.seen_path = saved
            shutil.rmtree(d, ignore_errors=True)

    def test_consumers_go_through_decided_status(self):
        """各处自己拼 `overlay.get(...)` 迟早漏一处，表现是「页面标了不投、命令行还在评」。"""
        for f in ("export_web_data.py", "prescreen.py"):
            src = (ROOT / "tools" / f).read_text(encoding="utf-8")
            self.assertIn("load_user_state", src, f"{f} 没读叠加层")
            self.assertIn("decided_status", src, f"{f} 没走统一的状态判定")


class TheEnvProbeIsCachedOnDisk(unittest.TestCase):
    """工具链探测每次导出跑一遍是纯浪费，而缓存必须落在**磁盘**上。

    2026-08-19 profile：一次导出 1.9 秒，其中 **0.47 秒（21%）** 是
    `node --version`、`typst --version` 这四个子进程。面板每写一次就重导一次，
    点十下就跑十遍——而工具链是「几个月装一次」的东西。

    ## 为什么不是进程内缓存

    第一版就是进程内的，**一点用都没有**：`serve.py` 起**子进程**跑导出
    （那是被「服务器用启动那一刻的旧代码、把新格式覆盖回旧格式」咬过两次之后
    定下的设计），每次都是全新解释器。

    差点因此把导出搬回同进程——那等于把那个静默毁数据的 bug 请回来。
    **缓存要迁就架构，不是反过来。**
    """

    def test_the_cache_is_a_file_not_process_state(self):
        import export_web_data as ex
        self.assertTrue(hasattr(ex, "_env_cache_file"), "没有磁盘缓存")
        f = ex._env_cache_file()
        self.assertNotIn(str(ROOT), str(f),
                         "缓存落在了仓库里——它是派生数据，而且 web/public 是静态服务的根")

    def test_a_second_probe_does_not_respawn_subprocesses(self):
        import export_web_data as ex
        ex._probe_env_safe(force=True)            # 建缓存
        import doctor
        calls = []
        orig = doctor.probe_env
        doctor.probe_env = lambda *a, **k: (calls.append(1), orig(*a, **k))[1]
        try:
            ex._probe_env_safe()
            self.assertEqual(calls, [], "缓存没命中——又去起了四个子进程")
        finally:
            doctor.probe_env = orig

    def test_force_still_reprobes(self):
        """`doctor.py` 那种「就是要看当前真实状态」的调用方要有一条路。"""
        import export_web_data as ex
        import inspect
        self.assertIn("force", inspect.signature(ex._probe_env_safe).parameters)


def none_overlay_calls(source: str) -> list[int]:
    """`decided_status(x, None)` —— 第二个参数硬写成字面 `None` 的行号。

    **判据只有一份**：下面那条扫全仓、`test_the_detector_can_fire` 喂已知的
    好坏例子，两条走的是这一个函数。各写一份的话，把扫描那份打瘫、自检那份
    照绿 —— 实测 2026-08-25 变异检验当场逮到（那时自检里另抄了一份）。
    """
    import ast
    out = []
    for n in ast.walk(ast.parse(source)):
        if not (isinstance(n, ast.Call) and len(n.args) >= 2):
            continue
        name = (n.func.attr if isinstance(n.func, ast.Attribute)
                else getattr(n.func, "id", ""))
        if name != "decided_status":
            continue
        if isinstance(n.args[1], ast.Constant) and n.args[1].value is None:
            out.append(n.lineno)
    return out


def prod_sources(root) -> list:
    """算「生产消费者」的文件。**`tests/` 不在里面** —— 只有测试在调，
    正是死代码的样子（`fold_user_state` 当时就只有一条测试在调）。"""
    return list((root / "tools").glob("*.py")) + list((root / ".agents").rglob("*.py"))


def judges_without_a_consumer(cli_src: str, prod_blob: str) -> list[str]:
    """`_cli` 里公开、而 `prod_blob` 里一次都没被调到的函数名。"""
    import ast
    import re as _re
    fns = [n.name for n in ast.parse(cli_src).body
           if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")]
    return [f for f in fns
            if not _re.search(rf"(?<!def )\b{_re.escape(f)}\s*\(", prod_blob)]


class EveryReaderSeesTheOverlay(unittest.TestCase):
    """叠加层拆出去之后，**每个读状态的地方**都要看得见它。

    这不是一次性迁移，是个会反复漏的形状：prescreen 漏过一次（页面标了不投、
    命令行照评）、doctor 又漏一次（自检报的数和面板对不上）、**fetch_details
    漏到 2026-08-25**（补 JD 时照抓他已经否掉的岗，烧的是猎聘那几秒一次的抓取节奏）。

    统一的写法是 `_cli.decided_status(entry, overlay_row)` —— 不改条目、
    每次显式取一次。这个类盯三件事：谁没走它、谁走了却把第二个参数传成 `None`、
    以及那份没人用的「正本」不许再长出来。
    """

    def test_no_reader_passes_none_as_the_overlay(self):
        """`decided_status(e, None)` 比直接读 `e["status"]` 更坏。

        它长得像已经查过叠加层了 —— 读代码的人不会再查一遍，而它每一次都
        取不到用户的决定。实测 2026-08-25 `fetch_details.missing_by_portal`
        就是这么写的：报告说 1120 个岗还活着，真数 1118。

        只抓**字面 `None`**，不抓变量：`decided_status(e, st.get(k))` 在
        取不到时同样是 None，那是正常的（这个岗没有决定），
        `fetch_details` 里那种硬写死才是。
        """
        bad = [f"{f.name}:{ln}"
               for f in sorted((ROOT / "tools").glob("*.py"))
               for ln in none_overlay_calls(f.read_text(encoding="utf-8"))]
        self.assertEqual(
            bad, [],
            "这几处把叠加层参数硬传成 None —— 看着守过规矩，实际永远查不到"
            "用户在总览页点的「不投 / 已下线」：\n  " + "\n  ".join(bad))

    def test_the_detector_can_fire(self):
        """对照用例：坏写法真的抓得出来，好写法不许误报。"""
        self.assertTrue(none_overlay_calls("_cli.decided_status(e, None)"))
        self.assertEqual(none_overlay_calls("_cli.decided_status(e, st.get(k))"), [],
                         "取不到时返回 None 是正常的（这个岗没有决定），不许误报")
        self.assertEqual(none_overlay_calls("other_fn(e, None)"), [],
                         "别的函数传 None 不归这条管")

    def test_every_public_judge_in_cli_has_a_consumer(self):
        """`_cli` 里的公开函数必须真有人调 —— **没有消费者的「正本」比没有更坏**。

        实测 2026-08-25：`fold_user_state` 零生产调用方，而 `doctor.py` 两处
        注释奉它为正本、写着「改折叠语义时两处一起改」。两边早就各折各的
        （它折 reason/date，doctor 那份折 hr_viewed），而真正漏着叠加层的
        `fetch_details` 没人去查 —— 因为看上去这件事已经统一了。已删。

        算「消费者」的是 `tools/` 与 `.agents/` 里的调用（含 `_cli` 内部互调：
        `addressee_said` 只被同文件的 `addressee_problem` 调，那也是真在跑）。
        测试里的调用**不算** —— 只有测试在调，正是死代码的样子。
        """
        prod = prod_sources(ROOT)
        dead = judges_without_a_consumer(
            (ROOT / "tools" / "_cli.py").read_text(encoding="utf-8"),
            "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in prod))
        self.assertEqual(
            dead, [],
            "这几个判据没有任何生产调用方 —— 要么接上消费方，要么删掉，"
            "别留一份没人跑的「正本」让人以为已经统一了：" + "、".join(dead))

    def test_the_dead_judge_detector_can_fire(self):
        """对照用例：只在测试里被调的函数**必须**报出来。

        这正是 `fold_user_state` 当时的样子 —— 定义在 `_cli`、只有一条测试在
        调、两处注释奉它为正本。把 `tests/` 算进消费者就再也认不出它了。
        """
        cli = "def only_in_tests(x):\n    return x\n\ndef used(x):\n    return x\n"
        self.assertEqual(judges_without_a_consumer(cli, "used(1)"), ["only_in_tests"])
        self.assertEqual(judges_without_a_consumer(cli, "used(1); only_in_tests(2)"), [])
        self.assertEqual(judges_without_a_consumer(cli, "def only_in_tests(x): pass"),
                         ["only_in_tests", "used"],
                         "定义行不算调用 —— 否则每个函数都自证有消费者")

    def test_tests_do_not_count_as_consumers(self):
        """清单本身也要断一句：混进 `tests/` 就再也认不出死判据了。

        判据函数有正反例护着（上一条），可**喂给它哪些文件**没有 —— 当下一个
        死函数都没有时，清单里放什么都返回空，改了也不红。
        """
        bad = [str(p) for p in prod_sources(ROOT) if "tests" in p.parts]
        self.assertEqual(bad, [], "把测试算成了消费者：" + "、".join(bad))
        self.assertTrue(any(p.name == "export_web_data.py" for p in prod_sources(ROOT)),
                        "连 tools/ 都没扫到 —— 那这条恒绿")

    def test_that_scan_reaches_the_sources(self):
        """对照用例：真的读到文件了 —— 否则上面两条恒绿。"""
        n = len(list((ROOT / "tools").glob("*.py")))
        self.assertGreaterEqual(n, 15, f"只扫到 {n} 个 tools 模块 —— 判据够不到文件了")

    def test_doctor_folds_before_counting(self):
        """doctor 不许 import 仓库模块（硬契约），所以整批折——盯行为不盯函数名。

        断的是**那句调用**，不是文件里出现过 `user_state.json` 这几个字：
        第一版只断了字符串在不在，而它上面那段注释里正好也写着这个文件名 ——
        把真正的读改成读别的文件，测试照绿（2026-08-25 变异检验逮到）。
        """
        src = (ROOT / "tools" / "doctor.py").read_text(encoding="utf-8")
        self.assertIn('with_name("user_state.json")', src,
                      "doctor 数的是裸 status——自检报的数会和面板对不上")
        self.assertIn("_cli.decided_status", src,
                      "整批折那处要注明语义正本是 _cli.decided_status——"
                      "不然改语义时必漏一边")

    def test_serve_watches_the_new_write_targets(self):
        """按钮现在写 user_state/portals/prefs——「data.json 旧没旧」的判断
        必须盯着它们，否则某次写后重导失败，陈旧页会永远端下去。"""
        src = (ROOT / "tools" / "serve.py").read_text(encoding="utf-8")
        i = src.index("def sources_mtime")
        body = src[i:i + 1600]
        for f in ("user_state.json", "portals.json", "prefs.json"):
            self.assertIn(f, body, f"sources_mtime 没盯 {f}")
