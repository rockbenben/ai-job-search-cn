"""哪些命令要用 Python，依赖表里得说全。

## 表里说「只有总览页要」，实际有一串命令在调 Python

`README.md` 与 `SETUP.md` 的依赖表原来都把 Python 归成「要看总览页就装」。
实测 `workflows/` 里 `python tools/…` 的调用：

| 命令 | 调的是什么 | 缺了会怎样 |
|---|---|---|
| `/job-rank` | `prescreen.py`、`jd_store.py` | 不做预筛淘汰（队列排不空）、每轮重抓 JD |
| `/job-scrape` | `jd_store.py` | 抓到的 JD 正文不入库，下轮重抓 |
| `/job-outcome` | `followups.py` | 「该催哪几个」只能手算——而该文件明写「**用工具算，不要手算**」，并列了三种静默错法 |
| `/job-upskill` | `gap_split.py` | 专业能力/业务域四格分不出来 |
| `/job-dashboard` | `serve.py` | 整条命令跑不了 |
| `/job-setup` | `query_yield.py`、`gap_split.py` | `--section search` 复跑「改搜索词」那节没有词级战绩可看，改词只能凭感觉 |

**而且没有任何工作流写过 no-Python 的降级路径**（`AGENTS.md` 只说了「没有 Python
时跳过自检」，那讲的是 `doctor.py`）。用户照 README 跳过 Python，走到 `/job-rank`
Step 1.7 时会撞上一句「跑 `python tools/prescreen.py`」。

这条不是要求把 Python 变成必装——`/job-apply` 一行 Python 都不调；`/job-setup`
也只在 `--section search` 复跑「改搜索词」那一节时用 Python 读每个词抓过的真实
战绩（`query_yield.py`）与跑偏情况（`gap_split.py`），没有它这一节照问，词只能
用户自己想（`workflows/job-setup.md`：「再让他从零想关键词是浪费」）。是要求
**表里别少说**：少说的代价是用户在流程中途才发现，而那时他已经投入了。

## 判据

README 在 Python 用途摘要旁链接到 SETUP 的完整清单。测试逐项比较工作流里的
Python 调用者与清单中的命令，避免说明文案或表头改写时误报。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CALL = re.compile(r"python tools/[a-z_]+\.py")


def commands_needing_python() -> set:
    """哪些工作流会调 Python 工具。**现扫，不写死清单。**"""
    out = set()
    for p in (ROOT / "workflows").glob("*.md"):
        if CALL.search(p.read_text(encoding="utf-8")):
            out.add(p.stem)
    return out


def python_uses(doc: Path) -> str:
    """完整用途清单集中在安装指南的 Python 小节。"""
    text = doc.read_text(encoding="utf-8")
    start = text.index("### Python 用途")
    return text[start:].split("\n### ", 1)[0]


class ThePythonRowNamesEveryCommandThatUsesIt(unittest.TestCase):

    DOCS = ("SETUP.md",)

    def test_the_scan_finds_callers(self):
        """控制用例：真扫到了调 Python 的工作流。"""
        cmds = commands_needing_python()
        self.assertGreaterEqual(
            len(cmds), 4,
            f"只扫到 {sorted(cmds)} 在调 python tools/——判据大概失效了")

    def test_readme_links_to_the_complete_python_uses(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("(SETUP.md#python-用途)", readme)
        self.assertIn("Python 3.10+", python_uses(ROOT / "SETUP.md"))

    def test_every_caller_is_named_in_the_row(self):
        """逐项核对工作流调用者，完整清单漏掉命令就失败。"""
        cmds = commands_needing_python()
        bad = []
        for name in self.DOCS:
            row = python_uses(ROOT / name)
            documented = set(re.findall(r"/job-[a-z-]+", row))
            for c in sorted(cmds):
                if f"/{c}" not in documented:
                    bad.append(f"{name}: 没提 `/{c}`")
        self.assertEqual(
            bad, [],
            "这些命令会调 Python 工具，依赖表却没说：\n  " + "\n  ".join(bad)
            + "\n用户照表跳过 Python，走到流程中途才撞上「跑 `python tools/…`」——"
            "\n而那时他已经投入了。少说不等于没有。"
            + f"\n实际在调的：{sorted(cmds)}")

    def test_python_stays_optional_for_the_core_two(self):
        """反向：`/job-apply` 一个 Python 工具都不调；`/job-setup` 只在
        `--section search` 复跑那节读词级战绩，第一次填资料没有它也走得完。
        再多一环，「强烈建议」就得改口「必装」。

        这条以前拿裸的 `setup` / `apply` 去比 `job-` 开头的命令名——那个集合里
        永远没有这两个字，等于没判任何东西。换成真名才照见现实：`/job-setup`
        确实调了 `query_yield.py` 与 `gap_split.py`（`workflows/job-setup.md`
        「重跑这一节时（`--section search`），先看实测产出再问」），所以这里
        锁的是**它调用的集合**，不是「它不碰 Python」。集合变了就重新核口径。
        """
        cmds = commands_needing_python()
        with self.subTest(cmd="job-apply"):
            self.assertNotIn(
                "job-apply", cmds,
                "`/job-apply` 现在也要 Python 了——那 Python 就是必装项，"
                "两份文档的表都要改口径，不能再写「强烈建议」")

        def calls(name: str) -> set:
            text = (ROOT / "workflows" / f"{name}.md").read_text(encoding="utf-8")
            return set(CALL.findall(text))

        with self.subTest(cmd="job-setup"):
            self.assertEqual(
                calls("job-setup"),
                {"python tools/query_yield.py", "python tools/gap_split.py"},
                "`/job-setup` 用到的 Python 工具不止「改搜索词」复跑那两个了——"
                "第一次填资料若也开始离不开 Python，两份文档就不能再把它写在"
                "「强烈建议」那一档，得改成必装")
        with self.subTest(cmd="job-apply calls"):
            self.assertEqual(
                calls("job-apply"), set(),
                "`/job-apply` 正文里出现了 `python tools/…` 的调用")


if __name__ == "__main__":
    unittest.main()
