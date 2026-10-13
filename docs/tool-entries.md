# 各 AI 工具的入口

从 `AGENTS.md`「工具特化」搬来（2026-09-29 落盘，计划定案 2026-09-28）。搬走的理由
是**闸门**：`AGENTS.md` 是每一家工具的常驻入口，agy 单文件 24,000 B 截断、Codex 累计
32 KiB 截断，两家都**静默**截断。这一节的大部分内容在生成器落地之后成了事实上的
冗余——「Claude 有 stub、其它工具读索引」正是生成物要消灭的那个差别。留下的两条
真规则在 `AGENTS.md` 里。

> **agy 还有第二道闸，2026-09-30 读它随二进制发布的那份规则文档量到**：除了单文件
> 24,000 B，全部常驻规则**共享一份 20,000 token 的总预算**（`defaultRulesBudget`），
> 超了不是截断而是**把整段降级成文件路径指针**——比截断更隐蔽，既不报错也不变空。
> 同一份文档还写着规则**按条目去重**：同一条经多条路径被发现，一次会话里只应用一次。
>
> **这道闸现在管不到我们，而「管不到」是算出来的不是感觉的**：本仓库给 agy 的常驻规则
> 只有 `AGENTS.md` 一份（它不读 `CLAUDE.md`——二进制里那个字面量 0 命中，正对照是
> `AGENTS.md` 52 次、`GEMINI.md` 46 次），而 23,500 B 那道字节闸在任何文种构成下都
> 换算不到 20,000 token（整篇汉字约 1.2 万，整篇 ASCII 约 6 千）。**所以不为它另设闸门**。
> 但**再加第二份常驻规则文件之前回来重算这条**——那时占预算的就不止一份了。

**本文件是「哪家工具怎么进来」的正本**：逐家的接入面（读哪个规则文件、扫哪个技能
目录、吃不吃斜杠、有没有探测信号）都在下面那几张表里，`AGENTS.md` 只留指针。
每一格都是**逐家取证**的，取证日期写在格子旁边；改判据之前先按文末「复核入口」
再量一次 —— 表会过期，量法不会。

## 逐家的接入面

**四列都是量出来的，不是从文档推的。** 每格后面的日期是取证日；厂商约定会变，
改判据前按文末「复核入口」再量一次。

| 工具 | 读 `AGENTS.md` | 扫 `.agents/skills/` | 吃斜杠 | 探测信号 |
|---|---|---|---|---|
| Claude Code | ✅（另有 `CLAUDE.md`） | ❌ 运行时只有 `.claude/skills/` | ✅ | `CLAUDECODE=1` |
| Antigravity CLI (agy) | ✅（`GEMINI.md` 也读，两份都加载、按条目去重；2026-09-30 读它自带的规则文档） | ✅ | ✅ | `ANTIGRAVITY_AGENT=1` |
| Qoder | ✅（另有 `AGENTS.local.md`） | ✅（legacy 开关默认开） | ✅ | `QODERCN_CLI=1` |
| Qwen Code | ✅ | ✅（0.24.7 起；0.14.0 不扫） | ✅ | `QWEN_CODE=1` |
| MiMo Code | ✅ | ✅（默认开） | ✅ | `MIMOCODE=1` |
| MCode | **未验** | ✅ | ✅ | `MAVIS_SESSION_TRANSFER_CLIENT=1`（2026-10-13 逐个量出来的） |

> **这一行的三列不是同一档的证据，别当成一样。**
> - 「扫 `.agents/skills/`」✅：2026-10-13 那次会话里，21 条 job-* 工作流确实是从
>   `.agents/skills/` 加载进来的（`lint_skills.py` 也过），所以这一列有据。
> - 「吃斜杠」✅：用户 2026-10-13 当场确认，技能注册成 `/<名>`。
> - 「探测信号」：真在会话里量了 `os.environ`，三个 `MAVIS_*` 都在，取最像会话级的那个。
> - 「读 `AGENTS.md`」**未验**：从会话内部看不见「常驻规则到底加载了哪几份」——
>   它不像 `CLAUDE.md` 那样在注入内容里留痕。**这一格原来被我填成 ✅，那是照着
>   「绝大多数家都 ✅」推的，不是量出来的**；表头写着「四列都是量出来的，不是从
>   文档推的」，所以留空比猜一个强。真要确认，从会话外看一眼它注入的规则文件清单。

