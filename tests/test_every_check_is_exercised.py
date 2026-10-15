# -*- coding: utf-8 -*-
"""每一条审计检查都要有测试**真的调用过**它 —— 只扫源码盯不住「它还响不响」。

## 实测

2026-08-31：`audit_pipeline` 里 59 条 `check_*`，按「测试里出现过 `名字(`」数，
**51 条被调用过，8 条没有**。那 8 条里 6 条在真语料上有输出（至少活着），
另外 **2 条永远是空的**：

    check_no_jd_but_sellable      没读 JD 却给了可投档位
    check_source_families         判词来源冒出新族

空可能是「语料干净」，也可能是「检查坏了」—— 而**一条永远绿的检查等于没有检查**，
这句话本仓库已经写过好几次。当天各造一个违规喂进去，两条都响了：语料真的干净。
本文件把那两条的对照用例固定下来。

## 其余 6 条记成明账，不许再涨

它们在真语料上有输出，所以「活着」这一点是看得见的；但没有任何东西钉住
「哪天它不响了会被发现」。棘轮的意思是：欠账就这几笔，新加的检查必须配测试。
"""
import ast
import pathlib
import re
import sys
import tempfile
import unittest
import unittest.mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import audit_pipeline as ap  # noqa: E402

#: 造样例用的换行。写成常量是因为这份文件由补丁脚本改过。
NL = chr(10)

#: 还没有测试调用过的检查。**这张表只许变短 —— 2026-08-31 已经清空。**
#:
#: 开出来时是 8 笔（其中 2 笔当天就补了对照，另 6 笔记成明账）。
#: 每一条都在真语料上有输出，所以它们至少是活着的；缺的是
#: 「哪天不响了会被发现」。
#:
#: **空表不等于这条守卫没用了。** 它现在的作用是一道闸门：
#: 新加一条检查而不配测试，`test_no_new_uncovered_check` 当场红。
UNCOVERED: dict = {}


def _checks() -> list:
    src = (ROOT / "tools" / "audit_pipeline.py").read_text(encoding="utf-8")
    return sorted(n.name for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef) and n.name.startswith("check_"))


def _called_in_tests() -> set:
    # **本文件也算数。** 第一版把自己排除在外（怕「自我满足」），结果是
    # 下面那两条对照用例明明补上了覆盖，棘轮却仍报它们没人调 ——
    # 而防自我满足的不是「排除自己」，是「调用时要喂一个违规进去」，
    # 那件事只有读的人能保证，排除自己拦不住。
    body = "\n".join(p.read_text(encoding="utf-8")
                     for p in (ROOT / "tests").glob("*.py"))
    return {c for c in _checks() if re.search(rf"\b{c}\s*\(", body)}


class TheRatchetOnlyGoesDown(unittest.TestCase):

    def test_no_new_uncovered_check(self):
        gap = set(_checks()) - _called_in_tests() - set(UNCOVERED)
        self.assertEqual(
            sorted(gap), [],
            "这几条检查没有任何测试调用过 —— 它哪天返回空，报告只会看起来很干净："
            + "、".join(sorted(gap))
            + "。给它造一个违规喂进去（模板见本文件下面两条）")

    def test_the_debt_list_does_not_rot(self):
        """表里列了、实际已经补上测试的，要清掉。"""
        done = set(UNCOVERED) & _called_in_tests()
        self.assertEqual(sorted(done), [],
                         "这几条已经有测试调用了，从 UNCOVERED 里删掉："
                         + "、".join(sorted(done)))

    def test_the_debt_is_real(self):
        """表里的名字必须真的是检查 —— 打错字会变成一条静默豁免。"""
        unknown = sorted(set(UNCOVERED) - set(_checks()))
        self.assertEqual(unknown, [], "UNCOVERED 里有不存在的名字：" + str(unknown))


