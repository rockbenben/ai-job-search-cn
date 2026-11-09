"""命令之间的接缝要么焊死（自动），要么是真选择（问一次）——不许有第三种。

## 第三种是什么

「建议用户去跑 X」。它既不自动（漏跑一次就积压一批），也不是选择（答案永远是
「跑」，问了等于把已有的答案再要一次）。本仓库在 scrape→rank 上实测过代价：
一轮抓 210 个、评 12 个、待评堆到 589——每轮都靠人记得接下一棒。

判据一条（`job-auto.md`「什么归机器，什么永远归人」）：**这一步的输入是不是只有
用户知道、或后果是不是只有用户承担。** 是 → 问；不是 → 焊死。

全链路**只有一处**主动问人：投出去那一下（任何命令都不代投，材料备好等他）。
另有两类**被动**例外 —— 资料里没有的事实只能问他、验证码只能他亲手过。
本文件按接缝逐条钉。

「投哪几个要问一次」曾经是第二处，2026-08-12 用户裁定撤掉：出材料花的是
AI 的 token 成本，不是他的时间成本，按分数取也没有只有他知道的输入。
**这句话里原来还留着它** —— 两份正本（`AGENTS.md`「只有一处要人」、
`job-rank.md` Step 5「真正归人的只剩投出去那一下」）早就改了，这份抄件
没跟上，而本模块恰恰是有人**新加一道闸门时会来读的那一份**。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / "workflows"


def wf(name: str) -> str:
    return (WF / f"{name}.md").read_text(encoding="utf-8")


class ApplyDoesNotReAskWhatTheUserAlreadyAnswered(unittest.TestCase):
    """`/job-apply <URL>` 本身就是「我要投这个岗」。评完还问一遍，是把答案要第二次。

    原样：对**所有**判词都问「是否针对这个岗位起草三渠道投递话术？」。
    与批量模式的闸门表（强匹配/值得投 → 出话术，其余只落评估）同岗不同待遇：
    批量 78 分直接出材料，单投 78 分还要等用户点头。
    """

    def test_good_verdicts_proceed_without_asking(self):
        t = wf("job-apply")
        self.assertIn("直接继续第 1.5 步起草**，不问", t,
                      "强匹配/值得投又要用户点一次头了")

    def test_weak_verdicts_do_not_ask_either(self):
        """可以考虑 / 不建议也不问 —— 「出材料的成本」不是归人的判断。

        这条原来叫 `test_weak_verdicts_still_ask_because_that_is_a_real_choice`，
        钉的是「还要出材料吗」那一问，理由是「弱匹配上花不花材料成本，只有用户能定」。
        **那正是 2026-08-12 裁定推翻的那条**：出材料花的是 AI 的工时不是他的，
        要他点一次头才是真成本（`AGENTS.md`「命令怎么自动衔接」、`job-auto.md`
        「归机器」表第一行）。一条判据把被推翻的理由钉成了规则，在绿灯下活了三周；
        用户 2026-09-02 的原话：「auto 不就是会自动运行吗」。

        现在钉两件：可以考虑照出（他点名了这个岗，问题已在「投前必问」里）；
        不建议只落评估（与批量闸门表一致）。两档都**不问**。
        """
        t = wf("job-apply")
        # **只看表，不看表下面的引用块。** 那段注释在解释这条规则的来历，
        # 里面原样引着「还要出材料吗」—— 扫整份文件必中。
        # 表从「按判词分流」起，到第一个以 `>` 开头的行止。
        i = t.index("按判词分流")
        rest = t[i:]
        j = rest.find("\n>")
        seg = rest[: j if j > 0 else 1600]
        self.assertNotIn("还要出材料吗", seg,
                         "又回到「可以考虑就停下来问出不出材料」—— 08-12 撤掉的那道闸门")
        self.assertRegex(seg, r"\| 可以考虑 \|[^\n]*不问",
                         "可以考虑那一行没写「不问」")
        self.assertRegex(seg, r"\| 不建议 \|[^\n]*不问",
                         "不建议那一行没写「不问」")
        self.assertRegex(seg, r"\| 不建议 \|[^\n]*不出材料",
                         "不建议那一行没说不出材料 —— 和批量闸门表就对不上了")


class ResumeTailoringIsItsOwnCommand(unittest.TestCase):
    """定制简历不进 `/job-apply`——它归独立命令 `/job-cv`，且只在特殊情况用。

    这条走过一个来回（都在 2026-08-12）：先按「材料成本归 AI」把批量升成三样
    （深评+开场白+定制简历），用户随即裁定收回——**简历不是第一道门，平时发主简历
    就够**，定制是例外不是默认。钉住终态，防止哪一版又把简历塞回 apply 的默认路径。
    """

    def test_apply_batch_is_two_artifacts_again(self):
        t = wf("job-apply")
        self.assertIn("批量做两样：深评 + 开场白", t)
        self.assertNotIn("批量做三样", t, "三样版本回潮了——用户已裁定收回")

    def test_apply_does_not_run_step5(self):
        t = wf("job-apply")
        self.assertIn("`/job-apply` 从第 4 步直接进第 6 步", t)
        self.assertIn("`/job-cv` 的执行正文", t, "第 5 步的所有权没写清，执行时还会顺手定制")

    def test_the_cv_command_exists_and_defaults_to_no(self):
        t = wf("job-cv")
        self.assertIn("默认发主简历", t)
        self.assertIn("特殊情况", t)
        self.assertIn("第 5 步", t, "job-cv 没指回 apply.md 第 5 步——机器会被复制第二份")

    def test_the_cv_command_is_in_the_index(self):
        t = (ROOT / "workflows" / "INDEX.md").read_text(encoding="utf-8")
        self.assertIn("`/job-cv <公司>`", t)

    def test_light_tailoring_has_the_one_page_constraint(self):
        """溢页教训钉在 5b（唯一权威的定制纪律）里：优势段写长，1 页版式必炸。"""
        self.assertIn("不得长于原版对应行", wf("job-apply"))

    def test_the_onboarding_docs_do_not_promise_tailored_resumes(self):
        """`SETUP.md` / `README.md` 也不许说 `/job-apply` 出定制简历。

        上面几条盯的是 `job-apply.md` / `job-cv.md` / `job-auto.md` / `AGENTS.md`
        —— **新用户真正照着做的那两份反而没人管**。
        2026-08-21 通读时抓到 `SETUP.md` 第 445 行还写着
        「起草三渠道投递话术……**与定制中文简历**」，停在 2026-08-12 裁定之前。

        判据只看 `/job-apply` 的流程说明那一段，不管别处提「定制简历」
        （两份文档都要能正常介绍 `/job-cv`）。
        """
        setup = (ROOT / "SETUP.md").read_text(encoding="utf-8")
        i = setup.index("## 5. 跑一遍完整流程")
        seg = setup[i:setup.index("## 6.", i)]
        self.assertNotIn(
            "与定制中文简历", seg,
            "SETUP 的 /job-apply 流程里还说它出定制简历 —— "
            "2026-08-12 已裁定：apply 发主简历，定制归 /job-cv")
        self.assertIn(
            "本命令不做定制", seg,
            "SETUP 的 /job-apply 流程没说清简历不定制")

    def test_auto_does_not_promise_resumes(self):
        t = wf("job-auto")
        self.assertIn("定制简历不进批量", t)
        self.assertNotIn("三样一次备齐", t)


class ConsiderTierHasAOneShotCommand(unittest.TestCase):
    """「可以考虑」档要不要出材料是真选择——但答案该一条命令给完，不是逐岗问 N 遍。"""

    def test_the_command_exists_in_the_workflow(self):
        t = wf("job-apply")
        self.assertIn("`/job-apply 可以考虑`", t)
        self.assertIn("这条命令本身就是那一问的答案", t,
                      "没写清命令即回答——执行时还会逐岗再问一遍")

    def test_the_command_is_in_the_index(self):
        """工作流索引是面板帮助的正文——命令不进索引，用户就不知道能这么敲。
        （索引表正本现在在 workflows/INDEX.md，2026-09-29 起。）"""
        t = (ROOT / "workflows" / "INDEX.md").read_text(encoding="utf-8")
        self.assertIn("`/job-apply 可以考虑`", t)

    def test_batch_default_has_no_silent_cap(self):
        """批量缺省不限量，且开跑前必须报数。

        用户 2026-08-12：「job-apply 默认是多少，要不然默认就100？这样基本就勾了」。
        固定数字会过期——岗池长过那个数，它就成了一道不出声的截断，
        用户以为勾满了其实没有。缺省不限量 + 开跑前报数，才既全覆盖又可预估。
        """
        t = wf("job-apply")
        self.assertIn("不给 N 就是不限量", t)
        self.assertNotIn("`N` 缺省 20", t, "缺省 20 还在，会静默截断")
        self.assertIn("开跑前先报数", t, "不限量就必须报数，否则用户没法预估规模")

    def test_one_command_covers_everything_worth_preparing(self):
        """「除了不投的都准备好」必须是一条命令，不是「先 auto 再 可以考虑」两条。

        用户 2026-08-12 原话：「有没有一个命令，可以让除了 不投的都用apply来准备命令」。
        在此之前 `/job-auto` 停在「值得投」、「可以考虑」要另敲一次——
        要备齐得敲两条，还得先知道判词分几档。
        """
        t = wf("job-apply")
        self.assertIn("`/job-apply 全部`", t, "job-apply 里没有「全部」这个入口")
        self.assertIn("除了不投的", t, "没写出用户会用的说法")
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "tools"))
        import _cli
        for tier in _cli.VERDICTS[:3]:      # 档名跟正本走，改档名时文档检查同步变
            with self.subTest(tier=tier):
                self.assertIn(tier, t)
        self.assertIn("哪些算「不投」", t, "没写清 全部 排除掉哪些——边界不明会误伤")
        idx = (ROOT / "workflows" / "INDEX.md").read_text(encoding="utf-8")
        self.assertIn("`/job-apply 全部`", idx,
                      "命令不进工作流索引，面板帮助里就看不到，用户不知道能这么敲")

    def test_already_evaluated_ones_are_not_locked_out(self):
        """已深评的「可以考虑」岗必须能补开场白——不重评，但不是不给话术。

        2026-08-12 实测：这一模式照搬了主批量的「已深评的不重评」当排除条件，
        于是**当年被闸门拦下的 62 个岗**（有评估、没话术）永远选不中。
        那条件防的是重复花钱评估，不是把话术锁死。
        """
        t = wf("job-apply")
        self.assertIn("`evaluated` 那条在这个模式下不作排除", t)
        self.assertIn("直接用它现成的", t, "没写清「不重评但补话术」的分流做法")


class AutoWrapUpSettlesTheBooks(unittest.TestCase):
    """auto 收尾必须补账再刷面板。实测漏过：出完 20 份深评没跑 writeback，
    面板排序读的还是粗筛旧账，靠导出脚本的警告才发现。"""

    def test_writeback_is_in_the_wrap_up(self):
        t = wf("job-auto")
        self.assertIn("tools/writeback.py --apply", t)
        i, j = t.find("收尾（无条件）"), t.find("writeback.py --apply")
        self.assertTrue(0 <= i < j, "writeback 没写进收尾块")


class SetupDoesNotTeachTheRedundantStep(unittest.TestCase):
    """`/job-setup` 的收尾不许教「搜完再跑 /job-rank」—— 那一步早就自动了。

    `/job-scrape` 的 Step 5.5 写着「报完覆盖情况就接着跑 `/job-rank --auto`，
    默认开着，`--no-rank` 才关」。所以让用户搜完再敲一次 rank 是**空转**。

    AGENTS.md 已经为这件事立过规矩：「接缝焊死之后，教程里那一步也要跟着删 ——
    多教一步的代价不是多敲一次，是让人以为不敲就会漏东西。」
    README 当时改了，**而新用户真正读到的那句话在 `/job-setup` 的收尾里**，
    它一直留着（2026-08-21 通读时发现）。

    判据只管**收尾那一段**：全文别处提 `/job-rank` 是正常的
    （能力分工、`--section` 说明都会提）。
    """

    def test_the_closing_summary_does_not_chain_rank_after_scrape(self):
        t = wf("job-setup")
        i = t.index("## Step 4：确认，并给出下一步")
        seg = t[i:]
        for bad in ("搜完跑 `/job-rank`", "搜完再跑 `/job-rank`",
                    "然后跑 `/job-rank`", "接着跑 `/job-rank`"):
            self.assertNotIn(
                bad, seg,
                f"收尾里写着「{bad}」—— 而 /job-scrape 抓完自动接 rank，"
                "多教这一步会让人以为不敲就会漏东西")

    def test_no_shipped_doc_chains_rank_after_scrape(self):
        """全仓任何一份 shipped markdown 都不许把 scrape → rank 画成箭头链。

        判据只抓**箭头链**（`/job-scrape` → `/job-rank`），不抓并列枚举 ——
        「主线那一行的命令：`/job-setup`、`/job-scrape`、`/job-rank`、…」是清单，
        「中间三段也可以单独敲」是实话，都合法。箭头才是在教顺序。

        2026-08-21 实测：改完 README 与 `/job-setup` 的收尾之后，
        **`SETUP.md:53` 还留着一条**（「只装 ①，跑 `/job-setup` → `/job-scrape`
        → `/job-rank`」）。**同一条规则的第三个落点** —— 前两处改了，
        没人回头扫一遍其余的。
        """
        import re
        import subprocess

        out = subprocess.run(["git", "ls-files", "*.md"], cwd=ROOT,
                             capture_output=True, text=True, encoding="utf-8")
        if out.returncode != 0:
            self.skipTest("跑不了 git ls-files")
        pat = re.compile(r"job-scrape[^\n]{0,20}(?:→|->)[^\n]{0,12}/?job-rank")
        bad = []
        for f in out.stdout.split():
            for n, ln in enumerate(
                    (ROOT / f).read_text(encoding="utf-8").splitlines(), 1):
                # 讲这条规则本身的行放过（AGENTS.md 引用了反例）
                if "别把这条脊梁" in ln or "一度写" in ln or "空转" in ln:
                    continue
                if pat.search(ln):
                    bad.append(f"{f}:{n}")
        self.assertEqual(
            bad, [],
            "这些地方把 scrape → rank 画成了箭头链，而 /job-scrape 抓完自动接 rank —— "
            "多教一步会让人以为不敲就会漏东西：" + " · ".join(bad))

    def test_scrape_really_does_auto_rank(self):
        """控制用例：那一步确实是自动的，否则本判据拦的是不存在的规则。"""
        self.assertIn("接着跑 `/job-rank --auto`", wf("job-scrape"),
                      "/job-scrape 不再自动接评分了？那 setup 的收尾该改回去")


class BatchDoesNotSpendOnDeadPostings(unittest.TestCase):
    """选岗清单里必须有 `expired`——下线岗做完材料也投不出去。

    2026-08-12 实测 `/job-apply --top 50`：72 个候选里 5 个已下线，两个还排在最前
    （81 分、66 分）。判词那一行拦不住：下线岗的判词可能正是「粗筛：值得投」，
    也可能是「已评分」这种既不含「跳过」也不含「不建议」的串。

    ## 这份说明原来自己也把数写错了

    第一版开头写的是「选岗**六条**」，而代码块里一直是 **7 条**——
    `job-apply.md` 正文同样写着「六条」，而同一份文件另外两处写的是「七条」。
    **同一个数在一份文件里出现三次、两处对不上**（2026-08-21 通读时发现）。

    所以下面那条判据**自己去数**，不在这里再写一个数：
    数字只要被人手抄第二遍，早晚会分叉。
    """

    #: 中文数字，够用到十。
    CN = "零一二三四五六七八九十"

    def test_expired_is_one_of_the_selection_conditions(self):
        t = wf("job-apply")
        self.assertIn('j["expired"] is falsy', t,
                      "选岗条件没排除已下线的岗——最贵的深评会花在投不出去的岗上")

    def test_the_stated_count_matches_the_list(self):
        """引出那个代码块的那句话里写的条数，必须等于块里真列出来的条数。

        **只查这一句**，不扫全文：同一段里「其余五条（…）」说的是七条里的
        一个子集，合法。判据扫宽一点就会把它误报成分叉。
        """
        t = wf("job-apply")
        i = t.index("条件就这几个字段")
        intro = t[i:t.index("```", i)]
        block = t[t.index("```", i):t.index("```", t.index("```", i) + 3)]
        n = len([l for l in block.splitlines() if l.strip().startswith("j[")])
        self.assertGreaterEqual(
            n, 5, f"选岗条件的代码块只抽到 {n} 行，判据在对着空气跑")
        self.assertIn(
            f"（{self.CN[n]}条", intro,
            f"代码块里实际列了 {n} 条，引出它的那句话却不是「{self.CN[n]}条」："
            f"{intro.strip()[:70]}")


class GmailSyncAppliesCertainEvidenceAndStagesTheRest(unittest.TestCase):
    """与 prescreen 同一条纪律：客观证据结案，推断只降权（这里是只列出）。

    ## 铁律要跟得上正文

    Step 6 把处理改成了**两档**（「直接写回」/「等你确认」），并明写
    「不再把所有改动攒着等确认」。而文末铁律 2 一直停在改版之前：
    「**用户批准 Step 6 那一批之前，什么都不许写。**」

    **同一份文件，一处说「确凿的直接写」，一处说「一个字都不许写」。**
    而这条命令会自动改 `job_search_tracker.csv` —— 矛盾落在最要紧的地方
    （2026-08-21 通读时发现）。

    `AGENTS.md` 的索引是权威：「证据确凿的直接回写（可撤销），
    含糊的列出来等你确认」—— 两档是现行设计，铁律 2 是旧的。
    """

    def test_the_iron_rule_does_not_forbid_the_auto_tier(self):
        """铁律不许说「什么都不许写」—— 那会把 Step 6 的「直接写回」档否掉。"""
        t = wf("job-gmail-sync")
        i = t.index("## 铁律")
        rules = t[i:]
        self.assertIn("直接写回", t, "Step 6 的两档没了？那这条判据该重看")
        self.assertNotIn(
            "用户批准 Step 6 那一批之前，什么都不许写", rules,
            "铁律还在说「什么都不许写」，而 Step 6 有「直接写回」那一档 —— "
            "同一份文件两个规矩，执行者按哪条做都能自圆其说")
        self.assertIn(
            "「等你确认」那一档", rules,
            "铁律没把「不许写」限定到「等你确认」那一档")

    def test_offers_never_auto_write(self):
        """再确凿的 offer 也只进「等你确认」—— 它触发谈薪，写错的代价不同量级。"""
        t = wf("job-gmail-sync")
        self.assertRegex(
            t, r"offer[^。]{0,30}(永远|一律)[^。]{0,20}等你确认",
            "没写清 offer 类永远不自动写回")

    def test_two_tiers_exist(self):
        t = wf("job-gmail-sync")
        self.assertIn("直接写回", t)
        self.assertIn("等你确认", t)

    def test_the_certain_tier_requires_both_conditions(self):
        """匹配唯一 + 信号确凿，缺一进「等确认」。只钉一条就会漏另一半。"""
        t = wf("job-gmail-sync")
        self.assertIn("匹配唯一", t)
        self.assertIn("信号确凿", t)

    def test_offers_always_wait_for_the_user(self):
        """offer 触发谈薪流程，写错的代价与拒信不同量级——再确凿也不自动写。"""
        t = wf("job-gmail-sync")
        self.assertIn("offer 类永远进「等你确认」档", t.replace("**", ""),
                      "offer 被划进了自动写回档")

    def test_it_refreshes_the_panel_after_writing(self):
        t = wf("job-gmail-sync")
        self.assertIn("export_web_data.py", t, "写回后不刷新面板，同步像没生效")


class EveryStateWriterRefreshesThePanel(unittest.TestCase):
    """写了 seen_jobs / 台账却不刷新 data.json，面板就在撒谎——展示的是写之前的状态。

    **名单从 README 那句承诺里现取，不写死。** 这里原来钉着四个名字，而
    `README.md`（和 `SETUP.md`）那一行承诺的是**七个**——
    `/job-rank`、`/job-outcome`、`/job-gmail-sync`、`/job-user`、`/job-cv`、
    `/job-reset`、`/job-scrape --no-rank`。差的那三个当时恰好都做对了，所以没人
    发现；可它们**没有被任何检查盯着**：哪天谁把 `job-user.md` 的收尾重导删了，
    README 照旧承诺，测试照旧全绿，而下一个切用户的人会看到上一个人的投递记录。

    `job-auto` 不在那句承诺里，但它确实也写状态，所以另外补上。
    """

    #: README 里承诺「收尾刷新面板数据」的那几条 —— 判据跟着承诺走
    PROMISE = "收尾刷新面板数据"
    EXTRA = ["job-auto"]

    @classmethod
    def _promised(cls, doc: str = "README.md") -> list:
        text = (ROOT / doc).read_text(encoding="utf-8")
        # README 用段落，SETUP 用用途表；两者只取刷新说明对应的命令。
        marker = re.compile(r"收尾刷新面板数据|完成后刷新总览数据")
        line = next((ln for ln in text.splitlines() if marker.search(ln)), "")
        if line.lstrip().startswith("|"):
            head = line.split("|")[1]
        else:
            head = marker.split(line)[0]
        seg = head.rsplit("以及", 1)[-1]
        return sorted(set(re.findall(r"/(job-[a-z-]+)", seg)))

    def test_the_promise_is_still_there(self):
        """控制用例：承诺那句话没了，下面那条就成了空跑。"""
        got = self._promised()
        self.assertGreaterEqual(
            len(got), 5,
            f"README 里「{self.PROMISE}」那句话没找到或形状变了（只解析出 {got}）——"
            "判据失去依据，回去看那一行")

    def test_setup_promises_the_same_list(self):
        """`SETUP.md` 抄了同一句承诺。**两份必须一致**，否则读哪一份取决于运气。

        判据只认 `README.md` 那一份（上面那条测试就是照它跑的）。SETUP 那份如果
        少一个命令名，读 SETUP 的人以为切用户不重导；多一个，测试不会去查它。
        两种都是「文档说了、没人管」。
        """
        a, b = self._promised("README.md"), self._promised("SETUP.md")
        self.assertEqual(
            a, b,
            "README 与 SETUP 承诺的收尾刷新命令对不上：\n"
            f"  README: {a}\n  SETUP:  {b}")

    def test_each_writer_ends_with_an_export(self):
        for name in self._promised() + self.EXTRA:
            with self.subTest(cmd=name):
                self.assertIn("export_web_data", wf(name),
                              f"{name} 写完状态不刷新面板，而 README 承诺了它会")

    def test_user_switch_reexports(self):
        """切换用户不重导，面板端出的是**上一个人**的投递记录——命名空间隔离的仓库里，
        这不是数据过时，是把别人的求职数据给了错的人。"""
        t = wf("job-user")
        self.assertIn("export_web_data.py", t, "切换用户后没有重导面板数据")
        self.assertIn("上一个人", t, "没写清为什么必须重导——下次会被当成可省略的收尾")


class TheChainIsDocumentedInOnePlace(unittest.TestCase):
    """接线图归 AGENTS.md（权威来源）。散在各文件里，改一处漏一处。"""

    def test_agents_has_the_chain_map(self):
        t = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("命令怎么自动衔接", t)

    def test_it_names_exactly_one_human_point(self):
        """2026-08-12 裁定后全链路只剩一处主动要人：投出去。被动例外（事实问询、
        验证码）也要列出，否则执行时会被当成「顺手也自动了」。"""
        t = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("只有一处要人：投出去那一下", t)
        self.assertIn("验证码只能你亲手过", t)
        self.assertNotIn("只有两处要人", t,
                         "旧的两处版本还在——两份说法并存必有一份在撒谎")

    def test_the_panel_no_longer_teaches_the_manual_handoff(self):
        """scrape 已自动接评分，面板的下一步还教「抓完接着 /job-rank 打分」，
        等于把焊死的接缝重新说成断的。"""
        src = (ROOT / "tools" / "build_dashboard.py").read_text(encoding="utf-8")
        self.assertNotIn("抓完接着 /job-rank 打分", src)
        self.assertIn("抓完会自动评分", src)

    def test_scrape_title_says_what_it_now_does(self):
        """标题是 `/` 菜单里的第一行说明。行为改成「抓完自动评」而标题还写
        「和抓过的自动去重」，用户会以为抓完还得自己评。"""
        h1 = wf("job-scrape").splitlines()[0]
        self.assertIn("自动评分", h1, f"标题没跟上新行为：{h1}")



def _section(path, title: str) -> str:
    """按标题切一节。**先屏蔽围栏代码块** —— 否则模板里的 `## 职位排序` 会被
    当成下一节的开头，`job-rank.md` 的 Step 5 会从 8213 字缩成 25 字。

    写这条守卫时按不屏蔽的切法量了两次，两次都得出「理由不在 Step 5」这个
    假结论 —— 一次是没找到边界退回了固定窗口，一次是切在了围栏里的标题上。
    """
    import re as _re

    raw = path.read_text(encoding="utf-8")
    fence, keep = False, []
    for ln in raw.split(chr(10)):
        if ln.lstrip().startswith("```"):
            fence = not fence
            keep.append(" " * len(ln))
            continue
        keep.append(" " * len(ln) if fence else ln)
    masked = chr(10).join(keep)
    heads = [m.start() for m in _re.finditer(r"^## .*$", masked, _re.M)]
    for i, pos in enumerate(heads):
        if masked.startswith("## " + title, pos):
            end = heads[i + 1] if i + 1 < len(heads) else len(raw)
            return raw[pos:end]
    return ""


class MaterialsFollowScoresWithoutAGate(unittest.TestCase):
    """「有几处要人」这件事有三个住址，2026-08-31 实测其中一个已经分叉。

    两份正本都说**一处**：`AGENTS.md`「只有一处要人：投出去那一下」、
    `job-rank.md` Step 5「全链路真正归人的只剩投出去那一下」。而本模块开头
    原来写着「只允许两处问人：投哪几个、投出去那一下」—— 把 2026-08-12 撤掉
    的那道点头闸门仍然列为允许。

    **本模块正是有人新加一道闸门时会来读的那一份。**
    `test_auto_mode_does_not_stop_early` 里那句「别按『材料很贵所以要问』把
    闸门加回来」防的就是这件事 —— 而它当时引的正是这个类名，**类却不存在**。
    声称有守卫比没有守卫更糟：读的人以为验过了，就不再去看。

    三条断言分别对应三个住址，不比对措辞（抄件本来就该用自己的话）。

    ⚠️ **只读模块 docstring，不扫全文。** 讲这条规则的文字自己要引用那几个词，
    扫全文就会撞上自己的反例 —— 这个仓库的常客。
    """

    @staticmethod
    def _module_doc() -> str:
        import ast as _ast
        return _ast.get_docstring(
            _ast.parse(Path(__file__).read_text(encoding="utf-8"))) or ""

    def test_the_authority_still_says_one(self):
        t = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("只有一处要人", t,
                      "正本不再说「只有一处要人」——那这条守卫钉的就不是现行规则了")

    def test_this_module_does_not_say_two(self):
        doc = self._module_doc()
        self.assertIn("只有一处", doc, "本模块说明没跟上正本的「只有一处」")
        self.assertNotIn("两处问人", doc,
                         "本模块说明又写回「两处问人」——那道闸门 2026-08-12 撤了")

    def test_the_cited_section_actually_carries_the_reason(self):
        """`AGENTS.md` 写「理由见 `workflows/job-rank.md` Step 5」——那一节得真载着它。

        现有的 `test_cross_references_resolve` 只验**小节存不存在**，不验它
        是否真说了引用方声称的那件事。这里补上这一格：撤闸门的理由与日期
        都得在那一节里，不然照着引用去读的人会扑空。
        """
        seg = _section(WF / "job-rank.md", "Step 5")
        self.assertTrue(seg, "job-rank.md 里切不出 Step 5")
        for token in ("2026-08-12", "不再问", "投出去那一下"):
            with self.subTest(token):
                self.assertIn(token, seg,
                              "AGENTS.md 说理由在 Step 5，那一节里却没有 " + token)


if __name__ == "__main__":
    unittest.main()


class WritersRefreshThePanel(unittest.TestCase):
    """会写盘的命令，收尾都要刷新面板。

    2026-08-13 全面检查命令逻辑时扫出两个漏的：

      `/job-scrape --no-rank` —— 默认那条路靠**转手给 `/job-rank`** 间接刷新，
          而加上 `--no-rank` 转手就没了，刷新跟着一起没。
          **搭在别人身上的收尾，别人不在时就不存在。**
      `/job-reset` —— 清完盘不清屏，总览页还显示着刚被清掉的岗。

    不刷的后果不是「数字旧一点」：用户看到的是跑之前的状态，
    会以为命令没生效，然后再跑一遍。
    """

    #: 只改个人资料、不动职位库的可以不刷。
    #:
    #: 后两条是 2026-09-02 换成推导之后露出来的**假阳性**，逐条核过才放行 ——
    #: 判据不是「看着像」，是**面板到底读不读它写的那个东西**。
    NO_PANEL = {"job-setup": "只写 profile/，不产生任何上面板的东西",
                "job-expand": "只往 profile/ 里补经历",
                "job-notion-sync": "它写的是 Notion，不是仓库。正文「永远只有一个"
                                   "方向」那条明写「绝不回流到 seen_jobs.json、"
                                   "投递记录或任何仓库文件……读仓库状态、写目标端」",
                "job-offer": "只往投递记录那一行的 `notes` 里写一句答复期，"
                             "而 `notes` 这一列导出器不读（`export_web_data` 与 "
                             "`build_dashboard` 里都查不到它）—— 面板上没有一处会变"}

    def test_every_writer_refreshes(self):
        bad = []
        for n in self._writers():
            if n in self.NO_PANEL:
                continue
            body = "\n".join(
                l for l in (ROOT / "workflows" / f"{n}.md")
                .read_text(encoding="utf-8").splitlines()
                if not l.lstrip().startswith(">"))
            if "export_web_data" not in body:
                bad.append(f"{n}：写了面板读的数据却不刷面板")
        self.assertEqual(bad, [], "\n  ".join(bad))

    #: 面板直接读的那几份盘上数据。
    PANEL_DATA = ("seen_jobs.json", "job_search_tracker.csv", "job-outcome.md",
                  "resume_refresh.json", "documents/applications")

    def _writers(self) -> list:
        """**从正文推导，不写死名单。**

        判据：非引用正文里有**同一行**既点名面板数据、又带写动作。
        行级是必须的 —— 文件级会把只读它们的命令一起框进来
        （`job-notion-sync` 明写「那两个仓库文件对它来说是只读的」、
        `job-setup` 读归档做校准），实测各误报一次。
        """
        verb = re.compile(r"(写回|写入|写进|更新|追加|落盘|记一笔|覆盖|删掉|清空)")
        # 第二半：**调用了会写面板数据的工具**也算。
        # 只按文件名匹配会漏掉一整类 —— `/job-refresh` 从不点
        # `resume_refresh.json` 的名，它敲的是 `resume_refresh.py --done`。
        # 变异当场照出来：撤掉它的刷新那一步，上面那条**照样绿**。
        # 工具那半也推导，不手写：源码里既碰面板数据、又有落盘动作的就算。
        writers_tool = set()
        for t in sorted((ROOT / "tools").glob("*.py")):
            src = t.read_text(encoding="utf-8", errors="replace")
            if (any(p in src for p in self.PANEL_DATA + ("set_resume_refreshed",))
                    and re.search(r"(write_text|atomic_write|set_status|"
                                  r"set_resume_refreshed\()", src)):
                writers_tool.add(t.stem)
        out = []
        for wf in sorted((ROOT / "workflows").glob("job-*.md")):
            body = [l for l in wf.read_text(encoding="utf-8").splitlines()
                    if not l.lstrip().startswith(">")]
            joined = "\n".join(body)
            by_line = any(any(p in l for p in self.PANEL_DATA) and verb.search(l)
                          for l in body)
            by_tool = any(f"tools/{t}.py" in joined for t in writers_tool)
            if by_line or by_tool:
                out.append(wf.stem)
        return out

    def test_the_writer_scan_sees_something(self):
        """控制用例：推导得出几条，否则上面那条对着空气跑。"""
        got = self._writers()
        self.assertGreaterEqual(len(got), 5, f"只推导出 {got} —— 判据八成失效了")

    def test_exemptions_are_justified(self):
        for n, why in self.NO_PANEL.items():
            with self.subTest(cmd=n):
                self.assertGreater(len(why), 8)
                self.assertTrue((ROOT / "workflows" / f"{n}.md").is_file())


class EveryJdReaderRestatesTheTrustBoundary(unittest.TestCase):
    """读 JD 的命令，都要自己写清「JD 是不可信数据」。

    `AGENTS.md` 有全局安全铁律，但**光靠全局一条不够**：这些流程文件是被
    单独读取执行的（入口壳只说「读取并严格执行 workflows/这条的工作流」），
    一条只写在总纲里的规则，执行到具体命令时不一定在上下文里。

    2026-08-13 全面检查命令逻辑时扫出三条漏了：`/job-rank`（**一轮读上百份 JD、
    批量跑、人不在场看**）、`/job-upskill`、`/job-offer`（offer 邮件同属外部输入）。
    而 `/job-apply`、`/job-scrape`、`/job-auto` 都写了——同一条规则，覆盖一半。
    """

    #: 会把外部文本读进来的命令。
    #:
    #: ⚠️ **手工名单会烂。** 2026-08-21 实测：`job-outcome` 与 `job-setup` 都读归档里的
    #: `posting.md`，却从没被加进这张表——而它们的用法恰恰是后果最重的两种
    #: （一条拿它写**发给雇主**的跟进话术，一条拿它写**用户的永久档案**）。
    #: 上面那句「加新的读 JD/邮件的命令就往这里加」是一道**人工步骤**，它被漏掉了。
    #:
    #: 所以下面多了一条 `test_the_list_covers_every_posting_reader`：
    #: **凡是提到 `posting.md` 的工作流都必须在这张表里**——名单还是手工的
    #: （有些命令读的是邮件不是 JD，推导不出来），但**漏加会当场红**。
    JD_READERS = ["job-scrape", "job-rank", "job-apply", "job-cv", "job-auto",
                  "job-upskill", "job-interview", "job-offer",
                  "job-outcome", "job-setup",
                  # `/job-expand` 不读 `posting.md`，所以下面那条推导抓不到它 ——
                  # 但它**抓用户主页、抓外部链接、上网搜**，再把结果写进
                  # `profile/candidate.md`。按那条推导自己写的原则
                  # 「规则跟着**内容**走，不跟着**时机**走」，它该在名单里。
                  # 2026-08-21 通读时它是唯一一条读外部内容却没写边界的命令。
                  "job-expand",
                  # `/job-notion-sync` Step 5.2 **用网页抓取能力取那个职位链接**，
                  # 把摘要写进 Notion 页面 —— 读的正是同一份不可信内容。
                  # 下面按 `posting.md` 的推导抓不到它：它读的是**活链接**，
                  # 归档那份不经它手。2026-09-01 通读时发现，此前整条漏掉。
                  # 它还是唯一一条**既读 JD、又能往外部服务写入**的命令。
                  "job-notion-sync"]

    def test_each_one_says_it(self):
        import re as _re
        bad = []
        for n in self.JD_READERS:
            f = ROOT / "workflows" / f"{n}.md"
            if not f.is_file():
                bad.append(f"{n}：工作流文件不存在"); continue
            if not _re.search(r"不可信|绝不执行 JD|JD 里嵌入的指令|信任边界",
                              f.read_text(encoding="utf-8")):
                bad.append(f"{n}：没写「JD 是不可信数据」")
        self.assertEqual(bad, [],
                         "这些命令会读外部文本却没复述信任边界：\n  " + "\n  ".join(bad))

    def test_the_list_covers_every_posting_reader(self):
        """归档里的 `posting.md` 是同一份不可信内容的**落盘副本**，读它的都要在名单里。

        规则要跟着**内容**走，不跟着**时机**走：存下来之后它依然不可信，
        而重读时少了「刚从不可信站点抓来」那层语境，**更容易被当成自家资料**。
        """
        readers = sorted(f.stem for f in (ROOT / "workflows").glob("*.md")
                         if "posting.md" in f.read_text(encoding="utf-8"))
        self.assertTrue(readers, "一条读 posting.md 的工作流都没扫到？判据失效了")
        missing = [n for n in readers if n not in self.JD_READERS]
        self.assertEqual(
            missing, [],
            f"这些工作流读归档里的职位描述，却不在 JD_READERS 里：{missing}。"
            "手工名单漏一条，那条命令就没人要求它复述信任边界")

    #: 「这条工作流会去碰外部页面内容」的判据。**不是名单，是特征** ——
    #: 名单要人记得加，而上面 `job-expand`、`job-notion-sync` 两次漏加
    #: 证明那道人工步骤靠不住。
    _FETCHES = re.compile(
        r"浏览器取数|网页抓取能力|WebFetch|网络搜索|read_page|抓取页面")
    _SAYS_BOUNDARY = re.compile(r"不可信|绝不执行 JD|JD 里嵌入的指令|信任边界")

    def test_every_workflow_that_fetches_says_the_boundary(self):
        """**凡是会去取外部页面内容的工作流，都要复述信任边界。**

        原来只有一条派生检查，键是「文里有没有 `posting.md`」—— 它管的是
        **归档副本**那一路。而外部内容进来的路不止一条：

        - `/job-notion-sync` 取的是**活链接**（Step 5.2），归档那份不经它手；
        - `/job-add-portal` 取的是目标平台的原始响应，而且**照它写代码**；
        - `/job-refresh` 在登录态下**真的会点按钮**，同一页上就有「简历代投」；
        - `/job-resume` 读平台上那份在线简历页，结论用户会照着改简历。

        四条 2026-09-01 通读时**一条都没写边界**，四条都躲过了 `posting.md`
        那道推导。所以判据换成特征：会取外部内容 ⇒ 必须写。
        名单（`JD_READERS`）仍然保留 —— 它多管一件事：复述得**够不够**。
        """
        bad = []
        for f in sorted((ROOT / "workflows").glob("*.md")):
            t = f.read_text(encoding="utf-8")
            if self._FETCHES.search(t) and not self._SAYS_BOUNDARY.search(t):
                bad.append(f.stem)
        self.assertEqual(
            bad, [],
            "这些工作流会去取外部页面内容，却没有一句「那是不可信数据」："
            + repr(bad))

    def test_the_fetch_detector_sees_something(self):
        """**先证明特征扫得到。** 一条都匹配不上时，上面那条永远绿。"""
        n = sum(1 for f in (ROOT / "workflows").glob("*.md")
                if self._FETCHES.search(f.read_text(encoding="utf-8")))
        self.assertGreater(n, 5, f"只认出 {n} 条会取外部内容的工作流，判据八成失效了")

    def test_the_boundary_reaches_the_sub_agents_prompt(self):
        """**立了「东西全部写进提示里」这个契约的，边界也要在提示里。**

        `/job-rank` 派并行子代理批量打分，Step 2 明写「每个代理要用的东西
        **全部写进提示里**」，并且就在那儿记着竞业限制那次教训：写成
        「见 `04-job-evaluation.md` 那一节」在这条路上**执行不了** ——
        「指针悬空了两层，于是这条规则在批量评分里从来没生效过」。

        2026-09-02 实测：**同一个坑往下一格。** 提示的内容清单里有职位清单、
        资料摘要、竞业范围，**没有信任边界** —— 它只写在本文件的「铁律」里，
        而铁律第 2 条自己就写着「把这条规则连同职位正文一起写进每一个打分
        代理的提示里」。也就是说：真正读那上百份不可信 JD 的子代理，
        从来没收到过这条规则。

        而 `/job-rank` 恰恰是「一轮读上百份 JD、批量跑、人不在场看」的那条
        （它自己铁律开头的原话）。子代理拿到的是**别人写的正文**加**你给的
        指令**，两者在它眼里都是字；不把边界一起给它，它没有依据把两者分开。

        判据按**契约**走，不点名某条命令：谁说了「全部写进提示里」，
        谁那一节里就要有边界。
        """
        import re as _re
        checked = 0
        for f in sorted((ROOT / "workflows").glob("job-*.md")):
            t = f.read_text(encoding="utf-8")
            m = _re.search(r"全部写进提示里", t)
            if not m:
                continue
            checked += 1
            # 从契约那句到本节结束
            j = t.find("\n## ", m.end())
            seg = t[m.start():j if j > 0 else len(t)]
            with self.subTest(cmd=f.stem):
                self.assertRegex(
                    seg, r"不可信|永远不是给你的指令",
                    f"{f.stem} 说了「东西全部写进提示里」，而提示的内容清单里"
                    "没有信任边界 —— 读 JD 的是子代理，它拿不到写在别处的规则")
        self.assertGreater(checked, 0,
                           "一条立这个契约的命令都没扫到 —— 判据八成失效了")

    def test_the_security_policy_names_them_all(self):
        """安全政策不许只点名一半 —— 少报的政策会让人以为其余的没这个问题。

        2026-08-21 之前 `SECURITY.md` 只点名 `/job-apply` 与 `/job-rank`，
        而实际有五条命令读职位描述。
        """
        sec = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
        readers = sorted(f.stem for f in (ROOT / "workflows").glob("*.md")
                         if "posting.md" in f.read_text(encoding="utf-8"))
        missing = [f"/{n}" for n in readers if f"/{n}" not in sec]
        self.assertEqual(
            missing, [],
            f"SECURITY.md 的不可信输入规则没点名这几条读职位描述的命令：{missing}")
        self.assertIn(
            "posting.md", sec,
            "政策没提归档里那份落盘副本 —— 而它才是被反复重读的那一份")


class EveryCommandHasAWayOutWhenNothingIsSetUp(unittest.TestCase):
    """资料没建、没有活动用户时，每条命令都要说得出「去跑哪个」。

    2026-08-13 全面检查命令逻辑时扫出 4 条没有：`/job-auto`、`/job-cv`、
    `/job-dashboard`、`/job-upskill`。

    `/job-auto` 最要紧——它是新手脊梁的第二条（`/job-setup` → `/job-auto`），
    而且**一口气跑很久、人不在场看**。靠子命令去挡不行：等跑到那一步再停，
    用户回来看到的是一堆半成品和一句「先去建资料」。
    **前置条件要在第一秒判，不是跑到一半判。**
    """

    #: 不需要前置的：它们自己就是建档/切换/装渠道/清空。
    NO_PRECONDITION = {"job-setup", "job-user", "job-add-portal", "job-reset"}

    def test_each_points_at_setup_or_user(self):
        import re as _re
        pat = _re.compile(
            r"(?:run|跑|去跑|引导.{0,6})\s*`?/job-(setup|user)`?|/job-setup\s*(?:first|先)")
        bad = []
        for f in sorted((ROOT / "workflows").glob("job-*.md")):
            if f.stem in self.NO_PRECONDITION:
                continue
            if not pat.search(f.read_text(encoding="utf-8")):
                bad.append(f.stem)
        self.assertEqual(bad, [],
                         "资料没建时这些命令给不出出路：\n  " + "\n  ".join(bad))

    def test_auto_checks_before_it_starts(self):
        """长跑命令尤其要在开跑前判——跑到一半才停等于白跑。"""
        t = (ROOT / "workflows" / "job-auto.md").read_text(encoding="utf-8")
        self.assertIn("开跑前的前置检查", t)
        self.assertIn("不是跑到一半判", t, "没说清为什么不能靠子命令挡")
