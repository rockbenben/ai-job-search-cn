# -*- coding: utf-8 -*-
"""存档里的岗必须能被查重认出来 —— 别因为钥匙换了代就当它是新岗。

## 事故

同一个岗热库和存档各有一份，2026-10-12 手工删掉 58 个（数记在
`_cli.is_anonymous_employer` 的 docstring 里，由测试现算校验）。
删的是果，因还在：

`job-scrape.md` Step 4 教的查重写法是**并两边的键**
（`set(seen) | set(_cli.archived(user))`），而职位库的键换过三代
（裸 URL → `<url>#<职位名>` → `stable_id(url, 职位名)`），旧键从来没迁过。
实测活动用户：热库 993 条里 647 条旧键，存档 3163 条里 3040 条旧键。
新入库一律算 `stable_id`，于是**新键与存档里 96% 的旧键永远碰不上**。

把存档 3156 条各当成「下一轮又搜到了」模拟一遍：那两行命中 **116 条（3.7%）**。
剩下 3040 条会被当新岗插回热库、重新评一遍死数据，存档里那份原样留着 ——
两份随后各自演化（一个记 55「可以考虑」、一个记「硬门 FAIL」）。

## 判据

**键是给机器记路的，岗的身份在条目的 `url` + `title` 里。**
查重按 `_cli.seen_index()`（链接+职位名，热库 ∪ 存档）判，与
`audit_pipeline._same_job` 同一判据。所以这里全部按「换个键形态还认不认得出」来测。

同链接挂着不同职位**不算见过** —— 那是
`tests/test_one_url_can_hold_several_jobs.py` 钉过的第六条同一形状，这里跟着钉一遍，
因为新写的索引一旦只比链接，就会把 6 个不存在的重复报成真问题。
"""
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402
import rekey as R  # noqa: E402


def make_user(tmp: pathlib.Path, user="u", hot=None, cold=None):
    base = tmp / "users" / user / "job_scraper"
    base.mkdir(parents=True)
    (base / "seen_jobs.json").write_text(
        json.dumps({"seen": hot or {}}, ensure_ascii=False), encoding="utf-8")
    if cold is not None:
        (base / "archive.json").write_text(
            json.dumps({"seen": cold}, ensure_ascii=False), encoding="utf-8")
    return base


JOB = {"url": "https://www.liepin.com/a/77945647.shtml", "title": "AI产品负责人",
       "rank_verdict": "硬门 FAIL (明确排除)"}


