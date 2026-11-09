# -*- coding: utf-8 -*-
"""评分明细那一格写着「见某节」，而面板拿它当解释用。

`JobReadout` 把每一维的 `note` 按分数分进「对口的地方」和「要掂量的地方」两列
（`splitReasons`，≥70 进前者）。那一整块的用途它自己写着：「为什么是这个结论
（对口的地方 / 要掂量的地方，说人话）」。

所以一句「见「优势」「缺口」两节」会**渲染在那两节旁边** —— 指路指到了读者
已经在看的地方。

## 实测（2026-08-27）

1020 条计权维度的说明里 **238 条（23%）只是指路**，「见「优势」「缺口」两节」
一句就占 202 条。更要紧的是分布：**8 个岗**「要掂量的地方」那一列**整列都是
指路**，而且全是 75-78 分的高分岗 —— 用户最会点开的那几个。

## 根因不在执行者

`04` 的输出模板里，那张表给薪资 / 强度 / 发展三维写的是 **`...`**，只有技能与
经验那格写明了要求。**规格没说该填什么，填进去的就是占位。** 同一个形状本仓库
反复栽过：`deadline` 没有落点、`调整` 没有字段、`rank_breakdown` 不在落盘清单里
—— 值都产出来了，中间没有位置。

所以这次是两半一起做：**模板补齐三格的要求**（防新增），**自检盯存量**。
"""
import re
import sys
import pathlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import audit_pipeline as ap  # noqa: E402

SRC = (ROOT / "tools" / "audit_pipeline.py").read_text(encoding="utf-8")
FRAMEWORK = (ROOT / "workflows" / "reference"
             / "04-job-evaluation.md").read_text(encoding="utf-8")
READOUT = (ROOT / "web" / "src" / "components"
           / "JobReadout.tsx").read_text(encoding="utf-8")


def _run(jobs):
    """拿一份构造快照跑这条检查。"""
    import json
    import tempfile
    from unittest import mock
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "users" / "u" / "job_scraper" / "dashboard").mkdir(parents=True, exist_ok=True)
        (root / "users" / "u" / "job_scraper" / "dashboard" / "data.json").write_text(
            json.dumps({"activeUser": "u", "jobs": jobs}, ensure_ascii=False),
            encoding="utf-8")
        (root / "users" / "u").mkdir(parents=True, exist_ok=True)
        (root / ".active_user").write_text("u", encoding="utf-8")
        with mock.patch.object(ap, "ROOT", root), mock.patch.object(ap, "_USER", ["u"]):
            return ap.check_dimension_notes_explain_something({}, {})


def _dim(name, score, note, weighted=True):
    return {"name": name, "score": score, "note": note, "weighted": weighted}


class APointerIsNotAnExplanation(unittest.TestCase):
    def test_it_fires(self):
        got = _run([{"company": "蓝湾智投科技", "score": 78, "dimensions": [
            _dim("强度与公司性质", 50, "见「优势」「缺口」两节")]}])
        self.assertTrue(got, "整格只写了「见某节」却没报")
        self.assertIn("指路", got[0][1])
        self.assertIn("/job-apply", got[0][2], "没给该敲的那条命令")

    def test_all_the_measured_wordings_are_caught(self):
        """实测出现过的五种写法，一种都不能漏。"""
        for note in ("见「优势」「缺口」两节", "见下方结论", "见下",
                     "见下「优势」与「缺口」", "同上一条"):
            with self.subTest(note=note):
                got = _run([{"company": "蓝湾智投科技", "score": 70,
                             "dimensions": [_dim("发展与风险", 60, note)]}])
                self.assertTrue(got, f"「{note}」没被认出来")

    def test_a_real_basis_is_left_alone(self):
        got = _run([{"company": "蓝湾智投科技", "score": 78, "dimensions": [
            _dim("强度与公司性质", 50, "2000-5000 人、不需要融资；JD 未提任何工作制")]}])
        self.assertEqual(got, [])

    def test_an_empty_note_is_not_this_check(self):
        """一个字没写是另一件事（「深评缺小节」那条管）—— 这里只管「写了但等于没写」。"""
        got = _run([{"company": "蓝湾智投科技", "score": 78,
                     "dimensions": [_dim("强度与公司性质", 50, "")]}])
        self.assertEqual(got, [])

    def test_a_note_that_merely_mentions_another_section_is_fine(self):
        """判据是**开头**就在指路，不是提到了别处。

        一句「团队新建，具体见下方结论」是有内容的 —— 拿子串匹配会把它也扫掉，
        而这类检查误报一次就会被整条忽略。
        """
        got = _run([{"company": "蓝湾智投科技", "score": 78, "dimensions": [
            _dim("发展与风险", 55, "AI 落地是支撑职能而非主营收线，具体见下方结论")]}])
        self.assertEqual(got, [])


