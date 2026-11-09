# -*- coding: utf-8 -*-
"""同一个**值**住在两个模块里时，得有人说清为什么、并钉住它们相等。

## 为什么按值扫，不按名字扫

`test_the_copies_in_doctor_still_match` 那条是按**名字**找副本 —— 而写下这段话
的 2026-08-30，那条守卫其实**还不存在**（`doctor.py` 里也引着它）；它 08-31 才
真的建起来，比的是**函数**、按行为比、扫全 `tools/`。

即便如此，按名字找副本的盲区一个没少 —— 值不是函数，改个名字就看不见了。
2026-08-30 按**值**扫了一遍全 `tools/`，当场看见两组：

    ('硬门 FAIL', '硬门FAIL', '不满足硬性条件')
        _cli.GATE_FAIL_PREFIXES  /  doctor._OUT_PREFIXES     ← 名字不同，看不见
    {'hired', 'interview', 'offer'}
        build_dashboard._INTERVIEW_STATUSES / doctor.INTERVIEW_STATUSES
                                                              ← 不是那两个文件

前一组当时**没有任何东西钉住两边相等** —— `test_material_counts_agree` 只管
`doctor` 文件内部用得一致。名字一改，副本就从守卫底下溜走了。

## `re.compile` 原来整类不在网里

`ast.literal_eval` 碰上 `Call` 抛 `ValueError`，而下面那段当时直接 `continue` ——
于是 `tools/` 下 **68 个**顶层正则常量一个都没进过这张网。实测 2026-08-31 把它们
收进来，当场看见一组真副本：

    re.compile(r"\\[[A-Z][A-Z0-9_]*\\]")
        build_dashboard._PLACEHOLDER_RE  /  doctor._PLACEHOLDER   ← 又是改了名

那一份的消费点是 `profile_ready`：正则认不出占位符 → `findall` 空 →交集空 →
判**「资料已就绪」**。漏检那一侧不报错，只是把门放开。

这一组**并不是没人盯**（`test_placeholder_families_agree` 拿三种写法比过两边一致），
溜得掉的是那三种之外的新写法。它照样该合 —— 而这条守卫的意义在于：发现它的
不是那条行为断言，是这张网收进 `re.compile` 的那一刻。（已合并到 `doctor.placeholders`。）

## 只看非标量

整数天然会撞：实测 `14` 同时是归档天数、封编制窗口、简历过期天数、
等待新鲜度、职位过期天数 —— 五个不相干的概念。**结构相同才说明是同一件事**，
所以只收 tuple / list / set / dict（≥2 项）和长字符串。

## 例外表要写理由，不只是名字

允许存在的副本都有各自的正当性（`doctor` 不 import 仓库模块是硬契约），
但**没人盯的副本不是**。所以每一条都要说清谁在钉。
"""
import ast
import pathlib
import sys
import unittest
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402
import build_dashboard as bd  # noqa: E402
import doctor  # noqa: E402

#: 允许一值多家的那几组：值的指纹 → `(住址集合, 谁在钉住它们相等)`。
#:
#: 这是**例外清单**，不是副本清单 —— 下面那条守卫自己按值扫，
#: 扫出来不在这张表里的就红。
#:
#: ⚠️ **住址也要申报。** 第一版只按值索引 —— 变异实测当场证明它漏一半：
#: 往 `prescreen` 里新造一份同值常量（第三家），而那个值已经在表里，
#: 守卫照样绿。副本悄悄多一家，正是这条要防的事。
ALLOWED = {
    ("tuple", "('硬门 FAIL', '硬门FAIL', '不满足硬性条件')"): (
        {"_cli.py:GATE_FAIL_PREFIXES", "doctor.py:_OUT_PREFIXES"},
        "doctor 不 import 仓库模块；相等由本文件 test_the_out_prefixes_match 钉住"),
    ("tuple", "('猎头', '人力资源', '人才', '咨询')"): (
        {"_cli.py:_AGENCY_WORDS", "doctor.py:AGENCY_WORDS"},
        "相等由 test_one_judge_for_agency_or_direct 的 test_the_word_lists_match 钉住"),
    ("set", "['hired', 'interview', 'offer']"): (
        {"build_dashboard.py:_INTERVIEW_STATUSES", "doctor.py:INTERVIEW_STATUSES"},
        "相等由 test_application_loop 钉住（那里连 export 那份别名一起比）"),
    ("regex", repr(r"职位链接\s*[：:]\s*(\S+)")): (
        {"_cli.py:LINK_LINE", "doctor.py:LINK_LINE"},
        "doctor 不 import 仓库模块；相等由 test_the_copies_in_doctor_still_match "
        "的 test_link_line_agrees 钉住"),
    ("tuple", "('%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d', '%Y年%m月%d日')"): (
        {"doctor.py:DATE_FORMATS", "followups.py:_DATE_FORMATS"},
        "解析函数只有一份（followups.parse_date，build_dashboard 与 "
        "export_web_data 都 import 它），doctor 那份是契约换来的副本，"
        "相等由 test_both_next_steps_agree 钉住"),
    ("regex", repr(r"```(?:bash|sh|shell|console)\n(.*?)```") + " [re.S]"): (
        {"_entries.py:_FENCE", "lint_skills.py:_FENCE_CMD"},
        "「什么算一段 bash 围栏」这一个判断。lint_skills.py 必须能**单独拷进临时目录**"
        "跑（test_cli_contract.CopyableToolsStayStandalone），与 doctor 同处境："
        "正本 import 不过去，只能各留一份。相等由本文件 "
        "test_the_bash_fence_pattern_matches 钉住（模式与旗标都比）。"
        "tests/test_skill_permissions_cover_its_workflow.py 里的第三份由 Task 5 删掉"
        "（改为 import _entries.commands_in），那张网只看 tools/，看不见它"),
    ("tuple", "('.claude', '.agents', '.codebuddy', '.workbuddy')"): (
        {"_entries.py:SHELL_FAMILIES", "lint_skills.py:SHELL_FAMILIES"},
        "各族技能壳的根（2026-11-09 接 WorkBuddy 时从两族扩到四族）。同一个「必须能"
        "单独拷进临时目录跑」的契约（上面那条 CopyableToolsStayStandalone）：正本在 "
        "lint 跑起来的那个临时目录里不存在，import 不过去，只能各留一份。相等由本文件 "
        "test_the_shell_families_match 钉住 —— 两边一旦分叉，lint 会去查一族根本不存在的"
        "外壳，而生成器真正写的那几族没人查"),
}


