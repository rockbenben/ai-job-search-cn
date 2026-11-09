import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile, readdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve, join } from "node:path";
import { test } from "node:test";
import { build } from "vite";

test("production build excludes legacy personal public files", async () => {
  const root = await mkdtemp(join(tmpdir(), "job-private-build-"));
  try {
    await mkdir(join(root, "public/pdf"), { recursive: true });
    await writeFile(join(root, "public/data.json"), '{"private":"fixture"}');
    await writeFile(join(root, "public/pdf/resume.pdf"), "fixture");
    await writeFile(join(root, "index.html"), "<html><head></head></html>");
    await build({ configFile: resolve("vite.config.ts"), root, logLevel: "silent" });
    assert.deepEqual(await readdir(join(root, "dist")), ["index.html"]);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
