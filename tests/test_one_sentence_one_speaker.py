# -*- coding: utf-8 -*-
"""给用户看的同一句话，不许有两个生产者。

`test_one_value_one_home` 盯的是**常量**，`test_the_copies_in_doctor_still_match`
盯的是**同名的函数与顶层常量**。两张网都按**名字**捞 —— 而这个仓库反复栽的那个
形状，捞不着的正是**函数体里那句写死的话**：它没有名字。

实测（2026-09-01 这一遍扫出来的，都是当天修掉的）：

    「试运行，没有写盘。确认无误后加 --apply」      7 个工具各写一份
    「投递记录里找不到这一行了——刷新一下页面再试」  tracker 里两份
    「…指向同一职位链接，面板只显示…」             连同它上面那段挑目录的
                                                   逻辑，两个文件里逐字各一份

最后那一组不只是一句话：**挑哪个目录更全是判断**，两份判断迟早分叉 ——
一边改了排序键，另一边照旧，同一份数据两个面板显示不同的目录，
而警告还都说「面板只显示 X」。

## 判据

`tools/*.py` 里的字符串字面量（**不含 docstring** —— 那是解释，本来就该引用），
去掉 `{...}` 占位后仍有 `MIN_CJK` 个以上汉字的，按内容归组；
落在两个以上「文件 + 函数」里就红，除非登记在 `ALLOWED` 里。

⚠️ **登记表是例外清单，不是副本清单。** 允许的每一条都要有人钉着它们相等 ——
`doctor` 那两条就是这么来的（它按硬约定不 import 仓库任何模块，只能持副本）。
"""
import ast
import pathlib
import re
import sys
import unittest
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402
import build_dashboard as bd  # noqa: E402
import doctor  # noqa: E402

#: 短句天然会撞（「已投递」「没有活动用户」这种），收进来全是噪音。
MIN_CJK = 12

CJK = re.compile("[一-鿿]")
HOLE = re.compile(r"\{[^{}]*\}")

#: 允许两个生产者的那几句：句子片段 → (住址集合, 谁在钉它们相等)。
ALLOWED = {
    "还没建档，切过去是空的 —— 不要了就 /job-user --remove": (
        {"_cli.py:user_list_line", "doctor.py:check_repo"},
        "doctor 按硬约定不 import 仓库模块，只能持副本；"
        "相等由本文件 test_the_empty_user_line_agrees 钉住"),
    "个岗在你发出去之前就下线了，那几份白做了": (
        {"build_dashboard.py:_ready_text", "doctor.py:ready_note"},
        "同上；相等由本文件 test_the_wasted_materials_line_agrees 钉住。"
        "这一句 2026-09-01 刚从 season_note 搬进 _ready_text——"
        "面板那份挂在季节上，季节一变整句消失，而终端那份从来只问「有没有」"),
    # 2026-10-14：终端自检接上面「补货优先于先发」那一支时，两句话开始有两个
    # 生产者 —— **而这正是要的那个形状**：同一个状态下两个出口必须说同一句话，
    # 否则用户看哪个算哪个。逐字相同不是巧合，是这里唯一的防分叉手段。
    #
    # 键名要照 `norm()` 切出来的**片段**写，不是照原句：`{...}` 被摘掉之后，
    # 一句话会被切成好几段。照整句写会一条都匹配不上，而
    # `test_the_registry_is_not_stale` 只验「键能命中某句」、不验「命中的是
    # 你要那一句」—— 写错时它照样绿，而失败信息会把人指向完全另一句话。
    "越少越不该停下找岗": (
        {"build_dashboard.py:next_step", "doctor.py:next_step"},
        "同一状态下两个出口必须给同一个答案；相等由 "
        "`tests/test_both_next_steps_agree.py::RestockingOutranksSendingWhenTheListIsThin` 钉住"),
    "可以投的名单快见底": (
        {"build_dashboard.py:next_step", "doctor.py:next_step"},
        "同上；没有它，「有待评积压就先评库存」那条只在一个出口有防护，"
        "`/job-scrape` → `/job-scrape` 死循环就是从那儿漏的"),
    # 同一句话的**后半段**是另一个片段：`{n_unranked}` 把句子切成了三段，
    # 每一段各自入库，所以登记也得逐段给。少一段，那一段照样红。
    "把库存评完，不够再抓": (
        {"build_dashboard.py:next_step", "doctor.py:next_step"},
        "同上；同一句的后半段"),
}