class TheTwoSilentOnesReallyFire(unittest.TestCase):
    """这两条在真语料上恒为空 —— 没有对照用例就分不清「干净」和「坏了」。"""

    def test_an_unknown_source_family_is_reported(self):
        out = ap.check_source_families(
            {"1": {"url": "https://x/1", "rank_breakdown": {"来源": "凭感觉猜的"}}})
        self.assertTrue(out, "来源冒出新族，一个字都没报")
        self.assertIn("凭感觉猜的", out[0][2])

    def test_a_known_source_family_is_clean(self):
        self.assertEqual(ap.check_source_families(
            {"1": {"url": "https://x/1",
                   "rank_breakdown": {"来源": "粗筛（读过 JD 正文）"}}}), [])

    def test_a_sellable_band_without_a_jd_is_reported(self):
        seen = {"1": {"url": "https://x/1", "title": "岗", "status": "ranked",
                      "rank_verdict": "可以考虑",
                      "rank_breakdown": {"来源": "粗筛（未抓 JD）"}}}
        with tempfile.TemporaryDirectory() as d:
            tmp = pathlib.Path(d)
            (tmp / "users" / "u" / "job_scraper" / "details").mkdir(parents=True)
            with unittest.mock.patch.object(ap, "ROOT", tmp), \
                    unittest.mock.patch.object(ap._cli, "pick_user",
                                               lambda *a, **k: "u"):
                out = ap.check_no_jd_but_sellable(seen, {})
        self.assertTrue(out, "没读 JD 却给了可投档位，一个字都没报")
        self.assertIn("没读 JD", out[0][1])

    def test_having_read_the_jd_is_clean(self):
        """来源写着读过 JD 的不该被报 —— 收窄错了会把合规的一起报。"""
        seen = {"1": {"url": "https://x/1", "title": "岗", "status": "ranked",
                      "rank_verdict": "可以考虑",
                      "rank_breakdown": {"来源": "粗筛（读过 JD 正文）"}}}
        with tempfile.TemporaryDirectory() as d:
            tmp = pathlib.Path(d)
            (tmp / "users" / "u" / "job_scraper" / "details").mkdir(parents=True)
            with unittest.mock.patch.object(ap, "ROOT", tmp), \
                    unittest.mock.patch.object(ap._cli, "pick_user",
                                               lambda *a, **k: "u"):
                self.assertEqual(ap.check_no_jd_but_sellable(seen, {}), [])


class TheSameQuestionOnManyJobsIsReported(unittest.TestCase):
    """开场白结尾那个问题，在几个岗上是同一句 —— 那就不是关于某一个岗的。

    这条在**清干净之后的**真语料上恒为空（2026-09-02 清完是 0），
    所以必须有对照用例，否则「干净」和「坏了」长得一模一样 ——
    这一课当天刚付过学费：新加的两条正则写窄了，检查器报 0，
    而 24 份还挂在盘上（见 `_cli.greeting_problems` 的说明里「当天的 0 份是假的」那段）。
    """

    def _apps(self, d, files):
        tmp = pathlib.Path(d)
        apps = tmp / "users" / "u" / "documents" / "applications"
        for name, greeting in files.items():
            (apps / name).mkdir(parents=True)
            (apps / name / "outreach.md").write_text(
                "# t\n\n## 打招呼开场白\n\n" + greeting + "\n", encoding="utf-8")
        return tmp

    def _run(self, files):
        with tempfile.TemporaryDirectory() as d:
            tmp = self._apps(d, files)
            with unittest.mock.patch.object(ap, "ROOT", tmp), \
                    unittest.mock.patch.object(ap._cli, "pick_user",
                                               lambda *a, **k: "u"):
                return ap.check_greeting_questions_are_about_this_job({}, {})

    def test_the_same_question_on_two_jobs_is_reported(self):
        q = "您好，我做过很多。想了解这个岗主要服务哪几类团队？"
        out = self._run({"A公司_岗": q, "B公司_岗": q})
        self.assertTrue(out, "同一句问话问了两家，一个字都没报")
        self.assertIn("同一句", out[0][2])

    def test_the_company_name_between_does_not_hide_it(self):
        """**骨架要去掉数字**，不然「N 个人」这类差异会把同一句拆成两句。"""
        out = self._run({"A公司_岗": "您好，我做过很多。想问下团队现在有 5 个人吗？",
                         "B公司_岗": "您好，我做过很多。想问下团队现在有 20 个人吗？"})
        self.assertTrue(out, "只差一个数字，就当成两句不同的问话了")

    def test_different_questions_are_clean(self):
        """收窄错了会把正常的一起报 —— 每个岗问自己的事，一条都不该报。"""
        self.assertEqual(self._run({
            "A公司_岗": "您好，我做过很多。想问下 SRS 是这个岗自己写吗？",
            "B公司_岗": "您好，我做过很多。想问下租户计费是核心职责吗？"}), [])

    def test_no_question_at_all_is_clean(self):
        """默认结尾本来就不带问题（06「结尾怎么收」），那种一条都不该报。"""
        self.assertEqual(self._run({
            "A公司_岗": "您好，我做过很多。详细的经历在简历里，期待您的回复。",
            "B公司_岗": "您好，我做过很多。详细的经历在简历里，期待您的回复。"}), [])


