"""「资料填完了没有」只能有一条判据，而且不能只认 `[YOUR_` 开头的占位符。

## 原来是八份副本，全都只看得见一半

| 在哪 | 原来的判据 |
|---|---|
| `tools/doctor.py` | 从模板现抽占位符 ✅ |
| `tools/build_dashboard.py` `profile_ready` | `"[YOUR_" not in text` |
| `tools/export_web_data.py` `profile_ok` | `re.search(r"\\[YOUR_[A-Z_]+\\]", …)` |
| `workflows/` 六处守卫（apply / expand / interview / offer / rank / resume） | 「仍含 `[YOUR_` 占位符」 |

`profile.example/candidate.md` 有 **74 种**占位符，`[YOUR_` 只覆盖 **38 种**。剩下那
一半是 `[DEGREE]`（学历）、`[COMPANY_TYPE]`、`[DISQUALIFYING_KEYWORDS]`（排除关键词）、
`[FORBIDDEN_CLAIM_1]`（能力边界禁区）这类——**恰好是评估要用的那些字段**。

实测：把模板里 `[YOUR_*]` 那一半填上、其余原样留着，窄判据判「已就绪」，而那份资料
还剩 36 个占位符。于是

- 面板的「下一步」跳过「先建资料」，直接建议去抓职位、去投递；
- `/job-rank` 拿 `[DEGREE]` 当学历去过硬性条件；
- `/job-apply` 核对「有没有越过能力边界」时，对照的是 `[FORBIDDEN_CLAIM_1]`。

doctor 早就修过这个（它的 `template_tokens` 注释里写着同一段发现），**但只修了自己
那一处**。同一条规则的第 N 个副本改一处不改其它，是这个仓库反复出现的形状。

## 判据

1. 判据只有一份实现：`build_dashboard.profile_ready`，别处一律调用它。
2. 它必须抓得住「只填了 `[YOUR_*]` 那一半」的资料。
3. 工作流不许再把窄判据写成**唯一**判据。
"""

import ast
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_dashboard as bd  # noqa: E402
import doctor  # noqa: E402
import export_web_data as ex  # noqa: E402

TEMPLATE = ROOT / "profile.example" / "candidate.md"

#: 写着这道守卫的工作流。新增一处就往这里加一行——漏了就等于那条路没人管。
#: 有资料守卫的那几份工作流。`job-scrape.md` 2026-08-31 一并收进来 ——它一直有一道门，
#: 只是原来只查「搜索词在不在」，没写成同一种形态。
GUARDS = ["job-apply.md", "job-expand.md", "job-interview.md",
          "job-offer.md", "job-rank.md", "job-resume.md",
          "job-scrape.md"]


class OneImplementation(unittest.TestCase):

    def test_export_imports_the_same_function(self):
        self.assertIs(
            ex.profile_ready, bd.profile_ready,
            "export_web_data 里的 profile_ready 不是 build_dashboard 那个")

    def test_export_actually_calls_it(self):
        """看**调用点**，不是看 import。

        第一版只写了 `assertIs(ex.profile_ready, bd.profile_ready)`——变异验证当场
        证明它是空转的：把调用点换回内联的 `"[YOUR_" not in text`，import 还在，
        断言照样绿。**导入了不等于用上了**，而漏掉的正是「有没有用上」。
        """
        src = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        calls = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            if not any(getattr(t, "id", "") == "profile_ok" for t in node.targets):
                continue
            calls.append(node.value)
        self.assertTrue(calls, "export_web_data 里找不到给 `profile_ok` 赋值的地方——"
                               "判据可能改了名，本测试要跟着改")
        for v in calls:
            with self.subTest(line=v.lineno):
                self.assertTrue(
                    isinstance(v, ast.Call)
                    and getattr(v.func, "id", "") == "profile_ready",
                    f"export_web_data:{v.lineno} 的 `profile_ok` 不是由 "
                    f"`profile_ready(...)` 算出来的：{ast.unparse(v)[:70]}"
                    "\n判据只留一份，别在这里另写。")

    def test_the_token_list_comes_from_the_template(self):
        """清单现从模板抽，不在代码里另抄——抄一份就会漏掉后加的占位符。"""
        self.assertTrue(
            doctor.template_tokens("candidate.md"),
            "从 profile.example/candidate.md 抽不到占位符，判据失去来源")


