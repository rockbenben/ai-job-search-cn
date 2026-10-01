#!/usr/bin/env python3
"""Supply-chain guards for the template's riskiest surfaces.

Run from anywhere: python tools/security_guards.py

This repo ships pre-approved tool permissions and CLI code that every
fork user executes. These guards make the dangerous changes LOUD, not
impossible: a PR that intentionally needs one of them must make the entry
derivable from the generator (or update the reviewed key surface in this file)
in the same diff, so the change is explicit and reviewable rather than buried.

Checks:
1. Every permission file — each one against ITS OWN key surface
   (SETTINGS_KEY_SCHEMAS), and every entry inside it against what the entry
   manifest can actually derive: gen_entries.SETTINGS_ALLOW, the Bash rules of
   each generated skill shell, and _entries.PORTAL_BASH. Two halves, because
   neither alone is a gate: a legal key with a hand-added wide value
   (Bash(python tools/:*) opens the whole tools/ directory) passed the old
   single-file string allowlist, and a second permission file (.gemini/,
   .codex/) was not read at all. Catches any grant that would auto-approve
   commands on every fork (Bash(*), Bash(curl:*), Skill(*)). If the manifest
   itself cannot be loaded, this is reported as a failure — never skipped.
2. .gitignore — the personal-data ignore rules must all still be present,
   and no un-allowlisted negation (!pattern) may re-include them. Catches
   weakening that would make future users silently commit their tracker,
   profile exports, or application archives.
3. .agents/**/package.json — no npm/bun lifecycle scripts (preinstall,
   install, postinstall, prepare, prepack) and no trustedDependencies.
   Catches code execution smuggled into `bun install`.

Stdlib only. Exit 0 on success, 1 with a failure list otherwise.
"""

import json
import subprocess
import sys
from pathlib import Path

# 管道/重定向时把输出定到 UTF-8。Windows 上 Python 只在 stdout 是真终端时才走
# WriteConsoleW；被管道接走就回落到 cp936(GBK)，而 Git Bash / VS Code / Windows
# Terminal 都按 UTF-8 解 —— 用户看到一屏乱码。这里的中文主要来自 argparse 的
# description / help，不是 print()，所以按 print 数中文的启发式扫不到它。
# 只改非 tty 那条路：真终端本来就对，强行改反而会让代码页 936 的 cmd.exe 开始乱码。
# 与 tools/_cli.py 的 force_utf8_output() 同一份逻辑；这里内联是因为**模块级不 import
# 仓库里的任何兄弟模块** —— 本文件会被测试拷进临时目录跑，模块级 import 会让它在
# 少了兄弟文件的那棵树上直接撞死。条目出处检查确实要用生成器，那是**函数里**惰性取的，
# 取不到就报成一条守卫失败（见 ManifestUnavailable），不是崩。
for _s in (sys.stdout, sys.stderr):
    try:
        if _s is not None and hasattr(_s, "reconfigure") and not _s.isatty():
            _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass



ROOT = Path(__file__).resolve().parent.parent
errors: list[str] = []

# 权限文件与**每个文件自己的 key 面**。各家格式不同（Claude 与 Gemini 那两份是 JSON，
# Codex 预批准走的是 execpolicy 的 `.rules`，形状完全不是一套），所以**按文件分**，
# 不共用一份白名单。一张表按文件分，就意味着「某家进不进这张表」问的是
# **它有没有一份会被自动读到的权限文件**——Codex 那一行的注释就是它没进来的理由。
#
# 原来只有 `ALLOWED_SETTINGS_KEYS = {"permissions"}` 与一份手抄的
# `ALLOWED_PERMISSIONS` 四条，看的也只有 `.claude/settings.json` 一个文件。
# 手抄那份的毛病不是「会漏」——它是**清单与生成物各写一遍同一个决定**，
# 生成器改了 `SETTINGS_ALLOW` 而这里没跟上时，红的是守卫、错的是清单
# （AGENTS.md「一条规则只贴在一个写手身上，另外两个照样会犯」）。
# 现在条目不再有第二份清单：条目要跟**生成器推得出来的那一份**比，
# 见 `derivable_entries()`。
#
# 报错按「顶层键.列表键」拼路径（Claude 那份就拼出 `permissions.allow must be a list
# of strings`），所以每条消息都指得到是哪个文件的哪个键下的哪一条。
#: `permissions.defaultMode` 允许的取值。**故意不含 `bypassPermissions`**：
#: 那等于把这份文件从「逐个入口预批」变成「全不询问」，而仓库的立场是
#: CONTRIBUTING.md「限定到入口，不开宽授权」。要放那一档，得先改这里的取值面，
#: 并说清为什么——盯这件事的是
#: `tests/test_security_guards.py::test_bypass_permissions_default_mode_fails`
#: 与 `tests/test_the_generator_and_the_guard_agree.py::test_bypass_permissions_mode_is_rejected`。
SCALAR_LEAVES = {"defaultMode": {"default", "acceptEdits", "plan"}}


