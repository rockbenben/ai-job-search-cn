---
name: job-dashboard
description: >
  打开这一页（在本机起服务，数据不出这台机器）
  不给参数时：服务当前用户的数据，端口 29029，起完自动打开浏览器
  触发词：打开总览页、看面板、打开这一页、open dashboard
allowed-tools: Read, Glob, Grep, WebFetch, WebSearch, Edit, Write, AskUserQuestion, Agent, Bash(python tools/serve.py:*)
---

<!-- 由 tools/gen_entries.py 生成：改 workflows/INDEX.md 或 tools/_entries.py，别改这里 -->

# job-dashboard（壳）

读取并严格执行 `workflows/job-dashboard.md`。
`allowed-tools` 是支持该字段的宿主使用的权限声明；其它宿主按当前会话实际工具与权限执行，不把工具别名差异当成能力缺失。

用户在这条命令后面给的内容（链接、公司名、方向词、整段职位描述）原样带进工作流。
个人数据路径（`profile/…`、`documents/…`、`resume/main.typ` 这类）在这条命令里一律指活动用户目录 `users/<活动用户>/` 下的那一份，解析规则见 `AGENTS.md`「活动用户与多用户」。
裸命令的行为：服务当前用户的数据，端口 29029，起完自动打开浏览器。