> ⚠️ **这一行只写简称 `MCode`。** 那家厂商的全名是活动用户**投过**的公司之一，
> `test_no_maintainer_data_in_repo` 盯着「被跟踪的文件里不许出现投过的公司名」
> ——2026-10-13 头一次加这一档时就是被它拦下的，报的是 `M******`。
> 与别处换 `<公司>` 一样：形状一点没少，只是不把那句话留在版本库里。
> 信号 `MAVIS_SESSION_TRANSFER_CLIENT` 与简称都不是那个串，照样能认。
| Codex CLI | ✅ | ✅ | ❌ **拦** | 没有可用的 |
| OpenCode | ✅（首命中即停） | ✅ | **未实测** | `OPENCODE=1`（没接） |
| Deep Code (DeepSeek) | ✅ | ✅ | **未实测**（`/` 开菜单，技能进不进那个菜单没量到） | 没装，量不到 |
| Crush | ✅（多份全叠加） | ✅ | ❌（`/` 是它自己的快捷键） | `CRUSH=1`（没接） |
| Goose | ✅ | ✅ | ❌（只认注册过的 recipe） | 没有可用的 |
| Amp | ✅（`AGENT.md` / `CLAUDE.md` 兜底） | ✅ | ❌（斜杠菜单已撤） | 没有可用的 |
| ~~Gemini CLI~~ | ❌ 只读 `GEMINI.md` | ✅ | ✅ | ~~`GEMINI_CLI=1`~~ **已删** |

三件事从这张表读出来：

1. **几乎每家都不用为它生成任何东西。** 读 `AGENTS.md` + 扫 `.agents/skills/` 这两列
   大多是 ✅，所以两族壳已经把它们全接住了。真需要单独伺候的只有 Claude 一家
   （它不扫 `.agents/skills/`，所以生成器给 `.claude/skills/` 也落一份）。
   **别为「支持某家工具」去新建一族目录** —— 先量这两列，多半是零个新文件。
   ⚠️ 「大多是」而不是「全是」：表里已有一格是「未验」（MCode 读不读 `AGENTS.md`），
   **这一列空着就是还没量，别拿「别家都 ✅」填**。
2. **后六家落 `generic` 就是对的，不是漏了。**
   **`generic` 那一档给的是哪种形式，2026-10-13 从免斜杠翻成了带斜杠。**
   原来的判据是「没实测 → 给裸形式」，理由是「裸形式各家都敲得动（触发词接得住），
   留一个敲不动的斜杠才是每条引导都作废」。前半句在 harness 里不成立：**裸形式不是
   命令，只是聊天框里的一段文字**，触发词接得住的是模型、不是宿主。

   而两种错法的**可见性不同**：带错斜杠，工具报错或列出命令；缺斜杠，用户根本不知道
   有这条命令（`AGENTS.md`「每一处引导都要写出该敲的命令」那一节）。这张表里量过的是 **8 家吃斜杠、
   4 家不吃、2 家未实测** —— 认不出来的那一批更可能落在吃斜杠的一边。
   真拦的 Codex 已经自己一格（`JOBS_CODE_TOOL=codex`），不再靠 generic 兜底。

   代价说清楚：**Crush / Goose / Amp 三家实测不吃斜杠，但探测不到、也没有格子**，
   它们现在会拿到敲不动的斜杠。要救得手工指定，而它们又**没有可用的信号**
   （Crush 有 `CRUSH=1`，但接了只会让自检多印一个工具名、命令形式一个字都不变——
   探测的唯一下游是 `COMMAND_SYNTAX` 那张表，判据是「吃不吃斜杠」不是「认不认得出」；
   Goose 与 Amp 连信号都没有）。这一格只能由用户按这张表自己填，是「规则在」与
   「兜得住」之间真实存在的缺口，不假装它闭合了。
   OpenCode 与 Deep Code 本来就未实测，仍按多数派走。
