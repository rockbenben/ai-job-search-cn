---
name: job-upskill
description: >
  算能力差距：你评过的岗都在要什么，你缺哪几项
  不给参数时：汇总模式：拿所有评过分的岗一起算（新用户也有语料）；--applied 换成只算真投出去的那批；给一个岗的链接就只看那一个
  触发词：我该学什么、能力差距、差在哪、学习计划、补短板、skill gaps、upskill、/job-upskill
allowed-tools: Read, Glob, Grep, WebFetch, WebSearch, Edit, Write, AskUserQuestion, Agent, Bash(python tools/applied_jds.py:*), Bash(python tools/gap_split.py:*)
---

<!-- 由 tools/gen_entries.py 生成：改 workflows/INDEX.md 或 tools/_entries.py，别改这里 -->

# job-upskill（壳）

读取并严格执行 `workflows/job-upskill.md`。
`allowed-tools` 是支持该字段的宿主使用的权限声明；其它宿主按当前会话实际工具与权限执行，不把工具别名差异当成能力缺失。

用户在这条命令后面给的内容（链接、公司名、方向词、整段职位描述）原样带进工作流。
个人数据路径（`profile/…`、`documents/…`、`resume/main.typ` 这类）在这条命令里一律指活动用户目录 `users/<活动用户>/` 下的那一份，解析规则见 `AGENTS.md`「活动用户与多用户」。
裸命令的行为：汇总模式：拿所有评过分的岗一起算（新用户也有语料）；--applied 换成只算真投出去的那批；给一个岗的链接就只看那一个。
