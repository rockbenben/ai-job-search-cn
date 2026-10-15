# -*- coding: utf-8 -*-
"""`doctor.py` 里的副本要和正本**判得一样**。

## 这条守卫此前被引用了两次，而它一直不存在

`tools/doctor.py` 写着「相等由 `test_the_copies_in_doctor_still_match` 钉住」，
`tests/test_one_value_one_home.py` 的说明也拿它当「按名字扫的那一条」来对比 ——
**全仓查无此函数**。声称有守卫比没有守卫更糟：读的人以为验过了，就不再去看。

代价当场就在：2026-08-23 给 `build_dashboard.is_out_verdict` 补了「已下线」
那一档（它自己的 docstring 记着那次实测），**`doctor` 那份没跟**。
2026-08-31 在真语料上比出 4 个岗两边判得不一样。

## 判据是**行为一致**，不是函数体一致

`doctor.py` 顶上那条契约是「不 import 本仓库的任何模块」，所以它引的是自己那份
常量副本（`_OUT_PREFIXES` 而不是 `_cli.GATE_FAIL_PREFIXES`）—— 函数体注定不同字，
按文本比会永远红。**钉行为**：同一批输入喂进去，两边给同一个答案。

这也是本仓库刚在别处交过的学费：守卫钉实现位置，等于把重构本身判成违规。

## 新出现的同名函数要登记

下面那条派生扫描不许有「同名、同义、却没人比过」的漏网：`doctor` 里任何与别处
同名的顶层函数，要么在 `JUDGED` 里写明由哪条断言比、要么在 `DIFFERENT_MEANING`
里写明同名不同义。入口名（`main` / `run`）不算共享判断，整类排除。

## 常量那一半原来整条不在扫描里

扫描只看**顶层函数** —— 而 `doctor` 的副本里数量更多、后果更直接的是**常量**：
`RESUME_STALE_DAYS`、`QUIET_DAYS`、`NO_REPLY_ALARM` 都是印在屏幕上的门槛，
一边 14 一边 15，用户看到的就是两句互相矛盾的话。

实测 2026-08-31 补上这一半时当场抓到一个漏网：**`doctor.LINK_LINE`** ——
和 `_cli.LINK_LINE` 同值、同义、逐字抄的一份正则，doctor 那行注释也写着
「与 `_cli.LINK_LINE` 同值」，而**没有任何一条断言比过它们**。
（另外三个是真被钉着的，只是钉在别的文件里 —— 所以登记表的值允许指向外部测试，
`test_the_named_guards_exist` 负责证明那些名字真的存在。）

## 登记表指名的守卫必须真的存在

「声称有守卫，守卫不存在」正是本文件开头那段学费。登记表本身也会犯同一个错：
写一个测试名进去、那个测试后来被改名或删掉，登记表看起来仍然完整。
所以每个名字都要能在 `tests/` 下找到，且它所在的文件真提到被钉的那个名字。
"""
import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
import _cli            # noqa: E402
import build_dashboard as bd   # noqa: E402
import doctor          # noqa: E402

#: 命令行入口，天生各不相同 —— 它们不是「共享的判断」，整类排除。
ENTRY_POINTS = {"main", "run"}

#: 同名、且确实是同一个问题：值是「谁在比」。
JUDGED = {
    "is_out_verdict": "test_is_out_verdict_agrees",
    "norm_url": "test_norm_url_agrees",
    "detect_code_tool": "test_detect_code_tool_agrees_between_doctor_and_cli",
}

#: 同名不同义 —— 各写各的是对的，值是理由。
DIFFERENT_MEANING = {
    "next_step": "doctor 的是终端最后那句「下一步做什么」（整轮一条）；"
                 "build_dashboard 的是逐岗那一行的下一步。",
}


#: 每个模块都有一个，指的是自己那份仓库根 —— 不是共享判断，整类排除。
PER_MODULE = {"ROOT"}

#: **同值、不同名**的副本：`(doctor 里叫什么, 正本模块, 正本叫什么, 是什么)`。
#:
#: 上面两条扫描按**名字**找副本，所以改了名的抄件整类漏掉 —— `doctor.py`
#: 自己在 `placeholders` 的 docstring 里记着这个洞（「同值、**不同名**，
#: 所以按名字找副本的那条守卫看不见它」），而那一个是**人工**发现的。
#: 2026-09-01 按值扫一遍，同类的还有下面五对，一对都没被钉过。
#:
#: 后果不是抽象的：`AGENCY_WORDS` 一边多一个词，同一个招聘方在终端判「猎头」、
#: 在面板判「直招」；`_OUT_PREFIXES` 分叉则是同一个岗一边算出局一边算在跑。
ALIASED_COPIES = [
    ("DATE_FORMATS", "followups", "_DATE_FORMATS", "人手填的台账里的日期写法"),
    ("_OUT_PREFIXES", "_cli", "GATE_FAIL_PREFIXES", "判词里「没过硬性条件」的前缀"),
    ("INTERVIEW_STATUSES", "build_dashboard", "_INTERVIEW_STATUSES", "算进面试的状态"),
    ("AGENCY_WORDS", "_cli", "_AGENCY_WORDS", "招聘方名字里的中介词"),
    ("OFFER_STATUSES", "build_dashboard", "_OFFER_STATUSES", "算进 offer 的状态"),
]