SETTINGS_KEY_SCHEMAS = {
    ".claude/settings.json": {
        "top": {"permissions"},
        # allow = 预批（要对着清单比出处）；defaultMode = 标量，取值面在下面收紧。
        #
        # 2026-09-30 按本文件自己的规定加宽：报错文案一直写着「defaultMode 能整个
        # 关掉询问，要加就在同一次 PR 里显式加进 SETTINGS_KEY_SCHEMAS」。这次加的是
        # `acceptEdits`（文件编辑不再逐个问），**不是** bypassPermissions ——
        # 后者在 SCALAR_LEAVES 里根本不允许，见那里。
        "leaf": {"allow"},
        "scalars": SCALAR_LEAVES,
        "required": True,
    },
    # Gemini 那一份**本仓库不生成**（2026-09-29 读安装包 schema 取证后撤回：
    # `tools.autoAccept` 在 0.58.0 里根本不存在，而曾经生成过的
    # `tools.allowed: ["run_shell_command", …]` 是「所有 shell 命令免确认」
    # 那种宽授权——判据见 `gen_entries.py` 顶部那段）。
    #
    # **2026-09-30：Gemini CLI 本身停了**（npm 包还在发版，个人版登录通道关了，
    # 官方指向 Antigravity CLI），推荐它的那一半（`--print gemini`、SETUP.md 的
    # 粘贴段）一起删掉了。**这一行留着**，因为它是**检查**不是推荐：包既然还装得上，
    # 有人手放一份时那条宽授权仍然要红。`required: False`，不生成、不要求存在，
    # 留着对任何人零成本。
    # 顺带当天量掉一条推测：后继的 agy **不读**这份文件 —— 它的二进制里
    # `.gemini/settings.json`、`run_shell_command(`、`confirmationRequired`、
    # `defaultApprovalMode` 四个字面量全是 0 命中（只有它自己的
    # `antigravity-cli/settings.json` 在）。所以「agy 是 Gemini 分支，可能还认
    # 这套键」不成立，这一行守的确实只是老 Gemini 安装。
    # leaf 只列取证到的四个键（`core` / `allowed` / `confirmationRequired` /
    # `exclude`，都在安装包 settings schema 的 `tools` 块里）。`autoAccept` 不在，
    # 别把它加回来当合法键。
    ".gemini/settings.json": {
        "top": {"tools"},
        "leaf": {"core", "allowed", "confirmationRequired", "exclude"},
        "required": False,
    },
    # Codex 不放这一行：它预批准命令**不是 config.toml 里的键**，而是 execpolicy
    # 的 `.rules` 文件（Starlark DSL，`prefix_rule(pattern=[…], decision="allow")`，
    # 用 `codex execpolicy check` 实测过），而那个目录会不会被自动加载没实测到。
    # 给一个猜出来的 key 面等于给一份静默不生效的文件发通行证。取证与结论见
    # `SETUP.md`「各家工具的权限文件」一节。
}

PERMISSION_FILES = tuple(SETTINGS_KEY_SCHEMAS)

#: 每个权限文件里**哪些键是「预批」**（要对着派生清单比出处）。
#: `None` = 没有取证结论，整份文件都当预批收（`.gemini/settings.json` 就是：
#: 那一家我们不生成，但谁手放一份宽授权仍然要红）。
#: 标量键（`defaultMode`）也不在这里——它不是命令条目，取值面由 scalars 单独管。
GRANT_LEAVES = {
    ".claude/settings.json": {"allow"},
    ".gemini/settings.json": None,
}

#: 参照系（生成器的清单）要 import 兄弟模块，但**模块级不 import**：需要的时候在
#: 函数里惰性取，取不到就报成一条守卫失败（不是 traceback，也不是「跳过」——
#: 见 `ManifestUnavailable`）。这样「本文件从任何地方单独跑」仍然是一条清楚的
#: 失败信息，而不是一个 ImportError 崩溃；而它的夹具（`tests/test_security_guards.py`）
#: 带的是整个 `tools/` 加 `workflows/`，所以条目出处这一半在测试里是真的在跑。
sys.path.insert(0, str(Path(__file__).resolve().parent))


