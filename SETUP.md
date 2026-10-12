# 安装指南

让 AI 求职助手在你本机跑起来的分步说明。

<!-- per-user-path-explainer -->
> ### 先说一件会让人找不到文件的事
>
> 本文（和仓库里其它文档）写到你的个人文件时用的都是**简写**，比如
> `profile/candidate.md`、`resume/main.typ`、`job_search_tracker.csv`。
> **它们不在仓库根目录**——真实位置是 `users/<你的用户名>/` 下的同名路径：
>
> ```
> 文档里写            实际位置
> profile/candidate.md   →  users/张三/profile/candidate.md
> resume/main.typ        →  users/张三/resume/main.typ
> ```
>
> 这么设计是为了多人能共用一份 clone、各自数据互不可见。当前是谁记在仓库根的
> `.active_user` 文件里，由 `/job-setup` 首次创建、`/job-user` 切换。
>
> **例外**：`resume/template.typ`、`cover_letter/template.typ`、`resume/example.typ`、
> `templates/README.md`、共享模板库 `templates/cv/` 与 `templates/cover_letters/`、
> `documents/README.md`——这几个是**全用户共享的框架文件**，就在仓库根，不按用户解析。
> （这条枚举的**正本在 `AGENTS.md`「活动用户与多用户」**。这里是抄给读本文的人看的，
> 要加新的共享条目，先加到正本。）
>
> 所以：`users/` 目录在你跑 `/job-setup` 之前是空的，`resume/` 下只有模板和示例——
> **这是正常的**，不是 clone 出了问题。
<!-- /per-user-path-explainer -->
<!-- 上面这段**有意**展示简写形式（它就是在教这套映射）。
     `tests/test_where_to_put_your_resume.py` 的路径检查按这对标记跳过它——
     别把标记删掉，也别把别的内容挪进这对标记之间。 -->

## 1. 环境依赖

**不必一次装齐。** 按下面的顺序装，每装完一项就多解锁一部分功能；缺的那项只影响
对应命令，其它照常工作，且命令会在报告里说明这轮实际走了哪条路径。

| | 装什么 | 解锁 |
|---|---|---|
| **① 必装** | **一个能读 `AGENTS.md` 并执行工作流的 AI 编码工具** + **Node 22.18+**（见下方「运行时」一节） | 填资料 `/job-setup`、**搜职位 `/job-scrape`**、**打分排序 `/job-rank`**、面试准备 `/job-interview`、记投递 `/job-outcome`、学习计划 `/job-upskill`、切换用户 `/job-user` |
| **② 要出简历 PDF 就装** | Typst（中文字体一般已自带） | `/job-apply` 编译 PDF（不装只给 `.typ` 源文件） |
| **③ 强烈建议装** | Python 3.10+（流水线全程只用标准库） | `/job-dashboard` 总览页；**以及 `/job-setup` 重跑「改搜索词」那节时先读每个词抓过的真实战绩（抓到多少岗、哪几个跑偏）、`/job-rank` 的预筛淘汰、`/job-scrape` 的 JD 详情库、`/job-outcome` 的催进度判定、`/job-upskill` 的缺口分格、`/job-add-template` 的模板撞名检查、`/job-auto` 的词表写回、`/job-refresh` 的刷新记录、以及 `/job-rank`/`/job-outcome`/`/job-gmail-sync`/`/job-interview`/`/job-user`/`/job-cv`/`/job-reset`/`/job-scrape --no-rank` 收尾刷新面板数据**——这几条命令没有它仍能跑，但各少一环（`/job-rank` 不做淘汰、每轮重抓 JD；`/job-setup` 改词时没战绩可看，只能自己想）。另外仓库自带的四个检查脚本也用它 |
| ④ 可选 | poppler（提供 `pdftotext` 与 `pdftoppm`） | 简历 PDF 的文本层校验与视觉检查（不装则跳过并说明；两个都在 poppler 里，一条安装命令带齐） |
| ⑤ 可选·进阶 | 能开浏览器的 AI 工具（Claude Code 装 Claude 浏览器扩展即可） | BOSS 直聘 / 智联 / 前程无忧（没有则退 `site:` 兜底）。见 3.1 |
| ⑥ 可选·进阶 | Gmail / Notion MCP 连接器 | `/job-gmail-sync`、`/job-notion-sync`（不装则整体跳过） |
| ⑦ 只有改 CLI 代码才需要 | Bun | 跑 `bun test`（CLI 的单元测试）。日常使用完全不需要 |