class ADeductionOnlyInProseIsNotADeduction(unittest.TestCase):
    """散文里说「已扣 5 分」，就得有一个字段真的扣了。

    实测 2026-08-29：**33 个岗**写了减分而一个字段都没扣，其中 5 个结论因此
    虚高一整档（含一个从「值得投」虚高上来的，差点按可投出了整套材料）。

    这条为什么单独要有：`check_composite_matches_its_dims` 比的是
    「综合分 vs 四维加权和」，而减分压根没扣时两边正好相等 ——
    **它看到的是一个完美自洽的错误**。同一件事有三个住址（散文、字段、分数），
    而那条检查只去了其中两个。
    """

    def test_a_claimed_deduction_without_a_field_is_reported(self):
        seen = {"1": {"title": "岗", "rank_score": 60,
                      "rank_breakdown": {"依据": "作 −5 减分（已扣，60→55）"}}}
        out = ap.check_the_deduction_was_actually_deducted(seen, {})
        self.assertTrue(out, "说扣了分却没字段真的扣，一个字都没报")
        self.assertIn("说扣了分", out[0][1])

    def test_an_actual_adjustment_field_is_clean(self):
        seen = {"1": {"title": "岗", "rank_score": 55,
                      "rank_breakdown": {"专业减分": -5,
                                         "依据": "作 −5 减分（已扣，60→55）"}}}
        self.assertEqual(
            ap.check_the_deduction_was_actually_deducted(seen, {}), [])

    def test_saying_it_does_not_deduct_is_not_a_claim(self):
        """**这是它自己记着的那个假阳性。**

        一条依据写的是「专业写的是『优先』不减分」，而 60 个字以外的
        「3-5 年」里那个 -5 把它匹配上了。判据现在要求两者挨着（14 字内）
        并排掉「不减分」—— 散文判据只要放宽一格，报出来的就不是事实而是噪音。
        """
        seen = {"1": {"title": "岗", "rank_score": 60,
                      "rank_breakdown": {
                          # ⚠️ 中间**不能用分号**：字符类本来就不跨 `；`，
                          # 那样这条用例根本考不到 14 字那道判据（第一版就是
                          # 这么写的，把判据放宽到 60 字它照样绿）。
                          # 逗号相连、且距离 17 字 > 14，才真的在考它。
                          "依据": "专业写的是「优先」不减分，这一条不影响打分，"
                                  "任职要求写的是 3-5 年"}}}
        self.assertEqual(
            ap.check_the_deduction_was_actually_deducted(seen, {}), [])


class AnUnclosedQuoteMeansItWasCutOff(unittest.TestCase):
    """引号开了没关，几乎只有一种成因：这句话被截断了。

    判据不按标点结尾判 —— 中文列表里省略句末问号是正常写法，那样报 196 条、
    占 44%，全是噪音（实测 2026-08-29）。
    """

    def _run(self, jobs):
        import json
        with tempfile.TemporaryDirectory() as d:
            tmp = pathlib.Path(d)
            (tmp / "web" / "public").mkdir(parents=True)
            (tmp / "web" / "public" / "data.json").write_text(
                json.dumps({"activeUser": "u", "jobs": jobs},
                           ensure_ascii=False), encoding="utf-8")
            with unittest.mock.patch.object(ap, "ROOT", tmp), \
                    unittest.mock.patch.object(ap._cli, "pick_user",
                                               lambda *a, **k: "u"):
                return ap.check_panel_text_is_not_cut_off({}, {})

    def test_an_unclosed_quote_is_reported(self):
        out = self._run([{"askBefore": ["职责 1 是「定义 AI 参与开发的"]}])
        self.assertTrue(out, "引号开了没关，一个字都没报")
        self.assertIn("断在半截", out[0][1])

    def test_a_balanced_quote_is_clean(self):
        self.assertEqual(
            self._run([{"askBefore": ["职责 1 是「定义 AI 参与开发的边界」"]}]), [])

    def test_a_missing_question_mark_is_not_a_cutoff(self):
        """中文列表里省略句末问号是正常写法 —— 按标点判会报 196 条噪音。"""
        self.assertEqual(
            self._run([{"askBefore": ["研发节奏是怎样的，有没有大小周"]}]), [])

    def test_the_job_title_is_left_alone(self):
        """职位名是抓回来的原文，平台自己就不配对。"""
        self.assertEqual(
            self._run([{"title": "AI 产品经理（「Agent 方向"}]), [])


