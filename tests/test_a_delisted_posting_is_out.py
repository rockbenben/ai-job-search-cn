# -*- coding: utf-8 -*-
"""「判词说出局」那张表漏了最确定的一种：**已下线**。

`is_out_verdict` 管的就是判词这一侧 —— 哪些岗不进流水线格子、该归档。
它认硬门 FAIL 的各种前缀、认「跳过」、认「不建议」，唯独不认「已下线」。

漏了看不出来，是因为**另一条路一直兜着**：

- `export_web_data.funnels` 先跑 `is_parked`（那个函数认已下线）；
- `archive.pick` 先看 `status == "expired"`。

实测活动用户 2026-08-23：库里 4 个判词以「已下线」开头的岗（3 个写
「已下线」、1 个写「已下线（评分前发现）」），`status` 全是 `expired`、
`is_parked` 全为真 —— **补进来一个结果都不变**。

## 那为什么还要补

判词是打分器写的，状态是下线探测写的，**两者本来就可能不同步**。真出现
「判词说已下线、状态还是 ranked」时：`is_parked` 不认、`status` 不是
`expired`、`is_out_verdict` 又漏 —— 三条路同时落空，那个岗会永远留在热库，
而 `archive` 存在的理由正是「热库不涨」。

一个判据把正确性押在「另一条路一定同时也对」上，就是这个仓库反复点名的
形状：两套真相各自都显得对，比单纯的错更难发现。

## 不能加进 `GATE_FAIL_PREFIXES`

那张表是给门名解析用的（`gate_in_verdict` 要从判词里抠出是哪道门）。
「已下线」不是一道门，混进去会让解析器去它里面找门名。
"""
import json
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402
import build_dashboard as bd  # noqa: E402
import export_web_data as ex  # noqa: E402

EX = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
# `is_out_verdict` 2026-08-26 搬到了 build_dashboard（和 `is_parked` 一起，
# 理由见那个函数的说明）—— 这几条钉的是它的实测记录，跟着搬。
BD = (ROOT / "tools" / "build_dashboard.py").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*>\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


class ADelistedVerdictCountsAsOut(unittest.TestCase):
    def test_the_bare_form(self):
        self.assertTrue(ex.is_out_verdict("已下线"))

    def test_the_form_with_a_suffix(self):
        """实测语料里就有这一种 —— 打分器在评分前就发现它没了。"""
        self.assertTrue(ex.is_out_verdict("已下线（评分前发现）"))

    def test_leading_space_is_tolerated(self):
        self.assertTrue(ex.is_out_verdict("  已下线"))

    def test_a_sentence_that_merely_mentions_it_is_not_a_verdict(self):
        """用前缀不用 `in`：判词栏里写「这家的岗常年已下线又重挂」不该出局。"""
        self.assertFalse(ex.is_out_verdict("常年已下线又重挂，蓄水池嫌疑"))


class TheRestOfTheTableIsIntact(unittest.TestCase):
    def test_the_gate_fail_prefixes_still_count(self):
        for v in ("硬门 FAIL (学历院校)", "不满足硬性条件（工作年限）",
                  "硬门FAIL (明确排除)"):
            with self.subTest(v=v):
                self.assertTrue(ex.is_out_verdict(v))

    def test_skip_and_not_recommended_still_count(self):
        for v in ("跳过", "粗筛：跳过", "不建议", "粗筛：不建议"):
            with self.subTest(v=v):
                self.assertTrue(ex.is_out_verdict(v))

    def test_the_sellable_bands_are_still_in(self):
        """档序从 `_cli.VERDICTS` 切，**不在这里再抄一份**
        （`test_shared_vocab_single_source` 盯着这个 —— 第一版就抄了）。"""
        bands = list(_cli.VERDICTS[:3])
        for v in bands + [f"粗筛：{b}" for b in bands] + [""]:
            with self.subTest(v=v):
                self.assertFalse(ex.is_out_verdict(v))

    def test_the_prefix_tolerance_reason_survives(self):
        """2026-08-13 精确匹配落空，让硬门没过的岗混进了可投名单。"""
        i = BD.index("def is_out_verdict(")
        seg = flat(BD[i:BD.index("    v = (verdict or \"\").strip()", i)].replace("#", " "))
        self.assertRegex(seg, r"判词带门名后缀是常态")
        self.assertRegex(seg, r"用 startswith 不用 ==")


class ItIsNotMixedIntoTheGateNames(unittest.TestCase):
    """`GATE_FAIL_PREFIXES` 是门名解析的入口，不是「出局」的全集。"""

    def test_delisted_is_not_a_gate_prefix(self):
        self.assertNotIn("已下线", _cli.GATE_FAIL_PREFIXES)

    def test_the_gate_extractor_does_not_claim_a_gate(self):
        """真混进去的话，这里会从「已下线（评分前发现）」里抠出一个门名。"""
        # 它返回的是元组，空元组也是 `('', '')` —— 非空，判真假会误绿。
        got = _cli.gate_in_verdict("已下线（评分前发现）")
        self.assertFalse(any(got), f"从「已下线」里抠出了门名：{got!r}")

    def test_a_real_gate_verdict_still_yields_its_name(self):
        self.assertTrue(any(_cli.gate_in_verdict("硬门 FAIL (学历院校)")))

    def test_the_reason_is_recorded(self):
        i = BD.index("def is_out_verdict(")
        seg = flat(BD[i:BD.index("    v = (verdict or \"\").strip()", i)].replace("#", " "))
        self.assertRegex(seg, r"\*\*不能加进 `GATE_FAIL_PREFIXES`\*\*")
        self.assertRegex(seg, r"「已下线」不是一道门")