#: 按值扫时要忽略的类型：**纯数字撞车绝大多数是巧合**。
#: 14 同时是「简历多久算旧」「归档多久算死」「国庆后几天」；20 同时是
#: 「零回音报警线」和「算 JD 命中率的最少样本数」。把它们塞进登记表
#: 只会让表变成噪音，而噪音会让人不再读它。**只扫字符串集合** ——
#: 上面五对全是，而 14 / 20 / 30 / 60 那些一个都不是。
def _str_collection(v) -> bool:
    return (isinstance(v, (tuple, list, set, frozenset)) and len(v) > 1
            and all(isinstance(x, str) for x in v))

#: 同名常量：值是「谁在比」。**允许指向别的文件里的测试** ——
#: 那三个门槛本来就钉在各自那条流程的守卫里，搬过来只会多一份。
#: `test_the_named_guards_exist` 保证这些名字不是空头支票。
JUDGED_CONSTANTS = {
    "LINK_LINE": "test_link_line_agrees",
    "RESUME_STALE_DAYS": "test_the_thresholds_match",
    "QUIET_DAYS": "test_the_silence_line_has_one_value",
    "NO_REPLY_ALARM": "test_the_alarm_threshold_has_one_value",
    # 2026-10-14：自检接上「名单见底时补货优先于先发」那一支时加的。
    # `doctor` 按硬约定不 import 仓库模块，所以这个门槛是一份**正当副本**。
    # 它比前三个更险一点：那三个印的是一句话里的数字，这个决定的是
    # **「手上还有材料没投的时候，到底叫他先发还是先补」**——
    # 两处各写一个数，差一个就足以让两个出口在这个状态下给相反的答案。
    "SHORTLIST_FLOOR": "test_doctors_floor_is_the_same_number",
}


