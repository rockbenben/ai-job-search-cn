# -*- coding: utf-8 -*-
"""宿主 AI 编码工具探测 + doctor 输出的命令形式适配。

为什么有这些断言：
- 探测信号全是对真实安装取证来的（2026-09-12 起，逐家复核到 2026-09-30）：
  Claude Code 注入 `CLAUDECODE=1`（不是 `CLAUDE_CODE` / `CLAUDE`，那两个从没存在过）、
  agy 注入 `ANTIGRAVITY_AGENT=1`、Qoder 注入 `QODERCN_CLI=1` /
  `QODER_AGENT_SDK_ENTRYPOINT=sdk-ts`（2026-09-29 在一个真 Qoder CN 会话里现测）、
  Qwen Code 注入 `QWEN_CODE=1`、MiMo Code 注入 `MIMOCODE=1`、MCode 注入
  `MAVIS_SESSION_TRANSFER_CLIENT`（2026-10-13 加；后三家出处见
  `_cli.detect_code_tool` 的 docstring）。
  上一版因为信号是凭空写的，真 Claude Code 会话被认成 generic——当时那一档是
  免斜杠，于是整个面板默认少一层斜杠。所以下面专门有一组断言「不该再认的信号
  不许触发」。**加新信号时 `TOOL_ENV` 必须跟着加**：跑测试的机器正好是那一档时，
  全表用例一起红，报的还是「认不出来」那种看不懂的话（Qoder 与 MCode 各栽过一回）。
- doctor 因「只用标准库、不 import 仓库模块」的契约保着一份逐字副本
  （见 doctor.detect_code_tool 的 docstring），这份测试同时钉两份。
"""

import contextlib
import io
import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import _cli  # noqa: E402
import doctor  # noqa: E402

#: 探测会碰到的全部变量。每个用例先把它们清干净，再按需设置。
TOOL_ENV = (
    "JOBS_CODE_TOOL",
    "ANTIGRAVITY_AGENT", "ANTIGRAVITY_AGENTAPI_EXE", "ANTIGRAVITY_LS_VERSION",
    "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT",
    # Qoder / MCode：跑在它们里面时这几个**就在环境里**，不列进来下面的
    # 用例会被宿主会话污染（`({}, "generic")` 那条会当场红）。
    # Qoder 那次是真栽过：2026-10-13 给 MCode 加 `MAVIS_*` 时它又原样
    # 栽了一回——每加一档信号都得在这张表里补一行，否则**跑测试的那台机器
    # 正好是那一档**时，全表用例一起红，而且报的是「'mavis' != 'generic'」，
    # 看不出是夹具漏了。
    "QODERCN_CLI", "QODER_AGENT_SDK_ENTRYPOINT",
    "QWEN_CODE", "MIMOCODE", "MAVIS_SESSION_TRANSFER_CLIENT",
    # 下面两组都「不许再认」，但**理由不同，别混成一档**：
    # 1) 上一版凭空写、实测根本不存在的假信号 —— 留着验它们不再触发。
    "CLAUDE_CODE", "CLAUDE", "CURSOR_VERSION", "TERM_PROGRAM", "CODEX",
    # 2) `GEMINI_CLI` 是**真信号**（Gemini CLI 确实注入过它），只是那家工具
    #    已停：官方把个人版登录通道关了（`reasonCode: UNSUPPORTED_CLIENT` /
    #    `tierId: free-tier`），后继是 Antigravity CLI（用户 2026-09-30 告知）。
    #    探测认它没有意义 —— 认出来也只是给一个装不上的工具印名字，
    #    所以整档删掉，它落回 generic。⚠️ 当时落回正好兜得住，是因为那之前
    #    generic 就是免斜杠；**2026-10-13 那一档翻成了带斜杠**，所以现在
    #    「删掉一档」不再是零成本的补救——它会让命令形式一起跟着变。
    "GEMINI_CLI",
)


@contextlib.contextmanager
def tool_env(**values):
    """临时替换宿主工具相关环境变量，退出时原样还回。"""
    saved = {k: os.environ.get(k) for k in TOOL_ENV}
    try:
        for k in TOOL_ENV:
            os.environ.pop(k, None)
        os.environ.update(values)
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@contextlib.contextmanager
def override_tool(name):
    """JOBS_CODE_TOOL 覆盖，其余信号保持环境原样（测优先级用）。"""
    saved = os.environ.get("JOBS_CODE_TOOL")
    os.environ["JOBS_CODE_TOOL"] = name
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop("JOBS_CODE_TOOL", None)
        else:
            os.environ["JOBS_CODE_TOOL"] = saved


