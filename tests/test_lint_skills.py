import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools._entries import SHELL_FAMILIES


REPO_ROOT = Path(__file__).resolve().parent.parent
LINTER_SCRIPT = REPO_ROOT / "tools" / "lint_skills.py"


def run_linter(root: Path) -> subprocess.CompletedProcess:
    """跑 linter 并按 **UTF-8** 解码它的输出。

    `text=True` 不指定 encoding 时按系统区域设置解码。linter 印的是中文，于是在
    Windows（GBK 控制台）上一旦外层设了 `PYTHONIOENCODING=utf-8`——在 GBK 终端上
    这是很自然的动作——子进程按 UTF-8 输出、父进程按 GBK 解，`result.stdout` 变成
    `None`，四条测试报 `TypeError: argument of type 'NoneType'`，看不出跟编码有关。

    环境不该改变测试结论。这里把**两头**都钉成 UTF-8：只钉父进程的解码不够——
    不设 `PYTHONIOENCODING` 时子进程按区域设置（GBK）输出，父进程按 UTF-8 解，
    中文变乱码，断言照样挂，只是换个方向错。
    """
    return subprocess.run(
        [sys.executable, str(root / "tools" / "lint_skills.py")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )


class LinterRepoFixture(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

        tools = self.root / "tools"
        tools.mkdir()
        shutil.copy(LINTER_SCRIPT, tools / "lint_skills.py")
        # The Python-test CI job does not install PyYAML; the separate lint job
        # does. These settings-focused tests only need a valid frontmatter map.
        (tools / "yaml.py").write_text(
            "class YAMLError(Exception):\n"
            "    pass\n\n"
            "def safe_load(_text):\n"
            "    return {'name': 'example', 'description': 'Example skill'}\n",
            encoding="utf-8",
        )

        # 基础夹具**不再**造 `.claude/commands/job-setup.md`：命令 stub 已整体删除，
        # 那一目录里再有文件就是 lint 要报的「残留 stub」（见 test_leftover_command_stub_fails）。
        # 入口现在是两族各一份壳 —— 只放一族会被「两族壳集合一致」那条守卫判红。
        #
        # 目录名用的是**路由壳**那个名字（`job-application-assistant`，真实仓库里唯一
        # 一份不生成、也没有工作流正文的壳），不是随手起的 `example`：新加的「两族都有
        # 壳却没有正文」那条判据（test_shell_in_both_families_without_workflow_fails）
        # 会把后者判红，而本文件大半测试都从 make_layout() 起。换句话说这份夹具今天
        # 同时是那条判据的**反向对照** —— 路由壳不许被点着，点着了这里一起红。
        for fam in SHELL_FAMILIES:
            skill = self.root / fam / "skills" / "job-application-assistant" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text(
                "---\nname: job-application-assistant\n"
                "description: Consulting router shell\n---\n",
                encoding="utf-8",
            )

        self.settings = self.root / ".claude" / "settings.json"
        self.write_settings({"permissions": {"allow": []}})

    def write_settings(self, data):
        self.settings.write_text(json.dumps(data), encoding="utf-8")


class SettingsShapeTests(LinterRepoFixture):
    def test_valid_settings_pass(self):
        result = run_linter(self.root)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("lint_skills: OK", result.stdout)

    def test_invalid_json_fails_cleanly(self):
        self.settings.write_text("{not json", encoding="utf-8")

        result = run_linter(self.root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(".claude/settings.json", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_non_object_root_fails_cleanly(self):
        for data in ([], "settings", 1, None):
            with self.subTest(data=data):
                self.write_settings(data)

                result = run_linter(self.root)

                self.assertEqual(result.returncode, 1)
                self.assertIn("top-level JSON value to be an object", result.stdout)
                self.assertNotIn("Traceback", result.stderr)

    def test_non_object_permissions_fails_cleanly(self):
        for permissions in ([], "permissions", 1, None):
            with self.subTest(permissions=permissions):
                self.write_settings({"permissions": permissions})

                result = run_linter(self.root)

                self.assertEqual(result.returncode, 1)
                self.assertIn("expected permissions to be an object", result.stdout)
                self.assertNotIn("Traceback", result.stderr)

    def test_non_list_allow_fails_cleanly(self):
        for allow in ({}, "Bash(bun run:*)", 1, None):
            with self.subTest(allow=allow):
                self.write_settings({"permissions": {"allow": allow}})

                result = run_linter(self.root)

                self.assertEqual(result.returncode, 1)
                self.assertIn("expected permissions.allow to be a list", result.stdout)
                self.assertNotIn("Traceback", result.stderr)


class WorkflowLayoutTests(LinterRepoFixture):
    """workflows/ 布局检查：壳指向、各族各一份、残留 stub、中立性。"""

    def make_entry(self, stem):
        """给 `workflows/<stem>.md` 在**各族各**放一份壳。

        生成器（`tools/gen_entries.py`）一次写全各族，夹具只落一族的话，
        「两族壳集合一致」那条守卫会先红，掩盖掉本条测试真正要验的那一项。
        """
        for fam in SHELL_FAMILIES:
            shell = self.root / fam / "skills" / stem / "SKILL.md"
            shell.parent.mkdir(parents=True, exist_ok=True)
            shell.write_text(
                f"---\nname: {stem}\ndescription: 测试壳\n---\n\n"
                f"读取并严格执行 `workflows/{stem}.md`。\n",
                encoding="utf-8")

    def make_layout(self):
        wf = self.root / "workflows"
        wf.mkdir()
        (wf / "job-setup.md").write_text("# /job-setup - Test\n\n用网页抓取能力取回页面。\n",
                                     encoding="utf-8")
        # 索引表正本在 workflows/INDEX.md（2026-09-29 从 AGENTS.md 搬来）；
        # 表是这份文件的全部内容，正好压着 B2 收尾正则的 \Z 分支。
        (wf / "INDEX.md").write_text(
            "## 工作流索引\n\n| 任务 | 正文 |\n|---|---|\n| 测试 | `workflows/job-setup.md` |\n\n",
            encoding="utf-8")
        self.make_entry("job-setup")
        # AGENTS.md 只留节名锚 + 指针；表不再住这里。
        (self.root / "AGENTS.md").write_text(
            "# AGENTS\n\n## 工作流索引\n\n索引表搬到 `workflows/INDEX.md`。\n\n"
            "## 能力对照表\n\n| 能力 |\n|---|\n| 网页抓取 / web fetch |\n| 网络搜索 / network search |\n"
            "| 结构化提问 / structured prompt |\n| 并行子代理 / parallel sub-agents |\n",
            encoding="utf-8")
        (self.root / "CLAUDE.md").write_text(
            "# CLAUDE\n\n**先读并遵守 @AGENTS.md 的全部规则**\n", encoding="utf-8")
        return wf

    def test_no_workflows_dir_skips_checks(self):
        # 基础 fixture 没有 workflows/ —— 旧布局 fork 必须照常通过
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_valid_layout_passes(self):
        self.make_layout()
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_shell_without_workflow_reference_fails(self):
        """壳在、正文里却不提它那份工作流 —— 入口指向空气。

        只坏 **一族**（`.agents`）：判据是分族核的，所以该只报 `.agents`，完好那族
        不许被牵连。两族一起坏的话，这条就看不出循环其实只查了「任一族有就算过」——
        那正是原来 stub/壳二选一写法的行为。
        """
        self.make_layout()
        broken = self.root / ".agents" / "skills" / "job-setup" / "SKILL.md"
        broken.write_text("---\nname: job-setup\ndescription: 测试壳\n---\n\n自由发挥。\n",
                          encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn(".agents/skills/job-setup/SKILL.md", result.stdout.replace("\\", "/"))
        self.assertNotIn("no skill shell in .claude", result.stdout)

    def test_leftover_command_stub_fails(self):
        """残留 stub 探测器：`.claude/commands/` 里再冒出文件就是手写的第二落点。

        取代原来那条 `test_fat_stub_fails`（「stub 不许超过 5 行」）。那条按 stub 的
        **形状**判，而形状整个作废了：入口文件本身不该存在，它写成什么样都不用去看。
        它防的东西（内容被抄进入口文件、和正文飘）由这条更硬地接管——一个文件都没有，
        就没有抄件可飘。
        """
        self.make_layout()
        stray = self.root / ".claude" / "commands" / "job-setup.md"
        stray.parent.mkdir(parents=True)
        stray.write_text("# /job-setup - Test setup command\n\n自由发挥。\n", encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("command stubs are gone", result.stdout)
        # 指引必须给出该去哪儿：索引与生成器，一条不落
        self.assertIn("workflows/INDEX.md", result.stdout)
        self.assertIn("tools/gen_entries.py", result.stdout)

    def test_shell_only_in_one_family_fails(self):
        """两族壳集合守卫：只在一族有的壳 = 生成器跑了一半。

        取代原来那条 `test_stub_pointing_at_missing_workflow_fails`（ghost stub）。
        同名的壳现在指向不存在的正文，这条从两族一致性方向抓到。
        「壳名必须对应一份工作流正文」那半边有**两处**在查：lint 的反向判据
        （下面 `test_shell_in_both_families_without_workflow_fails`）与
        `tests/test_docs_accuracy.py::test_shell_name_matches_its_workflow`
        （两族都查、不依赖 lint）—— 两族一起有的悬空壳，集合守卫看不见，
        靠的就是这两条。
        """
        self.make_layout()
        ghost = self.root / ".claude" / "skills" / "ghost" / "SKILL.md"
        ghost.parent.mkdir(parents=True)
        ghost.write_text("---\nname: ghost\ndescription: d\n---\n\n"
                         "读取并严格执行 `workflows/ghost.md`。\n", encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("families disagree", result.stdout)
        self.assertIn("ghost", result.stdout)

    def test_shell_in_both_families_without_workflow_fails(self):
        """两族**各**有一份壳、没有 `workflows/<名>.md` = 入口把用户领进空房间。

        这一向此前是 lint 的盲区，两个方向都遮住了它：`check_workflow_layout()` 的
        循环从工作流这一侧走（没有正文就轮不到它），而 `main()` 里那条集合守卫比的
        是两族**彼此**（两边同时多出来一份壳 = 相等 = 绿）。只剩
        `tests/test_docs_accuracy.py` 一条兜着，于是单独跑 `python tools/lint_skills.py`
        时（CI 的 lint job、 CONTRIBUTING 让它当第一道门）报的是 OK。

        「它不该顺手过滤掉悬空壳」也一并钉住了：见 `command_shells()` 的那条 ⚠️。
        """
        self.make_layout()
        for fam in SHELL_FAMILIES:
            shell = self.root / fam / "skills" / "ghost" / "SKILL.md"
            shell.parent.mkdir(parents=True)
            shell.write_text("---\nname: ghost\ndescription: d\n---\n\n"
                             "读取并严格执行 `workflows/ghost.md`。\n", encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        out = result.stdout.replace("\\", "/")
        # 两族**分别**报：只报一族看不出另一族是不是也带着同一份悬空壳
        for fam in SHELL_FAMILIES:
            self.assertIn(f"{fam}/skills/ghost/SKILL.md: no workflows/ghost.md", out)
        # 指引要给去处：索引 + 生成器，与残留 stub 那条同样一条不落
        self.assertIn("workflows/INDEX.md", out)
        self.assertIn("tools/gen_entries.py", out)
        # 悬空壳在两族是同一批 —— 集合守卫这条不该顺手报它（那会把「一半没跑」
        # 和「两边都悬空」两种病混成一条，而改法完全不同）
        self.assertNotIn("families disagree", out)

    def test_portal_skill_in_one_family_does_not_count_as_disagreement(self):
        """反向对照：渠道技能**只装在 `.agents` 族**，它不该把上面那条守卫点着。

        少了这条，判据会被「顺手」改成数两族全部 SKILL.md —— 那在本仓库的真实状态下
        （`.agents/skills/liepin-search`）立刻红，而红的是没坏的那半边。
        判据与 AGENTS.md 一致：有 `cli/src/cli.ts` 的是渠道，不是命令入口。
        """
        self.make_layout()
        portal = self.root / ".agents" / "skills" / "zzportal-search"
        (portal / "cli" / "src").mkdir(parents=True)
        (portal / "cli" / "src" / "cli.ts").write_text("// 渠道入口\n", encoding="utf-8")
        (portal / "SKILL.md").write_text("---\nname: zzportal-search\ndescription: d\n---\n",
                                         encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_workflow_without_entry_fails(self):
        wf = self.make_layout()
        (wf / "orphan.md").write_text("# 孤儿工作流\n", encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        # 两族**分别**报：只报一条「没有入口」看不出另一族是不是也没壳
        self.assertIn("no skill shell in .claude/skills/orphan/", result.stdout.replace("\\", "/"))
        self.assertIn("no skill shell in .agents/skills/orphan/", result.stdout.replace("\\", "/"))

    def test_shell_missing_from_one_family_fails(self):
        """少一族壳：生成器只跑了一半时，另一族照常、这一族的用户敲不到。

        「任一族有就算过」的写法在这里会放行 —— 那正是要防的那种半坏状态。
        """
        wf = self.make_layout()
        (wf / "job-scrape.md").write_text("# Job Scraper\n\n搜索职位。\n", encoding="utf-8")
        self.make_entry("job-scrape")
        (self.root / ".agents" / "skills" / "job-scrape" / "SKILL.md").unlink()
        index = self.root / "workflows" / "INDEX.md"
        index.write_text(index.read_text(encoding="utf-8")
                         + "| 抓取 | `workflows/job-scrape.md` |\n",
                         encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("no skill shell in .agents/skills/job-scrape/",
                      result.stdout.replace("\\", "/"))
        self.assertNotIn("no skill shell in .claude/skills/job-scrape/",
                         result.stdout.replace("\\", "/"))

    def test_skill_shell_counts_as_entry(self):
        """壳（两族各一份）就是入口，不需要任何 stub。"""
        wf = self.make_layout()
        (wf / "job-scrape.md").write_text("# Job Scraper\n\n搜索职位。\n", encoding="utf-8")
        self.make_entry("job-scrape")
        # Add scrape to workflows/INDEX.md (inside its "## 工作流索引" section, not
        # just anywhere in the file) to satisfy bidirectional completeness
        index = self.root / "workflows" / "INDEX.md"
        index.write_text(index.read_text(encoding="utf-8")
                         + "| 抓取 | `workflows/job-scrape.md` |\n",
                         encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_neutrality_literal_fails(self):
        wf = self.make_layout()
        (wf / "job-setup.md").write_text("# /job-setup - Test\n\n调用 WebFetch 抓取页面。\n",
                                     encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("WebFetch", result.stdout)

    def test_neutrality_covers_reference_dir(self):
        wf = self.make_layout()
        ref = wf / "reference"
        ref.mkdir()
        (ref / "notes.md").write_text("用 AskUserQuestion 问用户。\n", encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("AskUserQuestion", result.stdout)

    def test_missing_agents_md_fails(self):
        self.make_layout()
        (self.root / "AGENTS.md").unlink()
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("AGENTS.md", result.stdout)

    def test_workflow_missing_from_index_fails(self):
        wf = self.make_layout()
        (wf / "extra.md").write_text("# /extra - T\n", encoding="utf-8")
        self.make_entry("extra")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("not in the index", result.stdout)

    def test_index_referencing_missing_workflow_fails(self):
        self.make_layout()
        index = self.root / "workflows" / "INDEX.md"
        index.write_text(index.read_text(encoding="utf-8")
                         + "| 幽灵 | `workflows/ghost.md` |\n",
                         encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("ghost", result.stdout)

    def test_index_reference_outside_section_does_not_count(self):
        # A workflow name mentioned outside the index table must NOT satisfy the
        # index-completeness check - only "## 工作流索引" inside workflows/INDEX.md
        # counts as "registered". The index moved out of AGENTS.md (2026-09-29),
        # so this now pins the sharper edge: AGENTS.md prose - the old host of
        # the table - mentioning a workflow registers nothing. orphan2 gets its
        # own two-family shells (a valid entry point) so the only possible
        # failure is the index-completeness check itself.
        # Regression test for the pre-fix bug where the whole AGENTS.md file
        # was scanned for "workflows/<x>.md" mentions.
        wf = self.make_layout()
        (wf / "orphan2.md").write_text("# 孤儿工作流 2\n", encoding="utf-8")
        self.make_entry("orphan2")
        agents = self.root / "AGENTS.md"
        agents.write_text(agents.read_text(encoding="utf-8")
                          + "\n（角色段提及 `workflows/orphan2.md`，但这不在工作流索引节内）\n",
                          encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("not in the index: workflows/orphan2.md", result.stdout)

    def test_missing_workflow_index_section_fails(self):
        self.make_layout()
        index = self.root / "workflows" / "INDEX.md"
        index.write_text(index.read_text(encoding="utf-8")
                          .replace("## 工作流索引\n\n", ""), encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("工作流索引", result.stdout)

    def test_claude_md_without_import_fails(self):
        self.make_layout()
        (self.root / "CLAUDE.md").write_text("# CLAUDE\n\n先读 AGENTS.md。\n",
                                             encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("@AGENTS.md", result.stdout)

    def test_backticked_import_does_not_count(self):
        self.make_layout()
        (self.root / "CLAUDE.md").write_text("# CLAUDE\n\n先读 `@AGENTS.md`。\n",
                                             encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("@AGENTS.md", result.stdout)

    def test_capability_alias_removed_from_table_fails(self):
        wf = self.make_layout()
        (wf / "job-setup.md").write_text(
            "# /job-setup - Test\n\nUse the network search capability here.\n",
            encoding="utf-8")
        agents = self.root / "AGENTS.md"
        agents.write_text(agents.read_text(encoding="utf-8")
                          .replace("| 网络搜索 / network search |\n", ""),
                          encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("network search", result.stdout)

    def test_active_template_block_in_reference_fails(self):
        wf = self.make_layout()
        ref = wf / "reference"
        ref.mkdir()
        (ref / "05-cv-templates.md").write_text(
            "<!-- BEGIN ACTIVE-TEMPLATE -->\nx\n<!-- END ACTIVE-TEMPLATE -->\n",
            encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("ACTIVE-TEMPLATE", result.stdout)

    def test_cjk_error_message_survives_ascii_stdout(self):
        """错误信息内嵌中文（'## 工作流索引'）；在表示不了中文的控制台编码下必须降级
        输出，而不是在打印循环里抛 UnicodeEncodeError 把其余发现一起吞掉。
        锚点在 workflows/INDEX.md，换文件不换判据。"""
        self.make_layout()
        index = self.root / "workflows" / "INDEX.md"
        index.write_text(index.read_text(encoding="utf-8")
                          .replace("## 工作流索引\n\n", ""), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(self.root / "tools" / "lint_skills.py")],
            capture_output=True, text=True, errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "cp1252"})
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("UnicodeEncodeError", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_orphan_begin_marker_gets_its_own_message(self):
        """有 BEGIN 无配对 END：迁移脚本清不掉，指引必须不同——不能支使用户去跑一条
        对它无效的命令，那正是「lint 报错但没有任何工具能修」的来源。"""
        wf = self.make_layout()
        ref = wf / "reference"
        ref.mkdir()
        (ref / "05-cv-templates.md").write_text(
            "<!-- BEGIN ACTIVE-TEMPLATE -->\nx\n", encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("no matching END", result.stdout)
        self.assertNotIn("migrate_to_multiuser", result.stdout)

    def test_fenced_agents_import_does_not_count(self):
        """围栏代码块里的 @AGENTS.md 不会被求值，不能算作真导入。"""
        self.make_layout()
        (self.root / "CLAUDE.md").write_text(
            "# CLAUDE\n\n入口应该长这样：\n\n```markdown\n先读并遵守 @AGENTS.md 的全部规则\n```\n",
            encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("@AGENTS.md", result.stdout)

    def test_entry_point_check_runs_without_workflows_dir(self):
        """没有 workflows/ 时 @import 检查依旧要跑：它原本挂在 check_workflow_layout()
        的提前返回之后，于是在删掉 workflows/ 的仓库上静默不跑。"""
        (self.root / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
        (self.root / "CLAUDE.md").write_text("# CLAUDE\n\n先读 `@AGENTS.md`。\n",
                                             encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("@AGENTS.md", result.stdout)

    def test_dangling_reference_file_fails(self):
        """workflows/reference/*.md 的引用一样不能悬空——只匹配顶层名的正则对它全盲，
        而角色段引用的恰恰是 reference 文件。"""
        self.make_layout()
        agents = self.root / "AGENTS.md"
        agents.write_text(agents.read_text(encoding="utf-8")
                          + "\n按 `workflows/reference/04-job-evaluation.md` 评估职位。\n",
                          encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("reference/04-job-evaluation.md", result.stdout)

    def test_per_user_activation_path_is_allowed(self):
        """根级检查不得误伤正确位置的激活文件。

        fixture 仓库从不创建 users/，所以缺了这条反向用例时，把 glob 改宽（例如
        ROOT.rglob）测试依旧全绿，而每一个激活过模板的真实仓库会立刻 lint 失败。
        """
        self.make_layout()
        active = self.root / "users" / "张三" / "templates" / "active-cv.md"
        active.parent.mkdir(parents=True)
        active.write_text("# 激活模板\n", encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_block_message_never_prescribes_a_mutating_command(self):
        """指引只给手工步骤。曾经这里写的是 `migrate_to_multiuser.py --yes`——在尚未
        迁移的仓库上那条命令会零预览地搬走整棵个人数据树，在共享 clone 上会删掉别人
        还在用的共享块。一条只承诺「清掉一个陈旧的块」的提示不该触发那种规模的改动。"""
        wf = self.make_layout()
        (wf / "job-setup.md").write_text(
            "# /job-setup - Test\n\n<!-- BEGIN ACTIVE-TEMPLATE -->\nx\n<!-- END ACTIVE-TEMPLATE -->\n",
            encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("整段删掉", result.stdout)
        self.assertNotIn("--yes", result.stdout)
        # 集合外的文件连脚本名都不该提——那个脚本对它完全不看
        self.assertNotIn("migrate_to_multiuser", result.stdout)

    def test_orphan_marker_reported_alongside_a_complete_block(self):
        """同一文件里既有完整块又有孤立标记时，两条都要报——只报完整块的话，用户
        照着跑一遍迁移脚本，回来发现 lint 还是红的。"""
        wf = self.make_layout()
        ref = wf / "reference"
        ref.mkdir()
        (ref / "05-cv-templates.md").write_text(
            "<!-- BEGIN ACTIVE-TEMPLATE -->\nx\n<!-- END ACTIVE-TEMPLATE -->\n\n"
            "<!-- BEGIN ACTIVE-TEMPLATE -->\n残留\n", encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("contains an ACTIVE-TEMPLATE block", result.stdout)
        self.assertIn("no matching END", result.stdout)

    def test_unclosed_fence_swallows_the_import_per_commonmark(self):
        """未闭合围栏按 CommonMark 一直延伸到文件末尾——它后面的导入确实是代码。

        所以正确的诊断是「缺少真导入」，而不是先前那条「未闭合围栏」的自造错误：那条
        错误建立在「``` 计数为奇数 = 未闭合」这个错误前提上。
        """
        self.make_layout()
        (self.root / "CLAUDE.md").write_text(
            "# CLAUDE\n\n```\n粘贴残留，没有闭合\n\n"
            "**先读并遵守 @AGENTS.md 的全部规则**\n", encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("needs a real @AGENTS.md import", result.stdout)

    def test_longer_fence_wrapping_backticks_does_not_false_fail(self):
        """```` 包裹、内含单行 ``` 的合法片段不许误红。

        CommonMark 只用**不短于开头**的游程闭合围栏，所以内层那行 ``` 不是闭合符；
        按「数 ``` 的个数」判断会得出奇数并对一份完全正确的文件硬失败。
        """
        self.make_layout()
        (self.root / "CLAUDE.md").write_text(
            "# CLAUDE\n\n**先读并遵守 @AGENTS.md 的全部规则**\n\n"
            # 单行裸 ```：连同外层 ```` 共 3 个围栏行——按「数个数」判定即为奇数
            "代码块的开头写法：\n\n````markdown\n```\n````\n", encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_fenced_only_import_with_stray_fence_does_not_pass(self):
        """唯一的 @AGENTS.md 落在围栏里、外加一个杂散 ``` 时，绝不能报 OK。"""
        self.make_layout()
        (self.root / "CLAUDE.md").write_text(
            "# CLAUDE\n\n```\n杂散残留\n\n```markdown\n先读 @AGENTS.md\n```\n",
            encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)

    def test_non_utf8_workflow_is_reported_not_crashed(self):
        """非 UTF-8 的 workflow 文件只该是一条普通失败。

        抛栈会让 stdout 全空、把仓库里其余**所有** lint 错误一起吞掉；而迁移脚本的提示
        恰恰是「转成 UTF-8 后手工处理」——验证这条指引的工具不能崩在该文件上。
        """
        wf = self.make_layout()
        (wf / "job-setup.md").write_bytes("# /job-setup - 测试\n\n中文正文\n".encode("gbk"))
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("not valid UTF-8", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_stray_activation_hint_includes_mkdir(self):
        """手工指引必须可执行：目标目录在它诊断的那个状态下并不存在。"""
        self.make_layout()
        (self.root / "templates").mkdir()
        (self.root / "templates" / "active-cv.md").write_text("# 激活模板\n",
                                                              encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("mkdir -p users/<your user>/templates", result.stdout)

    def test_orphan_end_marker_is_reported(self):
        """孤立 END（无配对 BEGIN）同样要报——它是「部分删除」留下的残渣。

        少了这条，抽块之后留在 git 跟踪的共享框架文件里的那行 END 对 migrate 与 lint
        都永久不可见，正是这批检查要消灭的「静默而不是响亮」。
        """
        wf = self.make_layout()
        ref = wf / "reference"
        ref.mkdir()
        (ref / "05-cv-templates.md").write_text(
            "# 标题\n\n<!-- END ACTIVE-TEMPLATE -->\n", encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("no matching BEGIN", result.stdout)

    def test_lone_cr_file_is_read_as_bytes_like_migrate_does(self):
        """lint 必须与迁移脚本看同样的字节。

        改回 `read_text` 的话，通用换行会把孤立 `\\r` 当成换行，于是同一份内容 lint 认为
        「有完整块」（并指引去跑迁移），而按 bytes 读的迁移脚本根本看不见它。这里用孤立
        `\\r` 的文件钉住：块正则匹配不上，只应报「无配对 END」，不该报「有完整块」。
        """
        wf = self.make_layout()
        (wf / "job-setup.md").write_bytes(
            "# /job-setup - Test\r<!-- BEGIN ACTIVE-TEMPLATE -->\rx\r"
            "<!-- END ACTIVE-TEMPLATE -->\r".encode("utf-8"))
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("no matching END", result.stdout)
        self.assertNotIn("contains an ACTIVE-TEMPLATE block", result.stdout)

    def test_active_template_prose_mention_passes(self):
        """禁的是**块**，不是这个词：工作流要能向 fork 用户解释遗留标记。"""
        wf = self.make_layout()
        (wf / "job-setup.md").write_text(
            "# /job-setup - Test\n\n若 05 里仍留着 ACTIVE-TEMPLATE 遗留块，先跑迁移脚本。\n",
            encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_index_registration_survives_any_agents_section_order(self):
        """索引表搬到 workflows/INDEX.md 后，AGENTS.md 里谁前谁后影响不到 B2；
        钉住搬走后仍然成立的那半边：AGENTS.md 在「## 能力对照表」之后提到一个
        **真实存在、有入口、却没进索引表**的 workflows/x.md → 只许报
        「not in the index」，不许误报悬空指针（悬空扫描照旧看 AGENTS 全文，
        文件在盘上就该放行）。原来那条「索引恰好是最后一节」的 \\Z 分支由
        make_layout 的 INDEX.md 夹具常年代验——表就是那份文件的全部内容，
        test_valid_layout_passes 一绿它就在。"""
        wf = self.make_layout()
        (wf / "extra.md").write_text("# /extra - T\n", encoding="utf-8")
        self.make_entry("extra")
        agents = self.root / "AGENTS.md"
        agents.write_text(agents.read_text(encoding="utf-8")
                          + "\n能力对照表之后提到 `workflows/extra.md`。\n",
                          encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("not in the index: workflows/extra.md", result.stdout)
        self.assertNotIn("references missing workflows/extra.md", result.stdout)

    def test_dangling_reference_outside_index_fails(self):
        """段外的 workflows/*.md 指针（角色段、能力表降级列）也不能指向不存在的文件。

        「登记入索引」的判定限于索引节内，但悬空指针要看全文——AGENTS.md 的能力对照表
        降级列就点名了 gmail-sync/notion-sync/scrape。
        """
        self.make_layout()
        agents = self.root / "AGENTS.md"
        agents.write_text(agents.read_text(encoding="utf-8")
                          + "\n无此能力时 → `workflows/ghost.md` 全流程跳过。\n",
                          encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("ghost", result.stdout)

    def test_drifted_alias_fails_even_when_agents_md_mentions_it(self):
        """漂移写法的禁令不查 AGENTS.md：否则文件里提一句就把检查永久关掉。"""
        wf = self.make_layout()
        (wf / "job-setup.md").write_text(
            "# /job-setup - Test\n\nUse web search to find the posting.\n", encoding="utf-8")
        agents = self.root / "AGENTS.md"
        agents.write_text(agents.read_text(encoding="utf-8")
                          .replace("| 网络搜索 / network search |",
                                   "| 网络搜索 / network search（旧写法 web search，勿用） |"),
                          encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("web search", result.stdout)

    def test_root_level_activation_file_fails(self):
        """激活文件落在仓库根 = .active_user 缺失/迁移未完成，gitignore 让它对
        git status 沉默，必须由 lint 喊出来。"""
        self.make_layout()
        (self.root / "templates").mkdir()
        (self.root / "templates" / "active-cv.md").write_text("# 激活模板\n",
                                                              encoding="utf-8")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("templates/active-cv.md", result.stdout.replace("\\", "/"))


if __name__ == "__main__":
    unittest.main()


class DegradationCheckIsNeitherBlindNorTriggerHappy(unittest.TestCase):
    """`check_optional_profile_degradation` 自己被查了一遍——**元工具最怕空转**。

    2026-08-20 变异实测查出两个方向都错：

    1. **假阳性**：作者写了「该文件**还是**占位符时跳过」，而词表里只有
       「**仍是**占位符」，一字之差判红。中文近义写法穷举不完，
       所以判据改成最短公共片段（「占位符」「没填」「未填」）。
       这个仓库为同一形状付过三次学费（「读过」vs「读了」漏 613 条）。
    2. **假阴性**：`"never sync" in body` 是**整份文件级**豁免——文件任何角落
       出现一次，全篇所有引用都被放行。探针实测：开头写一句 never sync、
       三百行后真的去读 `behavioral.md`，检查全程绿。改成只豁免引用附近那一处。
    """

    def _probe(self, content: str) -> bool:
        """把探针写进 workflows/ 跑一次，返回「有没有红」。

        直接 import 而不是走子进程：这里要验的是**判据本身**，子进程还会跑
        另外七八项检查，别的项目一红就分不清是谁在红。
        """
        import sys as _sys
        _sys.path.insert(0, str(REPO_ROOT / "tools"))
        import lint_skills
        probe = REPO_ROOT / "workflows" / "job-zzprobe.md"
        try:
            probe.write_text(content, encoding="utf-8")
            lint_skills.errors.clear()
            lint_skills.check_optional_profile_degradation()
            return any("job-zzprobe" in e for e in lint_skills.errors)
        finally:
            probe.unlink(missing_ok=True)
            lint_skills.errors.clear()

    def test_missing_degradation_is_caught(self):
        self.assertTrue(self._probe("# 探针\n\n读 `profile/behavioral.md` 来校准语域。\n"),
                        "引用了可选 profile 却没写降级路径，检查居然是绿的")

    def test_synonyms_all_count_as_explained(self):
        """「还是/仍是/没填」是同一个意思，不许因为用词不同判红。"""
        for phrase in ("还是占位符", "仍是占位符", "没填", "未填"):
            with self.subTest(phrase=phrase):
                self.assertFalse(
                    self._probe(f"# 探针\n\n读 `profile/behavioral.md`；"
                                f"该文件{phrase}时跳过这项并说明。\n"),
                    f"写了降级路径（{phrase}）却被判红——词表在按整句匹配")

    def test_never_sync_exemption_is_local_not_file_wide(self):
        """豁免必须就近生效，否则它是一个能把自己关掉的开关。"""
        far = "# 探针\n\nnever sync anything.\n" + "填充\n" * 300 + \
              "读 `profile/behavioral.md` 来校准语域。\n"
        self.assertTrue(self._probe(far),
                        "文件开头一句 never sync 就让三百行后的真实引用蒙混过关")
        near = "# 探针\n\n本命令 never sync `profile/behavioral.md`。\n"
        self.assertFalse(self._probe(near), "就近的豁免声明应当生效")
