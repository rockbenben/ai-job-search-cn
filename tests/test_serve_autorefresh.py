"""网页版面板的自动刷新：命令行改了数据，刷新页面就该看到。

## 为什么要钉住

面板读的不是 `seen_jobs.json`，而是 `export_web_data.py` 生成的派生快照
`web/public/data.json`。而改上游的是**另一批人**：`/job-apply` 深评写回分数、`/job-rank`
批量打分、`/job-outcome` 记投递、`/job-scrape` 新增职位——十几个工作流，没有一个天然知道
自己还得去刷新一份派生文件。

实测翻过车：`/job-apply` 深评把某游戏公司从粗筛 83 改成 82 写回了 `seen_jobs.json`，
面板上一直显示 83，用户问「为什么没更新」。当时 12 个会改面板数据的工作流里，
只有 `upskill.md` 提到要跑导出；`dashboard.md` 还写着「数据变化后重新运行
`/job-dashboard` 刷新快照」——可 `/job-dashboard` 跑的是 `build_dashboard.py`，
它只管单页版，压根不碰 `data.json`。照着文档做，网页版照样是旧的。

修法是把判定收到**数据出口这一个点**上：请求 `/data.json` 时比一次 mtime。
谁改的、改了什么都不必知道，也就不存在「哪个工作流忘了补一句」。
"""

import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import serve as srv  # noqa: E402


def _bump(p: Path, text: str) -> None:
    """改内容并把 mtime 明确推后 —— 别让测试依赖文件系统时间戳的分辨率。"""
    p.write_text(text, encoding="utf-8")
    t = os.stat(p).st_mtime + 10
    os.utime(p, (t, t))