3. **Gemini CLI 那一行整条删掉了（2026-09-30）。** 分清「停的是哪一层」再动手：
   npm 包**还在发版**（0.61.0，2026-09-24），关的是**个人版登录通道** ——
   登录返回 `reasonCode: "UNSUPPORTED_CLIENT"` / `tierId: "free-tier"`，
   拿一个假 `GEMINI_API_KEY` 也绕不过去；官方把命令行这条线指向 Antigravity CLI。
   所以删的是「我们推荐/探测/为它渲染」这三样，`security_guards.py` 里
   `.gemini` 目录下 `settings.json` 的 key 面**留着**（包还装得上，手放一份时那条
   宽授权仍然要红）。后继的 agy 不读那份文件：它的二进制里那个路径、
   `run_shell_command(`、`confirmationRequired`、`defaultApprovalMode`
   四个字符串**全是 0 命中**（2026-09-30 量）。

> **「本机这一版」不是「这家工具」。** Qwen 那一格原来是「不扫 `.agents/skills/`、
> 不认斜杠」，据的是本机装的 0.14.0；2026-09-29 发的 0.24.7 把两件事都改了
> （`PROJECT_SKILL_DIRS = [".qwen", ".agents"]`），结论当场作废 —— 而照它做出来的
> 会是「给 Qwen 再生一族 `.qwen/skills/` 壳」这种多余活。**下结论前先核版本。**

## 工具特化

- **每一条命令的入口都是两族技能壳**，由 `tools/gen_entries.py` 从 `workflows/INDEX.md`
  与 `tools/_entries.py` 生成，两族**逐字相同**：`.claude/skills/` 是 Claude Code 唯一
  的运行时技能目录，`.agents/skills/` 是上面那张表里其余每一家读的那一份。
  壳里只有触发词与工具权限，正文一律指回 `workflows/`。
- **两族之外还有一条路，且它才是正本**：`workflows/INDEX.md` 那张索引表每行给了正文
  在哪、怎么敲、不给参数时干什么，读它就能执行任何一条命令，不依赖壳在不在
  （`AGENTS.md` 里那节工作流索引现在只是一个指向它的指针）。壳与索引表不是两种能力，
  是同一个能力的两种到货方式。
- **自动触发**：Claude Code 侧的说明见 `CLAUDE.md`；其余各家读的是同一批壳里那行
  「触发词：…」，说一句「找职位」照样开跑。

**`.claude/` 里没有任何正文。** 那底下只有 `SKILL.md` 壳：每条命令一份，由
`tools/gen_entries.py` 从 `workflows/INDEX.md` 与 `tools/_entries.py` 生成，外加一份
手写的路由壳 `job-application-assistant`（`/job-scrape` 与 `/job-upskill` 也一样，
没有特例）。壳就干两件事：什么时候自动触发、跑起来手里有哪些工具；正文全在
`workflows/`，别的工具照索引读那一份就行，不会少任何东西。原来那批
`.claude/commands/` 薄 stub 已整体删除：斜杠命令这一层壳两族都给，那个目录里
再长出文件，`tools/lint_skills.py` 就报。

对应地，**工作流正文里不许出现 `.claude/` 路径，也不许自称「本技能 / this skill」**。
实测代价（2026-08-18）：`job-scrape.md` 里留着一句「框架自己的 `search-queries.md`
**在本技能目录下**」——正文早就从技能里搬出来了，那个位置**根本没有这个文件**
（真身在 `workflows/reference/search-queries.md`）；而对非 Claude 工具来说，
「本技能目录」这个概念压根不存在。`tools/lint_skills.py` 现在扫这两类。

可插拔的平台技能是另一回事：它们在 `.agents/skills/`，**不在** `.claude/` 下——
那是本仓库自己的插件目录，由 `workflows/job-scrape.md` 发现并调用，与具体哪个
AI 工具无关。

