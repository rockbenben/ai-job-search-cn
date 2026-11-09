# -*- coding: utf-8 -*-
"""「还在用旧代码跑」一直不消失，是因为重启杀掉的是**新起的那个**。

用户 2026-08-24：「为什么一直出现 这一页的服务还在用旧代码跑：…到启动它的
终端按 Ctrl+C，再跑一次 python tools/serve.py」。

那条提醒本身没错 —— 错的是它给的修法在 Windows 上会把事情做反。

## 根因：`SO_REUSEADDR` 在 Windows 上的意思是「抢占」

`ThreadingHTTPServer.allow_reuse_address` 是 stdlib 的默认 `True`。
POSIX 上它的意思是「TIME_WAIT 里的旧连接不挡新监听」—— Ctrl+C 之后能立刻
重起，是好事。**Windows 上完全是另一回事：第二个进程照样 bind 成功。**

实测 2026-08-24（端口上已有一个我们自己的服务在跑）：

    ThreadingHTTPServer(("127.0.0.1", 29029), BaseHTTPRequestHandler)
    → 不抛异常，绑上了

于是这条路走下来是：

1. 用户跑 `python tools/serve.py`，看到「求职总览：http://127.0.0.1:29029/」，
   浏览器自动打开 —— 一切看着都对；
2. 内核把连接给了**先起的那个**（旧代码），页面挂出「还在用旧代码跑」；
3. 用户照提示在这个终端按 Ctrl+C —— 杀掉的是**刚起的这个新的**；
4. 旧的还在。回到第 1 步。

**提醒说的修法，恰好是让它永远修不好的那一步。**

## 修法：起之前先探一次

`probe_running` 连一下端口，连得上就问 `/data.json` 它是谁：

- 不是我们的东西 → 说「换个端口」，别去停别人的进程；
- 是我们的、代码是新的 → 那就是用户想要的那一页，打开它，`0` 退出；
- 是我们的、但它是改代码之前起的 → **给停掉它的命令**，`1` 退出。

第三条是这一整条链子真正缺的那一环：用户手上未必还有那个终端
（后台起的、关掉的、别的会话起的），「去按 Ctrl+C」对他不成立。

顺带把 `allow_reuse_address` 在 Windows 上关掉 —— 探测和 bind 之间还有一段
时间差，两个同时起时它是最后一道。
"""
import io
import json
import os
import pathlib
import re
import socket
import sys
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import serve  # noqa: E402

SRC = (ROOT / "tools" / "serve.py").read_text(encoding="utf-8")
APP = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*#:?\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TheClosingRunsItUnconditionally(unittest.TestCase):
    """`/job-auto` 收尾要**无条件**跑一次 `serve.py`。

    `report_running` 分三种情况：没在跑 / 在跑且代码是新的 /
    **在跑、但它是改代码之前起的**。收尾原来写的是「面板没在跑就跑」——
    那句话只认前两种，第三种下它什么都不做。

    而这一轮凡是改过 `tools/` 的，服务就是旧的：页面上那条「这一页的服务还在" + NL
    用旧代码跑：现在点按钮记的状态可能不准」正是它，而收尾一个字没提。
    实测 2026-08-31：改了 `_cli.py` 与 `export_web_data.py` 之后打开面板，
    那条警告就挂在第三块上。
    """

    def test_the_closing_does_not_say_only_when_not_running(self):
        t = (ROOT / "workflows" / "job-auto.md").read_text(encoding="utf-8")
        self.assertNotIn("面板没在跑就 python tools/serve.py", t,
                         "收尾又写成「没在跑就起」—— 旧服务那一种它不管")

    def test_the_closing_names_the_third_state(self):
        t = (ROOT / "workflows" / "job-auto.md").read_text(encoding="utf-8")
        i = t.index("python tools/serve.py               #")
        seg = t[i:i + 900]
        self.assertIn("三种", seg, "没说清它自己分几种情况")
        self.assertIn("改代码之前起的", seg, "没点名第三种")
        self.assertIn("report_running", seg, "没指到判据在哪")


class Fake(BaseHTTPRequestHandler):
    """假总览：`/data.json` 端出 `BODY` 里那份。"""

    BODY = b"{}"

    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(self.BODY)

    def log_message(self, *a):
        pass


