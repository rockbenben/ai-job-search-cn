import { test } from "node:test";
import assert from "node:assert/strict";
import { defaultCommandForm, formatJobCommands } from "../src/lib/commandFormatting.ts";

test("未识别、缺失和拼错的宿主都回退到完整自然语言请求", () => {
  for (const tool of [undefined, "", "generic", "typo-codxe"]) {
    const form = defaultCommandForm(tool, ["claude"], ["codex"]);
    assert.equal(form, "bare");
    assert.equal(formatJobCommands("/job-apply <职位链接>", form),
      "请读取并执行 workflows/job-apply.md <职位链接>");
  }
  assert.equal(defaultCommandForm("codex", ["claude"], ["codex"]), "dollar");
  assert.equal(defaultCommandForm("claude", ["claude"], ["codex"]), "slash");
  assert.equal(defaultCommandForm("cursor", ["claude", "cursor"], ["codex"]), "slash");
});

test("复制多个技能引用时保留参数", () => {
  assert.equal(formatJobCommands("跑 /job-rank --all，再 /job-apply <职位链接>", "dollar"),
    "跑 $job-rank --all，再 $job-apply <职位链接>");
});
test("格式转换不修改路径、网址、已有技能引用及其它菜单命令", () => {
  const text = "workflows/job-apply.md https://example.com/job-auto $job-auto /skills 中文/job-auto";
  assert.equal(formatJobCommands(text, "dollar"), text);
  assert.equal(formatJobCommands(formatJobCommands("/job-auto", "dollar"), "dollar"), "$job-auto");
});
test("用户可选择斜杠或自然语言", () => {
  assert.equal(formatJobCommands("/job-auto", "slash"), "/job-auto");
  assert.equal(formatJobCommands("/job-auto", "bare"), "请读取并执行 workflows/job-auto.md");
});
