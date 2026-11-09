# -*- coding: utf-8 -*-
"""写用户的原始数据不许先截断文件。

## 一处方向反了的不对称

2026-08-13 第 9 轮检查扫出来：

    web/public/data.json                 派生快照，丢了跑一次导出就回来   → **原子写**
    users/*/job_scraper/seen_jobs.json   1246 条职位，唯一副本            → 裸 write_text
    users/*/job_search_tracker.csv       76 条投递记录，唯一副本          → 裸 write_text

`Path.write_text` 走 `open(mode="w")`：**先把文件截断成 0 字节，再写内容**。
中途被打断——Ctrl+C、断电、磁盘满、进程被杀——文件就停在空的或半截的状态。

`data.json` 那边早就用了临时文件加 `os.replace`，注释写着理由（「并发的读会拿到
半截 JSON」）。**保护做在了丢得起的那一份上，丢不起的那两份反而裸着。**

而这个仓库的日常恰恰是「长跑的命令 + 随时可能 Ctrl+C」：`/job-auto` 一跑几十分钟，
中间反复写 `seen_jobs.json`。
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import _cli  # noqa: E402

#: 允许出现裸 `write_text` 的文件——**豁免必须写理由**，理由站不住就不许进来。
#:
#: 这里原来是反着的：列一个「写用户数据的工具」OWNERS 元组，逐个查。
#: 第 10 轮复核当场翻车：名单漏了 `query_yield.py`——它写回 `search-queries.md`，
#: 里面是用户**亲手校准**的搜索词优先级，正是丢不起的那类。
#: 固定名单的失效方式和「按来源分流的守卫」一模一样：新来的、没列进去的，
#: 静默漏过（第 1 轮、第 6 轮各抓过一次同形状）。**改成全量扫 + 显式豁免。**
ALLOW_FILES = {
    "_cli.py": "atomic_write 自己要写临时文件，它是机制本身",
    "export_web_data.py": "tmp.write_text + os.replace，本来就是原子写的范例",
    "build_dashboard.py": "单页 HTML 报告是派生产物，丢了重跑一次就回来",
    "doctor.py": "约定只读不写；真出现写盘是另一类错，由 test_doctor 管",
    "lint_skills.py": "lint 输出的是修复建议文本，不碰用户数据",
}


class AtomicWriteBehaves(unittest.TestCase):

    def test_it_replaces_the_content(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.json"
            p.write_text("旧", encoding="utf-8")
            _cli.atomic_write(p, "新")
            self.assertEqual(p.read_text(encoding="utf-8"), "新")

    def test_it_leaves_no_temp_file_behind(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.json"
            _cli.atomic_write(p, "内容")
            self.assertEqual(sorted(f.name for f in Path(d).iterdir()), ["x.json", "x.json.lock"])

    def test_the_temp_file_sits_next_to_the_target(self):
        """跨盘 `os.replace` 会退化成拷贝、失去原子性——临时文件必须同目录。"""
        src = (ROOT / "tools" / "_cli.py").read_text(encoding="utf-8")
        seg = src[src.index("def atomic_write"):]
        self.assertIn("with_name", seg,
                      "临时文件没有跟目标同目录，跨盘时 os.replace 不再原子")
        self.assertIn("os.replace", seg.replace("_os.replace", "os.replace"))

    def test_newline_is_passed_through(self):
        """CSV 必须 `newline=""`，否则台账每写一次多一堆空行。"""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.csv"
            _cli.atomic_write(p, "a,b\r\n1,2\r\n", newline="")
            self.assertEqual(p.read_bytes().count(b"\r\n"), 2,
                             "换行被转换了——newline 没透传")


    def test_it_retries_when_windows_holds_the_target_open(self):
        """Windows 上 `os.replace` 会撞「目标正被读」——要退避重试，不能一次就放弃。

        POSIX 的 rename 可以覆盖正被打开的文件；Windows 不行（Python 的 `open()`
        不带 `FILE_SHARE_DELETE`）。2026-08-13 换成原子写的当天，测试里那个
        「并发点几下按钮」的用例立刻炸出两次 `PermissionError: [WinError 32]`——
        一个线程在读台账，另一个在替换它。面板是 ThreadingHTTPServer，
        用户连点几下就是这个形状。

        **重试完还不行必须抛出去**，不许假装成功：静默吞掉会让盘上和页面上各说各话。
        """
        from unittest import mock
        calls = {"n": 0}
        real_replace = os.replace       # 必须先存下来——patch 之后再调就是无限递归

        def flaky(src, dst):
            calls["n"] += 1
            if calls["n"] < 3:               # 前两次撞上，第三次成功
                raise PermissionError(32, "另一个程序正在使用此文件")
            return real_replace(src, dst)

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.csv"
            p.write_text("旧", encoding="utf-8")
            # `atomic_write` 里是 `import os as _os` —— 拿到的是同一个模块对象，
            # patch 模块属性对它一样生效。
            with mock.patch("os.replace", side_effect=flaky):
                _cli.atomic_write(p, "新")
            self.assertGreaterEqual(calls["n"], 3, "没有重试，一次失败就放弃了")
            self.assertEqual(p.read_text(encoding="utf-8"), "新")

    def test_it_gives_up_loudly_rather_than_silently(self):
        """一直失败就要抛——静默成功比失败更危险。"""
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.csv"
            p.write_text("旧", encoding="utf-8")
            with mock.patch("os.replace",
                            side_effect=PermissionError(32, "一直占着")):
                with self.assertRaises(PermissionError):
                    _cli.atomic_write(p, "新")
            self.assertEqual(p.read_text(encoding="utf-8"), "旧",
                             "替换失败了，旧数据必须原封不动")

    def test_an_interrupted_write_leaves_the_old_file_intact(self):
        """**关键性质**：写到一半崩溃，旧文件必须原封不动。

        用子进程模拟「写到一半被杀」：进程在 `atomic_write` 内部写临时文件时退出，
        目标文件应当还是旧内容——而不是空文件。
        """
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "seen.json"
            old = json.dumps({"seen": {"a": 1}}, ensure_ascii=False)
            target.write_text(old, encoding="utf-8")
            code = (
                "import sys, os\n"
                f"sys.path.insert(0, {str(ROOT / 'tools')!r})\n"
                "import _cli\n"
                "from pathlib import Path\n"
                "p = Path(%r)\n" % str(target) +
                "orig = Path.write_text\n"
                "def boom(self, *a, **k):\n"
                "    orig(self, *a, **k)\n"
                "    os._exit(9)          # 临时文件写完了，替换之前被杀\n"
                "Path.write_text = boom\n"
                "_cli.atomic_write(p, '新内容会丢掉')\n"
            )
            r = subprocess.run([sys.executable, "-c", code],
                               capture_output=True, timeout=60)
            self.assertEqual(r.returncode, 9, "子进程没走到预期的中断点")
            self.assertEqual(target.read_text(encoding="utf-8"), old,
                             "写到一半被杀，旧数据没保住——这正是裸 write_text 的病")


class NoToolTruncatesUserData(unittest.TestCase):
    """`tools/` 下**任何文件**都不许裸 `write_text`——全量扫，不认名单。"""

    def test_no_bare_write_text_anywhere_in_tools(self):
        bad = []
        for p in sorted((ROOT / "tools").glob("*.py")):
            if p.name in ALLOW_FILES:
                continue
            for i, ln in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if ".write_text(" not in ln or ln.lstrip().startswith("#"):
                    continue
                if "atomic_write" in ln or "tmp.write_text" in ln:
                    continue
                bad.append(f"{p.name}:{i} {ln.strip()[:76]}")
        self.assertEqual(bad, [],
                         "这些地方写盘会先把文件截断，中途崩溃就丢数据（要么换 "
                         "_cli.atomic_write，要么进 ALLOW_FILES 并写明理由）：\n  "
                         + "\n  ".join(bad))

    def test_every_exemption_still_earns_it(self):
        """豁免名单不能变成垃圾场：列出的文件得存在，理由那格不能是空话。"""
        for name, why in ALLOW_FILES.items():
            with self.subTest(file=name):
                self.assertTrue((ROOT / "tools" / name).is_file(),
                                f"{name} 已经不存在了——豁免也该删，别留死条目")
                self.assertGreaterEqual(len(why), 8, f"{name} 的豁免理由太敷衍")

    def test_the_derived_snapshot_stays_atomic_too(self):
        """`data.json` 那边本来就是对的，别在统一写法时把它改回去。"""
        src = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
        self.assertIn("os.replace", src)


if __name__ == "__main__":
    unittest.main()