def _fingerprint(v):
    if isinstance(v, set):
        return (type(v).__name__, repr(sorted(v)))
    return (type(v).__name__, repr(v))


def _regex_fingerprint(node):
    """`re.compile("字面量"[, 旗标])` → 指纹，不是这个形状就交回 None。

    旗标算进指纹：同一个模式配 `re.M` 和不配，本来就不是同一个判断。
    """
    if not (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "compile"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "re" and node.args):
        return None
    try:
        pat = ast.literal_eval(node.args[0])
    except (ValueError, SyntaxError, TypeError):
        return None
    if not isinstance(pat, str):
        return None
    flags = ", ".join(ast.unparse(a) for a in node.args[1:])
    return ("regex", repr(pat) + (f" [{flags}]" if flags else ""))


def all_homes() -> dict:
    """值的指纹 → `[(文件, 常量名)]`，全 `tools/`，**不筛几家**。

    分出这一层是为了让自检数得到「网里到底有没有正则」——只看筛过的结果，
    抽取器整类失效时它是空的，而空集上的断言永远绿。
    """
    homes = defaultdict(list)
    for p in sorted((ROOT / "tools").glob("*.py")):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for n in tree.body:
            if not (isinstance(n, ast.Assign) and len(n.targets) == 1
                    and isinstance(n.targets[0], ast.Name)):
                continue
            if not n.targets[0].id.lstrip("_").isupper():
                continue
            fp = _regex_fingerprint(n.value)
            if fp is None:
                try:
                    v = ast.literal_eval(n.value)
                except (ValueError, SyntaxError, TypeError):
                    continue
                # 只看非标量：整数天然会撞，结构相同才说明是同一件事。
                if isinstance(v, (list, tuple, set, dict)) and len(v) >= 2:
                    pass
                elif isinstance(v, str) and len(v) >= 12:
                    pass
                else:
                    continue
                fp = _fingerprint(v)
            homes[fp].append((p.name, n.targets[0].id))
    return homes


def shared_values() -> dict:
    """只留住在多个文件里的那些。"""
    return {k: v for k, v in all_homes().items()
            if len({f for f, _n in v}) > 1}