⚠️ **但 `.agents/skills/` 下不只有渠道。** `.claude/skills/` 下那些壳在这儿**也各有
一份**（每条命令一份生成壳，另加手写的 `job-application-assistant` 路由壳；
具体几份由 `workflows/INDEX.md` 的行数决定，不在这儿写死），与
`.claude/skills/` 下的逐字相同 —— 那是给不读 `.claude/` 的工具准备的
同一份壳。所以「哪些是渠道」的判据不是目录位置，是**有没有 `.agents/skills/*/cli/src/cli.ts`**；
凡是发现渠道的地方都按这个判（`job-scrape.md` 1b、`job-add-portal --list`）；
这份点名清单由 `tests/test_a_portal_skill_is_the_one_with_a_cli.py` 的
`BothDiscoverySitesSayIt.SITES` 对着扫——多一个发现点而名单没改，那边就红。
两份壳必须逐字一致，否则同一个技能在 Claude Code 和别的工具里触发词、权限都能不一样。

**这一族有几份壳，本文件、`AGENTS.md` 与各份文档都不写数字。** 加一条命令就多一份壳，
而写死的数字没有任何东西钉着，只会安静地变成假话。`AGENTS.md` 与 `workflows/INDEX.md`
里那些「21 条」是同一类，改命令条数时记得一起看。真对着盘数的是
`tests/test_shell_families_are_byte_identical.py` 与 `python tools/gen_entries.py --check`。

### 换个工具，哪些命令还能用

**命令一条都不少**，因为索引正本 `workflows/INDEX.md` 每一行都给了三样东西：
正文在哪、怎么敲、不给参数时干什么。执行者读那一行就够，不需要任何 `.claude/` 下的文件。

真正会卡住的**不是命令，是能力**。缺了怎么办**一律以 `AGENTS.md`「能力对照表」的降级列为准**
——这里只补它没有的那一半：每项能力卡住的是哪几条命令。

| 能力 | 卡住哪几条 |
|---|---|
| Gmail 读取 | `/job-gmail-sync`——这条命令整个就是为读 Gmail 而存在的 |
| Notion 写入 | `/job-notion-sync`——同上，且它本来就是可选的，别的流程不依赖 |
| 浏览器取数 | `/job-scrape`、`/job-rank`、`/job-auto`、`/job-add-portal`、`/job-refresh` |
| PDF 编译 | `/job-apply`、`/job-resume`、`/job-add-template` |
| 并行子代理 | `/job-apply` 的双角色审稿、`/job-rank` 的批量评分 |
| 网页抓取 / 网络搜索 | `/job-apply`、`/job-expand`、`/job-interview`、`/job-upskill` 等取外部信息的环节 |

> 这张表**只答「卡住哪几条」，不重复降级写法**。上一版把降级列整列抄了过来，
> 两处立刻就有了各自的说法（比如 Gmail 那格，正本写「全流程跳过并说明原因」，
> 抄件写成「Step 0 就停」）。一条规则在权威文件里排进第二张表，就等着它们分叉——
> `tests/test_docs_accuracy.py` 现在盯着：能力对照表之外的**表格行**里不许再出现
> 那几个降级短语（散文里提、引号里引不算，讲规则总得能引用它）。
> 这张表搬到本文件之后，那道判据的扫描范围一起扩到了这里（2026-09-29），
> 否则表一挪，规则就只对着空气跑。

### `.claude/` 是接入件，不是逻辑——证据与一条已经作废的结论

**实测**（2026-08-18）：把 `.claude/` 和 `CLAUDE.md` 整个挪走，`tools/` 下**每个脚本**
都照样起得来（逐个 `--help`，退出码全 0），自检与总览页照常，能力缺口的分格照常出结果。
唯一报错的是 `tools/security_guards.py`——它的职责就是核对权限文件里每一条都追溯得到
生成器的清单，`.claude/settings.json` 不在当然要红，那正是它该有的反应。

