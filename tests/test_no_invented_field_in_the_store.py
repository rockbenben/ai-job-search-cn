# -*- coding: utf-8 -*-
"""职位库里攒着两个谁也没定义过的字段。

## 实测 2026-08-31

热库 1839 条、存档若干，条目上出现过 42 个字段。其中 **40 个**在 `tools/` 或
`workflows/` 里能查到出处（要么代码取它，要么某条流程写明「谁在等它」）。
剩下两个**全仓查无出处**：

    _url_fixed   4 条   值是一句修复说明：「入库时把猎聘 10 位职位号截成了
                        9 位……9 位那个 URL 打开的是另一个岗」
    spread_of    3 条（热库）+ 若干（存档）  值是另一个岗的链接

两个都不是脏数据 —— 它们是**执行者当场记下来的真事**。问题在于：名字是临时起的，
没有任何代码或流程读它们，于是那两件事记了等于没记。

`spread_of` 尤其可惜：它指的那几对，导出器的自动去重（「公司 + JD 正文前 300 字」）
**一对都没认出来**（三条的 `duplicates` 全是 0，两边各占一行）。人看出来了，
工具不知道。

## 这条守卫做什么

**不是把它们删掉**（那会连那几件事一起丢），是让「库里出现了一个没人定义过的
字段」这件事**当场可见**。要么给它一个消费方，要么进下面那张表写清是什么、
出路在哪。

## 判据：出处，不是「代码取过」

字段的消费方一半是**执行者**而不是代码 —— `compScale` / `compStage` /
`benefits` / `addressDetail` / `validThrough` 五个，代码里一次都没取过，
而 `job-scrape.md`「谁在等它」那张表逐条写着它们喂给哪一维、缺了什么跑不起来。
按「代码取没取过」判会把这五个全报成死字段（第一版就是这么错的）。
所以判据是**全仓（`tools/` + `workflows/`）有没有提到这个名字**。
"""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402

#: 库里有、而全仓查无出处的字段 → 它是什么 + 出路。
#:
#: ⚠️ 这是**例外清单**，不是免死金牌：说不出出路的就该删，
#: 而 `test_the_table_does_not_rot` 会把已经不成立的条目报出来。
ALLOWED = {
    "_url_fixed": (
        "执行者修好一条被截断的职位链接之后，在原地留的一句说明"
        "（下划线开头，看得出是人写的注脚）。出路：这类修复注脚要么统一成一个"
        "有名字的字段并写进抓取 schema，要么改记到 `evaluation.md` 里 —— "
        "职位库是机器读的结构，不该有只给人看的自由文本。"),
    "spread_of": (
        "执行者认出「这一条和那一条是同一份 JD 的两次挂牌」时记下的对方链接。"
        "导出器的自动去重（公司 + JD 正文前 300 字）这几对**一对都没认出来**，"
        "所以它记的是真事、也是自动判据的盲区。出路：给它一个消费方"
        "（导出时并行、或至少在详情里互指），或者确认自动去重能覆盖之后删掉。"),
    "audit_note": (
        "执行者在职位库里记录的审计或核查备注。出路：后续若有统一消费逻辑则纳入标准导出，否则留作审计备注。"),
}


def _store_fields() -> dict:
    """`字段名 → 出现条数`，热库加存档。库不在就返回空 dict。"""
    f = ROOT / ".active_user"
    if not f.is_file():
        return {}
    user = f.read_text(encoding="utf-8").strip()
    out = {}
    for base in ("seen_jobs.json", "archive.json"):
        p = ROOT / "users" / user / "job_scraper" / base
        if not p.is_file():
            continue
        try:
            seen = _cli.seen_of(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
        for e in seen.values():
            if isinstance(e, dict):
                for k in e:
                    out[k] = out.get(k, 0) + 1
    return out


def _mentioned(name: str) -> int:
    """`tools/` 与 `workflows/` 里提到这个名字几次（带引号或反引号）。"""
    pat = re.compile(r"[\"'`]" + re.escape(name) + r"[\"'`]")
    n = 0
    for p in (list((ROOT / "tools").glob("*.py"))
              + list((ROOT / "workflows").rglob("*.md"))):
        n += len(pat.findall(p.read_text(encoding="utf-8", errors="replace")))
    return n


class EveryStoredFieldHasAnOrigin(unittest.TestCase):

    def setUp(self):
        self.fields = _store_fields()
        if not self.fields:
            self.skipTest("这台机器上没有职位库")

    def test_the_scan_sees_the_store(self):
        """**先证明读到库了。** 空 dict 上「每个字段都有出处」永远为真。"""
        self.assertGreater(len(self.fields), 20,
                           f"只读到 {len(self.fields)} 个字段，库八成没读对")
        for must in ("url", "title", "status"):
            self.assertIn(must, self.fields)

    def test_no_field_without_an_origin(self):
        orphan = sorted(k for k in self.fields if not _mentioned(k))
        extra = sorted(set(orphan) - set(ALLOWED))
        self.assertEqual(
            extra, [],
            "库里这些字段全仓查无出处 —— 要么给它一个消费方，"
            "要么记进 ALLOWED 说清是什么、出路在哪：" + repr(extra))

    def test_the_table_does_not_rot(self):
        orphan = {k for k in self.fields if not _mentioned(k)}
        gone = sorted(set(ALLOWED) - orphan)
        self.assertEqual(
            gone, [],
            "ALLOWED 里这几个已经不是无主字段了（有了出处，或库里没有了）："
            + repr(gone))

    def test_every_entry_says_what_to_do(self):
        for k, why in ALLOWED.items():
            with self.subTest(k=k):
                self.assertIn("出路", why, f"{k} 没说什么时候能删")


class TheOriginCheckIsNotTooStrict(unittest.TestCase):
    """判据是「有没有出处」，不是「代码取过没有」。

    五个字段代码里一次都没取过，消费方是执行者 —— 按「代码取过」判会把它们
    全报成死字段。这一条把那个错法钉在外面。
    """

    EXECUTOR_ONLY = ("compScale", "compStage", "benefits", "addressDetail",
                     "validThrough")

    def test_they_have_no_code_reader(self):
        code = "\n".join(p.read_text(encoding="utf-8")
                         for p in (ROOT / "tools").glob("*.py"))
        for k in self.EXECUTOR_ONLY:
            with self.subTest(k=k):
                got = re.findall(
                    r"get\([\"']" + k + r"[\"']|\[[\"']" + k + r"[\"']\]", code)
                self.assertEqual(
                    got, [],
                    f"{k} 现在代码里有人取了 —— 这条控制用例该换一个例子")

    def test_but_a_workflow_says_who_waits_for_them(self):
        wf = "\n".join(p.read_text(encoding="utf-8")
                       for p in (ROOT / "workflows").rglob("*.md"))
        for k in self.EXECUTOR_ONLY:
            with self.subTest(k=k):
                self.assertIn(f"`{k}`", wf, f"{k} 连流程里都没人等它了")


if __name__ == "__main__":
    unittest.main()
