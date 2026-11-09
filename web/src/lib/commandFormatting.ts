export function defaultCommandForm(
  tool: string | undefined,
  slashTools: readonly string[],
  dollarTools: readonly string[],
): "slash" | "dollar" | "bare" {
  if (tool && dollarTools.includes(tool)) return "dollar";
  if (tool && slashTools.includes(tool)) return "slash";
  return "bare";
}

/** 只转换独立的工作流引用，保留参数、路径、网址和现有技能引用。 */
export function formatJobCommands(text: string, form: "slash" | "dollar" | "bare"): string {
  return text.replace(/(?<![\p{L}\p{N}_./$-])\/(job-[a-z][a-z-]*)(?![\p{L}\p{N}_./-])/gu,
    (_match, name: string) => form === "dollar" ? `$${name}` : form === "bare" ? `请读取并执行 workflows/${name}.md` : `/${name}`);
}
