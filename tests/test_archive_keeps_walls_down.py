# -*- coding: utf-8 -*-
"""归档：热库规模恒定的闸门，以及它绝不能弄丢的东西。

实测（2026-08-19）：职位库 87% 是死数据（出局判词），每次导出全量重算、
每次写回整份重写。归档把闸门装在增长曲线上：热库 ≈ 活数据 + 两周内的出局岗。

**用户当面问过的两件事，是这组测试的主轴：**

1. 「判断是否重复怎么办」——归档的键必须仍参与抓取去重与词表统计，
   否则死数据被当新岗抓回来重评一遍（白烧钱），挖空的词又被推荐（白抓一轮）。
2. 「有些职位还没投或需要重新判定呢」——待评/可投/已投/有材料的永远不归档；
   归档不是删除；`--revive` 一条命令全拉回来重判。
"""

import datetime as dt
import json
import shutil
import sys
import tempfile
import pathlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import archive as ar  # noqa: E402
import _cli  # noqa: E402

TODAY = dt.date(2026, 8, 19)


def _entry(title, verdict=None, status="ranked", rank_date="2026-07-20", **kw):
    e = {"url": f"https://x/{title}", "title": title, "company": "C",
         "status": status, "first_seen": "2026-07-19", "rank_date": rank_date}
    if verdict:
        e["rank_verdict"] = verdict
    e.update(kw)
    return e


class _Repo:
    def __enter__(self):
        self._t = tempfile.TemporaryDirectory()
        self.root = Path(self._t.name)
        (self.root / "users" / "u" / "job_scraper").mkdir(parents=True)
        (self.root / ".active_user").write_text("u", encoding="utf-8")
        self._saved = ar.ROOT
        ar.ROOT = self.root
        return self

    def __exit__(self, *a):
        ar.ROOT = self._saved
        self._t.cleanup()

    def write(self, seen):
        sj, _ = ar.paths("u")
        sj.write_text(json.dumps({"seen": seen}, ensure_ascii=False), encoding="utf-8")
        return sj


class TheTwoAgeLimitsArePinned(unittest.TestCase):
    """`DEAD_DAYS = 14` 与 `DECISION_DAYS = 30` —— 此前**一条测试都没提过它们**。

    它们决定**什么东西离开用户的视野**：`archive.py --apply` 每轮 `/job-auto`
    收尾都跑，归档过去的岗就不在面板上了（放得回来，但他得先想起来去翻）。
    两个方向都会静默出事：

        调小  → 「刚判完、他还没来得及翻案」的岗当天就被埋掉
        调大  → 热库白白扛着死数据，导出与写回一轮比一轮慢

    定义处写着理由（「两周是『职位多半已下线』的经验值」、「他表过态的，
    放回概率比规则杀的高」），而**没有一处验它们真的是这么用的**。

    钉的是**边界行为**：差一天在里面、够了就出去；以及那个不对称本身 ——
    他自己标的比规则杀的多留一倍。
    """

    def _aged(self, days, **kw):
        """一个出局了 `days` 天的岗。"""
        day = (TODAY - dt.timedelta(days=days)).isoformat()
        return _entry("岗", "硬门 FAIL (学历)", rank_date=day, **kw)

    def test_a_rule_killed_job_waits_the_full_two_weeks(self):
        """13 天还在，14 天出去。

        **天数写死，不从 `ar.DEAD_DAYS` 现算。** 第一版拿常量去造样本
        （`self._aged(ar.DEAD_DAYS - 1)`）—— 变异实测当场证明它空转：
        把 14 改成 7，样本跟着变成 6/7 天，测试照样绿。
        用常量造样本等于让它自己给自己出题。
        """
        self.assertEqual(ar.pick({"a": self._aged(13)}, {}, set(), set(),
                                 TODAY), {},
                         "13 天就归档了 —— 他还来得及翻案的那几天没了")
        self.assertIn("a", ar.pick({"a": self._aged(14)}, {}, set(), set(),
                                   TODAY),
                      "够两周了还不归档 —— 热库白扛死数据")

    def test_a_job_he_marked_himself_waits_twice_as_long(self):
        """他表过态的放回概率高，所以多留一倍。"""
        def mark(days):
            return {"a": {"decision": "skipped",
                          "date": (TODAY - dt.timedelta(
                              days=days)).isoformat()}}

        # 天数写死，理由同上一条。
        self.assertEqual(
            ar.pick({"a": self._aged(29)}, mark(29), set(), set(), TODAY), {},
            "他自己标的，不到一个月就埋了")
        self.assertIn(
            "a", ar.pick({"a": self._aged(30)}, mark(30), set(), set(), TODAY))

    def test_the_asymmetry_is_the_point(self):
        """规则杀的和他自己标的，等的时间必须不一样 —— 一样就白分两个数。"""
        self.assertGreater(ar.DECISION_DAYS, ar.DEAD_DAYS,
                           "他表过态的反而先被埋 —— 两个数写反了")

    def test_both_numbers_carry_their_reason(self):
        src = (ROOT / "tools" / "archive.py").read_text(encoding="utf-8")
        i = src.index("DEAD_DAYS = ")
        self.assertIn("职位多半已下线", " ".join(src[max(0, i - 300):i].split()),
                      "DEAD_DAYS 没留下理由")
        j = src.index("DECISION_DAYS = ")
        self.assertIn("放回概率", " ".join(src[max(0, j - 200):j].split()),
                      "DECISION_DAYS 没留下理由")