class TheWholeColumnCaseIsCalledOut(unittest.TestCase):
    """8 个岗整列都是指路 —— 那一列打开来一个字的解释都没有。"""

    def test_it_names_them(self):
        got = _run([{"company": "蓝湾智投科技", "score": 78, "dimensions": [
            _dim("强度与公司性质", 50, "见下"), _dim("技能与经验", 85, "专业能力 88")]}])
        self.assertIn("整列都是指路", got[0][2])
        self.assertIn("蓝湾智投科技", got[0][2])

    def test_one_real_note_in_the_column_is_enough_to_spare_it(self):
        got = _run([{"company": "蓝湾智投科技", "score": 78, "dimensions": [
            _dim("强度与公司性质", 50, "见下"),
            _dim("发展与风险", 60, "支撑职能，资源投入不确定")]}])
        self.assertNotIn("整列都是指路", got[0][2],
                         "那一列里有真说明，不该算「整列」")

    def test_the_high_scorers_come_first(self):
        """用户最会点开的是最高分那几个。"""
        jobs = [{"company": f"公司{i}", "score": s,
                 "dimensions": [_dim("发展与风险", 50, "见下")]}
                for i, s in enumerate((41, 78, 60))]
        msg = _run(jobs)[0][2]
        self.assertLess(msg.index("公司1"), msg.index("公司2"))


class TheCutMatchesTheFrontEnd(unittest.TestCase):
    """这里复刻了面板的分组切点。两边不等，「要掂量那一列」就认错了。"""

    def test_the_front_end_still_cuts_at_the_same_number(self):
        m = re.search(r"d\.score >= (\d+)", READOUT)
        self.assertIsNotNone(m, "面板那边的切点找不到了")
        self.assertEqual(int(m.group(1)), ap._PLUS_CUT)

    def test_the_copy_names_where_the_source_is(self):
        i = SRC.index("_PLUS_CUT = ")
        self.assertIn("JobReadout", SRC[max(0, i - 600):i],
                      "复刻了一个数却没说正本在哪")

    def test_the_source_states_its_own_derivation(self):
        """**正本自己要写出 70 是哪来的。**

        这个数的出处（粗筛四档 30/50/70/85，70 是其中最低的正面值）原来只写在
        `audit_pipeline` 那份**复刻件**的注释里，正本 `JobReadout.tsx` 只说
        「≥70 算对口」。后果 2026-08-27 当场发生：审计时把它认成了
        `gap_split.py` 里**被撤掉过**的那个 70（那次的问题是冒用 04 分档的名义），
        照着「04 的分档是 80/60/40，没有 70」把它改成了 60 —— 改完才被这个类拦下。

        **一个数的出处写在它的复刻件里，等于没写**：看正本的人看不到它。
        """
        i = READOUT.index("d.score >= 70")
        seg = READOUT[max(0, i - 1800):i]
        self.assertRegex(seg, r"30\s*/\s*50\s*/\s*70\s*/\s*85|粗筛四档",
                         "正本没说 70 是哪来的 —— 下一个人会拿 04 的分档去改它")
        self.assertRegex(seg, r"80/60/40|各维的分档",
                         "没点破它与 04 各维分档的区别，那正是认错的入口")


