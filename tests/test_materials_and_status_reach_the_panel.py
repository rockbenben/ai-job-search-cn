# -*- coding: utf-8 -*-
"""投递材料与投递状态要真的走到面板上 —— 导出器这三支分支此前一次都没跑过。

2026-08-21 量 `tools/` 的行覆盖率发现的。`export_web_data.main()` 本身有三份集成
测试在调（`test_dup_grouping` / `test_deep_eval_wins` / `test_pipeline_counts`），
但**它们的夹具里都没有简历 PDF、没有重复的投递目录、也没有台账行**，于是 `main()`
里这三段从来没被执行：

| 分支 | 它决定什么 | 断了会怎样 |
|---|---|---|
| 把 `resume.pdf` 拷进 `web/public/pdf/` 并写 `materials.resumePdf` | 面板上那个「简历」链接 | 点开 404，而页面上仍然显示有简历 |
| 两个投递目录指向同一个职位链接时选「材料更全的那个」并**告警** | 另一个目录的材料显示不出来 | 材料无声消失——用户以为自己没做过 |
| 把台账行合并成 `job.applied` | 「已投递」的计数与每行的状态 | 投过的岗看起来像没投过 |

三支都是**无声**的：不报错、不缺页，只是少了东西。这正是这个仓库最贵的一类。

`resumePdf` 这个键在改这份测试之前，**整套测试里没有任何一条提到过它**。
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import export_web_data as ex  # noqa: E402

URL = "https://example.com/job/1"
OTHER = "https://example.com/job/2"

#: 台账表头以 `tools/tracker.py` 为准；这里只是把它抄成夹具，
#: 真要改列名以那边为权威（`test_status_spelling_is_one_way` 盯着口径）。
TRACKER = (
    "date,company,sector,role,role_type,channel,status,contact_person,"
    "fit_rating,notes,cv_file,cover_letter_file,source,outcome_reason\n"
    f"2026-08-21,示例科技,,AI 产品经理,,,applied,,,在总览页记的,,,{URL},\n"
)


def _entry(url, title):
    return {"url": url, "title": title, "company": "示例科技", "status": "ranked",
            "first_seen": "2026-08-01", "salary": "40-60k·14薪",
            "rank_score": 78, "rank_verdict": "强匹配",
            "rank_breakdown": {"技能与经验": 80, "依据": "夹具"}}


def _app_dir(base: Path, name: str, url: str, *, with_pdf: bool,
             with_outreach: bool = False) -> Path:
    d = base / name
    d.mkdir(parents=True)
    (d / "posting.md").write_text(
        f"# 职位\n\n原始链接：{url}\n\n岗位职责：略。\n", encoding="utf-8")
    if with_outreach:
        # 干净链接 + 一段能解析出来的开场白：这份岗在面板上应当算「材料就绪」
        (d / "outreach.md").write_text(
            f"# 示例\n\n职位链接：{url}\n\n## 打招呼开场白\n\n您好。\n",
            encoding="utf-8")
    if with_pdf:
        # 内容无所谓，导出器只是 `shutil.copy` 它
        (d / "resume.pdf").write_bytes(b"%PDF-1.4\n% fixture\n")
    return d


class MaterialsAndStatusReachThePanel(unittest.TestCase):

    def _export(self, *, dup: bool, pdf: bool, tracker: bool,
                outreach: bool = False, seen_url: str = URL,
                app_url: str = URL, app_name: str = "示例科技_AI产品经理"):
        """跑一次真导出，返回 (jobs, 服务端打到 stderr 的话, 输出目录)。

        `seen_url` 是职位库里的链接（可能带平台埋点参数），`app_url` 是
        `outreach.md` / `posting.md` 里记的链接。两者可以不同写法。
        """
        import contextlib
        import io

        tmp = Path(tempfile.mkdtemp())
        u = tmp / "users" / "张三"
        (u / "job_scraper").mkdir(parents=True)
        (u / "profile").mkdir(parents=True)
        (u / "profile" / "candidate.md").write_text("# 候选人\n真实内容\n",
                                                    encoding="utf-8")
        (u / "job_scraper" / "seen_jobs.json").write_text(
            json.dumps({"seen": {seen_url: _entry(seen_url, "AI 产品经理"),
                                 OTHER: _entry(OTHER, "数据产品经理")}},
                       ensure_ascii=False), encoding="utf-8")
        apps = u / "documents" / "applications"
        _app_dir(apps, app_name, app_url, with_pdf=pdf,
                 with_outreach=outreach)
        if dup:
            # 同一个链接的第二个目录：材料更少，应当被让位并**告警**
            _app_dir(apps, "示例科技_AI产品经理_旧", app_url, with_pdf=False)
        if tracker:
            (u / "job_search_tracker.csv").write_text(TRACKER, encoding="utf-8")
        (tmp / ".active_user").write_text("张三", encoding="utf-8")

        out = tmp / "web" / "public"
        saved = ex.ROOT, ex.OUT_DIR, ex.PDF_DIR
        ex.ROOT, ex.OUT_DIR, ex.PDF_DIR = tmp, out, out / "pdf"
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err):
                self.assertEqual(ex.main(show_next_step=False), 0)
            jobs = json.loads(
                (out / "data.json").read_text(encoding="utf-8"))["jobs"]
        finally:
            ex.ROOT, ex.OUT_DIR, ex.PDF_DIR = saved
        return jobs, err.getvalue(), out

    def _job(self, jobs, url=URL):
        got = next((j for j in jobs if j.get("url") == url), None)
        self.assertIsNotNone(got, f"导出的 jobs 里找不到 {url}")
        return got

    def test_the_resume_pdf_is_copied_and_linked(self):
        """面板上那个「简历」链接：文件要真拷过去，键要真写上。"""
        jobs, _, out = self._export(dup=False, pdf=True, tracker=False)
        mats = self._job(jobs).get("materials") or {}
        rel = mats.get("resumePdf")
        self.assertTrue(
            rel, "有 resume.pdf 却没写 materials.resumePdf —— 面板上点不开简历")
        self.assertTrue((out / rel).is_file(),
                        f"键写了但文件没拷过去，点开就是 404：{rel}")

    def test_no_pdf_means_no_broken_link(self):
        """反向：没有 resume.pdf 时不许凭空写一个指向不存在文件的键。"""
        jobs, _, _ = self._export(dup=False, pdf=False, tracker=False)
        mats = self._job(jobs).get("materials") or {}
        self.assertIsNone(mats.get("resumePdf"),
                          "没有简历却说有 —— 面板上会出现一个死链接")

    def test_a_tracking_query_does_not_hide_the_materials(self):
        """职位库里带平台埋点参数、材料里记的是干净链接 —— 还是同一个岗。

        51job 的搜索结果给的是
        `…/171830509.html?s=sou_sou_soulb&t=0_0&req=…`，而 `outreach.md` 记的
        是去掉查询串的链接。只按 `#` 之前原样比，材料接不回去，面板会把这个
        岗说成「还没出材料」——用户于是对着已经备好的评估重跑一次。
        """
        seen = URL + "?s=sou_sou_soulb&t=0_0&req=fixture"
        jobs, _, _ = self._export(
            dup=False, pdf=False, tracker=False,
            outreach=True, seen_url=seen, app_url=URL)
        job = self._job(jobs, seen)
        mats = job.get("materials") or {}
        self.assertEqual(job.get("url"), seen,
                         "导出时把职位库里的链接改写掉了")
        self.assertTrue(
            mats.get("greeting"),
            "同一个岗只因查询串不同就丢了材料 —— 面板会显示「还没出材料」")

    def test_a_shared_base_with_a_different_title_does_not_steal_materials(self):
        """基础 URL 唯一，不代表是同一个岗。

        51job 公司页这类链接可能挂着多个职位。材料目录若只按 URL 兜底，
        A 岗的 outreach 会被端到 B 岗；目录名里带职位名，必须核一遍。
        """
        seen = URL + "?s=sou_sou_soulb&t=0_0&req=fixture"
        jobs, _, _ = self._export(
            dup=False, pdf=False, tracker=False,
            outreach=True, seen_url=seen, app_url=URL,
            app_name="示例科技_数据产品经理")
        job = self._job(jobs, seen)
        mats = job.get("materials") or {}
        self.assertFalse(
            mats.get("greeting"),
            "只凭基础 URL 把另一个职位的话术接上了")

    def test_duplicate_dirs_keep_the_richer_one_and_say_so(self):
        """两个目录指向同一个岗时：留材料全的那个，并且**要出声**。

        不出声的话，另一个目录的材料就是无声消失——用户会以为自己没做过。

        ⚠️ **看着像和 `test_dashboard_matching.py` 重复，其实不是：那条测的是
        `build_dashboard.build_model`——一个「只有测试在调」的夹具**
        （`build_dashboard.py` 顶上那段 ⚠ 记着这件事，
        `TheHarnessLabelStaysTrue` 钉着「生产代码不许用它」）。
        **这一条测的是 `export_web_data.main()`，也就是真正跑的那条路。**
        两处各算一份计数，改一边不会让另一边红——`ready_strong` 当初读错字段
        正是这么被发现的：夹具那份错了，面板那份一直是对的。
        所以两条都要留，别当重复删掉。"""
        jobs, err, _ = self._export(dup=True, pdf=True, tracker=False)
        mats = self._job(jobs).get("materials") or {}
        self.assertTrue(mats.get("resumePdf"),
                        "选中了材料更少的那个目录，简历因此丢了")
        self.assertIn("同一职位链接", err,
                      f"重复目录被静默丢掉了，一个字都没说：{err!r}")

    def test_the_tracker_row_becomes_the_applied_block(self):
        """台账里那一行要变成 `job.applied` —— 否则投过的岗看起来像没投过。"""
        jobs, _, _ = self._export(dup=False, pdf=False, tracker=True)
        applied = self._job(jobs).get("applied")
        self.assertTrue(applied, "台账里有这一行，导出的岗上却没有 applied")
        self.assertEqual(applied.get("status"), "applied")
        self.assertEqual(applied.get("date"), "2026-08-21")

    def test_a_job_without_a_tracker_row_is_not_marked_applied(self):
        """反向：没投过的岗不许被标成投过。"""
        jobs, _, _ = self._export(dup=False, pdf=False, tracker=True)
        self.assertFalse(self._job(jobs, OTHER).get("applied"),
                         "没投过的岗被标成已投递了")


if __name__ == "__main__":
    unittest.main()
