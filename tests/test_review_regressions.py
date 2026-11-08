"""Regression coverage for the November repository review."""
import contextlib
import datetime as dt
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import _cli
import archive
import build_dashboard as bd
import ingest
import portal_budget
import rekey
import score
import tracker


class ReviewRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.base = self.root / "users" / "sample" / "job_scraper"
        self.base.mkdir(parents=True)
        (self.root / ".active_user").write_text("sample", encoding="utf-8")
        self.store = self.base / "seen_jobs.json"
        self.job = {"company": "示例公司", "title": "甲岗位", "url": "https://example.com/1"}

    def dump(self, path, value):
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def test_old_archive_is_restored_without_losing_query_history(self):
        self.dump(self.store, {"query_log": [{"query": "示例"}]})
        cold = self.base / "archive.json"
        self.dump(cold, {"old": self.job})
        with patch.object(archive, "ROOT", self.root):
            result = archive.revive("sample", apply=True)
        self.assertEqual(result["revived"], 1)
        restored = _cli.read_json(self.store)
        self.assertEqual(restored["old"], self.job)
        self.assertEqual(restored["query_log"], [{"query": "示例"}])
        self.assertEqual(set(_cli.seen_of(restored)), {"old"})
        self.assertEqual(_cli.seen_of(_cli.read_json(cold)), {})

    def test_rekey_keeps_metadata(self):
        raw = {"old": self.job, "query_log": [{"query": "示例"}]}
        view = _cli.seen_of(raw)
        mapping, collisions = rekey.plan(view)
        self.assertFalse(collisions)
        rekey.apply_rekey(view, mapping)
        self.assertEqual(raw["query_log"], [{"query": "示例"}])
        self.assertEqual(len(view), 1)

    def test_empty_search_is_logged(self):
        self.dump(self.store, {"seen": {}})
        source = self.root / "empty.json"
        self.dump(source, [])
        with patch.object(ingest, "ROOT", self.root), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ingest.main(["--input", str(source), "--query", "示例", "--portal", "liepin-search", "--apply"]), 0)
        self.assertEqual(_cli.read_json(self.store)["query_log"][0]["rows"], 0)

    def test_anonymous_employers_keep_separate_urls(self):
        row = dict(self.job, company="某知名公司")
        key = ingest.pair_key(row["company"], row["title"])
        self.assertEqual(ingest.classify(row, {}, {key}, {key}, set())[0], "new")

    def test_shared_link_materials_match_the_title(self):
        other = dict(self.job, title="乙岗位")
        apps = [{"url": self.job["url"], "dir": "示例公司_甲岗位"}]
        self.assertEqual(bd.match_application(self.job, apps, [self.job, other]), apps[0])
        self.assertIsNone(bd.match_application(other, apps, [self.job, other]))

    def test_old_undo_cannot_delete_later_interview(self):
        path = self.base.parent / "job_search_tracker.csv"
        first = tracker.set_status(path, None, self.job, "applied", "2026-11-01")
        row = tracker.load(path)[1][0]
        tracker.set_status(path, row, self.job, "interview", "2026-11-02")
        result = tracker.undo(path, row, first["prev"], "2026-11-03", version=first["version"])
        self.assertFalse(result["ok"])
        self.assertEqual(tracker.load(path)[1][0]["status"], "interview")

    def test_budget_stale_writer_preserves_block(self):
        with patch.object(portal_budget, "ROOT", self.root):
            data, stamp = portal_budget.load_stamped("sample")
            other, other_stamp = portal_budget.load_stamped("sample")
            now = dt.datetime.now()
            portal_budget.block(data, "liepin-search", "验证码", now)
            portal_budget.save("sample", data, expect=stamp)
            with self.assertRaises(_cli.StaleWrite):
                portal_budget.save("sample", other, expect=other_stamp)
            self.assertTrue(portal_budget.block_state(portal_budget.load("sample"), "liepin", now, lane="cli")["blocked"])

    def test_score_rejects_an_outdated_plan(self):
        self.dump(self.store, {"seen": {"job": self.job}})
        stamp = _cli._stamp_of(self.store)
        self.dump(self.store, {"seen": {"job": dict(self.job, rank_score=99)}})
        with patch.object(score, "ROOT", self.root), self.assertRaises(_cli.StaleWrite):
            score.apply("sample", [{"key": "job", "store_stamp": stamp}], "2026-11-08")
        self.assertEqual(_cli.read_json(self.store)["seen"]["job"]["rank_score"], 99)

    def test_ambiguous_short_title_does_not_take_senior_materials(self):
        junior = dict(self.job, title="产品经理")
        senior = dict(self.job, title="高级产品经理")
        apps = [{"url": self.job["url"], "dir": "示例公司_高级产品经理"}]
        self.assertIsNone(bd.match_application(junior, apps, [junior, senior]))
        self.assertEqual(bd.match_application(senior, apps, [junior, senior]), apps[0])

    def test_audit_restores_the_previous_user_even_on_error(self):
        import audit_pipeline as audit
        previous = list(audit._USER)
        with patch.object(audit, "load", side_effect=RuntimeError("fixture")):
            with self.assertRaises(RuntimeError):
                audit.run("sample")
        self.assertEqual(audit._USER, previous)

    def test_undo_over_http_checks_the_operation_version(self):
        import serve
        import threading
        import urllib.request
        import urllib.error
        from http.server import ThreadingHTTPServer
        from tests.test_serve_writeback import _Temp
        with _Temp() as fixture, patch.object(serve, "_PINNED_USER", "张三"), patch.object(serve, "regenerate"):
            server = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            def post(route, body):
                body.update(token=serve.TOKEN, user="张三")
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}" + route,
                    data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
                try:
                    response = urllib.request.urlopen(request)
                except urllib.error.HTTPError as error:
                    response = error
                with response:
                    return response.status, json.load(response)
            try:
                job_id = _cli.stable_id("https://jobs.51job.com/all/12345.html", "甲岗")
                status, first = post("/api/status", {"id": job_id, "status": "applied"})
                self.assertEqual(status, 200)
                status, second = post("/api/status", {"id": job_id, "status": "interview"})
                self.assertEqual(status, 200)
                status, result = post("/api/status/undo", {"id": job_id, "prev": first["prev"], "version": first["version"]})
                self.assertEqual(status, 409)
                self.assertFalse(result["ok"])
                self.assertEqual(tracker.load(fixture.tmp / "users" / "张三" / "job_search_tracker.csv")[1][0]["status"], "interview")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_pdf_downloads_are_bound_to_the_served_user(self):
        import hashlib
        import serve
        import threading
        import urllib.request
        import urllib.error
        from http.server import ThreadingHTTPServer
        from tests.test_serve_writeback import _Temp
        with _Temp() as fixture, patch.object(serve, "_PINNED_USER", "张三"):
            first = hashlib.sha256("张三".encode()).hexdigest()[:20]
            second = hashlib.sha256("李四".encode()).hexdigest()[:20]
            for namespace, content in ((first, b"first pdf"), (second, b"second pdf")):
                folder = fixture.tmp / "web" / "public" / "pdf" / namespace
                folder.mkdir(parents=True)
                (folder / "resume.pdf").write_bytes(content)
            server = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                address = f"http://127.0.0.1:{server.server_port}/pdf/"
                with urllib.request.urlopen(address + first + "/resume.pdf") as response:
                    self.assertEqual(response.read(), b"first pdf")
                with self.assertRaises(urllib.error.HTTPError) as result:
                    urllib.request.urlopen(address + second + "/resume.pdf")
                self.assertEqual(result.exception.code, 409)
                result.exception.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_score_write_failure_restores_the_evaluation(self):
        dims = {name: 60 for name in score.scoring.DIM_WEIGHTS}
        entry = dict(self.job, rank_breakdown=dims, rank_score=60, rank_verdict="可以考虑")
        self.dump(self.store, {"seen": {"job": entry}})
        document = self.root / "evaluation.md"
        document.write_text("original evaluation", encoding="utf-8")
        row = {"key": "job", "store_stamp": _cli._stamp_of(self.store),
               "doc": document, "doc_stamp": _cli._stamp_of(document),
               "original_text": "original evaluation", "text": "updated evaluation",
               "dims": dims, "score": 61, "verdict": "可以考虑",
               "old": (dims, 60, "可以考虑")}
        write = _cli.atomic_write
        def fail_store(path, text, **kwargs):
            if Path(path) == self.store:
                raise _cli.StaleWrite("simulated conflict")
            return write(path, text, **kwargs)
        with patch.object(score, "ROOT", self.root), patch.object(_cli, "atomic_write", side_effect=fail_store):
            with self.assertRaises(_cli.StaleWrite):
                score.apply("sample", [row], "2026-11-08")
        self.assertEqual(document.read_text(encoding="utf-8"), "original evaluation")
        self.assertEqual(_cli.read_json(self.store)["seen"]["job"]["rank_score"], 60)