class Serving:
    """在一个真端口上起一个假服务，退出时收摊。"""

    def __init__(self, body: dict | None):
        self.body = body

    def __enter__(self):
        self.port = free_port()
        cls = type("H", (Fake,), {
            "BODY": json.dumps(self.body).encode("utf-8")
            if self.body is not None else b"not json at all"})
        self.srv = ThreadingHTTPServer(("127.0.0.1", self.port), cls)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *a):
        self.srv.shutdown()
        self.srv.server_close()


class TheProbeTellsWhoIsThere(unittest.TestCase):
    def test_a_free_port_is_none(self):
        self.assertIsNone(serve.probe_running(free_port(), timeout=0.5))

    def test_it_recognises_our_own_server(self):
        with Serving({"activeUser": "甲", "jobs": []}) as s:
            got = serve.probe_running(s.port, timeout=2)
        self.assertEqual(got, {"ours": True, "user": "甲", "stale": []})

    def test_it_carries_the_stale_list_through(self):
        """探测要报「那个在跑的是不是旧代码」—— 三条路里最要紧的一条靠它分。"""
        with Serving({"activeUser": "甲", "staleCode": ["_cli.py"]}) as s:
            got = serve.probe_running(s.port, timeout=2)
        self.assertEqual(got["stale"], ["_cli.py"])

    def test_someone_elses_server_is_not_ours(self):
        """认「是不是我们的」靠 `activeUser`。认错了会去教用户停别人的进程。"""
        with Serving({"hello": "world"}) as s:
            got = serve.probe_running(s.port, timeout=2)
        self.assertFalse(got["ours"])

    def test_a_non_json_reply_is_not_ours(self):
        with Serving(None) as s:
            got = serve.probe_running(s.port, timeout=2)
        self.assertFalse(got["ours"])


class TheThreeCasesSayThreeDifferentThings(unittest.TestCase):
    def _run(self, info):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = serve.report_running(info, 29029, "http://127.0.0.1:29029/")
        return code, out.getvalue(), err.getvalue()

    def test_someone_else_gets_a_port_suggestion(self):
        """停别人的进程没道理 —— 换端口才是这一格的答案。"""
        code, _out, err = self._run({"ours": False, "user": "", "stale": []})
        self.assertEqual(code, 1)
        self.assertIn("--port 29030", err)
        self.assertNotIn("taskkill", err)

    def test_a_fresh_one_is_just_opened(self):
        """它就是用户想要的那一页 —— 报错没有道理，再起一个更没有。"""
        code, out, err = self._run({"ours": True, "user": "甲", "stale": []})
        self.assertEqual(code, 0)
        self.assertIn("http://127.0.0.1:29029/", out)
        self.assertIn("不重复起", out)
        self.assertEqual(err, "")

    def test_a_stale_one_gets_the_command_to_stop_it(self):
        """**这条是整件事的落点。** 用户未必还有那个终端 ——
        「去按 Ctrl+C」对他不成立，得给命令。"""
        code, _out, err = self._run(
            {"ours": True, "user": "甲", "stale": ["_cli.py"]})
        self.assertEqual(code, 1)
        self.assertNotIn("Ctrl+C", err)
        self.assertRegex(err, r"taskkill|kill \$\(lsof")
        self.assertIn("29029", err)

    def test_the_stale_one_does_not_pretend_to_have_started(self):
        """印一句「求职总览：…」再退出，是这条链子上最坑的一步。"""
        _code, out, _err = self._run(
            {"ours": True, "user": "甲", "stale": ["_cli.py"]})
        self.assertNotIn("求职总览", out)

    def test_the_hint_matches_this_platform(self):
        got = serve._stop_hint(29029)
        if os.name == "nt":
            self.assertIn("taskkill", got)
            self.assertIn("netstat", got)
        else:
            self.assertIn("lsof", got)
        self.assertIn("29029", got)


