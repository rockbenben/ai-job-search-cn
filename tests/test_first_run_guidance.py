# -*- coding: utf-8 -*-
"""新用户从零开始的七个起始状态，每一个都要给出**能敲得通**的下一步。

自检的存在理由就是「用户进到这个仓库，不该需要先读文档才知道该干什么」
（`AGENTS.md`）。所以这条链上任何一处指错，代价都不是「提示不准」，
而是把唯一的入口指进死胡同。

## 这一轮抓到的那个

2026-08-13 第 7 轮检查，场景 D（新建了用户目录、`profile/` 完全是空的）：

    进度段：[--] 资料还没建（users/小明/profile/candidate.md 不存在）   ← 判对了
    下一步：    /job-setup --section search                          ← 指错了

两段自相矛盾，而用户会照着下一步敲。而 `--section` 在 `job-setup.md` 里的定义是
**update-only flow**——它假设那份资料已经在盘上；`--section search` 的写入目标里
就有 `profile/candidate.md` 的 `[YOUR_CITY]`，文件不存在时那一步无处可写。

根因不在 `fix_for` 的逻辑，在它**缺一个前提**：`STAGE_NEEDS["scrape"]` 只查
`search-queries.md`（搜岗这一档本来就不需要 candidate.md），于是缺项里只有
「搜索配置」，`fix_for` 看见它们全属同一节，就报了 `--section`。
它从来不知道「那份资料压根不存在」这件事。
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _canonical_env(tool: str = "claude") -> dict:
    """钉死标准命令形式（带斜杠）的子进程环境。

    doctor 按宿主工具把 `/job-xxx` 去斜杠，而子进程继承本会话的探测信号：
    Claude Code 会话里带斜杠、CI / 普通终端不带。这些断言钉的是文档正本的
    标准形式，渲染层去斜杠另有 test_code_tool_detection 整条覆盖
    （2026-09-12 这套在 CI 里红过两条）。

    默认 `claude` 就是这个文件原来那条漏判的成因：**七个场景全都只在一家
    工具下跑**，于是「非 Claude 用户看到的第一个指路」从来没有被测过。
    要测别的档就传 `tool`，那时命令是去斜杠的形态，断言得按那个写。
    """
    return dict(os.environ, JOBS_CODE_TOOL=tool)


def _filled_profile() -> str:
    t = (ROOT / "profile.example" / "candidate.md").read_text(encoding="utf-8")
    t = re.sub(r"\[YOUR_[A-Z_0-9]+\]", "小明", t)
    return re.sub(r"\[[A-Z][A-Z0-9_]*\]", "已填", t)


def _build(tmp: Path, scenario: str) -> None:
    """拷最小可跑集合，再按场景改状态。"""
    for d in ("tools", "workflows", "profile.example"):
        shutil.copytree(ROOT / d, tmp / d, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__"))
    (tmp / "web" / "public").mkdir(parents=True, exist_ok=True)
    (tmp / "web" / "dist").mkdir(parents=True, exist_ok=True)
    for f in ("AGENTS.md", "README.md", "SETUP.md"):
        if (ROOT / f).is_file():
            shutil.copy(ROOT / f, tmp / f)

    U = tmp / "users" / "小明"
    ptr = tmp / ".active_user"
    if scenario == "全新clone":
        return
    if scenario == "指针指向不存在的用户":
        ptr.write_text("查无此人", encoding="utf-8"); return
    if scenario == "指针是空文件":
        ptr.write_text("", encoding="utf-8"); return
    if scenario == "有用户但没有profile":
        (U / "job_scraper").mkdir(parents=True)
        ptr.write_text("小明", encoding="utf-8"); return
    if scenario == "profile还是占位符":
        (U / "profile").mkdir(parents=True)
        shutil.copy(ROOT / "profile.example" / "candidate.md",
                    U / "profile" / "candidate.md")
        ptr.write_text("小明", encoding="utf-8"); return
    if scenario == "profile填好了但没抓过岗":
        (U / "profile").mkdir(parents=True)
        (U / "profile" / "candidate.md").write_text(_filled_profile(), encoding="utf-8")
        ptr.write_text("小明", encoding="utf-8"); return
    if scenario == "抓到岗但一个没评":
        (U / "profile").mkdir(parents=True)
        (U / "profile" / "candidate.md").write_text(_filled_profile(), encoding="utf-8")
        (U / "job_scraper").mkdir(parents=True)
        (U / "job_scraper" / "seen_jobs.json").write_text(
            json.dumps({"seen": {f"https://x/{i}#岗{i}": {
                "title": f"岗{i}", "company": "某公司", "url": f"https://x/{i}",
                "status": "new", "first_seen": "2026-08-13"} for i in range(30)}},
                ensure_ascii=False), encoding="utf-8")
        ptr.write_text("小明", encoding="utf-8"); return
    raise AssertionError(f"没有这个场景：{scenario}")


def _doctor(scenario: str, tool: str = "claude") -> str:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _build(tmp, scenario)
        r = subprocess.run([sys.executable, str(tmp / "tools" / "doctor.py")],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=180, cwd=tmp,
                           env=_canonical_env(tool))
        out = (r.stdout or "") + (r.stderr or "")
        assert "Traceback" not in out, f"[{scenario}] 自检崩了：\n{out[-800:]}"
        assert r.returncode == 0, (
            f"[{scenario}] 退出码 {r.returncode}——自检的约定是「缺依赖是状态不是错误」，"
            f"只有「你不在这个仓库里」才 exit 1")
        i = out.find("下一步做什么")
        assert i >= 0, f"[{scenario}] 输出里没有「下一步做什么」这一段"
        return out[i:]


SCENARIOS = ["全新clone", "指针指向不存在的用户", "指针是空文件",
             "有用户但没有profile", "profile还是占位符",
             "profile填好了但没抓过岗", "抓到岗但一个没评"]


class EveryStartingStateGetsARunnableNextStep(unittest.TestCase):

    def test_none_of_them_crash_and_all_name_a_command(self):
        """七个状态都要能跑完、都要给出一条以 `/` 开头或写明命令的下一步。"""
        for s in SCENARIOS:
            with self.subTest(scenario=s):
                nxt = _doctor(s)
                self.assertTrue(
                    re.search(r"/job-\w+|python tools/", nxt),
                    f"[{s}] 下一步里没有任何能敲的命令：\n{nxt[:300]}")

    def test_a_missing_profile_says_build_it_not_patch_a_section(self):
        """**这一轮的那个 bug。** 资料一次都没建过时不许报 `--section`。

        `--section` 是 update-only：它假设资料已经在盘上，而
        `--section search` 要往 `candidate.md` 里写字段——文件都没有，无处可写。
        """
        nxt = _doctor("有用户但没有profile")
        self.assertIn("/job-setup", nxt)
        self.assertNotIn("--section", nxt,
                         "资料还没建就报 --section —— 那是 update-only 流程，"
                         "它假设文件已经存在")

    def test_an_existing_profile_still_gets_the_cheap_section_path(self):
        """反过来也要成立：文件在、只缺一节时，别让人整份重填。

        这是「分四轮问、答完第一轮就能走」那条设计的落点，不能为了修上面那条
        把它一起改没。
        """
        for s in ("profile还是占位符", "profile填好了但没抓过岗"):
            with self.subTest(scenario=s):
                self.assertIn("--section", _doctor(s),
                              f"[{s}] 资料已存在却要求整份重跑，把分节补填的路堵了")

    def test_a_dangling_pointer_is_not_treated_as_a_profile_problem(self):
        """`.active_user` 指向不存在的用户是**指针**问题，跑 /job-setup 修不了。"""
        nxt = _doctor("指针指向不存在的用户")
        self.assertIn("/job-user", nxt)
        self.assertIn("修不了", nxt, "没说清 /job-setup 解决不了它，用户会白跑一趟")

    def test_progress_and_next_step_do_not_contradict(self):
        """进度段说「资料还没建」，下一步就不能说「还差这几项」。

        后者听起来像已经填了大半，而实际上一个字都没有——**同一屏上的两段
        自相矛盾，用户只会照着下一步敲**。
        """
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _build(tmp, "有用户但没有profile")
            r = subprocess.run([sys.executable, str(tmp / "tools" / "doctor.py")],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=180, cwd=tmp,
                               env=_canonical_env())
            out = (r.stdout or "") + (r.stderr or "")
        self.assertIn("资料还没建", out, "进度段没报出「资料还没建」")
        nxt = out[out.find("下一步做什么"):]
        self.assertNotIn("还差这几项", nxt,
                         "进度段说没建过、下一步说「还差这几项」——两段对不上")


class TheFirstRunGuidanceWorksForEveryTool(unittest.TestCase):
    """新用户看到的第一条指路，不能要他去启动某一家的工具。

    `_CommandStream` 把整份输出里的 `/job-xxx` 按宿主工具改写，命令形式那一层
    是全局兜住的；但它**管不了一个不带 `/job-` 前缀的程序名**。首轮那段就踩过
    这个缝——它硬印一行

        claude              # 在这个目录启动 Claude Code

    对 Claude 用户是对的，对另外几家（吃斜杠的 agy / Qoder / Qwen / MiMo / MCode、
    要去斜杠的 Codex，以及认不出来的助手——**2026-10-13 起最后这批也吃斜杠了**）
    是让人去敲一个手上没有的命令。

    **这个 bug 能活着，是本文件那条判据的形状造成的**：七个场景原来全在
    `JOBS_CODE_TOOL=claude` 下跑，非 Claude 的首轮输出一次都没被断言过。
    所以这里断言的不是「没有 claude 这个词」——结尾那条 💡 本来就要印可选值，
    里面就有 claude；断言的是**缩进的「照抄就能敲」那一行里只准出现本仓库的命令**。
    这个口径不需要知道每一家的启动命令叫什么（那得逐家实测），也就不会多一家
    工具就失效。
    """

    #: 缩进两格以上 = 「这一行请直接敲」，不是散文。
    _TYPED = re.compile(r"^ {2,}(\S+)")

    def test_it_names_no_command_but_the_repo_own(self):
        for tool in ("claude", "codex", "generic"):
            with self.subTest(tool=tool):
                # 切掉结尾那条 💡：它印的 `JOBS_CODE_TOOL=a|b|c` 里必然带着各家名字，
                # 那是「认错了怎么纠正」，不是「现在该敲什么」。
                nxt = _doctor("全新clone", tool).split("💡")[0]
                typed = [m.group(1) for m in
                         (self._TYPED.match(line) for line in nxt.splitlines())
                         if m]
                self.assertTrue(typed, f"[{tool}] 首轮没印出任何「照抄就能敲」的行")
                self.assertTrue(any(c.lstrip("/").startswith("job-setup")
                                    for c in typed),
                                f"[{tool}] 首轮没把建档那条命令印成可敲的一行：{typed}")
                for cmd in typed:
                    self.assertTrue(cmd.lstrip("/").startswith("job-"),
                                    f"[{tool}] 首轮让人敲 {cmd} —— 那是某一家的启动命令，"
                                    f"换一家的用户照敲就是 command not found")


if __name__ == "__main__":
    unittest.main()
