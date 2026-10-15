"""深评分必须盖过粗筛分，粗筛分必须显示成「粗筛」。

## 为什么有这个测试

`/job-rank` 给的是**粗筛分**——只读职位文本，不做公司调研、不做能力边界逐条比对。
`/job-apply` 给的是**深评分**。实测同一个岗：粗筛 76「强匹配」，深评 62「值得投」
（技能与经验只有 55，业务域要从零补）——**14 分的落差**。

但面板和总览页读的都是 `seen_jobs.json` 里那个粗筛分，于是：

- 用户看到的一直是 76「强匹配」，深评那份 62 产出后就躺在 `evaluation.md` 里没人读；
- 排序、「推荐先投」全用粗的那个数。

`apply.md` 现在要求把深评分写回 `seen_jobs`，但**光靠流程指令不够**——AI 漏一步，
用户就又看到虚高的分。所以代码这一侧也必须兜底：**有 `evaluation.md` 就以它为准**。
两道保险，任一生效都能得到正确结果。
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import build_dashboard as bd  # noqa: E402
import export_web_data as ex  # noqa: E402
from _live import is_gate_fail  # noqa: E402

EVAL_MD = """# 岗位评估 — 某岗 @ 某公司

## 四维打分

| 维度 | 权重 | 分 | 依据 |
|---|---|---|---|
| 技能与经验 | 30% | **55** | 专业能力 88 × 0.6 + 业务领域 25 × 0.4（封顶 65）+ 加分项 0/5 |

综合得分：62/100

