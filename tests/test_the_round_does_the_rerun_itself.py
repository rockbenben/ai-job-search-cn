# -*- coding: utf-8 -*-
"""一轮 auto 跑完，不许再交给用户一条它自己就能跑的命令。

## 这一条守的是什么

`/job-auto` 的卖点是「中途不用你盯着」。收尾里 `stale_materials.py` 报的那批
（材料翻了档、或当时就没读全职位描述）是**手上有活没做完** —— 和「可投但还没
出材料」是同一件事的两半。而 2026-08-30 之前，收尾在末尾印一句
「要重跑就跑 `/job-apply --stale`」。

那句话本身合规（`AGENTS.md`「每一处引导都要写出该敲的命令」）。
错的是**位置**：一轮跑完之后交给用户的，是**又一条要敲的命令**，
内容还是这一轮本来就有能力做完的事。

判据是 2026-08-12 撤掉「挑哪几个」那道点头闸门时给的理由，
在这里一字不改地成立：**出材料花的是 AI 的工时，不是他的。**

## 它不管什么

真正归人的三件事照旧（`job-auto.md`「什么归机器，什么永远归人」）：
投出去那一下、验证码、资料里没有的事实。这条守卫只盯**机器能做完却推给人**
的那一类。
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
AUTO = (ROOT / "workflows" / "job-auto.md").read_text(encoding="utf-8")


def _loop_block() -> str:
    """循环那一段：从「## 循环」到「### 每批都要跑的机械步骤」。"""
    i = AUTO.index("## 循环")
    j = AUTO.index("### 每批都要跑的机械步骤")
    return AUTO[i:j]


def _closing_block() -> str:
    """收尾那个代码块：从「收尾（无条件）」到它后面第一个空行分隔的散文。"""
    seg = _loop_block()
    i = seg.index("收尾（无条件）")
    return seg[i:]


class TheRerunHappensInTheRound(unittest.TestCase):

    def test_the_queue_is_taken_before_making_materials(self):
        """出材料那一步自己先拿名单 —— 不是等收尾才报。"""
        seg = _loop_block()
        i = seg.index("出材料（")
        j = seg.index("收尾（无条件）")
        make = seg[i:j]
        self.assertIn("stale_materials.py", make,
                      "出材料那一步没去拿「该重跑」的名单")
        self.assertIn("/job-apply --stale", make,
                      "拿了名单却没说拿它干什么")

    def test_the_closing_run_is_a_check_not_a_todo(self):
        """收尾那次的定位要写清是复查 —— 否则读的人会以为还有活没干。"""
        seg = _closing_block()
        i = seg.index("stale_materials.py")
        note = seg[i:i + 300]
        self.assertTrue(
            re.search(r"复查|验收", note),
            "收尾那条还写成待办清单的口气，而这一轮已经做过一遍了")

    def test_it_does_not_hand_the_command_back_to_the_user(self):
        """全文不许再出现「要重跑，跑 /job-apply --stale」这类交回去的说法。

        判据看的是**祈使**：把命令连着「要…就…」写给用户。
        文档里解释这条命令做什么、或者说「单独看一个仍然可以」，都不算。

        ⚠️ **引用块（`>` 开头）不算。** 这个仓库记规则的办法就是把旧写法原样
        引出来再说它错在哪 —— 第一版这条守卫当场把我自己那句
        「原来这条只在收尾里报，末尾印一句『要重跑就跑 …』」报成了违规。
        同一条豁免在 `test_docs_accuracy` 里已经有：
        「散文里提、引号里引不算，讲规则总得能引用它」。
        """
        bad = [ln.strip() for ln in AUTO.splitlines()
               if "--stale" in ln and not ln.lstrip().startswith(">")
               and re.search(r"要重跑|你自己再跑|请跑", ln)]
        self.assertEqual(bad, [], "又把它交回给用户了：\n  " + "\n  ".join(bad))

    def test_no_browser_still_does_what_it_can(self):
        """`--no-browser` 不该让整批停摆 —— JD 已入库的那几个照样重判。

        `stale_materials.py` 每行都带 `jdReady`，split 是现成的
        （它自己印的那句「N 个 JD 已入库、直接重判，M 个要先抓」）。
        一面旗子挡住的是「要先抓」的那几个，不是整条队列。
        """
        seg = _loop_block()
        i = seg.index("出材料（")
        j = seg.index("收尾（无条件）")
        make = seg[i:j]
        self.assertIn("--no-browser", make, "没说这面旗子在这一步怎么算")
        self.assertTrue(re.search(r"已入库", make),
                        "没说清挡住的只是「要先抓」的那几个")


class TheQueueMustBeAbleToDrain(unittest.TestCase):
    """**队列排不空比没有队列更糟。**

    出队的唯一判据是重跑完留下的那行 `重跑日期：YYYY-MM-DD`，
    而写它的是写手 —— 和「小节写全没有」同一个形状：一句给写手看的提示。

    2026-08-30 把这批并进轮内之后，忘了写的代价变了性质：
    从「面板上那个数不降」变成 **每一轮的第 0 小步都把同样几个岗原样再跑
    一遍**。它已经不是一条统计，是一个循环。

    所以收尾那次复查不能只说「正常应该是 0」，还要说清不是 0 时是哪一种、
    当场怎么办 —— 一道只报数的闸门等于没有闸门（同一课本文件上一条记过）。
    """

    def test_the_recheck_says_what_a_nonzero_means(self):
        i = AUTO.index("收尾（无条件）")
        j = AUTO.index("### 每批都要跑的机械步骤")
        seg = AUTO[i:j]
        k = seg.index("stale_materials.py")
        # **范围取「这条命令到下一条命令」，不是定长窗口。** 原来写的是往后 700 字：
        # 那是照着当时的排版量出来的，而排版一变就失效 —— 2026-10-14 把夹在命令与
        # 它自己注释尾巴之间的那段 ⚠️ 挪到块尾（那才是它该待的地方，见
        # `job-auto.md` 收尾那段），「再跑一遍」落到 +718、「每一轮」落到 +738，
        # 刚好出窗，两条断言里的一条红了。**红的是窗，不是内容。**
        #
        # 按命令切块之后，两种排版都过：判据问的是「这段说明里有没有说清
        # 不补的代价」，而不是「它离命令有多远」。
        end = seg.index("\n    python tools/", k)
        note = seg[k:end]
        self.assertIn("重跑日期", note, "没说不是 0 多半是那行戳没写")
        self.assertTrue(re.search(r"再跑一遍|每一轮", note),
                        "没说清不补的代价是下一轮重跑同样几个岗")

    def test_it_separates_the_two_causes(self):
        """`--no-browser` 挡下的那几个是正常留到下一轮，不该被当成漏写戳。"""
        i = AUTO.index("收尾（无条件）")
        seg = AUTO[i:i + 2500]
        self.assertIn("--no-browser", seg)

    def test_the_stamp_is_still_the_only_dequeue_rule(self):
        """判据是结构化字段，不是去 grep 说明里的措辞。"""
        seg = (ROOT / "tools" / "stale_materials.py").read_text(encoding="utf-8")
        self.assertIn("_REREAD.search(text)", seg)


class TheToolStillOnlyReports(unittest.TestCase):
    """判据仍然只有一份：`stale_materials.py` 只报不改，做事的是 `/job-apply`。"""

    def test_the_tool_does_not_write_evaluations(self):
        src = (ROOT / "tools" / "stale_materials.py").read_text(encoding="utf-8")
        self.assertNotIn("write_text", src,
                         "它开始写盘了 —— 重判要读 JD 再判，那是命令的活")


if __name__ == "__main__":
    unittest.main()