class ManifestUnavailable(RuntimeError):
    """推得出哪些条目这件事没了参照系 —— 宁可比不了就红，不要静默放行。"""


def normalize_entry(entry: str) -> str:
    """把各家的语法包装剥掉，留下可比的核心。判据在 `_entries.normalize_entry`。

    Gemini 写 `run_shell_command(python tools/doctor.py)`，Claude 写
    `Bash(python tools/doctor.py:*)` —— 守卫要问的是**授权了哪条命令**，
    不是哪一家怎么括起来。这里只做转发，不抄第二份正则。
    """
    import _entries

    return _entries.normalize_entry(entry)


def derivable_entries() -> set[str]:
    """生成器清单能推出的全部权限条目（已归一化）。

    三个来源，与 `gen_entries.py` / `_entries.py` 里真正写权限的那三处一一对应：

      1. `gen_entries.SETTINGS_ALLOW` —— 跨壳共用的那几条（写进权限文件的就是它）；
      2. 每个生成壳的 `allowed-tools` 里的 `Bash(...)` —— 由该壳工作流的
         ```bash 围栏与 `MANIFEST[...]["extra_tools"]` 推出来；
      3. `_entries.PORTAL_BASH` —— 渠道 CLI 的两条前缀。

    **不在这里发明任何条目**：这里只把已有的三处汇成一个集合。往这个集合里加一条
    的意思，是先去 `SETTINGS_ALLOW` 或某份工作流围栏里把它写出来。
    """
    try:
        import _entries
        import gen_entries
    except ImportError as exc:            # 部分 clone、或 tools/ 不完整
        raise ManifestUnavailable(
            f"cannot load the entry manifest ({exc}) — every permission entry needs a "
            "source in tools/gen_entries.py / tools/_entries.py, and there is none to "
            "compare against. Run this file from the repo's own tools/ directory."
        ) from exc

    out = {normalize_entry(e) for e in gen_entries.SETTINGS_ALLOW}
    for name in _entries.generated_names():
        for tool in _entries.allowed_tools(name):
            if tool.startswith("Bash("):
                out.add(normalize_entry(tool))
    for tool in _entries.PORTAL_BASH:
        out.add(normalize_entry(tool))
    return out


def _walk_strings(node, out: list[str]) -> None:
    if isinstance(node, dict):
        for value in node.values():
            _walk_strings(value, out)
    elif isinstance(node, list):
        out.extend(x for x in node if isinstance(x, str))


def permission_entries() -> dict[str, list[str]]:
    """每个**存在的**权限文件 → 它授权的条目（原文，未归一化）。

    整份文件递归收，不只看 `permissions.allow`：条目的家在哪家、挂在哪个键下，四家
    各不相同，而「这个文件到底预批了什么」要一次看全。键面另有 schema 逐家对着查
    （`SETTINGS_KEY_SCHEMAS`），这里只负责取值。
    """
    out: dict[str, list[str]] = {}
    for rel in PERMISSION_FILES:
        path = ROOT / rel
        if not path.is_file():
            continue
        if not rel.endswith(".json"):
            # TOML 那一家（Codex）的权限不在 config.toml 里，见上面那段注释：
            # 没有需要解析的文件，所以也没有解析器。真加一家时在这里补解析，
            # 别把 JSON 那条路当万能。
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue                      # 形状问题由 _check_settings_file 报，这里不重复
        vals: list[str] = []
        grants = GRANT_LEAVES.get(rel)
        if grants is None:
            # 这一家没有「哪个键是预批」的取证结论 → 保持原样：整份递归收，
            # 任何字符串都当条目比出处。想蒙过去得同时改 schema。
            _walk_strings(data, vals)
        else:
            for top, node in data.items():
                if isinstance(node, dict):
                    for leaf, value in node.items():
                        if leaf in grants and isinstance(value, list):
                            vals.extend(x for x in value if isinstance(x, str))
        out[rel] = vals
    return out


