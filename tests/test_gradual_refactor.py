"""Regressions for identity, private exports, interrupted migration and writers."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import _cli
import build_dashboard as bd
import jd_store
import rekey
import serve


class RefactorRegressions(unittest.TestCase):
    def test_health_check_never_exports_the_snapshot(self):
        handler = Mock()
        handler.path = "/api/health"
        with patch.object(serve, "_PINNED_USER", "example"), \
             patch.object(serve, "refresh_if_stale", side_effect=AssertionError("unexpected export")), \
             patch.object(serve, "warn_if_code_changed", return_value=[]):
            serve.Handler.do_GET(handler)
        self.assertEqual(handler._json.call_args.args, (
            200, {"activeUser": "example", "staleCode": []}))

    def test_chinese_homepage(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "index.html").write_text("<head></head>", encoding="utf8")
            handler = Mock()
            with patch.object(serve, "DIST", root), patch.object(serve, "_PINNED_USER", "小林"):
                serve.Handler._serve_index(handler)
            self.assertEqual(handler._send.call_args.args[0], 200)

    def test_bom_overlay_is_preserved_and_bad_file_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as folder:
            seen = Path(folder) / "seen_jobs.json"
            state = seen.with_name("user_state.json")
            state.write_text(json.dumps({"a": {"decision": "skipped"}}), encoding="utf-8-sig")
            _cli.set_hr_viewed(seen, "b", True)
            self.assertEqual(set(_cli.read_json(state)), {"a", "b"})
            for content in ("broken", "[]"):
                state.write_text(content, encoding="utf8")
                with self.assertRaises(ValueError):
                    _cli.set_hr_viewed(seen, "b", True)
                self.assertEqual(state.read_text(), content)

    def test_independent_processes_merge_overlay_updates(self):
        with tempfile.TemporaryDirectory() as folder:
            code = """import sys
sys.path.insert(0, sys.argv[1])
import _cli
_cli.set_user_decision(sys.argv[2], sys.argv[3], 'skipped')
"""
            processes = [subprocess.Popen([sys.executable, "-c", code, str(ROOT / "tools"),
                                          str(Path(folder) / "seen_jobs.json"), str(i)])
                         for i in range(6)]
            self.assertEqual([p.wait(timeout=30) for p in processes], [0] * 6)
            self.assertEqual(len(_cli.read_json(Path(folder) / "user_state.json")), 6)

    def test_process_exit_releases_file_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "data.json"
            code = """import sys, time
sys.path.insert(0, sys.argv[1])
from file_lock import file_lock
with file_lock(sys.argv[2]):
    print('locked', flush=True)
    time.sleep(30)
"""
            worker = subprocess.Popen(
                [sys.executable, "-c", code, str(ROOT / "tools"), str(target)],
                stdout=subprocess.PIPE, text=True,
            )
            try:
                self.assertEqual(worker.stdout.readline().strip(), "locked")
            finally:
                worker.terminate()
                worker.wait(timeout=10)
                worker.stdout.close()
            _cli.atomic_write(target, "recovered")
            self.assertEqual(target.read_text(), "recovered")

    def test_same_version_concurrent_processes_have_one_winner(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / "data.json"
            target.write_text("original", encoding="utf8")
            stamp = json.dumps(_cli._stamp_of(target))
            code = """import json, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import _cli
root = Path(sys.argv[2])
(root / ('ready-' + sys.argv[3])).touch()
while not (root / 'release').exists():
    time.sleep(0.01)
try:
    _cli.atomic_write(root / 'data.json', sys.argv[3], expect=tuple(json.loads(sys.argv[4])))
    print('saved')
except _cli.StaleWrite:
    print('conflict')
