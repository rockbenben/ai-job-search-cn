import { createContext, useContext, useState, useEffect, type ReactNode } from "react";
import { defaultCommandForm, formatJobCommands } from "../lib/commandFormatting";

const KNOWN_TOOLS = [
  "antigravity", "claude", "cursor", "codex", "mavis", "mimo", "qoder", "qwen", "workbuddy", "generic",
] as const;
export type CodeTool = (typeof KNOWN_TOOLS)[number];

const SLASH_TOOLS: readonly CodeTool[] = [
  "antigravity", "claude", "cursor", "mavis", "mimo", "qoder", "qwen", "workbuddy",
];

const DOLLAR_TOOLS: readonly CodeTool[] = ["codex"];

// 旧版二选一设置不再覆盖新的自动适配。
const STORAGE_KEY = "job_search_command_form_v2";
export type CommandMode = "auto" | "slash" | "dollar" | "bare";

function asKnownTool(v: unknown): CodeTool | null {
  return typeof v === "string" && (KNOWN_TOOLS as readonly string[]).includes(v)
    ? (v as CodeTool)
    : null;
}

interface CodeToolContextType {
  commandMode: CommandMode;
  setCommandMode: (mode: CommandMode) => void;
  formatCommand: (cmd: string) => string;
}

const CodeToolContext = createContext<CodeToolContextType>({
  commandMode: "auto",
  setCommandMode: () => {},
  formatCommand: (cmd) => formatJobCommands(cmd, "bare"),
});

function readStoredMode(): CommandMode {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "slash" || saved === "dollar" || saved === "bare") return saved;
  } catch { /* 存储受限时仍可自动适配 */ }
  return "auto";
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
  const [mode, setMode] = useState<CommandMode>(readStoredMode);

  // 服务端探测结果变了（换了终端工具 / 起服务的环境变了）就跟过去；
  // 用户手选过哪一档是另一件事，它只走下面那个 effect，两者互不覆盖。
  useEffect(() => {
    const detected = asKnownTool(initialTool);
    if (detected) setTool(detected);
  }, [initialTool]);
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, mode);
    } catch {
      // 存不住不影响本次会话
    }
  }, [mode]);

  const form = mode === "auto"
    ? defaultCommandForm(tool, SLASH_TOOLS, DOLLAR_TOOLS)
    : mode;
  const formatCommand = (cmd: string) => formatJobCommands(cmd, form);

  return (
    <CodeToolContext.Provider
      value={{ commandMode: mode, setCommandMode: setMode, formatCommand }}
    >
      {children}
    </CodeToolContext.Provider>
  );
}

export function useCodeTool() {
  return useContext(CodeToolContext);
}
