# Codex 在本项目中怎么用

直接在 Codex 打开仓库即可。规则入口是根目录 `AGENTS.md`，技能从 `.agents/skills/`
自动发现，流程正文在 `workflows/`；不用再复制一套 `.codex/skills/`，也不需要安装
Claude Code。依据：[OpenAI 官方技能文档](https://learn.chatgpt.com/docs/build-skills)。

## 命令与执行

在 Codex **对话框**输入 `$job-auto` 就能抓岗、评分、备材料；这些是给 AI 的请求，
不是 PowerShell 或 Bash 命令。也可以直接说「帮我抓一轮新岗位并准备材料」。
文档正本保留 `/job-*`，总览与自检在 Codex 下复制为 `$job-*` 技能引用，参数原样保留。

| 环境 | 调用方式 |
|---|---|
| 桌面版 | `$job-setup`；也可输入 `/` 从菜单选择已启用技能 |
| CLI / IDE | `$job-setup`；也可输入 `/skills` 选择技能 |

CLI 能用斜杠菜单，但不能据此保证任意 `/job-setup` 都会自动注册成内置命令。
旧版 `/prompts:名称` 自定义命令已弃用，不作为本项目默认入口，不额外安装全局副本。
裸写 `job-setup` 是自然语言请求，不是显式技能引用。`$` 只作为 Codex 各端的默认，
不是所有 coding 工具的通用语法。未识别宿主时，项目给完整自然语言请求
（如「请读取并执行 workflows/job-auto.md」），前提是助手能读取本地项目。
依据（2026-11-09）：[桌面斜杠菜单](https://learn.chatgpt.com/docs/app/slash-commands)、
[技能调用](https://learn.chatgpt.com/docs/build-skills)、
[旧自定义命令](https://learn.chatgpt.com/docs/custom-prompts)。

- 自检与总览数据会用非空 `CODEX_THREAD_ID` / `CODEX_SESSION_ID` 识别 Codex。
  这两个标记于 2026-11-09 在本项目的 Codex 桌面会话中实测；缺标记的旧环境仍可用
  `JOBS_CODE_TOOL=codex` 覆盖。它们不能证明浏览器已连接。
- 技能壳中的 `Read`、`Bash`、`Agent` 等是其它宿主的工具名。Codex 用当前会话的文件、
  终端、提问与子代理能力完成同一件事；`allowed-tools` 不替代 Codex 自身权限。
- 用户已明确要求抓岗、评估、出材料时，直接转入对应工作流。不因从咨询进入而要求用户
  再输入一次命令。是否真能执行，以当前会话工具和权限为准。
- Windows 下按当前 shell 使用 PowerShell 语法；读写中文文件明确指定 UTF-8。
  子代理仅在用户或对应工作流要求时使用；共享个人数据由主会话写。
- 改框架时只读必要的个人资料，不把它们带进测试、日志、提交和联网请求。

## 浏览器按会话适配

需要网页交互时，执行 `workflows/reference/cdp-portals.md`「执行时自动选择浏览器」。
Codex 桌面版可能提供内置浏览器或电脑操作能力；CLI / IDE 可能连接浏览器工具。
两者都必须先看当前会话实际暴露了什么，不能只找 Claude 扩展，不能假定已登录。

本次会话实际提供了 `mcp__cua_repl` 和 `mcp__chrome_devtools`。这是会话取证，
不是所有 Codex 安装都会提供的保证。工具有延迟发现入口时先检索并读取接口说明；
使用工具规定的初始化方式，不自行拼接调试端口或编造调用。

2026-11-09 实际验证：Chrome DevTools 工具能被发现，但连接未建立；随后使用桌面
浏览器成功打开并读取了 OpenAI 官方技能文档。工具存在与连接可用分别检查，一条
连接失败不会把同轮可用的桌面浏览器一起判掉。

平台公开 API → 工具自带的浏览器能力（含已连接的浏览器工具）→ `web-access` →
`site:` 兜底的顺序保持不变。外部技能的适用范围不能把浏览器强制降到代理路径。
浏览器自己的域名授权被挡住时请用户授权；验证码由用户亲手处理，其他渠道继续跑。

## 修改后的检查

命令入口从 `workflows/INDEX.md` 与 `tools/_entries.py` 生成。改了正本运行
`python tools/gen_entries.py`，不要只修改某一族技能壳。
生成检查用 `python tools/gen_entries.py --check`，完整 Python 检查用
`python -m unittest discover -s tests -t .`。

本文件是 Codex 的工具映射补充，个人数据、渠道顺序、投递边界以 `AGENTS.md` 为准。