> **但那次实验下出来的那句结论已经不成立了，别连它一起抄。** 原话是「丢的只有 Claude
> Code 的斜杠命令和自然语言自动触发，其它工具想要同等便利，加自己的接入目录即可
> （如 `.codex/`）」——说那句的时候 `.agents/skills/` 里只住着猎聘一个渠道，
> **压根没有命令壳可丢**。2026-09-29 起 `tools/gen_entries.py` 把同一批壳**逐字写进两族**：
> `.claude/skills/` 给 Claude Code，`.agents/skills/` 给非 Claude 的各家（Codex CLI、
> Antigravity CLI (agy)、Qoder、Qwen Code、MiMo Code）。所以它们同样有命令入口与自然语言
> 触发，**没有 `.codex/` 这个落点，也不需要新增任何目录**。
>
> 守卫钉着这条边界：`.claude/commands/` 里再长出任何文件（命令 stub 已删，入口只由
> 生成器落到两族技能壳）、某条工作流在两族缺壳、或两族的壳集合对不上、工作流正文里
> 出现 `.claude/` 路径或自称「本技能」、`CLAUDE.md` 复述 `AGENTS.md` 已有的流程——
> `tools/lint_skills.py` 都会报。

## 命令形式：正本带斜杠，只有渲染层改

规则在 `AGENTS.md`「每一处引导都要写出该敲的命令」；这一节记的是它落到代码里的样子。

- **文档正本一律带斜杠**（`AGENTS.md`、`workflows/`、`workflows/INDEX.md`）——斜杠是
  命令的标准形式，去掉它是「某一家客户端的毛病」，不该污染正本。
- 改写只发生在**给用户看的最后一层**：`tools/doctor.py::adapt_commands()`，以及它包
  stdout 的那个 `_CommandStream`（包的是整条输出流，逐处 print 改必漏）。
- 给不给斜杠由一张表说了算：`doctor.COMMAND_SYNTAX`。**2026-09-29 / 09-30 逐家实测**，
  结论跟这张表原来的第一版相反：拦斜杠的不是「其余各家」，是 Codex 一家。

  | 工具 | 形式 | 实测出处 |
  |---|---|---|
  | `claude` | `slash` | 技能进它的斜杠表（二进制里的 `skillToolCommands`） |
  | `qoder` | `slash` | 它自己的口径：技能可按 `/<名>` 请求（2026-09-29 在真会话里看到的） |
  | `antigravity` | `slash` | 用户 2026-09-28 当场在 `/` 面板测过 `/job-scrape` 能匹配 |
  | `qwen` | `slash` | 0.24.7 把每个技能注册成 `/<技能名>`（2026-09-30 核；本机先前那版 0.14.0 不注册，结论按新版翻） |
  | `mimo` | `slash` | `MiMo：command/index.ts` 把技能以 `source: "skill"` 塞进命令表，`MiMo：skill/index.ts` 的注释写着「用户手敲斜杠照样能用」（2026-09-30 读源码） |
  | `mavis` | `slash` | 用户 2026-10-13 当场确认；信号 `MAVIS_SESSION_TRANSFER_CLIENT` 是逐个量出来的（见上面接入面表那一行） |
  | `codex`（探测不到，只能手工指定） | `no-slash` | `codex.exe` 0.159.0 里印着 `Unrecognized command '/-'. Type "/" for a list of supported commands.`（`tui\src\bottom_pane\chat_composer\inline_input.rs`）；技能是以 `<skills_instructions>` 注入给模型的，不注册成斜杠项 |
  | `generic` | `slash` | 兜「认不出来的那一批」。**2026-10-13 从 `no-slash` 翻过来的**，理由与代价见上面第 2 条 |
  | ~~`gemini`~~ | — | **2026-09-30 整格删掉**：那家已停（见上面那张接入面表的第 3 条）。它原来在这一档是**实测过的** —— bundle 里的 `SkillCommandLoader.ts` 确实把技能注册成 `/<技能名>`；删格的理由不是量错，是那家工具装不上了 |

**默认值是 `"slash"`（2026-10-13 从 `"no-slash"` 翻过来的）**：它兜的是**认不出来的那一批**，
而那批更可能落在吃斜杠的一边。免斜杠现在**只有 `codex` 一格**，它自己占着，
不再靠默认值兜。取值口径在 `doctor.command_syntax()` 一处，`adapt_commands()`、
包不包 stdout、印不印那一行工具名三处都从它读，不再各写一遍 `tool == "claude"`。