class ItCatchesTheHalfFilledProfile(unittest.TestCase):
    """这组是它存在的理由：窄判据放行、正确判据必须拦住。"""

    def setUp(self):
        # **不跳过：`profile.example/candidate.md` 是已跟踪文件，必然存在。**
        # 跳过等于把「有人删了它/改了名」翻译成「这条守卫安静消失」——
        # 而它正是整个占位符判据的取值来源（74 种占位符从这里现抽）。
        self.assertTrue(
            TEMPLATE.is_file(),
            "profile.example/candidate.md 不在了 —— 它是占位符判据的唯一来源，不该缺")
        self.tpl = TEMPLATE.read_text(encoding="utf-8")

    def _write(self, text):
        d = tempfile.mkdtemp()
        p = Path(d) / "candidate.md"
        p.write_text(text, encoding="utf-8")
        return p

    def test_the_narrow_criterion_really_would_pass_it(self):
        """控制用例：先证明「窄判据放行」这个前提成立，否则下一条不知道在拦什么。"""
        half = re.sub(r"\[YOUR_[A-Z0-9_]*\]", "已填", self.tpl)
        self.assertNotIn("[YOUR_", half, "构造件里还留着 [YOUR_，前提不成立")
        self.assertTrue(re.search(r"\[[A-Z][A-Z0-9_]*\]", half),
                        "构造件里没有别的占位符了——那这条规则无从谈起")

    def test_half_filled_is_not_ready(self):
        half = re.sub(r"\[YOUR_[A-Z0-9_]*\]", "已填", self.tpl)
        left = sorted(set(re.findall(r"\[[A-Z][A-Z0-9_]*\]", half))
                      & doctor.template_tokens("candidate.md"))
        self.assertFalse(
            bd.profile_ready(self._write(half)),
            f"只填了 `[YOUR_*]` 那一半就被判为资料已就绪，还剩 {len(left)} 个占位符："
            f"\n  {left[:10]}"
            "\n其中 [DEGREE] 是学历（硬性条件要用）、[FORBIDDEN_CLAIM_1] 是能力边界禁区"
            "（/job-apply 的核对清单要对照它）。")

    def test_a_filled_profile_is_ready(self):
        """反向也要成立，否则真填完了还被挡，用户就会绕过这道门。"""
        done = re.sub(r"\[[A-Z][A-Z0-9_]*\]", "已填", self.tpl)
        self.assertTrue(bd.profile_ready(self._write(done)),
                        "填完了却判为没就绪")

    def test_the_real_active_user_is_not_broken(self):
        """收紧判据不能把现有用户误判成没填完——那会让面板整个退回引导态。"""
        root = ROOT / "users"
        if not root.is_dir():
            self.skipTest("还没有用户目录")
        # **先证明它会亮。** 下面那两个 `continue` 都可能把循环体清空：
        # 没有 `candidate.md`、或资料里还留着占位符。真到那一步，这条会
        # **一次断言都不做地绿着** —— 而它守的正是「收紧判据别误伤现有用户」，
        # 恒绿等于这道门不存在（`docs/finding-gaps.md`「用仪器之前先证明它会亮」）。
        #
        # 实测 2026-08-31：8 个用户里 7 个真的被断言到。数着，空了就明说 skip，
        # 不要让它变成一次看不见的通过。
        checked = 0
        for ud in sorted(root.iterdir()):
            cand = ud / "profile" / "candidate.md"
            if not cand.is_file():
                continue
            text = cand.read_text(encoding="utf-8", errors="replace")
            if "[YOUR_" in text:            # 本来就没填完的，不在本条范围内
                continue
            checked += 1
            with self.subTest(user=ud.name):
                self.assertTrue(
                    bd.profile_ready(cand),
                    f"{ud.name} 的资料按旧判据是就绪的，收紧后被判成没填完")
        if not checked:
            self.skipTest("没有一份填完了的 candidate.md 可比 —— "
                          "这条这次什么都没验，不是通过")

    def test_a_missing_file_is_not_ready(self):
        self.assertFalse(bd.profile_ready(Path("Z:/no/such/candidate.md")))

    def test_user_written_brackets_are_not_placeholders(self):
        """用户自己写的 `[TODO]` 不是模板占位符，不该判成没填完。"""
        self.assertTrue(bd.profile_ready(self._write("## 候选人资料\n- 备注 [TODO] 待补\n")))


