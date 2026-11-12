# -*- coding: utf-8 -*-
"""`/job-expand` 是唯一从**对内文件**往**对外资料**搬内容的命令，而它不知道保密这回事。

全文搜 `job-expand.md`（实测 2026-08-24）：`保密` 0 命中、`脱敏` 0 命中、
`客户名` 0 命中、`可披露` 0 命中。

而它扫的是 `documents/` —— 他的旧简历、在线简历导出、推荐信。**那些都是对内
写的**：客户名、当事人、内部项目代号、未公开的成果在里面自由出现，因为写它们
的时候没打算给下一家看。这一步把它们挖成「能力信号」写进 `candidate.md`，
而 `candidate.md` 是话术与简历**唯一**的事实来源。**一条挖错的，最后是发出去的。**

## 规则早就有了，只是这一步够不着

`03-writing-style.md` 铁律 6「别人的秘密不是你的证据」写得很全，还配了一张
脱敏对照表；`profile.example/candidate.md` 的「作品与项目的分层」也有
「可披露口径」那一列（三选一：能点名 / 只能脱敏 / 完全不能提）。

**但 `/job-expand` 的落点表里根本没有那张表这一行**，更没提那一列。于是挖进去
的条目一律不带口径，而铁律 6 对没标的只能降级成「起草前问用户一句」——
每条都问等于不问。

## 「这是不是我的能力」和「这条能不能对外说」是两个问题

而且**答案常常相反**：一个人最硬的经历，往往正是最不能点名的那条
（律师的当事人、会计师的委托方、销售的客户名单、设计师未授权的稿）。
Step 4 把两问混在一起，用户点头的是前一个。
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXP = (ROOT / "workflows" / "job-expand.md").read_text(encoding="utf-8")
STYLE = (ROOT / "workflows" / "reference"
         / "03-writing-style.md").read_text(encoding="utf-8")
TPL = (ROOT / "profile.example" / "candidate.md").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*(?:>|#:?)\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


def seg() -> str:
    i = EXP.index("#### 落进那张表的，必须带「可披露口径」")
    return flat(EXP[i:EXP.index("### 要加进 `profile/behavioral.md` 的", i)])


class TheRoutingTableReachesThatTable(unittest.TestCase):
    def test_projects_have_a_destination_now(self):
        """挖到一个具体项目却没有落点，它要么被丢掉、要么被塞进技能那一节。"""
        i = EXP.index("| Step 3 的组 | 落到哪一节 |")
        rows = EXP[i:EXP.index("\n\n", i)]
        self.assertIn("作品与项目的分层", rows)

    def test_the_destination_exists_in_the_template(self):
        """指一个模板里没有的落点，写进去就是新建一个小节、把资料切碎。"""
        self.assertIn("| 线 | 起始 | 项目 | 只能主张 | 可披露口径 |", TPL)

    def test_the_original_rows_survive(self):
        i = EXP.index("| Step 3 的组 | 落到哪一节 |")
        rows = EXP[i:EXP.index("\n\n", i)]
        for k in ("主力能力", "领域知识", "工作方法", "证照类"):
            with self.subTest(k=k):
                self.assertIn(k, rows)


class TheDisclosureColumnIsMandatory(unittest.TestCase):
    def test_the_section_exists(self):
        self.assertIn("#### 落进那张表的，必须带「可披露口径」", EXP)

    def test_it_says_why_this_step_is_special(self):
        """别的命令读的资料是照模板填的，那一列建档时就问过了。"""
        s = seg()
        self.assertRegex(s, r"那些都是\*\*对内写的\*\*")
        self.assertRegex(s, r"一条挖错的，最后是发出去的")

    def test_it_names_what_counts_as_identifying(self):
        """只说「注意保密」执行者判不了。要列出哪几类算能定位到主体。"""
        s = seg()
        for w in ("客户", "当事人", "患者", "学生", "代号"):
            with self.subTest(w=w):
                self.assertIn(w, s)

    def test_it_names_the_three_values(self):
        """**钉那句枚举本身，不是那三个词。**

        三个词在下面的问法里也各出现一次 —— 第一版逐词 assertIn，
        把枚举整句删掉照样绿（变异实测）。枚举是「这一列取什么值」的定义，
        问法是「怎么开口问」，两件事。
        """
        self.assertRegex(
            seg(), r"三选一：\*\*能点名 / 只能脱敏 / 完全不能提\*\*")

    def test_it_separates_the_two_questions(self):
        """**这是整条的支点。** 混在一起问，用户点头的是另一个问题。"""
        s = seg()
        self.assertRegex(s, r"那是两个问题")
        self.assertRegex(s, r"答案也常常相反")

    def test_it_gives_the_wording_to_ask(self):
        """不给问法，这一步会变成执行者自己发挥。"""
        self.assertRegex(seg(), r"这条能对外点名吗？还是只能脱敏说？")

    def test_unanswered_means_not_written(self):
        """按「能点名」写进去 = 替他做了一个他自己没做的判断。"""
        s = seg()
        # 钉内容不钉星号位置：加粗落在整句还是半句是排版决定。
        self.assertRegex(s, r"他答不上来或跳过 →\s*\*?\*?不写进资料")
        self.assertRegex(s, r"列进 Step 6 的报告里等他定")

    def test_it_states_the_real_cost(self):
        s = seg()
        self.assertRegex(s, r"执业违规")
        self.assertRegex(s, r"给前东家的保密主张留下书面证据")

    def test_it_does_not_reinvent_the_redaction_recipe(self):
        """脱敏怎么写 `03` 已经有一张对照表 —— 这里再写一遍就是第二份。"""
        s = seg()
        self.assertIn("03", s)
        self.assertRegex(s, r"不用这里发明")

    def test_the_measurement_is_recorded(self):
        s = seg()
        self.assertRegex(s, r"唯一一个\*\*从对内文件往对外资料\s*搬内容\*\*的命令")


class TheRulesItLeansOnAreStillThere(unittest.TestCase):
    """这一整条建立在两份正本上。任一处没了，它就成了自说自话。"""

    def test_the_writing_rule_still_exists(self):
        self.assertRegex(flat(STYLE), r"\*\*别人的秘密不是你的证据。\*\*")

    def test_the_redaction_table_still_exists(self):
        self.assertIn("| 不能写 | 脱敏后 |", STYLE)

    def test_it_still_degrades_to_asking(self):
        """那条降级路径是没标口径时唯一的防线 —— 这一轮加的是「别让它一直兜底」。"""
        self.assertRegex(flat(STYLE), r"资料里没标 →\s*起草前问用户一句")

    def test_the_template_column_still_has_its_three_values(self):
        i = TPL.index("可披露口径三选一")
        seg_ = flat(TPL[i:i + 400])
        for v in ("能点名", "只能脱敏", "完全不能提"):
            with self.subTest(v=v):
                self.assertIn(v, seg_)


class TheSignalItLeansOnIsReal(unittest.TestCase):
    """现算：这一步真的在读那几个目录，而那些目录真的可能装着这类文件。"""

    def test_expand_really_scans_the_documents_dir(self):
        s = flat(EXP)
        self.assertIn("documents/cv/", s)
        self.assertIn("documents/references/", s)

    def test_expand_really_writes_into_the_profile(self):
        self.assertIn("### 写进 `profile/candidate.md`", EXP)

    def test_the_profile_is_the_only_source_for_outbound(self):
        """「一条挖错的最后是发出去的」建立在这句上 —— 它变了就要重看。"""
        apply_md = (ROOT / "workflows" / "job-apply.md").read_text(encoding="utf-8")
        self.assertRegex(
            flat(apply_md) + flat(STYLE),
            r"唯一来源|唯一的事实来源|一切事实主张的唯一来源")

    def test_the_active_user_actually_has_documents(self):
        """他真放了东西进去，这条才不是纸上规则。"""
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        d = (ROOT / "users" / p.read_text(encoding="utf-8").strip() / "documents")
        if not d.is_dir():
            self.skipTest("这位用户还没有 documents/")
        files = [f for f in d.rglob("*") if f.is_file()
                 and "applications" not in f.parts]
        if not files:
            self.skipTest("documents/ 下还没有他自己放的文件")
        self.assertGreater(len(files), 0)


if __name__ == "__main__":
    unittest.main()