class TheGateColumnAlsoUsesTheSevenNames(unittest.TestCase):
    """门名有两个住址：判词里那串，和深评表的第一列 —— **面板渲染的是后者**。

    实测 2026-08-30：把判词里那 29 条改成正规名之后，管判词那条报 0，
    而面板上仍有 **72 行**自造名（专业 62、地点 54、英语 8…）——
    检查说全清了，用户看到的还是那些名字。所以按数据来源拆成两条。
    """

    @staticmethod
    def _table(name):
        """深评里那张硬性条件表的最小形态。"""
        return NL.join(["## 硬性条件", "",
                        "| 门 | 结果 | 依据 |", "|---|---|---|",
                        "| " + name + " | PASS | 卡片字段 |", ""])

    def _run(self, table):
        with tempfile.TemporaryDirectory() as d:
            tmp = pathlib.Path(d)
            ev = tmp / "users" / "u" / "documents" / "applications" / "一个岗"
            ev.mkdir(parents=True)
            (ev / "evaluation.md").write_text(table, encoding="utf-8")
            with unittest.mock.patch.object(ap, "ROOT", tmp), \
                    unittest.mock.patch.object(ap._cli, "pick_user",
                                               lambda *a, **k: "u"):
                return ap.check_gate_table_names_are_one_of_the_seven({}, {})

    def test_a_made_up_gate_name_is_reported(self):
        out = self._run(self._table("专业"))
        self.assertTrue(out, "表里写了七道之外的门名，一个字都没报")
        self.assertIn("门名", out[0][1])

    def test_a_canonical_name_is_clean(self):
        canon = next(iter(ap._cli.GATES))
        self.assertEqual(self._run(self._table(canon)), [],
                         "把正规名 " + canon + " 报成了自造名")

    def test_the_message_says_the_panel_renders_this_one(self):
        """不写这句，读的人不知道它和判词那条为什么要分开报。"""
        out = self._run(self._table("专业"))
        self.assertIn("面板渲染的正是这张表", out[0][2])


class ASnapshotWithoutTheJdSaysSo(unittest.TestCase):
    """`posting.md` 要么自带 JD 正文，要么**坦白说没取到** —— 不许两头都不沾。"""

    def _run(self, text):
        with tempfile.TemporaryDirectory() as d:
            tmp = pathlib.Path(d)
            ev = tmp / "users" / "u" / "documents" / "applications" / "一个岗"
            ev.mkdir(parents=True)
            (ev / "posting.md").write_text(text, encoding="utf-8")
            with unittest.mock.patch.object(ap, "ROOT", tmp), \
                    unittest.mock.patch.object(ap._cli, "pick_user",
                                               lambda *a, **k: "u"):
                return ap.check_posting_snapshots_are_self_contained({}, {})

    def test_a_snapshot_with_no_body_and_no_excuse_is_reported(self):
        out = self._run("# 岗" + NL + NL + "原始链接：https://x/1.html" + NL)
        self.assertTrue(out, "既没正文也没坦白，一个字都没报")

    def test_a_snapshot_carrying_the_body_is_clean(self):
        body = "职责与要求。" * 40          # >= 200 字
        self.assertEqual(
            self._run("# 岗" + NL + NL + "## JD 原文" + NL + NL + body + NL), [])

    def test_saying_it_could_not_be_fetched_is_accepted(self):
        """坦白没有是可接受的 —— 那是「没取到」，不是「假装取到了」。"""
        self.assertEqual(
            self._run("# 岗" + NL + NL + "本轮没取到 JD 正文。" + NL), [])


