"""面板与命令行都靠 next_step 告诉用户「下一步做什么」——它给错了，用户就走错。

原实现按「从前往后」判断流水线：profile → 抓 → 评 → 材料 → 投 → 面试，第一个不满足的
就是下一步。这个假设只在**严格线性推进**时成立，而真实状态会跳跃，于是靠前的条件先命中，
给出**倒退的建议**。两个实测到的例子：

- 唯一的职位是硬门 FAIL：`ranked` 计数 > 0（它确实被评过），于是说「排好了，给头部岗
  生成材料」。但 gate_fail 的岗不该投，`ranked_urls` 里也没有它 → 命令退化成
  `/job-apply <职位URL>` 占位符，等于让用户去投一个不存在的岗。
- 已投但那个岗已过期：`status` 是 `expired` 不是 `ranked`，`ranked` 计数为 0，于是说
  「还没排名：跑 /job-rank」——而用户其实已经投了、在等回复。

修法：**倒着判断**，从流水线最靠后已经发生的事开始。
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))
sys.path.insert(0, str(REPO_ROOT / "tests"))
import build_dashboard as bd  # noqa: E402
from _srcscan import code_of  # noqa: E402


def _app(url, dirname="甲公司_岗A", preps=()):
    return {"dir": dirname, "url": url, "resume": None,
            "outreach": {"url": url, "greeting": "g", "email_subject": "",
                         "email_body": "", "wangshen": ""},
            "interview_preps": list(preps), "evaluation": None}


def _tracker(url="https://x/1", status="applied"):
    return [{"company": "甲公司", "role": "岗A", "source": url, "status": status,
             "notes": "", "date": "2026-07-30"}]


def _job(**over):
    j = {"url": "https://x/1", "title": "岗A", "company": "甲公司", "status": "ranked",
         "rank_score": 80, "rank_verdict": "强匹配"}
    j.update(over)
    return {"https://x/1": j}


def _step(seen, apps=(), tracker=()):
    m = bd.build_model(seen, list(apps), list(tracker), True, "张三", ["张三"])
    return m["next_step"], m


class NonLinearStateTests(unittest.TestCase):
    def test_all_ranked_jobs_gate_failed_does_not_tell_you_to_apply(self):
        """全是硬门 FAIL 时不该说「给头部岗生成材料」——没有可投的岗。"""
        ns, m = _step(_job(rank_score=None, rank_verdict="硬门 FAIL (学历院校)"))
        self.assertEqual(m["jobs"][0]["stage"], "gate_fail")
        self.assertNotIn("生成材料", ns["text"],
                         f"全是硬门 FAIL 却让人去投：{ns['text']}")
        self.assertNotIn("/job-apply <职位URL>", ns.get("command") or "",
                         "不得给出占位符命令——那是让用户去投一个不存在的岗")

    def test_all_ranked_jobs_low_score_does_not_tell_you_to_apply(self):
        """全是「不建议/跳过」时同理——那些岗按框架就是不该投的。"""
        ns, m = _step(_job(rank_score=30, rank_verdict="不建议"))
        self.assertEqual(m["jobs"][0]["stage"], "low")
        self.assertNotIn("生成材料", ns["text"], f"全是低分却让人去投：{ns['text']}")

    def test_applied_but_expired_job_is_not_told_to_rank(self):
        """已投的岗即使过期了，也不该倒回去让人 /job-rank。"""
        ns, _ = _step(_job(status="expired"), tracker=_tracker())
        self.assertNotIn("/job-rank", ns.get("command") or "",
                         f"已经投了却让人去打分：{ns['text']}")
        self.assertNotIn("还没排名", ns["text"])

    def test_materials_exist_for_a_never_scraped_job(self):
        """手动找到的岗直接跑了 /job-apply（从没进过 seen_jobs）——不该只说「还没抓职位」。"""
        ns, m = _step({}, apps=[_app("https://y/9", "乙公司_岗B")])
        self.assertEqual(m["unmatched_apps"], ["乙公司_岗B"])
        self.assertIn("乙公司_岗B", ns["text"] + (ns.get("command") or ""),
                      f"有材料的目录没被提到，用户会以为它丢了：{ns['text']}")


class LinearPathStillWorksTests(unittest.TestCase):
    """控制用例：正常线性推进的每一步都不能被上面的修改带坏。"""

    def test_nothing_scraped(self):
        ns, _ = _step({})
        # **零起点给脊梁那条，不是它的分解。** `AGENTS.md`「一次跑到头：只有三条命令」写着 `/job-setup → /job-auto → /job-outcome`，
        # 紧跟着一句「别把这条脊梁说成四步……多教一步的代价不是多敲一次，是让人以为不敲就会漏东西」。
        self.assertIn("/job-auto", ns.get("command") or "")

    def test_scraped_not_ranked(self):
        ns, _ = _step(_job(status="new", rank_score=None, rank_verdict=None))
        self.assertIn("/job-rank", ns.get("command") or "")

    def test_ranked_no_materials_points_at_the_batch_entry(self):
        """**这一条原来指向单岗 `/job-apply https://x/1`。**

        旧理由是「排序结果写在机器读的文件里，人能看的只有总览页，所以他得先去挑一个」
        ——**它对单岗成立，对这一支不成立**。这一支的条件是「有可投的已评岗没材料」，
        而用户不知道该做什么时问的是「我手上还有什么没做完的」，答案是一批。

        后果不是多敲一次：面板叫他一个一个敲，而他之所以在敲第 3 个，
        恰恰是因为他不知道有批量那条路（`job-apply.md`「按档批量」那一节的
        `全部` =「除了不投的都准备好」就是为这句话准备的）。

        `AGENTS.md` 另一条同样约束这里：**一条引导对应一条命令**——
        给出 `--top` / `可以考虑` / `全部` 三个里挑一个让用户选，那正是引导要替他省掉的。
        """
        ns, _ = _step(_job())
        self.assertEqual(ns.get("command"), "/job-apply 全部",
                         f"已排名未出材料还在一个一个教：{ns}")

    def test_the_batch_entry_says_batch_not_top_job(self):
        """文案不许再说「头部岗」——那条措辞就是单岗时代的残留。"""
        ns, _ = _step(_job())
        self.assertNotIn("头部岗", ns["text"], f"文案还停在单岗：{ns['text']}")

    def test_materials_ready_says_go_send(self):
        ns, _ = _step(_job(), apps=[_app("https://x/1")])
        self.assertIn("投递", ns["text"])

    def test_applied_and_nothing_left_points_back_at_the_loop(self):
        """唯一的岗投出去了、手上没别的 → 接着抓。

        原来这里断言 `/job-outcome`（去记一笔）。2026-08-29 那一格改成指回
        主循环（`AGENTS.md`「跟进归用户，工具不催」）—— 这个岗**已经**记过了，
        再指 `/job-outcome` 就是让他记第二遍。
        """
        ns, _ = _step(_job(), apps=[_app("https://x/1")], tracker=_tracker())
        self.assertIn("/job-auto", ns.get("command") or "")

    def test_interviewing_says_prep(self):
        ns, _ = _step(_job(), apps=[_app("https://x/1")],
                      tracker=_tracker(status="interview"))
        self.assertIn("/job-interview", ns.get("command") or "")

    def test_profile_missing_wins_over_everything(self):
        """资料没建时，无论后面多少数据，都得先去 /job-setup。"""
        m = bd.build_model(_job(), [_app("https://x/1")], _tracker(), False,
                           "张三", ["张三"])
        self.assertIn("/job-setup", m["next_step"].get("command") or "")


if __name__ == "__main__":
    unittest.main()


class MaterialsNudgeFollowsTheBatchGate(unittest.TestCase):
    """只有可投两档才催「去出材料」——催一条会白跑的命令比不催更糟。

    `job-apply.md` 的批量闸门写得很明确：强匹配/值得投 → 出开场白；
    可以考虑 → **停在这里**，只落 evaluation.md；不建议/跳过/硬性条件没过 → 同样停。

    而 `job_next_step` 唯一的守门原来是 `score is None`，
    **「不建议」「跳过」是有分数的**——于是照样被催去 `/job-apply`。
    2026-08-20 实测 461 个「还没出材料」里：不建议 265、跳过 9，
    合计 274 个岗在教用户敲一条不会产出话术的命令。

    「可以考虑」那 175 个另给措辞：04 的定义是「**先问清楚**关键信息再决定」——
    它是一个待办不是一个动作，催他出材料等于替他把还没做的决定当成做了。
    """

    def _next(self, verdict, score=70):
        return bd.job_next_step({"verdict": verdict, "score": score,
                                 "url": "https://x/1", "company": "某公司"})

    def test_sellable_two_bands_are_nudged(self):
        for v in ("强匹配", "值得投", "粗筛：值得投"):
            with self.subTest(v):
                ns = self._next(v)
                self.assertIsNotNone(ns)
                self.assertIn("还没出材料", ns["text"])
                self.assertTrue(ns["command"].startswith("/job-apply"))

    def test_weak_bands_are_not_nudged_to_a_no_op(self):
        for v in ("不建议", "跳过", "粗筛：不建议"):
            with self.subTest(v):
                self.assertIsNone(self._next(v),
                                  f"「{v}」被催去 /job-apply，而批量闸门明写这一档不出话术")

    def test_maybe_band_says_decide_first(self):
        ns = self._next("可以考虑")
        self.assertIsNotNone(ns)
        self.assertIn("先问清楚", ns["text"], "「可以考虑」是待办不是动作，不能当成「去出材料」")
        self.assertIn("可以考虑", ns["command"], "给的命令要能把这一档一起备料")

    def test_missing_verdict_still_gets_nudged(self):
        """判词缺失时照常催——方向往「多说一句」偏，不往「静默吞掉」偏。"""
        ns = bd.job_next_step({"company": "某司", "score": 70, "url": "https://x/1"})
        self.assertEqual(ns["command"], "/job-apply https://x/1")

    def test_real_export_has_no_futile_nudge(self):
        """控制测试：真实导出里不许再有「催出材料但不是可投两档」的岗。"""
        import json
        f = REPO_ROOT / "web" / "public" / "data.json"
        if not f.is_file():
            self.skipTest("还没导出过")
        import re as _re
        bad = [j.get("title", "")[:24] for j in json.loads(f.read_text(encoding="utf-8"))["jobs"]
               if "还没出材料" in ((j.get("nextStep") or {}).get("text") or "")
               and _re.sub(r"^粗筛[：:]\s*", "", j.get("verdict") or "")
               not in ("强匹配", "值得投")]
        self.assertEqual(bad, [], f"这些岗被催去出材料，而它们的判词不出话术：{bad[:8]}")


class TheLiveExporterAlsoHasAVerdictGate(unittest.TestCase):
    """**守卫钉的是夹具，活的那条导出路径当时没有闸门。**

    上面 `MaterialsNudgeFollowsTheBatchGate` 与 `NonLinearStateTests`
    走的都是 `bd.build_model`，而 `build_dashboard.py` 顶上明写
    「`build_model()` 只有测试在调」。它挑头部岗靠的是 `stage == "ranked"`
    ——低分档落在 `low`、硬门 FAIL 落在 `gate_fail`，**闸门在 `stage` 里**。

    而 `export_web_data` 自己算 `top` 时只判 `score is not None`。
    **「不建议」「跳过」是有分数的**（同一个文件里那条守卫自己写着这件事），
    按 `job-apply.md` 的批量闸门这两根本不出话术 —— 于是它们照样被当成
    「排好了，去出材料」的头部岗，而面板给出的命令是一条不会产出话术的命令。

    `bd.next_step` 的 docstring 其实已经把契约写明了：

        参数里 `top_ranked_url` 为 None 表示**没有可投的已评岗**
        （全是 gate_fail / 低分）

    所以这条钉的是**生产者遵守那个契约**，不是给消费者再加一道闸。
    """

    @staticmethod
    def _top_expr():
        return code_of("tools/export_web_data.py", "    top = next(")

    def test_the_live_top_rejects_the_bands_that_produce_nothing(self):
        seg = self._top_expr()
        self.assertIn("is_sellable", seg,
                      "活的导出路径算 top 时没有判词闸门——"
                      "「不建议」「跳过」是有分数的，会被当成头部可投岗")

    def test_the_gate_is_the_exported_one_not_a_second_list(self):
        """闸门走 `is_sellable` 正本，不许在这里内联一份判词白名单。

        `export_web_data` 自己写着判词是「自由度很高的字段」，白名单每次变动的
        默认后果是「漏一个」—— 抄第二份只会让那份漏掉，而漏掉的那次是静默的。
        """
        self.assertNotIn("值得投", self._top_expr(),
                         "判词白名单被抄了第二份")
