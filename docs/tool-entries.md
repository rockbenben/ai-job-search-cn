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

各列按已列出的实测或官方文档记录；两种依据注明来源，不互相冒充。厂商约定会变，
改判据前按文末「复核入口」重新核对。

| 工具 | 读 `AGENTS.md` | 扫 `.agents/skills/` | 吃斜杠 | 探测信号 |
|---|---|---|---|---|
| Claude Code | ✅（另有 `CLAUDE.md`） | ❌ 运行时只有 `.claude/skills/` | ✅ | `CLAUDECODE=1` |
| Antigravity CLI (agy) | ✅（`GEMINI.md` 也读，两份都加载、按条目去重；2026-09-30 读它自带的规则文档） | ✅ | ✅ | `ANTIGRAVITY_AGENT=1` |
| Qoder | ✅（另有 `AGENTS.local.md`） | ✅（legacy 开关默认开） | ✅ | `QODERCN_CLI=1` |
| Qwen Code | ✅ | ✅（0.24.7 起；0.14.0 不扫） | ✅ | `QWEN_CODE=1` |
| MiMo Code | ✅ | ✅（默认开） | ✅ | `MIMOCODE=1` |
| MCode | **未验** | ✅ | ✅ | `MAVIS_SESSION_TRANSFER_CLIENT=1`（2026-10-13 逐个量出来的） |
| Cursor | ✅（官方规则文档） | ✅（官方技能文档） | ✅（2026-11-09 用户确认 + 官方核对） | 暂无已验证自动信号；可用 `JOBS_CODE_TOOL=cursor` |
| Codex（桌面 / CLI / IDE） | ✅ | ✅ | 桌面 `/` 菜单；CLI / IDE `/skills`；各端默认 `$job-…` | `CODEX_THREAD_ID` / `CODEX_SESSION_ID` |
| OpenCode | ✅（首命中即停） | ✅ | **未实测** | `OPENCODE=1`（没接） |
| Deep Code (DeepSeek) | ✅ | ✅ | **未实测**（`/` 开菜单，技能进不进那个菜单没量到） | 没装，量不到 |
| Crush | ✅（多份全叠加） | ✅ | ❌（`/` 是它自己的快捷键） | `CRUSH=1`（没接） |
| Goose | ✅ | ✅ | ❌（只认注册过的 recipe） | 没有可用的 |
| Amp | ✅（`AGENT.md` / `CLAUDE.md` 兜底） | ✅ | ❌（斜杠菜单已撤） | 没有可用的 |
| WorkBuddy | ✅（2026-11-09 本次会话注入；**不读 `CLAUDE.md`**） | ❌（读项目级 `.codebuddy/skills/` 或 `.workbuddy/skills/`，两族都生成） | ✅ | `CLIENT_INFO_IDE_TYPE=WorkBuddy`（2026-11-09） |
| ~~Gemini CLI~~ | ❌ 只读 `GEMINI.md` | ✅ | ✅ | ~~`GEMINI_CLI=1`~~ **已删** |

