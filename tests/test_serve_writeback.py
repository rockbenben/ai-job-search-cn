"""本地服务的写回：定位要准、只改该改的、拒绝该拒的。

## 为什么每条都值得钉住

**定位**——`seen_jobs` 的键是 `<url>#<职位名>` 形式的去重键，而 51job 实测**同一个
URL 下挂着两个不同职位**。按 URL 匹配会同时命中两条，改错一条还不报错。所以服务端
按 `stable_id(url, title)` 反查——和导出给页面的 `id` 是同一个函数算的。

**字段**——`/job-rank --skip` 明确规定只改 `status` / `skip_date` / `skip_reason`，
不动 `rank_score` / `rank_verdict` / `first_seen`：分数是评估结果，不因为你不投而失效，
下次回看当初为什么排除，那些还得在。

**拒绝**——没有 token，你在浏览器里打开的**任何**网站都能往 `localhost:29029` 发 POST
把职位标成不投。跨站 POST 是允许的，只是读不到响应——而这里的破坏不需要读响应。
"""

import json
import sys
import tempfile
import threading
import types
import pathlib
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import serve as srv  # noqa: E402


def _fixture(tmp: Path) -> Path:
    """造一份带 51job 陷阱的 seen_jobs：两个不同职位挂在同一个 URL 上。"""
    u = tmp / "users" / "张三"
    (u / "job_scraper").mkdir(parents=True)
    (tmp / ".active_user").write_text("张三", encoding="utf-8")
    same_url = "https://jobs.51job.com/all/12345.html"
    seen = {
        "seen": {
            f"{same_url}#甲岗": {
                "title": "甲岗", "company": "某公司", "url": same_url,
                "first_seen": "2026-07-01", "status": "ranked",
                "rank_score": 71, "rank_verdict": "粗筛：值得投",
            },
            f"{same_url}#乙岗": {
                "title": "乙岗", "company": "某公司", "url": same_url,
                "first_seen": "2026-07-01", "status": "ranked",
                "rank_score": 44, "rank_verdict": "粗筛：不建议",
            },
            "https://x/9#丙岗": {
                "title": "丙岗", "company": "另一家", "url": "https://x/9",
                "first_seen": "2026-07-02", "status": "new",
            },
        }
    }
    (u / "job_scraper" / "seen_jobs.json").write_text(
        json.dumps(seen, ensure_ascii=False), encoding="utf-8")
    return u / "job_scraper" / "seen_jobs.json"