class EverySharedValueIsAccountedFor(unittest.TestCase):

    HOW = ("改法：能 import 的就 import 正本；不能的（doctor 那条硬契约）"
           "写一条断言钉住相等，再把它记进 ALLOWED 并注明谁在钉")

    def test_the_net_catches_compiled_regexes(self):
        """**先证明网里有正则**——它们原来整类被 `literal_eval` 挡在外面。

        少了这条，`_regex_fingerprint` 整个失效也没人知道：筛过的结果里
        少一组，而「少一组」正是这条守卫绿的样子。
        """
        n = sum(1 for k in all_homes() if k[0] == "regex")
        self.assertGreater(n, 30, f"只认出 {n} 条顶层正则，抽取器八成坏了")

    def test_the_flags_are_part_of_the_value(self):
        """同一个模式配 `re.M` 和不配，不是同一个判断 ——指纹要分得开。

        这一条**没有语料能变异出来**（今天全 `tools/` 里没有这样一对），
        所以直接钉：不写它，旗标从指纹里掉出去也一声不响，而那正是把两个
        不同的判断并成「同一个值」的样子。
        """
        def fp(src):
            return _regex_fingerprint(ast.parse(src).body[0].value)

        plain = fp('re.compile("^a")')
        flagged = fp('re.compile("^a", re.M)')
        self.assertIsNotNone(plain)
        self.assertNotEqual(plain, flagged, "旗标没进指纹")
        self.assertIsNone(fp('foo.compile("^a")'), "认错了别人的 compile")
        self.assertIsNone(fp('re.compile(PAT)'), "模式不是字面量时无从比较")

    def test_no_undeclared_copy(self):
        found = shared_values()
        extra = sorted(set(found) - set(ALLOWED))
        self.assertEqual(
            extra, [],
            "这些值住在多个模块里，而没人说清为什么、也没人钉住它们相等："
            + "；".join(f"{t} {v[:60]} -> "
                       + "、".join(f"{f}:{n}" for f, n in found[(t, v)])
                       for t, v in extra) + "。" + self.HOW)

    def test_no_extra_home_for_a_known_value(self):
        """已知的值也不许悄悄多一家 —— 只按值索引的话，第三家进来是无声的。"""
        found = shared_values()
        bad = []
        for k, (homes, _why) in ALLOWED.items():
            got = {f"{f}:{n}" for f, n in found.get(k, [])}
            if got and got != homes:
                bad.append(f"{k[1][:40]}：申报 {sorted(homes)}，实际 {sorted(got)}")
        self.assertEqual(bad, [], "；".join(bad) + "。" + self.HOW)

    def test_the_table_does_not_rot(self):
        """表里列了、实际已经合并掉的也要清 —— 过期的例外比没有更坏。"""
        gone = sorted(set(ALLOWED) - set(shared_values()))
        self.assertEqual(gone, [],
                         "ALLOWED 里这几组已经不是一值多家了：" + repr(gone))

    def test_every_entry_names_who_pins_it(self):
        for k, (_homes, why) in ALLOWED.items():
            with self.subTest(k=k):
                self.assertIn("钉住", why, "没说谁在盯，这条例外等于放行")


class ThePinsActuallyHold(unittest.TestCase):
    """例外表里承诺的那几条断言，真的存在且成立。"""

    def test_the_out_prefixes_match(self):
        """这一条此前**没有任何东西钉着** —— 名字不同，按名字扫的守卫看不见。"""
        self.assertEqual(tuple(doctor._OUT_PREFIXES),
                         tuple(_cli.GATE_FAIL_PREFIXES))

    def test_the_agency_words_match(self):
        self.assertEqual(tuple(doctor.AGENCY_WORDS), tuple(_cli._AGENCY_WORDS))

    def test_the_interview_statuses_match(self):
        self.assertEqual(set(doctor.INTERVIEW_STATUSES),
                         set(bd._INTERVIEW_STATUSES))

    def test_the_date_formats_match(self):
        import followups
        self.assertEqual(tuple(doctor.DATE_FORMATS),
                         tuple(followups._DATE_FORMATS))

    def test_the_bash_fence_pattern_matches(self):
        """两份「什么算一段 bash 围栏」必须认同一段文本。

        旗标也要比：少了 `re.S`，`(.*?)` 不再跨行，围栏里第二条命令就悄悄取不到
        —— 派生出来的壳缺一条权限，而缺权限的症状是「跑到那一步才要用户手批」。
        """
        import _entries
        import lint_skills
        self.assertEqual(_entries._FENCE.pattern, lint_skills._FENCE_CMD.pattern)
        self.assertEqual(_entries._FENCE.flags, lint_skills._FENCE_CMD.flags)

    def test_the_shell_families_match(self):
        """两份「两族技能壳的根」必须是同样两个目录，顺序也算。

        为什么会有第二份：`lint_skills.py` 要能单独拷进临时目录跑，正本 import 不过去。
        分叉的后果不是报错而是**查错地方** —— 生成器往 `.claude` + `.agents` 落两族，
        而 lint 若写成别的两个名字，它那条「两族壳集合一致」守卫就在数两个空目录，
        数完永远相等。
        """
        import _entries
        import lint_skills
        self.assertEqual(_entries.SHELL_FAMILIES, lint_skills.SHELL_FAMILIES)

    def test_the_hand_written_shells_match(self):
        """lint 那份「手写、不生成的壳」名单必须与正本同一个集合。

        同一个「不能 import 兄弟模块」的契约，同一条手工钉法。**它不在 ALLOWED 里**
        不是漏登记：上面那张网只收 ≥2 项的容器（`all_homes()` 的 `len(v) >= 2`），
        今天只有一个名字的 frozenset 根本不进网 —— 把它的指纹写进例外表反而会撞
        `test_the_table_does_not_rot`（表里不许留已经不成对的例外）。所以照
        `test_the_shell_families_match` 的样子直接比。

        分叉的后果与 SHELL_FAMILIES 那条同型但更安静：lint 的名单若是空的，那条
        「两族都有壳、没有正文」的判据会对真实存在的 `job-application-assistant`
        路由壳报红（ healthy 仓库红，改法是去删正则而不是补名单）；名单若多出
        一个还在生成的命令名，那条判据就对**它**永远沉默。
        """
        import _entries
        import lint_skills
        self.assertEqual(set(_entries.HANDWRITTEN_NAMES),
                         set(lint_skills.HANDWRITTEN_SHELLS))


if __name__ == "__main__":
    unittest.main()
