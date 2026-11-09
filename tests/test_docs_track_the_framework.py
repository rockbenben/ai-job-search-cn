"""用户文档必须跟得上框架——它们是新人最先读的东西。

## 这次全面检查抓到的

**① 措辞落后一个版本。** `04-job-evaluation.md` 里明写着「地区是 Pass/Fail 的门，
不计权重——**所以别再叫「五维」**」，而 `README.md` 与 `SETUP.md` 两份用户文档
都还在写「五维」。框架改了、文档没跟——新人读到的是一套已经不存在的模型。

**② 命令表停在半路。** README 的「完整流程是四步」停在 `/job-apply`，`SETUP.md` 的
「跑一遍完整流程」停在编译简历。而**投出去之后那一段收益最大**（记录 → 催进度 →
备面 → 谈薪），新人根本不知道这些工具存在。

这两类都不会被任何现有测试拦住：工作流之间的接线有 `test_lifecycle_coverage`
管，但**面向用户的入口文档**此前没人管。
"""

import re
import unittest
from pathlib import Path

from tools._entries import SHELL_FAMILIES

ROOT = Path(__file__).resolve().parent.parent

#: 不扫的目录。`workflows/` 与 `docs/` 要排除**是有理由的**：框架自己那句
#: 「别再叫『五维』」就写在 `workflows/reference/04-job-evaluation.md` 里，
#: 扫它等于让废弃声明自己触发废弃检查；`docs/` 下是历史计划，本来就该留着当时的说法。
_SKIP_DIRS = {"workflows", "docs", "node_modules", "users",
              ".git", *SHELL_FAMILIES, ".superpowers", ".private",
              ".pytest_cache", "__pycache__", "dist"}


def _all_docs() -> list[Path]:
    """仓库里**所有**能读到的 markdown（除去上面那几个目录）。

    废弃说法这一条对它们**一视同仁**：一个概念被框架废掉之后，它在哪份文档里都是
    错的。这张单子原来写死成 `[README.md, SETUP.md]`，代价（2026-08-18 实测）：
    `web/README.md` 里的「框架词（硬门、能力边界、五维）」躲了过去——同一个废弃
    说法，只因为文件不在名单上就没人管。而面板那份 README 恰恰是改界面的人唯一
    会读的文档。

    改成扫出来而不是数出来：新加一份文档自动进检查，不必记得回来改这里。
    """
    return sorted(
        p for p in ROOT.rglob("*.md")
        if not (set(p.relative_to(ROOT).parts[:-1]) & _SKIP_DIRS))


#: **两张单子，两种严格度。**
#:
#: `USER_DOCS` 是新人真的会读的那两份——「内部词不许上屏」这条只对它们成立。
#: `web/README.md`、`CONTRIBUTING.md`、`profile.example/*.md` 是写给维护者与 AI 看的，
#: 它们**必须**能直呼「硬门」「能力边界」，那正是它们在解释的东西。
#: 一开始把两条检查挂在同一张单子上，扫开的瞬间就冒出 15 条误报。
USER_DOCS = [ROOT / "README.md", ROOT / "SETUP.md"]
DOCS = _all_docs()
FRAMEWORK = (ROOT / "workflows" / "reference" / "04-job-evaluation.md").read_text(
    encoding="utf-8")


class DocsUseCurrentTerminology(unittest.TestCase):

    #: 框架自己废弃掉的说法 → 现在该说什么
    #: 废弃说法 → 现在该怎么说。**中英两种形式都要挡**：
    #: 第一版只写了中文「五维」，而 `scrape.md` 与 `setup.md` 里那句
    #: `the hard-gate + five-dimension evaluation` 用的是英文形式，
    #: 一直没人拦——同一个废弃概念换了种语言就绕过了守卫。
    RETIRED = {
        "五维": "四维（地点是 Pass/Fail，不计权重）",
        "five-dimension": "四维",
        "five dimensions": "四维",
    }

    def test_no_retired_terms(self):
        bad = []
        for d in DOCS:
            for i, ln in enumerate(d.read_text(encoding="utf-8").splitlines(), 1):
                for w, now in self.RETIRED.items():
                    if w in ln:
                        # 用相对路径不用 `d.name`：单子扫开之后有两个 README.md，
                        # 只报文件名就分不清是哪一份。
                        rel = d.relative_to(ROOT).as_posix()
                        bad.append(f"{rel}:{i} 「{w}」→ 应为{now}：{ln.strip()[:50]}")
        self.assertEqual(bad, [], "用户文档用的是框架已废弃的说法：\n" + "\n".join(bad))

    def test_the_framework_really_retired_it(self):
        """这条测试的前提得成立——否则它拦的是一个并不存在的规则。"""
        self.assertIn("别再叫「五维」", FRAMEWORK,
                      "框架里找不到废弃声明，这条检查失去依据")

    def test_docs_do_not_leak_internal_words(self):
        """AGENTS.md 的措辞规则同样适用于用户文档——它们比面板更早被读到。"""
        import sys
        sys.path.insert(0, str(ROOT / "tests"))
        from test_display_wording import BANNED_WORDS
        # 豁免**短语**，不豁免整行。原来的写法是「行里出现『内部词』三个字就整行
        # 放行」——同一行里再塞一个「台账」「驾驶舱」也跟着免检，豁免面比要守的
        # 面还宽。改成先把正当的引用短语挖掉，剩下的字照扫（与
        # test_workflow_output_templates 的 EXEMPT 同一做法）。
        EXEMPT_PHRASES = ("内部词", "给用户看", "硬门槛")
        bad = []
        for d in USER_DOCS:
            for i, ln in enumerate(d.read_text(encoding="utf-8").splitlines(), 1):
                s = ln.strip()
                for ph in EXEMPT_PHRASES:
                    s = s.replace(ph, " ")
                for w in BANNED_WORDS:
                    if w in s:
                        bad.append(f"{d.name}:{i} 「{w}」 {ln.strip()[:46]}")
        self.assertEqual(bad, [], "用户文档里出现内部词：\n" + "\n".join(bad))


