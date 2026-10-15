import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))
import build_dashboard as bd  # noqa: E402

OUTREACH_MD = """# 鲸涛保险公司 - AI产品经理（AIGC内容） 投递话术

- 渠道判定：HR 直招
- 生成日期：2026-07-27
- 职位链接：https://www.liepin.com/job/2.shtml

## 打招呼开场白（≤200 字，猎聘/BOSS 聊天框）

您好，看到 AI 产品经理岗位。可验证作品与真问题。

（字数：199）

## 邮件

**主题**：应聘 AI产品经理 - 张三 - 作品作者

尊敬的招聘负责人：

正文第一段。

正文第二段。

## 网申自评（纯文本）

1. 对岗位的理解
自评正文。

（字数：599）

## 本次使用的公司事实

- 某已核实事实 —— 来源：https://example-source.invalid/x
"""

EVAL_MD = """# 职位评估：鲸涛保险公司 - AI产品经理（AIGC内容）

## 硬门检查
| 门槛 | 结果 | 依据 |
|---|---|---|
| 学历与院校 | PASS | 优先非硬性 |
| 竞业限制 | PASS（基于假设值，请确认） | 假设值待确认 |

**综合得分：64/100**

## 结论：值得投
"""


def make_app_dir(base: Path) -> Path:
    app = base / "documents" / "applications" / "鲸涛保险公司_AI产品经理-AIGC内容"
    app.mkdir(parents=True)
    (app / "outreach.md").write_text(OUTREACH_MD, encoding="utf-8")
    (app / "evaluation.md").write_text(EVAL_MD, encoding="utf-8")
    (app / "resume.pdf").write_bytes(b"%PDF-1.4 fake")
    (app / "interview_prep_hr.md").write_text("prep", encoding="utf-8")
    return app