> ⚠️ **`codex` 那一格在 2026-10-13 之前是不存在的**——那时免斜杠靠默认值兜，
> 而 `codex` 探测不到（`CODEX` 那个变量根本不存在）、自动落 `generic`。
> 把它单独立格之后，「手工指定」第一次成了**有效**操作：
> `JOBS_CODE_TOOL=codex` 与面板上那个开关是仅有的两条退路。

> 这张表的第一版把除 Claude 以外的各家全写成 `no-slash`，理由就是「斜杠会被客户端
> 当成内置指令拦掉」。那句话是从 Codex 一家的行为推广出去的，其余几家当时**没有
> 逐家实测过**——白扣了它们的斜杠形式，而 `SETUP.md` 与本文件都照着它写。**「一家实测过」
> 与「其余家都一样」不是一个命题**，这条记在这儿。

> 同一次还编过一条**报错原文**。`README.md` 那版写过「许多终端命令行客户端（如 agy）
> 会拦，会提示 `Unknown command: /job-auto`」：agy 那半是错的（用户 2026-09-28 在它的
> `/` 面板里当场测过 `/job-scrape` 能匹配），而那串提示文案**在本仓库任何一次实测里
> 都没有出现过**——它是为了让「会拦」这个说法显得有出处才长出来的。判据：
> **没跑过的报错原文一律不许引**；要引就引量到那一家的那一条，带上文件名与版本号
> ——上面表里 Codex 那格就是那个形状。

### 探测信号逐个的出处

`tools/_cli.py::detect_code_tool()` 是正本；`doctor.py` 因「只用标准库、不 import
仓库模块」的契约保一份逐字副本。两条测试各管一段，互不重复：
`tests/test_code_tool_detection.py` 钉两份副本判得一样 + 不该再认的信号不许触发，
`tests/test_slash_survives_where_the_palette_is_the_skill_list.py` 钉渲染层那张表
（外加面板那份跨语言的抄件）。

| 工具 | 实测信号 | 怎么测出来的 |
|---|---|---|
| Claude Code | `CLAUDECODE=1`（另有 `CLAUDE_CODE_ENTRYPOINT`） | 对它注入给子进程的环境取证 |
| agy | `ANTIGRAVITY_AGENT=1`（另有 AGENTAPI_EXE / LS_VERSION） | agy.exe 里的字面量 |
| Qoder | `QODERCN_CLI=1`（另有 `QODER_AGENT_SDK_ENTRYPOINT=sdk-ts`） | 2026-09-29 在真 Qoder CN 会话里 `env \| grep -i qoder` |
| Qwen Code | `QWEN_CODE=1` | 它的 ShellExecutionService 给自己起的每个子 shell 注入（`cli.js` 里两处 `cpSpawn` 的 `env:` 块，2026-09-30 核） |
| MiMo Code | `MIMOCODE=1` | 主进程里 `process.env.MIMOCODE = "1"`（`MiMo：packages/opencode/src/index.ts`，紧邻 `AGENT=1`），子进程继承。它是 opencode 的分支，但**不设** `OPENCODE`，所以这个变量能唯一认出它 |
| Cursor、Codex CLI、Goose、Amp | 没有可识别标记 | 集成终端里 `TERM_PROGRAM` 是 `vscode` 不是 `cursor`；落 `generic` 那一档。**Codex 正好该落这里**——它是实测拦斜杠的那家，没有信号反而把它放进了安全档，所以既不为它加信号、也不给表里加格 |
| Crush / OpenCode | 有信号（`CRUSH=1` / `OPENCODE=1`）却**没接** | 接了只改自检里那行工具名，命令形式一个字都不变。判据是「吃不吃斜杠」，不是「认不认得出」。⚠️ 2026-10-13 起这层顾虑变了：Crush 实测**不吃**斜杠、OpenCode 未实测，两者落 `generic` 会拿到敲不动的斜杠——**所以「接上」现在能改变命令形式了**（各加一格 `no-slash`）。留着的唯一理由是没量过它们的桌面端与 CLI 是否同一形态，别为凑一家去猜 |
| ~~Gemini CLI~~ | ~~`GEMINI_CLI=1`~~ | **2026-09-30 删。** 它是**真信号**（那家确实给子 shell 注入过），与下面那批凭空写的假变量不是一回事；删的理由是那家已停，认一个装不上的工具没有意义 |