class TheBindItselfIsGuarded(unittest.TestCase):
    def test_windows_does_not_reuse_the_address(self):
        """探测和 bind 之间有时间差 —— 两个同时起时这是最后一道。"""
        self.assertEqual(serve._Server.allow_reuse_address, os.name != "nt")

    def test_the_server_class_is_actually_used(self):
        """定义了不用等于没定义。"""
        self.assertIn('srv = _Server(("127.0.0.1", PORT), Handler)', SRC)
        self.assertNotIn('ThreadingHTTPServer(("127.0.0.1", PORT)', SRC)

    def test_posix_keeps_the_fast_restart(self):
        """POSIX 上关掉它会让 Ctrl+C 之后重起撞 TIME_WAIT —— 那是另一个坑。"""
        i = SRC.index("class _Server(")
        seg = flat(SRC[i:SRC.index("def _stop_hint(", i)])
        self.assertIn("TIME_WAIT", seg)
        self.assertRegex(seg, r"Windows 上它的意思完全不同：抢占")


class TheProbeRunsBeforeTheExpensivePart(unittest.TestCase):
    def test_it_happens_before_the_reexport(self):
        """`refresh_if_stale()` 要重导两千多个岗 —— 探完就走的话那是白跑。

        锚在 `main()` 里那**一次调用**上，不是裸名字：裸名字第一次出现是
        它自己的 `def`，排在前面，这条会永远绿。
        """
        self.assertLess(
            SRC.index("_running = probe_running(PORT)"),
            SRC.index("    refresh_if_stale()                    #"))

    def test_it_happens_before_the_bind(self):
        self.assertLess(SRC.index("_running = probe_running(PORT)"),
                        SRC.index('srv = _Server(("127.0.0.1", PORT)'))

    def test_the_happy_path_still_opens_the_browser(self):
        """「已经在跑」时用户要的还是那一页 —— 少这一步就得他自己复制地址。"""
        i = SRC.index("_running = probe_running(PORT)")
        seg = SRC[i:i + 500]
        self.assertIn("open_dashboard(", seg)

    def test_the_reason_is_recorded(self):
        i = SRC.index("# **先看这个端口上是不是已经有一个在跑。**")
        seg = flat(SRC[i:SRC.index("_running = probe_running(PORT)", i)])
        self.assertIn("2026-08-24", seg)
        self.assertRegex(seg, r"Windows 上它的语义是抢占")
        self.assertRegex(seg, r"杀掉的是\*\*刚起的这个新的\*\*")


class ThePageStopsGivingTheWrongFix(unittest.TestCase):
    def test_the_banner_no_longer_says_go_press_ctrl_c(self):
        """那正是把新进程杀掉的那一步。"""
        i = APP.index("这一页的服务还在用旧代码跑")
        seg = APP[i:i + 300]
        self.assertNotIn("Ctrl+C", seg)

    def test_it_still_gives_a_command(self):
        i = APP.index("这一页的服务还在用旧代码跑")
        seg = APP[i:i + 300]
        self.assertIn("python tools/serve.py", seg)

    def test_it_says_the_command_will_tell_you_how(self):
        """页面上不列文件名、也不列 taskkill —— 那两样都归终端。
        页面只负责把人送到会说话的那一步。"""
        i = APP.index("这一页的服务还在用旧代码跑")
        seg = APP[i:i + 300]
        self.assertIn("它会告诉你怎么停掉旧的那个", seg)
        self.assertNotIn("taskkill", seg)


class TheStdlibDefaultIsWhatWeThinkItIs(unittest.TestCase):
    """这一整条建立在「stdlib 默认允许重绑」上。哪天它变了，这里先红。"""

    def test_the_stdlib_default_is_still_true(self):
        self.assertTrue(ThreadingHTTPServer.allow_reuse_address)

    @unittest.skipUnless(os.name == "nt", "只有 Windows 会让第二个也绑上")
    def test_windows_really_lets_a_second_bind_through(self):
        """实测那一条：同一端口上第二个 `ThreadingHTTPServer` **不抛异常**。

        它是这整个 bug 的根 —— 不验一次，下面所有说明都只是传说。
        """
        with Serving({"activeUser": "甲"}) as s:
            second = ThreadingHTTPServer(("127.0.0.1", s.port), Fake)
            second.server_close()

    @unittest.skipUnless(os.name == "nt", "同上")
    def test_our_class_refuses_that_second_bind(self):
        with Serving({"activeUser": "甲"}) as s:
            with self.assertRaises(OSError):
                serve._Server(("127.0.0.1", s.port), Fake).server_close()


if __name__ == "__main__":
    unittest.main()