> **WorkBuddy 这一行是 2026-11-09 在 5.9.3 桌面版上逐格量的，四列的证据各不一样。**
> - 读 `AGENTS.md` ✅：本次会话注入的 `<project_guidance>` 正是仓库根 `AGENTS.md`；
>   bundle `dist/codebuddy-lite-wb.mjs` 里有 `L="AGENTS.md"`，`product.json` 写着
>   「有 AGENTS.md 就别新建 CODEBUDDY.md」。⚠️ **但注入层把它截断了**：本次在约
>   第 250 行「跟进归用户」处 `[...too long, omitted...]`，后半段（能力对照表、
>   取数顺位、并行分派、工具特化）没进常驻上下文。截断在 IDE 注入层，不是它读文件
>   那一层 —— 与上面 agy 24,000 B / Codex 32 KiB 是同类题，别记成同一处。
> - 扫 `.agents/skills/` ❌：本会话技能清单里 23 份 job-* 壳一份都没加载；
>   项目级 `.codebuddy/`、`.workbuddy/skills/` 原本都不存在。bundle 里
>   `.agents/skills` 只出现一次，形如 `~/.agents/skills/`（用户级），且落在
>   `DEFAULT_TOOLCHAIN_ALLOW_WRITE_DIRS` 那串写权限白名单里，**不是**扫描路径。
>   ⚠️ **两个候选项目级目录没能量出桌面版究竟扫哪个**：CLI 文档与 bundle 的
>   「启动时加载的配置」清单点名 `.codebuddy/skills/`，桌面版会话说明写
>   `.workbuddy/skills/`。按「量不出来就别猜」的规矩两族都生成（见下面「工具特化」），
>   代价是生成物多一族；哪天实测出只认一处，从 `SHELL_FAMILIES` 删掉另一处即可。
> - 吃斜杠 ✅：`product.json` 里那条自定义技能说明写得明白：在项目级技能目录
>   里建一个 `SKILL.md`，然后敲 `/commit` 就能跑；bundle 里有 `user-invocable` /
>   `disable-model-invocation` 的可见性逻辑（`deriveSkillVisibility`），
>   skill 默认进 `/` 菜单。⚠️ 前提是壳真被加载 —— 这一行接进来之前，
>   `/job-auto` 在这家工具里是敲不动的。
> - 探测信号：`env` 在真会话里量到 `CLIENT_INFO_IDE_TYPE=WorkBuddy`、
>   `WORKBUDDY_PRODUCT_NAME=WorkBuddy`、`WORKBUDDY_APP_VERSION=5.9.3`、
>   `CODEBUDDY_HOST=workbuddy-desktop`、`WORKBUDDY_IS_PACKAGED=1` 等。
>   取最贴「跑在哪个 agent 里」的 `CLIENT_INFO_IDE_TYPE`，加一个产品名兜底。
>   ⚠️ 它也注入 `CLAUDE_PROJECT_DIR` / `CLAUDE_SESSION_ID`（兼容层），但
>   `CLAUDECODE` 实测不在 —— 所以这一档必须排在 `claude` 之前。
> - **`CLAUDE.md` / `.claude/skills` 在 bundle 里 0 命中**：Claude 侧那份
>   「Gmail → Claude MCP、浏览器 → Claude 扩展」的落点在这家工具里整个不生效。
>   浏览器能力改由 `workflows/reference/cdp-portals.md` 按工具对号入座，
>   见下面「浏览器能力按工具自动适配」。

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

三件事从这张表读出来：

1. **先量这两列，再决定要不要建目录。** 读 `AGENTS.md` + 扫 `.agents/skills/`
   大多是 ✅，所以各族壳已经把它们全接住了。真需要单独伺候的有两家：Claude
   （不扫 `.agents/skills/` → 给它 `.claude/skills/`）与 WorkBuddy
   （两个候选项目级目录都量到了证据、却量不出桌面版认哪个 → 两族都落）。
   ⚠️ **2026-11-09 修掉一句旧结论**：原来这里写「别为『支持某家工具』去新建
   一族目录」，那是对「量过且两列都 ✅」的归纳，不是禁令。真量出 ❌ 就该建，
   拿它当禁令会让人守着规则、放着工具接不进来。
   ⚠️ 「大多是」而不是「全是」：表里已有一格是「未验」（MCode 读不读 `AGENTS.md`），
   **这一列空着就是还没量，别拿「别家都 ✅」填**。
2. **未识别工具使用完整自然语言请求。** `generic` 现在为 `bare`，显示为
   「请读取并执行 workflows/job-auto.md」，参数原样附后。既不猜 `/` 注册，也不假定
   `$` 是所有工具的通用入口。裸写技能名不是明确的工作流调用；只有能读取项目文件的
   助手才能执行这个请求。不能读文件时需要提供工作流正文，不能假装技能已加载。

