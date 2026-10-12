# -*- coding: utf-8 -*-
"""入库只有一个出口，而它比的是「身份」不是「钥匙」。

`tools/ingest.py` 是把这一轮抓到的候选写进职位库的唯一入口。它存在的原因
写在那个文件的 docstring 里：**这一步此前只有散文**——整条流水线每一步都有
工具，唯独入库没有，于是判重是手工的。

实测代价（2026-10-12）：一轮补货入库 362 个新岗，其中 **58 个是热库与存档
同时已有的**，被当新岗插了回去，两份随后各自演化。

## 这里守什么

- **三道判重按顺序**，一道比一道宽（宽的放前面会把窄的挡掉）；
- **试运行是缺省**，写盘要 `--apply`；
- **新键撞车拒绝写盘**——写下去就是静默覆盖掉另一个岗；
- **跑第二遍是空操作**（幂等）；
- **工作流指向它**，且不再教手写进 `seen_jobs.json`。
"""
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402
import ingest  # noqa: E402

HOT = {"url": "https://www.liepin.com/a/11111111.shtml",
       "title": "AI产品经理", "company": "热库公司", "date": "2026-10-01",
       "status": "ranked", "rank_verdict": "值得投"}
COLD = {"url": "https://www.liepin.com/a/22222222.shtml",
        "title": "Agent产品负责人", "company": "存档公司", "date": "2026-09-01",
        "status": "ranked"}


def build(tmp: pathlib.Path, user="u", hot=None, cold=None, tracker=None):
    base = tmp / "users" / user / "job_scraper"
    base.mkdir(parents=True, exist_ok=True)
    (base / "seen_jobs.json").write_text(
        json.dumps({"seen": hot or {}, "query_log": []}, ensure_ascii=False),
        encoding="utf-8")
    if cold is not None:
        (base / "archive.json").write_text(
            json.dumps({"seen": cold}, ensure_ascii=False), encoding="utf-8")
    if tracker is not None:
        (tmp / "users" / user / "job_search_tracker.csv").write_text(
            "date,company,sector,role,role_type,channel,status\n"
            + "\n".join(tracker) + "\n", encoding="utf-8")
    return base


class TheGatesInOrder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        # **两个读盘的函数都从模块级的 ROOT 找路径**：`store_dir` 与
        # `tracker_pairs`（后者拼 `users/<用户>/job_search_tracker.csv`）。
        # 不打桩的话第 3 道会去读**真的**投递台账 —— 那台账里有 94 对
        # 真实公司，于是「投过了」这条在任何用例上都可能假绿。
        self.orig_root = ingest.ROOT
        ingest.ROOT = self.root
        self.addCleanup(setattr, ingest, "ROOT", self.orig_root)
        self.hot_key = _cli.stable_id(HOT["url"], HOT["title"])
        self.cold_key = _cli.stable_id(COLD["url"], COLD["title"])

    def classify(self, row, hot=None, cold=None, tracker=None):
        build(self.root, hot=hot, cold=cold, tracker=tracker)
        seen = _cli.seen_of(json.loads(
            (self.root / "users/u/job_scraper/seen_jobs.json").read_text("utf-8")))
        pairs = ingest.tracker_pairs("u")
        return ingest.classify(
            row, _cli.seen_index("u", root=self.root), pairs,
            {ingest.pair_key(v.get("company"), v.get("title"))
             for v in seen.values() if isinstance(v, dict)},
            set())

    def test_gate_one_sees_the_hot_store(self):
        kind, key = self.classify(dict(HOT), hot={self.hot_key: dict(HOT)})
        self.assertEqual(kind, "seen")
        self.assertEqual(key, self.hot_key)

    def test_gate_one_sees_the_archive_too(self):
        """热库查了没查存档，就是 2026-08-30 那次：28 个归档的岗被当新岗插回。"""
        kind, _key = self.classify(dict(COLD), hot={}, cold={self.cold_key: dict(COLD)})
        self.assertEqual(kind, "seen")

    def test_gate_one_ignores_the_url_spelling(self):
        """埋点参数、`m.` 子域 —— 键会跟着变，令牌不会（它过 `_cli.norm_url`）。

        **协议那一档不在这里手搓。** 把 `https` 换成 `http` 得写一个字符串替换，
        而那正是 `test_shared_vocab_single_source` 当成「又抄了一份协议归一化」
        的写法 —— 它扫的是源码文本，**连说明里提到它都算**（第一版这句注释
        自己就把那条守卫弄红了）。那条守卫盯的是真问题：两处各写一遍归一化，
        规则一变只有一处跟得上。这里要的只是「换个写法还认得出」。
        协议这一档交给 `norm_url` 自己的测试与真数据实测（活动用户 2026-10-12：
        存档里抽 300 条换协议，令牌 300/300 认得出）。
        """
        for url in (COLD["url"] + "?refcode=abc",
                    COLD["url"].replace("//www.", "//m.", 1)):
            kind, _ = self.classify({**COLD, "url": url}, hot={},
                                    cold={self.cold_key: dict(COLD)})
            self.assertEqual(kind, "seen", f"{url} 没认出来")

    def test_gate_two_catches_the_reposted_job(self):
        """同一家公司、同一个岗位名、换了链接 → **跳过**。

        这是用户 2026-10-12 裁的：宁可漏过一个重挂的岗，也不要库里多一份
        说法不一的同一个岗。原来 Step 4 写的是「照旧当新岗处理」，
        而 Step 2 写的是「同公司同岗位就跳过」—— 同一份文档两条相反的指令。
        """
        moved = {**HOT, "url": "https://www.liepin.com/a/99999999.shtml"}
        kind, _ = self.classify(moved, hot={self.hot_key: dict(HOT)})
        self.assertEqual(kind, "same_pair")

    def test_gate_three_skips_what_was_already_applied(self):
        kind, _ = self.classify(
            {"url": "https://www.liepin.com/a/33333333.shtml",
             "title": "投过的岗", "company": "投过的公司"},
            hot={}, tracker=["2026-08-10,投过的公司,,投过的岗,,,已投递"])
        self.assertEqual(kind, "applied")

    def test_a_narrower_gate_still_wins(self):
        """顺序不能换：链接认出来的岗不该被「公司+岗位」那条抢先判成 same_pair。"""
        kind, key = self.classify(dict(HOT), hot={self.hot_key: dict(HOT)},
                                  tracker=[f"2026-08-10,{HOT['company']},,{HOT['title']},,,已投递"])
        self.assertEqual(kind, "seen", "先宽后窄 = 明明见过却被记成『投过了』")
        self.assertEqual(key, self.hot_key)

    def test_a_genuinely_new_job_is_new(self):
        kind, _ = self.classify(
            {"url": "https://www.liepin.com/a/44444444.shtml",
             "title": "全新的岗", "company": "新公司"}, hot={self.hot_key: dict(HOT)})
        self.assertEqual(kind, "new")


