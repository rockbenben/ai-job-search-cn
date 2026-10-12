# -*- coding: utf-8 -*-
"""判据钉在「某一行代码长什么样」上时，一次合理的搬家就会让它红。

2026-08-31 把收尾那两个集合的记账从 `live_tail` 搬进 `_cli.note_live`
（手写尾巴的两条检查也要调它），**三条断言同时红**，三条钉的都是位置：

    查 `live_tail` 体内有没有 `LIVE_REWRITE`
    查那一行 `LIVE_REWRITE.update(...)` 长什么样
    查 `_cli.py` 源码里有没有 `LIVE_SEEN.update`

它们守的规则都对（去重只有一本账、值要留原样链接），只是问法错了 ——
红的不是回归，是重构本身。改成「调一次 `note_live`，看集合里有什么」之后，
同一批变异照样全红。

同一课这个仓库交过好几次：`test_the_copies_in_doctor_still_match` 的开头
写着「守卫钉实现位置，等于把重构本身判成违规」；`test_the_maybe_tier_is_two_things`、
`test_cli_contract` 也各栽过一次。

## 怎么分

needle 是**跨模块的名字**（`_cli.claim_without_source(`）时，钉的是
「这个消费方走不走正本」—— 那是契约，该钉，而且换不成行为断言
（「有没有走那一份」本来就是源码层面的事）。

needle 是**局部实现**（`skipped.add(`、`real = [n for n in users`）时，
钉的是位置：那个名字只在那个函数里成立，函数一改它就没了。

## 这是一条上限，不是一条「清零」

有一类换不成行为断言：TS 组件在 Python 里执行不了，只能扫源码
（`const plus = scored.filter(` 那种）。所以这条不要求降到 0 ——
要求的是**别再涨**。判据与措辞见 `CONTRIBUTING.md`
「判据钉**行为**，不钉那一行代码长什么样」。
"""
import ast
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
T = ROOT / "tests"

#: haystack 看着像「一段源码」的那些名字。
_SOURCEY = re.compile(
    r"\b(seg|src|body|code_of|read_text|SRC|APP|CSS|MAIN|AUDIT|EX|CLI"
    r"|TYPES|SHEET|APPLY|DOCTOR|BD|TOKENS|LOAD)\b")
#: needle 看着像「一段代码」而不是「一句话」。
_CODEY = re.compile(r"[A-Za-z_][\w.]*\s*[(=]")
#: `tests/` 里用到的模块别名。**要按这张表判，不能按「有个点」判** ——
#: `skipped.add(` 也是 `x.y` 的形状，那是个局部变量（判据自检当场照出来）。
#:
#: `scoring` 是 2026-10-12 加进来的：`test_the_pay_sentence_is_the_only_one_that_moves`
#: 钉的是「`score.py` 走不走 `scoring.rewrite_pay_said` 这份正本、别退回全局 `sub`」，
#: 按上面「怎么分」那一节那是契约，不是位置。表里缺这个名字时它被算成了按行钉。
_MODULES = ("_cli", "_ex", "_sc", "_vp", "ap", "AP", "bd", "ex", "tk", "wb",
            "fu", "ps", "qy", "vp", "sm", "oh", "tu", "gs", "sc", "scoring",
            "pb", "fd",
            "ar", "srv", "doctor", "tracker", "prescreen", "archive", "serve",
            "followups", "gap_split", "jd_store", "audit", "security_guards",
            "lint_skills")
#: 跨模块限定名 —— 那是契约，不是位置。
_QUALIFIED = re.compile(r"^(?:" + "|".join(_MODULES) + r")\.")

#: 实测 2026-08-31 的条数。**只许往下走。**
BASELINE = 228


def _pins() -> list:
    out = []
    for f in sorted(T.glob("test_*.py")):
        src = f.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)
                    and n.func.attr in ("assertIn", "assertNotIn")):
                continue
            if len(n.args) < 2:
                continue
            hay = ast.get_source_segment(src, n.args[1]) or ""
            if not _SOURCEY.search(hay):
                continue
            nd = n.args[0]
            if not (isinstance(nd, ast.Constant)
                    and isinstance(nd.value, str)):
                continue
            v = nd.value
            if not _CODEY.search(v) or _QUALIFIED.match(v.strip()):
                continue
            out.append(f"{f.name}:{n.lineno}  {v[:48]}")
    return out


