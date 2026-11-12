# -*- coding: utf-8 -*-
"""出材料之前先查一次详情库——不查的代价是把明天的抓取额度花在同一段字上。

详情库这个文件的第一行写着「抓过的 JD 存下来，**不重抓**」，Python 侧也确实
照做（`fetch_details.py` 逐个 `has_body` 跳过已有的）。漏的是**由 AI 执行、
不由工具执行**的那条路：`/job-apply` 第 0 步原来直接就是「调猎聘 CLI」
「用网页抓取能力抓」，手上有正文也照抓一遍。

实测代价（活动用户 2026-08-27）：那一轮 `/job-apply` 批量要跑 144 个岗，
其中 **138 个的正文详情库里已经有了**（猎聘 132、前程无忧 5、BOSS 4、智联 3）。
抓取额度是这里最稀缺的资源——每次请求之间要隔 8/4/3 秒、撞了风控整站冷却 24 小时。

修法只能是**读文件**，不能是敲工具：`/job-apply` 对外承诺不依赖 Python
（README 与 SETUP 都这么写，`test_materials_gap_nudge` 盯着）。好在不需要——
批量本来就在读 `web/public/data.json`，而那里每个岗的 `id` **就是**详情库的
文件名（两边同一个 `stable_id(url, title)`），`cat` 一下就够了。

第一版在这里加了个 `jd_store.py --get`，当场被那条测试拦下。拦对了：
真需要的东西是一行 `cat`，多出来的那个 flag 既破坏承诺又没有别的调用方。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import jd_store  # noqa: E402

APPLY = (ROOT / "workflows" / "job-apply.md").read_text(encoding="utf-8")
STORE = (ROOT / "tools" / "jd_store.py").read_text(encoding="utf-8")


#: 第 0 步查库那一节的唯一锚。用小节标题，不用命令串——命令串在正文里还会
#: 被引用第二次，`index()` 会落到别处（`test_test_anchors_are_unambiguous`）。
ANCHOR = "#### 抓之前先查一次详情库"


class TheWorkflowChecksBeforeItFetches(unittest.TestCase):
    def test_step0_names_what_to_read(self):
        """`AGENTS.md`「每一处引导都要写出该敲的命令」——指一个目录名不算。"""
        self.assertEqual(APPLY.count(ANCHOR), 1, "锚不唯一了")
        seg = APPLY[APPLY.index(ANCHOR):][:1200]
        self.assertIn("job_scraper/details/", seg, "没说去哪儿查")
        self.assertRegex(seg, r"^cat |\ncat ", "没给出能直接敲的读法")
        self.assertIn("grep -l", seg, "只有 id 那条路；手上只有链接时没法查")

    def test_it_stays_python_free(self):
        """`/job-apply` 对外承诺不依赖 Python，这一步不许把它破掉。

        `test_materials_gap_nudge` 已经全局盯着 `python tools/`；这里再钉一次
        本节，是因为**这一节最容易犯**——它要读的正是 Python 侧那个库。
        """
        seg = APPLY[APPLY.index(ANCHOR):][:1800]
        self.assertNotRegex(seg, r"python\s+tools/\S+\s+--get",
                            "又把查库写成敲工具了，没装 Python 的人就投不了")

    def test_the_check_comes_before_the_three_branches(self):
        """顺序就是全部意义。写在三条分流**后面**等于没写。"""
        self.assertLess(APPLY.index(ANCHOR),
                        APPLY.index("**猎聘职位 URL** —— 调用 CLI 取回结构化数据"),
                        "查库那一步排在了「调 CLI」后面，抓取照样发生")

    def test_a_hit_skips_the_fetch_outright(self):
        """「查一下」不等于「查到了就不抓」。后半句必须写死。"""
        seg = APPLY[APPLY.index(ANCHOR):][:900]
        self.assertRegex(seg, r"读到了就用它[，,].{0,20}一条都不跑",
                         "没写明命中就跳过下面三条分流")
        self.assertRegex(seg, r"才按下面分流去抓", "没写明什么时候才该去抓")

    def test_the_cost_is_written_next_to_it(self):
        """理由挨着写，否则下一个人会把这一步当多余的一次 IO 删掉。"""
        seg = APPLY[APPLY.index(ANCHOR):][:2000]
        self.assertRegex(seg, r"额度.*最稀缺|最稀缺的资源")
        self.assertRegex(seg, r"库里没有才去抓")


class TheConsumerAndTheMergeListAgree(unittest.TestCase):
    """消费者读职位库的哪个键，回填表就得搬哪个键——两处对不上，读到的恒为空。

    这是 `validThrough`/`deadline`、`datePosted`/`date` 之后同一形状的第三处：
    两边都「有」这个字段，中间没人把它接上，于是那条规则从上线起就没生效过。
    区别是这次不是名字不同，是**回填表里压根没有它**。
    """

    def test_the_field_the_panel_reads_is_one_the_merge_fills(self):
        exp = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
        self.assertIn('counterpart_of(e.get("recruiterTitle")', exp,
                      "消费者换了字段名，这条测试要跟着换")
        self.assertIn("recruiterTitle", jd_store.MERGE_FIELDS,
                      "面板读 recruiterTitle，而 --merge 不搬它——那个键恒为空")

    def test_the_dead_pipe_is_written_down(self):
        i = STORE.index("# `recruiterTitle` 与上面那几个断在不同的地方")
        seg = STORE[i:i + 1400]
        self.assertIn("recruiterTitle", seg)

    def test_the_count_is_by_value_not_by_key(self):
        """这个字段的键在 1510 份详情里都有，而其中 1479 份的值是 `null`。

        按键数会得出「覆盖率 98%」，真实是 2%。这一课要留在原地——
        下一个来数它的人会犯同一个错。
        """
        i = STORE.index("# `recruiterTitle` 与上面那几个断在不同的地方")
        self.assertRegex(STORE[i:i + 1400], r"null.{0,12}不算|真值",
                         "没写明这个数是按值数的")


if __name__ == "__main__":
    unittest.main()
