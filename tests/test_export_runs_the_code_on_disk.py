# -*- coding: utf-8 -*-
"""面板服务重导出时，必须跑**盘上最新的**导出器，不是它启动那一刻 import 的那份。

## 同一个坑绊倒两次

`serve.py` 是长驻进程，而 `export_web_data` 一改再改。原来 `_export_now` 是
同进程 `ex.main([...])`——用的是服务器启动那一刻的模块对象。后果不是
「新字段不生效」这么轻：服务会在下一次**自愈重导**时，用旧代码把带新字段的
`data.json` 整个覆盖回旧格式。症状看起来像「前端没渲染」，根因在进程生命周期。

- **第一次**（2026-08-13 上午）：新加的 `outcomeStats` 手动导出后存在、页面查无此块。
  当时的处理是在 `_export_now` 的 docstring 里写一段警告：「改完导出器要重启服务」。
- **第二次**（2026-08-13 晚，全面检查第 5 轮）：服务进程启动于 15:50，
  而 `export_web_data.py` 21:05 改过、`tracker.py` 21:11 改过——**进程比代码老
  五个多小时**。用户只要在面板上点一下按钮，那半天的改动就会被旧代码抹掉。

**警告不是机制。** 这个仓库的常态是 AI 频繁改代码、用户长时间开着面板，
「记得重启服务」这种要求注定失效。改成子进程之后问题从根上没了：
每次导出都加载盘上最新的代码。

这条守卫验的是**控制流**（有没有真的去起子进程），不是源码里有没有某个字符串——
后者在实现改回同进程、注释还留着的时候会照绿。
"""

import json
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import serve  # noqa: E402


class ExportGoesThroughASubprocess(unittest.TestCase):

    def test_it_spawns_the_exporter_on_disk(self):
        """`_export_now` 必须起子进程跑 `tools/export_web_data.py`。"""
        fake = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(serve.subprocess, "run", return_value=fake) as run, \
             mock.patch.object(serve, "active_user", return_value="张三"):
            serve._export_now()
        run.assert_called_once()
        argv = run.call_args[0][0]
        self.assertEqual(argv[0], sys.executable, "没用当前解释器起子进程")
        self.assertTrue(str(argv[1]).endswith("export_web_data.py"),
                        f"起的不是导出器：{argv[1]}")
        self.assertIn("--user", argv, "没显式钉住用户——页面标着 bob、数据是 alice 的")
        self.assertIn("张三", argv)

    def test_it_does_not_call_the_imported_module(self):
        """同进程调用是这个 bug 本身。真调了就会用到启动那一刻的旧代码。"""
        fake = mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(serve.subprocess, "run", return_value=fake), \
             mock.patch.object(serve, "active_user", return_value="张三"), \
             mock.patch.object(serve.ex, "main") as main:
            serve._export_now()
        main.assert_not_called()

    def test_a_failed_export_raises_instead_of_passing_silently(self):
        """导出失败要抛出去，让调用方那几处 `except` 把真因写进日志。

        静默降级正是这一整类 bug 的成因：页面照常给出旧数据，谁也不知道。
        """
        fake = mock.Mock(returncode=1, stdout="", stderr="炸了")
        with mock.patch.object(serve.subprocess, "run", return_value=fake), \
             mock.patch.object(serve, "active_user", return_value="张三"):
            with self.assertRaises(Exception) as cm:
                serve._export_now()
        self.assertIn("炸了", str(cm.exception), "错误原文没带上，日志里查不出为什么")

    def test_callers_still_catch_it(self):
        """抛出去的前提是调用方接得住——不然自愈重导失败会让整个请求崩掉。"""
        src = (ROOT / "tools" / "serve.py").read_text(encoding="utf-8")
        i = src.index("def refresh_if_stale")
        self.assertIn("except Exception", src[i:i + 1400],
                      "refresh_if_stale 没有兜住导出异常，一次导出失败会让面板打不开")