class _Temp:
    """把 serve 的 ROOT 指到临时目录，并把导出替换成可观测的假货。

    这里**故意不跑真导出器**：要验的是「过期判定准不准、有没有接到出口上」，
    真导出器的行为由它自己的测试负责。假货只做两件事——记一次调用、
    把 data.json 的 mtime 推到最新（真导出器也会这么做）。
    """

    def __enter__(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = Path(self._t.name)
        u = self.tmp / "users" / "张三"
        (u / "job_scraper").mkdir(parents=True)
        (u / "documents" / "applications" / "某公司_某岗").mkdir(parents=True)
        (self.tmp / "web" / "public").mkdir(parents=True)
        (self.tmp / ".active_user").write_text("张三", encoding="utf-8")
        self.sj = u / "job_scraper" / "seen_jobs.json"
        self.sj.write_text(json.dumps({"seen": {}}), encoding="utf-8")
        self.eval_md = u / "documents" / "applications" / "某公司_某岗" / "evaluation.md"
        self.eval_md.write_text("初稿", encoding="utf-8")
        self.data = self.tmp / "web" / "public" / "data.json"

        self.calls = 0
        self._saved = (srv.ROOT, srv._export_now)
        srv.ROOT = self.tmp
        srv._export_now = self._fake_export
        self.export_raises: Exception | None = None
        self.fresh()
        return self

    def _fake_export(self) -> None:
        self.calls += 1
        if self.export_raises:
            raise self.export_raises
        # `activeUser` 必须写——真导出器写它，过期判定也看它（同一份数据是不是
        # 这个人的）。假货少写一个字段，测的就不是真实行为了。
        self.data.write_text(
            json.dumps({"activeUser": "张三", "jobs": [], "gen": self.calls},
                       ensure_ascii=False), encoding="utf-8")
        t = max(srv.sources_mtime("张三"), os.stat(self.data).st_mtime) + 10
        os.utime(self.data, (t, t))

    def fresh(self) -> None:
        """把 data.json 造成「比所有上游都新」的状态。"""
        self.data.write_text(
            json.dumps({"activeUser": "张三", "jobs": [], "gen": 0}, ensure_ascii=False),
            encoding="utf-8")
        t = srv.sources_mtime("张三") + 10
        os.utime(self.data, (t, t))
        self.calls = 0

    def __exit__(self, *a):
        srv.ROOT, srv._export_now = self._saved
        self._t.cleanup()


class StaleUpstreamTriggersReexport(unittest.TestCase):

    def test_untouched_data_is_not_reexported(self):
        """没人动过就别跑导出 —— 每次请求都重导会把面板拖慢。"""
        with _Temp() as t:
            self.assertFalse(srv.refresh_if_stale())
            self.assertEqual(t.calls, 0)

    def test_rewriting_the_deep_eval_score_is_picked_up(self):
        """这就是翻车的原样场景：深评把分数写回 seen_jobs.json。"""
        with _Temp() as t:
            _bump(t.sj, json.dumps({"seen": {"u#岗": {"rank_score": 82}}}))
            self.assertTrue(srv.refresh_if_stale(), "改了 seen_jobs.json 却没重新导出")
            self.assertEqual(t.calls, 1)
            self.assertFalse(srv.refresh_if_stale(), "导完还判过期 —— 会每次请求都重导")

    def test_editing_a_file_inside_an_application_dir_is_picked_up(self):
        """必须**递归**看投递目录。

        目录自身的 mtime 只在增删文件时变；改 `evaluation.md` 的内容不会动它。
        只看目录 mtime 的话，「深评改了结论」这种最常见的情况就会整个漏掉。
        """
        with _Temp() as t:
            _bump(t.eval_md, "改过的评估结论")
            self.assertTrue(srv.refresh_if_stale(),
                            "投递目录里的文件改了内容却没被发现（只看了目录 mtime？）")

    def test_switching_users_is_picked_up(self):
        """切用户后面板必须换一份数据，否则会显示上一个人的职位。"""
        with _Temp() as t:
            (t.tmp / "users" / "李四" / "job_scraper").mkdir(parents=True)
            _bump(t.tmp / ".active_user", "李四")
            self.assertTrue(srv.refresh_if_stale(), "切了用户还在用旧用户的快照")

    def test_missing_data_json_is_generated(self):
        """快照不存在也算过期 —— 首次启动不该要求先手动跑一次导出。"""
        with _Temp() as t:
            t.data.unlink()
            self.assertTrue(srv.refresh_if_stale())
            self.assertTrue(t.data.is_file())

    def test_deleting_the_newest_file_inside_an_application_is_picked_up(self):
        """删文件不会产生「更晚的文件 mtime」，但会更新父目录 mtime。

        `sources_mtime` 原来只遍历文件，于是删掉最新一份材料后，它算出的
        最大值反而下降，`needs_reexport` 仍认为旧 `data.json` 是新的。
        """
        with _Temp() as t:
            old = time.time() - 100
            for p in t.tmp.rglob("*"):
                if p.is_file():
                    os.utime(p, (old, old))
            os.utime(t.data, (old + 5, old + 5))
            t.eval_md.unlink()
            self.assertTrue(srv.refresh_if_stale(),
                            "删掉投递目录里的材料后，面板没有重新导出")

    def test_editing_hr_answers_is_picked_up(self):
        """`profile/hr-answers.md` 是导出器的输入，也必须在刷新判据里。"""
        with _Temp() as t:
            hr = t.tmp / "users" / "张三" / "profile" / "hr-answers.md"
            hr.parent.mkdir(parents=True)
            old = time.time() - 100
            for p in t.tmp.rglob("*"):
                if p.is_file():
                    os.utime(p, (old, old))
            os.utime(t.data, (old + 5, old + 5))
            hr.write_text("## 问题\n答案\n", encoding="utf-8")
            self.assertTrue(srv.refresh_if_stale(),
                            "改了 HR 常问答案，面板没有重新导出")


class ExportFailureDoesNotTakeThePageDown(unittest.TestCase):

    def test_failure_keeps_serving_the_old_snapshot(self):
        with _Temp() as t:
            t.export_raises = RuntimeError("导出器炸了")
            _bump(t.sj, json.dumps({"seen": {"u#岗": {}}}))
            self.assertFalse(srv.refresh_if_stale(), "导出失败却报告成功")
            self.assertTrue(t.data.is_file(), "导出失败把旧快照弄没了")

    def test_no_active_user_does_not_raise(self):
        """没有活动用户时不许把请求打断，要安静地不刷新。

        原来 `active_user()` 抛的是 `SystemExit`（`BaseException` 的子类，
        `except Exception` 接不住），这条就是为它加的。2026-08-20 改成了
        普通异常 `NoActiveUser`——理由见 `serve.py` 里那个类的说明：
        写入侧同样会撞上，而它从没补过这一支。

        断言不变：这里验的是**行为**（安静返回 False），不是异常类型。
        """
        with _Temp() as t:
            (t.tmp / ".active_user").unlink()
            self.assertFalse(srv.refresh_if_stale())


class WiredIntoTheDataEndpoint(unittest.TestCase):
    """判定写对了还不够，得真的接在 `/data.json` 上。

    逻辑齐全但没接线是本仓库反复出现的一类问题（`/job-apply` 第 6 步点名了后果、
    却只让你写上游），所以这里走一次真 HTTP，不直接调函数。
    """

    def test_get_data_json_refreshes_first(self):
        with _Temp() as t:
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
            th = threading.Thread(target=httpd.serve_forever, daemon=True)
            th.start()
            try:
                _bump(t.sj, json.dumps({"seen": {"u#岗": {"rank_score": 82}}}))
                url = f"http://127.0.0.1:{httpd.server_address[1]}/data.json"
                with urllib.request.urlopen(url, timeout=10) as r:
                    body = json.loads(r.read())
                self.assertEqual(t.calls, 1, "GET /data.json 没触发重新导出")
                self.assertEqual(body["gen"], 1, "返回的还是重导之前那份")
            finally:
                httpd.shutdown()
                httpd.server_close()


class ConcurrentRequestsSerializeTheExport(unittest.TestCase):
    """ThreadingHTTPServer 每请求一线程；两个线程同时重写 data.json 会读到半截 JSON。"""

    def test_parallel_refreshes_do_not_overlap(self):
        with _Temp() as t:
            overlap = []
            inside = threading.Event()
            real = t._fake_export

            def slow():
                if inside.is_set():
                    overlap.append(1)
                inside.set()
                try:
                    real()
                finally:
                    inside.clear()

            srv._export_now = slow
            _bump(t.sj, json.dumps({"seen": {"u#岗": {}}}))
            ths = [threading.Thread(target=srv.refresh_if_stale) for _ in range(6)]
            for x in ths:
                x.start()
            for x in ths:
                x.join()
            self.assertEqual(overlap, [], "两个线程同时在导出 —— 会写出半截 data.json")


class DashboardDocSaysTheServerRefreshesItself(unittest.TestCase):
    """数据变了要不要重跑命令，文档必须说清。

    这条改过两次，两次都是因为**打开面板的路数变了**：

    1. 最早有**两套面板**（一个纯 Python 吐 HTML、一个 React），`/job-dashboard` 只刷得动
       其中一套，文档却笼统地说「重新运行 /job-dashboard 刷新快照」。那时验的是有没有
       写「只对单页版成立」。
    2. 两套并成一套后，剩下「单文件快照」与「起服务」两条路：前者是快照、数据变了
       要重跑，后者每次请求比 mtime。那时验的是**两句都在**。
    3. 现在单文件那条也删了（它在没有服务时会把状态按钮整排藏起来，只剩一个写不回
       盘的「不投这个岗」）。只剩一条路，于是**「要重跑」那句必须消失**——留着它
       会让用户以为抓完新岗还得敲一遍命令，而实际上刷新浏览器就够了。

    所以这一条现在是双向的：既要说「自己会重导」，也**不许**再出现「重新运行
    /job-dashboard 刷新快照」那类话。
    """

    def test_the_doc_says_the_server_refreshes_and_never_asks_for_a_rerun(self):
        doc = (ROOT / "workflows" / "job-dashboard.md").read_text(encoding="utf-8")
        self.assertIn("刷新浏览器即最新", doc,
                      "没说服务会自己重导，用户会以为要手动刷数据")
        self.assertIn("data.json", doc)
        self.assertNotIn("重新运行 `/job-dashboard`", doc,
                         "还在叫人重跑命令刷快照 —— 单文件那条路已经删了，"
                         "起服务这条刷新浏览器就够")


if __name__ == "__main__":
    unittest.main()