class TheTemplateNowSaysWhatGoesThere(unittest.TestCase):
    """防新增的那一半。规格里三格原来写的是 `...`。"""

    def _table(self):
        i = FRAMEWORK.index("### 评分明细")
        return FRAMEWORK[i:i + 1200]

    def test_no_placeholder_cell_is_left(self):
        table = self._table()
        for dim in ("薪资与职级", "强度与公司性质", "发展与风险"):
            row = next(ln for ln in table.splitlines() if ln.startswith(f"| {dim} "))
            with self.subTest(dim=dim):
                self.assertNotIn("| ... |", row, f"「{dim}」那一格还是占位符")

    def test_it_forbids_the_pointer(self):
        self.assertIn("这四格不许只写「见某节」", FRAMEWORK)

    def test_it_says_why_it_matters(self):
        """理由要留下 —— 不然下一个人会以为这是格式洁癖。"""
        self.assertIn("渲染在那两节旁边", FRAMEWORK)
        self.assertIn("规格没说该填什么", FRAMEWORK)


class TheBatchVoteHasADirection(unittest.TestCase):
    """`batch_note` 的第二个元素是「**这份有没有问题**」，别写反。

    这条检查报的是全库累计（238/1140 条说明只写「见某节」），而它自己那句
    「模板里那三格的要求 2026-08-27 已补齐」是一次**规则变更** ——
    累计数回答不了「那次补齐灵没灵」，只有「最近一批还犯不犯」能。

    接上时两处都写反了，两处都是当场看得出来的自相矛盾：

    ① 传了 `not _has_ptr`（「这份没问题」），于是印出「23 份里 23 份」；
    ② 票按 `_bad_here`（整列都是指路）投 —— 那是更严的子条件，
       全库只有 5 个岗命中，而标题报的是 1140 条**说明**里的 238 条。
       两个口径混着用，印出来的数和全库那 5 个对不上。

    改对之后是「最近一批（2026-08-27，23 份）里 **0 份**」—— 模板那次补齐
    生效了，而这正是累计数说不出来的那句话。
    """

    SRC = (pathlib.Path(__file__).resolve().parents[1]
           / "tools" / "audit_pipeline.py").read_text(encoding="utf-8")

    def test_batch_note_counts_problems_not_clean_ones(self):
        """契约本身：第二个元素为真 = 这份有问题。"""
        import audit_pipeline as ap
        rows = [("2026-08-30", True)] * 3 + [("2026-08-30", False)] * 7
        note = ap.batch_note(rows, min_size=5)
        self.assertIn("10 份", note)
        self.assertIn("里 3 份", note, "数的是「有问题的」，不是干净的")

    def test_a_clean_batch_reports_zero(self):
        import audit_pipeline as ap
        note = ap.batch_note([("2026-08-30", False)] * 9, min_size=5)
        self.assertIn("里 0 份", note)

    def _seg(self) -> str:
        i = self.SRC.index("def check_dimension_notes_explain_something")
        return self.SRC[i:self.SRC.index(chr(10) + "def ", i + 10)]

    def test_this_check_votes_the_right_way(self):
        seg = self._seg()
        self.assertIn("_rows.append((_d, _has_ptr))", seg,
                      "票写反了 —— batch_note 数的是有问题的那些")
        self.assertNotIn("not _has_ptr", seg)

    def test_the_vote_matches_the_headline(self):
        """票按「这一份有没有指路说明」投，和标题那个数同一个口径。

        按 `_bad_here`（整列都是指路）投是另一个更严的子条件 ——
        印出来会和全库那个数自相矛盾。
        """
        seg = self._seg()
        self.assertNotIn("_rows.append((_d, _bad_here))", seg)
        self.assertIn("_has_ptr = any(", seg)

    def test_it_is_actually_printed(self):
        """算了要真拼进报文 —— 「算了却没有消费者」这一课上一轮刚记过。"""
        seg = self._seg()
        ret = seg[seg.rindex('return [("warn"'):]
        self.assertIn("batch_note(_rows)", ret)


if __name__ == "__main__":
    unittest.main()
