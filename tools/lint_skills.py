#!/usr/bin/env python3
"""Lint the repo's skill shells and settings file.

Run from anywhere: python tools/lint_skills.py

Checks:
- Every SKILL.md (.claude/skills/*, .agents/skills/*) has YAML frontmatter that
  parses, with non-empty `name` and `description` keys
- `allowed-tools` Bash rules use the prefix form `Bash(<cmd>:*)`, not the
  exact-match space form `Bash(<cmd> *)` that no real invocation ever matches
- `allowed-tools` entries of the form `Bash(bun run <path>:*)` point at files
  that exist (skill paths resolve relative to the repo root and to .agents/)
- Every workflow has a skill shell in **both** families, and the two families
  hold the same set of shells. `tools/gen_entries.py` writes both in one run, so
  a shell missing from one family is that generator having run halfway
- Both directions: a shell present in both families with no `workflows/<name>.md`
  is an entry into an empty room (the per-workflow loop above cannot see it, and
  the family-set guard only compares the two families to each other). Exempts the
  hand-written routing shell - `HANDWRITTEN_SHELLS`
- `.claude/commands/` holds **nothing**: command stubs were deleted once skills
  started providing the slash-command syntax in every tool. A file appearing
  there after this is a hand-written second landing spot for a rule, which
  AGENTS.md forbids ("唯一权威来源") - the index it should have gone into is
  `workflows/INDEX.md`
- .claude/settings.json is valid JSON with a permissions.allow list

NOT checked here (deliberately, and where it lives instead):
- Whether `allowed-tools` *covers* everything the skill's workflow actually runs
  -> tests/test_skill_permissions_cover_its_workflow.py. This lint asks "are the
  rules you wrote well-formed"; that test asks "did you write all the ones you
  need". Two skills were missing their `python tools/*.py` rules for a long time
  precisely because nothing asked the second question.
- Whether a `python tools/x.py --flag` cited in a workflow exists and has that
  flag -> tests/test_cross_references_resolve.py.

Exit code 0 on success, 1 with a failure list otherwise.
"""

import json
import re
import sys
from pathlib import Path

# 管道/重定向时把输出定到 UTF-8。Windows 上 Python 只在 stdout 是真终端时才走
# WriteConsoleW；被管道接走就回落到 cp936(GBK)，而 Git Bash / VS Code / Windows
# Terminal 都按 UTF-8 解 —— 用户看到一屏乱码。这里的中文主要来自 argparse 的
# description / help，不是 print()，所以按 print 数中文的启发式扫不到它。
# 只改非 tty 那条路：真终端本来就对，强行改反而会让代码页 936 的 cmd.exe 开始乱码。
# 与 tools/_cli.py 的 force_utf8_output() 同一份逻辑；这里内联是因为本文件会被
# 测试单独拷进临时目录运行，不能依赖仓库里的任何模块。
for _s in (sys.stdout, sys.stderr):
    try:
        if _s is not None and hasattr(_s, "reconfigure") and not _s.isatty():
            _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass



# PyYAML 是这个脚本**唯一**的第三方依赖（流水线全程只用标准库，README「要装什么」
# 那张表里也只有这一行）。**但缺它不能让 `--help` 一起死**：本仓库对每个工具的契约是
# 「`--help` 不干活、退 0」（`tests/test_cli_contract.py`、`test_terminal_encoding.py`
# 都按这条枚举 `tools/*.py`）。
#
# 这里原来是模块级 `sys.exit`，于是没装 pyyaml 的机器上：
#   lint_skills.py --help        → 退出码 1，印一句看不出是「少装东西」的话
#   lint_skills.py --不存在的参数 → 退出码 1，而契约要求 argparse 的 2
#
# **两条都被测试钉着，却一直是绿的 —— 因为开发机上 pyyaml 装着。**
# 首次公开推送的 CI（ubuntu，没装 pyyaml）当场红了 7 个 error + 2 个 failure。
# 改成延迟到真要解析 YAML 那一刻才报，`--help` 与参数校验照常走 argparse。
try:
    import yaml
except ImportError:                                   # pragma: no cover - 环境相关
    yaml = None

#: 真要用 YAML 时才报缺依赖。退出码 1 = 「这件事此刻做不了」（同仓库其余工具的约定）。
_NEED_YAML = "lint_skills.py requires PyYAML: pip install pyyaml"

ROOT = Path(__file__).resolve().parent.parent
errors: list[str] = []

# 部分错误信息内嵌中文（如 '## 工作流索引'）。在无法表示中文的控制台编码下
# （英文 Windows 的 cp1252 等）print 会抛 UnicodeEncodeError，在错误打印循环里
# 把剩余全部发现连同可读的失败清单一起吞掉——降级为转义输出，不崩。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="backslashreplace")


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def _has_portal_skills() -> bool:
    """True if at least one portal directory exists under .agents/skills/.

    Checked against the actual filesystem (not the target string) so the
    zero-portal downgrade below self-heals the moment any portal skill
    (e.g. liepin-search) is installed.
    """
    skills_dir = ROOT / ".agents" / "skills"
    if not skills_dir.is_dir():
        return False
    return any(p.is_dir() for p in skills_dir.iterdir())