class NoWorkflowRestatesTheNarrowRule(unittest.TestCase):

    def test_no_guard_says_only_YOUR_(self):
        bad = []
        for name in GUARDS:
            p = ROOT / "workflows" / name
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                # 「不只是 `[YOUR_` 开头的那些」这种**否定**说法是对的，放行
                if "`[YOUR_` token" in line or re.search(r"仍含 `\[YOUR_`", line):
                    bad.append(f"workflows/{name}:{i}  {line.strip()[:70]}")
        self.assertEqual(
            bad, [],
            "这些守卫仍把「有没有 `[YOUR_`」当成唯一判据：\n  " + "\n  ".join(bad)
            + "\n模板 74 种占位符里它只看得见 38 种，学历与能力边界禁区都在视野之外。")

    def test_every_guard_file_exists(self):
        """控制用例：GUARDS 里的文件都在，否则上面那条对着空气跑。"""
        missing = [n for n in GUARDS if not (ROOT / "workflows" / n).is_file()]
        self.assertEqual(missing, [], f"GUARDS 里这些文件不存在：{missing}")

    def test_no_workflow_still_judges_the_whole_file(self):
        """**判据从名单换成特征。** `GUARDS` 是手写的七个文件名 ——
        也就是说漏加一条，它就永远查不到那一条。

        2026-09-02 实测漏了**两条**，其中一条是主线命令：

        - `/job-auto` —— 「`candidate.md` 不存在、或还留着模板占位符 → 停止」。
          脊梁是 `/job-setup` → `/job-auto` → `/job-outcome`，而 `/job-setup`
          第二轮问完说「够排序了」，照整份文件判 auto **当场拒绝** ——
          `AGENTS.md` 那一节的原话就是「同一份文档一边发出邀请，一边把门关上」。
        - `/job-upskill` —— 同样，而且和它自己索引里那句
          「拿所有评过分的岗一起算（**新用户也有语料**）」直接打架。

        2026-08-31 那次点名改了六条（`job-rank` / `job-apply` / `job-interview` /
        `job-expand` / `job-resume` / `job-offer`），**这张名单照抄了那六条加
        `job-scrape`**，于是没被点名的两条就此隐形。同 `JD_READERS` 那次
        （手写名单漏了 `job-expand` 与 `job-notion-sync`，后来也换成了特征）。

        特征：非引用正文里同时出现「占位符」与 `profile/candidate.md`
        —— 那就是在守这道门，必须按档判。`job-setup` 除外，它是**填**资料那条。
        （`job-add-template` 不会误伤：它说的是 `profile.example/candidate.md`
        里的模板占位符名，路径不同。）
        """
        bad = []
        for wf in sorted((ROOT / "workflows").glob("job-*.md")):
            if wf.stem == "job-setup":
                continue
            body = "\n".join(l for l in wf.read_text(encoding="utf-8").splitlines()
                             if not l.lstrip().startswith(">"))
            if "占位符" not in body or "profile/candidate.md" not in body:
                continue
            if "profile_gaps(udir," not in body:
                bad.append(wf.name)
        self.assertEqual(
            bad, [],
            f"这些工作流还在拿**整份文件**判资料填完没有：{bad}。"
            "\n照它走会把 `/job-setup` 自己发出的邀请挡在门外 —— "
            "规则见 `AGENTS.md`「资料没填完是分档的，不是一个整体判断」")

    def test_the_feature_scan_sees_something(self):
        """控制用例：特征扫得到，否则上面那条永远绿。"""
        n = 0
        for wf in (ROOT / "workflows").glob("job-*.md"):
            body = "\n".join(l for l in wf.read_text(encoding="utf-8").splitlines()
                             if not l.lstrip().startswith(">"))
            if "占位符" in body and "profile/candidate.md" in body:
                n += 1
        self.assertGreaterEqual(
            n, 7, f"只认出 {n} 条守这道门的工作流 —— 特征八成失效了")

    def test_the_guards_still_guard(self):
        """控制用例：这几份里确实还写着这道门，不是被整段删了。

        **认的记号 2026-08-31 换过。** 原来查的是 `profile_ready`（整份文件、
        还剩任何一个占位符就算没填完）—— 那条门比该有的严：`/job-setup` 分四轮问，
        第二轮问完说「够排序了 —— 跑 `/job-rank`」，而照整份文件判，`/job-rank`
        当场拒绝。现在各步按自己那一档判（`doctor.profile_gaps(udir, "<档>")`），
        规则在 `AGENTS.md`「资料没填完是分档的，不是一个整体判断」。

        这条**当时红了**，而且红得对：它是控制用例，守卫换了说法就该来同步它。"""
        for name in GUARDS:
            text = (ROOT / "workflows" / name).read_text(encoding="utf-8")
            with self.subTest(f=name):
                self.assertIn("profile_gaps(udir,", text,
                              f"workflows/{name} 里找不到这道门了——"
                              "要么被删了，要么改了说法没同步本测试")