class WorkflowsUseCurrentTerminologyToo(unittest.TestCase):
    """废弃说法在 `workflows/` 里同样不许用——那才是执行者真正读的地方。

    `DocsUseCurrentTerminology` 只扫 README 与 SETUP 两份用户文档。可框架词是给
    执行者看的，废弃说法留在 `workflows/` 里，每一次跑命令都会被读到一遍。

    实测漏了两处，而且都换了语言：`scrape.md` 与 `setup.md` 写着
    `the hard-gate + five-dimension evaluation`——**同一个废弃概念换成英文就绕过了
    守卫**（RETIRED 里原来只有中文「五维」）。

    判据对**讲这条规则本身的句子**免疫：一行里同时有废弃说法和现说法
    （「所以是四维，不是五维」），或带着「别再叫」这类废弃声明的，都放行。
    """

    RETIRED = DocsUseCurrentTerminology.RETIRED
    ABOUT = ("别再叫", "废弃", "原来", "改名", "retired", "曾经")

    def test_the_scan_sees_the_files(self):
        """控制用例：真扫到工作流文件了。"""
        n = len(list((ROOT / "workflows").rglob("*.md")))
        self.assertGreaterEqual(n, 10, f"只扫到 {n} 个工作流文件？路径大概不对")

    def test_no_retired_terms_in_workflows(self):
        bad = []
        for p in sorted((ROOT / "workflows").rglob("*.md")):
            for i, ln in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                for w, now in self.RETIRED.items():
                    if w.lower() not in ln.lower():
                        continue
                    # 现说法就在同一行（对比句），或明说是废弃的 → 放行
                    if now.split("（")[0] in ln or any(k in ln for k in self.ABOUT):
                        continue
                    rel = p.relative_to(ROOT).as_posix()
                    bad.append(f"{rel}:{i} 「{w}」→ 应为{now}：{ln.strip()[:56]}")
        self.assertEqual(
            bad, [],
            "工作流里用了框架已废弃的说法：" + chr(10) + "  " + (chr(10) + "  ").join(bad)
            + chr(10) + "执行者每跑一次命令就读一遍，比用户文档里的影响更直接。")


class DocsCoverTheWholeLifecycle(unittest.TestCase):
    """文档停在 /job-apply，等于告诉新人「投完就没事了」——而收益最大的一段在后面。

    这一组盯的是 `USER_DOCS`（新人真会读的那两份），**不是**扫开之后的全量 `DOCS`：
    「每条命令都要露过面」如果算上 `web/README.md`、`CONTRIBUTING.md`，那么一条命令
    只在维护者文档里出现过也算数——检查还在，但它保证的已经不是原来那件事了。
    """

    def _must_appear(self) -> list:
        """**每条命令都要在用户文档里露过面** —— 名单从 `workflows/` 推导。

        这里原来写死十条（21 条里的十条），也就是说**新加的命令不进这道门**：
        写了一条命令、README 一个字没提，新人永远不知道它存在，而这条守卫
        一声不响。同 `JD_READERS`（漏两条）、`GUARDS`（漏两条，其中一条是
        主线命令 `/job-auto`）、`WRITERS`（漏三条）—— 手写名单是这个仓库
        反复出现的那个根因，2026-09-02 一并改掉。

        实测改的时候 21 条**都在** README/SETUP 里，所以这次不是修缺口，
        是把门从「记得加名字」换成「加了命令就自动进门」。
        """
        return sorted(f"/{p.stem}" for p in (ROOT / "workflows").glob("job-*.md"))

    def test_the_command_scan_sees_them_all(self):
        """控制用例：推导得出 21 条上下，否则下面那条对着空气跑。"""
        got = self._must_appear()
        self.assertGreaterEqual(len(got), 15,
                                f"只推导出 {len(got)} 条命令 —— 判据八成失效了")

    def test_every_command_is_mentioned_somewhere(self):
        joined = "\n".join(d.read_text(encoding="utf-8") for d in DOCS)
        missing = []
        for c in self._must_appear():
            # 要求带反引号或出现在表格里——纯路径（resume/main.typ）不算
            if not re.search(rf"`{re.escape(c)}[ `<]", joined + " "):
                missing.append(c)
        self.assertEqual(missing, [],
                         f"这些命令在用户文档里从没出现过，新人不会知道它们存在：{missing}")

    def test_post_application_stage_is_documented(self):
        """投出去之后那一段（记录/催进度/备面/谈薪）不能只字不提。"""
        joined = "\n".join(d.read_text(encoding="utf-8") for d in DOCS)
        for k in ("背调", "催", "offer"):
            with self.subTest(topic=k):
                self.assertIn(k, joined, f"用户文档里没提「{k}」")

    def test_commands_in_docs_all_exist(self):
        """反过来也要成立：文档里提到的命令必须真的有。"""
        joined = "\n".join(d.read_text(encoding="utf-8") for d in DOCS)
        cited = set(re.findall(r"`/([a-z-]+)[ `<]", joined + " "))
        have = {p.stem for p in (ROOT / "workflows").glob("*.md")}
        # `/mcp` 之类是外部命令，不归本仓库管
        external = {"skills", "mcp", "login", "help", "clear", "config", "model"}
        ghosts = sorted(cited - have - external)
        self.assertEqual(ghosts, [],
                         f"文档里提到了不存在的命令：{ghosts}")


if __name__ == "__main__":
    unittest.main()