class OnlyLongDeadUnappliedJobsGoCold(unittest.TestCase):

    def test_the_gates(self):
        with _Repo() as r:
            seen = {
                "a": _entry("老出局", "硬门 FAIL (学历)"),                      # 归
                "b": _entry("刚出局", "粗筛：跳过", rank_date="2026-08-18"),     # 太新，留
                "c": _entry("待评", None, status="new"),                        # 活，留
                "d": _entry("可投", "粗筛：值得投"),                            # 活，留
                "e": _entry("可以考虑", "粗筛：可以考虑"),                      # 活，留
                "f": _entry("没日期的出局", "不建议", rank_date=None,
                            first_seen=None),                                   # 没日期，宁可留
            }
            del seen["f"]["rank_date"]; del seen["f"]["first_seen"]
            r.write(seen)
            got = ar.run("u", apply=False, today=TODAY)["chosen"]
            self.assertEqual(set(got), {"a"},
                             "只有「出局且超过 14 天」的该归——待评/可投/刚出局/没日期的都不许碰")

    def test_applied_jobs_never_go_cold(self):
        """投过的岗是台账与「已投递」视图的数据源，归了面板当场少一条投递。"""
        with _Repo() as r:
            r.write({"a": _entry("投过的出局岗", "不建议")})
            csv = ar.ROOT / "users" / "u" / "job_search_tracker.csv"
            # 列名用**真实台账的英文表头**（date,company,role,…,source）——
            # 第一版写成中文列名，match_tracker 一行都配不上：夹具与真实数据脱节，
            # 测出来的是一个不存在的库。
            csv.write_text("date,company,role,status,source" + chr(10)
                           + "2026-08-01,C,投过的出局岗,applied,https://x/投过的出局岗" + chr(10),
                           encoding="utf-8")
            self.assertEqual(ar.run("u", apply=False, today=TODAY)["chosen"], {},
                             "投过的岗被归档了——面板「已投递」会当场少一条")

    def test_user_decisions_get_a_longer_grace(self):
        """他手动标的「不投」多留到 30 天——表过态的，放回概率高。"""
        with _Repo() as r:
            sj = r.write({"a": _entry("手动标掉", "粗筛：值得投")})
            _cli.set_user_decision(sj, "a", "skipped", date="2026-08-01", reason="不想投")
            self.assertEqual(ar.run("u", apply=False, today=TODAY)["chosen"], {},
                             "18 天前手动标的就被归了——用户决定该留 30 天")
            self.assertNotEqual(
                ar.run("u", apply=False, today=dt.date(2026, 9, 5))["chosen"], {},
                "35 天后仍不归——宽限成了永久豁免")