#: (环境变量, 期望判定)。两份 detect 都按这张表对拍。
SCENARIOS = [
    ({}, "generic"),
    ({"ANTIGRAVITY_AGENT": "1"}, "antigravity"),
    ({"ANTIGRAVITY_AGENTAPI_EXE": "x"}, "antigravity"),
    ({"ANTIGRAVITY_LS_VERSION": "1"}, "antigravity"),
    ({"CLAUDECODE": "1"}, "claude"),
    ({"CLAUDE_CODE_ENTRYPOINT": "cli"}, "claude"),
    ({"QODERCN_CLI": "1"}, "qoder"),
    ({"QODER_AGENT_SDK_ENTRYPOINT": "sdk-ts"}, "qoder"),
    ({"QWEN_CODE": "1"}, "qwen"),
    ({"MIMOCODE": "1"}, "mimo"),
    ({"MAVIS_SESSION_TRANSFER_CLIENT": "1"}, "mavis"),
    # 在 Qoder 的终端里再开 Claude Code：两家信号同时在，Claude 赢
    # （优先级问题，不是形式问题——两家现在实测都吃斜杠，见 COMMAND_SYNTAX）。
    ({"CLAUDECODE": "1", "QODERCN_CLI": "1"}, "claude"),
    # 旧版虚构信号 —— 一个都不许再认。
    ({"CLAUDE_CODE": "1"}, "generic"),
    ({"CLAUDE": "1"}, "generic"),
    ({"CURSOR_VERSION": "0.40.0"}, "generic"),
    ({"TERM_PROGRAM": "cursor"}, "generic"),
    ({"TERM_PROGRAM": "vscode"}, "generic"),
    ({"CODEX": "1"}, "generic"),
    # Gemini CLI 已停（真信号，但工具没了）—— 与上面那组假信号理由不同，
    # 所以单列一条：它**曾经**判 gemini，现在整档删掉，落 generic。
    ({"GEMINI_CLI": "1"}, "generic"),
]