def check_skill(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        errors.append(f"{rel(path)}: missing YAML frontmatter (file must start with ---)")
        return
    end = text.find("\n---", 4)
    if end == -1:
        errors.append(f"{rel(path)}: unterminated YAML frontmatter")
        return
    try:
        data = yaml.safe_load(text[4:end])
    except yaml.YAMLError as exc:
        errors.append(f"{rel(path)}: frontmatter is not valid YAML: {exc}")
        return
    if not isinstance(data, dict):
        errors.append(f"{rel(path)}: frontmatter did not parse to a mapping")
        return
    for key in ("name", "description"):
        if not data.get(key):
            errors.append(f"{rel(path)}: frontmatter missing required key '{key}'")

    allowed = data.get("allowed-tools", "")
    if isinstance(allowed, str):
        # Bash rules must use the prefix form `Bash(<cmd>:*)`. The space form
        # `Bash(<cmd> *)` is an exact-match rule that no real invocation matches,
        # so the skill silently falls through to a prompt (or a denial inside a
        # restricted tool set) on every call. `.claude/settings.json` already uses
        # the colon form and security_guards.py pins it there - this covers the
        # SKILL.md half, which that guard cannot see.
        for entry in re.findall(r"Bash\(([^)]*)\)", allowed):
            e = entry.rstrip()
            if e.endswith("*") and not e.endswith(":*"):
                errors.append(
                    f"{rel(path)}: allowed-tools Bash rule is not in prefix form: "
                    f"Bash({entry}) - use `:*` not ` *`")
        for match in re.finditer(r"bun run ([^\s)]+)", allowed):
            # Strip the prefix-form suffix `:*` (and the bare `*` the older
            # space form left behind) before resolving the path on disk.
            target = match.group(1).rstrip("*").rstrip(":")
            if not target or target.endswith("/"):
                continue
            # Targets may contain globs (e.g. .agents/skills/*/cli/src/cli.ts);
            # require at least one existing file to match.
            if "*" in target:
                matches = list(ROOT.glob(target)) or list((ROOT / ".agents").glob(target))
                if not matches:
                    # .agents/skills/* is a pluggable portal-skill area: a bare
                    # fork with zero portals installed (before the first
                    # /job-add-portal, or between removing all portals and adding
                    # a replacement) is a legitimate state, not a broken path.
                    # Only warn, don't fail the build, when that is actually
                    # the current state - checked via _has_portal_skills(),
                    # not by string-matching the target path, so this downgrade
                    # self-heals as soon as any portal skill is installed and
                    # a genuinely broken glob under .agents/skills/ still fails.
                    if target.startswith(".agents/skills/") and not _has_portal_skills():
                        print(
                            f"note: {rel(path)}: allowed-tools glob matches no files "
                            f"(no portal skills installed yet): {target}"
                        )
                    else:
                        errors.append(f"{rel(path)}: allowed-tools glob matches no files: {target}")
            else:
                candidates = [ROOT / target, ROOT / ".agents" / target]
                if not any(c.is_file() for c in candidates):
                    errors.append(f"{rel(path)}: allowed-tools references a missing file: {target}")


def check_settings() -> None:
    path = ROOT / ".claude" / "settings.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f".claude/settings.json: {exc}")
        return
    if not isinstance(data, dict):
        errors.append(".claude/settings.json: expected top-level JSON value to be an object")
        return
    permissions = data.get("permissions", {})
    if not isinstance(permissions, dict):
        errors.append(".claude/settings.json: expected permissions to be an object")
        return
    if not isinstance(permissions.get("allow"), list):
        errors.append(".claude/settings.json: expected permissions.allow to be a list")


def check_misplaced_activation() -> None:
    """激活文件属于 users/<活动用户>/templates/，落在仓库根 = 解析出错。

    .gitignore 有根级 `templates/active-*.md` 兜底（防止误提交），但那同时也让
    `git status` 对这个文件沉默；没有这条检查，「.active_user 缺失/迁移未完成」
    就从一个响亮的症状变成静默的——用户以为模板已激活，`/job-apply` 却一直用默认模板。
    """
    for stray in sorted((ROOT / "templates").glob("active-*.md")):
        # 只给手工步骤：把「谁的激活文件该归到哪个用户」交给脚本去推断，会在共享 clone
        # 上把一个人的激活文件搬进另一个人的目录，之后 /job-apply 就用错人的个人资料起草。
        errors.append(
            f"{rel(stray)}: activation file sits in the repo root - it belongs in "
            "users/<active user>/templates/. This means .active_user was missing when "
            "/job-add-template ran, so the destination directory does not exist yet - "
            "create it first. Fix by hand, in this order: (1) make sure .active_user "
            "names your user (run /job-user); (2) mkdir -p users/<your user>/templates; "
            f"(3) mv {rel(stray).replace(chr(92), '/')} users/<your user>/templates/; "
            "or simply delete the stray file and re-run /job-add-template --use <name>.")


# workflows/ 正文必须工具中立：能力名写在 AGENTS.md 能力对照表，正文不点名工具。
NEUTRALITY_FORBIDDEN = ("WebFetch", "WebSearch", "AskUserQuestion",
                        "mcp__", "Agent tool", "$ARGUMENTS", "allowed-tools",
                        # Workflow bodies are the tool-neutral half: AGENTS.md
                        # sends every other tool to the index (「直接按「工作流索引」
                        # 读取并执行对应文件」, whose table lives in
                        # workflows/INDEX.md). So a body must not
                        # talk about itself as a *skill* - that is one tool's
                        # packaging, and phrases like "in this skill directory"
                        # send the reader somewhere that only exists under
                        # .claude/. Measured 2026-08-18: five such phrases
                        # survived the extraction of the bodies out of the skills,
                        # and one of them pointed at a template path that had not
                        # existed since the move.
                        "this skill", "本技能",
                        # Same reason, harder failure: a `.claude/…` path in a body
                        # is unreachable for anyone not running Claude Code.
                        ".claude/")
# workflows 正文允许使用的能力英文别名（AGENTS.md 能力表第一列必须定义它们）。
# 已知局限：正文引入清单之外的新短语检测不到——新增能力时同步维护这里。
CAPABILITY_PHRASES = {
    "web fetch": ("web fetch", "web-fetch"),
    "network search": ("network search",),
    "structured prompt": ("structured prompt",),
    "parallel sub-agents": ("parallel sub-agent",),   # 单复数同前缀
}
# 能力名的漂移写法：能力表里没有，也不该有。
# 这条检查**刻意不看 AGENTS.md**——它问的不是「别名有没有定义」，而是「正文别写这个
# 词」。若沿用 CAPABILITY_PHRASES 那套「canonical 出现在 AGENTS.md 里即放行」的机制，
# 任何人在 AGENTS.md 里提一句（哪怕是「旧写法，勿用」的说明）就会把它永久关掉。
FORBIDDEN_CAPABILITY_ALIASES = {
    ("web search", "web-search"): "network search",
}
# 3.0 之前的遗留 managed block：激活状态曾被写进共享框架文件，现在属于活动用户的
# templates/active-*.md。检测保留（老 fork 升级上来可能还带着它），指引一律是手工删除
# ——曾经能自动转换它的一次性迁移脚本已随「只保留公开仓库里真实会用到的东西」删除。
_ACTIVE_TEMPLATE_BLOCK = re.compile(
    r"<!--\s*BEGIN ACTIVE-TEMPLATE[^\n]*?-->\r?\n"
    r"((?:(?!<!--\s*BEGIN ACTIVE-TEMPLATE).)*?)"
    r"<!--\s*END ACTIVE-TEMPLATE\s*-->\r?\n?", re.S)
# 孤立 BEGIN / 孤立 END：块被删了一半的残渣。分开报，因为两者的手工处理位置不同。
# 正文里纯文字提到这个标记名不会命中任何一条（要求的是标记形状，不是裸 token）。
_ACTIVE_TEMPLATE_MARKER = re.compile(r"<!--\s*BEGIN ACTIVE-TEMPLATE")
_ACTIVE_TEMPLATE_END = re.compile(r"<!--\s*END ACTIVE-TEMPLATE")
# 指向 workflows 的悬空指针。整条字面量**只在这里写一次**：它原先在两处各抄一份
# （索引节内扫一遍、AGENTS.md 全文再扫一遍），而这两处的范围本来就不同，抄件飘掉的
# 症状是「reference/*.md 只在其中一处看得见」——正是下面那条注释记着的失误。
_DANGLING_WF = re.compile(r"workflows/([A-Za-z0-9_/-]+\.md)")
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


def _strip_code(text: str) -> str:
    """剥掉围栏代码块与行内代码——Claude Code 不求值它们里面的 @path 导入。

    按 CommonMark 的围栏规则匹配，而不是数 ``` 的个数：
    - 开头围栏是 ≥3 个反引号的游程，其后可以跟 info string（如 ```bash）；
    - **只有游程不短于开头、且该行除反引号外无其它内容**的行才闭合它；
    - 未闭合的围栏一直延伸到文件末尾。

    先前两版都栽在把「数量为奇数」当成「未闭合」：一个 ```` 包裹、内含单行 ``` 的
    合法片段会数出奇数个围栏，于是对一份完全正确的文件硬失败。用真正的匹配规则之后
    不再有歧义——未闭合就是「到文件末尾都算代码」，直接按这个语义剥掉即可。
    """
    keep, opener = [], None
    for line in text.splitlines():
        s = line.lstrip()
        run = len(s) - len(s.lstrip("`"))
        fence = run >= 3
        if opener is None:
            if fence:
                opener = run
            else:
                keep.append(line)
        elif fence and run >= opener and not s[run:].strip():
            opener = None                     # 合法闭合；其余行一律丢弃
    return _INLINE_CODE_RE.sub("", "\n".join(keep))

#: 两族技能壳的根。`.claude/skills/` 是 Claude Code 的运行时发现根，
#: `.agents/skills/` 是其余各家读的（2026-09-30 逐家核过：agy / Codex / Qoder /
#: Qwen Code / MiMo Code 都扫这里）。
#: 一份入口在两族各落一次，由 tools/gen_entries.py 一次生成 —— 与 tools/_entries.py
#: 的 SHELL_FAMILIES 同一个值（这里内联写死，是因为本文件会被测试单独拷进临时目录
#: 运行，不能 import 仓库里的任何兄弟模块）。
SHELL_FAMILIES = (".claude", ".agents")

#: 手写、不生成的壳 —— 与 tools/_entries.py 的 HANDWRITTEN_NAMES 同一个值，同一个
#: 「不能 import 兄弟模块」的理由。路由壳 `job-application-assistant` 没有对应的工作流
#: 正文（它是「聊到求职就自动接管」的入口，正文就是它自己），所以下面那条
#: 「壳要有正文」的反向检查要放行它。两边相等由
#: tests/test_one_value_one_home.py::test_the_hand_written_shells_match 钉住 ——
#: 那张按值扫的网只收 ≥2 项的容器，单名集合从网眼里漏过，所以手工钉。
HANDWRITTEN_SHELLS = frozenset({"job-application-assistant"})


def command_shells(fam: str) -> set:
    """这一族里**命令壳**的目录名，不含可插拔的渠道技能。

    渠道技能（判据：有 `cli/src/cli.ts`）只装在 `.agents` 族，把它算进「两族该一样」
    会让一条本来正常的仓库立刻红，而且红的还是没坏的那半边。判据正本在
    `docs/tool-entries.md` 的「但 `.agents/skills/` 下不只有渠道」那节，
    `/job-add-portal --list` 与这里同一份。

    ⚠️ 这里**只**摘渠道，不摘「对不上工作流的壳」：这个集合同时供着两族集合守卫，
    在谓词里过滤 = 悬空壳两处都看不见。那一向由 `check_workflow_layout()` 单独报。
    """
    skills = ROOT / fam / "skills"
    if not skills.is_dir():
        return set()
    return {d.name for d in skills.iterdir()
            if d.is_dir() and (d / "SKILL.md").is_file()
            and not (d / "cli" / "src" / "cli.ts").is_file()}


def check_workflow_layout() -> int:
    wf_dir = ROOT / "workflows"
    if not wf_dir.is_dir():
        return 0  # 迁移前的旧布局 fork：整组检查不适用
    # INDEX.md 是索引正本本身，不是一条命令工作流：它不需要技能壳入口，
    # 也不在自己的索引里登记自己（2026-09-29 索引表从 AGENTS.md 搬进来那天起）。
    # 其余对 workflows/*.md 的逐文件检查（入口、中立性、B2）照旧覆盖它——剥掉
    # 的只是「按命令工作流算的那几笔」。
    workflows = sorted(wf for wf in wf_dir.glob("*.md") if wf.stem != "INDEX")
    if not workflows:
        errors.append("workflows/: directory exists but holds no *.md workflow files")
    # 命令 stub 已在「技能壳覆盖斜杠命令」之后整体删除（19 份 .claude/commands/*.md）。
    # 这里反过来盯「别再长出来」：生成器接管之后，那个目录里再冒出文件，就是有人
    # 手写了一个命令的第二落点 —— AGENTS.md 只允许一个权威来源。
    # 原来那三条按 stub 形状判的检查（首行 `# /名`、必须指到 workflows/、不超过 5 行）
    # 一起作废：入口文件本身不该存在，它写成什么样都不用去看了。
    cmd_dir = ROOT / ".claude" / "commands"
    for p in sorted(cmd_dir.glob("*.md")) if cmd_dir.is_dir() else []:
        errors.append(
            f".claude/commands/{p.name}: command stubs are gone - entries are "
            "generated into .claude/skills/ and .agents/skills/ by "
            "tools/gen_entries.py; add the command to workflows/INDEX.md instead")
    for wf in workflows:
        # 壳目录与工作流同名。原来这里有一张 `{"scrape": "job-scraper", …}` 的
        # 手工映射表，存在的唯一理由就是两边名字对不上；命令统一加 job- 前缀后
        # 它退化成恒等映射，留着只会在下次加壳时忘了登记（漏登记的症状是「工作流
        # 没有入口」这种看起来像真缺陷的假报警）。同名即接线，不再有第二处要维护。
        #
        # 两族**分别**验，不是「任一族有就算过」：少一族 = 生成器只跑了一半，
        # 而那正好是让某一家工具敲不到这条命令的那种半坏状态。
        for fam in SHELL_FAMILIES:
            shell = ROOT / fam / "skills" / wf.stem / "SKILL.md"
            if not shell.is_file():
                errors.append(
                    f"workflows/{wf.stem}.md: no skill shell in {fam}/skills/"
                    f"{wf.stem}/ - run `python tools/gen_entries.py`")
                continue
            # 壳在、但正文不提它那份工作流 = 指针断了。生成物不会漂（漂了
            # `--check` 就红），手改过的壳会：这条留给「改了壳没跑生成器」那一次。
            if f"workflows/{wf.stem}.md" not in shell.read_text(
                    encoding="utf-8", errors="replace"):
                errors.append(
                    f"{fam}/skills/{wf.stem}/SKILL.md: shell does not reference "
                    f"workflows/{wf.stem}.md - the shell is the entry, the body is "
                    "the workflow; run `python tools/gen_entries.py`")
    # 反方向：两族各有一份壳、却没有 workflows/<名>.md —— 入口把用户领进一间空房间。
    # 上面那个循环是从工作流这一侧走的，看不见它；main() 里那条两族集合守卫只比
    # 两族彼此，两边同时多出来一份壳时它照样绿。
    # 不能把过滤塞进 command_shells()：那个谓词同时供着集合守卫，一过滤，悬空壳在
    # 两处都变成隐形，检查从「少一格」退成「整条没了」。
    stems = {wf.stem for wf in workflows}
    for fam in SHELL_FAMILIES:
        for name in sorted(command_shells(fam) - stems - HANDWRITTEN_SHELLS):
            errors.append(
                f"{fam}/skills/{name}/SKILL.md: no workflows/{name}.md - the shell is "
                "an entry into an empty room; a new command goes into "
                "workflows/INDEX.md, then run `python tools/gen_entries.py`")
    bodies = []
    for wf in sorted(wf_dir.rglob("*.md")):
        # bytes 读：read_text 走通用换行，会把孤立 \r 也当成换行，于是同一份内容
        # lint 说「有块」而按 bytes 读的迁移脚本说「没有」——两边必须看同样的字节。
        try:
            text = wf.read_bytes().decode("utf-8")
        except UnicodeDecodeError as exc:
            # 报成一条普通失败并继续。抛栈会让 stdout 全空，把仓库里其余**所有** lint
            # 错误一起吞掉——而迁移脚本的提示恰恰是「转成 UTF-8 后手工处理」，验证这条
            # 指引的工具不能是崩在该文件上的那一个。
            errors.append(f"{rel(wf)}: not valid UTF-8 ({exc.reason}) - re-save it as "
                          "UTF-8; workflows are read as bytes and decoded strictly")
            continue
        lower = text.lower()
        bodies.append(lower)
        for token in NEUTRALITY_FORBIDDEN:
            if token in text:
                # 两类禁忌，两种改法。给「this skill」提示「去查能力对照表」
                # 是答非所问——它要改的是**自称**，不是工具名。
                if token in ("this skill", "本技能", ".claude/"):
                    hint = ("workflow bodies are the tool-neutral half: AGENTS.md "
                            "routes every other tool to the command index (its table "
                            "is workflows/INDEX.md, its heading 「工作流索引」) - "
                            "say 'this workflow'/'这条工作流', and point at a path "
                            "every tool can reach")
                else:
                    hint = "use the capability names from AGENTS.md instead"
                errors.append(f"{rel(wf)}: tool-specific literal {token!r} - {hint}")
        for variants, canonical in FORBIDDEN_CAPABILITY_ALIASES.items():
            hit = next((v for v in variants if v in lower), None)
            if hit:
                errors.append(
                    f"{rel(wf)}: drifted capability alias {hit!r} - use {canonical!r}, "
                    "the name defined in the AGENTS.md capability table")
        # B4b: 工作流正文（含 reference/）禁止携带模板激活块（激活状态属于每用户目录）
        # 用原文 text（未小写化）匹配——BEGIN ACTIVE-TEMPLATE 是大写标记，小写化会漏检。
        posix = wf.relative_to(ROOT).as_posix()
        blocks = _ACTIVE_TEMPLATE_BLOCK.findall(text)
        if blocks:
            # 指引一律是**手工步骤**，不给会改文件的命令：一个只承诺「清掉一个陈旧的块」
            # 的提示，不该触发搬动个人数据那种规模的改动。
            hint = ("把该块整段删掉即可（激活状态改由 /job-add-template 写进活动用户的 "
                    "templates/active-*.md）；块里记的模板名，用 "
                    "/job-add-template --use <名字> 重新激活一次")
            errors.append(
                f"{posix}: contains an ACTIVE-TEMPLATE block - activation lives in "
                f"the active user's templates/active-*.md now, never in shared guidance. {hint}")
        # 孤立 BEGIN 是**独立**的一条，不是 elif：同一文件里既有完整块又有孤立标记时，
        # 只报完整块会让用户删完块以为完事——那条「还有半个标记」的指引必须一开始
        # 就给出来，否则用户先照着跑一遍无效命令再看到它。
        if len(_ACTIVE_TEMPLATE_MARKER.findall(text)) > len(blocks):
            errors.append(
                f"{posix}: has a BEGIN ACTIVE-TEMPLATE marker with no matching END - "
                "no tool excises an unpaired marker: delete it and its content by hand")
        if len(_ACTIVE_TEMPLATE_END.findall(text)) > len(blocks):
            errors.append(
                f"{posix}: has an END ACTIVE-TEMPLATE marker with no matching BEGIN - "
                "leftover from a partially removed block: delete the stray line by hand")
    all_bodies = "\n".join(bodies)

    # B2/B4a: 索引双向完整 + 能力别名有定义。这两项依赖 workflows 列表，留在本函数；
    # AGENTS.md/CLAUDE.md 的存在性与 @import 已移到 check_entry_points()——它们与
    # workflows/ 布局无关，挂在这个提前返回的函数里等于在旧布局 fork 上永远不跑。
    agents_md = ROOT / "AGENTS.md"
    if not agents_md.is_file():
        errors.append("AGENTS.md: missing - the workflows/ layout requires it as the "
                      "single entry point")
    else:
        agents_text = agents_md.read_text(encoding="utf-8")
        actual = {wf.stem for wf in workflows}
        # B2: 「是否已登记入索引」只看 `workflows/INDEX.md` 里「## 工作流索引」一节的
        # 正文（到下一个 ^## 或文件结尾为止），不看全文——否则工作流在角色段/能力表
        # 降级列里被提一句也会被误判为「已登记」。收尾用 (?=^## |\Z)：少了 \Z 分支，
        # 索引恰好是最后一节时整段匹配不上，会对一个明明存在的标题报 missing。
        # 正本原来在 AGENTS.md；2026-09-29 索引表搬进 workflows/INDEX.md，锚点跟着搬，
        # 判据一个字没松：索引文件缺了那节标题，双向完整性无从核验，照样红。
        index_src = ROOT / "workflows" / "INDEX.md"
        index_text = (index_src.read_text(encoding="utf-8", errors="replace")
                      if index_src.is_file() else "")
        index_match = re.search(r"^## 工作流索引\s*$(.*?)(?=^## |\Z)", index_text, re.M | re.S)
        if index_match is None:
            errors.append(
                "workflows/INDEX.md: missing '## 工作流索引' section header - cannot verify the "
                "bidirectional workflow index")
        else:
            # 「登记入索引」这一判定**故意只用顶层名**的正则：`reference/04-job-evaluation.md`
            # 那样的共享资料不是命令，不该出现在索引表里。下面那两处「指针指不指得到文件」
            # 用的是 _DANGLING_WF（认斜杠），三处判的是三件事。
            referenced = set(re.findall(r"workflows/([A-Za-z0-9_-]+)\.md", index_match.group(1)))
            for stem in sorted(actual - referenced):
                errors.append(f"workflows/INDEX.md: workflow not in the index: workflows/{stem}.md")
            # 「索引行指向不存在的文件」这一向，原来由下面那段对 AGENTS.md 全文的悬空
            # 指针扫描顺带覆盖（表当时就住在 AGENTS.md 里）。表搬走后必须跟着搬，
            # 否则索引里写一个不存在的 workflows/x.md 只剩测试网兜着、lint 全盲。
            for target in sorted(set(_DANGLING_WF.findall(index_match.group(1)))):
                if not (wf_dir / target).is_file():
                    errors.append(f"workflows/INDEX.md: references missing workflows/{target}")
        # 悬空指针反过来要看**全文**，且必须覆盖 workflows/reference/*.md：角色段写着
        # 「按 `workflows/reference/04-job-evaluation.md` 评估职位」，而只匹配顶层名的
        # 那个正则（上面 `referenced` 用的）根本看不见它——那恰恰是这段注释给出的
        # 动机本身。只有「登记入索引」那一判定限于索引节内。
        for target in sorted(set(_DANGLING_WF.findall(agents_text))):
            if not (wf_dir / target).is_file():
                errors.append(f"AGENTS.md: references missing workflows/{target}")
        lower_agents = agents_text.lower()
        for canonical, variants in CAPABILITY_PHRASES.items():
            if any(v in all_bodies for v in variants) and canonical not in lower_agents:
                errors.append(
                    f"AGENTS.md: capability alias {canonical!r} is used in workflows/ "
                    "but not defined in the capability table")

    return len(workflows)


_FENCE_CMD = re.compile(r"```(?:bash|sh|shell|console)\n(.*?)```", re.S)


def _fenced_commands(text: str) -> set:
    """```bash 块里每一条要跑的命令（去掉行尾注释）。"""
    out = set()
    for block in _FENCE_CMD.findall(text):
        for line in block.splitlines():
            line = line.strip().lstrip("$ ").split("#")[0].strip()
            if line:
                out.add(line)
    return out


def check_entry_points() -> None:
    """**只要 AGENTS.md 存在**，CLAUDE.md 就必须真正 @import 它——与 workflows/ 无关。

    这条原本住在 check_workflow_layout() 里，而那个函数在没有 workflows/ 时提前返回，
    于是一个删掉了 workflows/、或把正文搬回 .claude/ 的仓库，即使 CLAUDE.md 的导入写成
    反引号/代码块形式（永远不把规则载入上下文），lint 照样打印 OK。

    判据是「AGENTS.md 存在」而不是无条件：3.0 之前的布局本来就没有 AGENTS.md，规则直接
    住在 CLAUDE.md 里，对那种 fork 要求它存在是误伤。「workflows/ 布局下 AGENTS.md 必须
    存在」由 check_workflow_layout() 负责。
    """
    if not (ROOT / "AGENTS.md").is_file():
        return
    claude_md = ROOT / "CLAUDE.md"
    if not claude_md.is_file():
        errors.append("CLAUDE.md: missing - Claude Code needs it to import @AGENTS.md")
        return
    # 先剥掉围栏代码块与行内代码再判断：只看「前一个字符是不是反引号」会把围栏
    # 代码块里的 @AGENTS.md 示例当成真导入，而 Claude Code 根本不求值它。
    claude_text = claude_md.read_text(encoding="utf-8")
    if "@AGENTS.md" not in _strip_code(claude_text):
        errors.append(
            "CLAUDE.md: needs a real @AGENTS.md import - an occurrence inside backticks "
            "or a code fence stays literal and never loads the rules into context")
    # CLAUDE.md 自称「本文件不复述」「以下仅为 Claude Code 特有的补充」。判据取一个
    # 便宜又准的代理：**两份入口文件里出现同一条要跑的命令**，基本只可能是同一段流程
    # 被抄了两遍——工具专属的补充不会需要跑正本已经在跑的东西。
    #
    # 实测代价（2026-08-18）：两边都写着 `python tools/doctor.py` 的自检流程，而且
    # 抄件与正本**各自长出了对方没有的一条**。抄件多的那条（`.active_user` 指向的
    # 目录不存在时引导 /job-user）是中立规则，于是**只有读 CLAUDE.md 的工具拿得到**，
    # Codex / Gemini 那边整条丢失——恰恰违反了 AGENTS.md「唯一权威来源」的设定。
    shared = _fenced_commands(agents_text := (ROOT / "AGENTS.md").read_text(
        encoding="utf-8")) & _fenced_commands(claude_text)
    for cmd in sorted(shared):
        errors.append(
            f"CLAUDE.md: runs `{cmd}`, which AGENTS.md already runs - CLAUDE.md says "
            "it does not restate AGENTS.md. A rule that holds under any AI tool belongs "
            "in AGENTS.md; keep only 'where this lands in Claude Code' here")
    del agents_text


#: 会被 /job-setup 填充、但很可能留在占位符状态的可选 profile 文件。
#: 消费它们的工作流必须自己说清「未填时怎么办」，否则会拿 `[TRAIT_1]` 这类占位符
#: 推断出凭空编造的结论，或把没做的检查报成通过——两者都不会报错，只会静默失真。
_OPTIONAL_PROFILE_FILES = ("profile/behavioral.md", "profile/interview-star.md")

#: 判定「说清了」的证据。必须是**降级措辞**，且要求它出现在文件名附近（见下方邻近窗口）：
#: 早先一版把 "placeholder" 也算进来，结果每个工作流的 candidate.md 守卫里都有这个词，
#: 检查恒真、完全空转。
#: 「这个文件还没填」的说法。**按语义片段匹配，不按整句**——
#: 2026-08-20 实测：词表里有「仍是占位符」而没有「还是占位符」，一字之差就红，
#: 而作者明明写了降级路径。这个仓库为同一形状付过三次学费（「读过」vs「读了」漏 613 条、
#: 「预筛」vs「粗筛」漏 32 条），中文近义写法穷举不完，所以只认最短的公共片段。
_UNFILLED_MARKERS = ("未填", "占位符", "没填", "unfilled", "scaffold", "placeholder")

#: 文件名与降级措辞之间允许的最大距离（字符）。取值只需覆盖「一句话里同时提到两者」，
#: 放太宽会把文件另一处不相关的段落误判成已说明。
_MARKER_WINDOW = 500


def check_optional_profile_degradation() -> None:
    """消费可选 profile 文件的工作流，必须写明该文件未填时如何降级。

    实测起因：`profile/behavioral.md` 整份是 `/job-setup` 没填过的占位符（31 个 token），
    而 `/job-apply`、`/job-interview`、`/job-expand` 三个工作流都在读它——`/job-apply` 用它做语域检查、
    `/job-interview` 用它校准模拟面反馈、`/job-expand` 甚至往它里面追加内容。三处的 profile
    守卫却只检查 `candidate.md`。后果不是崩，而是静默失真：拿 `[PROFILE_TYPE]` 推断
    工作风格（凭空编造），或在核对清单里把没做的语域检查报成通过。

    这里不要求工作流必须「停下」——那太重，可选输入缺失本就该降级而非中止；
    只要求它**明确写出未填时的处理方式**，把口径固定在文件里，而不是靠执行时临场判断。
    """
    wf_dir = ROOT / "workflows"
    if not wf_dir.is_dir():
        return
    for wf in sorted(wf_dir.glob("*.md")):
        # setup 负责填这些文件、reset 负责清空它们，两者天然要提占位符，不适用本检查。
        if wf.stem in {"job-setup", "job-reset"}:
            continue
        # **不剥代码块**：/job-apply 的审稿者提示词整段在围栏块里，对 behavioral.md 的
        # 依赖就写在那儿。剥掉的话依赖就看不见了，检查会静默空转（本检查第一版即如此）。
        body = wf.read_text(encoding="utf-8")
        for rel in _OPTIONAL_PROFILE_FILES:
            positions = [m.start() for m in re.finditer(re.escape(rel), body)]
            if not positions:
                continue
            # 只是声明「绝不同步/绝不读取 profile」的，不算消费。
            # ⚠️ **就近判，不判整份**：这句话原来对整个文件生效，于是文件任何角落
            # 出现一次「never sync」，全篇所有引用都被放行——一个把自己关掉的开关。
            # 实测（2026-08-20）：探针文件开头写一句 never sync、几百行后真的去读
            # behavioral.md，检查全程绿。改成只豁免**引用附近**的那一处。
            positions = [
                pos for pos in positions
                if not any(w in body[max(0, pos - _MARKER_WINDOW): pos + _MARKER_WINDOW]
                           for w in ("never sync", "永不同步"))
            ]
            if not positions:
                continue
            explained = any(
                marker in body[max(0, pos - _MARKER_WINDOW): pos + _MARKER_WINDOW]
                for pos in positions
                for marker in _UNFILLED_MARKERS
            )
            if not explained:
                errors.append(
                    f"workflows/{wf.name}: reads {rel} but never says what to do when it is "
                    f"still an unfilled scaffold - add an explicit degradation path near the "
                    f"reference (skip the dependent check and say so), or the workflow will "
                    f"infer from [TRAIT_1]-style placeholders / report an unperformed check "
                    f"as passed")


def main() -> int:
    # argparse 是标准库。**这里不能 import 本仓库的模块**（比如共享的命令行 helper）：
    # 这个脚本会被测试**单独拷进一个临时目录**跑（见 tests 里的 shutil.copy），
    # 拷过去的只有它自己，任何跨文件 import 都会在那边直接 ImportError。
    import argparse
    argparse.ArgumentParser(description="检查两族技能壳与 workflows 的接线是否一致").parse_args()
    # `--help` 与未知参数在上一行就已经由 argparse 处理完并退出了，所以这道
    # 依赖检查放在它**后面** —— 缺 pyyaml 不该让「问一句怎么用」也失败。
    if yaml is None:
        sys.exit(_NEED_YAML)
    # 两族都扫。原来这里只扫 `.claude/skills/`，而 `.agents/skills/` 是其余各家读的：
    # 一族的 frontmatter 坏了、另一族的没查，等于半个仓库没人看。
    skills = [p for fam in SHELL_FAMILIES
              for p in sorted((ROOT / fam / "skills").glob("*/SKILL.md"))]
    if not skills:
        errors.append("no SKILL.md files found - glob roots are wrong or the tree moved")

    # 两族该是**同一批**壳：生成器一次写两族，少一族就是它只跑了一半。
    # 这条比「逐个工作流报缺壳」更早说清发生过什么（一次少 21 份，而不是 21 条各自
    # 像独立缺陷），也覆盖反方向：只在某一族多出来的壳（手写漏跑生成器）。
    # 渠道技能不在这个集合里 —— 它只装在 `.agents` 族，见 command_shells()。
    shells = {fam: command_shells(fam) for fam in SHELL_FAMILIES}
    left, right = SHELL_FAMILIES
    if shells[left] != shells[right]:
        gaps = []
        for fam, other in ((left, right), (right, left)):
            absent = sorted(shells[other] - shells[fam])
            if absent:
                gaps.append(f"{fam}/skills lacks {', '.join(absent)}")
        errors.append(
            f"skill families disagree on the shell set: {len(shells[left])} in "
            f"{left}/skills vs {len(shells[right])} in {right}/skills"
            + (f" ({'; '.join(gaps)})" if gaps else "")
            + " - entries are generated into both families by tools/gen_entries.py; "
              "run `python tools/gen_entries.py`")

    for skill in skills:
        check_skill(skill)
    check_settings()
    check_misplaced_activation()
    check_entry_points()
    check_optional_profile_degradation()
    n_workflows = check_workflow_layout()

    if errors:
        print(f"lint_skills: {len(errors)} failure(s)")
        for err in errors:
            print(f"  - {err}")
        return 1
    print(f"lint_skills: OK ({n_workflows} workflows, "
          f"{len(shells[left])} shells in {left}/skills, "
          f"{len(shells[right])} in {right}/skills, "
          f"{len(skills)} SKILL.md parsed, settings.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