class ParseTests(unittest.TestCase):
    def test_parse_outreach_channels_and_url(self):
        o = bd.parse_outreach(OUTREACH_MD)
        self.assertEqual(o["url"], "https://www.liepin.com/job/2.shtml")
        self.assertIn("您好，看到 AI 产品经理岗位", o["greeting"])
        self.assertNotIn("字数", o["greeting"])  # 尾部字数行剥离
        self.assertEqual(o["email_subject"], "应聘 AI产品经理 - 张三 - 作品作者")
        self.assertIn("正文第二段", o["email_body"])
        self.assertIn("自评正文", o["wangshen"])
        self.assertNotIn("公司事实", o["wangshen"])  # 不越界到后续小节

    def test_parse_outreach_missing_sections(self):
        o = bd.parse_outreach("# 空\n- 职位链接：https://x.invalid/1\n")
        self.assertEqual(o["greeting"], "")
        self.assertEqual(o["email_subject"], "")

    def test_parse_evaluation(self):
        e = bd.parse_evaluation(EVAL_MD)
        self.assertEqual(e["score"], "64")
        self.assertEqual(e["verdict"], "值得投")
        self.assertTrue(any("假设值" in f for f in e["gate_flags"]))

    def test_find_applications(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            make_app_dir(tmp)
            apps = bd.find_applications(tmp / "documents" / "applications")
            self.assertEqual(len(apps), 1)
            a = apps[0]
            self.assertEqual(a["url"], "https://www.liepin.com/job/2.shtml")
            self.assertTrue(a["resume"])
            self.assertEqual(a["interview_preps"], ["interview_prep_hr.md"])
            self.assertEqual(a["evaluation"]["verdict"], "值得投")

    def test_find_applications_missing_dir(self):
        self.assertEqual(bd.find_applications(Path("Z:/no/such/dir")), [])

    def test_load_tracker_missing(self):
        self.assertEqual(bd.load_tracker(Path("Z:/no/such.csv")), [])

    def test_profile_ready(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "candidate.md"
            self.assertFalse(bd.profile_ready(p))          # 不存在
            p.write_text("[YOUR_NAME] 占位", encoding="utf-8")
            self.assertFalse(bd.profile_ready(p))          # 未填
            p.write_text("真实资料", encoding="utf-8")
            self.assertTrue(bd.profile_ready(p))

    def test_load_seen_jobs_missing_exits(self):
        with self.assertRaises(SystemExit) as cm:
            bd.load_seen_jobs(Path("Z:/no/seen_jobs.json"))
        self.assertIn("/job-scrape", str(cm.exception))

    def test_load_seen_jobs_empty_exits(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "seen_jobs.json"
            p.write_text(json.dumps({"seen": {}}), encoding="utf-8")
            with self.assertRaises(SystemExit):
                bd.load_seen_jobs(p)


TRACKER_CSV = (
    "date,company,sector,role,role_type,channel,status,contact_person,"
    "fit_rating,notes,cv_file,cover_letter_file,source\n"
    "2026-07-20,澜图科技,互联网,平台产品经理,full_time,online,interview,,"
    ",,resume.pdf,,https://www.liepin.com/job/7.shtml\n"
    "2026-07-21,鲸涛保险,保险,AI产品经理（AIGC内容）,full_time,online,applied,,"
    ",,resume.pdf,,\n"
)


def seen_fixture() -> dict:
    return {
        "j-fit": {"title": "AI产品经理", "company": "甲公司 <Best&Co>",
                  "url": "https://www.liepin.com/a/1.shtml", "status": "ranked",
                  "portal": "liepin-search", "rank_score": 70, "rank_verdict": "值得投"},
        "j-mat": {"title": "AI产品经理（AIGC内容）", "company": "鲸涛保险公司",
                  "url": "https://www.liepin.com/job/2.shtml", "status": "ranked",
                  "portal": "liepin-search", "rank_score": 64, "rank_verdict": "值得投"},
        "j-gate": {"title": "API产品经理", "company": "乙公司",
                   "url": "https://www.liepin.com/a/3.shtml", "status": "ranked",
                   "portal": "liepin-search", "rank_score": None,
                   "rank_verdict": "硬门 FAIL (学历院校)"},
        "j-low": {"title": "销售经理", "company": "丙公司",
                  "url": "https://www.liepin.com/a/4.shtml", "status": "ranked",
                  "portal": "liepin-search", "rank_score": 38, "rank_verdict": "不建议"},
        "j-new": {"title": "产品经理", "company": "丁公司",
                  "url": "https://www.liepin.com/a/5.shtml", "status": "new",
                  "portal": "liepin-search"},
        "j-exp": {"title": "过期岗", "company": "戊公司",
                  "url": "https://www.liepin.com/a/6.shtml", "status": "expired",
                  "portal": "liepin-search"},
        "j-app": {"title": "平台产品经理", "company": "澜图科技",
                  "url": "https://www.liepin.com/job/7.shtml", "status": "ranked",
                  "portal": "liepin-search", "rank_score": 67, "rank_verdict": "值得投"},
    }


class StageTests(unittest.TestCase):
    def setUp(self):
        import io
        self.tracker = list(__import__("csv").DictReader(io.StringIO(TRACKER_CSV)))
        self.seen = seen_fixture()

    def test_normalize_key(self):
        self.assertEqual(bd.normalize_key("AI 产品经理（AIGC）"), "ai产品经理aigc")

    def test_match_tracker_by_source_url(self):
        job = self.seen["j-app"]
        row = bd.match_tracker(job, job["url"], self.tracker)
        self.assertIsNotNone(row)
        self.assertEqual(row["company"], "澜图科技")

    def test_match_tracker_fuzzy_company_role(self):
        job = self.seen["j-mat"]  # tracker 行公司为「鲸涛保险」（岗位名的子串），source 为空
        row = bd.match_tracker(job, job["url"], self.tracker)
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "applied")

    def test_match_tracker_none(self):
        job = self.seen["j-fit"]
        self.assertIsNone(bd.match_tracker(job, job["url"], self.tracker))

    def test_derive_stage_priority(self):
        # 已投压过一切（包括 gate_fail 岗被手动投过的假想情形）
        self.assertEqual(bd.derive_stage(self.seen["j-gate"], None, {"status": "applied"}), "applied")
        self.assertEqual(bd.derive_stage(self.seen["j-exp"], None, None), "expired")
        self.assertEqual(bd.derive_stage(self.seen["j-gate"], None, None), "gate_fail")
        app = {"outreach": {"url": "x"}, "evaluation": None,
               "resume": True, "interview_preps": [], "dir": "d", "url": "x"}
        self.assertEqual(bd.derive_stage(self.seen["j-fit"], app, None), "materials")
        self.assertEqual(bd.derive_stage(self.seen["j-fit"], None, None), "ranked")
        self.assertEqual(bd.derive_stage(self.seen["j-low"], None, None), "low")
        self.assertEqual(bd.derive_stage(self.seen["j-new"], None, None), "unranked")

    def test_build_model_counts(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            make_app_dir(tmp)
            apps = bd.find_applications(tmp / "documents" / "applications")
        model = bd.build_model(self.seen, apps, self.tracker, True)
        c = model["counts"]
        self.assertEqual(c["scraped"], 7)
        self.assertEqual(c["ranked"], 5)      # status==ranked 的条数
        self.assertEqual(c["materials"], 1)   # 这家有 outreach，但它已投 → 仍计已生成材料
        self.assertEqual(c["applied"], 2)     # 一家 source 匹配 + 一家模糊匹配
        self.assertEqual(c["interviewing"], 2)  # 一家 status=interview + 一家有 interview_prep
        by_url = {j["url"]: j for j in model["jobs"]}
        self.assertEqual(by_url["https://www.liepin.com/job/7.shtml"]["stage"], "applied")
        self.assertTrue(by_url["https://www.liepin.com/job/2.shtml"]["interviewing"])


def make_repo(tmp: Path, *, tracker: str | None = TRACKER_CSV,
              candidate: str = "真实资料，无占位", user: str = "张三",
              extra_users=()) -> Path:
    base = tmp / "users" / user
    (base / "job_scraper").mkdir(parents=True)
    (base / "job_scraper" / "seen_jobs.json").write_text(
        json.dumps({"seen": seen_fixture()}, ensure_ascii=False), encoding="utf-8")
    make_app_dir(base)
    (base / "profile").mkdir()
    (base / "profile" / "candidate.md").write_text(candidate, encoding="utf-8")
    if tracker is not None:
        (base / "job_search_tracker.csv").write_text(tracker, encoding="utf-8")
    for u in extra_users:
        (tmp / "users" / u).mkdir(parents=True)
    (tmp / ".active_user").write_text(user, encoding="utf-8")
    return tmp


class NextStepTests(unittest.TestCase):
    def _c(self, **kw):
        base = {"scraped": 0, "ranked": 0, "materials": 0, "applied": 0, "interviewing": 0}
        base.update(kw)
        return base

    def test_priorities(self):
        self.assertEqual(bd.next_step(self._c(), False)[1], "/job-setup")
        # **零起点给脊梁那条，不是它的分解。** `AGENTS.md`「一次跑到头：只有三条命令」写着 `/job-setup → /job-auto → /job-outcome`，
        # 紧跟着一句「别把这条脊梁说成四步……多教一步的代价不是多敲一次，是让人以为不敲就会漏东西」。
        self.assertEqual(bd.next_step(self._c(scraped=0), True)[1],
                         "/job-auto")
        self.assertEqual(bd.next_step(self._c(scraped=5, ranked=0), True)[1], "/job-rank")
        cmd = bd.next_step(self._c(scraped=5, ranked=3, materials=0), True, "https://x/1")[1]
        # **这一条原来断言 `/job-apply https://x/1`（单岗），2026-10-14 改成批量入口。**
        #
        # 旧理由是「排序结果写在机器读的文件里，人能看的只有总览页，所以他得先去挑一个」——
        # 它对**单岗**成立，对这一支不成立。这一支的条件是「有可投的已评岗没材料」，
        # 而用户不知道该做什么时问的是「我手上还有什么没做完的」，答案是一批。
        # 面板叫他一个一个敲，他之所以真去敲第 3 个，恰恰是因为他不知道有批量那条路。
        #
        # `AGENTS.md`「一条引导对应一条命令」：给 `--top` / `可以考虑` / `全部`
        # 三个里挑一个让用户选，那正是引导要替他省掉的一步 —— 所以是 `全部`。
        self.assertEqual(cmd, "/job-apply 全部")
        # 材料就绪但还没投：投递本身在招聘网站上做、没有命令可跑，但**投完那一步有**。
        # 引导要一直给到「下一个能敲的命令」，不能停在「去投吧」——那正是用户反馈的
        # 问题（每个环节都要知道下一步怎么用命令行互动）。
        txt0, cmd0 = bd.next_step(self._c(scraped=5, ranked=3, materials=2, applied=0), True)
        self.assertEqual(cmd0, "/job-outcome <公司>")
        self.assertIn("投完", txt0, "没说清那条命令是投完之后才跑的")
        # 投过之后不再一律指向 /job-outcome。原来这里钉的是
        # `applied > 0 → "/job-outcome"`，而那正是 bug：`applied` 是**已记录的投递数**，
        # 不是「有一笔没记的投递」。刚跑完 /job-outcome 它还让你去跑 /job-outcome，
        # 投了 20 个全记完也一样——建议永远不推进。
        # 还有备好没投的 → 指那个；全投出去了 → 接着抓下一批
        # （2026-08-29 前这里是「等回复 / 催进度」，见 `AGENTS.md`
        # 「跟进归用户，工具不催」）。
        txt, cmd = bd.next_step(self._c(scraped=5, ranked=3, materials=2, applied=1), True)
        self.assertIn("1", txt, "没说清还剩几个材料就绪但没投")
        # 这条曾经断言「无命令」。现在给的是 `/job-outcome <公司>`——**不是** bug 回潮：
        # 防的那个死循环是「不论什么状态都只会说『去记一笔』」，而这里两个子分支
        # 说的是不同的事（还有 N 个没投 vs 都投完了该催），文案还在倒数剩余数。
        # 命令指的是「投完那 N 个之后」，文案里写明了先后。
        self.assertEqual(cmd, "/job-outcome <公司>")
        self.assertIn("投完", txt, "没写明这条命令是投完之后才跑的")
        self.assertNotEqual(
            txt,
            bd.next_step(self._c(scraped=5, ranked=3, materials=2, applied=2), True)[0],
            "两个子分支说了同一句话 —— 那才是「建议永远不推进」")
        self.assertEqual(
            bd.next_step(self._c(scraped=5, ranked=3, materials=2, applied=2), True)[1],
            "/job-auto")
        self.assertEqual(bd.next_step(self._c(scraped=5, ranked=3, materials=2, applied=1, interviewing=1), True)[1].split()[0], "/job-interview")


if __name__ == "__main__":
    unittest.main()


class NonUtf8PersonalFileTests(unittest.TestCase):
    """用户可编辑的个人文件不是 UTF-8 时，必须是一条可读的警告，不是 traceback。

    Excel 保存 .csv、记事本保存 .md 在中文 Windows 上都写 ANSI/GBK；抛栈会让整个
    /job-dashboard 挂掉，连 dashboard.html 都不生成。
    """

    def test_gbk_tracker_degrades_to_warning(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "job_search_tracker.csv"
            p.write_bytes("date,company\n2026-01-01,阿里巴巴\n".encode("gbk"))
            self.assertEqual(bd.load_tracker(p), [])

    def test_gbk_candidate_degrades_to_not_ready(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "candidate.md"
            p.write_bytes("## 候选人资料\n姓名：张三\n".encode("gbk"))
            self.assertFalse(bd.profile_ready(p))

    def test_gbk_application_dir_is_reported_not_silent(self):
        import contextlib
        import io as _io
        with tempfile.TemporaryDirectory() as td:
            apps_dir = Path(td) / "applications"
            (apps_dir / "甲公司_后端").mkdir(parents=True)
            (apps_dir / "甲公司_后端" / "outreach.md").write_bytes(
                "## 打招呼开场白\n你好\n".encode("gbk"))
            err = _io.StringIO()
            with contextlib.redirect_stderr(err):
                apps = bd.find_applications(apps_dir)
            self.assertEqual(apps, [])
            self.assertIn("跳过投递目录", err.getvalue())


class SummaryEncodingTests(unittest.TestCase):
    """摘要行的全角字符不得在 cp1252 stdout 上让进程崩掉。

    dashboard.html 在崩溃点之前就已正确写盘，所以用户拿到的是「文件生成了但命令报
    失败」，而末尾那条「哪些投递目录没上板」的警告一并丢失。
    """

    def test_full_width_summary_survives_cp1252(self):
        import os
        import subprocess
        code = ("import sys; sys.path.insert(0, r'%s')\n"
                "import build_dashboard\n"
                "print('dashboard: x  （用户：张三）')\n") % str(REPO_ROOT / "tools")
        res = subprocess.run([sys.executable, "-c", code], capture_output=True,
                             text=True, errors="replace",
                             env={**os.environ, "PYTHONIOENCODING": "cp1252"})
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertNotIn("UnicodeEncodeError", res.stderr)