class TheRulerWouldLightUp(unittest.TestCase):
    """两头都要证明：扫得到断言，也分得开契约与位置。"""

    def test_it_scans_a_healthy_number_of_files(self):
        self.assertGreater(len(list(T.glob("test_*.py"))), 300)

    def test_it_finds_some(self):
        self.assertGreater(len(_pins()), 50,
                           "一条都扫不到 —— 抽取多半失配了，下面那条就是空跑")

    def test_a_cross_module_name_is_not_counted(self):
        """`_cli.x(` 是契约，不该算进这个数。"""
        self.assertIsNotNone(_QUALIFIED.match("_cli.claim_without_source("))
        self.assertIsNone(_QUALIFIED.match("skipped.add("))

    def test_a_plain_sentence_is_not_counted(self):
        """给用户看的话不是代码 —— 扫进来这个数会失去意义。"""
        self.assertIsNone(_CODEY.search("发之前删掉：开场铺垫"))
        self.assertIsNotNone(_CODEY.search('if e.get("evaluated"):'))


class ItOnlyGoesDown(unittest.TestCase):

    def test_no_new_line_pinned_guard(self):
        got = _pins()
        self.assertLessEqual(
            len(got), BASELINE,
            f"钉在某一行代码上的断言从 {BASELINE} 涨到了 {len(got)} —— "
            "换成钉行为（调一次那个函数，看它做了什么）。"
            "判据见 `CONTRIBUTING.md`「判据钉**行为**，不钉那一行代码长什么样」。"
            "\n新增的大致在：" + repr(got[-4:]))

    def test_the_baseline_is_not_stale(self):
        """降下来了就该把这个数收紧 —— 一个只挂着不降的上限是张免死金牌。"""
        n = len(_pins())
        self.assertLessEqual(
            BASELINE - n, 12,
            f"实际只剩 {n} 条，上限还写着 {BASELINE} —— 把它收到 {n}")


#: 「长得像源码」——这一条只收前端那几种记号，宁可漏不可误报：
#: 一句中文文案里不会出现 `=>` 或 `??`。
_JSY = re.compile(r"=>|\s&&\s|\?\?|\?\.|className=|=== ")


def _shared_code_pins() -> dict:
    """一段源码字面量 → 逐字钉着它的测试文件（只留 ≥2 家的）。"""
    homes = {}
    for f in sorted(T.glob("test_*.py")):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)
                    and n.func.attr in ("assertIn", "assertNotIn",
                                        "assertRegex")
                    and n.args):
                continue
            a = n.args[0]
            if (isinstance(a, ast.Constant)
                    and isinstance(a.value, str)
                    and len(a.value) >= 10
                    and _JSY.search(a.value)):
                homes.setdefault(a.value, set()).add(f.name)
    return {k: v for k, v in homes.items() if len(v) > 1}


class OneLineOneGuard(unittest.TestCase):
    """同一行源码不许被两个以上测试文件逐字钉着。

    钉一行已经脆了（上面那条棘轮管的就是这个）；**钉三遍是脆乘以三** ——
    换个行、多个空格、把条件提成变量，三条一起红，而页面一个像素都没变。

    实测 2026-08-31 扫出两组：

        ×3  面板首屏那块内联命令表外面那行 JSX 条件
            （`test_command_reference` / `test_settings_open_in_a_modal` /
              `test_the_first_screen_is_the_job_list`，六条断言）
        ×2  评分明细「全都没打分」那一支的判断式
            （`test_web_copy` 那份与正本逐字相同，纯重复）

    第一组改钉 `className="firstrun"`（`tests/jsx.py` 的 `FIRSTRUN`）与
    `desk_entry()`；第二组把重复那份删了，原地留了指路。

    ⚠️ 这条**不是**「不许钉源码」——前端没有可跑的运行时，钉源码有时是唯一
    的办法。它只禁**同一行钉在多家**：真要多家关心同一件事，就把锚点提成一个
    共用常量（`tests/jsx.py` 就是这个用途），改一处三家都跟着走。
    """

    def test_the_scan_sees_code_literals(self):
        """**先证明它认得出源码字面量。** 认不出的话下面那条在空集上永远绿。"""
        n = sum(1 for f in sorted(T.glob("test_*.py"))
                for ln in f.read_text(encoding="utf-8").splitlines()
                if _JSY.search(ln))
        self.assertGreater(n, 100, f"只认出 {n} 行，正则八成坏了")

    def test_no_line_is_pinned_from_two_places(self):
        bad = _shared_code_pins()
        self.assertEqual(
            bad, {},
            "同一行源码被多个测试文件逐字钉着，改一次会一起红：" + "；".join(
                f"{k[:40]!r} ← {sorted(v)}" for k, v in bad.items()))


if __name__ == "__main__":
    unittest.main()