def norm(s: str) -> str:
    return HOLE.sub("｟｠", s).strip()


def cjk_len(s: str) -> int:
    return len(CJK.findall(s))


def _doc_ids(tree) -> set:
    out = set()
    for n in ast.walk(tree):
        if not isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef,
                              ast.AsyncFunctionDef)):
            continue
        b = getattr(n, "body", None)
        if (b and isinstance(b[0], ast.Expr)
                and isinstance(b[0].value, ast.Constant)
                and isinstance(b[0].value.value, str)):
            out.add(id(b[0].value))
    return out


def speakers() -> dict:
    """句子 → `{"文件:函数"}`，全 `tools/`。"""
    homes = defaultdict(set)
    for p in sorted((ROOT / "tools").glob("*.py")):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        owner = {}
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for n in ast.walk(fn):
                    owner.setdefault(n, fn.name)
        docs = _doc_ids(tree)
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Constant) and isinstance(n.value, str)):
                continue
            if id(n) in docs:
                continue
            # **只管函数体里那句写死的话。** 模块级的字面量（`CHECKS` 里的
            # 检查名、各种表）归 `test_one_value_one_home` 按值扫 ——
            # 两张网重叠只会互相报对方的东西：实测「资料：境外学历没写认证
            # 进度」既是 `--only` 的选择器、又是那条检查的报文标题，
            # **同字是巧合**（另一条检查那两处就是不同的），改一处也不会
            # 弄坏另一处。
            if n not in owner:
                continue
            v = norm(n.value)
            if cjk_len(v) < MIN_CJK:
                continue
            homes[v].add(f"{p.name}:{owner.get(n, '<module>')}")
    return homes


class EverySentenceHasOneSpeaker(unittest.TestCase):

    def setUp(self):
        self.homes = speakers()
        # **先证明抽取器看得见东西。** 空集上的断言永远绿 —— 这个仓库
        # 给这个形状起过名字：「写了、跑着、绿着，但看不见」。
        self.assertGreater(len(self.homes), 300,
                           f"只扫到 {len(self.homes)} 句，抽取器八成坏了")

    def test_no_sentence_is_said_by_two(self):
        bad = []
        for text, who in sorted(self.homes.items()):
            if len(who) < 2:
                continue
            hit = next((v for k, v in ALLOWED.items() if k in text), None)
            if hit and who <= hit[0]:
                continue
            bad.append(f"{text[:50]} ← {'、'.join(sorted(who))}")
        self.assertEqual(bad, [], "这几句话有两个生产者，改一处忘一处只是时间问题"
                                  "（真该有两份就登记进 ALLOWED 并写明谁钉着）：\n  "
                                  + "\n  ".join(bad))

    def test_the_registry_is_not_stale(self):
        """登记表不许留着已经不成立的条目 —— 那会遮住真的重复。"""
        for text, (who, _why) in ALLOWED.items():
            with self.subTest(text=text[:24]):
                got = {k: v for k, v in self.homes.items() if text in k}
                self.assertTrue(got, f"这一句已经不在代码里了：{text[:30]}")
                seen = set().union(*got.values())
                self.assertEqual(
                    seen, who,
                    f"住址变了，登记表没跟：{text[:30]}")