class StaleCodeGetsCalledOut(unittest.TestCase):
    """写盘那一路仍是同进程的——改了代码不重启，服务就按旧逻辑写盘。

    子进程只解决了**导出**。`apply_status` → `tracker.set_status` →
    `_cli.atomic_write` 这条链上的对象全是服务启动时 import 进来的，
    改了它们必须重启。

    2026-08-13 一天撞了三次（新字段查无此块 / 进程比代码老五小时 / tracker 刚换
    原子写而服务里还是裸写）。前两次的处理都是「写段注释提醒重启」——
    **三次之后该承认注释不是机制**，所以有了 `warn_if_code_changed`。
    """

    def test_it_watches_the_modules_that_matter(self):
        watched = set(serve._CODE_MTIME)
        for f in ("serve.py", "tracker.py", "_cli.py", "export_web_data.py"):
            self.assertIn(f, watched, f"{f} 改了不会被发现——它就在写盘那条链上")

    def test_the_list_covers_everything_serve_imports(self):
        """名单**从 serve.py 的 import 现推**，不手抄。

        手抄的那份漏过一个：`portal_budget` 是函数内 import（`apply_unblock` 里），
        写的是封控冷却，而它不在名单里——加接口的人不会想到还要回来改一个常量。
        顶层 import 和函数内 import 在「进程比代码老」这件事上没有区别。
        """
        src = (ROOT / "tools" / "serve.py").read_text(encoding="utf-8")
        local = {p.name for p in (ROOT / "tools").glob("*.py")}
        imported = {f"{m}.py" for m in re.findall(r"^\s*import (\w+)", src, re.M)
                    if f"{m}.py" in local}
        watched = set(serve._CODE_MTIME)
        missed = sorted(imported - watched)
        self.assertEqual(missed, [],
                         f"serve.py 会 import 这些本地模块，但它们不在看守名单里："
                         f"{missed}——改了之后服务照旧跑内存里那份")

    def test_it_warns_when_a_file_gets_newer(self):
        """伪造一个「比进程新」的 mtime，必须喊，而且要说出该敲什么。"""
        import io
        from unittest import mock
        f = "tracker.py"
        old = serve._CODE_MTIME[f]
        buf = io.StringIO()
        try:
            serve._CODE_MTIME[f] = old - 10          # 假装进程启动得更早
            serve._STALE_WARNED.discard(f)
            with mock.patch.object(serve.sys, "stderr", buf):
                changed = serve.warn_if_code_changed()
        finally:
            serve._CODE_MTIME[f] = old
            serve._STALE_WARNED.discard(f)
        self.assertIn(f, changed)
        out = buf.getvalue()
        self.assertIn("python tools/serve.py", out,
                      "只说「改过了」不说该敲什么，用户不知道怎么办")
        self.assertIn("Ctrl+C", out)

    def test_it_does_not_nag_twice_for_the_same_file(self):
        """每次请求都刷一遍同样的警告，等于没有警告。"""
        import io
        from unittest import mock
        f = "tracker.py"
        old = serve._CODE_MTIME[f]
        try:
            serve._CODE_MTIME[f] = old - 10
            serve._STALE_WARNED.discard(f)
            b1, b2 = io.StringIO(), io.StringIO()
            with mock.patch.object(serve.sys, "stderr", b1):
                serve.warn_if_code_changed()
            with mock.patch.object(serve.sys, "stderr", b2):
                serve.warn_if_code_changed()
        finally:
            serve._CODE_MTIME[f] = old
            serve._STALE_WARNED.discard(f)
        self.assertTrue(b1.getvalue().strip(), "第一次就该喊")
        self.assertEqual(b2.getvalue(), "", "同一个文件喊第二遍就是噪音")

    def test_the_selfheal_path_calls_it(self):
        """挂在自愈检查上——那是每次取数据都会走的地方。"""
        src = (ROOT / "tools" / "serve.py").read_text(encoding="utf-8")
        i = src.index("def refresh_if_stale")
        self.assertIn("warn_if_code_changed", src[i:i + 600],
                      "没挂在自愈检查里，这个提示永远不会触发")

    def test_the_flag_rides_the_snapshot_to_the_page(self):
        """提醒必须走到**页面**上——终端警告 nohup 一包就没人看见。

        `with_stale_flag` 把变更名单塞进这一次的 /data.json 响应（不落盘）；
        前端读 `staleCode` 渲染横幅。三段各验各的：注入对、空名单不动原文、
        坏 JSON 原样端出（一个提醒不值得把整页搞挂）。
        """
        raw = json.dumps({"jobs": [], "nextStep": {"text": "x"}},
                         ensure_ascii=False).encode("utf-8")
        out = json.loads(serve.with_stale_flag(raw, ["tracker.py"]).decode("utf-8"))
        self.assertEqual(out["staleCode"], ["tracker.py"])
        self.assertEqual(out["nextStep"], {"text": "x"}, "原有字段不能被弄丢")
        self.assertEqual(serve.with_stale_flag(raw, []), raw,
                         "没变更就该原样端出，不要空数组污染快照")
        broken = b"{not json"
        self.assertEqual(serve.with_stale_flag(broken, ["a.py"]), broken,
                         "坏 JSON 要原样端出——提醒不值得把整页搞挂")

    def test_the_page_renders_the_flag(self):
        """前端得真用上这个字段，不然服务端塞了也白塞。"""
        app = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
        self.assertIn("staleCode", app, "页面没读 staleCode，横幅永远不会出现")
        self.assertIn("python tools/serve.py", app,
                      "提醒里没写出该敲的命令（面板通例：每处引导都写出命令）")

    def test_detected_tool_rides_the_snapshot_per_response(self):
        """盘上 data.json 的 detectedTool 是**导出那一刻**的环境，可能来自别的工具。

        实测 2026-09-12：Claude Code 起的面板，端的是早先 Antigravity 会话导出的
        快照（快照只在数据上游变化时重导，环境换了不重导），整页命令用了那份快照的档。
        with_detected_tool 在响应时按起服务的环境盖写，不落盘。
        ⚠️ **别在这条里断言「免斜杠」**：那是被测工具的档位，不是「盖写生效」这件事，
        而档位 2026-10-13 又翻过一次（认不出来的那批改成带斜杠）。
        """
        raw = json.dumps({"jobs": [], "detectedTool": "antigravity"},
                         ensure_ascii=False).encode("utf-8")
        out = json.loads(serve.with_detected_tool(raw, "claude").decode("utf-8"))
        self.assertEqual(out["detectedTool"], "claude")
        self.assertEqual(out["jobs"], [], "原有字段不能被弄丢")
        broken = b"{not json"
        self.assertEqual(serve.with_detected_tool(broken, "claude"), broken,
                         "坏 JSON 要原样端出——盖一个字段不值得把整页搞挂")

    def test_the_data_route_applies_the_override(self):
        """盖写必须挂在 /data.json 的出口，两个响应分支都算。"""
        src = (ROOT / "tools" / "serve.py").read_text(encoding="utf-8")
        i = src.index('if path == "/data.json"')
        seg = src[i:i + 2200]
        self.assertIn("with_detected_tool", seg,
                      "/data.json 出口没盖写 detectedTool，换工具起服务会端旧值")
        self.assertIn("_cli.detect_code_tool()", seg,
                      "盖写值得按当前环境现探，不能写死")