class AFieldTheDocSaysIsAvailable(unittest.TestCase):
    """`cdp-portals.md` 的字段表说「能取到」，而实测落库覆盖率是 0%。

    这条盯的是**差距会不会合上**：抓取器开始取它，它就自己消失。

    ⚠️ **要两家以上才报** —— 一家为 0 可能是那家页面上真没有，
    两家同时为 0 才说明是我们没取。
    """

    @staticmethod
    def _seen(n_per_site, with_field=()):
        out, i = {}, 0
        for portal in ("liepin-search", "boss-browser", "zhaopin-browser"):
            for _ in range(n_per_site):
                i += 1
                e = {"url": "https://x/" + str(i), "portal": portal}
                if portal in with_field:
                    e["recruiter"] = "某某 · 猎头顾问"
                out[str(i)] = e
        return out

    def test_two_dead_sites_are_reported(self):
        out = ap.check_doc_claims_vs_reality(self._seen(25))
        self.assertIn("字段：能取到，但一直没取", [k for _l, k, _m in out],
                      "两家以上覆盖率 0%，一个字都没报")

    def test_a_thin_corpus_is_not_evidence(self):
        """每家不到 20 个岗就不算数 —— 样本太小时 0% 说明不了任何事。"""
        self.assertEqual(ap.check_doc_claims_vs_reality(self._seen(3)), [])

    def test_a_site_that_carries_it_is_not_listed(self):
        """有值的那家不算「没取」—— 收窄错了会把已经接好的报成断的。"""
        out = ap.check_doc_claims_vs_reality(
            self._seen(25, with_field=("liepin-search",)))
        # ⚠️ 这条检查一次报**两个字段**（`recruiter` 与 `benefits`）。
        # 样例只给 `recruiter` 赋了值，所以 `benefits` 那一行报猎聘是**对的** ——
        # 第一版把两行合起来断言，当场自己把自己判红。只看要考的那一行。
        msg = " ".join(m for _l, _k, m in out if "`recruiter`" in m)
        self.assertTrue(msg, "recruiter 那一行没报出来")
        self.assertNotIn("猎聘", msg, "猎聘那家有值，却被报成一直没取")


class ClaimingToHaveReadTheJdMeansItIsStored(unittest.TestCase):
    """判词写着读过 JD 正文，详情库里就得有那条正文。

    浏览器读来的正文只活在那一次访问里 —— 不落库的话，出材料时要再开一次
    页面、再花一次额度。

    ⚠️ **只看自称读过的那批。** 判词写着「粗筛（未抓 JD）」的本来就没读，
    把它们算进来会让这个数永远下不去，而一个永远红的自检会被当噪音略过。
    """

    def _run(self, seen):
        with tempfile.TemporaryDirectory() as d:
            tmp = pathlib.Path(d)
            (tmp / "users" / "u" / "job_scraper" / "details").mkdir(parents=True)
            with unittest.mock.patch.object(ap, "ROOT", tmp), \
                    unittest.mock.patch.object(ap._cli, "pick_user",
                                               lambda *a, **k: "u"):
                return ap.check_jd_read_but_not_stored(seen, {})

    def test_a_claim_without_a_stored_body_is_reported(self):
        out = self._run({"1": {"url": "https://x/1", "title": "岗",
                               "portal": "boss-browser",
                               "rank_date": "2026-08-31",
                               "rank_breakdown": {"来源": "粗筛（读过 JD 正文）"}}})
        self.assertTrue(out, "自称读过而库里没有，一个字都没报")
        self.assertIn("读了 JD 没落库", out[0][1])

    def test_not_claiming_to_have_read_is_out_of_scope(self):
        """没自称读过的不许算进来 —— 那会让这个数永远下不去。"""
        self.assertEqual(
            self._run({"1": {"url": "https://x/1", "title": "岗",
                             "portal": "boss-browser",
                             "rank_breakdown": {"来源": "粗筛（未抓 JD）"}}}), [])

    def test_a_deep_eval_source_also_counts_as_claiming(self):
        """来源以「深评」开头的同样是自称读过。"""
        self.assertTrue(self._run(
            {"1": {"url": "https://x/1", "title": "岗",
                   "portal": "liepin-search", "rank_date": "2026-08-31",
                   "rank_breakdown": {"来源": "深评（writeback.py 回写）"}}}))


if __name__ == "__main__":
    unittest.main()