# Personal-data ignore rules that must never disappear from .gitignore.
REQUIRED_IGNORE_RULES = [
    # Whole-directory rule (matches .gitignore:23 exactly): must stay the bare
    # `profile/` form, not a glob like `profile*` or `profile.*`, or it would
    # also swallow (or fail to distinguish from) the unrelated
    # `profile.example/` setup-scaffolding directory.
    "profile/",
    "salary_data.json",
    # Depth-independent: the job-scrape skill resolves `job_scraper/` relative
    # to its own directory, so the state file lands under .claude/skills/... and
    # a repo-rooted rule silently fails to match it.
    "**/job_scraper/seen_jobs.json",
    "documents/cv/**",
    "documents/linkedin/**",
    "documents/diplomas/**",
    "documents/references/**",
    "documents/applications/**",
    "documents/interview/**",
    "job_search_tracker.csv",
    "resume/main.typ",
    "resume/*.pdf",
    "cover_letter/main.typ",
    # Compiled cover letters embed the target company name and candidate
    # details - as sensitive as resume/*.pdf, which is already required.
    "cover_letter/*.pdf",
    # The optional resume photo is personal data too.
    "resume/photo.*",
    # Claude Code 会把 settings.local.json 合并到 settings.json 之上，因此它同样能
    # 预授权命令。它此前既不在 .gitignore 里也不被任何守卫读取，`git add -A` 会直接
    # 把它连同本机授予的权限一起提交，在每个 pull 的 fork 上无提示生效。
    ".claude/settings.local.json",
    # /job-notion-sync 的状态含 Notion 数据库与页面 id（对应到每一次投递），/job-scrape 的
    # 抓取清单同样是个人数据。二者按 skill 目录解析，落在 users/ 之外，所以必须
    # 由这两条深度无关的规则单独兜住。
    "**/job_scraper/notion_sync.json",
    "**/job_scraper/*.md",
    # JD 原文快照：抓取下来的岗位原文，与 documents/ 下其它子目录同属个人数据
    "documents/postings/**",
    # 多用户：每用户数据根与活动用户指针（个人数据，绝不提交）
    "users/",
    ".active_user",
    # 根级激活文件兜底：.active_user 缺失/迁移未完成时，激活文件可能误落到
    # 仓库根而非 users/<用户>/templates/ 下
    "templates/active-*.md",
    # 命令产出的个人数据：/job-gmail-sync 的状态（邮件 message id + 主题）、
    # /job-html-report 的仪表盘、/job-upskill 的学习计划。生成物同样含个人信息。
    "gmail_sync/",
    "reports/",
    # 整目录，与 gmail_sync/ / reports/ 一致。**别改回扩展名通配**：
    # `upskill/*.md` 只挡 md，而这个目录归 /job-upskill 写，它哪天缓存一份
    # 语料就是一个 .json 静默进版本库。同一类脆处在 web/public/ 上栽过一次。
    "upskill/",
    # 面板的导出快照与构建产物。**这两条 2026-08-20 补**——它们一直在 .gitignore
    # 里，却从没进过这份必需清单：删掉那两行不会有任何守卫报警，而
    # `web/public/data.json` 是全仓个人数据密度最高的**单个文件**——一份里同时有
    # 全部职位与评分、投递记录、三渠道话术全文（含网申自评这种上千字的段落）、
    # 薪资期望，外加 `pdf/` 下的真实简历 PDF。实测这两个目录里 37 个文件。
    # 它比这份清单里任何一条都更该被守住，却恰恰是唯一没被守住的。
    "web/public/",
    "web/dist/",
    # 维护者的本机笔记：发布前清单（点名了哪些标识符要清）、历史 bundle。
    # 按设计就是「不该被别人看到、但本机需要」的那一类。
    ".private/",
]

# Negation (re-include) rules the template legitimately ships. .gitignore is
# order-sensitive: a later `!pattern` re-includes a path an earlier rule
# excluded, so a rule can be physically present in REQUIRED_IGNORE_RULES yet
# no longer ignored (e.g. adding `!salary_data.json`). Set membership on the
# required rules cannot see that. Any negation outside this allowlist is a
# failure - add an intentional one here in the same PR, exactly as with the
# permission entries (which now have to trace back to the generator's manifest),
# so the widening is explicit and reviewable.
ALLOWED_IGNORE_NEGATIONS = {
    "!documents/**/.gitkeep",
}

FORBIDDEN_SCRIPTS = {"preinstall", "install", "postinstall", "prepare", "prepack"}


