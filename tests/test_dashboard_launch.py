"""Opening a local dashboard does not wait on unused ports or regenerate data."""
import socket
import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from unittest.mock import Mock
from contextlib import redirect_stdout, redirect_stderr

from tests.test_a_second_server_does_not_shadow_the_first import Fake, Serving, free_port
import serve


class DashboardLaunchTests(unittest.TestCase):
    def test_real_detached_child_becomes_ready_and_is_reused(self):
        # 独立的小服务模拟首次导出耗时，验证真实进程与 HTTP 就绪检查的衔接。
        script = '''import argparse, json, time
from http.server import BaseHTTPRequestHandler, HTTPServer
parser = argparse.ArgumentParser()
parser.add_argument('--user')
parser.add_argument('--port', type=int)
args = parser.parse_args()
time.sleep(0.3)
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({'activeUser': args.user, 'staleCode': []}).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        pass
HTTPServer(('127.0.0.1', args.port), Handler).serve_forever()
'''
        children = []
        real_spawn = subprocess.Popen
        def spawn(*args, **kwargs):
            child = real_spawn(*args, **kwargs)
            children.append(child)
            return child
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tools").mkdir()
            (root / "tools/serve.py").write_text(script, encoding="utf-8")
            port = free_port()
            try:
                with patch.object(serve, "ROOT", root), \
                     patch.object(serve.subprocess, "Popen", side_effect=spawn), \
                     patch.object(serve, "active_user", return_value="example"), \
                     patch.object(serve, "_load_or_make_token", return_value="test"), \
                     patch.object(serve, "open_dashboard") as browser:
                    self.assertEqual(serve.main(["--background", "--port", str(port)]), 0)
                    self.assertEqual(serve.main(["--background", "--port", str(port)]), 0)
                    self.assertEqual(len(children), 1)
                    self.assertEqual(browser.call_count, 2)
                    browser.assert_called_with(f"http://127.0.0.1:{port}/")
                    self.assertIsNone(children[0].poll())
            finally:
                for child in children:
                    child.terminate()
                    child.wait(timeout=5)

    def test_background_server_has_detached_output_and_no_recursive_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(serve, "ROOT", root), \
                 patch.object(serve.subprocess, "Popen") as spawn, \
                 patch.object(serve, "probe_running", return_value={"ours": True, "user": "example", "stale": []}), \
                 patch.object(serve, "open_dashboard"):
                spawn.return_value.pid = 123
                spawn.return_value.poll.return_value = None
                self.assertEqual(serve.start_background("example", 29031), 0)
                arguments = spawn.call_args.args[0]
                options = spawn.call_args.kwargs
                self.assertNotIn("--background", arguments)
                self.assertEqual(arguments[-4:], ["--user", "example", "--port", "29031"])
                self.assertEqual(options["stdin"], subprocess.DEVNULL)
                self.assertEqual(options["stderr"], subprocess.STDOUT)
                self.assertEqual(options["env"]["JOBS_NO_BROWSER"], "1")
                self.assertEqual(Path(options["stdout"].name),
                                 root / "users/example/job_scraper/dashboard/serve.log")
                if os.name == "nt":
                    self.assertTrue(options["creationflags"] & subprocess.DETACHED_PROCESS)
                else:
                    self.assertTrue(options["start_new_session"])

    def test_background_command_returns_before_snapshot_preparation(self):
        with patch.object(serve, "active_user", return_value="example"), \
             patch.object(serve, "_load_or_make_token", return_value="test"), \
             patch.object(serve, "probe_running", return_value=None), \
             patch.object(serve, "start_background", return_value=0) as start, \
             patch.object(serve, "refresh_if_stale",
                          side_effect=AssertionError("preparing data in launcher")):
            self.assertEqual(serve.main(["--background", "--port", "29031"]), 0)
            start.assert_called_once_with("example", 29031)

    def test_free_port_is_detected_without_a_tcp_connection(self):
        port = free_port()
        with patch.object(socket.socket, "connect_ex",
                          side_effect=AssertionError("unnecessary TCP connection")):
            self.assertIsNone(serve.probe_running(port))

    def test_existing_server_is_checked_without_requesting_data(self):
        requested = []
        original = Fake.do_GET

        def health_only(handler):
            requested.append(handler.path)
            original(handler)

        with patch.object(Fake, "do_GET", health_only):
            with Serving({"activeUser": "example", "staleCode": []}) as server:
                result = serve.probe_running(server.port)
        self.assertEqual(requested, ["/api/health"])
        self.assertEqual(result, {"ours": True, "user": "example", "stale": []})

    def test_old_server_without_health_endpoint_remains_supported(self):
        requested = []
        original = Fake.do_GET

        def legacy(handler):
            requested.append(handler.path)
            if handler.path == "/api/health":
                handler.send_error(404)
            else:
                original(handler)

        with patch.object(Fake, "do_GET", legacy):
            with Serving({"activeUser": "example", "jobs": []}) as server:
                result = serve.probe_running(server.port)
        self.assertEqual(requested, ["/api/health", "/data.json"])
        self.assertTrue(result["ours"])
        self.assertEqual(result["user"], "example")

    def test_slow_start_is_retried_before_opening_browser(self):
        ready = {"ours": True, "user": "example", "stale": []}
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(serve, "ROOT", Path(directory)), \
             patch.object(serve.subprocess, "Popen") as spawn, \
             patch.object(serve, "probe_running", side_effect=[None, None, ready]) as probe, \
             patch.object(serve.time, "sleep"), \
             patch.object(serve, "open_dashboard") as browser:
            spawn.return_value.poll.return_value = None
            self.assertEqual(serve.start_background("example", 29031), 0)
            self.assertEqual(probe.call_count, 3)
            browser.assert_called_once_with("http://127.0.0.1:29031/")

    def test_early_exit_reports_only_this_launch_log(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "users/example/job_scraper/dashboard/serve.log"
            log.parent.mkdir(parents=True)
            log.write_text("old failure\n", encoding="utf-8")
            def spawn(*args, **kwargs):
                kwargs["stdout"].write("本次启动失败\n".encode("utf-8"))
                kwargs["stdout"].flush()
                return Mock(pid=123, poll=Mock(return_value=2))
            errors = io.StringIO()
            with patch.object(serve, "ROOT", root), \
                 patch.object(serve.subprocess, "Popen", side_effect=spawn), \
                 patch.object(serve, "probe_running") as probe, \
                 patch.object(serve, "open_dashboard") as browser, redirect_stderr(errors):
                self.assertEqual(serve.start_background("example", 29031), 1)
            self.assertIn("本次启动失败", errors.getvalue())
            self.assertIn("退出码 2", errors.getvalue())
            self.assertNotIn("old failure", errors.getvalue())
            probe.assert_not_called()
            browser.assert_not_called()

    def test_timeout_does_not_report_success_or_open_browser(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(serve, "ROOT", Path(directory)), \
             patch.object(serve.subprocess, "Popen") as spawn, \
             patch.object(serve, "probe_running", return_value=None), \
             patch.object(serve, "open_dashboard") as browser, \
             redirect_stderr(io.StringIO()) as errors:
            spawn.return_value.poll.return_value = None
            self.assertEqual(serve.start_background("example", 29031, timeout=0.01), 1)
            self.assertIn("仍在运行", errors.getvalue())
            browser.assert_not_called()
            spawn.return_value.terminate.assert_not_called()

    def test_existing_wrong_user_or_stale_code_is_not_success(self):
        for info in ({"ours": True, "user": "other", "stale": []},
                     {"ours": True, "user": "example", "stale": ["serve.py"]}):
            with self.subTest(info=info), \
                 patch.object(serve, "active_user", return_value="example"), \
                 patch.object(serve, "_load_or_make_token", return_value="test"), \
                 patch.object(serve, "probe_running", return_value=info), \
                 patch.object(serve, "start_background") as spawn, \
                 patch.object(serve, "open_dashboard") as browser:
                self.assertEqual(serve.main(["--background"]), 1)
                spawn.assert_not_called()
                browser.assert_not_called()

    def test_browser_failure_keeps_ready_server_and_reports_url(self):
        for result in (False, OSError("no browser"), serve.webbrowser.Error("no browser")):
            with self.subTest(result=result), patch.dict(os.environ, {"JOBS_NO_BROWSER": "0"}), \
                 patch.object(serve.webbrowser, "open", side_effect=result if isinstance(result, Exception) else None,
                              return_value=False), redirect_stdout(io.StringIO()) as output:
                serve.open_dashboard("http://127.0.0.1:29031/")
                self.assertIn("浏览器未能自动打开", output.getvalue())
                self.assertIn("http://127.0.0.1:29031/", output.getvalue())

    def test_disconnect_during_headers_or_body_is_handled(self):
        for operation in ("end_headers", "write"):
            for error in (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                handler = Mock()
                target = handler.wfile.write if operation == "write" else handler.end_headers
                target.side_effect = error()
                serve.Handler._send(handler, 200, b"body", "text/plain")
                self.assertTrue(handler.close_connection)

    def test_other_response_errors_are_reported(self):
        handler = Mock()
        handler.wfile.write.side_effect = OSError("disk or unexpected socket error")
        with self.assertRaises(OSError):
            serve.Handler._send(handler, 200, b"body", "text/plain")