class AutoRunsAsFarAsTheProfileAllows(unittest.TestCase):
    """README「快速开始」承诺：「这三档都由 `/job-auto` 一条命令跑，它会按你资料
    填到哪一档跑到哪一步」。而 `/job-auto` 的前置检查此前只判 `rank` 档，出材料
    那一步标着「无条件」—— 第二轮答完的用户敲它，抓完评完，`/job-apply` 的 `apply`
    档守卫当场拒绝。承诺在 README 里，落点在本文件里没有。2026-09-04 通读发现。

    钉两头：README 的那句承诺还在（不然这条没有出处），`job-auto.md` 真的判了
    `apply` 档且**不是停**。
    """

    AUTO = (ROOT / "workflows" / "job-auto.md").read_text(encoding="utf-8")
    README = (ROOT / "README.md").read_text(encoding="utf-8")

    def test_the_readme_still_makes_the_promise(self):
        self.assertIn("填到哪一档跑到哪一步", self.README,
                      "README 不再承诺按档跑了 —— 那本文件下面那条要跟着改，别空钉")

    #: 钉的是跨模块契约名（`doctor.` 限定），不是某一行长什么样 ——
    #: `test_a_guard_pins_behaviour_not_a_line` 的判据就是这条分界。
    GATE = 'doctor.profile_gaps(udir, "apply")'

    def test_auto_checks_the_apply_tier(self):
        body = "\n".join(l for l in self.AUTO.splitlines()
                         if not l.lstrip().startswith(">"))
        self.assertIn(self.GATE, body,
                      "job-auto 没判 apply 档 —— 第二轮答完的用户会在抓完评完之后"
                      "才被 /job-apply 拒绝，正是它自己那段「半成品」警告描述的样子")

    def test_auto_degrades_instead_of_stopping(self):
        """判了之后要「跳过出材料」，不是「停止」——那是和 rank 档不同的处理。"""
        i = self.AUTO.index(self.GATE)
        seg = self.AUTO[max(0, i - 400): i + 400]
        self.assertIn("不停", seg, "apply 档缺的处理写成了停 —— 那就不是按档跑，是按最高档挡")
        self.assertIn("跳过", seg, "没说出材料那一段要跳过")

    def test_the_skip_names_a_command(self):
        """`AGENTS.md`「每一处引导都要写出该敲的命令」——补第三轮得给命令。"""
        i = self.AUTO.index(self.GATE)
        seg = self.AUTO[i: i + 900]
        self.assertIn("/job-setup --section boundaries", seg)

    def test_the_unconditional_line_names_the_exception(self):
        """「出材料（无条件）」那一行要把这个例外写进去 —— 不然执行者读到
        那一行照样跑，前置检查白判。"""
        line = next(l for l in self.AUTO.splitlines() if l.startswith("出材料（**无条件**"))
        self.assertIn("资料没到", line,
                      "出材料那一行仍是纯「无条件」—— 前置检查判了却没人听")


if __name__ == "__main__":
    unittest.main()


class TheTwoImplementationsAgree(unittest.TestCase):
    """`doctor.still_template` 与 `build_dashboard.profile_ready` 判的是同一件事。

    两处**实现不同**：doctor 只比 `profile.example` 的占位符清单，
    profile_ready 另外还认 `[YOUR_`、`[DEGREE]` 这类字面。
    两边都要读同一份模板，给出不同答案时**面板和命令行会一个放行一个拦**，
    而用户看不出是哪一层挡的：`profile_ready` 是面板判「这个用户建过档没有」，
    `still_template` 是 `profile_gaps` 逐节判「这一步要的那几节填了没有」。
    （2026-08-31 之前工作流的门也引 `profile_ready`，现在引分档那一套；
    这条钉的一致性不受影响 —— 两个实现仍然都在，也仍然都在用。）

    2026-08-20 实测三种输入下结论一致（都靠现比对模板，没写死词表）。
    这条钉住这个一致性：谁改了其中一个实现，这里会红。
    """

    def _both(self, content: str):
        import sys as _sys
        import tempfile
        _sys.path.insert(0, str(ROOT / "tools"))
        import doctor
        import build_dashboard as bd
        d = Path(tempfile.mkdtemp())
        (d / "profile").mkdir()
        (d / "profile" / "candidate.md").write_text(content, encoding="utf-8")
        return (doctor.still_template(d, "candidate.md"),
                not bd.profile_ready(d / "profile" / "candidate.md"))

    def test_placeholder_families_agree(self):
        for content, label in [
            ("# 候选人\n\n姓名：[YOUR_NAME]\n学历：本科\n", "YOUR_ 家族"),
            ("# 候选人\n\n姓名：张三\n学历：[DEGREE]\n", "DEGREE 家族"),
            ("# 候选人\n\n姓名：张三\n学历：本科\n", "填好了"),
        ]:
            with self.subTest(label):
                a, b = self._both(content)
                self.assertEqual(a, b,
                                 f"{label}：doctor 说还是模板={a}，"
                                 f"profile_ready 说没填完={b} —— 两个守卫会一个放行一个拦")

    def test_neither_hardcodes_a_placeholder_list(self):
        """判据要现比对 `profile.example`，写死词表会随模板演进而失效。"""
        import inspect
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "tools"))
        import doctor
        import build_dashboard as bd
        for fn in (doctor.still_template, bd.profile_ready):
            src = inspect.getsource(fn)
            self.assertIn("profile.example", src,
                          f"{fn.__name__} 不再现比对模板了——写死的清单会过时")