# settings 文件里**经过审阅**的键面在上面的 `SETTINGS_KEY_SCHEMAS`（每个文件一份）。
# 只看 permissions.allow 等于没看：`hooks` 能在每次会话启动时跑任意命令，
# `permissions.defaultMode: bypassPermissions` 直接关掉所有确认，
# `permissions.additionalDirectories` 把可写范围扩到仓库外——这些都不经过 allow 列表。
# 出现清单外的键就报错，要求在同一个 PR 里显式加进来，与条目出处检查同一套路。
#
# （原来这里还有两个模块级常量 `ALLOWED_SETTINGS_KEYS` / `ALLOWED_PERMISSION_KEYS`，
# 是各家共用一份键面白名单 —— 四家之后它们表达的是 Claude 一家的形状，
# 已并入 `SETTINGS_KEY_SCHEMAS`，不再留第二份判据。）

# Claude Code 会把 settings.local.json 合并到 settings.json 之上，所以它同样能预授权命令。
# 它的**内容**是每台机器本地授予的，不该拿仓库的允许清单去卡（那会让每个开发者授予一次
# 本地权限就红）。真正的风险只有一个：它被提交进版本库，于是本机授权推给每个 pull 的
# fork。所以判据是「有没有被 git 跟踪」，而不是里面写了什么。
LOCAL_SETTINGS = ".claude/settings.local.json"


