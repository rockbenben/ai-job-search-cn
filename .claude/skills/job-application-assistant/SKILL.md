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

## 这个壳自己做不了投递，到那一步要让用户敲命令

**它只做咨询**：读资料、给判断、写字。真要出材料那一步 —— 深评、定制简历、
编译 PDF、双角色审稿 —— **让用户敲 `/job-apply <职位链接>` 这条命令**（要定制简历是
`/job-cv <职位链接>`）。**开头那个斜杠给不给，由你此刻所在的工具定**：2026-09-30
逐家实测，Claude Code、Qoder、Antigravity (agy)、Qwen Code、MiMo Code、MCode **都吃斜杠**
（技能就注册成 `/<名>`，参数原样送到）；**要去掉斜杠的只有 Codex CLI** —— 它把开头的 `/`
留给自己的内置指令，在那儿给 `job-apply <职位链接>`，或直接把要办的事说成「投这个岗 <链接>」。
**认不出来的助手也照给带斜杠**（2026-10-13 改：逐家量过 12 家、8 家吃斜杠，认不出来的那一批
更可能落在吃斜杠的一边；理由与代价见 `docs/tool-entries.md` 表下第 2 条）——所以这段里的
`/job-apply` 在别处也不用改写。
判据在 `AGENTS.md`「每一处引导都要写出该敲的命令」——**这份壳两族逐字相同、
不经过渲染层**，所以那一步适配只能由读到它的你现场做，别照抄这里的字形。
命令本身归另外两个壳，权限由它们各自的工作流正文派生，与本壳无关。

**权限窄是有意的，不是漏了。** 这个壳是**聊到求职就自动接管**的，而
`workflows/job-apply.md` 的代码块里要跑四类命令（`typst compile`、`typst fonts`、
`pdftotext -layout -enc UTF-8`、渠道 CLI），还要起并行子代理做审稿 —— 上面那行
`allowed-tools` 里 **Bash 和 Agent 一个都没有**（2026-08-24 核过）。
一个凭一句话就自动接管的壳，手里不该攥着编译、写盘、起子代理这些能力；
**够不着不是缺陷，是这个壳的边界**。

所以到了那一步**别硬走**（照着工作流跑到一半撞权限，用户看到的是一堆失败的
命令），也别绕道用 `Write` 手搓一份材料 —— 直接把命令给他。判据同
`AGENTS.md`「每一处引导都要写出该敲的命令」。