## 结论：值得投
"""

SEEN = {
    # 键是 <url>#<职位名> 的去重键；url 字段才是匹配用的
    "https://x/1#某岗": {
        "url": "https://x/1", "title": "某岗", "company": "某公司",
        "status": "ranked", "rank_score": 76, "rank_verdict": "粗筛：强匹配",
        "salary": "4-6万", "location": "上海", "portal": "zhaopin-cdp",
    },
}


def _mk(tmp: Path, *, with_eval: bool) -> Path:
    u = tmp / "users" / "张三"
    (u / "job_scraper").mkdir(parents=True)
    (u / "job_scraper" / "seen_jobs.json").write_text(
        json.dumps({"seen": SEEN}, ensure_ascii=False), encoding="utf-8")
    (u / "profile").mkdir()
    (u / "profile" / "candidate.md").write_text("# 候选人\n真实内容\n", encoding="utf-8")
    d = u / "documents" / "applications" / "某公司_某岗"
    d.mkdir(parents=True)
    (d / "outreach.md").write_text(
        "## 打招呼开场白\n\n- 职位链接：https://x/1\n\n你好。\n", encoding="utf-8")
    if with_eval:
        (d / "evaluation.md").write_text(EVAL_MD, encoding="utf-8")
    (tmp / ".active_user").write_text("张三", encoding="utf-8")
    return u


def _export(with_eval=True):
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        _mk(tmp, with_eval=with_eval)
        out = tmp / "web" / "public"
        saved = ex.ROOT, ex.OUT_DIR, ex.PDF_DIR
        ex.ROOT, ex.OUT_DIR, ex.PDF_DIR = tmp, out, out / "pdf"
        try:
            assert ex.main() == 0
            return json.loads((out / "data.json").read_text(encoding="utf-8"))
        finally:
            ex.ROOT, ex.OUT_DIR, ex.PDF_DIR = saved


class DeepEvalOverridesTriage(unittest.TestCase):
    def test_export_prefers_evaluation_score(self):
        j = _export()["jobs"][0]
        self.assertEqual(j["score"], 62,
                         "有 evaluation.md 时必须用深评的 62，不是粗筛的 76")

    def test_export_prefers_evaluation_verdict(self):
        j = _export()["jobs"][0]
        self.assertEqual(j["verdict"], "值得投")
        self.assertNotIn("粗筛", j["verdict"], "深评结论不该再带「粗筛」前缀")

    def test_export_marks_it_as_deeply_evaluated(self):
        """用户要能一眼看出这个分是查过公司的。"""
        self.assertTrue(_export()["jobs"][0].get("evaluated"))

    def test_triage_only_job_keeps_triage_label(self):
        j = _export(with_eval=False)["jobs"][0]
        self.assertEqual(j["score"], 76)
        self.assertIn("粗筛", j["verdict"],
                      "没深评过的岗要显示成「粗筛：…」，别冒充深评结论")
        self.assertFalse(j.get("evaluated"))

    def test_dashboard_card_shows_deep_score(self):
        """Python 面板同样要用深评分——两个页面不能各说各的。"""
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            u = _mk(tmp, with_eval=True)
            apps = bd.find_applications(u / "documents" / "applications")
            model = bd.build_model(SEEN, apps, [], True, "张三", ["张三"])
            job = model["jobs"][0]
            self.assertEqual(job["score"], 62,
                             f"面板还在用粗筛分：{job['score']}")
            self.assertNotIn("粗筛", job["verdict"])


class SalaryMonthsUnknownIsDetected(unittest.TestCase):
    """「没写几薪」的提示要在真实数据上真的会触发。

    这个提示原来只在虚构演示数据里出现过——导出器根本没设这个字段，
    于是「4-6万/月 × 几薪？」这个年包歧义在页面上一个字都不提。
    """

    CASES = [
        ("4-6万", True, "月薪没写薪数 → 年包算不出来"),
        ("3.5-5万·15薪", False, "写了 15 薪"),
        ("40-60K·16薪", False, "写了 16 薪"),
        ("10-15万/年", False, "年薪，本来就是年包"),
        ("8千-1.5万", True, "月薪没写薪数"),
        ("薪资面议", False, "没有数字，不是「没写薪数」的问题"),
        ("", False, "没有薪资信息"),
    ]

    def test_detection(self):
        for salary, expect, why in self.CASES:
            with self.subTest(salary=salary):
                self.assertEqual(
                    ex.salary_months_unknown(salary), expect,
                    f"{salary!r} 应为 {expect} —— {why}")



class EvaluationParsesAllRealFormats(unittest.TestCase):
    """`parse_evaluation` 必须认得 AI 实际产出的每一种写法。

    这是同一类 bug 的**第三次**（前两次：话术标题的「渠道 N：」前缀、邮件主题的
    加粗冒号位置）。共同形状：AI 按 markdown 习惯写出多种合法变体，解析器只认一种，
    于是**一部分真实数据静默解析成空**——这里的后果是深评分读不出来，
    面板继续显示 /job-rank 的粗筛分。

    4 份真实产出里有 2 份解析不出来。三种写法都记在下面。
    """

    FORMATS = [
        # 输出模板里规定的写法
        ("**综合得分：64/100**\n\n## 结论：值得投\n", "64", "值得投"),
        # 加了「约」——正则里 `综合得分：\s*(\d+)` 直接失配
        ("**综合得分：约 62/100 —— 值得投，缺口在沟通阶段坦诚**\n", "62", "值得投"),
        # 把加权算式写出来，判词在下一行且带括注
        ("**综合 = 55×0.30 + 72×0.25 + 62×0.20 + 58×0.25 = 62 → 「值得投」**\n\n"
         "## 结论\n\n**值得投（62）**。\n", "62", "值得投"),
        # 判词与分数同段但顺序相反
        ("## 结论\n\n**强匹配**，综合得分 81/100。\n", "81", "强匹配"),
    ]

    def test_every_format_yields_score_and_verdict(self):
        for text, score, verdict in self.FORMATS:
            with self.subTest(text=text[:36]):
                ev = bd.parse_evaluation(text)
                self.assertEqual(ev["score"], score, f"分数没解析出来：{ev}")
                self.assertEqual(ev["verdict"], verdict, f"判词没解析出来：{ev}")

    def test_no_score_stays_empty_not_garbage(self):
        """真的没有分数时要返回空，不能瞎抓一个数字。"""
        ev = bd.parse_evaluation("## 结论\n\n信息不足，无法打分。JD 只有 3 行。\n")
        self.assertEqual(ev["score"], "")

    def test_all_real_evaluations_parse(self):
        """控制测试：仓库里若有真实投递目录，每一份都必须解析出分数与判词。"""
        files = sorted(ROOT.glob("users/*/documents/applications/*/evaluation.md"))
        if not files:
            self.skipTest("这个 clone 里没有真实投递目录")
        bad = []
        for f in files:
            t = f.read_text(encoding="utf-8", errors="replace")
            # 硬性条件没过的评估按框架就是不打分——那是规定的样子，不是解析失败。
            # 判据收在 `_live.is_gate_fail`（**只有一份**）：原来这里自己抄了
            # 一份，还比 `test_eval_table_layouts` 少认一种写法，两处因此
            # 对同一份文件给出不同答案。
            if is_gate_fail(t):
                continue
            ev = bd.parse_evaluation(t)
            if not ev["score"] or not ev["verdict"]:
                bad.append(f"{f.parent.name}(score={ev['score']!r},"
                           f"verdict={ev['verdict']!r})")
        self.assertFalse(bad, f"这些评估解析不出分数/判词，深评分会被静默丢弃：{bad}")

if __name__ == "__main__":
    unittest.main()


class AnnualPackageReadsMonthsFromTheString(unittest.TestCase):
    """薪数写在薪资串里时必须认，不能只看 `salaryMonths` 字段。

    CDP 渠道（BOSS / 智联 / 前程）**不填 `salaryMonths`**，薪数只存在于原始串里
    （`70-100K·18薪`）。只读字段就会当成没写薪数、按 12 薪估——
    实测把一个 151-216 万的岗算成 84-120 万，**低估约 80%**，
    而年包直接决定薪资维度那 25% 的权重。
    """

    CASES = [
        # (薪资串, salaryMonths 字段, 期望年包低值, 期望高值, 是否按12薪估)
        ("70-100K·18薪", None, 126.0, 180.0, False),
        ("40-60K·16薪", None, 64.0, 96.0, False),
        # 25k×20=500k=50万，35k×20=700k=70万。写这条测试时我先算成了 60-84 万——
        # 手算年包就是这么容易错，这一列存在的理由
        ("25-35k·20薪", 20, 50.0, 70.0, False),
        ("40-70k", None, 48.0, 84.0, True),        # 真的没写薪数
        ("3.5-5万", None, 42.0, 60.0, True),
        ("10-15万/年", None, 10.0, 15.0, False),   # 本来就是年包
        ("8千-1.5万", None, 9.6, 18.0, True),
    ]

    def test_months_from_string(self):
        for salary, field, lo, hi, assumed in self.CASES:
            with self.subTest(salary=salary):
                a = ex.annual_package(salary, field)
                self.assertIsNotNone(a, f"{salary} 应该能折算")
                self.assertAlmostEqual(a["low"], lo, places=1,
                                       msg=f"{salary} 年包下沿算错：{a}")
                self.assertAlmostEqual(a["high"], hi, places=1,
                                       msg=f"{salary} 年包上沿算错：{a}")
                self.assertEqual(a["assumed12"], assumed,
                                 f"{salary} 的「按12薪估」标记不对：{a}")

    def test_no_numbers_yields_nothing(self):
        self.assertIsNone(ex.annual_package("薪资面议", None))
        self.assertIsNone(ex.annual_package("", None))


class ZeroIsAScoreNotAnAbsence(unittest.TestCase):
    """深评给 0 分也是给过分——不许因为它是假值而回退到粗筛分。

    `resolve_score` 的分支原来是 `if score or verdict`。0 分且判词恰好没解析出来时
    整个分支被跳过，面板回退去显示**粗筛的高分**——正好绕开这个函数存在的理由
    （它就是为「面板 76、深评 62」那次栽跟头而写的）。

    真实数据里暂时没有 0 分深评（2026-08-20 查过 284 个材料目录），
    但 0 是合法分数，而这一步错的代价是把虚高的分端给用户。
    """

    ENTRY = {"rank_score": 76, "rank_verdict": "强匹配"}

    def test_zero_score_wins_over_the_store(self):
        for verdict, want_v in (("", ""), ("跳过", "跳过")):
            with self.subTest(verdict=verdict):
                got = bd.resolve_score(
                    self.ENTRY, {"evaluation": {"score": 0, "verdict": verdict}})
                self.assertEqual(got[0], 0, "深评 0 分被当成「没评过」，回退到粗筛分了")
                self.assertEqual(got[1], want_v)
                self.assertTrue(got[2], "0 分也是深评过")

    def test_truly_empty_evaluation_falls_back(self):
        """分和判词都空才算「没深评过」——那时回退是对的。"""
        for ev in ({"score": None, "verdict": ""}, {"score": "", "verdict": "  "}):
            with self.subTest(ev=ev):
                self.assertEqual(bd.resolve_score(self.ENTRY, {"evaluation": ev}),
                                 (76, "强匹配", False))

    def test_the_branch_tests_presence_not_truthiness(self):
        src = (ROOT / "tools" / "build_dashboard.py").read_text(encoding="utf-8")
        seg = src.split("def resolve_score")[1].split("\ndef ")[0]
        self.assertNotIn("if score or verdict:", seg,
                         "又改回真值判断了——0 分会被当成没评过")
        self.assertIn("has_score", seg)