⚠️ **只许用实测过的信号。** 上一版写的 `CLAUDE_CODE`、`CLAUDE`、`CURSOR_VERSION`、
`CODEX` 在对应工具里根本不存在，结果真 Claude Code 会话被认成 generic
（2026-09-12 实测）。那四个名字如今就在探测测试的名单里，专门验「它们不再触发」。
`GEMINI_CLI` 也在那份名单里，但**归的是另一组**：那四个从来不存在，它是真有、
只是工具没了 —— 测试里分开写，别混成「假信号」。

Qoder 那一行有个**测不出来的部分**：从会话内部只能看到「这两个变量在当前这个
Qoder 会话里存在」，看不到它们是不是桌面端也注入。这不妨碍用它——本函数的返回值
只流向一个下游（上面那张表），而 Qoder 那一格是量出来的（它的 harness 自己写着技能
可按 `/<名>` 请求），所以「命中 Qoder 但那其实是别的界面」最坏是自检里那行工具名
不准；真敲不动的时候还有触发词，把要办的事说出来照样接得住。国际版那个
`QODER_CLI=1`（计划文档 §6 记着）在这个真会话里**复现不出来**，只有 `-cn` 那份，
所以没用它——将来测到了再加，不为凑一家去猜；认不出来就落 `generic`，
那是**带斜杠**那一档（2026-10-13 改，见上面第 2 条）。手工纠正：
`JOBS_CODE_TOOL=claude|antigravity|mimo|mavis|qoder|qwen|generic|codex`
（覆盖优先于自动探测，任意名字原样透传；自检末尾印的那串可选值是从表里派生的，
不是手抄的字面量）。

面板那头是同一张表的**跨语言抄件**：`web/src/context/CodeToolContext.tsx` 里的
`KNOWN_TOOLS` 与 `SLASH_TOOLS` 两份名单。原来它自己写了一遍 `tool !== "claude"`，
于是 2026-09-29 把几家翻成吃斜杠之后**一行都不用改就全绿**，而面板继续给
Qoder / agy 免斜杠 —— 抄件与正本分叉不会自己喊，所以现在由
`ThePanelCarriesTheSameTable` 逐格对拍（名单不等，或又出现按单家公司硬编码的判断
→ 红）。表外的名字（`codex` 除外）仍然**有意**归一到 `generic`：归一之后差别只在那一行
叫什么名字。`codex` 2026-10-13 起自己一格——它探测不到，但归一之后**命令形式也不再
跟着它走**了，所以那不是「只差个名字」。

换工具丢的东西**只剩斜杠那一层字形，而且只剩一家丢**：六家工具（Claude Code、
Antigravity CLI (agy)、MiMo、MCode、Qoder、Qwen Code）都吃 `/job-apply` 这种敲法
（Claude 还带补全）；**认不出来的那一批现在也吃**（2026-10-13 改）；只有 Codex 要把它
换成 `job-apply`，或直接把要办的事说出来——**同一批壳、同一行触发词**。分档的正本
在上面那张表（`doctor.COMMAND_SYNTAX`），落地的地方是 `doctor.adapt_commands()`。

> 这句话的**句式带守卫**：`tests/test_docs_accuracy.py::TheToolCountIsTheEnumeration`
> 钉的是「『N 家工具』后面括号里点名的家数要等于那个汉字数字」。
> 2026-10-13 改写这一句时它当场报「找不到那句——句式改了就把这条一起改」，
> **拦的正是「改写之后数字与点名脱钩、守卫从此空转」**。所以这一句要改就照原句式改。

