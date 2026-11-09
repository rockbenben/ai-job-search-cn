"""面试阶段只有一份清单：准备那侧和记录那侧必须对得上。

## 改了准备，没改记录

`interview.md` 的 Step 1.3 自己记着这笔账：

> 原来这里的四个选项是 phone screen / technical / case / final round，一个笔试都没有。
> 学生只能选 `technical`，然后拿到一份按「专业面 + STAR 案例」组织的准备包，
> 去应对一场两小时的在线编程考试。

于是它把阶段扩成了完整一套：在线测评 / 笔试·机试 / 群面·无领导 / 演练·实操·试讲 /
HR 初面 / 专业面·业务面 / 交叉面 / 总监面·终面 / 谈薪。

**可真正把阶段记下来的 `outcome.md` 归档模板，还是原来那四个英文选项。**

    ## Interview stages reached
    - [x] Phone screen (YYYY-MM-DD)
    - [ ] Technical interview
    - [ ] Case interview
    - [ ] Final round

做过笔试的人没有格子可打，只能勾「专业面」。而 `interview.md` 的 Step 1 正是从
`outcome.md` 读「走到哪一关了」来决定下一关怎么准备——**下一轮又按 STAR 案例组织**。
绕了一圈回到它自己写下的那个反例。

这就是这个仓库反复出现的形状：一条规则改在了它最显眼的那一处，
而真正执行它的那一处没动。

## 判据

`outcome.md` 归档模板里的每一个阶段勾选项，都要能在 `interview.md` 的阶段地图里找到；
且面试前那几关（在线测评、笔试机试、实操试讲）必须有格子——那正是当初出事的地方。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INTERVIEW = ROOT / "workflows" / "job-interview.md"
PREP = ROOT / "workflows" / "reference" / "07-interview-prep.md"
OUTCOME = ROOT / "workflows" / "job-outcome.md"

#: 面试**之前**就会淘汰人的那几关。当初漏的就是它们，所以单独钉住。
PRE_INTERVIEW = ("在线测评", "笔试", "实操")

#: 旧的四个英文选项，别再写回去。
RETIRED = ("Phone screen", "Technical interview", "Case interview", "Final round")

#: 末尾那个格子记的是**结果**不是关卡（原模板里是 `Offer received`），
#: 它本来就不该出现在 `interview.md` 的阶段地图里——那份地图回答的是
#: 「这一关怎么准备」，而拿到 offer 之后走的是 `/job-offer`，不是再准备一场面试。
NOT_A_STAGE = ("拿到 offer", "背调")

#: 「背调」同理：`07-interview-prep.md` 的阶段地图里有它（第 10 关，带薪资红线），
#: 归档要记，但它不是一场要准备的面试——走的是 `/job-offer` 的背调红线自查，
#: 不是 `interview.md` 的准备包。


def outcome_stages() -> list:
    """归档模板里那组阶段勾选项的名字。"""
    text = OUTCOME.read_text(encoding="utf-8")
    i = text.find("## 走到了哪几关")
    if i < 0:
        return []
    blk = text[i:text.find("\n## ", i + 1)]
    out = []
    for m in re.finditer(r"^-\s*\[[ x]\]\s*(.+?)\s*(?:（.*）)?\s*$", blk, re.M):
        out.append(m.group(1).strip())
    return out


def framework_stages() -> list:
    """`07-interview-prep.md` 的阶段地图——**这份才是权威**。

    `interview.md` 自己就写着「阶段与应对要点见 `07-interview-prep.md` 的阶段地图」。
    """
    t = PREP.read_text(encoding="utf-8")
    i = t.find("## 一、国内面试阶段地图")
    if i < 0:
        return []
    blk = t[i:t.index(chr(10) + "## 二、", i)]
    return [m.group(1).strip()
            for m in re.finditer(r"^\| \*\*(.+?)\*\* \|", blk, re.M)]


class OneStageListForPrepAndRecord(unittest.TestCase):

    def test_the_archive_really_lists_stages(self):
        """控制用例：归档模板里真有一组阶段，否则下面全是空跑。"""
        st = outcome_stages()
        self.assertGreaterEqual(
            len(st), 5,
            f"归档模板里只抽到 {len(st)} 个阶段：{st}——"
            "要么模板改了结构，要么阶段清单又被砍回去了")

    def test_the_retrospective_is_still_there(self):
        """控制用例：`interview.md` 里那段实测记录还在，否则本测试失去依据。"""
        self.assertIn(
            "一个笔试都没有", INTERVIEW.read_text(encoding="utf-8"),
            "interview.md 里那段「原来四个选项一个笔试都没有」的记录不见了")

    def test_every_archived_stage_exists_in_the_prep_map(self):
        """归档能勾的，准备那侧必须认得。"""
        prep = INTERVIEW.read_text(encoding="utf-8")
        bad = []
        for s in outcome_stages():
            if s in NOT_A_STAGE:
                continue
            # 「笔试 / 机试」这种并列，任一半对得上就算认得
            if not any(part.strip() in prep
                       for part in re.split(r"[/·]", s) if part.strip()):
                bad.append(s)
        self.assertEqual(
            bad, [],
            f"归档模板里这些阶段，`interview.md` 的阶段地图里没有：{bad}"
            "\n两份清单必须是同一份——记录那侧多出来的关，准备那侧不会为它组织内容。")

    def test_the_framework_map_is_found(self):
        """控制用例：07 的阶段地图抽得到。"""
        st = framework_stages()
        self.assertGreaterEqual(
            len(st), 8, f"07 的阶段地图只抽到 {st}——表格结构可能改了")

    def test_every_framework_stage_has_a_box(self):
        """**正向**：权威地图里的每一关，归档都要有格子。

        上面那条只查了反向（归档能勾的，准备侧要认得），所以 07 里有、
        归档里没有的关它看不见——实测就漏了「背调」：07 把它列为第 10 关并挂着
        薪资红线（口头报的数字对不上个税记录，offer 会被直接撤回），
        而归档里没有格子可打。
        """
        archived = " ".join(outcome_stages())
        bad = []
        for s in framework_stages():
            parts = [p.strip() for p in re.split(r"[/·]", s) if p.strip()]
            if not any(p in archived for p in parts):
                bad.append(s)
        self.assertEqual(
            bad, [],
            f"07 的阶段地图里有这几关，归档模板里没有格子：{bad}"
            + chr(10) + "07 是权威地图（interview.md 自己指向它）。归档记不下的关，"
            + chr(10) + "下一轮准备就无从知道用户走到哪了。")

    def test_the_pre_interview_stages_have_a_box(self):
        joined = " ".join(outcome_stages())
        missing = [s for s in PRE_INTERVIEW if s not in joined]
        self.assertEqual(
            missing, [],
            f"归档模板里没有这几关的格子：{missing}"
            "\n校招与部分技术/金融岗的淘汰主要发生在面试之前。没有格子，"
            "\n做过笔试的人只能勾「专业面」，下一轮准备就又按 STAR 案例组织了——"
            "\n那正是 interview.md 里记着的那个反例。")

    def test_the_readme_does_not_advertise_a_short_list(self):
        """README 介绍 `/job-interview` 时列的阶段，不能只有面试那几关。

        实测 README 写的是「HR 面 / 专业面 / 交叉面 / 终面 / 谈薪 / 背调」——**六关**，
        漏掉的正好是面试**之前**那四关（在线测评、笔试·机试、群面、演练·试讲）。
        而那正是 `interview.md` 自己记下的反例：「原来这里的四个选项一个笔试都没有，
        学生只能选 technical」。README 是这份清单的第三个消费方，前两个改了它没改。

        判据只查面试前那几关——它们是当初出事的地方，也是最容易被当成「不算面试」
        而略掉的。
        """
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        # ⚠️ 锚点要认**命令介绍**那一条，不是随便哪次提到 `/job-interview`。
        # 第一版用 `find("`/job-interview")`，命中的是依赖表里那次（第 42 行），
        # 700 字窗口里当然没有阶段清单——测试红得莫名其妙，而不是因为文档错了。
        i = readme.find("`/job-interview <公司>`")
        self.assertGreater(
            i, 0, "README 里找不到 `/job-interview <公司>` 那条命令介绍了——锚点要跟着改")
        blk = readme[i:].splitlines()[0]
        missing = [s for s in PRE_INTERVIEW if s not in blk]
        self.assertEqual(
            missing, [],
            f"README 介绍 /job-interview 时没提这几关：{missing}"
            + chr(10) + "校招与部分技术/金融岗的淘汰主要发生在面试之前。README 是用户"
            + chr(10) + "**最先读到**的那份，列一半会让人以为这命令只管面试。")

    def test_the_old_english_four_are_gone(self):
        text = OUTCOME.read_text(encoding="utf-8")
        back = [w for w in RETIRED if w in text]
        self.assertEqual(
            back, [], f"归档模板里又出现了旧的英文阶段：{back}")


if __name__ == "__main__":
    unittest.main()
