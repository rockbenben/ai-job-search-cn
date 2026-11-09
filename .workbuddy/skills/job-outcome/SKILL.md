---
name: job-outcome
description: >
  投完记一笔：约面了 / 挂了 / 没下文
  不给参数时：列出还在跑的投递，问你要改哪一个
  触发词：记一笔、约面了、挂了、没下文、log outcome
allowed-tools: Read, Glob, Grep, WebFetch, WebSearch, Edit, Write, AskUserQuestion, Agent, Bash(python tools/followups.py:*), Bash(python tools/export_web_data.py:*)
---

<!-- 由 tools/gen_entries.py 生成：改 workflows/INDEX.md 或 tools/_entries.py，别改这里 -->

# job-outcome <公司>（壳）

读取并严格执行 `workflows/job-outcome.md`。
`allowed-tools` 是支持该字段的宿主使用的权限声明；其它宿主按当前会话实际工具与权限执行，不把工具别名差异当成能力缺失。

用户在这条命令后面给的内容（链接、公司名、方向词、整段职位描述）原样带进工作流。
个人数据路径（`profile/…`、`documents/…`、`resume/main.typ` 这类）在这条命令里一律指活动用户目录 `users/<活动用户>/` 下的那一份，解析规则见 `AGENTS.md`「活动用户与多用户」。
裸命令的行为：列出还在跑的投递，问你要改哪一个。