"""
            workers = [subprocess.Popen(
                [sys.executable, "-c", code, str(ROOT / "tools"), folder, str(i), stamp],
                stdout=subprocess.PIPE, text=True) for i in range(2)]
            try:
                import time
                deadline = time.monotonic() + 10
                while len(list(root.glob("ready-*"))) < 2:
                    if time.monotonic() > deadline:
                        self.fail("writer processes did not start")
                    time.sleep(0.01)
                (root / "release").touch()
                results = [worker.communicate(timeout=15)[0].strip() for worker in workers]
                self.assertEqual(sorted(results), ["conflict", "saved"])
            finally:
                for worker in workers:
                    if worker.poll() is None:
                        worker.terminate()
                    worker.wait(timeout=10)

    def test_stale_process_cannot_overwrite_a_new_commit(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "data.json"
            target.write_text("old", encoding="utf8")
            stamp = _cli._stamp_of(target)
            _cli.atomic_write(target, "updated", expect=stamp)
            with self.assertRaises(_cli.StaleWrite):
                _cli.atomic_write(target, "stale", expect=stamp)
            self.assertEqual(target.read_text(), "updated")

    def test_same_url_selects_exact_role_and_rejects_ambiguous_body(self):
        url = "https://example.org/job/1"
        entries = {str(i): {"url": url, "title": title}
                   for i, title in enumerate(("Engineer", "Senior Engineer"))}
        rows = [{"source": url, "role": e["title"]} for e in entries.values()]
        self.assertEqual(bd.match_tracker(entries["1"], url, rows)["role"], "Senior Engineer")
        self.assertIsNone(bd.match_tracker(entries["1"], url, rows[:1]))
        with self.assertRaises(ValueError):
            jd_store.select_entry(entries, url)
        legacy = {url: entries["0"], url + "#Senior Engineer": entries["1"]}
        with self.assertRaises(ValueError):
            jd_store.select_entry(legacy, url)
        reference = _cli.stable_id(url, "Senior Engineer")
        self.assertEqual(jd_store.select_entry(entries, reference)["title"], "Senior Engineer")

    def test_indexed_material_matching_keeps_existing_results(self):
        entries = [{"url": f"https://example.org/{i}", "title": "Engineer"} for i in range(50)]
        apps = [{"url": e["url"], "dir": "Engineer", "resume": True} for e in entries]
        index = bd.application_index(apps, entries)
        for entry in entries:
            self.assertEqual(bd.match_application(entry, apps, entries),
                             bd.match_application(entry, apps, entries, index=index))

    def test_private_snapshot_paths_do_not_cross_users(self):
        self.assertNotEqual(_cli.dashboard_dir("a", ROOT), _cli.dashboard_dir("b", ROOT))
        self.assertTrue(_cli.dashboard_dir("a", ROOT).is_relative_to(ROOT / "users" / "a"))

    def test_snapshot_response_is_pinned_to_each_user_and_rejects_unknown_owner(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for user in ("alice", "bob"):
                target = _cli.dashboard_dir(user, root) / "data.json"
                target.parent.mkdir(parents=True)
                target.write_text(json.dumps({"activeUser": user}), encoding="utf8")
                handler = Mock()
                handler.path = "/data.json"
                with patch.object(serve, "ROOT", root), patch.object(serve, "_PINNED_USER", user), \
                     patch.object(serve, "refresh_if_stale"), patch.object(serve, "warn_if_code_changed", return_value=[]):
                    serve.Handler.do_GET(handler)
                self.assertEqual(handler._send.call_args.args[0], 200)
                self.assertEqual(json.loads(handler._send.call_args.args[1])["activeUser"], user)
            target.write_text("{}", encoding="utf8")
            handler = Mock()
            handler.path = "/data.json"
            with patch.object(serve, "ROOT", root), patch.object(serve, "_PINNED_USER", "bob"), \
                 patch.object(serve, "refresh_if_stale"):
                serve.Handler.do_GET(handler)
            self.assertEqual(handler._send.call_args.args[0], 409)

    def test_rekey_resumes_after_overlay_write_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder) / "users" / "demo" / "job_scraper"
            base.mkdir(parents=True)
            seen = base / "seen_jobs.json"
            overlay = base / "user_state.json"
            entry = {"url": "https://example.org/1", "title": "Engineer"}
            seen.write_text(json.dumps({"seen": {"old": entry}}), encoding="utf8")
            overlay.write_text(json.dumps({"old": {"decision": "skipped"}}), encoding="utf8")
            original = _cli.atomic_write
            def interrupted(path, *args, **kwargs):
                if Path(path) == overlay:
                    raise OSError("simulated write failure")
                return original(path, *args, **kwargs)
            with patch.object(_cli, "atomic_write", interrupted):
                with self.assertRaises(OSError):
                    rekey.run("demo", True, Path(folder))
            rekey.run("demo", True, Path(folder))
            key = _cli.job_key(entry)
            self.assertEqual(_cli.read_json(overlay)[key]["decision"], "skipped")
            self.assertEqual(set(_cli.read_json(seen)["seen"]), {key})
            self.assertFalse((base / "rekey-pending.json").exists())


class WritebackDimensions(unittest.TestCase):
    def test_changed_dimensions_are_written_even_when_total_is_equal(self):
        from tests.test_writeback_tool import _Repo, EVAL_OK
        fixture = _Repo()
        fixture.setUp()
        try:
            fixture._dir("demo", EVAL_OK)
            fixture._run("--apply")
            doc = fixture.apps / "demo" / "evaluation.md"
            doc.write_text(doc.read_text(encoding="utf8")
                           .replace("强度与公司性质 | 70", "强度与公司性质 | 75")
                           .replace("发展与风险 | 70", "发展与风险 | 66"), encoding="utf8")
            fixture._run("--apply")
            dims = fixture._entry()["rank_breakdown"]
            self.assertEqual((dims["强度与公司性质"], dims["发展与风险"]), (75, 66))
            self.assertIn("一致", fixture._run("--apply")[1])
        finally:
            fixture.tearDown()
