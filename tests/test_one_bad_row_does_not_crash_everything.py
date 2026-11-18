# -*- coding: utf-8 -*-
"""职位库里一条读不出来的记录，把九个工具打成栈回溯。

`seen_jobs.json` 是人和 AI 都写的（`/job-rank --skip` 那几条 schema 就是执行者
手写 JSON）。一条 `null`、一个字符串、一个列表 —— 每一种都让下游的
`e.get(...)` 当场 `AttributeError`。

实测 2026-09-01，喂一条 `null`，16 个工具里 **9 个吐栈回溯**：

    archive · audit_pipeline · prescreen · query_yield · stale_materials
    writeback · export_web_data · outreach_header · doctor

`export_web_data` 崩掉 = **面板整个出不来**；`doctor` 崩掉更糟 —— 它是会话第一条
命令，契约写着「任何状态下都能跑（包括 `.active_user` 不存在、`users/` 为空、
profile 还是占位符）」。

## 判据分两种，因为契约不同

- 八个工具走 `_cli.stop_on_unreadable_rows`：**干净地停下**，退出码 2，
  说清是哪几个键、文件在哪、这几条没被改动。
  **不替他删** —— `seen_of` 按契约返回原字典的引用，在那儿滤掉等于下一次
  写盘就把那几行从盘上抹掉，而坏成什么样只有他自己知道。
- `doctor` 不能停：摘掉那几条、把数报出来、接着走完。

退出码 2 与「渠道名打错」「`--today` 不是日期」同一个约定：
**1 是「这件事此刻不能做」，2 是「输入坏了，改了再来」。**

## 另外两条不是「整行坏」，是「一个字段坏」

- `query_yield.collect` 的循环少一个 `isinstance` 守卫，而同文件另外两处都有；
- 库里 `rank_score` 写成字符串时，`resolve_score` 的兜底那一支把原值直接递出去，
  导出器在 `jobs.sort(key=... -(j["score"] or 0))` 上 `TypeError` —— 而同一个
  函数上面那一支早就 `try/except` 转过了。转不动就当没分，面板显示「还没评分」。

> `isinstance(v, dict)` 这个判断此刻在那九个文件里散着写了 **69 遍**，而九个
> 还是都崩了 —— 散写的守卫盖不全，正是它该收成一处的理由。
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
from _live import keep_panel_snapshot  # noqa: E402
import _cli  # noqa: E402
import build_dashboard as bd  # noqa: E402

USER = "探针用户_坏记录"

GOOD = {"url": "https://www.liepin.com/job/1.shtml", "title": "产品经理",
        "company": "某公司", "status": "ranked", "rank_score": 70,
        "rank_verdict": "值得投", "first_seen": "2026-08-01",
        "portal": "liepin-search"}

#: 整行读不出来的几种形状。
BROKEN = {"null": None, "字符串": "我不是字典", "列表": []}

#: 碰这个文件、且会因为一条坏记录崩掉的那几个。
STOPPERS = ("archive", "audit_pipeline", "prescreen", "stale_materials",
            "writeback", "export_web_data", "outreach_header")
#: 契约不许停的那一个。
SURVIVORS = ("doctor", "query_yield")


def _store(extra):
    d = ROOT / "users" / USER
    shutil.rmtree(d, ignore_errors=True)
    (d / "job_scraper").mkdir(parents=True)
    (d / "profile").mkdir(parents=True)
    (d / "job_scraper" / "seen_jobs.json").write_text(
        json.dumps({"seen": {"a": dict(GOOD), **extra}}, ensure_ascii=False),
        encoding="utf-8")


def run(tool):
    r = subprocess.run([sys.executable, str(ROOT / "tools" / f"{tool}.py"),
                        "--user", USER], cwd=ROOT, capture_output=True,
                       text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    return r.returncode, (r.stdout or "") + (r.stderr or "")


_restore = None


def setUpModule():
    """把面板快照护住。

    ⚠️ **`export_web_data` 会把快照写进你传的那个 `--user` 的
    `job_scraper/dashboard/data.json`（2026-11-09 起按用户分，此前是全用户
    共用一份）。** 这份测试要跑它（它正是崩得最狠的那个：
    一条坏记录 = 面板整个出不来），跑完那份快照就变成探针用户的 1 个岗 ——
    于是所有读真实快照的测试（那一堆 `TheSignalItLeansOnIsReal`）
    集体失真：实测这一脚 9 红 + 跳过从 28 涨到 81。

    上一轮刚在渠道账本上栽过同一件事（拿真数据当夹具）。这次是共享快照，
    换了个文件，同一个形状。

    还原分两种机器（本机有 / 干净 clone 没有），判据与实测代价都在
    `_live.keep_panel_snapshot` 的 docstring 里 —— **收在那里而不是抄一份**：
    这个 dance 原来在两个模块里各写了一遍，两遍漏的是同一半。
    """
    global _restore
    _restore = keep_panel_snapshot()


def tearDownModule():
    shutil.rmtree(ROOT / "users" / USER, ignore_errors=True)
    _restore()


class TheJudgeIsOne(unittest.TestCase):

    def test_it_finds_the_broken_ones(self):
        seen = {"a": dict(GOOD), **{k: v for k, v in BROKEN.items()}}
        self.assertEqual(sorted(_cli.unreadable_rows(seen)),
                         sorted(BROKEN), "没认全")

    def test_a_clean_store_has_none(self):
        self.assertEqual(_cli.unreadable_rows({"a": dict(GOOD)}), [])

    def test_it_survives_a_store_that_is_not_a_dict(self):
        for junk in (None, [], "x", 3):
            with self.subTest(junk=junk):
                self.assertEqual(_cli.unreadable_rows(junk), [])


class NobodyShowsATraceback(unittest.TestCase):

    def test_every_tool_survives_every_shape(self):
        for tag, bad in BROKEN.items():
            _store({"b": bad})
            for tool in STOPPERS + SURVIVORS:
                with self.subTest(shape=tag, tool=tool):
                    _code, out = run(tool)
                    self.assertNotIn("Traceback", out,
                                     f"{tool} 撞上一条「{tag}」就甩栈回溯")

    def test_the_control_group_is_clean(self):
        """**先证明夹具本身跑得通。** 好数据上就崩的话，上面那条测的是别的事。"""
        _store({})
        for tool in STOPPERS + SURVIVORS:
            with self.subTest(tool=tool):
                _code, out = run(tool)
                self.assertNotIn("Traceback", out, f"{tool} 在干净数据上就崩")


class TheContractDecidesStopOrCarryOn(unittest.TestCase):

    def test_the_eight_stop_cleanly(self):
        _store({"b": None})
        for tool in STOPPERS:
            with self.subTest(tool=tool):
                code, out = run(tool)
                self.assertEqual(code, 2, f"{tool} 没停下：{out[:80]}")
                self.assertIn("读不出来", out)
                self.assertIn("没有被改动", out, "没说清那几条动没动过")

    def test_the_doctor_carries_on(self):
        """会话第一条命令，契约是「任何状态下都能跑」。"""
        _store({"b": None})
        code, out = run("doctor")
        self.assertEqual(code, 0, out[-200:])
        self.assertIn("读不出来", out, "摘掉了却不说 —— 后面每个数都少算了它")
        self.assertIn("下一步", out, "崩没崩另说，它得照样给出下一步")

    def test_the_judge_does_not_touch_the_rows(self):
        """**不替他删。** 坏成什么样只有他知道，删不删不归工具判。

        `seen_of` 按契约返回**原字典的引用**（「就地改完把外层 `store` 写回去
        仍然对」），所以在这儿删一下，下一个写盘的工具就会把那几行从盘上抹掉。
        判据直接钉这一条：它拿到的那个 dict，跑完必须一个键都没少。

        ⚠️ **别用「跑几个工具再看盘上」来验这件事。** 第一版是那么写的 ——
        而停下的那几个本来就不写盘，会写的那几个在这份夹具上没东西可写，
        于是「在内存里删掉」这种改法对盘上毫无影响，断言压根红不了
        （变异实测当场证明它空转）。
        """
        seen = {"a": dict(GOOD), "b": None, "c": "我不是字典"}
        with self.assertRaises(SystemExit):
            _cli.stop_on_unreadable_rows(seen, "某路径")
        self.assertEqual(sorted(seen), ["a", "b", "c"], "它把坏记录删了")
        self.assertIsNone(seen["b"])

    def test_the_rows_are_still_on_disk_after_a_round(self):
        """再兜一层：真跑一圈之后，盘上那几行还在。"""
        _store({"b": None})
        for tool in STOPPERS + SURVIVORS:
            run(tool)
        raw = json.loads(
            (ROOT / "users" / USER / "job_scraper" / "seen_jobs.json")
            .read_text(encoding="utf-8"))
        self.assertIn("b", raw["seen"], "有人把那条坏记录从盘上抹掉了")


class ABadFieldIsNotABadRow(unittest.TestCase):
    """整行坏 → 停；一个字段坏 → 当它没有，别把整页数据带走。"""

    def test_a_string_score_becomes_no_score(self):
        got = bd.resolve_score({"rank_score": "七十", "rank_verdict": "值得投"},
                               None)
        self.assertIsNone(got[0], "字符串分数递出去了，导出器排序时会炸")
        self.assertEqual(got[1], "值得投", "判词不该跟着丢")

    def test_a_real_score_still_comes_through(self):
        self.assertEqual(bd.resolve_score({"rank_score": 70}, None)[0], 70)
        self.assertEqual(bd.resolve_score({"rank_score": "70"}, None)[0], 70)

    def test_zero_is_a_score(self):
        """0 是合法分数 —— 别被 `or` 吃掉（同函数上面那一支记着这一课）。"""
        self.assertEqual(bd.resolve_score({"rank_score": 0}, None)[0], 0)

    def test_the_export_still_builds_with_a_bad_score(self):
        _store({"b": dict(GOOD, url="https://x/2", rank_score="七十")})
        code, out = run("export_web_data")
        self.assertEqual(code, 0, out[-200:])
        self.assertNotIn("Traceback", out)


if __name__ == "__main__":
    unittest.main()


class TheFilesNextToItAreGuardedToo(unittest.TestCase):
    """`seen_jobs.json` 旁边那几份 —— 同一个形状，同一批工具。

    实测 2026-09-01（上一轮扫完职位库之后接着扫）：

        叠加层 user_state.json 里一条 `null`
            → export_web_data 💥（面板整个出不来）、archive 💥（在 /job-auto 收尾里）
        勾选框 portals.json 写成 `[]`
            → export_web_data 💥

    两处都是**外层判了、里层没判**：

    - `load_user_state` 判了「整份是不是字典」，没判每一行；而读的人一律写
      `ustate.get(k, {}).get("decision")` —— 那个默认值只在**键不存在**时生效，
      键在而值是 `null` 就直接 `AttributeError`。
    - `portals_enabled` 的说明写着「缺文件 = 全开——没设置过不等于全关」，
      而它只盖住了「读不出来」，没盖住「读出来是个列表」。

    **台账那一份是干净的**：少一列、多一列、没表头、整个空、日期乱写，
    五种形状 16 个工具一个都没崩 —— 那份文件用户自己会用 Excel 改，
    早就被当成不可信输入处理了。
    """

    def test_a_null_row_in_the_overlay_becomes_an_empty_dict(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            sj = pathlib.Path(d) / "seen_jobs.json"
            sj.write_text("{}", encoding="utf-8")
            _cli.user_state_path(sj).write_text(
                json.dumps({"a": None, "b": {"decision": "skipped"},
                            "c": "我不是字典"}, ensure_ascii=False),
                encoding="utf-8")
            got = _cli.load_user_state(sj)
        self.assertEqual(got["a"], {}, "null 那一行没被收住")
        self.assertEqual(got["c"], {}, "字符串那一行没被收住")
        self.assertEqual(got["b"], {"decision": "skipped"}, "好的那一行不该动")

    def test_the_keys_are_kept(self):
        """换成空字典，**不删键** —— 同职位库那边一条原则。"""
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            sj = pathlib.Path(d) / "seen_jobs.json"
            sj.write_text("{}", encoding="utf-8")
            _cli.user_state_path(sj).write_text('{"a": null}', encoding="utf-8")
            self.assertIn("a", _cli.load_user_state(sj))

    def test_a_malformed_portals_file_means_all_on(self):
        """解得开但不是字典 = 没设置过 = 全开（那句话本来就写在它上面）。"""
        import export_web_data as ex
        import tempfile
        import unittest.mock as _m
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            (root / "users" / "u" / "job_scraper").mkdir(parents=True)
            (root / "users" / "u" / "job_scraper" / "portals.json").write_text(
                "[]", encoding="utf-8")
            with _m.patch.object(ex, "ROOT", root):
                got = ex.portals_enabled("u")
        self.assertTrue(got and all(got.values()),
                        "坏文件被读成「全关」—— 那会让整轮一家都不抓")

    def test_a_real_portals_file_still_switches_things_off(self):
        """反向支点：真设置过的还得听他的。"""
        import export_web_data as ex
        import tempfile
        import unittest.mock as _m
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            (root / "users" / "u" / "job_scraper").mkdir(parents=True)
            (root / "users" / "u" / "job_scraper" / "portals.json").write_text(
                json.dumps({"BOSS": False}), encoding="utf-8")
            with _m.patch.object(ex, "ROOT", root):
                got = ex.portals_enabled("u")
        self.assertFalse(got["BOSS"], "他关掉的那家又被打开了")