def _is_tracked(rel: str) -> bool:
    """该路径是否已被 git 跟踪。无法判定（无 git / 非仓库）时返回 False。"""
    try:
        res = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", rel],
            cwd=str(ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
    except (OSError, ValueError):
        return False
    return res.returncode == 0


def _check_settings_file(rel: str) -> None:
    """一个权限文件：先查它**自己那家**的键面，再查每一条条目有没有出处。

    两件事缺一不可。原来只查第一件，而且只查 `.claude/settings.json` 一个文件，
    于是另一家在无人看的地方写着「`run_shell_command`（不带括号）= 所有 shell
    命令免确认」这种条目也没谁说。而现在只查键面同样不够：
    **合法的键 + 手加的宽值**（`Bash(python tools/:*)` 把整个 `tools/` 授权出去）
    照样过 —— CONTRIBUTING.md「限定到入口，不开宽授权」那条规则当时**任何地方都没执行**。
    """
    schema = SETTINGS_KEY_SCHEMAS[rel]
    path = ROOT / rel
    if not path.is_file():
        if schema["required"]:
            errors.append(f"{rel}: missing")
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{rel}: unreadable or invalid JSON: {exc}")
        return
    if not isinstance(data, dict):
        errors.append(f"{rel}: top-level JSON value must be an object")
        return

    for key in sorted(set(data) - schema["top"]):
        errors.append(
            f"{rel}: unreviewed settings key {key!r}. Keys outside "
            f"{sorted(schema['top'])} can grant execution without going through "
            "the allow list (e.g. 'hooks' runs commands on every session start). If it is "
            "intentional, add it to SETTINGS_KEY_SCHEMAS in tools/security_guards.py in the "
            "same PR so the widening is explicit and reviewable."
        )
    for top in sorted(schema["top"] & set(data)):
        node = data[top]
        if not isinstance(node, dict):
            errors.append(f"{rel}: {top} must be an object")
            continue
        for key in sorted(set(node) - schema["leaf"]
                          - set(schema.get("scalars") or {})):
            errors.append(
                f"{rel}: unreviewed permissions key {key!r} under {top!r}. 'defaultMode' "
                "can disable prompting entirely and 'additionalDirectories' widens the "
                "writable area beyond the repo. Add it to SETTINGS_KEY_SCHEMAS "
                "in tools/security_guards.py in the same PR."
            )
        for leaf in sorted(schema["leaf"] & set(node)):
            value = node[leaf]
            if not isinstance(value, list) or not all(isinstance(e, str) for e in value):
                errors.append(f"{rel}: {top}.{leaf} must be a list of strings")
        for key, allowed_values in sorted((schema.get("scalars") or {}).items()):
            if key not in node:
                continue
            value = node[key]
            if value not in allowed_values:
                errors.append(
                    f"{rel}: {top}.{key}={value!r} 不在本仓库认可的取值里 "
                    f"{sorted(allowed_values)}。`bypassPermissions` 故意不在——"
                    "它把「逐个入口预批」变成「全不询问」，要那一档请连这里的取值面"
                    "一起改，别只改生成物。")

    # 第二条判据：每一条都要有出处。`permission_entries()` 整份递归收，
    # 所以「藏在别的键下的一个字符串数组」也会被当作条目对着清单比 —— 想蒙过去
    # 得同时改 schema，那就是同一次 PR 里的一次显式加宽。
    entries = permission_entries().get(rel, [])
    if not entries:
        return
    try:
        allowed = derivable_entries()
    except ManifestUnavailable as exc:
        errors.append(f"{rel}: {exc}")
        return
    for entry in entries:
        if normalize_entry(entry) not in allowed:
            errors.append(
                f"{rel}: permission not in the reviewed allowlist - the generator's "
                f"manifest cannot derive it: {entry!r}. Pre-approved permissions run "
                "without prompting on every fork, and entries must be repo-owned "
                "deterministic prefixes, never widened "
                "(the rule lives in CONTRIBUTING.md 里「限定到入口，不开宽授权」). "
                "If this entry is intentional, make tools/gen_entries.py derive it "
                "(SETTINGS_ALLOW, a workflow ```bash fence, or MANIFEST extra_tools "
                "with a reason) in the same PR, so the widening is explicit and "
                "reviewable."
            )


def check_permissions() -> None:
    for rel in PERMISSION_FILES:
        _check_settings_file(rel)
    if _is_tracked(LOCAL_SETTINGS):
        errors.append(
            f"{LOCAL_SETTINGS} is tracked by git. Claude Code merges it over settings.json, so "
            "committing it pre-approves this machine's local grants on every fork that pulls. "
            "Run: git rm --cached .claude/settings.local.json  (it is in .gitignore already)."
        )


def check_gitignore() -> None:
    path = ROOT / ".gitignore"
    try:
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    except OSError as exc:
        errors.append(f".gitignore: unreadable: {exc}")
        return
    rules = set(lines)
    for rule in REQUIRED_IGNORE_RULES:
        if rule not in rules:
            errors.append(
                f".gitignore: required personal-data rule missing: {rule!r}. "
                "These rules keep fork users from committing personal data. If the rule moved "
                "or was renamed intentionally, update REQUIRED_IGNORE_RULES in "
                "tools/security_guards.py in the same PR."
            )
    for line in lines:
        if line.startswith("!") and line not in ALLOWED_IGNORE_NEGATIONS:
            errors.append(
                f".gitignore: negation rule not in the reviewed allowlist: {line!r}. "
                "A negation re-includes a path an earlier rule excluded and can silently "
                "re-expose personal data (a required ignore rule stays present but stops "
                "taking effect). If this negation is intentional, add it to "
                "ALLOWED_IGNORE_NEGATIONS in tools/security_guards.py in the same PR."
            )


def check_package_manifests() -> None:
    manifests = [
        p for p in ROOT.glob(".agents/**/package.json") if "node_modules" not in p.parts
    ]
    if not manifests:
        # A fork with zero portal skills installed (before the first
        # /job-add-portal, or between removing all portals and adding a
        # replacement) legitimately has no .agents/**/package.json yet, and
        # git does not track empty directories - .agents/skills/ can vanish
        # from disk entirely in that state. That is not the same failure as
        # the glob root being renamed/moved (which ROOT resolving from this
        # script's own path under tools/ already rules out), so only note it.
        print("note: .agents: no package.json files found (no portal skills installed yet)")
    for manifest in manifests:
        relpath = manifest.relative_to(ROOT)
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{relpath}: unreadable or invalid JSON: {exc}")
            continue
        if not isinstance(data, dict):
            errors.append(f"{relpath}: top-level JSON value must be an object")
            continue
        scripts = data.get("scripts", {})
        if not isinstance(scripts, dict):
            errors.append(f"{relpath}: scripts must be an object")
            continue
        bad = FORBIDDEN_SCRIPTS & set(scripts)
        if bad:
            errors.append(
                f"{relpath}: lifecycle script(s) {sorted(bad)} are forbidden - they execute "
                "arbitrary code during `bun install` on every fork user's machine."
            )
        if "trustedDependencies" in data:
            errors.append(
                f"{relpath}: trustedDependencies is forbidden - it re-enables dependency "
                "lifecycle scripts that bun blocks by default."
            )


def main() -> int:
    # argparse 是标准库。**模块级不 import 本仓库的模块**（比如共享的命令行 helper）：
    # 从任何地方单独跑这份文件时，跨文件 import 会让它当场 ImportError，
    # 而它该给的是一条清楚的失败信息 —— 需要兄弟模块的那两处（清单比对）都在函数里
    # 惰性取，取不到报 ManifestUnavailable。
    import argparse
    argparse.ArgumentParser(description="检查权限文件的条目出处、gitignore 与依赖清单").parse_args()
    check_permissions()
    check_gitignore()
    check_package_manifests()
    if errors:
        print(f"security_guards: {len(errors)} failure(s)")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("security_guards: OK (permission files trace back to the entry manifest, "
          "gitignore rules, package manifests)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
