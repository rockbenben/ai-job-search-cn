---
name: job-refresh
description: >
  把在线简历刷一遍，让 HR 搜得到你（一天一次）
  不给参数时：网页刷得了的那几家全刷一遍；今天刷过的会跳过，网页没有刷新按钮的（BOSS、前程无忧）如实告诉你要开 APP
  触发词：刷一下简历、刷新在线简历、让 HR 搜到我、refresh resume
allowed-tools: Read, Glob, Grep, WebFetch, WebSearch, Edit, Write, AskUserQuestion, Agent, Bash(python tools/resume_refresh.py:*), Bash(python tools/export_web_data.py:*), Bash(agent-browser:*)
---

<!-- 由 tools/gen_entries.py 生成：改 workflows/INDEX.md 或 tools/_entries.py，别改这里 -->

# job-refresh（壳）

读取并严格执行 `workflows/job-refresh.md`。
`allowed-tools` 是支持该字段的宿主使用的权限声明；其它宿主按当前会话实际工具与权限执行，不把工具别名差异当成能力缺失。
涉及浏览器时，先按当前会话实际提供的工具自动选择，执行 `workflows/reference/cdp-portals.md`「执行时自动选择浏览器」；不要只查某一家扩展，也不要从工具名推断已有登录态。

用户在这条命令后面给的内容（链接、公司名、方向词、整段职位描述）原样带进工作流。
个人数据路径（`profile/…`、`documents/…`、`resume/main.typ` 这类）在这条命令里一律指活动用户目录 `users/<活动用户>/` 下的那一份，解析规则见 `AGENTS.md`「活动用户与多用户」。
裸命令的行为：网页刷得了的那几家全刷一遍；今天刷过的会跳过，网页没有刷新按钮的（BOSS、前程无忧）如实告诉你要开 APP。
