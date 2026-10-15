# -*- coding: utf-8 -*-
"""命令入口的派生器：两族技能壳与权限片段都从这里出。

**正本只有两个。** 一个是 `workflows/INDEX.md` 的索引表（说明、举例、裸命令行为，
面板帮助也读它）；另一个是本文件的 `MANIFEST`（索引表补不上的那一半：触发词、
额外权限）。壳正文一律指向 `workflows/`，一个字都不复述。

为什么必须**两族**（`.claude/skills/` 与 `.agents/skills/`）：2026-09-29/30 逐家取证，
Claude Code 2.1.282（那两天装着的那一版）的运行时技能根只有 `.claude/skills`（项目）与
`~/.claude/skills`（用户）；
`.agents/skills` 在它的二进制里只是 `claude import` 的**搬运源**，不是发现根。
而 agy / Codex / Qoder / Qwen Code / MiMo Code 读的都是 `.agents/skills`
（Gemini CLI 原来在这一串里，那家已停，整条删掉）。
所以一处生成、两处落地：
两族共用 `render_shell()` 这**一个**函数，字节必然相同 —— 盘上逐字节对照的那条
（`tests/test_shell_families_are_byte_identical.py`）跟着壳文件一起落地，见计划里的 Task 5。

零第三方依赖：frontmatter 手写，不用 pyyaml —— 与本目录其余脚本同源。

## 权限从哪来，缺了怎么办

`allowed_tools()` = `BASE_TOOLS` + 工作流 ```bash 围栏里**真跑的命令**派生出的 Bash 规则
+ 渠道 CLI 前缀（正文提到渠道时）+ `MANIFEST[name]["extra_tools"]`。

派生**宁缺勿宽**：映射不出规则的命令就留成缺口，由覆盖测试
（`tests/test_skill_permissions_cover_its_workflow.py`）把它报成「工作流要跑 X，
壳里没这条」，然后二选一 —— 把那条写成围栏里的一步，或在 `extra_tools` 里显式批并写理由。
**不靠放宽规则来让测试变绿**（`Bash(python:*)` 那种一条等于没有闸门）。

`derives_nothing()` 与 `_rule_for()` 是同一份判定的两面：映射得出规则就叫「可派生」，
否则就是刻意不派生。自证测试（`tests/test_entries_derivation.py`）用它来跳过，
所以「哪些不派生」全仓只有这一份。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: 生成物标记。写在 frontmatter **之后**的正文首行 —— 写在前面的 HTML 注释会让
#: 技能解析器读不到 `---` 开头的 frontmatter。
GENERATED_HEADER = ("<!-- 由 tools/gen_entries.py 生成："
                    "改 workflows/INDEX.md 或 tools/_entries.py，别改这里 -->")

SHELL_FAMILIES = (".claude", ".agents")

#: 手写、不生成的壳。`job-application-assistant` 没有对应的工作流文件，
#: 它是「聊到求职就自动接管」的路由壳，正文是三十几行的边界说明，不是壳套正文。
HANDWRITTEN_NAMES = frozenset({"job-application-assistant"})

#: 路由壳的宽词。命令壳的触发词不许与它重合（见 tests/test_entries_derivation.py），
#: 也不许只比它多一个虚词（见 tests/test_every_shell_can_be_triggered.py）。
#:
#: ⚠️ **这一段是手抄，抄的是 `.claude/skills/job-application-assistant/SKILL.md`
#: 里那行「触发词：…」**，而它已经飘过一次（壳里有「这个岗能投吗」，常量没有）。
#: 飘的后果不是报错，是**守卫静默缩小**：路由壳把词加宽、常量没跟上，撞词检查就
#: 少盯一个词 —— 而它要防的那次撞车正好变成看不见的。所以 `router_shell_words()`
#: 回读盘上那份壳，两者由 `tests/test_every_shell_can_be_triggered.py` 逐词钉住（双向）。
#:
#: 为什么留着手抄、不在 import 时直接派生：`_entries` 被 `gen_entries.py` import，
#: 而生成器要在**只含 `tools/` 与 `workflows/INDEX.md` 的临时树**里跑
#: （`tests/test_generated_entries_are_current.py::test_the_check_flag_exits_nonzero_on_drift`），
#: import 时读壳会把那次运行撞死，把那条对照用例打成假对照。方向仍然是**常量跟着壳**：
#: 运行时读的是壳的 frontmatter，常量只是快照，快照对不对由测试说了算。
ROUTER_GENERIC_WORDS = frozenset({
    "求职", "投递", "简历", "求职信", "面试", "岗位匹配", "职业规划",
    "这个岗能投吗",
    "job posting", "CV", "cover letter", "interview prep", "apply",
})

#: 每个壳都有的读/搜/问能力。Bash 与渠道前缀按工作流正文里真出现的命令派生。
BASE_TOOLS = ("Read", "Glob", "Grep", "WebFetch", "WebSearch",
              "Edit", "Write", "AskUserQuestion", "Agent")

#: 渠道 CLI 的前缀，**按渠道逐条列具体路径**，不用通配。
#:
#: 通配那两条曾经是静默不生效的（2026-09-29 终审实测，见下面第二段）：判据
#: 「哪些目录算渠道」仍然是「有没有 `.agents/skills/<渠道>/cli/src/cli.ts`」
#: （`docs/tool-entries.md`「工具特化」⚠️ 那段，`/job-add-portal --list` 同源），
#: 但那是**发现**渠道的判据，不是**授权**渠道的写法 —— 两件事原来共用一个字面量，
#: 于是发现判据的形状被抄进了权限文件。
#:
#: 实测（Claude Code 2.1.278，真 `-p` 无头会话，仓库已授信，命令不碰网络）：
#:   * `node .agents/skills/*/cli/src/cli.ts --help`（字面量与规则**逐字相等**）
#:     → 直接放行，跑了
#:   * `node .agents/skills/liepin-search/cli/src/cli.ts --help`（真实调用）
#:     → 「This command requires approval」，没跑
#:   * `pdftotext -layout -enc UTF-8 …`（无通配的 `Bash(pdftotext:*)`）→ 放行
#: 三条一起读：前缀匹配是按字面比的，**中间的 `*` 是星号本身**，不是通配段 ——
#: 与 Codex 那侧 `codex execpolicy check` 测到的完全同形（`_concrete_prefixes`
#: 的注释记着那次）。所以通配那两条盖不住任何一次真实调用，读起来像预批、
#: 实际是空转：每次搜岗仍要人手点一次授权。
#:
#: 新接一个渠道 = 在这里补一条具体前缀。漏补会红，不会静默：
#: `tests/test_the_generator_and_the_guard_agree.py::test_portal_wildcard_is_expanded_not_copied`
#: 拿盘上的 `*/cli/src/cli.ts` 跟片段比，盘上有而清单没有 → 红。
PORTAL_BASH = (
    "Bash(node .agents/skills/liepin-search/cli/src/cli.ts:*)",
    "Bash(bun run .agents/skills/liepin-search/cli/src/cli.ts:*)",
)

#: 跨壳共用的授权：**凡某个壳里已经批过的 Bash 条目，壳外也该批**。
#:
#: 为什么要有这一份。各壳的 `allowed-tools` 只在「以 Skill 方式调用那个壳」时生效，
#: 于是同一个动作换个入口就要重新点一次授权：AGENTS.md 要求会话开始先跑的
#: `python tools/doctor.py`、数据变了重导面板的 `export_web_data.py`、
#: `/job-dashboard` 让 AI 自己起的 `serve.py`，都不发生在任何壳里——
#: 2026-09-30 用户报「每步都要授权」，主因就是这个入口差。
#:
#: 上一版这里手抄了三条命令名。那是个止疼片：它只治「我此刻发现的三个」，
#: 而真正的规则是「壳内已批 = 仓库认定这个动作安全」，壳外没理由重新怀疑一遍。
#: 现在改成从 `allowed_tools()` 取并集，正本仍然只有一份（每个壳的工作流围栏
#: + `extra_tools`），这里不新增任何条目、也不删任何一条。
#:
#: 天花板由派生那头守着，不在这里：`_rule_for` 拒收 `python -c`（那授权的是任意
#: 内联代码）、含 `<占位符>` 的路径、以及不从仓库根算起的脚本；
#: `test_no_entry_opens_a_whole_directory` 拦 `tools/:*` 与 `Skill(*)`。
#: 所以这份表再长，也只会长到「22 个仓库自己的入口脚本」这一级。


RUNNERS = ("python", "python3", "node", "bun", "npm", "npx",
           "typst", "pdftotext", "pdftoppm")

_FENCE = re.compile(r"```(?:bash|sh|shell|console)\n(.*?)```", re.S)


def fence_blocks(text: str) -> list:
    """全文所有围栏 `(外层标签, 正文)`，按**外层**配对 —— 与
    `tests/test_workflow_prose_is_chinese.py::_walk` 同一套约定：
    只有裸 ``` 闭合外层，带 info string 的行算嵌套开头（不改外层标签）。

    `commands_in()` 只读 `_FENCE` 认的那几种标签（bash / sh / shell / console）；
    这里收**全部**，因为守卫要问的恰恰是派生没读到的那半边：标签不在这四个里的
    围栏对 `commands_in` 是盲区，而正文提取（`_inline_commands`）先把围栏整段
    剥掉——**未贴标签的围栏两头都看不见**。实测代价（2026-09-29，Task 3 评审）：
    `job-auto.md` 收尾段的 writeback / archive / export_web_data / check_outreach
    藏在裸 ``` 围栏里，生成的壳一条都没批，招牌命令每一步都要人手点授权。
    守卫在 `tests/test_skill_permissions_cover_its_workflow.py`
    （`test_no_unlabelled_fence_hides_a_runner_command`），判命令用同一个
    `_one_command`，不另抄围栏正则。
    """
    out = []
    depth, tag, body = 0, None, []
    for ln in text.splitlines():
        st = ln.strip()
        if st.startswith("```"):
            info = st.lstrip("`").strip()
            if depth == 0:
                depth, tag, body = 1, info, []
            elif info == "":
                out.append((tag, "\n".join(body)))
                depth, tag = 0, None
            continue
        if depth:
            body.append(ln)
    if depth:                             # 未闭合的外层围栏：正文算到文件末尾
        out.append((tag, "\n".join(body)))
    return out


#: 触发词。来源分三类（spec §5.4）：
#:   - 索引表第三列「…」里已有的自然语言说法，直接取（7 条）
#:   - 今天已有壳里写好的（job-scrape / job-upskill）
#:   - 其余 13 条按「动词 + 宾语，用户此刻想干的那件事」新写
#: 每条都带一个英文兜底词。**触发词不许就是 `ROUTER_GENERIC_WORDS` 里那个宽词，
#: 也不许是「那个宽词 + 一个虚词」**（2026-09-29 Task 6 裁的是这两条）：
#: 路由壳是「聊到求职就接管」，一条同样宽的说法等于两个壳同时够格，谁接管看运气。
#: ⚠️ 这里**不是**「不许出现宽词」—— 盘上 12 条现役触发词合法地**包含**某个路由词
#: （「刷一下简历」含「简历」），那是裁定允许的形状；原来这句写的「不许用」
#: 与判据不符，而这是改 MANIFEST 的人第一个读到的文件（下面第二条写着怎么判）。
#:
#: 三条长度上限 + 一条撞词判据，都由 `tests/test_every_shell_can_be_triggered.py`
#: 盯着，判据与变异证据写在那里：
#:   - **长度按各自文字怎么数**（2026-09-29 评审：原来只有 14 **字符**一条，
#:     而它对中文是瞎的 —— 中文没有空格分词，一个汉字就是一个词）：
#:     汉字 ≤9、英文 ≤3 词、总字符 ≤14。前两条是补的洞，第三条一个字没动，
#:     它是 Task 6 Step 2 定的那个数（当时实测三条超了并缩短 ——
#:     `apply to this job`(17)、`application report`(18)、`interview prep for`(18)。
#:     **别放宽上限去迁就写法**，是把那几条改短）。总字符那条管中英混排与
#:     单个超长单词，那两种形状前两条各只数得到自己那半边。
#:   - **包含某个路由词的触发词，去掉那个词之后还得留下一个真动作**：只多一个虚词
#:     （`interview prep` + ` for`）等于没写，两条壳在模型眼里一样宽。上面那三条里
#:     的 `interview prep for` 正是同时栽在「长度」与「外套」这两条上 ——
#:     判据的来由与实测记录写在该测试文件的模块 docstring。
MANIFEST: dict[str, dict] = {
    "job-setup": {
        "triggers": ("我要开始用", "第一次用", "建档", "填我的资料", "初始设置", "job setup"),
    },
    "job-scrape": {
        "triggers": ("找职位", "找新岗", "抓职位", "有没有新岗位", "搜岗",
                     "find jobs", "job scrape", "/job-scrape"),
        # 三条派生不出来的权限，逐条给理由（宁缺勿宽：显式批一条，而不是放开规则）。
        #
        # 1) doctor.py —— `AGENTS.md`「会话开始：先跑自检」要求**任何**命令在第一次
        #    实质回复前跑一次 `python tools/doctor.py`。那是仓库级的一步，不写在任何
        #    一份工作流的围栏里，围栏派生永远看不见它；而今天的壳有这条，删掉就是
        #    倒退（job-scrape.md 里出现的 `doctor` 只有 `doctor.profile_gaps(…)`
        #    那个函数名，不是命令）。
        # 2) export_web_data.py —— `workflows/job-scrape.md` 的 `--no-rank` 分支要
        #    「自己收尾：跑一次 python tools/export_web_data.py 刷新面板」。它是运行时
        #    步骤，但写在**正文**不是围栏。派生只认围栏，原因是同一份正文里还有一句
        #    「下次改这一步之前，先跑 python tools/audit_pipeline.py」——那是给改流程的
        #    人看的，按正文派生就等于替一条永不执行的命令开权限（同一条判据见
        #    `commands_in` 的 docstring，`tests/test_skill_permissions_cover_its_workflow.py`
        #    的 INLINE_EXEMPT 也按这个区分）。
        # 3) bun --version —— 同一段的降级路径（「node 不可用 → 试 bun」）也在正文。
        #    与围栏里那条 `node --version` 同样是纯探测，精确形式，不比它宽。
        "extra_tools": (
            "Bash(python tools/doctor.py:*)",
            "Bash(python tools/export_web_data.py:*)",
            "Bash(bun --version)",
        ),
    },
    "job-rank": {
        "triggers": ("给这些岗打分", "排个序", "哪个岗值得投", "评一评", "job rank"),
        # 「**写回之后跑 `python tools/export_web_data.py` 刷新面板数据**——分数落了
        # 库而面板还是旧的」（job-rank.md 写回之后那一步）。同样是写在正文里的收尾步骤。
        "extra_tools": ("Bash(python tools/export_web_data.py:*)",),
    },
    "job-auto": {
        "triggers": ("自动跑一轮", "一条龙跑完", "全都跑了", "job auto"),
        # /job-auto 把 scrape→rank→apply 接成循环，因此**子流程之外**还有几条
        # 它自己那一步要跑的命令，写在正文而不是围栏里（围栏派生看不见它们）。
        # 逐条给理由，与 job-scrape 那一份同判据：
        # 1) query_yield.py —— 「补货完**必须跑** `python tools/query_yield.py --apply`」
        #    （job-auto.md「补货」那段与「每轮补货后都要把词表写回」那条）。不跑就是下一轮拿同一批挖空的词再抓，
        #    自动循环把这个浪费放大成十几轮 —— 这条是硬步骤，不是给维护者看的。
        # 2) portal_budget.py —— 撞限流/风控时「跑 `python tools/portal_budget.py
        #    --block <渠道> --why "…"`」（job-auto.md 那张故障分流表），以及跳出循环前
        #    「**重查一次闸门**」（同一文件跳出循环前那一步）。额度闸门是账号安全的唯一防线，
        #    漏了它的后果有实测（2026-08-19 用户的猎聘账号被标异常）。
        # 3) jd_store.py —— 「想先看看某个岗当初漏掉的是什么，
        #    `python tools/jd_store.py --show <职位链接>` 把库里那份 JD 正文印出来」
        #    （job-auto.md「单独看一个仍然可以」那段）：重判一个岗而不重开页面的那条路，运行时真会敲。
        # （原来还有第 4 条 audit_pipeline.py —— 评审抓到「裸围栏两头盲」
        #  之后，循环那段围栏贴上了 bash，它的 --sections / --actionable /
        #  --rewrite-list 三步现在由围栏直接派生，显式批就是重复授权，删。）
        "extra_tools": (
            "Bash(python tools/query_yield.py:*)",
            "Bash(python tools/portal_budget.py:*)",
            "Bash(python tools/jd_store.py:*)",
        ),
    },
    "job-apply": {
        "triggers": ("投这个岗", "深评一下", "写个打招呼", "开场白怎么说", "write opener"),
        # 英文兜底词 2026-09-29 换过两次，第二次是评审：`score this job` 单位无关地弱 ——
        # 它只说「打分」那一半（这条命令干的是**评 + 写开场白**，见 workflows/job-apply.md），
        # 而「打分」恰好是 job-rank「给这些岗打分」的英文近邻，两句撞在同一件事上。
        # `write opener` 说的是只有这条命令才产出的那件东西（打招呼开场白），
        # 与 job-rank 没有一个词重合。原来那条 `apply to this job` **跟长度无关就不合法**：
        # 去掉路由词 `apply` 只剩 `to this`，全是虚词（判据见下面第二条上限）。
        # 中文那四条已经把两半都说了，英文这条只负责按 description 语义匹配的那几家
        # （agy 那一类）里的稳妥命中。
    },
    "job-cv": {
        "triggers": ("给这个岗定制简历", "改一版简历投它", "custom cv"),
        # 收尾「跑 `python tools/export_web_data.py` 刷新面板——简历 PDF 会出现在
        # 该岗卡片里；**没刷新等于做了没做**」（job-cv.md「收尾」那一节）。运行时步骤写在正文，
        # 围栏派生够不着，判据与 job-scrape 那条 export_web_data 完全一样。
        "extra_tools": ("Bash(python tools/export_web_data.py:*)",),
    },
    "job-resume": {
        "triggers": ("看看我简历", "审一遍简历", "简历有什么问题", "resume review"),
    },
    "job-refresh": {
        "triggers": ("刷一下简历", "刷新在线简历", "让 HR 搜到我", "refresh resume"),
    },
    "job-outcome": {
        "triggers": ("记一笔", "约面了", "挂了", "没下文", "log outcome"),
        # 「记录写完就跑 `python tools/export_web_data.py` 刷新面板——台账改了而
        # 面板还停在上一版」（job-outcome.md 写回记录那一步之后）。`AGENTS.md`「命令怎么自动衔接」
        # 把「写回后刷新面板」列为自动接缝，所以这条是运行时的，不是说明。
        "extra_tools": ("Bash(python tools/export_web_data.py:*)",),
    },
    "job-offer": {
        "triggers": ("拿到offer了", "谈薪", "两个offer怎么选", "背调", "offer"),
    },
    "job-interview": {
        "triggers": ("准备面试", "这家会问什么", "模拟面试", "mock interview"),
    },
    "job-expand": {
        "triggers": ("挖我的经历", "还有什么没写进资料", "翻我的文档", "expand profile"),
    },
    "job-dashboard": {
        "triggers": ("打开总览页", "看面板", "打开这一页", "open dashboard"),
    },
    "job-html-report": {
        "triggers": ("投后分析", "哪类岗回复率高", "卡在哪一环", "reply rates"),
    },
    "job-gmail-sync": {
        "triggers": ("同步邮件", "查我的 Gmail", "面试邀请邮件", "拒信", "gmail sync"),
    },
    "job-notion-sync": {
        "triggers": ("推到 Notion", "同步看板", "notion sync"),
    },
    "job-upskill": {
        "triggers": ("我该学什么", "能力差距", "差在哪", "学习计划", "补短板",
                     "skill gaps", "upskill", "/job-upskill"),
    },
    "job-add-portal": {
        "triggers": ("接一个新招聘网站", "加一个渠道", "新平台怎么接", "add portal"),
    },
    "job-add-template": {
        "triggers": ("换一套模板", "换个简历模板", "加个模板", "add template"),
    },
    "job-reset": {
        "triggers": ("清空我的数据", "重新开始", "reset my data"),
    },
    "job-user": {
        "triggers": ("现在是谁在用", "切换用户", "新建一个用户", "switch user"),
        # 切完人要「**然后跑 `python tools/export_web_data.py`**，再回复」（job-user.md 切完人要回复用户那一段）。
        # 这条不跑不是「面板旧了」那么轻：盘上那份 `data.json` 还是**上一个人**的，
        # 而它比新活动用户的上游文件更新，`serve.py` 据此判定「不过期」直接端出去
        # ——面板标着 bob、装着 alice。`AGENTS.md` 把「切换用户后重导数据」列为
        # 自动接缝，正是这一条。
        "extra_tools": ("Bash(python tools/export_web_data.py:*)",),
    },
    "job-application-assistant": {
        "handwritten": True,
        "triggers": (),
    },
}


def read_index() -> dict[str, dict]:
    """`workflows/INDEX.md` 的扁平视图：`{name: item}`。

    复用 `build_dashboard.parse_commands()` —— 面板帮助与命令入口读**同一份**解析，
    两处就不可能各自长出对方没有的一条。
    """
    from build_dashboard import parse_commands

    return {it["name"]: it for g in parse_commands() for it in g["items"]}


def generated_names() -> list[str]:
    return sorted(n for n in read_index() if n not in HANDWRITTEN_NAMES)


def shell_names() -> list[str]:
    """两族各应有哪些壳：生成器落的那一批 + 手写的路由壳。

    不写「21 + 1」这种数字：加一条命令这里就多一个，而数字没人钉着。
    条数的正本在 `workflows/INDEX.md` 那张表，手写的那份见 `HANDWRITTEN_NAMES`。
    """
    return sorted(set(generated_names()) | HANDWRITTEN_NAMES)


#: 权限条目的**语法包装**：Claude 写 `Bash(python tools/doctor.py:*)`，
#: Gemini 写 `run_shell_command(python tools/doctor.py)`。判据问的是
#: 「授权了哪条命令」，不是「哪一家怎么括起来」，所以比对前先剥壳。
#: 住在派生器里而不是守卫与生成器各写一条正则：`gen_entries.py` 的按工具片段
#: （`--print codex` / `--print agy`）与 `security_guards.py` 的出处比对用的是
#: **同一个**「核心串」，两处判据一旦分叉，守卫就会把自家合法写法读成没出处。
_RUNNER_WRAP = re.compile(r"^(?:Bash|run_shell_command)\((.*)\)$")


def normalize_entry(entry: str) -> str:
    """一条权限条目 → 去掉各家包装后的核心串（两端空白也去掉）。

    `Skill(...)` 不剥：那是 Claude 独有的技能授权形状，剥成光一个技能名就与
    「某个字符串出现在某个列表里」无异了，而守卫要盯的正是它的**完整形状**
    （`Skill(*)` 这种通配必须看得见）。
    """
    m = _RUNNER_WRAP.match(entry.strip())
    return m.group(1) if m else entry.strip()


def _one_command(line: str) -> str:
    """一行围栏文本 → 「解释器 + 第一个参数」；不是要跑的命令就返回空串。"""
    line = line.strip().lstrip("$ ").strip()
    line = line.split("#")[0].strip()          # 行尾注释不算命令的一部分
    parts = line.split()
    if len(parts) >= 2 and parts[0] in RUNNERS:
        return f"{parts[0]} {parts[1]}"
    if len(parts) == 1 and parts[0] in RUNNERS:
        return parts[0]
    return ""


def _fence_commands(workflow_text: str) -> list:
    """```bash 块里的命令，**按文中顺序**去重。派生规则用它：
    壳里 `allowed-tools` 的先后跟着工作流走，读得下去，也保持确定性。
    """
    out: list = []
    for block in _FENCE.findall(workflow_text):
        for line in block.splitlines():
            cmd = _one_command(line)
            if cmd and cmd not in out:
                out.append(cmd)
    return out


def commands_in(workflow_text: str) -> set:
    """工作流的 ```bash 块里，每条命令的「解释器 + 第一个参数」。

    **只认代码块**：正文里「Claude Code 本身走 `npm install -g` 安装」是在说别人的
    安装方式，把它算进来就是替一条永远不执行的命令申请权限。

    **只比到「解释器 + 第一个参数」这一层**（`python tools/gap_split.py`）。再细就
    等于把每个参数组合都钉死，工作流换个 flag 就红。

    （这两个判据原来是 `tests/test_skill_permissions_cover_its_workflow.py` 自己写的，
    2026-08-18 由它抓出两处「壳够不着工作流」的事故。搬进这里是为了同一个判据
    只有一份；那个测试改为 import 本函数。）
    """
    return set(_fence_commands(workflow_text))


def covered(cmd: str, rules: list) -> bool:
    """某条命令是否被任一规则允许。

    规则是前缀形式 `<前缀>:*`，也可能是精确形式（`node --version`）。
    两种都按「命令以规则的前缀开头」判——精确形式恰好是前缀的退化情形。
    通配的路径段（`.agents/skills/*/cli/...`）按正则比。

    ⚠️ **最后那半句比真实的 Claude Code 宽。** 2026-09-29 实测（2.1.278，真无头会话）：
    `Bash(node .agents/skills/*/cli/src/cli.ts:*)` 放行的是**字面上以那串含星号的路径
    开头**的命令，真实调用 `node .agents/skills/liepin-search/cli/src/cli.ts …` 要人工
    批准 —— 也就是说通配规则在壳上写着等于没写。所以那种规则如今**不许出现在任何
    生成物里**（`tests/test_bash_permissions_use_the_prefix_form.py::test_no_mid_pattern_wildcard`
    拦，正本 `_entries.PORTAL_BASH` 逐渠道列具体路径），这一支因此对生产判据不可达，
    留着只因为它是「前缀匹配」这句话的退化情形对照（`tests/test_skill_permissions_cover_its_workflow.py`
    里那条自证还喂它）。别把它当成「写个通配就一劳永逸」的依据。
    """
    for r in rules:
        prefix = r[:-2] if r.endswith(":*") else r
        if "*" in prefix:
            pat = "^" + ".*".join(re.escape(x) for x in prefix.split("*"))
            if re.match(pat, cmd):
                return True
        elif cmd.startswith(prefix):
            return True
    return False


#: 第三方 CLI：限定到程序名就够（`Bash(pdftotext:*)` 是 `.claude/settings.json`
#: 里已有的写法）。它们没有「入口文件」可以收窄。
PROGRAM_SCOPED = ("typst", "pdftotext", "pdftoppm", "npm", "npx")

#: 路径类参数只有在**从仓库根算起**时才是「仓库拥有的确定性前缀」。
#: `node src/cli.ts`（`job-add-portal` 让人先 `cd` 进新渠道自己的 `cli/` 再跑）不算：
#: 那个目录不在仓库里，这条前缀匹配的其实是「当前目录下碰巧叫 cli.ts 的那个文件」，
#: 而它写成 `bun run src/cli.ts:*` 还会被 `lint_skills.check_skill` 当缺文件拒掉。
#: 顶层目录新增时这里会漏派生 —— 覆盖测试把它报成缺口，而不是悄悄多发一条宽规则。
REPO_ROOTED = ("tools/", ".agents/")


def _rule_for(cmd: str):
    """一条「解释器 + 第一个参数」→ 权限规则；**刻意不派生的返回 None**。

    判据本身在 `commands_in`（取什么）与 `covered`（怎么算被允许）里，这里只做映射。

    刻意**不派生**的三类（宁缺勿宽）：
      - 解释器 + 以 `-` 开头的第一个参数（`python -c "…"`）：那授权的是任意内联代码。
        **例外一**：`--version`（`node --version` / `bun --version`）是纯探测，
        今天的壳写的就是精确形式，照抄精确形式（窄于 `Bash(node:*)`）。
        **例外二**：`PROGRAM_SCOPED` 里那些第三方 CLI 先看程序名这一层——它们的第一个
        参数**本来就只能**是 flag（`pdftotext -layout -enc UTF-8 a.pdf b.txt`），
        拿 flag 判「不派生」等于永远派生不出 `Bash(pdftotext:*)`，而那条才是
        `PROGRAM_SCOPED` 这个常量存在的理由（也是 `.claude/settings.json` 已有的写法）。
        解释器不吃这条例外：`python` / `node` / `bun` 不在 `PROGRAM_SCOPED` 里。
      - 含 `<` `>` 占位符的目标（`users/<活动用户>/…`）：路径不存在，
        `lint_skills.check_skill` 会当场拒绝。
      - 不在 `REPO_ROOTED` 里的脚本路径（`node src/cli.ts`）：见上面那张表的理由。
    """
    parts = cmd.split()
    prog = parts[0]
    arg = parts[1] if len(parts) > 1 else ""

    if not arg:
        return None                             # 光一个解释器，没有可收窄的对象
    if arg == "--version":
        return f"Bash({prog} --version)"        # 纯探测：精确形式，不比它宽
    if prog in PROGRAM_SCOPED:
        return f"Bash({prog}:*)"
    if arg.startswith("-") or "<" in arg or ">" in arg:
        return None
    if not arg.startswith(REPO_ROOTED):
        return None
    if arg.endswith(".py") and prog in ("python", "python3"):
        return f"Bash({prog} {arg}:*)"
    if arg.endswith(".ts") and prog in ("node", "bun"):
        return (f"Bash(bun run {arg}:*)" if prog == "bun"
                else f"Bash(node {arg}:*)")
    return None


#: 跨壳表里**该带**的非 Bash 工具。判据只有一条：它今天真的会弹。
#:
#:   · `WebFetch` / `WebSearch` —— 抓 posting 与搜岗的默认动作，各壳都批了，
#:     壳外（不通过 Skill 进来的普通对话）却要逐个点；
#:   · `Agent` —— AGENTS.md 能力对照表把「并行子代理 / 双角色审稿」当核心机制，
#:     批它等于让那条机制在壳外也能跑。
#:
#: **不带**的：`Edit` / `Write`（`defaultMode: acceptEdits` 已经管了，列进来是第二份
#: 授权同一个动作）；`Read` / `Glob` / `Grep`（只读检索，按我的判断 Claude 默认不问，
#: **这一条我没实测**——真测出来会弹，加进来的成本是一行）；`AskUserQuestion`
#: （它本来就是问用户，不是要授权的动作）。
ALSO_SHARED = ("WebFetch", "WebSearch", "Agent")


def shared_grants() -> tuple:
    """跨壳共用的授权：全部生成壳的 Bash 并集 + `ALSO_SHARED`。

    条目一律**从 `allowed_tools()` 取**，不在这里写第二遍：`_rule_for` 改判据时
    只有正本跟着变，这份派生品自动对齐（`PORTAL_BASH` 那条注释记过手抄的教训）。
    排序稳定，生成物逐字节可比。
    """
    out = set(ALSO_SHARED)
    for name in generated_names():
        for tool in allowed_tools(name):
            if tool.startswith("Bash("):
                out.add(tool)
    return tuple(sorted(out))


def derives_nothing(cmd: str) -> bool:
    """这条命令是不是我们**刻意不派生**的那几类之一。

    `bash_rules` 与「自证覆盖」那条测试共用这一个判定：写两份必然飘，而飘的那份
    会把缺口藏起来（测试跳过得比实现宽 = 再也不检查）。
    """
    return _rule_for(cmd) is None


def bash_rules(workflow_text: str) -> list:
    """命令对 → 规则串（按工作流里的先后，去重）。**只做映射。**"""
    rules: list = []
    for cmd in _fence_commands(workflow_text):
        rule = _rule_for(cmd)
        if rule and rule not in rules:
            rules.append(rule)
    return rules


def _uses_portal(workflow_text: str) -> bool:
    return ".agents/skills" in workflow_text or "cli/src/cli.ts" in workflow_text


def allowed_tools(name: str) -> list[str]:
    """一个壳的 `allowed-tools` 全序列：基础能力 + 正文派生的 Bash + 渠道前缀。"""
    tools = list(BASE_TOOLS)
    wf = ROOT / "workflows" / f"{name}.md"
    if not wf.is_file():
        return tools
    text = wf.read_text(encoding="utf-8", errors="replace")
    for rule in bash_rules(text):
        if rule not in tools:
            tools.append(rule)
    if _uses_portal(text):
        for rule in PORTAL_BASH:
            if rule not in tools:
                tools.append(rule)
    for extra in MANIFEST.get(name, {}).get("extra_tools", ()):
        if extra not in tools:
            tools.append(extra)
    return tools


#: 读**盘上的壳**的判据。与上面那套「往外派生权限」的判据是两件事：那边写壳，
#: 这边回读壳。住在这里而不是让每个测试各抄一条正则 —— 同一个判据写两处，
#: 改一处忘一处，而忘的那一处正是缺口藏身的地方
#: （`AGENTS.md`「一条规则只贴在一个写手身上，另外两个照样会犯」）。
#: `tests/test_skill_permissions_cover_its_workflow.py` 的 `_ALLOWED` 读的是
#: `allowed-tools` 那一行，不是 `description`，两件概念不合并。
_DESC_BLOCK = re.compile(r"^description: >(.*?)^(?=\S)", re.S | re.M)

#: 壳的 description 里那句「触发词：…」的行首。词与词之间用顿号。
_TRIG_HEAD = "触发词："


def description_block(shell_text: str) -> str:
    """一份壳的 `description` 正文（到下一个顶格键为止）。没有则空串。

    技能匹配只看 frontmatter 的 `name` + `description`，所以「触发词写进了壳的
    正文」不等于「触发词够得着」——够得着的只有这一段。
    """
    m = _DESC_BLOCK.search(shell_text)
    return m.group(1) if m else ""


def trigger_words(shell_text: str) -> tuple:
    """盘上那份壳的 `description` 里印着哪些触发词（**顺序照壳**）。

    「触发词：」那一段在壳里会**折行**（手写路由壳实测折在顿号后面：
    「…职业规划、\\n  job posting、CV…」），所以先把换行连同缩进接回去再按顿号切。
    只按换行切会把「job posting、CV」当成一个词，那个假词谁都盖不住 ——
    而 `ROUTER_GENERIC_WORDS` 与壳的那根钉也永远对不上。
    """
    desc = description_block(shell_text)
    i = desc.find(_TRIG_HEAD)
    if i < 0:
        return ()
    tail = re.sub(r"\n[ \t]*", "", desc[i + len(_TRIG_HEAD):])
    # 收尾的标点不算词的一部分：渠道壳「…、job openings。」那种写法，
    # 留着句号会让「job openings」与命令壳的同名触发词比不出相等。
    return tuple(w for w in
                 (x.strip().strip("、").strip("。；;，, ").strip()
                  for x in tail.strip().strip("、").split("、")) if w)


def router_shell_words(fam: str = SHELL_FAMILIES[0]) -> frozenset:
    """路由壳自己声明的那批宽词 —— `ROUTER_GENERIC_WORDS` 的正本。

    读的是盘上那份壳（运行时读的就是它），不是常量。取哪几个文件由
    `HANDWRITTEN_NAMES` 说（今天是唯一的一份 `job-application-assistant`）——
    取并集而不是挑一个：真多出第二份手写壳时守卫跟着变严，而不是猜该读谁。
    """
    out: set = set()
    found = False
    for name in sorted(HANDWRITTEN_NAMES):
        path = ROOT / fam / "skills" / name / "SKILL.md"
        if not path.is_file():
            continue
        found = True
        out |= set(trigger_words(path.read_text(encoding="utf-8")))
    if not found:
        raise FileNotFoundError(
            f"{fam}/skills 下一份手写壳都没有 —— 路由壳没了，撞词守卫无从判起")
    return frozenset(out)


def router_generic_words_in_force() -> frozenset:
    """撞词守卫实际该用的那批宽词：**快照 ∪ 壳自己声明的**。

    等不等由 `test_the_constant_is_the_shells_own_words` 判，但守卫不能只信快照：
    「壳加宽了而常量没跟上」这一格如果靠另一条测试来兜，就等于把一条规则贴在
    一个写手身上（`AGENTS.md`「一条规则只贴在一个写手身上，另外两个照样会犯」）。
    取并集之后，两边任何一边加宽都**立刻**让守卫变严，红不红与那条钉有没有跑到
    无关。方向也不会松：并集只可能比快照宽。
    """
    return ROUTER_GENERIC_WORDS | router_shell_words()


def render_shell(name: str) -> str:
    """完整的 `SKILL.md` 文本。**两族共用这一个函数**，所以字节必然相同。"""
    it = read_index()[name]
    trig = MANIFEST.get(name, {}).get("triggers", ())
    tools = ", ".join(allowed_tools(name))
    does = it["does"]
    bare = it.get("bare", "")
    trigger_line = f"  触发词：{'、'.join(trig)}\n" if trig else ""
    bare_line = f"裸命令的行为：{bare}。\n" if bare else ""
    return (
        "---\n"
        f"name: {name}\n"
        "description: >\n"
        f"  {does}\n"
        f"  不给参数时：{bare}\n"
        f"{trigger_line}"
        f"allowed-tools: {tools}\n"
        "---\n"
        "\n"
        f"{GENERATED_HEADER}\n"
        "\n"
        f"# {it['cmd'].lstrip('/')}（壳）\n"
        "\n"
        f"读取并严格执行 `workflows/{name}.md`。\n"
        "\n"
        "用户在这条命令后面给的内容（链接、公司名、方向词、整段职位描述）原样带进工作流。\n"
        # 索引表的第四列会把它那些路径原样抄进壳里（`job-resume` 那条就写着
        # `resume/main.typ`）。`AGENTS.md`「活动用户与多用户」要求任何命令/技能提到
        # 这类路径时写明它解析为 `users/<活动用户>/` 下的对应路径，而
        # `tests/test_multiuser_paths.py` 是照着**盘上的文件**核这条的：壳里只抄了
        # 路径、没说活动用户，多人共用一份 clone 时它就去读仓库根那份。
        "个人数据路径（`profile/…`、`documents/…`、`resume/main.typ` 这类）在这条命令里"
        "一律指活动用户目录 `users/<活动用户>/` 下的那一份，解析规则见 "
        "`AGENTS.md`「活动用户与多用户」。\n"
        f"{bare_line}"
    )