class _Temp:
    """把 serve 的 ROOT 指到临时目录，用完还原。"""

    def __enter__(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = Path(self._t.name)
        self.sj = _fixture(self.tmp)
        self._saved = srv.ROOT
        srv.ROOT = self.tmp
        return self

    def __exit__(self, *a):
        srv.ROOT = self._saved
        self._t.cleanup()

    def entry(self, title: str) -> dict:
        seen = json.loads(self.sj.read_text(encoding="utf-8-sig"))["seen"]
        return next(v for v in seen.values() if v["title"] == title)

    def state(self, title: str) -> str:
        """这个岗**实际**是什么状态。

        2026-08-19 之后「不投 / 已下线」不在职位库里，在叠加层
        （`job_scraper/user_state.json`）。测试要断言的是**用户看到的状态**，
        不是它存在哪个文件里——存哪儿是实现，状态才是契约。
        """
        seen = json.loads(self.sj.read_text(encoding="utf-8-sig"))["seen"]
        key = next(k for k, v in seen.items() if v["title"] == title)
        st = srv._cli.load_user_state(self.sj)
        return srv._cli.decided_status(seen[key], st.get(key))

    def decision(self, title: str) -> dict:
        seen = json.loads(self.sj.read_text(encoding="utf-8-sig"))["seen"]
        key = next(k for k, v in seen.items() if v["title"] == title)
        return srv._cli.load_user_state(self.sj).get(key, {})


def sid(url: str, title: str) -> str:
    return srv.ex.stable_id(url, title)


class LocatesTheRightJob(unittest.TestCase):
    def test_same_url_two_jobs_are_told_apart(self):
        """51job 陷阱：URL 相同、职位名不同，必须各归各的。

        ⚠️ **这里排除的是「乙岗」——同一 URL 下的第二条，不能改成第一条。**
        按 URL 匹配的缺陷实现会返回「同 URL 的第一条」，如果测试排除的正好是第一条，
        缺陷版也会蒙对，这条测试就永远不会红。实测验证过：改成排除甲岗时，
        把定位换成按 URL 匹配，这条照样绿。**测第二条才是真的在测。**
        """
        with _Temp() as t:
            url = "https://jobs.51job.com/all/12345.html"
            srv.apply_skip(sid(url, "乙岗"), "只排除乙")
            self.assertEqual(t.state("乙岗"), "skipped")
            self.assertEqual(t.state("甲岗"), "ranked",
                             "同一 URL 下的另一个职位被误伤了 —— 定位退化成按 URL 匹配")

    def test_unknown_id_reports_instead_of_silently_doing_nothing(self):
        with _Temp():
            r = srv.apply_skip("jdeadbeef00", "")
            self.assertFalse(r["ok"])
            self.assertIn("找不到", r["error"])


class SurvivesAnExcelStore(unittest.TestCase):
    """中文 Windows 上 Excel 存出来的两种文件，不能把写操作变成 500。"""

    def test_a_bom_store_can_be_written(self):
        """职位库带 BOM 时，定位/写回仍要工作。"""
        with _Temp() as t:
            t.sj.write_bytes(b"\xef\xbb\xbf" + t.sj.read_bytes())
            r = srv.apply_skip(sid("https://jobs.51job.com/all/12345.html", "甲岗"),
                               "测试")
            self.assertTrue(r["ok"], r)
            self.assertEqual(t.state("甲岗"), "skipped")

    def test_a_gbk_tracker_is_reported_not_raised(self):
        """台账是 GBK 时不能抛 UnicodeDecodeError，也不能静默新建一行。"""
        with _Temp() as t:
            (t.tmp / "users" / "张三" / "job_search_tracker.csv").write_bytes(
                ("date,company,role,status,source,notes\n"
                 "2026-08-01,某公司,甲岗,applied,https://jobs.51job.com/all/12345.html,\n"
                 ).encode("gbk"))
            r = srv.apply_status(
                sid("https://jobs.51job.com/all/12345.html", "甲岗"), "applied")
            self.assertFalse(r["ok"], "GBK 台账上接口报成功了")
            self.assertEqual(r.get("code"), "tracker_unreadable",
                             "没有 code —— 页面会把编码问题当成「这个岗没了」")
            self.assertIn("UTF-8", r["error"])
            self.assertIn("另存为", r["error"], "没说怎么修")

    def test_a_bom_store_can_be_rewritten(self):
        """BOM 不只影响读：放回会整份重写职位库。"""
        with _Temp() as t:
            t.sj.write_bytes(bytes([0xEF, 0xBB, 0xBF]) + t.sj.read_bytes())
            url = "https://jobs.51job.com/all/12345.html"
            srv.apply_skip(sid(url, "甲岗"), "")
            srv.apply_restore(sid(url, "甲岗"))
            self.assertEqual(t.state("甲岗"), "ranked")

    def test_a_missing_store_says_scrape_not_encoding(self):
        """没有职位库不是「文件坏了」——把人指去另存 UTF-8 是修一份不存在的文件。"""
        with _Temp() as t:
            t.sj.unlink()
            with self.assertRaises(srv.StoreUnreadable) as cm:
                srv.apply_status(sid("https://x/9", "丙岗"), "applied")
            msg = str(cm.exception)
            self.assertIn("还没抓过职位", msg)
            self.assertIn("/job-scrape", msg)
            self.assertNotIn("另存为", msg)


class TheWriteOriginIsExact(unittest.TestCase):
    """同源 = scheme + host + port；只比端口不够。"""

    def _req(self, origin: str, port: int = 29029):
        class R:
            pass
        r = R()
        r.headers = {"Origin": origin}
        r.server = types.SimpleNamespace(server_address=("127.0.0.1", port))
        return r

    def test_an_https_origin_is_not_http(self):
        self.assertFalse(srv.Handler._same_origin(
            self._req("https://127.0.0.1:29029")))

    def test_the_real_http_origin_passes(self):
        self.assertTrue(srv.Handler._same_origin(
            self._req("http://127.0.0.1:29029")))
        self.assertTrue(srv.Handler._same_origin(
            self._req("http://localhost:29029")))

    def test_another_port_is_not_the_same_origin(self):
        self.assertFalse(srv.Handler._same_origin(
            self._req("http://127.0.0.1:29030")))


class TouchesOnlyTheSkipFields(unittest.TestCase):
    def test_score_and_first_seen_survive(self):
        with _Temp() as t:
            url = "https://jobs.51job.com/all/12345.html"
            srv.apply_skip(sid(url, "甲岗"), "方向不对")
            e = t.entry("甲岗")
            self.assertEqual(e["rank_score"], 71, "分数被动了")
            self.assertEqual(e["rank_verdict"], "粗筛：值得投")
            self.assertEqual(e["first_seen"], "2026-07-01")

    def test_reason_defaults_but_is_never_empty(self):
        with _Temp() as t:
            url = "https://jobs.51job.com/all/12345.html"
            srv.apply_skip(sid(url, "甲岗"), "")
            self.assertEqual(t.decision("甲岗")["reason"], "用户手动排除")

    def test_restore_goes_back_to_ranked_when_it_has_a_score(self):
        """打过分的别退成 new —— 那会让它下次被当成没评过重跑一遍。"""
        with _Temp() as t:
            url = "https://jobs.51job.com/all/12345.html"
            srv.apply_skip(sid(url, "甲岗"), "")
            srv.apply_restore(sid(url, "甲岗"))
            e = t.entry("甲岗")
            self.assertEqual(e["status"], "ranked")
            self.assertNotIn("skip_date", e)
            self.assertNotIn("skip_reason", e)

    def test_restore_goes_back_to_new_when_it_was_never_scored(self):
        with _Temp() as t:
            srv.apply_skip(sid("https://x/9", "丙岗"), "")
            srv.apply_restore(sid("https://x/9", "丙岗"))
            self.assertEqual(t.entry("丙岗")["status"], "new")

    def test_restore_refuses_a_stale_store(self):
        """放回也要带版本戳；读之后被别处改了，不能整份盖回去。"""
        with _Temp() as t:
            url = "https://jobs.51job.com/all/12345.html"
            job_id = sid(url, "甲岗")
            orig = srv._cli.set_user_decision

            def concurrent(seen_file, key, decision, **extra):
                data = json.loads(t.sj.read_text(encoding="utf-8"))
                data["seen"][f"{url}#甲岗"]["status"] = "expired"
                t.sj.write_text(json.dumps(data, ensure_ascii=False),
                                encoding="utf-8")
                return orig(seen_file, key, decision, **extra)

            srv._cli.set_user_decision = concurrent
            try:
                with self.assertRaises(srv._cli.StaleWrite):
                    srv.apply_restore(job_id)
            finally:
                srv._cli.set_user_decision = orig

    def test_restore_clears_a_legacy_status_even_with_an_overlay_decision(self):
        """旧库里的 status 与叠加层同时标了出局时，放回必须两边都撤。

        原来这一支在「叠加层里有一条决定」时提前返回，只删叠加层；库里那份
        旧 `status=expired` 原样留着，于是接口报成功、岗还是出局。
        2026-10-24 活动用户的数据里就有 1 条这样的岗。
        """
        with _Temp() as t:
            url = "https://jobs.51job.com/all/12345.html"
            job_id = sid(url, "甲岗")
            data = json.loads(t.sj.read_text(encoding="utf-8"))
            data["seen"][f"{url}#甲岗"]["status"] = "expired"
            t.sj.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            srv._cli.set_user_decision(t.sj, f"{url}#甲岗", "expired",
                                       date="2026-10-01")
            r = srv.apply_restore(job_id)
            self.assertTrue(r["ok"], r)
            self.assertEqual(t.state("甲岗"), "ranked",
                             "放回说成功，旧 status 却还把它留在出局区")
            self.assertEqual(t.decision("甲岗"), {},
                             "叠加层里的决定没撤")


class RejectsWritesWithoutTheToken(unittest.TestCase):
    """起一个真服务，验证两道锁都拦得住。"""

    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
        cls.port = cls.srv.server_address[1]
        cls.th = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.th.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def _post(self, payload, origin=None):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/skip",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        if origin:
            req.add_header("Origin", origin)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_no_token_is_rejected(self):
        code, body = self._post({"id": "jwhatever00"})
        self.assertEqual(code, 403, f"没有 token 也放行了：{body}")

    def test_wrong_token_is_rejected(self):
        code, _ = self._post({"id": "jwhatever00", "token": "not-the-token"})
        self.assertEqual(code, 403)

    def test_foreign_origin_is_rejected_even_with_a_token(self):
        """两道锁是冗余的，故意的。"""
        code, _ = self._post({"id": "jwhatever00", "token": srv.TOKEN},
                             origin="https://evil.example")
        self.assertEqual(code, 403)

    def test_the_rejection_arrives_as_a_response_not_a_reset(self):
        """**拒绝要以 403 的形式送达，不能以连接重置的形式。**

        原来 `do_POST` 的 Origin 校验排在读 body 之前：不合格就直接 403 并关连接，
        而客户端可能还在写 body → TCP RST → 客户端拿到的是
        `ConnectionResetError`，不是那句「这个请求不是本页发出的」。

        这条 bug 的指纹是**间歇性**：能不能在关连接前把 body 发完取决于调度。
        实测全量跑 2/7 红、单跑必绿，而同一个类里另外两条拒绝（无 token / 错 token）
        从不抖——因为它们本来就发生在读完 body 之后。

        所以这里发一个**大到必然分片**的 body：真要是又把检查提到读 body 之前，
        重置的概率会被这个尺寸顶到接近必然，抖不起来。
        """
        big = {"id": "jwhatever00", "token": srv.TOKEN, "pad": "x" * 300_000}
        for i in range(5):
            with self.subTest(attempt=i):
                code, body = self._post(big, origin="https://evil.example")
                self.assertEqual(
                    code, 403,
                    "跨站 POST 被拒时没拿到 403 —— 检查是不是又排到读 body 之前了")
                self.assertIn("安全限制", str(body),
                              "403 里没有给用户看的说明")

    def test_localhost_origin_passes_the_origin_check(self):
        """同源要放行——否则页面自己也用不了。这里只验证没被 Origin 挡下。"""
        code, body = self._post({"id": "jdefinitely-not-there", "token": srv.TOKEN},
                                origin=f"http://127.0.0.1:{self.port}")
        self.assertNotEqual(code, 403, f"同源请求被误拦：{body}")

    def test_another_local_port_is_not_the_same_origin(self):
        """Origin 是 scheme + host + port；只比 host 会让另一个本地服务混进来。"""
        code, _ = self._post(
            {"id": "jdefinitely-not-there", "token": srv.TOKEN},
            origin=f"http://127.0.0.1:{self.port + 1}")
        self.assertEqual(code, 403, "不同端口的 Origin 被当成了同源")

    def test_no_active_user_answers_instead_of_dropping_the_connection(self):
        """这台机器上还没有资料时，点按钮要收到一句话，不是「网络错误」。

        ## 这一半漏了很久，因为维护者的机器上永远有资料

        `active_user()` 原来抛 `SystemExit`——它继承 `BaseException`，
        `do_POST` 那句 `except Exception` **接不住**：异常穿出去、处理线程死掉、
        连接不带响应就关了。客户端拿到的是 `RemoteDisconnected`。

        读那一侧（`refresh_if_stale`）早就撞过并就地补了 `except SystemExit`，
        注释还写着「别让请求崩掉」；**写这一侧一直没补**。两侧各修一半、
        谁也不知道另一半漏着，正是 `test_one_file_one_tolerance.py` 盯的形状。

        2026-08-20 才露出来，而且不是在这台机器上：把「会进提交的那批文件」
        拷进一个空目录（不带 `users/`、不带 `.active_user`）跑测试——也就是
        **首次 CI 和每一个 contributor 看到的样子**——`/api/skip` 当场断连接。

        ## 判据

        不打桩 `apply_skip`，打桩 `active_user`：漏的就是「它抛出来之后没人接」
        这一环，桩要下在那一环上。三件事一起验——**有响应**（不是断连接）、
        **不是 5xx**（这不是服务出错，是这台机器还没建档）、
        **话里说了下一步**（`tests/test_error_messages.py` 的规矩）。
        """
        real = srv.active_user
        srv.active_user = lambda: (_ for _ in ()).throw(
            srv.NoActiveUser("还没有你的资料 —— 先跑 /job-setup 建档"))
        try:
            code, body = self._post({"id": "jnope", "token": srv.TOKEN})
        finally:
            srv.active_user = real
        self.assertLess(code, 500,
                        f"没有活动用户被当成服务故障报了 {code}：{body}")
        msg = str(body.get("error") or "")
        self.assertIn("/job-setup", msg,
                      f"没告诉用户下一步该敲什么：{msg!r}")
        for dev in ("SystemExit", "NoActiveUser", "Traceback"):
            self.assertNotIn(dev, msg, f"把开发词印给用户了：{msg!r}")


class NoJobsYetIsNotAFailure(unittest.TestCase):
    """刚建完档、还没抓过岗时打开总览页 —— 那是流程的下一步，不是故障。

    ## 撞到它的是「最常见的一条路」

    `AGENTS.md` 让助手在用户想看总览时**自己去起** `serve.py`。而新用户跑完
    `/job-setup` 的下一件事往往就是想看看长什么样。此前这条路上没有前置检查，
    于是一路走到「自动导出失败」那个分支，端给用户的是：

        ⚠ 自动导出失败，页面显示的是旧数据：RuntimeError: 导出器退出码 1：…
        web/public/data.json 生成失败 —— 手动跑一次 python tools/export_web_data.py 看它报什么错

    三处都不对：**没有页面**（进程退出了），谈不上「显示的是旧数据」；
    那个错**就印在上一行**，让人再跑一遍等于重做刚看过的事；而
    `RuntimeError` / `退出码 1` 是开发词，`AGENTS.md`「给用户看的措辞」那节
    明令不许搬上台面。2026-08-20 在干净 clone 上实测到。

    ## 判据

    把 `web/dist` 与 `seen_path` 都打成桩（前者要存在、后者要不存在），
    验三件事：**非零退出**（别假装打开了）、**话里有 /job-scrape**（下一步）、
    **不含开发词**。
    """

    def test_it_names_the_next_command_instead_of_dumping_an_exception(self):
        import contextlib
        import io

        def _must_not_serve(*a, **k):
            # 把起服务这条路堵死。**第一版没堵，变异测试当场吃了亏**：
            # 停用前置检查之后 `main()` 一路走到 `serve_forever()`，测试不是变红
            # 而是**卡住**——挂起不是失败信号，没人会把它读成「守卫抓到了」。
            # 判据要能失败得又快又响。
            raise AssertionError("不该走到起服务这一步 —— 前置检查没拦住")

        # **`_Server`，不是 `ThreadingHTTPServer`。** 2026-08-24 起服务那行换成了
        # 子类（Windows 上不许 `SO_REUSEADDR`），这个陷阱当场变成空的 ——
        # 堵错了名字，`main()` 会一路走到 `serve_forever()` 把测试挂住。
        # `probe_running` 一并堵掉：它会去连本机 29029，那台机器上真有服务在跑时
        # `main()` 在前置检查之前就「已经在跑了」并 0 退出（实测吃过）。
        real = (srv.DIST, srv.seen_path, srv.active_user, srv.token_path,
                srv._Server, srv.probe_running)
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "index.html").write_text("<html></html>", encoding="utf-8")
            srv.DIST = d
            srv.seen_path = lambda user: d / "还没有这个文件.json"
            srv.active_user = lambda: "someone"
            # `main()` 现在会在钉住用户后重取 token；测试里不能让它写到
            # 真实 `users/someone/.api_token`（那是测试污染，不是用户）。
            srv.token_path = lambda user: d / ".api_token"
            srv._Server = _must_not_serve
            srv.probe_running = lambda *a, **k: None
            err = io.StringIO()
            try:
                with contextlib.redirect_stderr(err):
                    rc = srv.main([])
            finally:
                (srv.DIST, srv.seen_path, srv.active_user, srv.token_path,
                 srv._Server, srv.probe_running) = real
        msg = err.getvalue()
        self.assertEqual(rc, 1, f"没有职位数据却不是非零退出：{msg!r}")
        self.assertIn("/job-scrape", msg, f"没告诉用户下一步该敲什么：{msg!r}")
        for dev in ("RuntimeError", "Traceback", "退出码 1", "export_web_data.py"):
            self.assertNotIn(dev, msg, f"把开发词印给用户了：{msg!r}")