class TheAllowedCopiesReallyAgree(unittest.TestCase):
    """例外清单上的每一条，都要有人现算着比。"""

    def test_the_empty_user_line_agrees(self):
        """摆一个空壳用户出来，看正本怎么说；再看 doctor 那份一不一样。"""
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            (root / "users" / "空壳" / "profile").mkdir(parents=True)
            line = _cli.user_list_line(root)
        self.assertIn("还没建档，切过去是空的", line,
                      "正本没说这句话 —— 底下那半条就是在空集上断言")
        src = (ROOT / "tools" / "doctor.py").read_text(encoding="utf-8")
        self.assertIn("还没建档，切过去是空的 —— 不要了就 /job-user --remove", src,
                      "doctor 那份和 _cli 正本的措辞分叉了")

    def test_the_wasted_materials_line_agrees(self):
        """两个入口对同一件事必须说同一句话。"""
        panel = bd._ready_text(62, 30, 0, None, 11)
        self.assertIn("11 个岗在你发出去之前就下线了，那几份白做了", panel)
        src = (ROOT / "tools" / "doctor.py").read_text(encoding="utf-8")
        self.assertIn("个岗在你发出去之前就下线了，那几份白做了", src,
                      "终端那份和面板正本的措辞分叉了")

    def test_the_terminal_says_it_whatever_the_season(self):
        """**这才是那次事故的判据。** 面板那份原来挂在季节上，
        终端这份从来只问「有没有」—— 两边现在同一条判据。

        钉行为：同一份材料，换两个季节（八月淡季 / 九月旺季）各问一次，
        那句话都要在。第一版钉的是 `doctor.ready_note` 里 `if a.get("lost")`
        那一行，被 `test_a_guard_pins_behaviour_not_a_line` 当场拦下 ——
        拦得对，改这一行的写法它就红，而行为一点没变。
        """
        import datetime as _dt
        import json
        import tempfile
        gone = {"materials": {"greeting": "x"}, "applied": None,
                "dupOf": None, "skipped": False, "expired": True,
                "queuedDays": 30, "queuedLong": True}
        # **手上还得有活的那几份。** `ready_note` 先看 `n`（还能发的有几个），
        # 一个都没有就整句不说 —— 只喂已下线的，它返回空串，这一条会红在
        # 「什么都没说」上，而不是红在季节上。
        live = dict(gone, expired=False, queuedDays=9, queuedLong=False)
        with tempfile.TemporaryDirectory() as d:
            tmp = pathlib.Path(d)
            (tmp / "web" / "public").mkdir(parents=True)
            udir = tmp / "users" / "甲"
            udir.mkdir(parents=True)
            (tmp / "web" / "public" / "data.json").write_text(
                json.dumps({"activeUser": "甲",
                            "jobs": [gone] * 3 + [live] * 4},
                           ensure_ascii=False), encoding="utf-8")
            for day in (_dt.date(2026, 8, 1), _dt.date(2026, 9, 10)):
                with self.subTest(day=day):
                    self.assertIn("在你发出去之前就下线了",
                                  doctor.ready_note(udir, day),
                                  "换个季节这句话就没了 —— 那正是面板栽的那一下")


class TheSharedPickerHasOneHome(unittest.TestCase):
    """同一链接下挑哪个投递目录 —— 那不只是一句话，是一个判断。"""

    def test_both_entry_points_call_it(self):
        ex = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
        bdsrc = (ROOT / "tools" / "build_dashboard.py").read_text(
            encoding="utf-8")
        self.assertIn("dedup_apps_by_url(all_apps)", ex)
        self.assertIn("dedup_apps_by_url(apps)", bdsrc)
        # 生产者只许一个：那句警告只能由正本拼出来。
        made = [ln for ln in bdsrc.splitlines() + ex.splitlines()
                if "指向同一职位链接" in ln and 'f"' in ln]
        self.assertEqual(len(made), 1, "那句警告又长出第二个生产者了")

    def test_it_keeps_the_richer_one(self):
        """留信息更全的那个 —— 后者胜出会把已经出好的 PDF 静默藏起来。"""
        thin = {"url": "u", "dir": "甲", "resume": False,
                "interview_preps": [], "outreach": None}
        rich = {"url": "u", "dir": "乙", "resume": True,
                "interview_preps": ["a"], "outreach": "x"}
        for order in ((thin, rich), (rich, thin)):
            with self.subTest(order=[a["dir"] for a in order]):
                got = bd.dedup_apps_by_url(list(order))
                self.assertEqual(got["u"]["dir"], "乙")

    def test_a_dir_without_a_url_is_dropped(self):
        self.assertEqual(bd.dedup_apps_by_url(
            [{"url": "", "dir": "甲", "resume": False,
              "interview_preps": [], "outreach": None}]), {})


if __name__ == "__main__":
    unittest.main()
