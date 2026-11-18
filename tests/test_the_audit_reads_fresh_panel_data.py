# -*- coding: utf-8 -*-
"""收尾先审计后刷新，而那一档里有一条读的正是面板数据。

`/job-auto` 的收尾原来是这个顺序：

    writeback --apply          写回深评补账（改档位）
    archive --apply            出局超两周的收进存档
    outreach_header --apply    话术抬头现算
    trim_opening --apply       删开场白的铺垫
    audit_pipeline --actionable   ← 这里
    stale_materials.py
    export_web_data.py         ← 刷新面板数据

而 `--actionable` 那一档里的 `check_sellable_without_materials`（「可投档却
没材料」）读的是面板快照（`users/<活动用户>/job_scraper/dashboard/data.json`）。
上面四条 `--apply` 刚改过职位库，
**它判的是 `writeback` 补账之前的档位** —— 刚被补账升上「值得投」的岗它
看不见，刚被降下去的它照旧点名，而这一条给的处置是「去出材料」。

`AGENTS.md` 那条接缝写着「写回后刷新面板」，收尾这一段原来是反的。

## 判据钉的是性质，不是行号

「刷新在审计之前」只是这一次的修法。真正要守的是：
**`--actionable` 那一档里只要有一条读 `data.json`，收尾就必须先刷新。**
所以下面第一条现算「有没有这样的检查」，有才要求那个顺序 ——
哪天那条检查改成读快照，这条守卫会自己说「前提没了」。
"""
import ast
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import audit_pipeline as ap  # noqa: E402

AUTO = (ROOT / "workflows" / "job-auto.md").read_text(encoding="utf-8")
SRC = (ROOT / "tools" / "audit_pipeline.py").read_text(encoding="utf-8")


def _bodies() -> dict:
    """检查函数 → **代码**（docstring 不算）。

    ⚠️ 连 docstring 一起看的话，「读了 data.json」会被说明文字骗过去：
    `check_sellable_without_materials` 的说明里引着
    「选岗优先读面板那份快照…」——把代码里那一行改掉，
    判据照样认为它在读面板数据（变异当场照出来）。
    """
    tree = ast.parse(SRC)
    out = {}
    for n in tree.body:
        if not isinstance(n, ast.FunctionDef):
            continue
        body = n.body[1:] if ast.get_docstring(n) else n.body
        out[n.name] = "\n".join(ast.get_source_segment(SRC, x) or ""
                                for x in body)
    return out


def _actionable_reading_panel() -> list:
    """`--actionable` 那一档里、读了 `data.json` 的检查。

    准入判据与 `run()` 一致：**调过 `sendable_state` 的才进那一档**
    （它自己的说明：「判据是行为，不是名单 —— 一条检查调了 `sendable_state`，
    就说明它分得清哪些还来得及补」）。`live_tail` 是它的常见入口，
    但不是唯一入口 —— `check_sellable_without_materials` 直接调
    `sendable_state`，按 `live_tail` 找会把它整个漏掉（变异照出来的）。
    """
    seg = _bodies()
    out = []
    for label, fn in ap.CHECKS:
        body = seg.get(fn.__name__, "")
        if ("sendable_state" in body or "live_tail" in body) \
                and "data.json" in body:
            out.append(label)
    return out


class ThePremiseIsStillTrue(unittest.TestCase):
    """前提没了就该说出来 —— 不是默默地继续钉一个不再需要的顺序。"""

    def test_the_scan_sees_the_checks(self):
        self.assertGreater(len(ap.CHECKS), 30, "检查清单扫空了")

    def test_the_body_really_excludes_the_docstring(self):
        """判据自检：说明文字不算「读了它」。

        `check_sellable_without_materials` 的说明里引着
        「选岗优先读面板那份快照…」—— 连 docstring 一起看的话，
        把代码里那一行删掉，这条守卫照样认为它在读面板数据。
        变异「那条检查不再读面板数据」第一次就是这么溜过去的。
        """
        body = _bodies()["check_sellable_without_materials"]
        self.assertNotIn("不要照着", body, "docstring 混进来了")
        self.assertIn("data.json", body, "代码里那一行没扫到")

    def test_some_actionable_check_reads_the_panel(self):
        got = _actionable_reading_panel()
        self.assertTrue(
            got,
            "`--actionable` 那一档里已经没有读 `data.json` 的检查了 —— "
            "下面那条顺序要求的前提没了，把这一份删掉或改写")


class TheClosingRefreshesFirst(unittest.TestCase):

    def _closing(self) -> str:
        i = AUTO.index("收尾（无条件）：")
        return AUTO[i:AUTO.index("```", i)]

    def test_the_refresh_comes_before_the_audit(self):
        seg = self._closing()
        for cmd in ("python tools/export_web_data.py",
                    "python tools/audit_pipeline.py --actionable"):
            with self.subTest(cmd):
                self.assertIn(cmd, seg, f"收尾里找不到 `{cmd}`")
        self.assertLess(
            seg.index("python tools/export_web_data.py"),
            seg.index("python tools/audit_pipeline.py --actionable"),
            "收尾先审计后刷新 —— 那一档里有一条读的正是面板数据，"
            "它判的会是 writeback 补账之前的档位")

    def test_the_writers_come_before_the_refresh(self):
        """刷新要在写盘之后，否则刷的是没写回的那份。"""
        seg = self._closing()
        i = seg.index("python tools/export_web_data.py")
        for w in ("writeback.py --apply", "outreach_header.py --apply",
                  "trim_opening.py --apply"):
            with self.subTest(w):
                self.assertIn(w, seg[:i], f"`{w}` 排到刷新后面去了")

    def test_the_reason_is_recorded_next_to_it(self):
        """不写下来，下一个人会按「先审计后收工」的直觉再排回去。"""
        seg = self._closing()
        i = seg.index("python tools/export_web_data.py")
        note = seg[i:i + 500]
        self.assertIn("先刷新，再审计", note)
        self.assertIn("data.json", note)

    def test_nothing_writes_after_the_audit(self):
        """审计之后不能再有写盘的一步，否则刷新又落后了。"""
        seg = self._closing()
        after = seg[seg.index("python tools/audit_pipeline.py --actionable"):]
        self.assertNotIn("--apply", after,
                         "审计之后还有写盘的一步 —— 那面板又落后了一轮")


if __name__ == "__main__":
    unittest.main()
