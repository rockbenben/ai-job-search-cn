# AI 求职助手（中文版）

> 让 AI 搜国内岗位、筛选匹配机会、备好投递材料，你来点发送

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE) [![365 开源计划 #029](https://img.shields.io/badge/365%20%E5%BC%80%E6%BA%90%E8%AE%A1%E5%88%92-%23029-1f6feb)](https://github.com/rockbenben/365opensource)

[下载源码](https://github.com/rockbenben/ai-job-search-cn/archive/refs/heads/main.zip) · [快速开始](#快速开始) · [全部命令](workflows/INDEX.md)

![求职总览页：并排查看岗位评分、薪资、开场白和下一步操作](docs/images/dashboard.webp)

把这个仓库交给 **WorkBuddy、Claude Code 或 Codex**：AI 先核对学历、户口、外包与执业资格，再按技能、薪资、工作强度和发展排序，备好投递话术。上图使用虚构演示数据，公司与职位均为虚构。

资料和材料保存为本机文件，换 AI 工具也能接着用。日常只需三条命令：填资料、自动找岗备材料、记录结果；投递由你自己完成。

## 支持哪些工具和招聘站

**运行环境：一个 AI 编码工具 + Node 22.18+。** 先在终端运行 `node --version` 确认版本，详细安装步骤见 [SETUP.md](SETUP.md)。

| AI 工具 | 如何开始 |
|---|---|
| **WorkBuddy** | 打开仓库文件夹，在对话框输入 `/job-setup`；浏览器渠道使用自带的 `agent-browser` |
| **Claude Code** | 在仓库目录启动，输入 `/job-setup`；浏览器渠道可使用 Claude 浏览器扩展 |
| **Codex（桌面版 / CLI / IDE）** | 打开仓库，在对话框输入 `job-setup`；命令去掉开头的斜杠，见 [Codex 接入说明](docs/codex.md) |
| Antigravity CLI、Qoder、Qwen Code、MiMo、MCode | 在仓库目录启动，输入 `/job-setup` |
| Cursor 等其它助手 | 打开仓库后，先让助手读取 [AGENTS.md](AGENTS.md)，再输入 `/job-setup`；能力差异见 [工具接入说明](docs/tool-entries.md) |

下文示例保留 `/`，**Codex 用户去掉开头的斜杠即可**。也可以直接说「自动跑一轮」「投这个岗 <职位链接>」，由助手执行对应工作流。

| 渠道 | 支持方式 | 你需要做什么 |
|---|---|---|
| 猎聘 | 公开接口，免登录 | 无需登录或配置招聘账号 |
| BOSS 直聘 / 智联招聘 | 浏览器，使用你的登录会话 | 在助手使用的浏览器里各登录一次，并设置求职期望 |
| 前程无忧 | 浏览器，登录后推荐更对口 | 建议在助手使用的浏览器里登录 |
| 其它招聘站 | 用 `/job-add-portal` 接入 | 有公开接口就接搜索 CLI；要登录或遇反爬就走浏览器，不是接不了 |

WorkBuddy 的浏览器与日常浏览器独立，需要在里面登录招聘站。没有可用浏览器时，后三家退到 `site:` 网络搜索，岗位信息会少一些；每轮会说明实际使用了哪些渠道。各工具的登录态差异见 [浏览器渠道说明](workflows/reference/cdp-portals.md)。

## 能做什么

- **找岗并排序**：跨轮去重，先筛硬性条件，再比较技能、薪资、工作强度与发展；不确定的信息单独列出。
- **备好投递材料**：逐岗生成评估、打招呼开场白、邮件正文和网申自评，区分猎头与 HR 直招；需要时再出求职信。
- **审简历与按需定制**：日常发主简历，特殊岗位用 `/job-cv <公司>` 出定制版；材料里的经历和数字必须有资料依据。
- **在总览页管理进度**：筛选岗位、复制开场白，点「我投了 / 约面了 / 挂了」写回记录，可撤销；也能看回复率和拒绝原因。
- **准备后续环节**：按公司准备笔试与面试、模拟问答、谈薪和背调；从岗位要求里找技能差距，给出学习计划。

## 快速开始

### 1. 下载仓库，用你的 AI 工具打开

```bash
git clone https://github.com/rockbenben/ai-job-search-cn.git
cd ai-job-search-cn
```

在 WorkBuddy 或 Codex 桌面版里打开这个文件夹；使用命令行工具时，从这个目录启动。工作流和你的资料都在这里。

### 2. 填资料，拿到第一批岗位和话术

下面的命令输入 **AI 工具的对话框**，不是系统终端。Codex 用户按上表去掉斜杠。

| 日常命令 | 会得到什么 |
|---|---|
| `/job-setup` | 分四轮填写资料。第一轮填城市和岗位关键词，答完就能搜岗；后续补经历、薪资和偏好后继续评分、出材料 |
| `/job-auto` | 自动搜岗 → 评分 → 给可以投的岗位备材料，直到连续两轮找不到新岗位或达到轮次上限；可用 `--target 20` 限定目标数量 |
| `/job-outcome <公司>` | 投递后记结果：约面了、挂了、没下文或拿到 offer |

**材料备好后，由你去招聘网站发送。** 之后重复「`/job-auto` 补充岗位 → 自己发 → `/job-outcome <公司>` 记结果」即可。

第一次跑完，你会看到有理由的岗位排序和逐岗材料，保存在 `users/<你的名字>/documents/applications/<公司>_<岗位>/`。资料没填齐时，助手会说明当前能完成哪一步，只补问这一步缺的信息。

**有简历就先用现成的。** 运行 `/job-setup` 建好用户后，把简历放进 `users/<你的名字>/documents/cv/`（当前用户名见 `.active_user`），再运行 `/job-setup` 让助手读取并补齐资料。推荐 PDF，也支持 `.md`、`.txt`、`.tex`；Word（`.doc` / `.docx`）请先另存为 PDF。没有简历也能直接问答建档。

简历照片可选，放在你自己的简历目录 `users/<你的名字>/resume/`，不要放仓库根的 `resume/`。照片启用与格式要求见 [SETUP.md](SETUP.md)，证书、推荐信等材料的放法见 [文档目录说明](documents/README.md)。

### 3. 按需要补装

缺少可选依赖时，助手会说明少了哪部分，其余流程继续。

| 想用的功能 | 额外准备 | 没装时 |
|---|---|---|
| 求职总览页 `/job-dashboard` | Python 3.10+；首次在 `web/` 目录执行 `npm install && npm run build` | 直接查看生成的 Markdown 材料 |
| 中文简历 PDF | [Typst](https://typst.app) 0.13+ | 交付 `.typ` 源文件 |
| PDF 文本层校验 | poppler 提供的 `pdftotext` | 跳过校验并说明 |
| Gmail 同步 / Notion 看板 | 对应连接器 | 跳过对应同步功能 |

Python 还支持环境自检、搜索记录和评分预筛等辅助步骤；没装也能搜岗、评分和出话术。已有 Python 时，在终端运行 `python tools/doctor.py`，它会检查当前环境与进度，并给出一条下一步命令。

## 按场景使用

| 你的情况 | 输入什么 |
|---|---|
| 猎头或 HR 发来一个岗位 | `/job-apply <职位链接>`，也可以在命令后粘贴整段职位描述，只评这一个岗 |
| 想先审主简历 | `/job-resume`，核对经历、数字和结构，只报问题 |
| 想看岗位和投递进度 | `/job-dashboard`，启动本机总览页，默认端口 29029 |
| 约到面试 | `/job-interview <公司>`，准备该公司各轮面试，也可模拟问答 |
| 拿到 offer | `/job-offer <公司>`，比较薪资与选择，准备谈薪和背调 |
| 想知道该补什么技能 | `/job-upskill`，汇总评过的岗位要求与自己的差距 |
| 多人共用仓库或切换求职者 | `/job-user`，查看、切换或新建用户 |

总览页可以直接点按钮改投递状态；要补充面试经过、拒绝原因或复盘，用 `/job-outcome <公司>`。投过的公司会在其它岗位上标记「这家投过」，是否继续投由你决定。

`/job-rank`、`/job-outcome`、`/job-gmail-sync`、`/job-interview`、`/job-user`、`/job-cv`、`/job-reset`、`/job-scrape --no-rank` 收尾刷新面板数据，无需手工导出。

还有简历刷新、经历补充、模板切换等功能，见 [全部命令与参数](workflows/INDEX.md)。

## 你的数据在哪

> [!NOTE]
> 个人资料和投递材料保存在本机 `users/<你的名字>/`，该目录整体被 `.gitignore` 忽略。AI 处理资料时仍遵循你所用工具及模型服务的数据政策，不能据此理解为完全离线。

| 数据 | 保存位置 |
|---|---|
| 身份、薪资、教育与经历 | `users/<你>/profile/` |
| 岗位归档、评估与投递话术 | `users/<你>/documents/applications/` |
| 主简历与求职信 | `users/<你>/resume/`、`users/<你>/cover_letter/` |
| 投递记录 | `users/<你>/job_search_tracker.csv` |

仓库只带占位模板，真实资料在首次建档时生成。多人数据按目录分开，**同一操作系统账号下仍能互相读取明文文件**；需要保密时，请使用不同系统账号或各自下载一份仓库。

职位描述按不可信内容处理：其中的「发简历到某邮箱」「上传到某网站」不能作为发送你个人数据的授权。投递只走你自己确认过的正规渠道，详见 [安全说明](SECURITY.md)。

## 使用限制

- 仅供个人求职使用，请低频访问招聘站，遵守站点规则；浏览器渠道使用你的账号，有账号风控风险。遇到验证码由你处理，助手继续其它可用渠道。
- 招聘站可能限流、要求登录或下线岗位。评分依据当时拿到的信息，不保证岗位持续有效，也不能代替你核实劳动关系、薪资和工作强度。
- `/job-apply` 默认使用主简历，不自动给每个岗重做简历。需要定制时运行 `/job-cv <公司>`；助手不会代发邮件或提交投递表单。
- 部分辅助流程的真实使用验证仍有限：截至 2026-10-14，Gmail 同步、投后 HTML 分析、模板切换和 offer 评估尚无完整实跑产出，面试准备样本也较少。有自动化检查，但仍欢迎反馈实际问题。

## 只想用猎聘搜索 CLI？

搜索工具可以脱离整套工作流使用：Node 22.18+ 即可，无需 AI 工具、Bun、安装依赖或编译。

```bash
# 搜索职位
node .agents/skills/liepin-search/cli/src/cli.ts search -q "后端开发" -l "北京" --format table

# 读取职位详情
node .agents/skills/liepin-search/cli/src/cli.ts detail "<职位URL>" --format plain
```

输出包含职位、公司、薪资、学历、年限和是否猎头等字段，内置限速与退避。接口说明见 [url-reference.md](.agents/skills/liepin-search/url-reference.md)；只有修改 CLI 和运行其测试才需要 Bun。

## 文档

- [安装指南](SETUP.md)：依赖安装、简历模板与浏览器配置
- [全部工作流](workflows/INDEX.md)：命令、参数和默认行为
- [工具接入说明](docs/tool-entries.md)：WorkBuddy、Claude Code、Codex 等工具的能力差异
- [总览页说明](web/README.md)：页面操作与本机运行方式
- [AGENTS.md](AGENTS.md)：工作区规则，供 AI 工具读取
- [CONTRIBUTING.md](CONTRIBUTING.md)：开发、检查与贡献说明
- [SECURITY.md](SECURITY.md)：安全模型与漏洞报告

## 许可

采用 [MIT 许可](LICENSE)，保留两方版权声明。派生自 [MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search)，部分安全守卫、技能校验、PDF 校验及测试保留上游代码，其余按国内求职场景重写。

## 关于 365 开源计划

[365 开源计划](https://github.com/rockbenben/365opensource) 的第 **#029** 个项目——一个人 + AI，一年 300+ 个开源项目。

[提交你的需求 →](https://365.aishort.top/) · [Discord](https://discord.gg/PZTQfJ4GjX) · [Telegram](https://t.me/aishort_top)
