import { createContext, useContext, useState, useEffect, type ReactNode } from "react";

/**
 * 当前跑在哪个 AI 编码工具里，决定命令块显不显示开头的斜杠。
 *
 * 取值正本是 tools/_cli.py 的 detect_code_tool()，由导出快照带过来；
 * 「哪几家吃斜杠」的正本是 tools/doctor.py 的 COMMAND_SYNTAX，下面这份
 * SLASH_TOOLS 是它的**抄件** —— 跨语言、import 不到，所以由
 * `tests/test_slash_survives_where_the_palette_is_the_skill_list.py`
 * 的 ThePanelCarriesTheSameTable 逐格对拍（名单不等就红）。
 * 2026-09-29 / 09-30 逐家实测：Claude Code / Qoder / agy / Qwen Code / MiMo Code
 * 几家都吃斜杠（技能注册成 `/<名>`），只有 Codex CLI 把 `/` 留给自己的内置指令。
 * 2026-10-13 加 MCode（`MAVIS_SESSION_TRANSFER_CLIENT`，量出来的信号）。
 * Gemini CLI 原来在这一档，2026-09-30 整档删掉 —— 那家已停，后继是 agy。
 *
 * ## `generic` 2026-10-13 从免斜杠翻成带斜杠
 *
 * 原来「认不出来」被归到免斜杠那一档。**实测 `docs/tool-entries.md` 里量过
 * 12 家，8 家吃斜杠** —— 认不出来的那一批更可能落在吃斜杠的一边。
 * 而两种错法的可见性不同：带错斜杠，工具会报错或列出命令；缺斜杠，
 * 用户根本不知道有这条命令（`AGENTS.md`「用户不知道该敲什么」）。
 * 真拦的那一家（Codex）现在自己一格，不再靠 generic 兜底。
 * 理由的完整版在 `tools/doctor.py` 的 `COMMAND_SYNTAX` 上方。
 *
 * `cursor` 没给格子：吃不吃斜杠没实测过，让它落 generic（带斜杠）。
 */
const KNOWN_TOOLS = [
  "antigravity", "claude", "codex", "mavis", "mimo", "qoder", "qwen", "generic",
] as const;
export type CodeTool = (typeof KNOWN_TOOLS)[number];

/**
 * 这一档的命令带开头的斜杠。
 *
 * **只剩 Codex 免斜杠** —— 它的二进制里印着
 * `Unrecognized command '/-'. Type "/" for a list of supported commands.`。
 * 「认不出来」（`generic`）在这一档里：见上面那段与 doctor 的说明。
 */
const SLASH_TOOLS: readonly CodeTool[] = [
  "antigravity", "claude", "generic", "mavis", "mimo", "qoder", "qwen",
];

const STORAGE_KEY = "job_search_command_form";

function asKnownTool(v: unknown): CodeTool | null {
  return typeof v === "string" && (KNOWN_TOOLS as readonly string[]).includes(v)
    ? (v as CodeTool)
    : null;
}

interface CodeToolContextType {
  /** 用户手选过就是他的选择，否则跟着探测结果。 */
  isSlashMode: boolean;
  setSlashMode: (on: boolean) => void;
  formatCommand: (cmd: string) => string;
}

const CodeToolContext = createContext<CodeToolContextType>({
  isSlashMode: false,
  setSlashMode: () => {},
  formatCommand: (cmd) => (cmd.startsWith("/") ? cmd.slice(1) : cmd),
});

function readStoredMode(): boolean | null {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "slash") return true;
    if (saved === "no_slash") return false;
  } catch {
    // localStorage 用不了就按探测结果走
  }
  return null;
}

export function CodeToolProvider({
  initialTool,
  children,
}: {
  initialTool?: string;
  children: ReactNode;
}) {
  const [tool, setTool] = useState<CodeTool>(
    () => asKnownTool(initialTool) ?? "generic",
  );
  // 手选过的那一档单独存：它是「形式」的选择，不是「哪家工具」的选择。
  // 存成工具名的那份旧值（claude / generic）读出来认不出，自然回落到探测结果。
  const [mode, setMode] = useState<boolean | null>(readStoredMode);

  // 服务端探测结果变了（换了终端工具 / 起服务的环境变了）就跟过去；
  // 用户手选过哪一档是另一件事，它只走下面那个 effect，两者互不覆盖。
  useEffect(() => {
    const detected = asKnownTool(initialTool);
    if (detected) setTool(detected);
  }, [initialTool]);
  useEffect(() => {
    if (mode === null) return;
    try {
      localStorage.setItem(STORAGE_KEY, mode ? "slash" : "no_slash");
    } catch {
      // 存不住不影响本次会话
    }
  }, [mode]);

  const isSlashMode = mode ?? SLASH_TOOLS.includes(tool);

  const formatCommand = (cmd: string) => {
    if (!isSlashMode && cmd.startsWith("/")) {
      return cmd.slice(1);
    }
    return cmd;
  };

  return (
    <CodeToolContext.Provider
      value={{ isSlashMode, setSlashMode: setMode, formatCommand }}
    >
      {children}
    </CodeToolContext.Provider>
  );
}

export function useCodeTool() {
  return useContext(CodeToolContext);
}