> 这一段原来写的是「换工具唯一真正失去的是语法糖：斜杠命令**和自然语言自动触发**，
> 两者都是 Claude Code 读 `.claude/` 得来的」。斜杠那一半成立，自动触发那一半已经被
> **本文件开头那三条**否掉了——两句话在同一个文件里隔着十行互相打架，而它抄的是
> `.agents/skills/` 里只住着一个渠道那个时代的结论。留这段引文是为了说清为什么撤：
> **「入口在哪一族」和「有没有入口」是两件事，别写成一句。**

## 复核入口

上面每一格都可能过期。要改判据（尤其是「加一族壳」「翻一档斜杠」这种会动生成物的），
先按下面这几条重量一次 —— **本机就有，不用信文档**。

**第 0 步永远是核版本。** `<工具> --version`，再 `npm view <包名> version` 对一下
本机装的是不是最新。Qwen 那一格的结论就是被这一步翻掉的：本机 0.14.0 与当周发的
0.24.7 行为不同，据旧版下的结论会做出多余的活。

- **看技能有没有被发现，别读代码，先找有没有这类子命令。** 有的话一条命令就够：
  它会把每个技能的启用状态、描述与**绝对路径**印出来，直接回答「这个仓库的
  `.agents/skills/` 被这家发现了没有」。（Gemini CLI 那条 `skills list` 就是这个
  形状；它停了，但同族的后继与分支多半留着类似入口，先 `--help` 看一眼。）
- **读安装包/bundle。** npm 装的那几家的 bundle **没混淆到读不了**：
  `var XxxLoader = class {` 这种能直接读，注释里连源文件路径都留着。
  按**字符串字面量**搜，别按函数名搜 —— 压缩后的短名每版重编，换版本全废；
  `".claude","skills"`、`skillsOut`、`sourceLabel`、`PROJECT_SKILL_DIRS` 才是稳的。
  Windows 上 `grep` 大文件（几十 MB 起）用 `-a -z -o -E '模式.{0,N}'` 才跨得过
  内嵌 markdown 的换行，但**窗口别开太大**：20 MB 以上的文件配几百字符的窗口会
  直接超时，改成 `grep -n` 拿行号再 `sed -n` 打印那几行。
- **读原生二进制**（agy、Codex、Claude 这三家用到的是编译好的可执行文件，不是能直接
  读的 JS bundle——Codex 虽然走 npm 装，装下来的也是 exe；Claude 在这台机器上连 npm
  都没走）。同样按字面量搜。
  判「某个配置文件它读不读」，搜那个**路径字符串**与它的键名：
  本次判 agy 不读 `.gemini` 目录下那份 `settings.json`，用的就是路径与
  `run_shell_command(` / `confirmationRequired` / `defaultApprovalMode` 全 0 命中。
- **agy 自带文档随二进制发布**，在用户目录的 `antigravity-cli/builtin/skills/
  agy-customizations/docs/` 下（规则、技能、MCP、钩子、JSON 配置各一份，
  尺寸闸门就写在规则那份里）。
- **量「用户敲 `/job-scrape` 这家吃不吃」，用活体探针，别读文档。** 在仓库外建一个
  空目录，放几个带唯一标记的文件，用那家的非交互模式问「哪些标记出现了」，
  **一定带一个正对照**（明知它读得到的那一份）。问「是/否 + 名字」比问
  「把所有标记列出来」可靠。文档说支持 ≠ 此刻真存在，文档没提 ≠ 不存在 ——
  这两个方向的错本仓库各栽过一次，解药都是同一个：跑一次，或读 bundle。
- **探测信号**：在真会话里 `env | grep -i <工具名>`；拿不到真会话就去二进制里搜
  字面量。**搜不到不等于没有**，但「看着像」的名字一律不许写进代码。
- **引用别家项目的源码路径要带上项目名**（写成 `MiMo：command/index.ts` 这种，
  别光写一个路径）。读的人得知道那个文件不在本仓库；另外
  `tests/test_cross_references_resolve.py` 会核「反引号里带斜杠的路径在盘上找得到」，
  那条判据管的是本仓库的路径，别家的源码它永远核不了。