3. **Gemini CLI 那一行在表里划掉了（2026-09-30）** —— 留着是为了留个位置，不是它还在被支持。分清「停的是哪一层」再动手：
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

- **每一条命令的入口都是各族技能壳**，由 `tools/gen_entries.py` 从 `workflows/INDEX.md`
  与 `tools/_entries.py` 生成，各族**逐字相同**：`.claude/skills/` 是 Claude Code 唯一
  的运行时技能目录，`.agents/skills/` 是上面那张表里大部分家读的那一份，
  `.codebuddy/skills/` 与 `.workbuddy/skills/` 是 WorkBuddy 的两个候选项目级落点
  （两处都量到证据、没量出桌面版究竟认哪个，所以都落；出处见表格下那段脚注）。
  **族数不写死在任何文档里**，正本是 `tools/_entries.py::SHELL_FAMILIES`，
  `tools/lint_skills.py` 保一份逐字副本（相等由 `test_one_value_one_home.py` 钉住）。
  壳里只有触发词与工具权限，正文一律指回 `workflows/`。
- **各族之外还有一条路，且它才是正本**：`workflows/INDEX.md` 那张索引表每行给了正文
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
`.claude/commands/` 薄 stub 已整体删除：斜杠命令这一层壳各族都给，那个目录里
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
同一份壳。WorkBuddy 那两族同样各有这一整套（含手写路由壳；它不走生成器，
加族时要人工同步，由 `test_shell_families_are_byte_identical.py` 逐族对拍）。
所以「哪些是渠道」的判据不是目录位置，是**有没有 `.agents/skills/*/cli/src/cli.ts`**；
凡是发现渠道的地方都按这个判（`job-scrape.md` 1b、`job-add-portal --list`）；
这份点名清单由 `tests/test_a_portal_skill_is_the_one_with_a_cli.py` 的
`BothDiscoverySitesSayIt.SITES` 对着扫——多一个发现点而名单没改，那边就红。
各族壳必须逐字一致，否则同一个技能在 Claude Code 和别的工具里触发词、权限都能不一样。

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
> ⚠️ **2026-11-09 补一句**：WorkBuddy 是这条的例外——它两个候选项目级目录都不在
> 当时那两族里，而两个都量到了证据、却量不出桌面版究竟认哪个，于是新增了两族。
> 判据没变（先量那两列），变的是量出来的结果；别把上面那句当成「永远不许新增目录」。
>
> 守卫钉着这条边界：`.claude/commands/` 里再长出任何文件（命令 stub 已删，入口只由
> 生成器落到各族技能壳）、某条工作流在某族缺壳、或各族的壳集合对不上、工作流正文里
> 出现 `.claude/` 路径或自称「本技能」、`CLAUDE.md` 复述 `AGENTS.md` 已有的流程——
> `tools/lint_skills.py` 都会报。

### 当前 Codex 调用方式（2026-11-09 复核）

Codex 支持斜杠菜单，项目技能默认使用 `$job-…` 显式引用，各端通用。桌面 `/` 菜单
可选择已启用技能，CLI / IDE 可用 `/skills`。旧版 CLI 拒绝未知 `/job-*` 的记录仅说明
那个入口未注册，不能推广为 Codex 不支持斜杠。下文免斜杠的旧记录仅为历史；
当前 `COMMAND_SYNTAX["codex"]` 为 `dollar`，总览提供自动、斜杠、技能引用和自然语言四档。
当前依据与操作见 [Codex 说明](codex.md)。

### 浏览器能力按工具自动适配（2026-11-09）

Codex 接入补充见 [docs/codex.md](codex.md)。现在先从真实会话标记识别宿主，
再由执行者检查当轮实际工具清单（含延迟发现的工具），选择浏览器；两步分开，
不把「识别到 Codex」当成「浏览器已连接」。执行步骤的正本在
`workflows/reference/cdp-portals.md`「执行时自动选择浏览器」。生成器为涉及浏览器
的命令壳自动加入该入口，`job-scrape` 的探测步骤也指向它。

