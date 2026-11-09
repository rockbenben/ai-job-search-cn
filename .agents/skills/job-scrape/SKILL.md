---
name: job-scrape
description: >
  抓新岗并自动评分：抓完直接排出可以投的，不停在「待评」
  不给参数时：全部方向都抓一轮（按实测产出剪掉挖空的词），抓完自动评分
  触发词：找职位、找新岗、抓职位、有没有新岗位、搜岗、find jobs、job scrape、/job-scrape
allowed-tools: Read, Glob, Grep, WebFetch, WebSearch, Edit, Write, AskUserQuestion, Agent, Bash(python tools/portal_budget.py:*), Bash(node --version), Bash(python tools/jd_store.py:*), Bash(python tools/ingest.py:*), Bash(python tools/query_yield.py:*), Bash(node .agents/skills/liepin-search/cli/src/cli.ts:*), Bash(bun run .agents/skills/liepin-search/cli/src/cli.ts:*), Bash(agent-browser:*), Bash(python tools/doctor.py:*), Bash(python tools/export_web_data.py:*), Bash(bun --version)
---

<!-- 由 tools/gen_entries.py 生成：改 workflows/INDEX.md 或 tools/_entries.py，别改这里 -->

# job-scrape（壳）

读取并严格执行 `workflows/job-scrape.md`。
`allowed-tools` 是支持该字段的宿主使用的权限声明；其它宿主按当前会话实际工具与权限执行，不把工具别名差异当成能力缺失。
涉及浏览器时，先按当前会话实际提供的工具自动选择，执行 `workflows/reference/cdp-portals.md`「执行时自动选择浏览器」；不要只查某一家扩展，也不要从工具名推断已有登录态。

用户在这条命令后面给的内容（链接、公司名、方向词、整段职位描述）原样带进工作流。
个人数据路径（`profile/…`、`documents/…`、`resume/main.typ` 这类）在这条命令里一律指活动用户目录 `users/<活动用户>/` 下的那一份，解析规则见 `AGENTS.md`「活动用户与多用户」。
裸命令的行为：全部方向都抓一轮（按实测产出剪掉挖空的词），抓完自动评分。