class TheReasonIsWrittenDown(unittest.TestCase):
    """为什么不能图快改回同进程——理由要留在代码里，不然下一个人会「优化」掉它。"""

    def test_the_docstring_keeps_both_incidents(self):
        src = (ROOT / "tools" / "serve.py").read_text(encoding="utf-8")
        i = src.index("def _export_now")
        doc = src[i:i + 2200]
        self.assertIn("子进程", doc)
        self.assertIn("覆盖回旧格式", doc, "没写清后果，读的人会以为只是「新字段不生效」")
        self.assertIn("警告不是机制", doc,
                      "没写清为什么光加注释不够——那正是第一次的处理方式，它失败了")


if __name__ == "__main__":
    unittest.main()


class TheWriteTokenIsComparedSafely(unittest.TestCase):
    """写盘凭据用定时安全比较，不用 `!=`。

    这条链的唯一凭据就是这个 token（Origin 校验挡跨站，但它自己承认
    「Origin 缺失也放行……真正兜底的是 token」）。

    普通 `!=` 一撞上不同的字符就返回，响应时间随「猜对了几个前缀字符」变化。
    跨站页面 POST 得到、读不到响应——**但读不到不等于量不到耗时**，
    no-cors 请求的时长照样可测。`secrets` 在这个文件里本来就 import 了，
    换成 `compare_digest` 是零成本。
    """

    def test_it_uses_compare_digest(self):
        src = (ROOT / "tools" / "serve.py").read_text(encoding="utf-8")
        self.assertIn("secrets.compare_digest(", src,
                      "token 又改回普通比较了——那是可测的定时侧信道")
        self.assertNotIn('body.get("token") != TOKEN', src)

    def test_a_non_string_token_is_a_403_not_a_500(self):
        """`compare_digest` 收到非字符串会抛 TypeError → 变成 500，
        把内部异常端给用户；这里必须先转 str，让它干脆地 403。"""
        src = (ROOT / "tools" / "serve.py").read_text(encoding="utf-8")
        self.assertIn('str(body.get("token") or "")', src,
                      "没先转成字符串——传个数字进来就是 500 而不是 403")

    def test_the_token_is_actually_random(self):
        """凭据本身得是随机的，不然比较方式再安全也没意义。

        2026-10-23 起这个 token **落盘持久化**了（服务重启不该作废已经开着的
        那个页面——那正是「点『我投了』没反应」的根因）。所以它不再每次启动
        现生成一个，而是**第一次随机生成、之后一直用同一个**。

        随机性这条判据没有因此失效：第一次的值仍由 `secrets` 生成，
        仍然不可猜；跨站页面照样读不到它（它只在本页的 DOM 里）。
        变的是「多久换一次」，不是「从哪儿来」。
        """
        self.assertGreaterEqual(len(serve.TOKEN), 16, "token 太短")
        src = (ROOT / "tools" / "serve.py").read_text(encoding="utf-8")
        i = src.index("def _load_or_make_token(")
        seg = src[i:i + 1500]
        self.assertRegex(seg, r"secrets\.token_urlsafe\(",
                         "token 不是 secrets 生成的")
        # **不许写死成常量**：赋值那一行的右边必须是一次调用，不是字面量。
        m = re.search(r"(?m)^\s*TOKEN\s*=\s*(.+)$", src)
        self.assertIsNotNone(m, "找不到 TOKEN 的赋值")
        self.assertNotIn('"', m.group(1),
                         "token 像是写死在源码里的常量 —— 那就不是凭据了")