> **本仓库不绑定单一 AI 工具**（README 也是这么说的）：Claude Code、Codex CLI、
> Antigravity CLI (agy)、Qoder、Qwen Code、MiMo、Cursor 都能用，入口都是 `AGENTS.md`。
> 命令入口由 `tools/gen_entries.py` 生成到**两族技能目录、逐字相同**：
> `.claude/skills/` 给 Claude Code，`.agents/skills/` 给其余几家（见 README
> 「那 `.claude/` 是干什么的？」与 `docs/tool-entries.md`）。所以「换工具就得自己
> 报工作流文件名」那句是旧话：说「投这个岗 <链接>」、或直接敲命令名，跑的都是同一份
> `workflows/job-apply.md`，自动触发词也在壳里带着。索引正本 `workflows/INDEX.md`
> 仍然是第三条路——每行写着正文在哪、怎么敲、不给参数时干什么，壳不在也照样执行。
>
> **本文的示例按 Claude Code 写，理由只有一个：斜杠。** 2026-09-30 逐家实测之后
> 这个理由归五家了——命令形式表（`tools/doctor.py` 的 `COMMAND_SYNTAX`）里
> `claude` / `antigravity` / `mimo` / `qoder` / `qwen` 五格都是 `slash`，
> `/job-auto` 那种敲法在这五家里就是它的原生形态。**只有 Codex CLI 拦**：它把开头的
> `/` 留给自己的内置指令（实测出处见 `docs/tool-entries.md`），连同认不出来的助手
> 一起落 `generic` 那一档、给 `job-auto`。Cursor 与 Codex 至今没有可识别标记，
> 所以落 `generic` 是默认行为而不是判断；认错了手工指定：
> `JOBS_CODE_TOOL=claude|antigravity|mimo|qoder|qwen|generic`。

**只想先看看效果**：只装 ①，跑 `/job-setup` → `/job-scrape`（抓完自动打分排序），就能拿到真实的排序名单。
猎聘搜索 CLI 直接跑在 Node 上（零 runtime 依赖、无编译步骤），不需要额外运行时。

### Claude Code

安装 Claude Code（Anthropic 的 Claude 命令行工具）：

```bash
npm install -g @anthropic-ai/claude-code
```

