---
name: job-auto
description: >
  一条命令跑完：抓岗 → 评分 → 出材料，一直跑到挖不动为止
  不给参数时：不设目标个数，跑到挖不动为止（连续两轮抓不到新的、或满 20 轮就停）
  触发词：自动跑一轮、一条龙跑完、全都跑了、job auto
allowed-tools: Read, Glob, Grep, WebFetch, WebSearch, Edit, Write, AskUserQuestion, Agent, Bash(python tools/stale_materials.py:*), Bash(python tools/audit_pipeline.py:*), Bash(python tools/check_outreach.py:*), Bash(python tools/export_web_data.py:*), Bash(python tools/writeback.py:*), Bash(python tools/archive.py:*), Bash(python tools/outreach_header.py:*), Bash(python tools/trim_opening.py:*), Bash(python tools/serve.py:*), Bash(python tools/doctor.py:*), Bash(agent-browser:*), Bash(python tools/query_yield.py:*), Bash(python tools/portal_budget.py:*), Bash(python tools/jd_store.py:*)
---

<!-- 由 tools/gen_entries.py 生成：改 workflows/INDEX.md 或 tools/_entries.py，别改这里 -->

# job-auto（壳）

读取并严格执行 `workflows/job-auto.md`。
`allowed-tools` 是支持该字段的宿主使用的权限声明；其它宿主按当前会话实际工具与权限执行，不把工具别名差异当成能力缺失。
涉及浏览器时，先按当前会话实际提供的工具自动选择，执行 `workflows/reference/cdp-portals.md`「执行时自动选择浏览器」；不要只查某一家扩展，也不要从工具名推断已有登录态。

用户在这条命令后面给的内容（链接、公司名、方向词、整段职位描述）原样带进工作流。
个人数据路径（`profile/…`、`documents/…`、`resume/main.typ` 这类）在这条命令里一律指活动用户目录 `users/<活动用户>/` 下的那一份，解析规则见 `AGENTS.md`「活动用户与多用户」。
裸命令的行为：不设目标个数，跑到挖不动为止（连续两轮抓不到新的、或满 20 轮就停）。