class NothingIsLostAndItComesBack(unittest.TestCase):

    def test_archive_keeps_every_field_and_folds_the_overlay_in(self):
        with _Repo() as r:
            sj = r.write({"a": _entry("老出局", "硬门 FAIL (学历)", rank_score=None,
                                      rank_breakdown={"依据": "原话"})})
            _, arc = ar.paths("u")
            ar.run("u", apply=True, today=TODAY)
            cold = json.loads(arc.read_text(encoding="utf-8"))["seen"]
            self.assertIn("a", cold)
            self.assertEqual(cold["a"]["rank_breakdown"]["依据"], "原话",
                             "归档丢字段——它必须是搬家，不是删除")
            hot = json.loads(sj.read_text(encoding="utf-8"))
            self.assertNotIn("a", hot["seen"])
            self.assertEqual(hot["archived"]["count"], 1,
                             "归档计数没记在热库顶层——导出就得去啃冷库")

    def test_revive_is_a_dry_run_by_default(self):
        """`--apply` 那面旗子的 help 写着「不加就是试运行」—— 那是对整条命令的承诺。

        而 2026-08-30 之前 `--revive` 这一支根本不看它：敲一次就把整份存档
        （实测活动用户 **1074 个岗**）搬回热库、写盘、删掉存档文件。
        仓库里六个工具都印「试运行，没有写盘。确认无误后加 --apply」，
        肌肉记忆是现成的 —— **唯独这一条会当场动手，而它动的量最大**。
        """
        with _Repo() as r:
            sj = r.write({"a": _entry("老出局", "不建议"),
                          "b": _entry("可投", "粗筛：值得投")})
            ar.run("u", apply=True, today=TODAY)
            _, arc = ar.paths("u")
            before = arc.read_bytes()
            hot_before = sj.read_bytes()
            got = ar.revive("u")                      # 不给 apply
            self.assertTrue(got.get("dry"), "没标出这是试运行")
            self.assertEqual(got["revived"], 1, "试运行也要说会拉回几个")
            self.assertEqual(arc.read_bytes(), before, "试运行动了存档")
            self.assertEqual(sj.read_bytes(), hot_before, "试运行动了热库")

    def test_revive_round_trip(self):
        """改了硬性条件要重判：--revive 全拉回，一个不少。"""
        with _Repo() as r:
            sj = r.write({"a": _entry("老出局", "不建议"),
                          "b": _entry("可投", "粗筛：值得投")})
            ar.run("u", apply=True, today=TODAY)
            got = ar.revive("u", apply=True)
            self.assertEqual(got["revived"], 1)
            hot = json.loads(sj.read_text(encoding="utf-8"))
            self.assertIn("a", hot["seen"], "拉回来丢了岗")
            _, arc = ar.paths("u")
            self.assertEqual(_cli.seen_of(json.loads(arc.read_text(encoding="utf-8"))), {}, "恢复后归档应为空")
            self.assertEqual(hot["archived"]["count"], 0)


class TheFourPortsAreWired(unittest.TestCase):
    """四个口子：去重、词表、导出计数、auto 收尾。漏一个归档就是负资产。"""

    def test_scrape_dedup_reads_the_archive(self):
        wf = (ROOT / "workflows" / "job-scrape.md").read_text(encoding="utf-8")
        self.assertIn("查重还必须连存档一起查", wf)
        self.assertIn("archive.json", wf)

    def test_query_yield_reads_the_archive(self):
        """**验行为，别验它自己有没有写 `archive.json` 这个字面量。**

        2026-08-30 起读存档走 `_cli.archived`（读文件、解析、兜住坏文件那三步
        原来在两个文件里各有一份）—— 钉字面量的话，一次正当的收口就把这条弄红了，
        而它要守的那件事一点没变。
        """
        src = (ROOT / "tools" / "query_yield.py").read_text(encoding="utf-8")
        self.assertIn("_cli.archived", src,
                      "词表只读热库——出局岗一归档，挖空的词又会被推荐成「最值钱的格子」")

    def test_the_shared_reader_really_reads_it(self):
        """那一层自己得真的读那个文件 —— 上面那条靠它兜底。"""
        import _cli
        src = pathlib.Path(_cli.__file__).read_text(encoding="utf-8")
        i = src.index("def archived(")
        self.assertIn("archive.json", src[i:src.index(chr(10) + "def ", i)])

    def test_the_exporter_reports_the_count_without_reading_the_cold_file(self):
        src = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
        self.assertIn("archivedCount", src)
        i = src.index("archivedCount")
        self.assertNotIn("archive.json", src[i - 400:i + 400],
                         "导出为了个计数去读冷库——它一年后几十 MB，每次点击读一遍，"
                         "归档省下的时间就还回去了")

    def test_auto_runs_it_at_the_tail(self):
        auto = (ROOT / "workflows" / "job-auto.md").read_text(encoding="utf-8")
        self.assertIn("archive.py --apply", auto)

    def test_rank_all_documents_the_revive_rule(self):
        wf = (ROOT / "workflows" / "job-rank.md").read_text(encoding="utf-8")
        self.assertIn("--revive", wf)
        self.assertIn("改的是「门」才 revive", wf,
                      "没写清什么时候要 revive——用户只会在两个极端里选一个")

    def test_the_panel_explains_where_the_jobs_went(self):
        app = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
        self.assertIn("archivedCount", app,
                      "「搜到职位」的数字会在归档后凭空变小，面板不解释就像丢了数据")
        self.assertIn("--revive", app, "面板每处引导都要写出命令")