class TheDedupeSeesEveryKeyGeneration(unittest.TestCase):
    """存档里那条岗，无论它挂着哪一代键，下一轮抓取都要认得出来。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def index_for(self, cold_key):
        make_user(self.root, hot={}, cold={cold_key: dict(JOB)})
        return _cli.seen_index("u", root=self.root)

    def test_bare_url_key(self):
        idx = self.index_for(JOB["url"])
        self.assertIn(_cli.job_token(JOB["url"], JOB["title"]), idx,
                      "存档里的裸 URL 键认不出来——会被当新岗插回")

    def test_url_hash_title_key(self):
        idx = self.index_for(f"{JOB['url']}#{JOB['title']}")
        self.assertIn(_cli.job_token(JOB["url"], JOB["title"]), idx)

    def test_stable_id_key(self):
        idx = self.index_for(_cli.stable_id(JOB["url"], JOB["title"]))
        self.assertIn(_cli.job_token(JOB["url"], JOB["title"]), idx)

    def test_the_old_key_union_would_have_missed_it(self):
        """证人：这条必须能区分新旧两种判据，否则上面几条是空跑。

        它同时是「`_cli.archived` 的 docstring 与 Step 4 别再教并键查重」的守卫——
        判据是行为（那种比法认不出这条岗），不是那段文字长什么样
        （`tests/test_a_guard_pins_behaviour_not_a_line.py` 那条棘轮）。
        """
        cold_key = JOB["url"]                     # 上一代键
        make_user(self.root, hot={}, cold={cold_key: dict(JOB)})
        cold = _cli.archived("u", root=self.root)
        new_key = _cli.stable_id(JOB["url"], JOB["title"])
        self.assertNotIn(new_key, set(cold),
                         "键 union 现在能命中了——这条证人就不再区分两种判据")
        self.assertIn(_cli.job_token(JOB["url"], JOB["title"]),
                      _cli.seen_index("u", root=self.root))

    def test_protocol_and_tracking_params_still_match(self):
        """库里存 https、这一轮锚点给 http（智联 2026-08-19 那次的形态）。"""
        cold = {JOB["url"]: dict(JOB)}
        make_user(self.root, hot={}, cold=cold)
        idx = _cli.seen_index("u", root=self.root)
        variant = ("http://www.liepin.com/a/77945647.shtml?refcode=abc123",
                   "AI产品负责人")
        self.assertIn(_cli.job_token(*variant), idx,
                      "埋点参数/协议让同一条岗看起来像新岗")

    def test_hot_and_cold_are_both_indexed(self):
        make_user(self.root, hot={"a": dict(JOB)},
                  cold={"b": {"url": "https://x/2.html", "title": "岗二"}})
        idx = _cli.seen_index("u", root=self.root)
        self.assertEqual(len(idx), 2)
        self.assertIn(_cli.job_token("https://x/2.html", "岗二"), idx)

    def test_one_url_holding_two_jobs_is_not_one_job(self):
        """同链接不同职位名 = 两个岗，不许因为链接相同就当见过。"""
        other = {"url": JOB["url"], "title": "平台产品负责人"}
        make_user(self.root, hot={}, cold={JOB["url"]: dict(JOB)})
        idx = _cli.seen_index("u", root=self.root)
        self.assertNotIn(_cli.job_token(other["url"], other["title"]), idx)


class PlanMovesKeysWithoutTouchingValues(unittest.TestCase):
    def test_plan(self):
        rows = {JOB["url"]: dict(JOB),
                "前程无忧_某公司": {"url": "", "title": "没链接的兜底键"}}
        mapping, coll = R.plan(rows)
        self.assertEqual(mapping, {JOB["url"]: _cli.stable_id(JOB["url"], JOB["title"])})
        self.assertEqual(coll, [])

    def test_two_jobs_one_key_refuses(self):
        """同一个岗被存了两份（旧键不同、身份相同）时不许覆盖掉一条。"""
        rows = {"k1": dict(JOB), "k2": dict(JOB)}
        mapping, coll = R.plan(rows)
        self.assertTrue(coll, "两条算出同一个键，却没报撞车")
        self.assertNotIn("k1", mapping)
        self.assertNotIn("k2", mapping)


class TheMigrationIsSafe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.base = make_user(
            self.root,
            hot={JOB["url"]: dict(JOB, rank_score=55),
                 "https://x/2.html#岗二": {"url": "https://x/2.html", "title": "岗二"}},
            cold={"https://x/3.html#岗三": {"url": "https://x/3.html", "title": "岗三"}})
        (self.base / "user_state.json").write_text(
            json.dumps({JOB["url"]: {"decision": "skipped", "date": "2026-08-21"}},
                       ensure_ascii=False), encoding="utf-8")
        # 顶层那几个键不是 seen 的邻居，是数据本身
        data = json.loads((self.base / "seen_jobs.json").read_text(encoding="utf-8"))
        data["query_log"] = [{"query": "Agent产品经理", "count": 3}]
        data["archived"] = {"count": 1, "date": "2026-10-12"}
        _cli.atomic_write(self.base / "seen_jobs.json",
                          json.dumps(data, ensure_ascii=False, indent=1))

    def _rows(self, name):
        f = _cli.seen_of(json.loads((self.base / name).read_text(encoding="utf-8")))
        return f

    def test_apply_moves_keys_and_keeps_values(self):
        R.run("u", True, root=self.root)
        hot = self._rows("seen_jobs.json")
        self.assertEqual(set(hot), {_cli.stable_id(JOB["url"], JOB["title"]),
                                    _cli.stable_id("https://x/2.html", "岗二")})
        self.assertEqual(hot[_cli.stable_id(JOB["url"], JOB["title"])]["rank_score"], 55)
        self.assertEqual(set(self._rows("archive.json")),
                         {_cli.stable_id("https://x/3.html", "岗三")})

    def test_top_level_keys_survive(self):
        """`query_log` / `archived` 是词表与归档计数，被顺手抹掉没人会当场发现。"""
        R.run("u", True, root=self.root)
        data = json.loads((self.base / "seen_jobs.json").read_text(encoding="utf-8"))
        self.assertEqual(data["query_log"], [{"query": "Agent产品经理", "count": 3}])
        self.assertEqual(data["archived"]["count"], 1)

    def test_the_panel_marks_follow_the_key(self):
        R.run("u", True, root=self.root)
        st = _cli.load_user_state(self.base / "seen_jobs.json")
        self.assertEqual(list(st), [_cli.stable_id(JOB["url"], JOB["title"])])
        self.assertEqual(st[_cli.stable_id(JOB["url"], JOB["title"])]["decision"],
                         "skipped")

    def test_running_twice_changes_nothing(self):
        R.run("u", True, root=self.root)
        before = (self.base / "seen_jobs.json").read_text(encoding="utf-8")
        r = R.run("u", True, root=self.root)
        self.assertEqual(sum(len(s["mapping"]) for s in r["stores"]), 0)
        self.assertEqual((self.base / "seen_jobs.json").read_text(encoding="utf-8"),
                         before)

    def test_dry_run_writes_nothing(self):
        before = {p.name: p.read_text(encoding="utf-8")
                  for p in self.base.glob("*.json")}
        r = R.run("u", False, root=self.root)
        self.assertTrue(r["stores"])
        for p in self.base.glob("*.json"):
            self.assertEqual(p.read_text(encoding="utf-8"), before[p.name])

    def test_a_collision_refuses_the_whole_file(self):
        """同一个岗被存了两份时，**一份都不写**——不能在这里用覆盖把它咽下去。"""
        dup = dict(JOB, rank_score=72)
        hot = json.loads((self.base / "seen_jobs.json").read_text(encoding="utf-8"))
        hot["seen"]["https://x/9.html#" + JOB["title"]] = dup
        # 让第二条与第一条算出同一个键：同链接同职位名，只是键不同
        hot["seen"]["https://x/9.html#" + JOB["title"]]["url"] = JOB["url"]
        _cli.atomic_write(self.base / "seen_jobs.json",
                          json.dumps(hot, ensure_ascii=False, indent=1))
        before = (self.base / "seen_jobs.json").read_text(encoding="utf-8")
        r = R.run("u", True, root=self.root)
        self.assertTrue(r["collisions"], "两条同身份的岗没报撞车")
        self.assertEqual((self.base / "seen_jobs.json").read_text(encoding="utf-8"),
                         before, "报了撞车还是写了盘")


if __name__ == "__main__":
    unittest.main()
