"""Browser regression with synthetic responses and an existing web build."""
import json
import mimetypes
import os
from pathlib import Path
import subprocess
import unittest
from urllib.parse import urlparse


class RestoreBrowserTest(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("JOBS_BROWSER_TEST") == "1",
        "Set JOBS_BROWSER_TEST=1 after building web; requires Playwright and Chrome",
    )
    def test_expire_then_restore_without_reload(self):
        from playwright.sync_api import expect, sync_playwright

        repository = Path(__file__).resolve().parents[1]
        distribution = repository / "web" / "dist"
        fixture_script = (
            "import {jobs} from './web/src/data/sample.ts';"
            "console.log(JSON.stringify(jobs[0]))"
        )
        fixture = json.loads(subprocess.check_output(
            ["node", "--input-type=module", "-e", fixture_script],
            cwd=repository, encoding="utf8",
        ))
        fixture.update(id="review-1", dupOf=None, skipped=False, expired=False, applied=None)
        fixture["nextStep"] = {"text": "Review fixture", "command": "/job-outcome"}
        snapshot = {"isRealData": True, "activeUser": "example", "jobs": [fixture]}
        operations = []
        pending_writes = []

        def respond(route):
            path = urlparse(route.request.url).path
            if path == "/data.json":
                route.fulfill(json=snapshot)
                return
            if path in ("/api/expire", "/api/restore"):
                fixture["expired"] = path == "/api/expire"
                operations.append(path)
                if path == "/api/expire":
                    pending_writes.append(route)
                    return
                route.fulfill(json={"ok": True})
                return
            asset = distribution / (path.strip("/") or "index.html")
            if asset.is_file():
                route.fulfill(path=asset, content_type=mimetypes.guess_type(asset.name)[0])
                return
            route.fulfill(status=404)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            try:
                page = browser.new_page()
                page.set_default_timeout(5000)
                page.route("**/*", respond)
                page.add_init_script(
                    "window.__API_TOKEN__='demo';window.__API_USER__='example';"
                )
                page.goto("http://review.localhost/")
                row = page.locator('tr[data-row-key="review-1"]')
                row.wait_for()
                expire = page.get_by_role("button", name="职位已下线", exact=True)
                if not expire.is_visible():
                    row.click()
                expire.click()
                expect(row).to_have_count(0)
                self.assertEqual(len(pending_writes), 1)
                pending_writes[0].fulfill(json={"ok": True})
                page.get_by_text("不投的岗位（1", exact=False).last.click()
                page.get_by_role("button", name="放回可以投", exact=False).click()
                expect(row).to_have_count(1)
                self.assertEqual(operations, ["/api/expire", "/api/restore"])
                page.reload()
                expect(row).to_have_count(1)
            finally:
                browser.close()

    @unittest.skipUnless(
        os.environ.get("JOBS_BROWSER_TEST") == "1",
        "Set JOBS_BROWSER_TEST=1 after building web; requires Playwright and Chrome",
    )
    def test_local_views_open_without_additional_script_requests(self):
        from playwright.sync_api import expect, sync_playwright

        repository = Path(__file__).resolve().parents[1]
        distribution = repository / "web" / "dist"
        fixture = json.loads(subprocess.check_output(
            ["node", "--input-type=module", "-e",
             "import {jobs} from './web/src/data/sample.ts';console.log(JSON.stringify(jobs[0]))"],
            cwd=repository, encoding="utf8",
        ))
        fixture.update(id="review-local", dupOf=None, skipped=False, expired=False, applied=None)
        fixture["nextStep"] = {"text": "Review fixture", "command": "/job-outcome"}
        snapshot = {
            "isRealData": True, "activeUser": "example", "jobs": [fixture],
            "commands": [{"group": "开始", "items": [{
                "name": "job-auto", "cmd": "/job-auto", "does": "找工作", "examples": [],
            }]}],
            "hrAnswers": [{"q": "期望薪资", "a": "示例回答", "empty": False}],
            "prefs": [{"key": "outsourced", "enabled": True, "label": "外包",
                          "note": "示例", "n": 1}],
            "baseResume": {"updated": "2026-11-09", "sections": ["经历"],
                           "missingSections": []},
            "resumeInsight": {
                "sweetSpot": {"count": 1, "total": 1, "withBody": 1,
                              "industries": [], "asks": [], "resumeChecked": True},
                "medianStack": 70, "medianDomain": 60, "blockers": [],
            },
            "outcomeStats": {"total": 1, "buckets": [], "byBand": [],
                             "repliedRate": None, "interviewRate": None,
                             "waitingMedian": None, "reasons": []},
        }
        requested = []
        block_scripts = False

        def respond(route):
            path = urlparse(route.request.url).path
            if path == "/data.json":
                route.fulfill(json=snapshot)
                return
            if path.endswith(".js"):
                requested.append(path)
            if block_scripts and path.endswith(".js"):
                route.abort("failed")
                return
            asset = distribution / (path.strip("/") or "index.html")
            if asset.is_file():
                route.fulfill(path=asset, content_type=mimetypes.guess_type(asset.name)[0])
                return
            route.fulfill(status=404)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            try:
                page = browser.new_page()
                page.set_default_timeout(5000)
                page.route("**/*", respond)
                page.add_init_script(
                    "window.__API_TOKEN__='demo';window.__API_USER__='example';"
                )
                page.goto("http://review.localhost/")
                row = page.locator('tr[data-row-key="review-local"]')
                row.wait_for()
                initial = list(requested)
                block_scripts = True
                for desk, selector in (
                    ("jobprefs", ".jobprefs"),
                    ("baseresume", ".bresume"),
                    ("resume", ".rread"),
                    ("ostats", ".ostats"),
                    ("cmds", ".cmdbook"),
                ):
                    page.locator(f'[data-desk="{desk}"]').click()
                    expect(page.locator(".ant-modal-body").locator(selector)).to_be_visible()
                    self.assertEqual(requested, initial)
                    page.locator(".ant-modal-close").click()
                page.locator('[data-desk="hrqa"]').click()
                expect(page.locator(".hrqa")).to_be_visible()
                page.locator(".ant-modal-close").click()
                page.locator('[data-desk="hrqa"]').click()
                expect(page.locator(".hrqa")).to_be_visible()
                page.locator(".ant-modal-close").click()
                row.click()
                expect(page.get_by_role("button", name="职位已下线", exact=True)).to_be_visible()
                self.assertEqual(requested, initial)
            finally:
                browser.close()

    @unittest.skipUnless(
        os.environ.get("JOBS_BROWSER_TEST") == "1",
        "Set JOBS_BROWSER_TEST=1 after building web; requires Playwright and Chrome",
    )
    def test_failed_initial_read_can_retry_without_reloading_the_page(self):
        from playwright.sync_api import expect, sync_playwright

        distribution = Path(__file__).resolve().parents[1] / "web" / "dist"
        requests = {"index": 0, "data": 0}

        def respond(route):
            path = urlparse(route.request.url).path
            if path == "/data.json":
                requests["data"] += 1
                if requests["data"] == 1:
                    route.fulfill(status=503, json={"error": "temporary failure"})
                else:
                    route.fulfill(json={"isRealData": True, "activeUser": "example", "jobs": []})
                return
            if path == "/":
                requests["index"] += 1
            asset = distribution / (path.strip("/") or "index.html")
            if asset.is_file():
                route.fulfill(path=asset, content_type=mimetypes.guess_type(asset.name)[0])
                return
            route.fulfill(status=404)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            try:
                page = browser.new_page()
                page.route("**/*", respond)
                page.goto("http://review.localhost/")
                expect(page.get_by_text("读不到本机数据", exact=False)).to_be_visible()
                page.get_by_role("button", name="重试读取", exact=True).click()
                expect(page.get_by_role("heading", name="可以投的岗位", exact=True)).to_be_visible()
                self.assertEqual(requests, {"index": 1, "data": 2})
            finally:
                browser.close()
