# -*- coding: utf-8 -*-
"""`jd_store --merge` 报「503 处两边不一致」，其中 500 处根本不是矛盾。

这份冲突清单**就是**「可能按旧值做过判定」的那批岗 —— `merge_into_seen`
从不覆盖已有值，所以任何判过的岗读到的一定是列表页那个旧值。它是这条命令
最有用的产出，而 `/job-rank` 的 Step 0 每一轮都会跑到它。

实测活动用户 2026-08-23：

    location  500   ← `上海` → `上海徐汇万科`，同一个地方的不同精度
    salary      3   ← 真的对不上，而且都是详情页更高

`15-20k` / `30-40k` 差一倍。**那一条的判词是「粗筛：跳过」** ——
列表页 15-20k 按最乐观 16 薪折 32 万、低于 42 万底线所以被扔了，
而盘上存着的详情写的是 30-40k（64 万）。一个岗按一份自己盘上已有更好版本的
数字被丢掉，而提示它的那行字被 500 行噪音埋着（样本只印 8 行）。

## 为什么 location 特殊

它在框架里只服务**一道 Pass/Fail 的门**（跨城搬迁，`04-job-evaluation.md`）。
同城内写得多细都不改判定，换了城市才改。所以同城 = 更精确，不同城 = 真矛盾。

## 判过没有：不看 `status`，看有没有判词

合并从不覆盖，判过的岗读到的**一定**是旧值 —— 与它现在处在哪个状态无关。
按 `status in (...)` 判会漏掉状态被后续流程改过的那些。
"""
import io
import json
import re
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import jd_store as st  # noqa: E402