Codex 桌面本次实测提供 `mcp__cua_repl` 与 `mcp__chrome_devtools`；CLI / IDE
是否提供浏览器工具要看实际连接。工具名只作已知示例，不是固定白名单。
`allowed-tools` 对其它宿主的声明不替代 Codex 自身工具与权限；咨询转入已授权的
执行流程时，不再要求用户重新输入命令。

「浏览器取数」这一行以前只写了 Claude 的落点。换到 WorkBuddy 时，AI 照着
`AGENTS.md` 那句「Claude 浏览器扩展」去找 `mcp__claude-in-chrome__*`，找不到就
判定「这个工具没有浏览器能力」，**直接退到 `site:` 兜底** —— 能力明明在，却用不上。
三处一起改掉，让落点按当前工具对号入座：

1. **能力对照表**（`AGENTS.md`）那一行改成中立的「用你所在工具自带的浏览器能力」，
   逐家落点指向 `workflows/reference/cdp-portals.md`（它是权威）。
2. **自检输出**（`tools/doctor.py::BROWSER_BACKEND`）按 `detect_code_tool()` 渲染那句，
   不再写死「Claude Code 用浏览器扩展」。WorkBuddy 下会明说自带的 `agent-browser`
   首次使用自动装好，并**如实说明它开的是独立 Chromium、登录态要登一次**；
   `~/.claude/skills/web-access` 那份 CDP skill 在 WorkBuddy 下也不再被误报为
   「你还装了备用抓取方式」（这家工具不读那个目录）。
3. **壳的 `allowed-tools`**（`tools/_entries.py::BROWSER_BASH`）：WorkBuddy 的
   `agent-browser` 是 Bash CLI，不是 MCP 工具。壳里没有 `Bash(agent-browser:*)`
   时 `/job-scrape` 走顺位 1 会被逐次弹授权。现在按「工作流正文提到这项能力」
   自动派生**程序名级**白名单（与 `PORTAL_BASH` / `_uses_portal()` 同构），
   各族壳逐字一致，权限文件 `.claude/settings.json` 也由 `shared_grants()` 同步。
   落点**不写进共用工作流正文** —— `AGENTS.md` 要求正文只写能力名、不点名工具。

⚠️ **登录态不是白来的，别把一家的说法照抄给另一家**：Claude 浏览器扩展驱动用户
日常那个已登录的 Chrome，登录态天然带着；`agent-browser` 开的是**独立的
Chromium**，BOSS / 智联要在它里面各登录一次，之后同一 daemon 会话内 cookies 才保留
（见它 SKILL.md 里讲 daemon 与会话保留的那一节）。差异写进 `SETUP.md` 3.1 与
`workflows/reference/cdp-portals.md`，自检那句也照实说。

## 命令形式：正本带斜杠，显示时按宿主适配

`AGENTS.md` 与 `workflows/` 的命令正本仍是 `/job-*`。显示层统一读取
`tools/doctor.py::COMMAND_SYNTAX`：已支持的其它宿主采用 `slash`，未识别宿主采用 `bare` 完整自然语言请求，
Codex 采用 `dollar`，复制为 `$job-*`，参数原样保留。裸写名称属于自然语言请求。

Codex CLI 支持 `/skills` 菜单；桌面版的 `/` 菜单会列出已启用技能。默认复制使用各端
支持的 `$job-*`，避免从终端环境猜桌面还是 CLI。旧 CLI 对未知 `/job-*` 的报错只能
说明那个命令未注册，不能作为整个 Codex 产品不支持斜杠的依据。官方链接见
[Codex 接入说明](codex.md)。已弃用的 `/prompts:名称` 不作为默认安装方案。