class TokenInjectionAnchorExists(unittest.TestCase):
    """注入锚点必须真的在构建产物里 —— 注不进去会**静默**退回静态模式。"""

    def test_built_index_has_a_head_tag(self):
        idx = ROOT / "web" / "dist" / "index.html"
        if not idx.is_file():
            self.skipTest("web/dist 还没构建")
        self.assertRegex(
            idx.read_text(encoding="utf-8"), r"<head[^>]*>",
            "构建产物里没有 <head>，token 注不进去，页面会以为没有服务")


class OneSentenceOneHome(unittest.TestCase):
    """「这个岗找不到了」这句话给用户看，所以只许有一份。

    实测 2026-08-30：`serve.py` 里逐字抄了 **6 遍** —— 六个端点各写各的。
    改一处就是制造分叉，而用户在同一个页面上会看到两种说法。
    同一趟还合掉了四个端点共用的那段五行开场（读活动用户、拼路径、载 JSON、
    `find_entry`、找不到就回那句话）：**抄四遍的代价不在行数**，
    在于其中任何一条改了读法，另外三条不会跟着改。
    """

    SRC = (pathlib.Path(__file__).resolve().parents[1]
           / "tools" / "serve.py").read_text(encoding="utf-8")
    MSG = "职位列表里找不到这个岗了"

    def test_the_message_has_one_home(self):
        n = self.SRC.count(self.MSG)
        self.assertEqual(n, 1, f"这句话在 serve.py 里出现了 {n} 次")

    def test_the_endpoints_go_through_it(self):
        self.assertGreaterEqual(self.SRC.count("return not_found()"), 6,
                                "有端点没走那一份，自己拼了一句")

    def test_the_lookup_has_one_home(self):
        self.assertGreaterEqual(self.SRC.count("_locate(job_id)"), 4,
                                "改字段的端点没走同一段查找")
        self.assertEqual(
            self.SRC.count("key, entry = find_entry(_cli.seen_of(data), job_id)"),
            1, "查找那几行又被抄了一份")


if __name__ == "__main__":
    unittest.main()
