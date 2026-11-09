---
name: job-apply
description: >
  深评一个岗：核对硬性条件、逐项打分、出打招呼话术
  不给参数时：「可以投」这一档全部出深评 + 开场白，不限量
  触发词：投这个岗、深评一下、写个打招呼、开场白怎么说、write opener
allowed-tools: Read, Glob, Grep, WebFetch, WebSearch, Edit, Write, AskUserQuestion, Agent, Bash(node .agents/skills/liepin-search/cli/src/cli.ts:*), Bash(typst:*), Bash(pdftotext:*), Bash(bun run .agents/skills/liepin-search/cli/src/cli.ts:*), Bash(agent-browser:*)
---

<!-- 由 tools/gen_entries.py 生成：改 workflows/INDEX.md 或 tools/_entries.py，别改这里 -->

# job-apply <职位链接>（壳）

读取并严格执行 `workflows/job-apply.md`。
`allowed-tools` 是支持该字段的宿主使用的权限声明；其它宿主按当前会话实际工具与权限执行，不把工具别名差异当成能力缺失。
涉及浏览器时，先按当前会话实际提供的工具自动选择，执行 `workflows/reference/cdp-portals.md`「执行时自动选择浏览器」；不要只查某一家扩展，也不要从工具名推断已有登录态。

用户在这条命令后面给的内容（链接、公司名、方向词、整段职位描述）原样带进工作流。
个人数据路径（`profile/…`、`documents/…`、`resume/main.typ` 这类）在这条命令里一律指活动用户目录 `users/<活动用户>/` 下的那一份，解析规则见 `AGENTS.md`「活动用户与多用户」。
裸命令的行为：「可以投」这一档全部出深评 + 开场白，不限量。