需要一个 Anthropic API key 或 Claude Pro/Team 订阅。详见
[Claude Code 文档](https://docs.anthropic.com/en/docs/claude-code)。

### Python

`/job-dashboard`（求职总览页）与仓库自带的四个检查脚本需要 Python 3.10+。
**流水线全程只用标准库**；四个检查脚本里只有 `lint_skills.py` 例外，
它要 `pip install pyyaml`（读 `SKILL.md` 的 YAML frontmatter）。
那是给贡献者跑的，日常求职一条都用不到。

**没有它也能跑完整条流水线**——`/job-setup` 填资料、`/job-scrape` 找岗、
`/job-rank` 打分、`/job-apply` 出话术都不依赖 Python。装它换来的是：

- **总览页**：一个岗展开就能「复制开场白」粘去投；投递状态点一下就写回、
  记拒绝原因、投后统计（回复率、按分数段的回复率、拒绝原因分布）、
  屏蔽不想看的公司与职位
- 几条命令各少一环的地方补齐：`/job-rank` 的预筛淘汰与详情库、`/job-outcome`
  的「该催哪几个」、`/job-upskill` 的缺口分格、`/job-auto` 的词表写回

> 上面这一句原来写的是「**其它命令都不用它**」——不准确：本页 §1 的依赖表
> 自己就列了一批命令用 Python 做各自的一环。它们**没有 Python 仍能跑**，
> 但各少一环，这和「不用它」是两回事。

检查：

> ⚠️ **总览页还要构建一次前端。** 界面是 React 写的（`web/`），第一次出总览页
> 之前要跑一次 `cd web && npm install && npm run build`——只需要一次，之后数据变了
> 直接跑 `/job-dashboard` 就行。Node 你本来就要装（下一节，`/job-scrape` 与 `/job-rank` 用它）。
>
> **构建末尾那段黄字不是报错**：Vite 提醒「有的代码块超过 500 kB」——那条提醒是给
> 要走网络下发的网站看的，而这一页只在你自己电脑上跑（`127.0.0.1`），不经网络。
> 看到 `✓ built in …` 就是成功了。
>
> 这一条以前不需要：总览页曾经由一个纯 Python 脚本直接吐 HTML，与 React 那套并存。
> 两套各有一份布局与文案，「同一条规则只修一侧」反复发生，所以合并成了一套。
> 代价就是这一次 npm 构建。

```bash
python3 --version
```

Windows 上 `py --version` 通常最可靠。如果你的系统把 Python 暴露成 `python` 而非
`python3`，下面命令里用 `python`。

### 职位搜索 CLI 的运行时：Node 就够，不用装 Bun

猎聘搜索 CLI（`liepin-search`）用 TypeScript 写，**零运行时依赖、没有编译步骤**，
直接从源码跑。Node 22.18+ 默认就会剥离 TS 类型（22.6 起有这个能力，但要加 `--experimental-strip-types` 开关；
22.18 才成为默认），所以下面这条不带任何开关：

```bash
node .agents/skills/liepin-search/cli/src/cli.ts search -q "后端开发" -l "北京" --format table
```

**多半你已经装了 Node**——但各家 AI 工具的装法不一样（有的走 npm、有的是原生可执行
文件），从手上那个工具反推不出「机器上有没有 Node」。确认一下版本够：

```bash
node --version    # 需要 v22.18 或更高
```

低于 v22.18，或者 `node` 根本不存在（比如你用的是 Cursor 这类不走 npm 的工具），
就去 [nodejs.org](https://nodejs.org) 装/升一下。

<details>
<summary>Bun：只有要改 CLI 代码、跑它的单元测试时才装</summary>

CLI 的测试用 `bun:test` 写，所以开发时需要 Bun；**日常使用完全不需要**。

- macOS/Linux：`curl -fsSL https://bun.sh/install | bash`
- Windows PowerShell：`powershell -ExecutionPolicy Bypass -c "irm https://bun.sh/install.ps1 | iex"`
  （或 `winget install Oven-sh.Bun`）

装了之后 `bun run …` 与 `node …` 两种方式都能跑 CLI，行为一致，两者都在 CI 里验证。

</details>

### 中文环境准备

猎聘 CLI 的 `-q`/`-l` 参数直接传中文（职位关键词、城市名），下面几点能避免中文在
终端里显示异常：

- **Windows PowerShell / cmd**：如果输出的中文乱码，先切到 UTF-8 代码页再运行 CLI：
  ```powershell
  chcp 65001
  ```
  Windows Terminal 默认已经是 UTF-8，通常不需要这一步；老式 `cmd.exe` 窗口更容易碰到。
- **终端字体**：确认终端字体支持中文字符（Windows Terminal、iTerm2、大多数 Linux
  终端默认都支持）。
- **Git 中文文件名**：如果你的资料目录（`documents/`）里有中文文件名，执行一次
  `git config core.quotepath false`，避免 `git status` 把中文文件名转义成八进制转义
  序列。

### Typst（用于编译简历）

安装 Typst（一个静态二进制，无需 TeX 发行版）：

- **Windows：** `winget install --id Typst.Typst`（安装后需**新开终端**）
- **macOS：** `brew install typst`
- **Linux：** 从 [Typst releases](https://github.com/typst/typst/releases) 下载对应平台的二进制，加入 `PATH`

简历用 `typst compile` 编译，不涉及 TeX 发行版、字体宏包安装或引擎选择。

安装后快速验证：

```bash
typst --version
typst compile resume/example.typ /tmp/example.pdf
```

```powershell
typst --version
typst compile resume/example.typ $env:TEMP\example.pdf
```

#### 中文字体

**一般不用管。** 模板的回退链已覆盖三平台的自带字体，中文环境的机器基本都能命中。
只有**精简 Linux / 容器 / WSL 这类本来就没装中文字体的环境**才需要补装，
装开源的 [Noto Sans SC / Noto Serif SC](https://fonts.google.com/noto)（可免费商用）即可。

模板的回退链覆盖三平台，按顺序是：

```
Noto Sans SC → Source Han Sans SC          （跨平台，开源）
→ 微软雅黑 / 黑体 / 等线                    （Windows）
→ PingFang SC / Hiragino Sans GB / STHeiti （macOS）
→ Noto Sans CJK SC / WenQuanYi Zen Hei     （Linux）
```

小节标题另走一条**衬线链**（`Noto Serif SC → Source Han Serif SC → 宋体 → Songti SC /
STSong → Noto Serif CJK SC`）。**这条不命中不要紧**——实测过：Typst 会继续退到上面那条
黑体链，标题只是从衬线变成黑体，**不会出豆腐块**。下面的自检只查黑体链就够了。

**一个都没命中时不会有任何报错。** 实测行为是：Typst 打印
`warning: unknown font family`、**exit 0**、照样产出 PDF，而且 **PDF 文本层完整可提取**
——所以 `/job-apply` 的 ATS 文本层校验**也会通过**。你会拿到一份渲染成豆腐块、却过了
全部自动检查的简历，一路投出去都不会有人提醒你。

**自己确认一句就够**（有任何输出即正常）：

```bash
typst fonts | grep -iE "noto sans sc|source han sans|microsoft yahei|simhei|dengxian|pingfang sc|hiragino sans gb|stheiti|noto sans cjk|wenquanyi"
```

```powershell
typst fonts | Select-String -Pattern "Noto Sans SC|Source Han Sans|Microsoft YaHei|SimHei|DengXian|PingFang SC|Hiragino Sans GB|STHeiti|Noto Sans CJK|WenQuanYi"
```

一条都没有 → 先装字体再编译简历。
（`/job-apply` 的第 5c 步也会做这个检查并停下告知，但自己先确认一次更省事。
**不要**拿「stderr 有没有 `unknown font family`」当判据——回退链跨平台，任何平台都必然
为另两个平台的字体报 warning，那不是错误。）

若你需要注册自定义 LaTeX 简历模板（`/job-add-template` 支持可选的 `xelatex`/`lualatex` 引擎），
需要自行安装对应的 TeX 发行版（Windows: [MiKTeX](https://miktex.org/download)；
macOS: [MacTeX](https://tug.org/mactex/)；Linux: `texlive-full`）与中文宏包，
并在模板说明中记录所需宏包与字体。这属于可选路径，框架默认不需要。

### 可选：pdftotext（用于 ATS 校验）

`/job-cv` 会对编译好的定制简历做 ATS 可解析性校验：提取 PDF 的文本层，按招聘系统
（ATS）实际看到的样子验证联系方式、阅读顺序与关键词覆盖。这一步用到
[poppler](https://poppler.freedesktop.org/) 的 `pdftotext`，它不随 TeX 发行版附带：

- **macOS：** `brew install poppler`
- **Debian/Ubuntu：** `sudo apt install poppler-utils`
- **Windows：** `choco install poppler`

缺少 `pdftotext` 时，`/job-apply` 会跳过这步机械校验并告警，退回到目视关键词检查——
其余一切照常。

## 2. 获取代码

在 GitHub 上 fork 本仓库到你自己的账号下，再克隆你 fork 后的副本：

```bash
git clone <你 fork 后的仓库地址>
cd <仓库目录>
```

## 3. 安装职位搜索 CLI 依赖（**这一步可以跳过**）

`liepin-search` **零运行时依赖**——直接 `node .agents/skills/liepin-search/cli/src/cli.ts …`
就能跑。这一步只拉 TypeScript 的开发期类型，**只有你要改 CLI 代码、跑类型检查时才需要**。

要装的话，从仓库根目录运行：

- PowerShell：

```powershell
Push-Location ".agents/skills/liepin-search/cli"
npm install
Pop-Location
```

- Bash / zsh / Git Bash：
```bash
(cd .agents/skills/liepin-search/cli && npm install)
```

（装了 Bun 的话 `bun install` 等价。）

> 这一节原来只给 `bun install`，还写着「不装也能直接 `bun run` 起来」——而本文
> 上面刚说过「**Node 就够，不用装 Bun**」、表格里 Bun 也标着「只有改 CLI 代码才需要」。
> **同一份安装指南里自相矛盾**：Node-only 的用户照着第 3 节做，撞到的是
> `bun: command not found`。

想再接入其他**有免登录 API** 的国内平台，用 `/job-add-portal` 生成对应的搜索技能——它会照着
同一套 CLI 结构脚手架出来，并在注册前用真实查询跑一遍验证，验证不通过就不接入。

**BOSS 直聘 / 智联招聘 / 前程无忧不走这条路**：实测这三家没有可用的免登录接口
（具体实测见
[`workflows/reference/cdp-portals.md`](workflows/reference/cdp-portals.md)），
`/job-add-portal` 建出来的 CLI 只会静默返回 0 结果，所以本项目**不为它们建 CLI**。`/job-scrape`
改走下面的浏览器渠道前置条件，覆盖这三家。

### 3.1 可选：BOSS 直聘 / 智联招聘 / 前程无忧要怎么开

这三家没有免登录接口，只能**通过浏览器**读（页面结构与实测见
[`workflows/reference/cdp-portals.md`](workflows/reference/cdp-portals.md)）。
驱动浏览器有两个顺位，**先看第一个够不够**：

#### 顺位 1（推荐）：用你 AI 工具自带的浏览器能力

**Claude Code 用户装了 Claude 浏览器扩展就已经具备**，不需要装本仓库以外的任何东西。
它驱动的就是你自己那个日常 Chrome，所以：

- **登录态天然带着**——你在 BOSS / 智联登录过，它就能读到你能读的东西。
- 需要在页面上点、填、滚动时也能做（这类 GUI 操作正是它的强项）。

你要做的只有一件事：**在 BOSS 直聘和智联招聘各登录一次**（前程无忧不用登录也能读）。
登录后顺手在站内把「求职期望」设准——`/job-scrape` 会先读你的站内期望，搜出来的岗明显更对口。

#### 顺位 2（没有扩展时）：装一个 CDP skill

1. **一个能驱动登录态 Chrome 的 CDP skill —— ⚠️ 本项目不附带，需你自己装一次。**

   仓库里只有 `.claude/skills/` 与 `.agents/skills/` 下那几个自带技能。CDP 那一层
   （连上你日常 Chrome、取 DOM、开关后台 tab）是**独立的第三方 skill**，装在你的用户
   全局目录（`~/.claude/skills/`），不在本仓库里。

   实测可用的一个是 **[`web-access`](https://github.com/eze-is/web-access)**
   （MIT，作者 一泽 Eze）。装法任选其一：

   ```bash
   # Plugin 方式（推荐，可随上游更新）
   claude plugin marketplace add https://github.com/eze-is/web-access
   claude plugin install web-access@web-access --scope user

   # 或者手动 clone
   git clone https://github.com/eze-is/web-access ~/.claude/skills/web-access
   ```

   也可以直接让 Claude 装：`帮我安装这个 skill：https://github.com/eze-is/web-access`

   **本项目不绑定这一个实现。** `workflows/reference/cdp-portals.md` 的流程只用到四种
   能力——连 Chrome 的 remote-debugging 端口、按 CSS 选择器取 DOM、开关后台 tab、截图。
   任何提供这四种能力的 skill 都能替代；换了别的实现，把该文件里出现的 `web-access`
   读作「你那个 CDP skill」即可。

   > 装完后**它自己还有前置条件**：Node.js 22+，以及在 Chrome 地址栏打开
   > `chrome://inspect/#remote-debugging` 勾选「Allow remote debugging for this browser
   > instance」（可能要重启浏览器）。这些由该 skill 自己的前置检查负责提示，不是本项目管的。

   **没有这层能力也完全能用本项目**：猎聘走 `liepin-search` CLI（免登录、仓库自带），
   BOSS/智联/前程自动退到 `site:` 网络搜索兜底。覆盖不如 CDP 完整，`/job-scrape` 会在
   报告里如实标注实际走的是哪条路径。
2. **一个已在对应网站登录、并开启了 remote-debugging 的 Chrome**——`web-access` 复用
   这个已登录会话，天然带着你的登录态；没有登录态浏览器，或 `web-access` 的前置检查
   （`check-deps`）没通过，这三家就退到 `site:` 兜底（网络搜索检索公开索引页）。
3. **在 BOSS / 智联站内设好你的「求职期望」**（岗位 + 城市，智联还能设到区）。
   实测这两家登录后，**裸搜索页返回的就已经是按你的期望过滤好的结果**——`/job-scrape`
   优先直接用它，不再自己拼查询参数。期望设得越准，这两个渠道的结果就越对口。
   **前程无忧看登录态**：登录后同样完全个性化（裸入口的页面标题直接变成你的期望岗位
   与城市），未登录才退回关键词搜索——那时裸入口给的是本地泛招聘。2026-08-19 实测，
   逐家记录见 cdp-portals.md。

**诚实说明（务必读）**：要点如下，**账号安全铁律与诚实边界的完整、权威版本以
[`workflows/reference/cdp-portals.md`](workflows/reference/cdp-portals.md)
为单一来源**（「账号安全铁律」「诚实边界」两节）——本处只列要点，日后收紧规则时
以 cdp-portals.md 为准，不在此逐字重述：

- **交互式 / 半自动，不是批量采集**：CDP 一次拿到的是当前页可见的有限结果，不承诺
  覆盖全站，更不是能像 `liepin-search` 那样跑批量的 CLI。
- **有账号风控 / 封号风险**：走的是你自己的登录会话——保持低频、不批量开页，撞到
  验证码/滑块/风控提示立即停手、不硬闯，风险自担（细则见 cdp-portals.md）。
- 覆盖方式是 **走浏览器为主、`site:` 兜底**——浏览器按上面那两个顺位取（先看工具
  自带的，没有才装 CDP skill）。两个顺位都够不着、或浏览器结果稀薄时才退/补 `site:`，
  报告里如实标注该轮实际走的是哪一层，不谎称走了浏览器。

## 4. 填写个人资料

**在你自己那家 AI 编码工具里打开这个项目目录。** 命令行类的先 `cd` 进来再启动它——
工作流、命令入口、你的资料都在这个目录里，从别的目录启动它看不到。用的是哪一家都一样。

然后运行：

```
/job-setup
```

它会提供三条路径：

- **路径 A（documents 文件夹）：** 把你的简历、领英导出、证书、推荐信放进
  **`users/<你的名字>/documents/`** 下对应的子目录（简历放 `cv/`、证书放 `diplomas/`、
  领英导出放 `linkedin/`、推荐信放 `references/`），它读完并交叉印证后再提出资料更新。
  适合你手头有多份材料时。

  **格式：PDF 最省事**，`.md` / `.txt` / `.tex` 也行；**Word（`.doc`/`.docx`）读不了**，
  先「另存为 → PDF」。放哪、放什么、`/job-setup` 各读出什么，完整对照表见
  [`documents/README.md`](documents/README.md)。

  > 路径是**每个人各自**的（`<你的名字>` 见仓库根 `.active_user`）。放到仓库根的
  > `documents/` 下不行：那样多人共用一份 clone 时互相可见，而且 `/job-setup` 不去那里找。
  > 目录由 `/job-setup` 建立首个用户时一并建好。
- **路径 B（导入单份简历）：** 用 `@` 提及文件或直接粘贴文本给出一份简历，Claude 提取后
  就缺失项追问。
- **路径 C（访谈模式）：** 按分节的结构化问题逐段回答。

三条路径结果相同：填好的资料文件。

### 会填充哪些文件

下表用的是**简写**（见本文开头那段说明）——实际都在 `users/<你的名字>/` 下。

<!-- per-user-path-explainer -->
| 文件 | 内容 |
|------|------|
| `profile/candidate.md` | 你的完整候选人资料（教育、经历、技能、职业目标、你说过做不了的事） |
| `profile/behavioral.md` | 行为特质（MBTI + 自评） |
| `profile/interview-star.md` | 你经历里的 STAR 案例 |
| `profile/search-queries.md` | `/job-scrape` 用的搜索查询 |
| `resume/main.typ` | 含真实信息的 Typst 主简历 |
<!-- /per-user-path-explainer -->

个人数据在 `profile/`，已默认 gitignore；首次 `/job-setup` 会从仓库里的 `profile.example/`
占位符模板生成 `profile/`，再写入你的真实资料。

**简历照片（可选）**：互联网/大厂投递通常可以不放，体制内、传统行业投递常要求附照片。
要启用的话，把照片放到**你自己那份简历的旁边**：

```
users/<你的名字>/resume/photo.jpg
```

必须和 `users/<你的名字>/resume/main.typ` **同一个目录**——Typst 的 `image()` 不允许
引用入口文件所在目录之外的东西。**不是仓库根的 `resume/`**：那里放的是共享模板
（`template.typ`），照片搁进去 Typst 找不到。

放好之后在 `users/<你的名字>/resume/main.typ` 里给 `resume()` 函数加上
`照片: "photo.jpg"` 参数（值是**相对同目录的文件名**，不带路径）；不放照片就不加这个
参数，模板会自动回退到无照片排版。用 PNG 的话命名成 `photo.png` 并相应改参数，
**别把 PNG 改名成 `.jpg`**。

### 重新填写

之后可以只更新某些分段：

```
/job-setup --section skills
/job-setup --section experience
/job-setup --section search
```

`--section search` 尤其实用——随着你的求职优先级变化，它重跑搜索配置访谈，并基于你的
完整资料建议一些你没考虑过的岗位方向。

## 5. 跑一遍完整流程

找一个你感兴趣的职位（用 `/job-scrape`，或手动找），然后：

```
/job-apply <职位详情页链接>
```

或者直接粘贴职位描述：

```
/job-apply [在这里粘贴职位描述]
```

Claude 会：
1. 按你的资料评估匹配度（国内硬性条件 + 技能·薪资·强度·发展四项评分 + 待核实的信息），同时判定本次投递是否命中
   求职信触发场景（校招网申系统要求上传求职信、体制内、外企、传统行业等；直聊
   HR/猎头等默认场景不触发）
2. 判定**投递路径**（平台直聊 / 网申·报名·公共邮箱）与**对话方**（猎头 / HR 直招）；结论是「强匹配 / 值得投」就直接往下走，更弱的档才停下来问你
3. 起草该出的那几个渠道的话术（直聊出打招呼开场白；网申与公共邮箱出网申自评或邮件正文）；命中场景时额外起草一份正式求职信。
   **简历发你的主简历，本命令不做定制**——要针对某个岗定制走 `/job-cv`
4. 派一个独立的**审稿者**子代理调研公司、核实事实、批评草稿
5. 修订后落盘到 `users/<你的名字>/documents/applications/<公司>_<岗位>/` 并呈现

**投之前**先跑一次 `/job-resume`——它逐条比对基简历与你的资料：数字对不对得上、有没有
写到你自己说过做不了的事、结构与页数合不合规。基简历是所有投递共用的那一份，写歪了
每一次投递都带着同一个毛病出去。

**投出去之后**这一段同样有工具接着：

```
/job-outcome <公司>        投完记一笔（后面的催进度、备面、框架校准全靠它）
/job-outcome followup      十来天没动静时，算清哪些该催并起草跟进话术
/job-interview <公司>      阶段化面试准备包 + 可选模拟面；问答会记下来，总览页能回看
/job-offer <公司>          拿到 offer：可守区间、背调红线自查、多 offer 比较、离职过渡清单
```

其中 `/job-offer` 的**背调红线**那一节不要跳过：口头报的薪资必须经得起个税 APP 记录
核对，一旦对不上，offer 会被直接撤回。

## 6. 编译你的简历

**平时不需要编译定制简历**——`/job-apply` 发的是你的主简历，不为每个岗重做一份。
只有特殊情况才跑 `/job-cv`（何时算特殊情况见 `workflows/job-cv.md`），它会自动完成
编译与校验（`typst compile` + 视觉检查 + ATS 文本层校验），PDF 落在
`users/<你的名字>/documents/applications/<公司>_<岗位>/resume.pdf`。

如果你想手动重新编译某一份定制简历（把 `<你的名字>` 换成 `.active_user` 里那一行）：

```bash
# Bash / zsh / Git Bash
typst compile "users/<你的名字>/documents/applications/<公司>_<岗位>/resume.typ" \
              "users/<你的名字>/documents/applications/<公司>_<岗位>/resume.pdf"
```

```powershell
# PowerShell
typst compile "users/<你的名字>/documents/applications/<公司>_<岗位>/resume.typ" "users/<你的名字>/documents/applications/<公司>_<岗位>/resume.pdf"
```

这些命令针对默认的 Typst 简历模板。如果你想换用自己的模板（Typst 或 LaTeX），运行 `/job-add-template`
—— 它会采集模板的编译引擎、字体、样式规则与页数上限，试编译通过后接入出材料的命令。详见 README 里的模板相关小节。

## 7. 各家工具的权限文件：哪份是真的、哪份本仓库不生成

`/job-auto` 一轮要跑好几个 `python tools/…`，第一条不批就反复问你（见常见问题里
「跑 /job-auto 时它反复问」那一节）。换成别的 AI 工具，它也有一套「预批准」的配置——
问题是**那套配置长什么样、放在哪**，各家全不一样，而一份「看着像」的配置会被信任、
被提交，然后**静默什么都不做**。所以这一节按取证说话。

取证方式：读**本机装好的那一家自带的** schema 与二进制，不读二手文档
（官方 docs 那条 configuration 的 raw URL 现在 404，而安装包里的字段说明就是原文）。

| 工具 | 本仓库生成它的权限文件吗 | 取证结论 |
|---|---|---|
| Claude Code | **生成** `.claude/settings.json` | 仓库自己就按这个形状写；`tools/security_guards.py` 现在逐条查它有没有出处 |
| ~~Gemini CLI~~（2026-09-30 已停） | **不生成**（2026-09-29 取证后撤回，盘上那份已删） | `tools.allowed` 这个键确实存在（0.58.0 安装包的 settings schema），但它的值形如 `run_shell_command(git)`——**不带括号只写一个工具名 = 所有 shell 命令都免确认**；而 `tools.autoAccept` 在 0.58.0 的 schema 里查无此键（审批模式那个键在 `general` 块下）。曾经生成的那份两样都占。**停的是个人版登录通道，npm 包还在发版**，官方把命令行这条线指向 Antigravity CLI；所以 `tools/security_guards.py` 里那一格 key 面**留着**——谁手放一份宽授权进来，照样红。后继的 agy 不读这份文件（它的二进制里那个路径 0 命中） |
| Codex CLI | **不生成** | 预批准命令**不是** `config.toml` 里的键，而是 execpolicy 的 rules 文件（Starlark DSL）。形状与匹配语义都实测过（下面那条命令能自己复现），但**哪个目录下的 rules 会被自动加载没实测到** |
| Antigravity CLI（agy） | **不生成**（它的配置在用户主目录，归用户，本仓库不写那儿） | 那套流传的键名（`allowed_patterns` / `approval_policy` 等）在 agy 的二进制里 0 命中——写了不生效；实测到的只有命令行开关 |

**每一家的可粘片段都由生成器给，别手抄**（片段里那些命令前缀与
`.claude/settings.json` 同源，改一处两处一起动）：

```bash
python tools/gen_entries.py --print claude   # 已生成那份的原文
python tools/gen_entries.py --print codex    # prefix_rule(...) 的写法 + 实测到的匹配语义
python tools/gen_entries.py --print agy      # 下面那一节粘的就是它
```

自己复现 Codex 那一条（不需要登录，纯本地）：

```bash
codex execpolicy check --rules <规则文件> --pretty pdftotext -layout -enc UTF-8 in.pdf out.txt
```

> ⚠️ 别把 Claude 那条 `.agents/skills/*/cli/src/cli.ts` 的通配原样抄给别家。
> 2026-09-29 实测：Codex 的 `prefix_rule` 按 token 逐段比，token 里的 `*` **匹配不上
> 任何渠道**（返回的是空命中列表）。所以非 Claude 的片段已经把那个通配展开成
> 你机器上真装着的渠道路径。

### Antigravity CLI（agy）的权限

agy 读**用户主目录**下的配置，本仓库不写那儿。它「预批准某条命令」的配置文件形状
**没有核实到**，所以下面这段不是「粘进某个文件就生效」的配置，而是**本仓库预批的那几条
命令前缀**的中立写法（不带任何家的语法包装）：agy 哪天支持前缀白名单，照它自己的写法
把这几条粘进去。不加也能用，只是每条命令要批一次。

```text
# Antigravity CLI (agy) 1.2.13（2026-09-30 复核）—— 本仓库不写 agy 的配置（它在用户主目录，归用户）。
# 权限片段的 schema 没核实到，所以这里不给可直接粘贴的配置文件写法，只给
# 要授权的那几条命令前缀（中立写法，不带任何家的语法包装）。
# 实测依据：agy.exe 里搜不到 allowed_patterns / approval_policy / approval_mode /
# allow_inline_scripts / allow_dangerous_commands 这些键名（Go 的 toml tag 会以
# 字面量留在二进制里）—— 本机 ~/.antigravity/config.toml 用的正是这套键名，
# 而它每一项都静默不生效；别照着那份教别人。
# 核实到的只有命令行开关（`agy --help`）：
#   --mode accept-edits            自动允许改文件，命令仍然逐条问
#   --sandbox                      开终端沙箱限制
#   --dangerously-skip-permissions 全部自动批准（本仓库不推荐，等于把闸门拆了）
# 下面不含 `Skill(...)` 那一条 —— 那是 Claude 的技能授权，agy 没有对应物。
  Agent
  bun --version
  bun run .agents/skills/liepin-search/cli/src/cli.ts
  node --version
  node .agents/skills/liepin-search/cli/src/cli.ts
  pdftotext
  python tools/applied_jds.py
  python tools/archive.py
  python tools/audit_pipeline.py
  python tools/check_outreach.py
  python tools/doctor.py
  python tools/export_web_data.py
  python tools/fetch_details.py
  python tools/followups.py
  python tools/gap_split.py
  python tools/ingest.py
  python tools/jd_store.py
  python tools/outreach_header.py
  python tools/portal_budget.py
  python tools/prescreen.py
  python tools/query_yield.py
  python tools/resume_refresh.py
  python tools/score.py
  python tools/serve.py
  python tools/stale_materials.py
  python tools/template_usage.py
  python tools/trim_opening.py
  python tools/writeback.py
  typst
  WebFetch
  WebSearch
```

最后那条 `--dangerously-skip-permissions` 等于把闸门拆了，本仓库不推荐。
要取最新的一段：`python tools/gen_entries.py --print agy`（上面那一整段就是它的输出，
装了新的渠道 CLI 之后要重新取一次——有条测试盯着这两份一致）。

## 常见问题

### 职位搜索 CLI 跑不起来
先看 `node --version` 是不是 **v22.18 以上**——低于这个版本，Node 剥不掉 TS 类型，
CLI 直接起不来（装了 Bun 的话可以改用 `bun run …` 绕过）。搜索需要网络访问。
**不需要**先跑 `bun install`：CLI 零运行时依赖，那一步只拉开发期类型（见第 3 节）。
如果详情命令报 `PARSE_FAILED` 或结果为空，可能是猎聘对详情页的临时限流——
先用 `curl` 请求同一 URL 看是不是跳到了 `transit.html` 挑战页，是的话**停手等待**
（详见 `.agents/skills/liepin-search/url-reference.md` 的「详情页的临时限流」一节），
不要加大请求频率。

### Typst 编译报错
- 确认 `typst --version` 能跑通；Windows 上装完 Typst 需要新开终端才能让 `PATH` 生效
- 中文显示为方块字：检查系统是否安装了模板要求的中文字体（字体回退链见 `resume/README.md`
  的「依赖」一节与 `resume/template.typ` 顶部；推荐装 Noto Sans SC / Noto Serif SC）
- 若你注册了自定义 LaTeX 模板（`/job-add-template` 的可选引擎），LaTeX 编译报错时确认对应发行版
  与宏包已安装，且引擎（`xelatex`/`lualatex`）与模板要求一致

### 跑 `/job-auto` 时它反复问「要不要跑 `python tools/…`」

**那是预期行为，不是坏了。** 下面那份共享清单只预批了四条（两个运行时的 CLI、
`pdftotext`、那个自动触发技能），**不含 `python`**。而 `/job-auto` 一轮要跑好几个
`python tools/*.py`（自检、额度闸门、导出面板……），所以第一次跑会被问上几次 ——
它承诺的「中途不用你盯着」说的是**不用你做判断**，不是「不会向你要授权」。

三种做法，选一个：

- **在提示里点「总是允许」**（推荐）。Claude Code 会把那一条记进你自己的
  `.claude/settings.local.json`，下次不再问。一次一条，你看得见批的是什么。
- **自己先批**：在 `.claude/settings.local.json` 里照 `settings.json` 现有那几条的
  形状写一条（`Bash(<命令前缀>:*)`）。那是**你自己的本机覆盖**，不进版本库。
- **什么都不做**：每次问一下，照答即可。

> ⚠️ **别把它加进提交进版本库的 `.claude/settings.json`。** 那会替每一个 fork
> 用户预批，而 `tools/security_guards.py` 会当场红 —— 按它自己的说法，这类守卫
> 的职责是让危险改动**变响**，而不是让它变得不可能。真要加，按 CONTRIBUTING
> 「提交前必跑的三件」的做法：同一个 PR 里连它的清单一起改，让改动走审阅。
>
> 早期版本正是预授权过 `Bash(python:*)` 才撤掉的 —— 那一条把仓库外的任意
> Python 命令也一并放行了，见下一节。

### 旧 clone 遗留的 `.claude/settings.local.json`
共享的 Claude Code 权限现在放在 `.claude/settings.json`（允许 `node …/cli.ts`、`bun run …/cli.ts`、`pdftotext` 与 `job-application-assistant` 技能——**两个运行时各一条**，所以 Node 用户不会被权限拦住）。本仓库早期版本曾提交过一份更宽的
`.claude/settings.local.json`，预授权了 `Bash(curl:*)`、`Bash(python:*)`、`Bash(bun:*)`。
如果你在那次改动之前 clone 过，git 会把旧文件留在你的工作副本里，其权限仍会叠加在
`settings.json` 之上。删掉它（或裁剪成你自己的个人覆盖项）：

```bash
rm .claude/settings.local.json
```
