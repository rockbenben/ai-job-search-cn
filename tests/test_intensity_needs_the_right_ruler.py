# -*- coding: utf-8 -*-
"""04 说强度词表要按候选人所在形态现推，而批量打分的代理拿不到形态。

`04-job-evaluation.md` 第 3 维（工作强度与公司性质，占 20% 权重）写着：

> **工作强度信号词：按候选人所在行业现推，不要照搬下面的例子。**
> 强度在不同行业根本不是同一件事，词表也完全不重合：
> 按项目/版本推进的看加班节奏与周末制度；按班次运转的看排班方式与夜班频次；
> 按周期考核的看考核口径与淡旺季落差。
> 所以：**先从 `profile/candidate.md` 判断候选人在哪种形态里**，再据此定这一维
> 要在 JD 里找什么词。判完在依据里写清「本次按什么信号判的」。

它甚至写下了这么做的代价：

> 这里原来写死一份词表（「大小周」「奋斗者」这一类）。那是**某一个行业的黑话**：
> 换成按班次运转的岗位，JD 里一个都不会出现，于是这一维**静默地全部标成未知**
> —— 不是没信息，是拿错了尺子。

## 而这条规则在批量打分里从来没跑过

`/job-rank` 的枚举给代理的是「工作强度与公司类型**偏好**」—— 那是「他能接受多大
强度」，不是「他这一行的强度用什么词说」。**两件事。** 而同一段明写着
「**不要**让代理再去读一遍资料文件」，所以它连推都没得推。

实测活动用户 2026-08-24：

    打过强度分的岗                     783 个
    依据里写了「本次按什么信号判的」      0 份
    分数落在 50 或 70 两个值上          648 个（83%）

## 2026-10-12：这条规则第一次真的跑起来了

上面那份数是「修好之前」的。修好之后（枚举里补进了形态）第一次整轮实测：

    打过强度分的岗                     928 个
    依据里写了「本次按什么信号判的」      5 份
    分数落在 50 或 70 两个值上          790 个（85%）

**5 份全部出自 2026-10-12 那一轮**，写的正是 04 要求的形状
（「强度按项目/版本推进形态看加班与周末制度，JD 未提及大小周……」）。
所以下面那条断言从 `== 0` 改成了 `>= 1`：它原本的用途是「修好之前一条都没写」
的证据，规则生效之后它的作用变成**「别哪天悄悄退回 0」**——
这一轮只兑现了 5/928，说明还没普及，但已经不是零。

**「前两个值占 85%」这一格没动**（83% → 85%，方向还略微变差），
说明「写了口径」和「分数真的散开」是两件事，见下面那条断言。

## 修法：把输入补进枚举，不是新造判断

「技能匹配的强/中/弱三类领域」也不是资料里的字段，是 Step 1 读完资料**提炼**出来
放进提示的。形态走同一条路 —— 不改资料模板、不加一步问答。
"""
import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
RANK = (ROOT / "workflows" / "job-rank.md").read_text(encoding="utf-8")
EVAL = (ROOT / "workflows" / "reference"
        / "04-job-evaluation.md").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*(?:>|#:?)\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


def seg() -> str:
    i = RANK.index("他属于哪种强度形态")
    return flat(RANK[max(0, i - 200):i + 900])


class TheEnumerationCarriesTheShape(unittest.TestCase):
    def test_it_is_in_the_enumeration(self):
        """枚举是代理唯一能拿到的东西 —— 不在这儿等于不存在。"""
        i = RANK.index("**不要**让代理再去读一遍资料文件。")
        j = RANK.index("他属于哪种强度形态")
        self.assertLess(j, i, "写在枚举之外了，代理拿不到")

    def test_it_distinguishes_shape_from_preference(self):
        """**这是整条的支点。** 枚举里本来就有「偏好」，混起来就等于没加。"""
        s = seg()
        self.assertRegex(s, r"这是\*\*两件事\*\*")
        self.assertRegex(s, r"偏好是「他能接受多大强度」")
        self.assertRegex(s, r"形态是「他这一行的强度用什么词说」")

    def test_it_names_all_three_shapes(self):
        s = seg()
        for k in ("按项目/版本推进", "按班次运转", "按周期考核"):
            with self.subTest(k=k):
                self.assertIn(k, s)

    def test_each_shape_comes_with_what_to_look_for(self):
        """只给形态名，代理还是不知道该找什么词。"""
        s = seg()
        for k in ("加班节奏", "排班", "夜班频次", "考核口径", "淡旺季"):
            with self.subTest(k=k):
                self.assertIn(k, s)

    def test_it_says_why_the_agent_cannot_derive_it(self):
        """钉完整那句，不是「代理手上没有资料文件」这半句 ——
        同一段里「明确排除」那一条也写着同样六个字，窗口正好盖到它，
        于是把这半句整个删掉照样绿（变异实测）。"""
        s = seg()
        self.assertRegex(
            s, r"代理手上没有资料文件\*\*，\s*只给它偏好、不给形态，它只能套一份通用词表")

    def test_it_demands_the_signal_be_written_down(self):
        """04 要的那句话得有人转达 —— 那是用户唯一能纠正它的地方。"""
        s = seg()
        self.assertRegex(s, r"在 `依据` 里写一句本次按什么信号判的")

    def test_the_field_it_writes_into_exists(self):
        """指一个输出里没有的字段，等于又一个悬空指针。"""
        self.assertIn("rank_breakdown", RANK)
        self.assertRegex(flat(RANK), r"「依据」|`依据`")

    def test_the_measurement_is_recorded(self):
        s = seg()
        self.assertIn("2026-08-24", s)
        self.assertRegex(s, r"783 个打过强度分的岗里 \*\*0 份\*\*")
        self.assertRegex(s, r"83% 落在 50 和 70 两个值上")

    def test_the_neighbours_survive(self):
        """这一条是插进一长串枚举中间的 —— 前后各项一个都不许挤掉。"""
        s = flat(RANK)
        for k in ("技能匹配的强/中/弱三类领域", "期望薪资区间与底线",
                  "发展与风险那几项", "地点限制", "硬门判据"):
            with self.subTest(k=k):
                self.assertIn(k, s)


class TheRuleItServesIsStillWritten(unittest.TestCase):
    def _seg(self) -> str:
        i = EVAL.index("### 3. 工作强度与公司性质")
        return flat(EVAL[i:EVAL.index("**公司性质**", i)])

    def test_it_still_forbids_a_fixed_wordlist(self):
        self.assertRegex(self._seg(), r"按候选人所在行业现推，不要照搬下面的例子")

    def test_it_still_has_the_three_shapes(self):
        s = self._seg()
        for k in ("按项目/版本推进的", "按班次运转的", "按周期考核的"):
            with self.subTest(k=k):
                self.assertIn(k, s)

    def test_it_still_says_where_the_shape_comes_from(self):
        self.assertRegex(
            self._seg(), r"先从 `profile/candidate\.md` 判断候选人在哪种形态里")

    def test_it_still_demands_the_signal_be_stated(self):
        self.assertRegex(self._seg(), r"判完在依据里写清「本次按什么信号判的」")

    def test_it_still_records_what_a_fixed_wordlist_costs(self):
        """这一整条建立在那段代价上 —— 它没了，加进枚举就成了无端加负担。"""
        self.assertRegex(self._seg(), r"静默地全部标成未知")
        self.assertRegex(self._seg(), r"不是没信息，是拿错了尺子")

    def test_unknown_is_still_not_optimistic(self):
        self.assertRegex(self._seg(), r"JD 不提就标记未知")
        self.assertRegex(self._seg(), r"不要因为没提就假设是轻松的")


class TheShapeIsDerivedNotStored(unittest.TestCase):
    """不改资料模板 —— 「三类领域」也不是字段，是 Step 1 提炼出来的。"""

    def test_the_template_has_no_such_field(self):
        tpl = (ROOT / "profile.example" / "candidate.md").read_text(encoding="utf-8")
        self.assertNotIn("强度形态", tpl,
                         "改成存字段了 —— 那就得让 /job-setup 问一遍，"
                         "这一条的前提（不加问答）要重看")

    def test_the_sibling_item_is_also_derived(self):
        """「三类领域」是同一条路上的先例 —— 它没了，这个类比就断了。"""
        self.assertIn("技能匹配的强/中/弱三类领域", RANK)

    def test_step_one_really_reads_the_profile(self):
        """提炼的前提是 Step 1 手上有资料。"""
        self.assertRegex(flat(RANK), r"从 Step 1 读过的那几份文件里提炼出来")


class TheSignalItLeansOnIsReal(unittest.TestCase):
    """现算：那句话真的一份都没写过，分数真的堆在两个值上。"""

    def _scored(self):
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        f = (ROOT / "users" / p.read_text(encoding="utf-8").strip()
             / "job_scraper" / "seen_jobs.json")
        if not f.is_file():
            self.skipTest("还没有职位库")
        seen = json.loads(f.read_text(encoding="utf-8"))["seen"]
        out = [e for e in seen.values() if isinstance(e, dict)
               and isinstance((e.get("rank_breakdown") or {}).get("强度与公司性质"),
                              (int, float))]
        if len(out) < 100:
            self.skipTest("打过强度分的太少")
        return out

    def test_the_dimension_is_actually_being_scored(self):
        """控制组：这一维真的在打分 —— 不然上面那些数说明不了什么。"""
        self.assertGreater(len(self._scored()), 100)

    def test_nobody_states_which_signals_were_used(self):
        """**2026-10-12：规则第一次生效，这条从「0 份」变成「至少 1 份」。**

        原来是 `assertEqual(n, 0)`，docstring 写着「修好之后这条会红，那时把
        这一节的实测数更新掉，别删了它」—— 那天到了：那一轮 928 个打过强度分的
        岗里有 5 份按 04 的要求写清了口径。

        所以它现在守的是**另一头**：规则生效之后别哪天悄悄退回 0。
        5/928 说明还没普及（见上面那段实测），但已经不是零。
        """
        rows = self._scored()
        n = sum(1 for e in rows
                if re.search(r"按什么信号|本次按|强度信号",
                             str((e.get("rank_breakdown") or {}).get("依据") or "")))
        self.assertGreaterEqual(
            n, 1, f"{n}/{len(rows)} 份 —— 又退回 0 了：04 要求的「写清本次按什么"
                  "信号判的」没人写了，去查 `/job-rank` 的枚举里形态那一项还在不在")

    def test_the_scores_pile_up_on_two_values(self):
        """堆在两个整数上是「没真判」的形状。散开了就说明尺子拿对了。"""
        import collections
        rows = self._scored()
        c = collections.Counter(
            int((e.get("rank_breakdown") or {})["强度与公司性质"]) for e in rows)
        top2 = sum(n for _v, n in c.most_common(2))
        self.assertGreater(
            top2, len(rows) * 0.6,
            f"分数已经散开了（前两个值只占 {top2}/{len(rows)}）—— "
            f"这一节引的 83% 过时了，去更新")


if __name__ == "__main__":
    unittest.main()