class TestCodeToolDetection(unittest.TestCase):

    def test_detect_matrix(self):
        for env, expected in SCENARIOS:
            with self.subTest(env=env):
                with tool_env(**env):
                    self.assertEqual(_cli.detect_code_tool(), expected)

    def test_detect_code_tool_agrees_between_doctor_and_cli(self):
        """doctor 的副本与正本 _cli.detect_code_tool 判得完全一样。"""
        for env, expected in SCENARIOS:
            with self.subTest(env=env):
                with tool_env(**env):
                    self.assertEqual(
                        doctor.detect_code_tool(), _cli.detect_code_tool())
                    self.assertEqual(doctor.detect_code_tool(), expected)

    def test_override_beats_autodetect(self):
        with tool_env(ANTIGRAVITY_AGENT="1"), override_tool("claude"):
            self.assertEqual(_cli.detect_code_tool(), "claude")
            self.assertEqual(doctor.detect_code_tool(), "claude")

    def test_override_passes_unknown_name_through(self):
        # cursor / codex 自动探测分不出来，但 JOBS_CODE_TOOL=cursor 这类
        # 手工指定要原样透传 —— doctor 的脚注靠这个叫出工具名。
        with tool_env(CLAUDECODE="1"), override_tool("cursor"):
            self.assertEqual(_cli.detect_code_tool(), "cursor")
            self.assertEqual(doctor.detect_code_tool(), "cursor")

    # ---- adapt_commands：免斜杠的那一档（2026-10-13 起只剩 codex）去斜杠，其余原样 ----

    def test_adapt_strips_slash_only_for_the_unverified_group(self):
        # **2026-10-13：免斜杠的只剩 codex 一家。** generic（认不出来的那一批）
        # 翻成了带斜杠，理由见 `doctor.COMMAND_SYNTAX` 上方那段。
        for tool in ("codex",):
            with self.subTest(tool=tool):
                self.assertEqual(
                    doctor.adapt_commands("跑 /job-auto 接着抓", tool),
                    "跑 job-auto 接着抓")
                self.assertEqual(
                    doctor.adapt_commands("/job-apply <url>", tool),
                    "job-apply <url>")
                self.assertEqual(
                    doctor.adapt_commands("`/job-rank --all`", tool),
                    "`job-rank --all`")
                # 路径与 URL 里的片段不是命令，不许动。
                self.assertEqual(
                    doctor.adapt_commands(
                        "workflows/job-apply.md 里写着 /job-setup", tool),
                    "workflows/job-apply.md 里写着 job-setup")
                self.assertEqual(
                    doctor.adapt_commands("https://x//job-auto", tool),
                    "https://x//job-auto")
        # 实测吃斜杠的六家 + 认不出来的那一批：一切原样（剥掉就是白退回裸形式）。
        for tool in ("claude", "antigravity", "mimo", "mavis", "qoder", "qwen",
                     "generic"):
            with self.subTest(tool=tool):
                self.assertEqual(
                    doctor.adapt_commands("跑 /job-auto 接着抓", tool),
                    "跑 /job-auto 接着抓")
                # 路径与 URL 里的片段在「原样」这一档同样不许动。
                self.assertEqual(
                    doctor.adapt_commands(
                        "workflows/job-apply.md 里写着 /job-setup", tool),
                    "workflows/job-apply.md 里写着 /job-setup")
                self.assertEqual(
                    doctor.adapt_commands("https://x//job-auto", tool),
                    "https://x//job-auto")

    def test_adapt_passes_non_string_through(self):
        self.assertIs(doctor.adapt_commands(None, "generic"), None)

    # ---- doctor.main 全输出适配（48 个 print 点一起被盖住）----

    def _run_main(self, tool):
        with override_tool(tool), contextlib.redirect_stdout(io.StringIO()) as buf:
            rc = doctor.main([])
        return rc, buf.getvalue()

    def test_main_antigravity_keeps_the_slash_form(self):
        rc, out = self._run_main("antigravity")
        self.assertEqual(rc, 0)
        # agy 的 `/` 面板就是技能列表（用户 2026-09-28 当场测过 `/job-scrape`），
        # 所以这一档给斜杠。
        self.assertRegex(out, doctor._SLASH_CMD)
        self.assertIn("已识别为 Antigravity", out)
        self.assertNotIn("不带开头斜杠", out)

    def test_main_generic_output_is_slash_free(self):
        _rc, out = self._run_main("generic")
        # **2026-10-13 改了判据**：generic 从「免斜杠」翻成「带斜杠」，
        # 所以这一条现在反过来验——认不出来的那一批**保留**斜杠，
        # 理由与实测见 `doctor.COMMAND_SYNTAX` 上方。
        # Codex 那一档免斜杠由 `test_main_codex_output_has_no_slash` 单独钉。
        self.assertRegex(out, doctor._SLASH_CMD)
        self.assertNotIn("用 Claude Code 时带斜杠", out)

    def test_main_codex_output_has_no_slash(self):
        """Codex 是唯一免斜杠的那一档（它的二进制里印着会拦）。"""
        _rc, out = self._run_main("codex")
        self.assertNotRegex(out, doctor._SLASH_CMD)
        self.assertIn("不带开头的斜杠", out)

    def test_main_says_which_tool_it_thinks_it_is_for_everyone(self):
        """这一行每家都印 —— 探测错了的唯一线索。

        原来只有去斜杠那几家印，吃斜杠的那几家什么也不说 —— 而探测错的人恰恰
        多半落在那一边，输出里找不到任何线索，`JOBS_CODE_TOOL` 那条手工纠正
        正是给他准备的。

        **名单从 `COMMAND_SYNTAX` 数，不比手抄** —— 那张表的键与探测函数源码里的
        `return` 字面量逐条对拍（正本在
        `tests/test_slash_survives_where_the_palette_is_the_skill_list.py`），
        所以给探测加一档而忘了给它一个名字 → 这里当场红。`generic` 不在
        `_TOOL_LABELS` 里是设计：认不出来时印的是另一句（「没认出你在用哪家助手」）。
        """
        for tool in sorted(set(doctor.COMMAND_SYNTAX) - {"generic"}):
            with self.subTest(tool=tool):
                label = doctor._TOOL_LABELS.get(tool)
                self.assertTrue(label, f"{tool} 探测得出来却没有名字可印")
                _rc, out = self._run_main(tool)
                self.assertIn(f"已识别为 {label}", out)
                self.assertIn("JOBS_CODE_TOOL=", out, "认错了得知道怎么纠正")

    def test_the_manual_override_hint_lists_every_detectable_tool(self):
        """脚注那串 `JOBS_CODE_TOOL=a|b|c` 得跟探测的档位同步。

        这串在 `doctor.py` 里是从 `COMMAND_SYNTAX` 派生的，所以**期望值必须在这里
        写死** —— 拿 `set(doctor.COMMAND_SYNTAX)` 去比它就是自己比自己，永远绿。
        写死之后：探测加一档 → `COMMAND_SYNTAX` 少格子先红（正本在另一份测试文件），
        表里加了格而派生串漏了名字 → 这里红。
        **2026-10-13：`codex` 进这串了。** 原来它不在里面，理由是
        「探测不出来，手工指定也不改变命令形式」——那一条在 `generic` 翻成
        带斜杠之后**不成立了**：`JOBS_CODE_TOOL=codex` 现在是少数能把命令
        切回免斜杠的手段（面板上那个开关之外唯一的退路），不列出来就成了死路。
        `cursor` 仍不在：吃不吃斜杠没实测过，列出来等于宣称量过。
        """
        _rc, out = self._run_main("generic")
        hint = next(line for line in out.splitlines() if "JOBS_CODE_TOOL=" in line)
        listed = set(re.findall(r"[a-z]+", hint.split("JOBS_CODE_TOOL=", 1)[1]))
        self.assertEqual(listed, {"claude", "antigravity", "mimo", "mavis",
                                  "qoder", "qwen", "codex", "generic"})


if __name__ == "__main__":
    unittest.main()