class TheToolBehaves(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.base = build(self.root, hot={_cli.stable_id(HOT["url"], HOT["title"]): dict(HOT)},
                          cold={_cli.stable_id(COLD["url"], COLD["title"]): dict(COLD)})
        self.inp = self.root / "batch.json"
        self.rows = [dict(HOT, date="2026-10-20"), dict(COLD, date="2026-10-20"),
                     {"url": "https://www.liepin.com/a/55555555.shtml",
                      "title": "全新的岗", "company": "新公司", "portal": "liepin-search",
                      "date": "2026-10-20"}]
        self.inp.write_text(json.dumps(self.rows, ensure_ascii=False), encoding="utf-8")
        self.ingest = ingest
        self.ingest.ROOT = self.root                    # 打在临时仓库上
        self.addCleanup(setattr, self.ingest, "ROOT", ROOT)

    def run_tool(self, *extra):
        import contextlib
        import io as _io
        self.buf = _io.StringIO()
        with contextlib.redirect_stdout(self.buf):
            code = self.ingest.main(["--input", str(self.inp), "--user", "u",
                                     "--query", "验收词", "--portal", "liepin-search",
                                     "--today", "2026-10-20", *extra])
        return code

    def read(self):
        return _cli.seen_of(json.loads((self.base / "seen_jobs.json").read_text("utf-8")))

    def test_dry_run_is_the_default(self):
        before = (self.base / "seen_jobs.json").read_bytes()
        self.assertEqual(self.run_tool(), 0)
        self.assertEqual((self.base / "seen_jobs.json").read_bytes(), before,
                         "不加 --apply 也写盘了")

    def test_apply_adds_only_the_new_one(self):
        self.assertEqual(self.run_tool("--apply"), 0)
        seen = self.read()
        # 热库原本 1 条（存档那 1 条在 archive.json 里，不在这份文件）
        self.assertEqual(len(seen), 2, "见过的两条也进来了")
        self.assertEqual(
            [v.get("title") for v in seen.values() if isinstance(v, dict)].count("全新的岗"),
            1)

    def test_apply_refreshes_the_date_and_nothing_else(self):
        """Step 4：见过的岗**只更新 date**。判词、分数一个都不许动。"""
        self.assertEqual(self.run_tool("--apply"), 0)
        v = self.read()[_cli.stable_id(HOT["url"], HOT["title"])]
        self.assertEqual(v["date"], "2026-10-20")
        self.assertEqual(v["rank_verdict"], "值得投", "连判词一起被改了")
        self.assertEqual(v["status"], "ranked", "status 被改了")

    def test_new_entries_enter_as_status_new(self):
        """判断是 `prescreen.py` / `/job-rank` 的活。这里下判断就是第二个真相。"""
        self.assertEqual(self.run_tool("--apply"), 0)
        new = [v for v in self.read().values()
               if isinstance(v, dict) and v.get("title") == "全新的岗"][0]
        self.assertEqual(new["status"], "new")
        self.assertEqual(new["found_by"], "验收词")
        self.assertEqual(new["first_seen"], "2026-10-20")

    def test_running_twice_changes_nothing(self):
        """第二遍不该再加一个岗、也不该再刷一次 date —— 判重生效的证据。

        比的是 **`seen` 那一份**，不是整个文件：`query_log` 每跑一次就该长一条
        （「跑过就要留痕，零产出尤其」——`query_yield.py` 整份文档都建在
        「跑了记 0、不跑记 —」这个区分上），拿它当幂等的判据会把**该长**
        的东西当重复。职位本身一个字节都不许变。
        """
        self.assertEqual(self.run_tool("--apply"), 0)
        once = json.dumps(self.read(), ensure_ascii=False, sort_keys=True)
        self.assertEqual(self.run_tool("--apply"), 0)
        twice = json.dumps(self.read(), ensure_ascii=False, sort_keys=True)
        self.assertEqual(twice, once, "第二遍不是空操作 —— 判重没生效")

    def test_a_second_run_still_leaves_a_trace(self):
        """反过来也守着：`query_log` 少了这一轮，词表会把「没跑过」和「跑了没产出」分不开。"""
        self.assertEqual(self.run_tool("--apply"), 0)
        self.run_tool("--apply")
        ql = json.loads((self.base / "seen_jobs.json").read_text("utf-8"))["query_log"]
        self.assertEqual(len(ql), 2)
        self.assertEqual([e["new"] for e in ql], [1, 0],
                         "第二轮一条新的都没有 —— 词表靠这个数分「跑了没产出」")

    def test_it_refuses_to_write_when_a_key_collides(self):
        """两条岗算出同一个键 → **整批不写盘**，非零退出。

        比任何一条规则都重要：写下去就是静默覆盖掉另一个岗，而覆盖完
        面板上看不出来——少了一个岗，别的都还在。

        ## 怎么造出这个碰撞（第一版没造出来，测试是虚的）

        碰撞要成立，得同时满足「键撞上」与「`seen_index` 没认出来」——
        前者看 `stable_id`，后者看条目的 `url`/`title`。所以库里那条必须
        **键是对的、字段是错的**：键已经是新候选该用的那个 `stable_id`，
        而它的 `url` 指向别处，于是令牌对不上、判重看不见它。
        这正是键与身份已经脱节的那一种库，而写下去就是拿新的盖掉旧的。
        """
        twin = {**HOT, "title": "另一个岗"}
        want = _cli.stable_id(twin["url"], twin["title"])
        build(self.root, hot={want: {**HOT, "url": "https://elsewhere.example/x"}},
              cold=None)
        before = (self.base / "seen_jobs.json").read_bytes()
        self.inp.write_text(json.dumps([twin], ensure_ascii=False), encoding="utf-8")
        self.assertEqual(self.run_tool("--apply"), 1, "撞车了还返回 0")
        self.assertEqual((self.base / "seen_jobs.json").read_bytes(), before,
                         "撞车还写盘了")
        # 报出来的那一行要指名是哪个键、哪个岗
        self.assertIn(want, self.buf.getvalue())
        # 新键没被占（因为这条本来就撞了），库里那条一个字没动
        v = self.read()[want]
        self.assertEqual(v["url"], "https://elsewhere.example/x")

    def test_an_ordinary_new_job_is_not_blocked_by_that(self):
        """上一条不能变成「永远写不进去」——不撞车的那批照写。"""
        twin = {**HOT, "title": "另一个岗"}
        build(self.root, hot={_cli.stable_id(HOT["url"], HOT["title"]): dict(HOT)},
              cold=None)
        self.inp.write_text(json.dumps([twin], ensure_ascii=False), encoding="utf-8")
        self.assertEqual(self.run_tool("--apply"), 0)
        self.assertEqual(len(self.read()), 2)


class TheWorkflowPointsAtIt(unittest.TestCase):
    def test_scrape_step_names_the_tool(self):
        wf = (ROOT / "workflows" / "job-scrape.md").read_text(encoding="utf-8")
        self.assertIn("tools/ingest.py", wf,
                      "Step 4 没指向入库工具 —— 判重就退回手工，而手工已经漏过一次")

    def test_it_no_longer_teaches_hand_writing_the_store(self):
        wf = (ROOT / "workflows" / "job-scrape.md").read_text(encoding="utf-8")
        for bad in ('seen_jobs.json"]["seen"] =', 'seen["', 'data["seen"][key] ='):
            self.assertNotIn(bad, wf,
                             f"又教回手写职位库了（{bad}）—— 那正是 58 个重复的来路")


if __name__ == "__main__":
    unittest.main()