# -*- coding: utf-8 -*-
"""派生器的已知答案。

这几条不是「跑一遍看输出对不对」——那是把实现抄成断言。它们是**手算**出来的：
从今天的 `.claude/skills/job-scrape/SKILL.md` 逐行数出来，再要求派生器复现。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import _entries  # noqa: E402


class KnownAnswers(unittest.TestCase):
    def test_the_scrape_shell_gets_all_six_python_tools(self):
        """`job-scrape` 要六条 `python tools/*.py`，一条都不能少。

        手算依据：从今天的 `.claude/skills/job-scrape/SKILL.md` 逐行数出来的
        doctor / query_yield / jd_store / export_web_data / portal_budget /
        **ingest**。

        portal_budget 那条最容易漏 —— 它是 Step 0.46 的额度闸门，而漏掉的后果
        有实测：2026-08-19 用户的猎聘账号被标异常、要短信验证。

        第六条是 2026-10-12 加的 `ingest`：Step 2 的入库命令。**它漏掉的
        后果与前五条同一形状** —— 招牌命令每一步都要用户手点授权，
        而 `/job-scrape` 是入口命令，入口点不动等于整条链走不下去。
        """
        got = [t for t in _entries.allowed_tools("job-scrape")
               if t.startswith("Bash(python tools/")]
        self.assertEqual(sorted(got), sorted([
            "Bash(python tools/doctor.py:*)",
            "Bash(python tools/query_yield.py:*)",
            "Bash(python tools/jd_store.py:*)",
            "Bash(python tools/export_web_data.py:*)",
            "Bash(python tools/portal_budget.py:*)",
            "Bash(python tools/ingest.py:*)",
        ]))

    def test_the_index_yields_every_command(self):
        idx = _entries.read_index()
        self.assertEqual(len(idx), 21, f"索引里读到的命令数不对：{sorted(idx)}")
        for name, it in idx.items():
            self.assertTrue(it["does"], f"{name} 没有说明")
            self.assertTrue(it["examples"], f"{name} 没有举例")

    def test_the_router_shell_is_not_generated(self):
        self.assertIn("job-application-assistant", _entries.HANDWRITTEN_NAMES)
        self.assertNotIn("job-application-assistant", _entries.generated_names())
        self.assertIn("job-application-assistant", _entries.shell_names())
        self.assertTrue(_entries.MANIFEST["job-application-assistant"]["handwritten"])

    def test_every_generated_name_has_a_workflow_file(self):
        for name in _entries.generated_names():
            self.assertTrue((ROOT / "workflows" / f"{name}.md").is_file(),
                            f"{name} 没有对应的工作流正文")

    def test_the_manifest_and_the_index_name_the_same_commands(self):
        """两个正本必须说同一批命令名，而且要双向。

        索引里多一条而 MANIFEST 没有 → 那个壳没有触发词，自动触发静默失效；
        MANIFEST 多一条（改名、删命令）→ 那条永远是死数据，没人会去看。
        两种都不报错，只是悄悄少东西——正是本仓库反复在清的形状。
        """
        idx, mani = set(_entries.read_index()), set(_entries.MANIFEST)
        stale = sorted(mani - idx - _entries.HANDWRITTEN_NAMES)
        self.assertEqual(stale, [], f"MANIFEST 里有索引里没有的名字：{stale}")
        missing = sorted(n for n in _entries.generated_names() if n not in mani)
        self.assertEqual(missing, [], f"索引里的命令在 MANIFEST 里没有条目：{missing}")
        for name in _entries.generated_names():
            self.assertTrue(_entries.MANIFEST[name]["triggers"],
                            f"{name} 没有触发词，那个壳不会被自动触发")

    def test_no_command_shell_steals_a_router_word(self):
        """路由壳是「聊到求职就自动接管」，词很宽；命令壳必须更具体。

        撞词的后果不是报错，是**用户说「简历」时两个壳同时够格**，谁接管看运气。

        词表取 `router_generic_words_in_force()`（快照 ∪ 壳自己那行），不取常量：
        常量是手抄的，只读它的话「壳加宽、常量没跟上」这一格会让守卫**静默缩小**——
        而那正是它要防的形状。常量与壳等不等另由
        `test_the_constant_is_the_shells_own_words` 钉。
        """
        wide = _entries.router_generic_words_in_force()
        for name in _entries.generated_names():
            hits = set(_entries.MANIFEST[name]["triggers"]) & wide
            self.assertEqual(hits, set(), f"{name} 的触发词撞了路由壳：{sorted(hits)}")

    def test_no_wide_bash_rule_is_derived(self):
        """派生器绝不产出开宽授权。"""
        for name in _entries.generated_names():
            for tool in _entries.allowed_tools(name):
                self.assertNotIn("tools/:*", tool, f"{name}: {tool} 把整个目录授权出去了")
                self.assertNotIn("Skill(", tool, f"{name}: {tool} 是技能授权，不该由派生器给")
                self.assertNotIn("python -c", tool,
                                 f"{name}: {tool} 授权了任意内联代码")


class TheMappingIsTheExistingJudgement(unittest.TestCase):
    """`bash_rules` 只做「命令对 → 规则串」，判据本身不许重写。"""

    def test_script_paths_are_scoped_to_the_script(self):
        self.assertEqual(_entries.bash_rules(
            "```bash\npython tools/gap_split.py --applied\n```\n"),
            ["Bash(python tools/gap_split.py:*)"])

    def test_version_probe_stays_exact_not_prefixed(self):
        """今天的壳写的是 `Bash(node --version)`，窄于 `Bash(node:*)`。

        派生成前缀形式就是把「只许探版本」放宽成「随便跑 node」。
        """
        self.assertEqual(_entries.bash_rules("```bash\nnode --version\n```\n"),
                         ["Bash(node --version)"])

    def test_third_party_cli_is_scoped_to_the_program(self):
        self.assertEqual(_entries.bash_rules(
            "```bash\ntypst compile a.typ\npdftotext -layout -enc UTF-8 a.pdf b.txt\n```\n"),
            ["Bash(typst:*)", "Bash(pdftotext:*)"])

    def test_inline_code_and_placeholders_derive_nothing(self):
        """`python -c` 授权的是任意代码；`node src/cli.ts` 那种占位路径根本不存在。

        两者都不派生 —— 让覆盖测试把缺的那条报出来，由 MANIFEST 的
        `extra_tools` 逐条显式批、附理由。
        """
        text = ('```bash\npython -c "print(1)"\n'
                'node src/cli.ts search -q "<测试查询>"\n'
                'typst compile "users/<活动用户>/resume/main.typ" out.pdf\n```\n')
        self.assertEqual(_entries.bash_rules(text), ["Bash(typst:*)"])

    def test_the_derived_rules_cover_the_commands_they_came_from(self):
        """自证：从一份真工作流派生出的规则，必须覆盖它自己的每一条可派生命令。

        跳过的是**我们刻意不派生**的那几类（解释器 + flag，如 `python -c`；不在仓库根
        锚定的路径，如 `node src/cli.ts`；含 `<` `>` 的占位目标）。
        判据只有一份：`derives_nothing()` 就是 `bash_rules` 里那个「映射不出规则」的
        判定本身，不在这里复述一遍——复述出来的第二份会跟正本一起飘。
        """
        checked = 0
        # 共用一份判定还有个洞要补：映射整个失效时（连仓库脚本都不派生了），
        # 下面的循环会把每一条都跳过、于是全绿。这一句钉住映射的方向。
        self.assertFalse(_entries.derives_nothing("python tools/gap_split.py"),
                         "`_rule_for` 连一条仓库脚本都映射不出规则了，这条自证就是空跑")
        for name in _entries.generated_names():
            text = (ROOT / "workflows" / f"{name}.md").read_text(encoding="utf-8")
            # 只剥 `Bash(` 这一层壳，留着里面的 `:*`：`covered()` 认前缀形式，
            # 而精确形式（`node --version`）是它的退化情形。多剥三个字符会把
            # 精确规则切成半条，于是这条自证在最窄的那类规则上永远为假。
            bash_rules = [r[len("Bash("):-1] for r in _entries.allowed_tools(name)
                          if r.startswith("Bash(")]
            for cmd in sorted(_entries.commands_in(text)):
                if _entries.derives_nothing(cmd):
                    continue
                checked += 1
                self.assertTrue(_entries.covered(cmd, bash_rules),
                                f"{name}: 派生规则没覆盖到自己取出的 {cmd}")
        self.assertGreater(checked, 20,
                           f"这条自证只比了 {checked} 条命令——它大概在空跑")


class TheCounterCanFail(unittest.TestCase):
    def test_commands_in_really_reads_fences(self):
        """变异内建：认得出围栏里的命令，也不把散文里的一句话当命令。"""
        text = ("# x\n\n```bash\npython tools/doctor.py\n```\n\n"
                "正文里提到 python tools/never_run.py 但不该被算进去。\n")
        self.assertEqual(_entries.commands_in(text), {"python tools/doctor.py"})

    def test_covered_can_say_no(self):
        """对照用例：`covered` 不是恒真。"""
        self.assertFalse(_entries.covered("python tools/x.py", ["python tools/y.py:*"]))
        self.assertTrue(_entries.covered("python tools/x.py --a", ["python tools/x.py:*"]))
        self.assertTrue(_entries.covered(
            "node .agents/skills/liepin-search/cli/src/cli.ts detail",
            ["node .agents/skills/*/cli/src/cli.ts:*"]))


class TheRenderedShellIsLintable(unittest.TestCase):
    """`render_shell` 的产物要过 `tools/lint_skills.py::check_skill`，而那条检查
    要 pyyaml（CI 上没装）。所以这里按**形状**验，不 import yaml：
    lint 拒绝的四件事都能用字符串判定，且都是今天手写壳已经满足的形状。
    """

    def test_frontmatter_shape_and_marker_position(self):
        for name in _entries.generated_names():
            with self.subTest(shell=name):
                text = _entries.render_shell(name)
                self.assertTrue(text.startswith("---\n"),
                                f"{name}: frontmatter 必须以 --- 开头，否则技能解析器读不到")
                self.assertIn("\n---\n", text[4:], f"{name}: frontmatter 没有闭合")
                head, body = text[4:].split("\n---\n", 1)
                self.assertIn(f"\nname: {name}\n", f"\n{head}", f"{name}: name 不对")
                self.assertIn("\ndescription: >\n", f"\n{head}\n",
                              f"{name}: description 缺失")
                # 标记必须在闭合 `---` **之后**的正文首行；写在前面的 HTML 注释
                # 会让 frontmatter 不再以 `---` 开头 —— 整个文件读不出元数据。
                self.assertTrue(body.lstrip("\n").startswith(_entries.GENERATED_HEADER),
                                f"{name}: 生成标记不在正文首行")
                for tool in _entries.allowed_tools(name):
                    inner = tool[len("Bash("):-1] if tool.startswith("Bash(") else tool
                    if inner.endswith("*"):
                        self.assertTrue(inner.endswith(":*"),
                                        f"{name}: {tool} 是永远匹配不上的空格形式，"
                                        "要用 `:*`")


if __name__ == "__main__":
    unittest.main()
