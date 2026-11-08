---
name: job-rank
description: >
  给抓到还没评的岗批量打分，排出可以投的
  不给参数时：把还没评的全部评完，分批循环直到队列排空
  触发词：给这些岗打分、排个序、哪个岗值得投、评一评、job rank
allowed-tools: Read, Glob, Grep, WebFetch, WebSearch, Edit, Write, AskUserQuestion, Agent, Bash(python tools/fetch_details.py:*), Bash(python tools/jd_store.py:*), Bash(python tools/archive.py:*), Bash(python tools/writeback.py:*), Bash(python tools/prescreen.py:*), Bash(python tools/score.py:*), Bash(python tools/audit_pipeline.py:*), Bash(python tools/export_web_data.py:*), Bash(python tools/validate_evaluations.py:*)
---

<!-- 由 tools/gen_entries.py 生成：改 workflows/INDEX.md 或 tools/_entries.py，别改这里 -->

# job-rank（壳）

读取并严格执行 `workflows/job-rank.md`。

用户在这条命令后面给的内容（链接、公司名、方向词、整段职位描述）原样带进工作流。
个人数据路径（`profile/…`、`documents/…`、`resume/main.typ` 这类）在这条命令里一律指活动用户目录 `users/<活动用户>/` 下的那一份，解析规则见 `AGENTS.md`「活动用户与多用户」。
裸命令的行为：把还没评的全部评完，分批循环直到队列排空。
