# CLAUDE.md — Claude Code 特化入口

**先读并遵守 @AGENTS.md 的全部规则**——角色、活动用户与多用户解析、全局安全铁律、
能力对照表都在那里；21 条命令的索引表在 `workflows/INDEX.md`。本文件不复述。

以下仅为 Claude Code 特有的补充。

## 会话开始

**没有 Claude 特有的做法。** 规则在 `AGENTS.md`「会话开始：先跑自检，把「下一步」
告诉用户」那一节，本文件开头的 @AGENTS.md 已经把它载进来了。

> 这里原来抄了一份。抄件与正本**已经各自长出了对方没有的一条**：正本多「没有 Python
> 时怎么办」，抄件多「`.active_user` 指向的目录不存在时该引导 `/job-user`」。后者是
> 条中立规则，却只有读 CLAUDE.md 的工具看得到——**Codex / Gemini 那边整条丢了**。
> 现在它回到了正本里。
>
> 判据：一条规则如果换个 AI 工具照样成立，它就属于 `AGENTS.md`。CLAUDE.md 只留
> 「在 Claude Code 里这件事落在哪」——下面两节才是。

## Slash 命令与 skill 触发

- `.claude/skills/` 里的每个命令入口都是薄壳（与 `.agents/skills/` 下那份逐字相同，
  由 `tools/gen_entries.py` 生成），一律读取并严格执行对应的 `workflows/<名>.md`。
  原来的 `.claude/commands/` 命令 stub 已整体删除——**入口只有壳这一种形态，
  而每个壳都带 frontmatter**。
- **每个壳都带触发词**（自动触发），正文同在 `workflows/`，壳只负责触发与
  `allowed-tools` 权限。生成的那些由 `tools/gen_entries.py` 落，各族逐字相同；只有
  `job-application-assistant`（求职咨询语境那束宽词）是**手写**的，
  改了它必须各族同步 —— 它不走生成器，没人替你兜。
- **壳上的 `allowed-tools` 要盖得住它那份工作流。** 每个入口都是壳、每个壳都有
  frontmatter，所以工作流里要在 shell 里跑的命令没写进那行 `allowed-tools` 就够不着。
  实测栽过：`job-upskill` 的工作流写着「用工具分，别手数」，而壳里一条 `Bash` 都没有。
  改工作流时顺手看一眼壳；写法与判据见 `CONTRIBUTING.md`「改技能壳」。

## 能力对照表的 Claude 侧落点

- Gmail 读取 → `mcp__claude_ai_Gmail__*`（claude.ai Settings → Connectors → Gmail）
- Notion 写入 → Notion MCP（OAuth）
- 浏览器取数与页面操作（含登录态） → **先用 Claude 浏览器扩展**
  （`mcp__claude-in-chrome__*`：`tabs_context_mcp` 拿标签页上下文、`navigate`、
  `computer` 点击/输入/截图、`read_page` 读可达性树）。它驱动的就是用户自己那个
  已登录的 Chrome，登录态天然带着，用户不必再装第三方东西。
  **只有扩展不可用或够不着时**，才退到 `web-access` skill 的 CDP 代理
  （第三方全局技能，本项目不附带，自管代理与封号风险提示）。
  两者都没有 → `site:` 域名限定搜索兜底。
  ⚠️ 但**先看平台有没有公开 API**（猎聘就有，走它的 CLI 比读页面干净得多）——
  完整顺位见 `AGENTS.md`「取数渠道的顺位」，浏览器只是其中的第 2、3 层。

## 产出内容规则

- outreach 文案或简历里提及 agentic coding / AI 工具时，明确点名 **Claude Code**。