SRC = (ROOT / "tools" / "jd_store.py").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(s.split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


class AMorePreciseAddressIsNotAConflict(unittest.TestCase):
    def test_a_bare_city_versus_a_full_address(self):
        self.assertTrue(st.is_refinement("location", "上海", "上海徐汇万科"))

    def test_a_district_versus_a_building(self):
        self.assertTrue(st.is_refinement(
            "location", "上海-黄浦区", "上海-黄浦区大上海时代广场"))

    def test_separator_styles_do_not_matter(self):
        """列表页爱用 `·`，详情页爱用 `-` —— 不抹平的话同一个地方算两个。"""
        self.assertTrue(st.is_refinement(
            "location", "上海·徐汇·虹梅路", "上海-徐汇区H88越虹广场B座11F"))

    def test_a_different_city_is_a_real_conflict(self):
        """换城市要改跨城搬迁那道门的判定 —— 这个必须报出来。"""
        self.assertFalse(st.is_refinement("location", "上海-徐汇区", "北京-朝阳区"))

    def test_two_chars_is_enough_to_tell_cities_apart(self):
        for a, b in (("上海", "上饶"), ("南京", "南通"), ("南昌", "南京"),
                     ("哈尔滨", "哈密")):
            with self.subTest(a=a, b=b):
                self.assertFalse(st.is_refinement("location", a, b))

    def test_the_shorthand_only_applies_to_location(self):
        """别的字段没有「同城」这层语义，首二字相同不算一回事。"""
        self.assertFalse(st.is_refinement("salary", "15-20k", "15万年薪"))

    def test_a_longer_salary_string_is_still_the_same_offer(self):
        self.assertTrue(st.is_refinement("salary", "30-40k", "30-40k·15薪"))

    def test_a_different_salary_is_a_real_conflict(self):
        self.assertFalse(st.is_refinement("salary", "15-20k", "30-40k"))

    def test_an_empty_side_is_never_a_refinement(self):
        """空值走的是「补空缺」那条路，根本到不了这里；到了也别吞掉。"""
        self.assertFalse(st.is_refinement("location", "", "上海"))
        self.assertFalse(st.is_refinement("location", "上海", ""))

    def test_the_reason_is_at_the_code(self):
        i = SRC.index("def is_refinement(")
        seg = flat(SRC[i:SRC.index("    a, b = old.translate", i)])
        self.assertRegex(seg, r"其中 \*\*500 处是 location\*\*")
        self.assertRegex(seg, r"真正互相矛盾的只有 \*\*3 条薪资\*\*")
        self.assertIn("2026-08-23", seg)

    def test_it_says_why_location_gets_the_city_rule(self):
        i = SRC.index("def is_refinement(")
        seg = flat(SRC[i:SRC.index("    a, b = old.translate", i)])
        self.assertRegex(seg, r"它在框架里只服务\*\*一道 Pass/Fail 的门\*\*")
        self.assertRegex(seg, r"同城 = 更精确，不同城 = 真矛盾")

    def test_it_says_which_way_to_err(self):
        i = SRC.index("def is_refinement(")
        seg = flat(SRC[i:SRC.index("    a, b = old.translate", i)])
        self.assertRegex(seg, r"宁可多报不可漏报")


class TheTwoKindsAreCountedApart(unittest.TestCase):
    """`merge_into_seen` 的返回里两类分开，调用方才能分开报。"""

    def _run(self, entry: dict, detail: dict) -> dict:
        seen = {"k": dict(entry)}
        real_load, real_seen = st.load, st._seen_stamped
        st.load = lambda u, url, title: detail
        st._seen_stamped = lambda u: (Path("nowhere.json"), {"seen": seen}, None)
        try:
            return st.merge_into_seen("谁", apply=False)
        finally:
            st.load, st._seen_stamped = real_load, real_seen

    def test_a_refinement_lands_in_refined(self):
        r = self._run({"url": "u", "title": "t", "location": "上海"},
                      {"location": "上海徐汇万科"})
        self.assertEqual(r["refined"], {"location": 1})
        self.assertEqual(r["conflicts"], [])

    def test_a_real_conflict_lands_in_conflicts(self):
        r = self._run({"url": "u", "title": "t", "salary": "15-20k"},
                      {"salary": "30-40k"})
        self.assertEqual(r["refined"], {})
        self.assertEqual(len(r["conflicts"]), 1)
        self.assertEqual(r["conflicts"][0]["field"], "salary")

    def test_the_conflict_carries_both_values_and_the_url(self):
        r = self._run({"url": "https://x/1", "title": "某岗", "salary": "15-20k"},
                      {"salary": "30-40k"})
        c = r["conflicts"][0]
        self.assertEqual((c["old"], c["new"]), ("15-20k", "30-40k"))
        self.assertEqual(c["url"], "https://x/1")
        self.assertEqual(c["title"], "某岗")

    def test_filling_a_blank_is_still_not_a_conflict(self):
        """「只补空缺」那条路不能被这次改动带坏。"""
        r = self._run({"url": "u", "title": "t"}, {"salary": "30-40k"})
        self.assertEqual(r["filled"], {"salary": 1})
        self.assertEqual(r["conflicts"], [])
        self.assertEqual(r["entries"], 1)

    def test_it_still_does_not_overwrite(self):
        seen = {"k": {"url": "u", "title": "t", "salary": "15-20k"}}
        real_load, real_seen = st.load, st._seen_stamped
        st.load = lambda u, url, title: {"salary": "30-40k"}
        st._seen_stamped = lambda u: (Path("nowhere.json"), {"seen": seen}, None)
        try:
            st.merge_into_seen("谁", apply=False)
        finally:
            st.load, st._seen_stamped = real_load, real_seen
        self.assertEqual(seen["k"]["salary"], "15-20k", "把打过分的值改掉了")


class ItSaysWhetherADecisionRodeOnTheOldValue(unittest.TestCase):
    def _judged(self, entry_extra: dict) -> bool:
        seen = {"k": {"url": "u", "title": "t", "salary": "15-20k",
                      **entry_extra}}
        real_load, real_seen = st.load, st._seen_stamped
        st.load = lambda u, url, title: {"salary": "30-40k"}
        st._seen_stamped = lambda u: (Path("nowhere.json"), {"seen": seen}, None)
        try:
            r = st.merge_into_seen("谁", apply=False)
        finally:
            st.load, st._seen_stamped = real_load, real_seen
        return r["conflicts"][0]["judged"]

    def test_a_rank_verdict_counts(self):
        self.assertTrue(self._judged({"rank_verdict": "粗筛：跳过"}))

    def test_a_previous_verdict_counts(self):
        """判过又被打回待评的，读到的照样是旧值。"""
        self.assertTrue(self._judged({"prev_verdict": "硬门 FAIL (工作年限)"}))

    def test_never_judged_is_false(self):
        self.assertFalse(self._judged({"status": "new"}))

    def test_a_status_code_alone_is_not_the_test(self):
        """按 `status` 判会把没判过的也算进去 —— 判据必须是「有没有判词」。"""
        self.assertFalse(self._judged({"status": "ranked"}))

    def test_the_reason_is_at_the_code(self):
        i = SRC.index('"judged": bool(')
        seg = flat(SRC[max(0, i - 700):i].replace("#", " "))
        self.assertRegex(seg, r"判据不是 `status`，是「有没有判词」")
        self.assertRegex(seg, r"任何判过的岗读到的\*\*一定\*\*是列表页那个旧值")


class TheReportSeparatesThemAndNamesAnAction(unittest.TestCase):
    def _print(self, r: dict) -> str:
        """跑真的 `main()`，只把它的两个外部依赖挡掉。

        **不传真用户名。** `pick_user` 会去 `users/` 下核存在性，
        测试一挑名字就得跟着仓库里的夹具走；`status()` 还要读那个人的
        `seen_jobs.json`。两个都跟这次改动无关，挡掉。
        """
        saved = (st.merge_into_seen, st._cli.pick_user, st.status)
        st.merge_into_seen = lambda u, a: r
        st._cli.pick_user = lambda name, root=None: "某人"
        st.status = lambda u: {"have": 0, "total": 0,
                               "new_total": 0, "new_have": 0}
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                st.main(["--merge"])
        except SystemExit:
            pass
        finally:
            st.merge_into_seen, st._cli.pick_user, st.status = saved
        return buf.getvalue()

    BOTH = {"entries": 0, "filled": {}, "refined": {"location": 500},
            "conflicts": [{"title": "某岗", "field": "salary", "old": "15-20k",
                           "new": "30-40k", "judged": True,
                           "url": "https://x/1"}]}

    def test_refinements_are_reported_as_not_a_problem(self):
        out = self._print(self.BOTH)
        self.assertIn("500 处只是详情页写得更细", out)
        self.assertIn("不用管", out)

    def test_the_real_conflicts_get_their_own_count(self):
        out = self._print(self.BOTH)
        self.assertIn("⚠ 1 处两边真的对不上", out,
                      "两类又被合在一起数了")

    def test_the_two_counts_are_not_added_together(self):
        """501 是原来那个把噪音算进去的数。"""
        self.assertNotIn("501 处", self._print(self.BOTH))

    def test_it_still_says_nothing_was_overwritten(self):
        self.assertIn("已有值原样保留、没有改写", self._print(self.BOTH))

    def test_it_names_a_command_that_can_be_typed(self):
        out = self._print(self.BOTH)
        self.assertIn("/job-apply https://x/1", out,
                      "只报不给动作，看见了也只能干看着")

    def test_it_says_why_that_command(self):
        self.assertIn("深评直接读 JD 正文里的数", self._print(self.BOTH))

    def test_an_unjudged_conflict_gets_no_action_line(self):
        """还没判过的岗没有要复核的判定 —— 别催人去跑。"""
        r = dict(self.BOTH)
        r["conflicts"] = [{**self.BOTH["conflicts"][0], "judged": False}]
        out = self._print(r)
        self.assertIn("⚠ 1 处", out)
        self.assertNotIn("已经按旧值判过了", out)

    def test_no_refinements_means_no_line_about_them(self):
        r = dict(self.BOTH, refined={})
        self.assertNotIn("写得更细", self._print(r))

    def test_no_english_status_code_reaches_the_terminal(self):
        """`ranked` / `skipped` 是内部码，AGENTS.md 明禁印给用户看。"""
        out = self._print(self.BOTH)
        for code in ("ranked", "skipped", "gate_fail", "new"):
            with self.subTest(code=code):
                self.assertNotRegex(out, rf"\b{code}\b")

    def test_the_reason_is_at_the_print_site(self):
        i = SRC.index("两边真的对不上")
        seg = flat(SRC[max(0, i - 500):i].replace("#", " "))
        self.assertRegex(seg, r"原来两类合在一起报「503 处不一致」")


class TheSurroundingContractIsIntact(unittest.TestCase):
    def test_the_no_overwrite_rule_is_still_documented(self):
        i = SRC.index("def merge_into_seen(")
        seg = flat(SRC[i:SRC.index('    path, data, stamp = _seen_stamped(user)', i)])
        self.assertIn("**只补空缺**：已有值一律保留", seg)
        self.assertRegex(seg, r"会让「分数为什么变了」无从追查")

    def test_the_docstring_carries_the_measurement(self):
        i = SRC.index("def merge_into_seen(")
        seg = flat(SRC[i:SRC.index('    path, data, stamp = _seen_stamped(user)', i)])
        self.assertRegex(seg, r"报的是「\*\*503 处\*\*两边不一致」")
        self.assertRegex(seg, r"\*\*500 处是 location\*\*")
        self.assertIn("2026-08-23", seg)

    def test_the_docstring_says_this_step_changes_nothing(self):
        """给了命令之后最容易滑向「那就顺手改了吧」。"""
        i = SRC.index("def merge_into_seen(")
        seg = flat(SRC[i:SRC.index('    path, data, stamp = _seen_stamped(user)', i)])
        self.assertRegex(seg, r"\*\*这一步不动数据\*\*")

    def test_the_merge_fields_still_include_salary_and_location(self):
        self.assertIn("salary", st.MERGE_FIELDS)
        self.assertIn("location", st.MERGE_FIELDS)

    def test_rank_step0_still_runs_the_merge(self):
        """这段输出的读者是跑 /job-rank 的人 —— 接线断了就没人看得到。"""
        doc = (ROOT / "workflows" / "job-rank.md").read_text(encoding="utf-8")
        self.assertIn("python tools/jd_store.py --merge --apply", doc)


class TheSignalItLeansOnIsReal(unittest.TestCase):
    """有语料时验一次：噪音真的压倒性，而真冲突真的存在。"""

    def _corpus(self):
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        u = p.read_text(encoding="utf-8").strip()
        if not (ROOT / "users" / u / "job_scraper" / "details").is_dir():
            self.skipTest("没有详情库")
        r = st.merge_into_seen(u, apply=False)
        if sum(r["refined"].values()) + len(r["conflicts"]) < 20:
            self.skipTest("不一致太少，说明不了")
        return r

    #: 噪音要比真冲突多多少倍，才值得分两类报。
    #:
    #: 规则上线时是 **500 : 3（167 倍）** —— 那时 3 条真薪资冲突滚在 500 行
    #: location 噪音里，8 行样本靠运气才露出 1 条。
    #: 2026-09-01 复量是 **213 : 25（8.5 倍）**：噪音那边基本没动（location 199），
    #: 真冲突从 3 涨到 25，涨的是 `isHeadhunter`（10）、`compStage`（7）、
    #: `compScale`（4）—— 都是后来才开始抓的公司字段，两边各存各的。
    #: **分两类仍然值得**：213 行照样能淹掉 25 行。所以倍数下调，理由记在这儿；
    #: 真要它再掉下去（比如到 3 倍），那才是「该合并成一类报」的信号。
    RATIO = 5

    def test_refinements_outnumber_real_conflicts(self):
        r = self._corpus()
        self.assertGreater(sum(r["refined"].values()),
                           len(r["conflicts"]) * self.RATIO,
                           "噪音不再压倒性 —— 分两类报的理由变弱了，重新量一次")

    def test_the_noise_is_almost_all_location(self):
        r = self._corpus()
        self.assertEqual(max(r["refined"], key=r["refined"].get), "location")

    def test_the_real_conflicts_are_worth_a_line_each(self):
        """真冲突要是成百上千，「逐个跑 /job-apply」这条建议就不成立了。"""
        r = self._corpus()
        self.assertLess(len(r["conflicts"]), 50,
                        f"{len(r['conflicts'])} 条真冲突 —— 逐个复核不现实了，"
                        f"该改成批量路径")


if __name__ == "__main__":
    unittest.main()
