# -*- coding: utf-8 -*-
"""`/job-rank` 里那条修复命令的说明，和代码对不上了三处。

`job-rank.md` 在「年限门」那一节末尾给出存量修法
（`audit_pipeline.py --requeue-unfounded --apply`），并描述它做什么。
2026-08-23 逐条比对，三处都停在旧版本上：

| 文档说 | 代码做的 |
|---|---|
| 「判据不成立的那**两类**」 | **三类** —— 年限两档、无依据、**排除无出处** |
| 「抹掉那**三个** rank 字段」 | **四个**（`rank_breakdown` 后来补的） |
| （没提） | 抹之前把原判存进 `prev_verdict` 留痕 |

第三条尤其要紧：不写下来，读的人会以为跑一次就把上一轮的判断丢了，
于是不敢跑 —— 而那正是这条命令存在的意义（它一次能救回一百多个被误杀的岗）。
第一条同理：**「按一条他资料里根本没有的排除杀掉的」是三类里最大的一类**
（实测活动用户「明确排除」判了 396 个 FAIL），而文档里查无此条。

这一族在本仓库叫「文档声称 vs 实测」，审计里有一条同名检查
（`check_doc_claims_vs_reality`），但它盯的是职位库里的字段覆盖率，
盯不到这里 —— 所以这份守卫自己去比。
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import _cli  # noqa: E402
import audit_pipeline as AP  # noqa: E402
from _srcscan import strip_comments  # noqa: E402

RANK = (ROOT / "workflows" / "job-rank.md").read_text(encoding="utf-8")
SRC = (ROOT / "tools" / "audit_pipeline.py").read_text(encoding="utf-8")


def _doc() -> str:
    """`job-rank.md` 里描述这条命令的那一段。"""
    i = RANK.index("它动**判据不成立**的那")
    j = RANK.index("### 学历门要看", i)
    return RANK[i:j]


def _popped_fields() -> list:
    """**真跑一遍**，读回哪些字段真的被抹掉了。

    原来这里正则 `audit_pipeline.py` 里**字面**写着的那个元组 —— 于是判据钉住的是
    「那一行长什么样」，不是「抹掉了什么」。2026-10-14 把那个字面量提成
    `_cli.RANK_FIELDS`（`audit_pipeline` 两处 + `serve.py` 一处共用）之后，正则当场
    失效、三条用例一起红，红的方式是 `assert None`：**看着像环境坏了，其实是锚没了**。

    改法照的是本文件下面 `test_the_code_really_requeues_the_third_class` 用的那条路
    —— 喂一份临时语料进真代码，读回结果。**带一个控制字段**：它要是也一起没了，
    说明这一支变成了「全抹」，那读出来的名单就只是「跑过」的同义词。

    语料里的 rank 字段是**从 `_cli.RANK_FIELDS` 播种的**，不是抄四个名字：
    抄一份的话，将来往那个元组里加第 5 个字段，语料里压根没有它，抹没抹都看不见，
    判据会对着一个已经不准的数字继续绿（变异实测：加一个字段，全绿）。
    """
    entry = {f: "x" for f in _cli.RANK_FIELDS}
    entry.update({
        "url": "https://x/1", "title": "医药数据产品经理",
        "company": "示例科技", "status": "ranked", "workYears": "5年以上",
        "rank_verdict": "硬门 FAIL (候选人明确排除（航空航天））",
        "rank_score": 40, "rank_date": "2026-10-14",
        "rank_breakdown": {"依据": "x"},
        "note_kept": "控制字段",
    })
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        p = _store(root, {"a": entry}, excludes="生物医药")
        _requeue(root)
        after = json.loads(p.read_text(encoding="utf-8"))["seen"]["a"]
    assert after.get("note_kept") == "控制字段", (
        "连控制字段都被抹了 —— 这一支成了「全抹」，读出来的名单说明不了任何事")
    return sorted(set(entry) - set(after))


def _store(root: Path, entries: dict, excludes="生物医药"):
    d = root / "users" / "u" / "job_scraper"
    d.mkdir(parents=True)
    (d / "details").mkdir()
    (root / "users" / "u" / "profile").mkdir(parents=True)
    (root / "users" / "u" / "profile" / "candidate.md").write_text(
        "\n".join(["# 候选人", "", "## 工作年限", "",
                   "产品方向 3 年，总年限 8 年。", "",
                   "## 明确排除", "", f"- 不做 {excludes}", ""]),
        encoding="utf-8")
    (d / "seen_jobs.json").write_text(
        json.dumps({"seen": entries}, ensure_ascii=False), encoding="utf-8")
    return d / "seen_jobs.json"


def _requeue(root: Path, apply=True):
    old = AP.ROOT
    try:
        AP.ROOT = root
        return AP.requeue_unfounded_gate_fails("u", apply=apply)
    finally:
        AP.ROOT = old


class TheFieldListMatches(unittest.TestCase):
    def test_the_doc_names_every_field_the_code_pops(self):
        seg = _doc()
        for f in _popped_fields():
            with self.subTest(field=f):
                self.assertIn(f"`{f}`", seg, f"代码抹了 {f}，文档没写")

    def test_the_doc_says_the_right_count(self):
        """「三个」这种数最容易停在旧版本上 —— 从代码里数出来再比。"""
        n = len(_popped_fields())
        cn = "零一二三四五六七八九"[n] if n < 10 else str(n)
        self.assertIn(f"抹掉 **{cn}**个 rank 字段", _doc(),
                      f"代码抹 {n} 个字段，文档说的不是这个数")

    def test_the_breakdown_field_is_actually_popped(self):
        """这一条是文档漏掉的那个 —— 少抹它，导出侧照着四维拆解把判词重建出来。"""
        self.assertIn("rank_breakdown", _popped_fields())


class TheThreeClassesAreAllDescribed(unittest.TestCase):
    #: 每一类 → 它的判据出自哪个检查（文档要指得出来）。
    CLASSES = {
        "年限": "check_years_gate_vs_platform_field",
        "无依据": "check_gate_fail_without_evidence",
        "排除无出处": "check_exclusions_trace_to_the_profile",
    }

    def test_the_doc_no_longer_says_two(self):
        self.assertNotIn("的那两类", _doc(), "文档还写着「两类」")
        self.assertIn("的那**三**类", _doc())

    def test_every_class_is_described(self):
        seg = _doc()
        for key, phrase in (("年限", "经验不限"),
                            ("无依据", "判不了就别判死"),
                            ("排除无出处", "一次都没出现")):
            with self.subTest(cls=key):
                self.assertIn(phrase, seg, f"「{key}」那一类没写进去")

    def test_the_missing_class_points_at_its_judge(self):
        """新补的那一类要说清判据在哪，否则读的人没法核。"""
        self.assertIn("check_exclusions_trace_to_the_profile", _doc())

    def test_all_three_judges_exist(self):
        for name in self.CLASSES.values():
            with self.subTest(check=name):
                self.assertTrue(hasattr(AP, name), f"{name} 不在了")

    def test_the_code_really_requeues_the_third_class(self):
        """**行为断言。** 只查源码里有没有 `_orphan_exclusions(` 的话，
        把 `anchors` 置空让那一支永不触发，照样绿（变异实测）。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = _store(root, {
                "a": {"url": "https://x/1", "title": "医药数据产品经理",
                      "company": "示例科技", "status": "ranked",
                      "workYears": "5年以上",
                      "rank_verdict": "硬门 FAIL (候选人明确排除（航空航天）)",
                      "rank_score": 40},
            }, excludes="生物医药")
            got = _requeue(root)
            after = json.loads(p.read_text(encoding="utf-8"))["seen"]["a"]
        self.assertEqual(got, ["a"],
                         "「航空航天」在他资料里查无此条，却没被退回")
        self.assertEqual(after["status"], "new")

    def test_an_exclusion_that_does_trace_is_left_alone(self):
        """写得出出处的排除是**有效判决**，不许一起退回。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = _store(root, {
                "a": {"url": "https://x/1", "title": "医药数据产品经理",
                      "company": "示例科技", "status": "ranked",
                      "workYears": "5年以上",
                      "rank_verdict": "硬门 FAIL (候选人明确排除（生物医药）)",
                      "rank_score": 40},
            }, excludes="生物医药")
            self.assertEqual(_requeue(root), [])
            self.assertEqual(
                json.loads(p.read_text(encoding="utf-8"))["seen"]["a"]["status"],
                "ranked")

    def test_the_other_two_selectors_are_still_wired(self):
        code = strip_comments(SRC)
        i = code.index("def requeue_unfounded_gate_fails(")
        body = code[i:code.index("\ndef ", i + 10)]
        self.assertIn("工作年限", body, "年限那一档不见了")
        self.assertIn("_unfounded_gate_fails(", body, "无依据那一档不见了")


class TheReceiptIsDocumented(unittest.TestCase):
    def test_the_doc_mentions_it(self):
        """不写下来，读的人以为跑一次就把上一轮的判断丢了，于是不敢跑。"""
        seg = _doc()
        self.assertIn("prev_verdict", seg, "留痕这件事文档一个字没说")
        self.assertRegex(" ".join(seg.split()), r"抹之前先把原判存进")

    def test_it_separates_the_two_ideas(self):
        """「不写新判词」和「抹掉旧判词不留痕」是两件事 —— 那正是当初做错的地方。"""
        self.assertRegex(" ".join(_doc().split()),
                         r"「不写新判词」和「抹掉旧判词不留痕」是两件事")

    def test_the_code_really_writes_it(self):
        code = strip_comments(SRC)
        i = code.index("def requeue_unfounded_gate_fails(")
        body = code[i:code.index("\ndef ", i + 10)]
        self.assertIn('e["prev_verdict"]', body)
        self.assertIn('"退回于"', body)

    def test_the_date_key_matches_what_the_doc_says(self):
        self.assertIn("退回于", _doc(), "日期键的名字文档写的和代码不一样")


class TheUntouchedRulesStaySaid(unittest.TestCase):
    def test_the_doc_says_deep_evaluations_are_skipped(self):
        """代码明确跳过 `evaluated` 的，而文档原来一个字没提 ——
        不写的话，用户不知道深评结论是安全的。"""
        seg = _doc()
        self.assertIn("evaluated", seg)
        self.assertRegex(" ".join(seg.split()), r"一律不动")

    def test_the_code_really_skips_them(self):
        """**行为断言。** `e.get("evaluated")` 在函数里出现两次，
        把年限那一支的判断换成 `if False:` 另一处照样在，源码检查绿
        （变异实测）。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = _store(root, {
                "a": {"url": "https://x/1", "title": "岗", "company": "示例科技",
                      "status": "ranked", "workYears": "经验不限",
                      "evaluated": True,
                      "rank_verdict": "硬门 FAIL (工作年限)", "rank_score": 40},
            })
            self.assertEqual(_requeue(root), [], "深评过的被退回了")
            after = json.loads(p.read_text(encoding="utf-8"))["seen"]["a"]
        self.assertEqual(after["status"], "ranked")
        self.assertEqual(after["rank_verdict"], "硬门 FAIL (工作年限)")

    def test_the_same_job_without_the_flag_is_requeued(self):
        """对照组：只差 `evaluated` 一个字段 —— 否则上一条可能是别的原因不动。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _store(root, {
                "a": {"url": "https://x/1", "title": "岗", "company": "示例科技",
                      "status": "ranked", "workYears": "经验不限",
                      "rank_verdict": "硬门 FAIL (工作年限)", "rank_score": 40},
            })
            self.assertEqual(_requeue(root), ["a"])

    def test_no_new_verdict_is_still_promised(self):
        self.assertIn("**不写新判词**", _doc())

    def test_the_backup_is_still_promised(self):
        seg = _doc()
        self.assertIn("seen_jobs.json.bak-before-requeue", seg)
        code = strip_comments(SRC)
        self.assertIn(".json.bak-before-requeue", code, "代码不再存备份了")

    def test_the_three_year_rules_above_survive(self):
        """这条命令是那三条判法的存量修法。判法没了，它就成了孤儿。"""
        for rule in ("**`workYears` 写「不限」时一律不 FAIL**",
                     "没有数字就不是门", "小的那个都够，就绝不 FAIL"):
            with self.subTest(rule=rule):
                self.assertIn(rule, RANK)


if __name__ == "__main__":
    unittest.main()
