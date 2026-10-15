"""生成各 AI 工具的命令入口：两族技能壳 + 权限片段。

用法：
    python tools/gen_entries.py              # 写盘
    python tools/gen_entries.py --check      # 只比对；有差异退出 1 并列出文件（CI 用这条）
    python tools/gen_entries.py --print agy  # 打印 agy 的可粘权限片段（写进 SETUP.md 的那段）
    python tools/gen_entries.py --print claude|codex  # 同上，每家一份自己的形状

**生成物入库**，与 `web/dist` 那类 gitignored 产物相反：入口文件是用户 clone 下来
就要能用的东西，不是构建产物。入库的代价是会漂，所以 CI 跑 `--check`。

行尾由生成器定，**统一 CRLF**：本仓库盘上就是 CRLF，`AGENTS.md` 的字节账按盘上
CRLF 算（spec §4.3），一次行尾翻动会让闸门余量凭空变化。「跟随原文件」还有个洞——
一个存成 LF 的文件会永远保持 LF，`--check` 也不会说它不对。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# import 即把 stdout/stderr 定到 UTF-8（`_cli` 在模块级调 force_utf8_output()）。
# 这一句不是可选的：`--help` 的 description 与 `--check` 的失败清单都是中文，
# 而 Windows 上被管道接走时 stdout 回落到 cp936 —— 既乱码也会
# UnicodeEncodeError 崩掉（`tests/test_terminal_encoding.py` 按 `tools/*.py` 枚举这条）。
# 与仓库其余 CLI 同源（applied_jds / jd_store / gap_split 都是 `import _cli`）。
import _cli  # noqa: E402,F401  （只为编码副作用；本工具不读 .active_user，不涉及用户）
import _entries  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

#: `.claude/settings.json` 的 `permissions.allow`。
#: **只放仓库自己的确定性命令前缀**（CONTRIBUTING.md「限定到入口，不开宽授权」）。
#: 各壳自己 `allowed-tools` 里那些逐条派生，不在这里重复；这里放的是**跨壳共用**的：
#: 渠道 CLI 两条前缀、PDF 文本层校验、以及路由壳的 Skill 名。
#:
#: 渠道那两条**从 `_entries.PORTAL_BASH` 取**，不在这里抄第二遍（一值一家，
#: `tests/test_one_value_one_home.py` 那条规矩）。原来这里是一份手抄，于是 2026-09-29
#: 实测出「中间的 `*` 按字面比、通配那两条盖不住任何真实调用」时，改的地方只有一处
#: 判据（`PORTAL_BASH`），这份生成物跟着就对了 —— 而它没对上的那一刻，红的是
#: `test_every_allow_entry_has_a_source`，不是这里安静地留着另一套写法。
SETTINGS_ALLOW = (
    "Skill(job-application-assistant)",
    *_entries.shared_grants(),
)

SETTINGS_DEFAULT_MODE = "acceptEdits"

#: Gemini CLI 的权限文件**不生成**：2026-09-29/30 取证后整份撤回，
#: 那家工具本身也从本仓库的支持名单里整条删掉。
#:
#: 原来这一份是按「以为的样子」写的，读的是本机装好的 0.58.0 安装包里的 settings
#: schema（`node_modules/@google/gemini-cli/bundle/chunk-*.js`，schema 里连 label
#: 与 description 都是明文字符串，比文档可靠 —— 官方 `docs/cli/configuration.md`
#: 那条 raw URL 现在 404）：
#:
#:   * `tools.allowed` —— **存在**，类型 array<string>，schema 自带的例子是
#:     `["run_shell_command(git)", "run_shell_command(npm test)"]`，
#:     描述原话「Tool names that bypass the confirmation dialog」。
#:     也就是说**光写一个 `run_shell_command` 是把所有 shell 命令都免掉确认**，
#:     而原来生成的那份就正这么写着 —— 它比 `Bash(python tools/:*)` 宽得多。
#:   * `tools.autoAccept` —— **不存在**。整个 bundle 里只有内部变量
#:     `autoAcceptWorkspacePolicies`，schema 没有这个键；审批模式在
#:     `general.defaultApprovalMode`（迁移代码把 `tools.approvalMode` 标为
#:     已弃用并搬过去）。写进版本库的那个键**静默什么都不做**。
#:
#: 一条都没核实的还有：括号里的命令前缀到底怎么匹配（schema 只说
#: "See shell tool command restrictions for matching details"，bundle 里够不着实现）。
#: 所以整份撤回，不再猜。
#:
#: **撤回之后又现量过一轮，三条都是当天量的：**
#:   1. 那家已停：npm 包还在发版（0.61.0），但个人版登录通道关了
#:      —— 登录返回 `reasonCode: "UNSUPPORTED_CLIENT"` / `tierId: "free-tier"`，
#:      拿一个假 `GEMINI_API_KEY` 也绕不过去；官方把命令行这条线指向
#:      Antigravity CLI（用户当日告知）。所以探测那一档、渲染表那一格、
#:      `--print gemini` 这个片段一起删了 —— 不再教任何人粘它。
#:   2. **后继的 agy 不读这份文件**：本机的 `agy` 二进制里
#:      `.gemini/settings.json`、`run_shell_command(`、`confirmationRequired`、
#:      `defaultApprovalMode` 四个字面量**全是 0 命中**，只有
#:      `antigravity-cli/settings.json`（它自己的用户级配置）在。所以「agy 是
#:      Gemini 分支，说不定还认这套键」这条推测是错的。
#:   3. 但 `security_guards.py` 里 `.gemini/settings.json` 的 key 面**留着**：
#:      包还在发版，能装上的人（企业通道 / 手里有旧安装的）手加一份时，那条宽授权
#:      （裸 `run_shell_command`）仍然要有人拦。它是 `required: False` 的检查，
#:      不生成、不要求存在，删掉它只会在有人真放一份时静默放行。
#:
#: 判据正本在**入库的文件**里：`SETUP.md`「各家工具的权限文件」一节逐条记着
#: 取证结论，`security_guards.py` 里 `.gemini/settings.json` 那条注释是同一结论的
#: 键面版本。
#: （原来这里指的是 `docs/superpowers/` 下那份设计文档的 §5.3 —— 而 `.gitignore`
#: 把那一整片排除出版本库，clone 出去的人点不到这个出处。「规则真、出处假」正是
#: 本仓库点名的失败模式（`AGENTS.md`「每一处引导都要写出该敲的命令」那节记着它）。）

GENERATED_NOTE = ("由 tools/gen_entries.py 生成，"
                  "改 workflows/INDEX.md 或 tools/_entries.py，别改这里")

#: 可粘片段的工具名。**每家一份**，不是把 Claude 那四条抄给别家 ——
#: 上一版 `--print agy` 印的就是 Claude 的清单，里面那条 `Skill(...)` 是
#: Claude 独有语法，而那段是要贴进 SETUP.md 给用户照粘的（评审抓到）。
#: `gemini` 也在 2026-09-29/30 那轮从这里删掉（那家已停，理由在上面那段）。
SNIPPET_TOOLS = ("claude", "codex", "agy")


def _settings_json() -> str:
    return json.dumps({"permissions": {
                          "defaultMode": SETTINGS_DEFAULT_MODE,
                          "allow": list(SETTINGS_ALLOW),
                      }},
                      ensure_ascii=False, indent=2) + "\n"


def desired_files(root: Path = ROOT) -> dict[Path, str]:
    """路径 → 应有的内容。**不写盘**，`--check` 与单测都调它。"""
    out: dict[Path, str] = {}
    for fam in _entries.SHELL_FAMILIES:
        for name in _entries.generated_names():
            out[root / fam / "skills" / name / "SKILL.md"] = _entries.render_shell(name)
    out[root / ".claude" / "settings.json"] = _settings_json()
    # Gemini / Codex / agy 的权限文件一个都不生成，理由逐条在上面那段与 `--print` 里。
    # 生成一个「静默不生效」的文件比不生成坏：它会被信任、被提交、被当作已经批过。
    return out


def _render(text: str) -> bytes:
    """LF → CRLF，然后编码。生成物的行尾由这里定，不看原文件。"""
    return text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_render(text))


def diff(root: Path = ROOT) -> list[str]:
    """有差异的文件（相对路径，正斜杠），排序稳定。缺文件也算差异。"""
    out = []
    for path, want in sorted(desired_files(root).items()):
        rel = str(path.relative_to(root)).replace("\\", "/")
        if not path.is_file():
            out.append(f"{rel}（缺）")
        elif path.read_bytes() != _render(want):
            out.append(rel)
    return out


def write_all(root: Path = ROOT) -> list[Path]:
    wrote = []
    for path, text in sorted(desired_files(root).items()):
        _write(path, text)
        wrote.append(path)
    return wrote


def _bare(entry: str) -> str:
    """一条 `SETTINGS_ALLOW` → 「授权了哪条命令」的核心，连 `:*` 前缀星号一起去掉。

    剥壳这一步住在 `_entries.normalize_entry`（判据只有一份，见那里的注释）；
    这里只多剥 `:*` —— 那是 Claude 的「前缀匹配」记号，别家没有这个写法。
    """
    core = _entries.normalize_entry(entry)
    return core[:-2] if core.endswith(":*") else core


def _portal_cli_paths() -> list[str]:
    """盘上真装着的渠道 CLI 入口（相对路径，正斜杠）。

    「哪些目录算渠道」的判据不是目录位置，是**有没有 `cli/src/cli.ts`**
    （常驻那一条写在 `AGENTS.md`「工具特化」，整段来龙去脉在
    `docs/tool-entries.md`「工具特化」的 ⚠️ 那一段；`/job-add-portal --list`
    也按这条判）。这里复用它，不另立一份。
    """
    return sorted(p.relative_to(ROOT).as_posix().replace("\\", "/")
                  for p in (ROOT / ".agents" / "skills").glob("*/cli/src/cli.ts"))


def _concrete_prefixes(entry: str) -> list[str]:
    """一条前缀 → 各家都能直接照抄的具体前缀（通配段展开成盘上真有的渠道）。

    `Skill(...)` 返回空表：那不是命令前缀，是 Claude 独有的技能授权形状，
    抄给别家就是「一段贴过去静默不生效」的写法（`--print agy` 上一版犯的正是这条，
    2026-09-29 评审抓到）。各渲染器要提它，用**说明**提，不是原样提。

    通配必须展开的理由是**实测**的，不是洁癖：Codex 的 `prefix_rule` 按 token 逐段
    比，`pattern=["node", ".agents/skills/*/cli/src/cli.ts"]` 对
    `node .agents/skills/liepin-search/cli/src/cli.ts` 的判定是 `matchedRules: []`
    （2026-09-29 用 `codex execpolicy check` 跑出来的）。把一个别家不认的 `*`
    原样印进「可粘片段」，用户粘完得到的同样是静默不生效。
    """
    if entry.startswith("Skill("):
        return []
    bare = _bare(entry)
    if not bare:
        return []
    if "*" not in bare:
        return [bare]
    return [bare.replace(".agents/skills/*/cli/src/cli.ts", path)
            for path in _portal_cli_paths()]


def _snippet_claude() -> list[str]:
    return [
        "# Claude Code —— 本仓库真的生成这一份：.claude/settings.json",
        "# 内容与下面四条逐字相同（改前缀要改 `SETTINGS_ALLOW`，别改生成物）。",
    ] + [f"  {entry}" for entry in SETTINGS_ALLOW]


def _snippet_codex() -> list[str]:
    lines = [
        "# Codex CLI 0.159.0（2026-09-30 复核）—— 本仓库不生成 Codex 的权限文件，这一段只是形状。",
        "# 已实测：预批准不是 config.toml 里的键，而是 execpolicy 的 .rules 文件",
        "#（Starlark DSL）。形状与语义都跑过 `codex execpolicy check --rules <文件> <命令…>`：",
        "#   * pattern 是 token 列表，命令以它开头即放行（带参数照样盖得住）",
        "#   * token 里的 `*` 不是通配 —— 所以渠道那两条已按盘上装着的渠道展开",
        "# 没实测到的是：哪个目录下的 .rules 会被自动加载（只有 `-r/--rules <PATH>`",
        "# 显式指定这一条是确认存在的）。所以自己加时先跑上面那条 check 验一遍，",
        "# 别指望丢进某个目录就生效 —— 静默不生效比没有这条更坏。",
    ]
    for entry in SETTINGS_ALLOW:
        if entry.startswith("Skill("):
            lines.append('# 跳过 Skill(...)：那是 Claude 的技能授权形状，Codex 侧无对应物')
            continue
        for prefix in _concrete_prefixes(entry):
            tokens = ", ".join(f'"{token}"' for token in prefix.split())
            lines.append(f'prefix_rule(pattern=[{tokens}], decision="allow")')
    return lines


def _snippet_agy() -> list[str]:
    return [
        "# Antigravity CLI (agy) 1.2.13（2026-09-30 复核）—— 本仓库不写 agy 的配置（它在用户主目录，归用户）。",
        "# 权限片段的 schema 没核实到，所以这里不给可直接粘贴的配置文件写法，只给",
        "# 要授权的那几条命令前缀（中立写法，不带任何家的语法包装）。",
        "# 实测依据：agy.exe 里搜不到 allowed_patterns / approval_policy / approval_mode /",
        "# allow_inline_scripts / allow_dangerous_commands 这些键名（Go 的 toml tag 会以",
        "# 字面量留在二进制里）—— 本机 ~/.antigravity/config.toml 用的正是这套键名，",
        "# 而它每一项都静默不生效；别照着那份教别人。",
        "# 核实到的只有命令行开关（`agy --help`）：",
        "#   --mode accept-edits            自动允许改文件，命令仍然逐条问",
        "#   --sandbox                      开终端沙箱限制",
        "#   --dangerously-skip-permissions 全部自动批准（本仓库不推荐，等于把闸门拆了）",
        "# 下面不含 `Skill(...)` 那一条 —— 那是 Claude 的技能授权，agy 没有对应物。",
    ] + [f"  {prefix}" for entry in SETTINGS_ALLOW
         for prefix in _concrete_prefixes(entry)]


def snippet(tool: str) -> str:
    """某一家工具的可粘权限片段。**逐家一份**，全部从 `SETTINGS_ALLOW` 派生，不手抄。"""
    renderer = {"claude": _snippet_claude, "codex": _snippet_codex,
                "agy": _snippet_agy}[tool]
    return "\n".join(renderer()) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="gen_entries.py",
        description="生成两族技能壳（.claude/skills、.agents/skills）与权限片段。"
                    "正本是 workflows/INDEX.md 与 tools/_entries.py 的 MANIFEST。")
    ap.add_argument("--check", action="store_true",
                    help="只比对不写盘；有差异退出 1 并列出文件（CI 用这条）")
    ap.add_argument("--print", choices=SNIPPET_TOOLS, dest="print_what",
                    help="打印某一家工具的可粘权限片段（每家一份，都从 SETTINGS_ALLOW 派生），不写盘")
    args = ap.parse_args(argv)

    if args.print_what:
        print(snippet(args.print_what), end="")
        return 0

    if args.check:
        drift = diff()
        if drift:
            print(f"{len(drift)} 份生成物与派生器不一致 —— "
                  "跑 `python tools/gen_entries.py` 再提交：")
            for rel in drift:
                print(f"  {rel}")
            return 1
        print(f"OK：{len(desired_files())} 份生成物都是最新的")
        return 0

    wrote = write_all()
    print(f"写了 {len(wrote)} 份：")
    for p in wrote:
        print(f"  {p.relative_to(ROOT)}")
    print(f"\n{GENERATED_NOTE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
