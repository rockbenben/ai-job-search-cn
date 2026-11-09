---
name: job-expand
description: >
  从你的文档和公开主页里，挖还没写进资料的经历
  不给参数时：扫 documents/ 下的简历、领英导出、学历证明、推荐信这四类，加上资料里的公开主页链接（postings/ 里的职位描述不扫——那是别人写的，不是你的经历）；找到的先列出来给你确认，不直接写进资料
  触发词：挖我的经历、还有什么没写进资料、翻我的文档、expand profile
allowed-tools: Read, Glob, Grep, WebFetch, WebSearch, Edit, Write, AskUserQuestion, Agent
---

<!-- 由 tools/gen_entries.py 生成：改 workflows/INDEX.md 或 tools/_entries.py，别改这里 -->

# job-expand（壳）

读取并严格执行 `workflows/job-expand.md`。
`allowed-tools` 是支持该字段的宿主使用的权限声明；其它宿主按当前会话实际工具与权限执行，不把工具别名差异当成能力缺失。

用户在这条命令后面给的内容（链接、公司名、方向词、整段职位描述）原样带进工作流。
个人数据路径（`profile/…`、`documents/…`、`resume/main.typ` 这类）在这条命令里一律指活动用户目录 `users/<活动用户>/` 下的那一份，解析规则见 `AGENTS.md`「活动用户与多用户」。
裸命令的行为：扫 documents/ 下的简历、领英导出、学历证明、推荐信这四类，加上资料里的公开主页链接（postings/ 里的职位描述不扫——那是别人写的，不是你的经历）；找到的先列出来给你确认，不直接写进资料。
