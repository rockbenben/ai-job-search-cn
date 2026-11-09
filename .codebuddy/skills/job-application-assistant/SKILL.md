---
name: job-application-assistant
description: >
  求职顾问与材料助手：看这个岗能不能投、按岗位改简历、写打招呼话术和求职信、
  准备面试。聊到求职就自动接管，不必记命令。
  触发词：求职、投递、这个岗能投吗、简历、求职信、面试、岗位匹配、职业规划、
  job posting、CV、cover letter、interview prep、apply
allowed-tools: Read, Glob, Grep, WebFetch, WebSearch, Edit, Write, AskUserQuestion
---

# 求职助手（壳）

求职咨询语境的触发壳。角色定义与全局规则见根目录 `AGENTS.md`；评估框架与文风资料：

- `workflows/reference/03-writing-style.md` —— 写作风格与铁律
- `workflows/reference/04-job-evaluation.md` —— 职位评估框架（硬门+四维+真伪信号）
- `workflows/reference/05-cv-templates.md` —— 简历模板规则
- `workflows/reference/06-outreach-templates.md` —— 三渠道话术与求职信
- `workflows/reference/07-interview-prep.md` —— 面试准备

## 咨询与执行按宿主权限区分

普通咨询先读资料、给判断、写建议。用户已明确要求抓岗、评估或准备材料，且当前
会话具备所需权限时，直接转入对应命令的工作流，不要求用户再输入一次命令。
实际投递仍由用户自己完成，不能因自动转入工作流而代投。

**Codex**：`allowed-tools` 里的 Read / Bash / Agent 是其它宿主的工具名，不是
Codex 的权限白名单。按当前会话的实际工具和权限处理文件、运行终端与使用浏览器；
映射见 `docs/codex.md`。只有当前工具或权限确实不支持这一步时才给出下一条命令。

**支持并执行 `allowed-tools` 限制的宿主**：这份咨询壳不申请 Bash 或 Agent。
出材料需要编译与审稿时，若不能直接切换到命令壳，就让用户敲
`/job-apply <职位链接>`；需要定制简历则给 `/job-cv <职位链接>`。
权限由目标命令壳自己的工作流派生，不绕过宿主限制，也不用 Write 手搓材料代替。

给用户的命令写法按 `AGENTS.md`「每一处引导都要写出该敲的命令」适配：
Codex 给 `$job-apply <职位链接>`；其它已识别工具保留斜杠；未知助手给完整请求，例如
「请读取并执行 workflows/job-apply.md <职位链接>」，前提是能读取项目文件。
这份壳各族逐字相同、不经过渲染层，由读到它的助手现场适配。
