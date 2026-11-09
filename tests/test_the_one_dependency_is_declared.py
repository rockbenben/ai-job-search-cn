# -*- coding: utf-8 -*-
"""四个检查脚本里有一个要第三方包，而这件事只写在 CI 里。

README 与 SETUP 都写着「Python 3.10+（只用标准库）……仓库自带的**四个检查脚本**
也用它」，CONTRIBUTING 的「提交前必跑的三件」第一条就是 `python tools/lint_skills.py`
—— 而它 `import yaml`。全仓文档 grep 不到一次 PyYAML；唯一写下这件事的地方是
`.github/workflows/ci.yml` 的 `pip install pyyaml`。

也就是说：**新贡献者照着 CONTRIBUTING 敲，第一条就撞 `requires PyYAML`**，
而他刚被告知这里只用标准库。

## 为什么不去掉这个依赖

`lint_skills.py` 读的是 `SKILL.md` 的 YAML frontmatter，里面有折叠块标量
（`description: >` 接多行）。手写一个子集解析器不划算 —— 解析错了这个 lint 会
**静默放行**，比装一个包糟得多。所以修的是文档，不是代码。

## 这条守卫钉什么

1. 「只用标准库」这句话不许再盖住那个例外
2. 要敲的命令旁边就要有 `pip install pyyaml`。同一条道理写在
   `AGENTS.md` 的「每一处引导都要写出该敲的命令」那一节：知道要装，
   不等于知道敲什么。（**引用要留在同一行里** —— 节名被换行截断，
   `test_cross_references_resolve` 就查无此节。）
3. **例外只有这一个** —— 哪天别的 `tools/*.py` 也引入第三方包，这里要红
"""
import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

README = (ROOT / "README.md").read_text(encoding="utf-8")
SETUP = (ROOT / "SETUP.md").read_text(encoding="utf-8")
CONTRIB = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")


def _third_party_imports(path: Path) -> set:
    """这个文件 import 了哪些**非标准库、非本仓库**的模块。"""
    local = {p.stem for p in (ROOT / "tools").glob("*.py")}
    out = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.add(node.module.split(".")[0])
    return out - set(sys.stdlib_module_names) - local


class OnlyOneToolHasADependency(unittest.TestCase):
    def test_the_exception_is_exactly_lint_skills(self):
        bad = {p.name: sorted(_third_party_imports(p))
               for p in sorted((ROOT / "tools").glob("*.py"))
               if _third_party_imports(p)}
        self.assertEqual(bad, {"lint_skills.py": ["yaml"]},
                         "第三方依赖的分布变了 —— 文档里那句「只用标准库」要跟着改：\n"
                         f"  {bad}")

    def test_the_import_fails_loudly_with_the_fix(self):
        """缺包时要给出该敲的那条命令，不是一个 ImportError 栈。"""
        src = (ROOT / "tools" / "lint_skills.py").read_text(encoding="utf-8")
        i = src.index("import yaml")
        self.assertIn("except ImportError", src[i:i + 120])
        self.assertIn("pip install pyyaml", src[i:i + 250],
                      "报了缺包却不说怎么装")

    def test_doctor_stays_stdlib_only(self):
        """`doctor.py` 是「任何状态下都能跑」的那一个，它的承诺最硬。"""
        self.assertEqual(_third_party_imports(ROOT / "tools" / "doctor.py"), set())


class TheDocsSaySo(unittest.TestCase):
    def test_contributing_puts_the_install_next_to_the_command(self):
        i = CONTRIB.index("python tools/lint_skills.py")
        self.assertIn("pip install pyyaml", CONTRIB[max(0, i - 200):i],
                      "要敲的命令上方没有那条安装命令 —— 知道要装不等于知道敲什么")

    def test_readme_no_longer_covers_the_exception(self):
        paragraphs = [p for p in README.split("\n\n") if "lint_skills.py" in p]
        self.assertTrue(paragraphs, "README 缺少 lint_skills.py 的依赖说明")
        near = "\n".join(paragraphs)
        self.assertIn("pip install pyyaml", near,
                      f"README 还在拿「只用标准库」盖住那个例外：{near[:80]}")

    def test_setup_says_it_too(self):
        self.assertIn("pip install pyyaml", SETUP)
        self.assertIn("流水线全程只用标准库", SETUP,
                      "把例外说成常态了 —— 流水线那一半确实是零依赖，别一起否掉")

    def test_it_says_who_needs_it(self):
        """日常求职一条都用不到 —— 不说清楚，用户会以为自己也得装。"""
        self.assertIn("那是给贡献者跑的", SETUP)


class CIAndDocsAgree(unittest.TestCase):
    def test_ci_installs_exactly_what_the_docs_name(self):
        ci = (ROOT / ".github" / "workflows" / "ci.yml")
        if not ci.is_file():
            self.skipTest("没有 CI 配置")
        text = ci.read_text(encoding="utf-8")
        self.assertIn("pip install pyyaml", text)
        self.assertIn("python tools/lint_skills.py", text,
                      "CI 装了包却没跑那个脚本？那这条依赖就没有由头了")

    def test_every_job_that_runs_the_suite_installs_it(self):
        """**「文件里提过」不等于「要用它的那个 job 装了」。**

        上一条只查整份 ci.yml 里有没有那句话 —— 而 `pip install pyyaml` 当时
        只在 `lint` job 里，跑测试套件的 `python-tests` job 一个字都没有。
        套件会真的执行 `tools/lint_skills.py`（`test_cli_contract` 按
        `tools/*.py` 枚举跑 `--help`、`test_lint_skills` 直接调它），
        于是首次公开推送的 CI 当场 **7 error + 2 failure**，
        而同一份代码在装着 pyyaml 的开发机上全绿 ——
        **干净 clone 挡得住「文件少了」，挡不住「环境多了」。**

        这里按 job 逐个查，不解析 YAML：这条测试讲的正是「pyyaml 是可选的」，
        它自己就不该需要 pyyaml 才跑得起来。
        """
        ci = ROOT / ".github" / "workflows" / "ci.yml"
        if not ci.is_file():
            self.skipTest("没有 CI 配置")
        lines = ci.read_text(encoding="utf-8").splitlines()
        # job 是 `jobs:` 下缩进 2 空格的键；下一个同级键之前都算它的块。
        jobs, cur = {}, None
        for ln in lines:
            m = ln.startswith("  ") and not ln.startswith("   ") and ln.rstrip().endswith(":")
            if m and ln.strip().rstrip(":").replace("-", "").replace("_", "").isalnum():
                cur = ln.strip().rstrip(":")
                jobs[cur] = []
            elif cur:
                jobs[cur].append(ln)
        self.assertTrue(jobs, "一个 job 都没解析出来 —— 下面那条会空跑")
        bad = [name for name, body in jobs.items()
               if "unittest discover" in "\n".join(body)
               and "pip install pyyaml" not in "\n".join(body)]
        self.assertEqual(
            bad, [],
            f"这些 job 跑了测试套件却没装 pyyaml：{bad}。"
            "\n套件会真的执行 tools/lint_skills.py，缺它就是 7 error + 2 failure，"
            "而开发机上装着它、永远看不出来。")


if __name__ == "__main__":
    unittest.main()