class TheReasonIsRecorded(unittest.TestCase):
    def _seg(self) -> str:
        i = BD.index("def is_out_verdict(")
        return flat(BD[i:BD.index("    v = (verdict or \"\").strip()", i)].replace("#", " "))

    def test_it_names_the_paths_that_were_masking_it(self):
        """要钉**具体那两句**。`is_parked` 在下一段也出现（「`is_parked` 不认」），
        只断言这个词的话，把第一段整句删掉照样绿（变异实测）。"""
        seg = self._seg()
        self.assertRegex(seg, r"`funnels` 前面先跑 `is_parked`")
        self.assertRegex(seg, r"`archive\.pick`\s*先看 `status == \"expired\"`")

    def test_it_admits_the_change_is_a_no_op_today(self):
        """不写清楚，下一个人会以为它修了一个正在发生的事故。"""
        seg = self._seg()
        self.assertRegex(seg, r"\*\*补进来一个结果都不变\*\*")
        self.assertIn("2026-08-23", seg)

    def test_it_says_why_it_is_worth_补_anyway(self):
        seg = self._seg()
        self.assertRegex(seg, r"判词是打分器 写的、状态是下线探测写的"
                              r"|判词是打分器写的、状态是下线探测写的")
        self.assertRegex(seg, r"永远 留在热库|永远留在热库")


class TheOtherPathsStillCatchThemToo(unittest.TestCase):
    """补的是第三条路，不是替掉前两条 —— 它们没了这条也不该独木难支。"""

    JOB = {"verdict": "已下线", "expired": True, "url": "https://x/1"}

    def test_is_parked_still_says_yes(self):
        self.assertTrue(bd.is_parked(self.JOB))

    def test_the_funnel_still_drops_it(self):
        self.assertEqual(ex.funnels_of(dict(self.JOB, materials=True)), [])

    def test_the_archiver_still_calls_the_verdict_judge(self):
        arc = (ROOT / "tools" / "archive.py").read_text(encoding="utf-8")
        self.assertIn("from export_web_data import is_out_verdict", arc)
        self.assertIn('dead = st == "expired" or user_decided '
                      'or is_out_verdict(vd)', arc)


class TheSignalItLeansOnIsReal(unittest.TestCase):
    """有语料时验一次：这个写法真的出现过，而且补它确实不改变结果。

    ## 取样范围 2026-10-12 从热库改成「热库 + 存档」

    原来只读 `web/public/data.json`，而那份快照只含**热库**。于是这条在
    2026-10-12 报了「语料里一个『已下线』判词都没有」——

        热库  997 条   判词以「已下线」开头  0 条
        存档 3159 条  判词以「已下线」开头  5 条
        （已下线 / 已下线 / 已下线 / 已下线（评分前发现）/ 已下线（页面写着「职位已关闭」））

    **写法没有死，语料搬家了**：带这个判词的岗早就被 `archive.py` 收走，
    而快照按设计不导出存档。判据却写在「这个判据管的那个字段」上，
    `is_out_verdict` 至今认这五种写法（下面有实测那一格）。

    判「这个写法不再被使用」之前先量全两边——那是同一条教训的另一个形状：
    **产出为空**可以是「没人写了」，也可以是「写到别处去了」。
    """

    def _jobs(self):
        p = ROOT / "web" / "public" / "data.json"
        if not p.is_file():
            self.skipTest("还没导出过")
        jobs = json.loads(p.read_text(encoding="utf-8"))["jobs"]
        if len(jobs) < 200:
            self.skipTest("语料太小")
        return jobs

    def _cold(self):
        ptr = ROOT / ".active_user"
        if not ptr.is_file():
            self.skipTest("没有活动用户")
        f = (ROOT / "users" / ptr.read_text(encoding="utf-8").strip()
             / "job_scraper" / "archive.json")
        if not f.is_file():
            self.skipTest("没有存档")
        return json.loads(f.read_text(encoding="utf-8")).get("seen", {})

    def test_the_spelling_really_occurs(self):
        hot = self._jobs()
        cold = self._cold()
        n = sum(1 for j in hot
                if (j.get("verdict") or "").strip().startswith("已下线"))
        m = sum(1 for v in cold.values()
                if isinstance(v, dict)
                and str(v.get("rank_verdict") or "").strip().startswith("已下线"))
        self.assertGreater(n + m, 0,
                           f"热库 {n} 条 + 存档 {m} 条，语料里一个「已下线」判词都没有 —— "
                           "重新量一次这个写法还在不在用（两边都量过了才是「不在用」）")

    def test_the_rule_still_recognises_it(self):
        """上面那几条不能只是躺在数据里：判据得真认它们。

        没有这一条，把取样范围从热库放宽到存档之后，「写法还在」只证明了
        「字符串还在」，没证明**规则还认它** —— 而这条守卫守的正是后者。
        """
        import export_web_data as ex
        cold = self._cold()
        seen = [str(v.get("rank_verdict")) for v in cold.values()
                if isinstance(v, dict)
                and str(v.get("rank_verdict") or "").strip().startswith("已下线")]
        self.assertTrue(seen, "存档里一个「已下线」判词都没有，这条没法验")
        for vd in seen:
            self.assertTrue(ex.is_out_verdict(vd), f"`is_out_verdict` 不认「{vd}」")

    def test_adding_it_changed_nothing_today(self):
        """真改了什么的话，那就不是「补全枚举」，是行为变更，要单独说清。"""
        changed = [j.get("title") for j in self._jobs()
                   if (j.get("verdict") or "").strip().startswith("已下线")
                   and not bd.is_parked(j)]
        self.assertEqual(changed, [],
                         f"有 {len(changed)} 个已下线的岗没被 is_parked 排掉 —— "
                         f"补进 is_out_verdict 会改变它们的结果，要单独复核")


if __name__ == "__main__":
    unittest.main()
