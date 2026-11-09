---
name: job-resume
description: >
  审一遍你的主简历，只报问题、不改你的数字
  不给参数时：审主简历 resume/main.typ，不是某次投递的定制版；还会对一遍你在招聘网站上那份在线简历（HR 主动搜的是它）。只出报告，一个字不改
  触发词：看看我简历、审一遍简历、简历有什么问题、resume review
allowed-tools: Read, Glob, Grep, WebFetch, WebSearch, Edit, Write, AskUserQuestion, Agent, Bash(typst:*), Bash(pdftotext:*), Bash(agent-browser:*)
---

<!-- 由 tools/gen_entries.py 生成：改 workflows/INDEX.md 或 tools/_entries.py，别改这里 -->

# job-resume（壳）

读取并严格执行 `workflows/job-resume.md`。
`allowed-tools` 是支持该字段的宿主使用的权限声明；其它宿主按当前会话实际工具与权限执行，不把工具别名差异当成能力缺失。
涉及浏览器时，先按当前会话实际提供的工具自动选择，执行 `workflows/reference/cdp-portals.md`「执行时自动选择浏览器」；不要只查某一家扩展，也不要从工具名推断已有登录态。

用户在这条命令后面给的内容（链接、公司名、方向词、整段职位描述）原样带进工作流。
个人数据路径（`profile/…`、`documents/…`、`resume/main.typ` 这类）在这条命令里一律指活动用户目录 `users/<活动用户>/` 下的那一份，解析规则见 `AGENTS.md`「活动用户与多用户」。
裸命令的行为：审主简历 resume/main.typ，不是某次投递的定制版；还会对一遍你在招聘网站上那份在线简历（HR 主动搜的是它）。只出报告，一个字不改。