总览页默认自动适配，并提供斜杠、技能引用、自然语言三个手动选项；手动选择可切回
自动。新版本单独保存设置，旧免斜杠设置不再覆盖自动适配结果。
`doctor.adapt_commands()` 与前端格式化器都只处理独立的工作流引用，保留文件路径、
网址、已有技能引用及 `/skills` 等客户端命令；前后端的宿主表由测试逐项核对。

### Cursor 的能力与身份识别（2026-11-09）

Cursor 已确认支持 `/技能名`，会发现项目 `.agents/skills/`，无需再生成一套 Cursor
技能副本。官方依据：[技能目录与斜杠调用](https://cursor.com/docs/skills)、
[AGENTS.md 支持](https://cursor.com/docs/rules)。

当前没有经过会话实测的自动识别信号，不能将 `TERM_PROGRAM=vscode` 解释为 Cursor。
显式指定 `JOBS_CODE_TOOL=cursor` 时，自检、总览命令显示按 slash 适配；总览也可手动
选「斜杠模式」。无法确认身份时仍给完整自然语言请求，不能据此说 Cursor 不支持斜杠。

### 探测信号逐个的出处

`tools/_cli.py::detect_code_tool()` 是正本；`doctor.py` 因「只用标准库、不 import
仓库模块」的契约保一份逐字副本。两条测试各管一段，互不重复：
`tests/test_code_tool_detection.py` 钉两份副本判得一样 + 不该再认的信号不许触发，
`tests/test_slash_survives_where_the_palette_is_the_skill_list.py` 钉渲染层那张表
（外加面板那份跨语言的抄件）。

| 工具 | 实测信号 | 怎么测出来的 |
|---|---|---|
| WorkBuddy | `CLIENT_INFO_IDE_TYPE=WorkBuddy`（另有 `WORKBUDDY_PRODUCT_NAME` / `WORKBUDDY_APP_VERSION=5.9.3` / `CODEBUDDY_HOST=workbuddy-desktop`） | 2026-11-09 在真 5.9.3 桌面会话里 `env` 逐个量；取最贴「跑在哪个 agent 里」的那个，产品名兜底。⚠️ 它也注入 `CLAUDE_PROJECT_DIR` / `CLAUDE_SESSION_ID`，但 `CLAUDECODE` 实测不在，所以排在各家之前 |
| Claude Code | `CLAUDECODE=1`（另有 `CLAUDE_CODE_ENTRYPOINT`） | 对它注入给子进程的环境取证 |
| agy | `ANTIGRAVITY_AGENT=1`（另有 AGENTAPI_EXE / LS_VERSION） | agy.exe 里的字面量 |
| Qoder | `QODERCN_CLI=1`（另有 `QODER_AGENT_SDK_ENTRYPOINT=sdk-ts`） | 2026-09-29 在真 Qoder CN 会话里 `env \| grep -i qoder` |
| Qwen Code | `QWEN_CODE=1` | 它的 ShellExecutionService 给自己起的每个子 shell 注入（`cli.js` 里两处 `cpSpawn` 的 `env:` 块，2026-09-30 核） |
| MiMo Code | `MIMOCODE=1` | 主进程里 `process.env.MIMOCODE = "1"`（`MiMo：packages/opencode/src/index.ts`，紧邻 `AGENT=1`），子进程继承。它是 opencode 的分支，但**不设** `OPENCODE`，所以这个变量能唯一认出它 |
| Codex | 非空 `CODEX_THREAD_ID` / `CODEX_SESSION_ID` | 2026-11-09 在本项目 Codex 桌面会话的子 shell 中实测；只记录变量名和是否非空，不记录会话 ID。显式覆盖优先，其后 WorkBuddy 的产品标记，再判 Codex；不拿版本号或安装路径判断，也不据此判断浏览器连接 |
| Cursor | 暂无已验证的自动识别信号；支持 `JOBS_CODE_TOOL=cursor` | 2026-11-09 用户确认 + 官方文档核对 `/skill-name` 与 `.agents/skills/` 支持；明确识别为 Cursor 时采用 slash。不能用普通 VS Code 终端信号猜测 |
| Goose、Amp | 没有可识别标记 | 未识别时采用 generic 的完整自然语言请求 |
| Crush / OpenCode | 已有信号但未接入具体宿主档 | 当前使用 generic 的完整自然语言请求；不根据安装路径或未经验证的变量猜测命令语法 |
| ~~Gemini CLI~~ | ~~`GEMINI_CLI=1`~~ | **2026-09-30 删。** 它是**真信号**（那家确实给子 shell 注入过），与下面那批凭空写的假变量不是一回事；删的理由是那家已停，认一个装不上的工具没有意义 |

⚠️ **只许用实测过的信号。** 上一版写的 `CLAUDE_CODE`、`CLAUDE`、`CURSOR_VERSION`、
`CODEX` 在对应工具里根本不存在，结果真 Claude Code 会话被认成 generic
（2026-09-12 实测）。那四个名字如今就在探测测试的名单里，专门验「它们不再触发」。
`GEMINI_CLI` 也在那份名单里，但**归的是另一组**：那四个从来不存在，它是真有、
只是工具没了 —— 测试里分开写，别混成「假信号」。

Qoder 那一行有个**测不出来的部分**：从会话内部只能看到「这两个变量在当前这个
Qoder 会话里存在」，看不到它们是不是桌面端也注入。这不妨碍用它——本函数的返回值
用于上面的命令形式表，而 Qoder 那一格是量出来的（它的 harness 自己写着技能
可按 `/<名>` 请求），所以「命中 Qoder 但那其实是别的界面」最坏是自检里那行工具名
不准；真敲不动的时候还有触发词，把要办的事说出来照样接得住。国际版那个
`QODER_CLI=1`（计划文档 §6 记着）在这个真会话里**复现不出来**，只有 `-cn` 那份，
所以没用它——将来测到了再加，不为凑一家去猜；认不出来就落 `generic`，
那是**完整自然语言请求**那一档（2026-10-13 改，见上面的命令形式说明）。手工纠正：
`JOBS_CODE_TOOL=workbuddy|claude|cursor|antigravity|mimo|mavis|qoder|qwen|generic|codex`
（覆盖优先于自动探测，任意名字原样透传；自检末尾印的那串可选值是从表里派生的，
不是手抄的字面量）。

面板那头是同一张表的**跨语言抄件**：`web/src/context/CodeToolContext.tsx` 里的
`KNOWN_TOOLS`、`SLASH_TOOLS` 与 `DOLLAR_TOOLS` 三份名单。原来它自己写了一遍 `tool !== "claude"`，
于是 2026-09-29 把几家翻成吃斜杠之后**一行都不用改就全绿**，而面板继续给
Qoder / agy 免斜杠 —— 抄件与正本分叉不会自己喊，所以现在由
`ThePanelCarriesTheSameTable` 逐格对拍（名单不等，或又出现按单家公司硬编码的判断
→ 红）。表外的名字（`codex` 除外）仍然**有意**归一到 `generic`：归一之后差别只在那一行
叫什么名字。`codex` 2026-10-13 起自己一格，2026-11-09 起自动识别；若把它归一成
`generic`，命令形式也会错，所以那不是「只差个名字」。

命令显示按宿主适配：八家工具（Claude Code、
Antigravity CLI (agy)、MiMo、MCode、Qoder、Qwen Code、WorkBuddy、Cursor）都吃 `/job-apply` 这种敲法
（Cursor 于 2026-11-09 经用户确认与官方文档核对，其他沿用已有实测）；未识别宿主显示完整自然语言请求；Codex 默认把它
换成 `$job-apply`，或直接把要办的事说出来——**同一批壳、同一行触发词**。分档的正本
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
