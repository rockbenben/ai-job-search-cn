# -*- coding: utf-8 -*-
"""拿探针用户真跑一遍工具，跑完盘上不许多出东西。

## 实测代价（2026-09-03，发布前）

历史上 `export_web_data` 不管传哪个 `--user`，都写同一份
`web/public/data.json`（2026-11-09 起改为各写各的 `job_scraper/dashboard/`，
`_live.PANEL_SNAPSHOT` 跟着改成按活动用户解析）。两个模块要拿探针用户真跑它
（`test_one_bad_row_does_not_crash_everything`、`test_the_file_he_saved_in_excel`），
两个都记得「跑完把快照写回去」——
**两个都漏了同一半：干净 clone 上原来就没有快照，于是什么也没写回，
探针那份 1 个岗、却标着 `isRealData: true` 的假快照留在了盘上。**

一次跑不出问题（写它的模块按字母序在后面，读快照的那些在前面，当轮已跑完）。
代价在**第二次跑**：

    干净 clone，第一遍   Ran 7340, OK (skipped=406)
    同一棵树，第二遍     FAILED (failures=8, errors=12)

而 快照目录在 `users/` 下（整目录 gitignore）—— 「本来没有」和「留下一个假的」
在 `git status` 里长得一模一样。**只有再跑一遍才看得见。**

## 为什么判据钉在「谁能碰那份快照」上

先只修了两份里的一份，第二遍从 `failures=8` 降到 `failures=6` ——
**另一份照样漏**。同一个 dance 抄两遍，漏的是同一半；抄三遍还会漏。
所以还原收进 `_live.keep_panel_snapshot` 一处，这里钉住「别再抄第四份」。
"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
sys.path.insert(0, str(TESTS))

#: **共享**的那一份，也就是挂在 `ROOT` 底下的。
#: `tmp / "web" / "public" / "data.json"` 这种是夹具自己的临时目录，随便写 ——
#: 判据不带 `ROOT` 前缀的话，五个用临时目录的模块会被一起误报（实测过）。
SHARED = r'ROOT\s*/\s*"web"\s*/\s*"public"\s*/\s*"data\.json"'

#: 给它起了名字之后再动它 —— 原来那两份就是这么写的（`SNAP = ROOT / …`
#: 一行，`SNAP.write_bytes(...)` 在另一行），**只按单行扫根本抓不到**。
ALIAS = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*" + SHARED, re.M)

#: 写盘/删除的动作。读（`read_bytes` / `read_text` / `is_file`）不算 ——
#: 读真实快照的判据有几十条，它们本来就该读。
WRITE_VERBS = r"(?:write_bytes|write_text|unlink)"


def _modules():
    for p in sorted(TESTS.glob("test_*.py")):
        yield p, p.read_text(encoding="utf-8")


def _snapshot_writes(text: str) -> list:
    """这份源码里「动了共享快照」的那几行。"""
    hits = [m.group(0).strip() for m in
            re.finditer(r"^.*\(\s*" + SHARED + r"\s*\)\s*\." + WRITE_VERBS
                        + r"\s*\(.*$", text, re.M)]
    for name in set(ALIAS.findall(text)):
        hits += [m.group(0).strip() for m in
                 re.finditer(r"^.*\b" + re.escape(name) + r"\s*\."
                             + WRITE_VERBS + r"\s*\(.*$", text, re.M)]
    return hits


class OnlyOnePlaceTouchesTheSharedSnapshot(unittest.TestCase):

    def test_the_scan_sees_the_helper_being_used(self):
        """控制用例：真有模块在用那个辅助，否则下面那条是空跑。"""
        users = [p.name for p, t in _modules() if "keep_panel_snapshot" in t]
        self.assertGreaterEqual(
            len(users), 2,
            f"只有 {users} 在用 keep_panel_snapshot —— 判据多半失效了")

    def test_no_test_module_writes_the_snapshot_itself(self):
        """自己写回/删除那份快照 = 又抄了一份 dance，迟早又漏那一半。"""
        bad = [f"{p.name}: {line}"
               for p, text in _modules() for line in _snapshot_writes(text)]
        self.assertEqual(
            bad, [],
            "这些模块自己动共享面板快照，没走 `_live.keep_panel_snapshot`：\n  "
            + "\n  ".join(bad)
            + "\n改法：setUpModule 里 `_restore = keep_panel_snapshot()`，"
              "tearDownModule 里 `_restore()`。")

    def test_the_detector_can_actually_fail(self):
        """判据自检：把原来那种写法喂给它，必须认出来。

        钉的正是**跨行**那一种（`SNAP = ROOT / …` 一行、`SNAP.write_bytes(...)`
        在另一行）—— 第一版判据只按单行扫，对它完全瞎，却对五个用临时目录的
        模块误报。绿得毫无道理，红得也毫无道理。
        """
        old = ('SNAP = ROOT / "web" / "public" / "data.json"\n'
               'def tearDownModule():\n'
               '    SNAP.write_bytes(_SAVED["data"])\n')
        self.assertTrue(_snapshot_writes(old), "认不出原来那种写法")

    def test_a_temp_dir_snapshot_is_not_reported(self):
        """反向：夹具在自己的临时目录里写 data.json 是正常的，不许误报。"""
        fixture = '(tmp / "web" / "public" / "data.json").write_text(payload)\n'
        self.assertEqual(_snapshot_writes(fixture), [],
                         "临时目录里的夹具被当成共享快照了")


class TheHelperHandlesBothMachines(unittest.TestCase):
    """两种机器各钉一条 —— 漏掉的正是「本来没有」那一种。"""

    def setUp(self):
        from _live import keep_panel_snapshot, PANEL_SNAPSHOT
        self.keep, self.snap = keep_panel_snapshot, PANEL_SNAPSHOT
        self.existed = self.snap.is_file()
        self.before = self.snap.read_bytes() if self.existed else None

    def tearDown(self):
        if self.before is None:
            self.snap.unlink(missing_ok=True)
        else:
            self.snap.write_bytes(self.before)

    def _fake(self, body=b'{"probe": 1}'):
        self.snap.parent.mkdir(parents=True, exist_ok=True)
        self.snap.write_bytes(body)

    def test_a_snapshot_that_was_not_there_is_removed(self):
        """干净 clone：原来没有 → 跑完必须删掉，别留一份探针数据。"""
        self.snap.unlink(missing_ok=True)
        restore = self.keep()
        self._fake()
        restore()
        self.assertFalse(self.snap.is_file(),
                         "原来没有快照，跑完却留下一份 —— 下次跑就读到它了")

    def test_a_snapshot_that_was_there_comes_back_byte_for_byte(self):
        """本机：原来有 → 跑完必须原样写回，一个字节都不许变。"""
        self._fake(b'{"real": "\xe4\xb8\x80\xe5\x85\xb1 1590 \xe4\xb8\xaa"}')
        original = self.snap.read_bytes()
        restore = self.keep()
        self._fake(b'{"probe": 1}')
        restore()
        self.assertEqual(self.snap.read_bytes(), original,
                         "真实快照被探针那份盖掉了")


if __name__ == "__main__":
    unittest.main()