def _toplevel_functions(path: Path) -> set:
    return {n.name for n in ast.parse(path.read_text(encoding="utf-8")).body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _toplevel_values(path: Path) -> dict:
    """模块级 `名字 -> 字面值`。求不出值的（函数调用、推导式）跳过。

    `re.compile("…")` 取它的 pattern —— 副本常以编译好的正则形态出现，
    只看裸字面量会漏掉一整类。
    """
    out = {}
    for n in ast.parse(path.read_text(encoding="utf-8")).body:
        if not isinstance(n, ast.Assign):
            continue
        v = n.value
        if (isinstance(v, ast.Call) and getattr(v.func, "attr", "") == "compile"
                and v.args):
            v = v.args[0]
        try:
            val = ast.literal_eval(v)
        except Exception:
            continue
        for t in n.targets:
            if isinstance(t, ast.Name):
                out[t.id] = val
    return out


def _toplevel_constants(path: Path) -> set:
    """顶层的全大写赋值。小写的模块级变量是实现细节，不算共享的判断。"""
    return {t.id
            for n in ast.parse(path.read_text(encoding="utf-8")).body
            if isinstance(n, ast.Assign)
            for t in n.targets
            if isinstance(t, ast.Name) and t.id.isupper()}


class EverySharedNameIsAccountedFor(unittest.TestCase):
    """漏网检测：新加一个同名函数而不登记，这里当场红。"""

    def test_no_unregistered_shared_name(self):
        mine = _toplevel_functions(TOOLS / "doctor.py") - ENTRY_POINTS
        shared = set()
        for f in sorted(TOOLS.glob("*.py")):
            if f.name == "doctor.py":
                continue
            shared |= mine & _toplevel_functions(f)
        unknown = shared - set(JUDGED) - set(DIFFERENT_MEANING)
        self.assertEqual(
            unknown, set(),
            "doctor 里这些函数与别处同名，却没人说清是同一个问题还是同名不同义："
            + repr(sorted(unknown)))

    def test_no_unregistered_shared_constant(self):
        """常量那一半 —— 原来整条不在扫描里，当场漏掉了 `LINK_LINE`。"""
        mine = _toplevel_constants(TOOLS / "doctor.py") - PER_MODULE
        # **先证明扫描看得见东西。** 抽取器返回空集时，下面那条在空集上
        # 永远绿 —— 这个仓库给这个形状起过名字：「写了、跑着、绿着，
        # 但看不见」。变异当场照出来：把全大写那个条件改成 `False`，
        # 整条守卫一声不响。
        self.assertGreater(len(mine), 10,
                           f"只扫到 {len(mine)} 个顶层常量，抽取器八成坏了")
        shared = set()
        for f in sorted(TOOLS.glob("*.py")):
            if f.name == "doctor.py":
                continue
            shared |= mine & _toplevel_constants(f)
        unknown = shared - set(JUDGED_CONSTANTS)
        self.assertEqual(
            unknown, set(),
            "doctor 里这些常量与别处同名，却没人说清由谁比："
            + repr(sorted(unknown)))

    def test_the_aliased_copies_still_hold_the_same_value(self):
        """改了名的抄件仍要和正本同值 —— 这一条是**唯一**在比它们的东西。"""
        import importlib
        for mine, mod_name, theirs, what in ALIASED_COPIES:
            with self.subTest(copy=mine, source=f"{mod_name}.{theirs}"):
                mod = importlib.import_module(mod_name)
                a = getattr(doctor, mine, None)
                b = getattr(mod, theirs, None)
                self.assertIsNotNone(a, f"doctor 里没有 {mine} 了 —— 登记表过期")
                self.assertIsNotNone(
                    b, f"{mod_name} 里没有 {theirs} 了 —— 登记表过期")
                # **有序的按顺序比。** `DATE_FORMATS` 是逐个 strptime 试过去的，
                # 重排会改解析优先级 —— 拿 set 比就看不见这种改动。
                ordered = isinstance(a, (tuple, list)) and isinstance(b, (tuple, list))
                self.assertEqual(
                    list(a) if ordered else set(a),
                    list(b) if ordered else set(b),
                    f"{what}：doctor.{mine} 与 {mod_name}.{theirs} 分叉了")

    def test_no_unregistered_aliased_copy(self):
        """按**值**扫一遍：doctor 的字符串集合与别处同值却没登记的，当场红。

        名字不同也躲不过 —— 这正是按名字扫的那两条看不见的那一类。
        """
        mine = {n: v for n, v in _toplevel_values(TOOLS / "doctor.py").items()
                if _str_collection(v)}
        self.assertGreater(len(mine), 3,
                           f"只扫到 {len(mine)} 个字符串集合，抽取器八成坏了")
        known = {(m, mod, t) for m, mod, t, _ in ALIASED_COPIES}
        unknown = []
        for f in sorted(TOOLS.glob("*.py")):
            if f.name == "doctor.py":
                continue
            for n, v in _toplevel_values(f).items():
                if not _str_collection(v):
                    continue
                for mn, mv in mine.items():
                    if set(mv) != set(v):
                        continue
                    if mn == n:
                        continue        # 同名的归上面两条扫描管
                    if (mn, f.stem, n) in known:
                        continue
                    unknown.append(f"doctor.{mn} == {f.stem}.{n}")
        self.assertEqual(
            sorted(set(unknown)), [],
            "这些副本同值、不同名，没人说清谁是正本、由谁比：" + repr(sorted(set(unknown))))

    def test_the_named_guards_exist(self):
        """登记表不许写空头支票 —— 指名的测试要真在，且**它自己**比的就是它。

        「那个文件提到过这个名字」不够。第一版就是这么写的，而登记表本身
        住在这个文件里 —— 于是任何名字都能在这里找到，把 `NO_REPLY_ALARM`
        指向 `test_norm_url_agrees` 照样绿。**判据收到函数体这一级**：
        断言里没出现那个名字，就说明它比的不是这件事。
        """
        here = Path(__file__).resolve().parent
        bodies = {}
        for f in sorted(here.glob("test_*.py")):
            src = f.read_text(encoding="utf-8")
            for node in ast.walk(ast.parse(src)):
                if isinstance(node, ast.FunctionDef):
                    bodies.setdefault(node.name, []).append(
                        ast.get_source_segment(src, node) or "")
        for name, guard in {**JUDGED, **JUDGED_CONSTANTS}.items():
            with self.subTest(name):
                self.assertIn(guard, bodies,
                              guard + " 找不到 —— 登记表指着一条不存在的守卫")
                self.assertTrue(
                    any(name in b for b in bodies[guard]),
                    guard + " 的函数体里根本没出现 " + name
                    + " —— 它比的不是这件事")

    def test_the_table_is_not_stale(self):
        """反过来也要真：登记了却已经不同名，说明表该清了。"""
        mine = _toplevel_functions(TOOLS / "doctor.py")
        for name in list(JUDGED) + list(DIFFERENT_MEANING):
            with self.subTest(name):
                self.assertIn(name, mine, name + " 已经不在 doctor.py 里了")
        consts = _toplevel_constants(TOOLS / "doctor.py")
        for name in JUDGED_CONSTANTS:
            with self.subTest(name):
                self.assertIn(name, consts, name + " 已经不在 doctor.py 里了")


class TheCopiesInDoctorStillMatch(unittest.TestCase):
    """两边对同一批输入给同一个答案。"""

    #: 判词语料：正本那两张表 + 真实数据里出现过的形状 + 边界。
    VERDICTS = (
        list(_cli.GATE_FAIL_PREFIXES)
        + [p + " (学历)" for p in _cli.GATE_FAIL_PREFIXES]      # 带门名后缀
        + list(_cli.VERDICTS)                                  # 五档正本
        + ["粗筛：" + v for v in _cli.VERDICTS]                 # 带粗筛前缀
        + ["已评分", "已下线", "已下线（页面写着「职位已关闭」）",
           "", "   ", None]
    )
    # ⚠️ 五档**不许在这里再抄一遍** —— `test_shared_vocab_single_source`
    # 当场把第一版抓了红：正本是 `_cli.VERDICTS`，抄一份就等着两边分叉。
    # 写这条守卫时自己犯了它要防的那个错，记在这儿。

    def test_is_out_verdict_agrees(self):
        """2026-08-23 给 `build_dashboard` 补的「已下线」那一档，副本要跟上。"""
        bad = [v for v in self.VERDICTS
               if doctor.is_out_verdict(v) != bd.is_out_verdict(v)]
        self.assertEqual(bad, [],
                         "两份 is_out_verdict 判得不一样：" + repr(bad))

    def test_the_corpus_reaches_the_case_that_drifted(self):
        """判据自检：语料里得真有「已下线」，否则这条断言是空的。"""
        self.assertTrue(
            any(isinstance(v, str) and v.startswith("已下线")
                for v in self.VERDICTS),
            "语料里没有「已下线」—— 那正是飘掉的那一档")
        self.assertTrue(bd.is_out_verdict("已下线"), "正本自己都不认它了？")

    def test_norm_url_agrees(self):
        """URL 归一化：去重键、匹配材料目录、面板对表全靠它。"""
        urls = [
            "https://www.liepin.com/job/123.shtml",
            "https://www.liepin.com/job/123.shtml?utm_source=x&d=1",
            "http://WWW.Liepin.com/job/123.shtml/",
            "https://www.zhipin.com/job_detail/abc.html#anchor",
            "https://jobs.51job.com/x/1.html?from=search",
            "", "   ", "not a url", None,
        ]
        bad = [u for u in urls if doctor.norm_url(u) != _cli.norm_url(u)]
        self.assertEqual(bad, [], "两份 norm_url 归一化得不一样：" + repr(bad))

    def test_link_line_agrees(self):
        """话术与评估里那行「职位链接：」—— 两份正则要认同一批写法。

        它决定审计能不能点名「哪个岗」，也决定 `doctor` 数得出「备好没发」
        的是哪几个。认不出来不会报错，只会静默少算。
        """
        lines = [
            "职位链接：https://www.liepin.com/job/1.shtml",
            "职位链接: https://www.zhipin.com/job_detail/a.html",
            "职位链接　：  https://jobs.51job.com/all/2.html",
            # 加粗那种写法**两边都不认**，这是有意的：实测 596 行真实的
            # 「职位链接」里 0 行是加粗形态（586 行 `- 职位链接：`、8 行裸写、
            # 2 行跟在评估日期后面），读不出来的行也是 0。写在这儿是为了
            # 钉住「两边一致」，不是为了将来把它加进去。
            "**职位链接**：https://x.com/y",
            "原始链接：https://x.com/y",       # 另一个字样，两边都不该认
            "职位链接：", "没有链接的一行", "",
        ]

        def got(rx, ln):
            m = rx.search(ln)
            return m.group(1) if m else None

        bad = [ln for ln in lines
               if got(doctor.LINK_LINE, ln) != got(_cli.LINK_LINE, ln)]
        self.assertEqual(bad, [], "两份 LINK_LINE 读出来不一样：" + repr(bad))
        # 判据自检：**两头都要有**。全读不出来时上面在空集上永远绿；
        # 全读得出来时，一个「什么都认」的正则也照样绿。
        hit = [ln for ln in lines if got(_cli.LINK_LINE, ln)]
        self.assertGreaterEqual(len(hit), 3, "语料没覆盖到能读出链接的写法")
        self.assertLess(len(hit), len(lines), "语料里没有该读不出来的行")


if __name__ == "__main__":
    unittest.main()
