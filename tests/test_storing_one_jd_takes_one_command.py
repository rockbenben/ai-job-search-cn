# -*- coding: utf-8 -*-
"""落库这条规则一直没人执行，因为执行它要造一个文件。

`job-rank.md` 写着「读到的 JD 正文当场存进详情库，不要读完就扔」。但在
2026-08-26 之前，落库只有 `--import-from <目录>` 一条路：读页面的人手上只有
一段正文，为了存它得先拼出详情 JSON、写到某个临时目录、再收一次。

全库实测（2026-08-26）：**191 个**岗的判词写着读过 JD 正文而详情库里查不到
（猎聘 113、BOSS 48、智联 14、前程 10）。同一天一轮 `/job-auto` 评了 13 个岗，
落库 4 个 —— 正好是当轮要出材料的那 4 个，其余 9 个照旧只读不存。

**摩擦大的规则不会被执行**，写多少遍都一样。所以修的不是文档，是那条路：
`--save <职位链接>`，正文从标准输入进，一步到位。

## 两处「看起来成功」的陷阱，这里都钉着

- **标题不让调用方给。** 库里的键是 `stable_id(url, title)`，标题差一个字，
  存进去的这份就再也读不回来 —— 而它写了盘、有文件、不报错。所以标题从
  `seen_jobs.json` 那条取，链接对不上就停。
- **正文太短的不收。** 判据与 `--import-from` 同源（`has_body`）。几十个字的
  占位收进来，`/job-rank` 会以为抓过了，然后拿那一句话去打分——比没有更糟。
"""
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import jd_store as st  # noqa: E402

RANK = (ROOT / "workflows" / "job-rank.md").read_text(encoding="utf-8")
URL = "https://www.liepin.com/job/1234567.shtml"
BODY = "岗位职责：负责智能体产品的需求梳理、方案设计与上线维护。" * 6


class _Bench:
    """一个只有一条职位记录的临时用户。"""

    def __enter__(self):
        self.tmp = TemporaryDirectory()
        root = Path(self.tmp.name)
        d = root / "users" / "u" / "job_scraper"
        d.mkdir(parents=True)
        (d / "seen_jobs.json").write_text(json.dumps({
            "jd1": {"url": URL, "title": "AI产品经理", "company": "蓝湾智投科技",
                    "salary": "40-70k", "salaryMonths": 16, "location": "上海"},
        }, ensure_ascii=False), encoding="utf-8")
        self.patch = mock.patch.object(st, "ROOT", root)
        self.patch.start()
        return self

    def __exit__(self, *a):
        self.patch.stop()
        self.tmp.cleanup()

    def stored(self):
        return st.load("u", URL, "AI产品经理")


class OneCommandStoresIt(unittest.TestCase):
    def test_the_body_lands_and_can_be_read_back(self):
        with _Bench() as b:
            self.assertIsNone(b.stored(), "临时库本该是空的")
            r = st.save_from_text("u", URL, BODY, apply=True)
            got = b.stored()
            self.assertIsNotNone(got, "存了却读不回来 —— 键算错了")
            self.assertTrue(st.has_body(got))
            self.assertEqual(got["description"], BODY.strip())
            self.assertEqual(r["chars"], len(BODY.strip()))

    def test_a_dry_run_writes_nothing(self):
        with _Bench() as b:
            st.save_from_text("u", URL, BODY, apply=False)
            self.assertIsNone(b.stored(), "没加 --apply 却写盘了")

    def test_a_link_that_only_normalises_the_same_still_lands(self):
        """**这条是键的另一半。** 用户手上那个链接常常和库里存的不是同一个字符串
        —— 最常见的就是 `http` 对 `https`。键要拿**库里那条**的链接算，拿传进来的
        算就会存到一个谁也找不到的地方，而且照样写盘、照样不报错。

        （查询串不在此列：`norm_url` 有意保留它，`?from=wx` 归一化后并不等价，
        那种链接会走「库里没有这条」那一支停下来。）"""
        with _Bench() as b:
            st.save_from_text("u", "http://www.liepin.com/job/1234567.shtml",
                              BODY, apply=True)
            self.assertIsNotNone(b.stored(),
                                 "换个写法的同一个链接，存进去就读不回来了")

    def test_it_carries_the_fields_the_store_already_has(self):
        """带上已有的结构化字段，`--merge` 那一跳才不会白跑一趟。"""
        with _Bench():
            r = st.save_from_text("u", URL, BODY, apply=True)
            for f in ("salary", "salaryMonths", "location", "company", "title"):
                self.assertIn(f, r["fields"], f"「{f}」没带过去")


class TheTwoSilentFailuresAreRefused(unittest.TestCase):
    def test_an_unknown_link_stops_and_says_what_to_type(self):
        with _Bench():
            with self.assertRaises(SystemExit) as cm:
                st.save_from_text("u", "https://example.com/nope", BODY, apply=True)
            msg = str(cm.exception)
            self.assertIn("职位库里没有这条链接", msg)
            self.assertIn("/job-scrape", msg, "没给该敲的那条命令")

    def test_the_caller_cannot_pass_a_title(self):
        """标题是键的一半。让调用方给，就是给「存了读不回来」开了口子。"""
        import inspect
        params = list(inspect.signature(st.save_from_text).parameters)
        self.assertNotIn("title", params, f"签名收了标题：{params}")

    def test_too_short_a_body_is_refused(self):
        with _Bench() as b:
            with self.assertRaises(SystemExit) as cm:
                st.save_from_text("u", URL, "就一句话", apply=True)
            self.assertIn("以为抓过", str(cm.exception))
            self.assertIsNone(b.stored(), "拒了却还是写了盘")

    def test_the_threshold_is_the_shared_one(self):
        """判据与 `--import-from` 同源，不许在这里另写一个数。"""
        src = (ROOT / "tools" / "jd_store.py").read_text(encoding="utf-8")
        i = src.index("def save_from_text(")
        body = src[i:src.index("\ndef ", i + 10)]
        self.assertIn("has_body(", body, "没走共用的判据")
        self.assertNotIn("len(body) <", body, "自己又写了一个长度阈值")


class TheWorkflowNamesTheCommand(unittest.TestCase):
    """`AGENTS.md`：凡是告诉用户接下来做什么的地方，都要写出该敲的命令。"""

    def test_the_rule_carries_a_runnable_line(self):
        i = RANK.index("读到的 JD 正文当场存进详情库")
        self.assertIn("jd_store.py --save", RANK[i:i + 700],
                      "规则还在，命令没跟上 —— 这正是它 191 次没被执行的原因")

    def test_the_second_site_names_it_too(self):
        i = RANK.index("本步新抓到的 JD 一律存进详情库")
        self.assertIn("--save", RANK[i:i + 400])

    def test_the_incident_is_on_record(self):
        self.assertRegex(RANK, r"摩擦大的规则(不[易会被]|难)")


if __name__ == "__main__":
    unittest.main()
