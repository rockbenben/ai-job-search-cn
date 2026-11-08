"""同岗多投放归组：同一份 JD 的多个投放，列表里只占一行。

## 为什么

同一个岗常被多个猎头重复投放——实测同一份供应链 JD 有**五个**投放、启蒙教育四个、
模型评测三个。不归组的话「值得投 31 个」是虚的：用户会把同一个岗研究两遍，
「先投哪个」的判断也被稀释（去重后真实数字约 23）。

## 规则

- 键用 **JD 正文前缀哈希**（归一化后前 300 字）。不同猎头脱敏程度不同（删公司名等），
  全文哈希会漏；前缀保守——**宁可漏归组，不可错合并**（把两个不同的岗合成一个，
  比重复显示严重得多）。
- 组内**年包下沿最高的当主投放**，年包相同才比分数；其余标 `dupOf`、列表隐藏；
  主投放带 `duplicates`（各投放的链接与薪资）——同岗不同价本身是职级未定/广撒网的
  信号，要摆出来。
- 没有 JD 正文的不参与归组（浏览器渠道、未抓到的）。

> **这份注释和下面的断言原来都写的是「分最高的当主投放」，而实现早就改成按年包了**
> （`export_web_data.py` 那段注释记着改的理由：分数会被 `/job-apply` 的深评写回，
> 主投放就跟着漂到另一个价位上去——实测面板显示的年包从 128-160 万变成 85-136 万，
> 少了 43 万；年包是 JD 自己的属性，不受任何写回影响）。
>
> **测试没拦住这次改动，因为它测不到。** 两个 entry 的 `salary` 都写死成
> `30-40k·14薪`：年包一样 → 主键打平 → 落到次级键 `-score` → 分高的胜出 → 通过。
> 实现按年包排也过，按分数排也过，**这条规则实际上零约束**。
> 2026-08-13 全面检查时发现，改成年包与分数**故意相反**，两种实现只有一种能过。
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import export_web_data as ex  # noqa: E402

DESC = ("岗位职责：负责某产品线的规划设计与迭代，深入业务场景挖掘需求，"
        "输出产品方案与需求文档，协调研发测试推动落地上线，并持续跟踪效果优化。"
        "任职要求：三年以上产品经验，具备优秀的沟通协调与逻辑分析能力。") * 2


def _mk(tmp: Path, entries: dict, details: dict) -> None:
    u = tmp / "users" / "张三"
    (u / "job_scraper" / "details").mkdir(parents=True)
    (u / "profile").mkdir(parents=True)
    (u / "profile" / "candidate.md").write_text("# 候选人\n真实内容\n", encoding="utf-8")
    (u / "job_scraper" / "seen_jobs.json").write_text(
        json.dumps({"seen": entries}, ensure_ascii=False), encoding="utf-8")
    for jid, desc in details.items():
        (u / "job_scraper" / "details" / f"{jid}.json").write_text(
            json.dumps({"description": desc}, ensure_ascii=False), encoding="utf-8")
    (tmp / ".active_user").write_text("张三", encoding="utf-8")


def _export(entries, details):
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        _mk(tmp, entries, details)
        out = tmp / "web" / "public"
        saved = ex.ROOT, ex.OUT_DIR, ex.PDF_DIR
        ex.ROOT, ex.OUT_DIR, ex.PDF_DIR = tmp, out, out / "pdf"
        try:
            assert ex.main() == 0
            return json.loads((out / "data.json").read_text(encoding="utf-8"))["jobs"]
        finally:
            ex.ROOT, ex.OUT_DIR, ex.PDF_DIR = saved


def entry(url, title, score, salary="30-40k·14薪"):
    return {"url": url, "title": title, "company": "某公司", "status": "ranked",
            "first_seen": "2026-07-01", "salary": salary,
            "rank_score": score, "rank_verdict": "粗筛：值得投",
            "rank_breakdown": {"技能与经验": 60, "依据": "测试"}}


class SameJdPostingsCollapse(unittest.TestCase):
    def test_shared_prefix_with_different_tail_stays_visible(self):
        first = entry("https://x/first", "产品经理", 70)
        second = entry("https://x/second", "产品经理", 60)
        ids = [ex.stable_id(e["url"], e["title"]) for e in (first, second)]
        prefix = DESC * 3
        jobs = _export({"first": first, "second": second},
                       {ids[0]: prefix + "负责医疗产品", ids[1]: prefix + "负责金融产品"})
        self.assertEqual(len(jobs), 2)
        self.assertFalse(any(j.get("dupOf") for j in jobs))

    def test_highest_annual_becomes_primary_even_when_it_scores_lower(self):
        """**年包与分数故意相反**——这是这条测试唯一能拦住回退的形状。

        `e_rich` 年包高（50-60k·16薪 = 96-115 万）但分低（60）；
        `e_poor` 年包低（30-40k·14薪 = 50-67 万）但分高（70）。
        按年包排 → `e_rich` 当主投放；按分数排 → `e_poor` 当主投放。两者只能中一个。
        """
        e_rich = entry("https://x/rich", "甲岗", 60, salary="50-60k·16薪")
        e_poor = entry("https://x/poor", "甲岗（猎头版）", 70)
        ids = {"rich": ex.stable_id(e_rich["url"], e_rich["title"]),
               "poor": ex.stable_id(e_poor["url"], e_poor["title"])}
        jobs = _export({"u1#甲岗": e_rich, "u2#甲岗2": e_poor},
                       {ids["rich"]: DESC, ids["poor"]: DESC})
        primary = next(j for j in jobs if j["id"] == ids["rich"])
        dup = next(j for j in jobs if j["id"] == ids["poor"])
        self.assertEqual(len(primary.get("duplicates") or []), 1,
                         "年包高的要当主投放——分数会被深评写回改写，年包不会")
        self.assertEqual(dup.get("dupOf"), primary["id"],
                         "年包低的标 dupOf，哪怕它分数更高")
        self.assertEqual(primary["duplicates"][0]["url"], "https://x/poor",
                         "其它投放的链接必须保留——投哪个渠道由用户挑")

    def test_score_breaks_the_tie_when_annual_is_equal(self):
        """年包打平（两处挂同一个价）才轮到分数说话。"""
        e1 = entry("https://x/1", "甲岗", 70)
        e2 = entry("https://x/2", "甲岗（猎头版）", 60)
        ids = {"a": ex.stable_id(e1["url"], e1["title"]),
               "b": ex.stable_id(e2["url"], e2["title"])}
        jobs = _export({"u1#甲岗": e1, "u2#甲岗2": e2},
                       {ids["a"]: DESC, ids["b"]: DESC})
        self.assertEqual(len(next(j for j in jobs if j["id"] == ids["a"])
                             .get("duplicates") or []), 1)
        self.assertEqual(next(j for j in jobs if j["id"] == ids["b"]).get("dupOf"),
                         ids["a"], "年包相同时按分数，分高的当主投放")

    def test_different_jds_are_never_merged(self):
        """错合并比重复显示严重得多——两个不同的岗绝不能合成一个。"""
        e1, e2 = entry("https://x/1", "甲岗", 70), entry("https://x/2", "乙岗", 60)
        ids = [ex.stable_id(e["url"], e["title"]) for e in (e1, e2)]
        other = DESC.replace("产品线", "完全不同的另一条业务线")
        jobs = _export({"u1#甲": e1, "u2#乙": e2}, {ids[0]: DESC, ids[1]: other})
        self.assertFalse(any(j.get("dupOf") for j in jobs))
        self.assertFalse(any(j.get("duplicates") for j in jobs))

    def test_missing_description_never_groups(self):
        e1, e2 = entry("https://x/1", "甲岗", 70), entry("https://x/2", "甲岗", 60)
        jobs = _export({"u1#甲": e1, "u2#甲2": e2}, {})
        self.assertFalse(any(j.get("dupOf") for j in jobs),
                         "没有正文就没有归组依据，不许瞎猜")


if __name__ == "__main__":
    unittest.main()
