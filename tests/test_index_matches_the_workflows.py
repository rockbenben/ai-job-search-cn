# -*- coding: utf-8 -*-
"""工作流索引说的，必须是工作流正文真做的。

索引第三列同时是**面板上那份帮助**。它和 `workflows/` 正文是两份文档，
中间没有任何东西把它们绑在一起——实测两个方向都漏过：

- **索引编了正文没有的敲法**：`/job-rank 只评这轮新增的`。照抄下去，
  「只评这轮新增的」会被当成**方向词**去匹配职位标题，一个都匹配不上；
  而裸 `/job-rank` 本来就只评没评过的。一条看着很懂的命令，跑起来是空的。
- **正文有的能力索引里查不到**：`/job-scrape health`（体检各渠道通不通）、
  `/job-user --remove`（索引的说明里明写着「删除用户」，却没有一个例子说怎么删）、
  `/job-auto --no-scrape`、`/job-rank --all` / `--skip` …… 一共漏了十来个。

这条守卫管**开关**（`--xxx`）：正文里定义过的，索引里要么出现，要么进豁免名单。
豁免要写理由——不是不许有内部开关，是不许**默认**沉默。
"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import export_web_data as ex  # noqa: E402

#: 调参用的内部开关，不进面板帮助——它们要么有更好的门面命令，要么普通用户
#: 调了也判断不出好坏。加进来必须写清为什么用户不需要看见。
INTERNAL = {
    "job-rank": {
        "--top": "名单长度，面板自己会排序，用户不需要调",
        "--fetch": "每轮抓详情条数，防的是平台限流，是实现细节",
        "--auto": "「评到排空」的门面是 /job-auto，不必让用户记两个入口",
        "--annual-floor": "薪资下限从 candidate.md 读，命令行覆盖是调试用",
        "--edu-floor": "同上，学历门槛也来自资料",
        # 2026-08-21 加：`--off-track` 的出处补上了（`search-queries.md`
        # 「需要主动规避的方向」），于是它进了 job-rank.md 的可运行块。
        # 和 job-auto 那两条同一个理由——**它们是 prescreen.py 的参数**，
        # 用户永远不会敲 `/job-rank --off-track`。
        "--off-track": "转传给 prescreen 的降权词，来自 search-queries.md"
                       "「需要主动规避的方向」；只影响先评谁的顺序，不改任何判词",
        # 2026-08-24 加：「回头补 JD」那一节列了 `fetch_details.py` 的三种模式。
        # **它们是那个工具的参数，不是 `/job-rank` 的开关** —— 用户永远不会敲
        # `/job-rank --recheck`。同 job-auto / job-scrape 那两组的形状。
        # （`--urls` 不在这里：它在正文里只出现在 ```bash 块的行首，
        # 按 `flags_in` 的口径不算「定义过」—— 给它豁免会被
        # test_exemptions_are_not_stale 逮到。）
        # 2026-08-26 加：落库那条规则原来只有 `--import-from <目录>` 一条路，
        # 于是 191 个岗读了没存。加了 `jd_store.py --save <链接>`（正文从标准
        # 输入进）之后，规则那一节才有一条能直接敲的命令。**同样是那个工具的
        # 参数** —— 用户永远不会敲 `/job-rank --save`。
        "--save": "jd_store 的入口：把刚读到的一份 JD 正文一步存进详情库",
        # `--import-from` **不在这里**：它在正文里只出现在 ```bash 块的行首，
        # 按 `flags_in` 的口径不算「定义过」。顺手给它一条豁免，当场被
        # test_exemptions_are_not_stale 逮到 —— 和上面 `--urls`、`--protect`
        # 是同一个坑，这已经是第三次。
        "--missing": "fetch_details 的模式：抓「待评且缺 JD」的猎聘岗",
        "--recheck": "fetch_details 的模式：连「判过但没读过 JD 正文」的一起抓",
        # `--protect` **不在这里**：job-rank.md 里它只出现在行内散文
        # （「传 --off-track 时必须一起传 --protect」），按 `flags_in` 的口径
        # 不算「定义过」。给它一条豁免会被 test_exemptions_are_not_stale 拦下 ——
        # 那条守的正是「为一个并不存在的开关放行」。第一版就这么写了，当场被逮到。
    },
    # `--browser-scrape` 2026-08-19 退役：抓哪几家改成只看面板勾选，它成了默认行为。
    # 正文里只剩「仍然收，但给不给都一样」这句兼容说明，不再是一个开关，所以不进豁免名单
    # ——留着它 test_exemptions_are_not_stale 会为一个已经不存在的开关放行。
    "job-auto": {"--top": "不是 auto 自己的开关——它转调 /job-apply 时按 --target 传，"
                          "用户要限量该写 /job-auto --target N",
                 # 下面四个是 `prescreen.py` 的命令行参数，2026-08-13 起在 job-auto.md
                 # 里列成一张「从哪读」的表——**它们不是 `/job-auto` 的开关**，
                 # 用户永远不会敲 `/job-auto --edu-floor`，是 auto 内部转传给
                 # prescreen 的。写进正文是因为「每次现编 off-track 词表」出过问题
                 # （同一个岗这轮排前面下轮排后面），出处必须有个明确说法。
                 "--annual-floor": "转传给 prescreen 的阈值，值从 candidate.md 读，"
                                   "不是用户在 auto 上敲的开关",
                 "--edu-floor": "同上，学历门槛也来自资料",
                 "--protect": "同上，目标职能词来自 search-queries.md",
                 "--off-track": "同上；而且它只影响先评谁的顺序，不改任何判词"},
    # 2026-08-24 加：job-scrape.md Step 1b 第 5 条列了一张「哪些原生筛选参数
    # 不要传」的表。**这五个 + --location 都是渠道 CLI 自己的参数**，不是
    # `/job-scrape` 的开关 —— 用户永远不会敲 `/job-scrape --edu`。写进正文是因为
    # 它们看起来是白捡的效率（少抓一批、省额度），而实测传了会静默丢掉能投的岗。
    # 同一个形状在 job-auto / job-rank 的 prescreen 参数上已经有先例（见上）。
    "job-scrape": {
        "--edu": "渠道 CLI 的筛选码，不是 /job-scrape 的开关；正文写它是为了说"
                 "**不要传**（按本科过滤会排掉 283 个岗，其中 24 个本来能投）",
        # `--years` **不在这里**：它在正文里只出现在行内那串枚举
        # （「`--edu` / `--years` / `--salary` / …」），按 `flags_in` 的口径不算
        # 「定义过」。给它一条豁免会被 test_exemptions_are_not_stale 逮到 ——
        # job-rank 的 `--protect` 那条注释记的是同一个坑。
        "--salary": "同上；会把 31 个写「面议」的一起排掉，其中 5 个能投",
        "--industry": "同上；会排掉 225 个行业字段为空的，其中 57 个能投",
        "--comp-scale": "同上；会排掉 319 个规模字段为空的，其中 68 个能投",
        "--location": "同上，但它是**例外中的例外**：猎聘 CLI 里必填，且过滤的是"
                      "客观事实（城市），不是「这个岗要不要得起你」那种判断",
        # 2026-08-25 加：Step 0.44 的渠道点名表有一列「`--check` 用的名字」——
        # 它是 portal_budget.py 的参数，不是 /job-scrape 的开关，用户永远不会敲
        # `/job-scrape --check`。同 job-rank 那组 fetch_details 豁免的形状。
        "--check": "portal_budget.py 的额度查询参数；表里列它是告诉执行者"
                   "每条渠道用什么名字问闸门",
    },
    # 2026-09-01 加：`flags_in` 现在也认「可选参数：」那一段里的开关，
    # 于是 `job-dashboard` 的两个露了出来。`--port` 进了索引；`--user` 不进 ——
    # **它在斜杠形式里是位置参数**：用户敲的是 `/job-dashboard <名字>`
    # （索引第三列已经列着），`--user` 是工作流转给 `serve.py` 的写法。
    # 把它也塞进索引，等于让用户在同一件事上记两种敲法。
    "job-dashboard": {"--user": "斜杠形式里它是位置参数（`/job-dashboard <名字>`，"
                                "索引已列）；`--user` 只是转给 serve.py 的写法"},
    "job-notion-sync": {"--min-score": "阈值调参，默认值来自评估框架"},
    "job-add-portal": {"--query": "接入新渠道时的探测参数，属开发流程"},
}


def flags_in(text: str) -> set:
    """正文里**定义过**的开关：出现在列表项开头或反引号紧跟的 `--xxx`。

    ## 「可选参数：」那一段里的，即使写在句子中间也算

    上面那两条只认**列表项开头** —— 口径是有理由的，行内散文里被**提到**
    的开关不等于被**提供**（`--protect`、`--urls`、`--years` 三次假阳性都是
    这么来的，INTERNAL 里的注释逐条记着）。

    但有一种写法例外：段落自己标着「**可选参数：**」。那是**提供**的明确信号，
    不是顺口一提。实测 2026-09-01：当时的总览工作流第 5 条写着
    「**可选参数：** …… `--port` 换端口（默认 29029）」，而它落在编号项
    `5.` 的句子中间 —— 两条正则一个都够不着，于是 `--port` 对索引**完全隐形**。
    索引第三列同时是面板上那份帮助，那里当时只有一个裸 `/job-dashboard`；
    `AGENTS.md` 更把它当成「没有参数可给的命令」的**举例**写进了规则里。

    只认「可选参数」四个字之后往下 400 字 —— 全仓只有 2 条命令有这种段，
    噪音为零（实测）。
    """
    found = set(re.findall(r"[-*|]\s*\*{0,2}`(--[a-z-]+)", text)) | set(
        re.findall(r"^\s*-\s+`?(--[a-z-]+)", text, re.M))
    for m in re.finditer(r"可选参数[：:]", text):
        found |= set(re.findall(r"`(--[a-z-]+)", text[m.end():m.end() + 400]))
    return found


class IndexCoversWhatTheWorkflowsSupport(unittest.TestCase):

    def setUp(self):
        self.cmds = {it["name"]: it
                     for g in ex.parse_commands() for it in g["items"]}
        self.assertGreaterEqual(len(self.cmds), 15, "索引像是没解析出来")

    def test_no_flag_is_silently_unreachable(self):
        missing = []
        for name, it in self.cmds.items():
            f = ROOT / "workflows" / f"{name}.md"
            if not f.is_file():
                continue
            shown = set(re.findall(r"--[a-z-]+", " ".join(it["examples"])))
            for flag in flags_in(f.read_text(encoding="utf-8")) - shown:
                if flag in INTERNAL.get(name, {}):
                    continue
                missing.append(f"{name} 的 {flag} —— 正文定义了，索引里查不到")
        self.assertEqual(missing, [],
                         "这些开关用户没有任何途径发现（要么进索引，要么进 INTERNAL 并写明理由）：\n  "
                         + "\n  ".join(missing))

    def test_exemptions_are_justified(self):
        """豁免必须写理由——空字符串等于偷偷关掉这条守卫。"""
        for cmd, flags in INTERNAL.items():
            for flag, why in flags.items():
                with self.subTest(flag=f"{cmd} {flag}"):
                    self.assertGreater(len(why), 8, f"{cmd} {flag} 的豁免理由太短")

    def test_exemptions_are_not_stale(self):
        """豁免名单里的开关得真存在，否则它在为一个已删掉的开关放行。"""
        for cmd, flags in INTERNAL.items():
            f = ROOT / "workflows" / f"{cmd}.md"
            self.assertTrue(f.is_file(), f"{cmd} 没有工作流文件")
            real = flags_in(f.read_text(encoding="utf-8"))
            for flag in flags:
                with self.subTest(flag=f"{cmd} {flag}"):
                    self.assertIn(flag, real, f"{cmd} 早就没有 {flag} 了，豁免该删")

    def test_a_missing_flag_would_actually_be_caught(self):
        """变异内建：伪造一个正文有、索引无的开关，必须被抓到。"""
        self.assertIn("--zzz", flags_in("- `--zzz` → 假开关"))
        self.assertNotIn("--zzz", set(re.findall(r"--[a-z-]+", "/job-rank --all")))


class TheWorkflowsSupportWhatTheIndexAdvertises(unittest.TestCase):
    """反方向：索引举的敲法，正文里必须真有。

    ## 为什么单开一条

    本文件开头点名了**两个**漂移方向，而上面那个类只挡住了一个
    （正文有 → 索引要有）。**另一个方向一直没人管**——而它恰恰是开头举的
    第一个例子：索引一度写着 `/job-rank 只评这轮新增的`，正文里查无此说法，
    照抄下去「只评这轮新增的」会被当成**方向词**去匹配职位标题，一个都匹配不上。

    这个方向更伤：索引第三列**同时是面板上那份帮助**。编一个假例子出去，
    用户照着敲，命令不报错、也不做那件事——**静默无事发生**，
    而这个仓库把「静默」列为比出错更坏的一类。

    2026-08-20 补。补的时候实测反方向是干净的（0 处），
    但**咬过一次的边界不能只修一半**。
    """

    #: 举例用的占位值，不是子命令——正文里当然查不到。
    #: 判据是「它是不是一个**要用户照敲的词**」：网址、路径、`<尖括号>` 都不是。
    PLACEHOLDER = ("://", "~/", "<")

    def setUp(self):
        self.cmds = {it["name"]: it
                     for g in ex.parse_commands() for it in g["items"]}
        self.assertGreaterEqual(len(self.cmds), 15, "索引像是没解析出来")

    def _pairs(self):
        """(命令名, 正文, 这条例子里要用户照敲的词)。"""
        for name, it in sorted(self.cmds.items()):
            f = ROOT / "workflows" / f"{name}.md"
            if not f.is_file():
                continue
            body = f.read_text(encoding="utf-8")
            for line in it["examples"]:
                yield name, body, line

    def test_every_advertised_flag_exists_in_the_workflow(self):
        bad = []
        for name, body, line in self._pairs():
            for flag in sorted(set(re.findall(r"--[a-z-]+", line))):
                if flag not in body:
                    bad.append(f"{name}: 索引举了 `{flag}`，正文里查无此开关（例：{line}）")
        self.assertEqual(
            bad, [],
            "索引（= 面板上那份帮助）在教用户敲正文不认的开关。"
            "用户敲下去不会报错，只会什么都不发生：\n  " + "\n  ".join(bad))

    def test_every_advertised_subcommand_exists_in_the_workflow(self):
        """裸子命令词同理：`health` / `broad` / `followup` / `比较` / `profile` …"""
        bad = []
        for name, body, line in self._pairs():
            head = re.split(r"[（(]", line)[0].strip()
            m = re.fullmatch(r"/" + re.escape(name) + r"\s+(\S+)", head)
            if not m:
                continue
            word = m.group(1)
            if word.startswith("-") or any(t in word for t in self.PLACEHOLDER):
                continue
            if word not in body:
                bad.append(f"{name}: 索引举了 `{word}`，正文里查无此说法（例：{line}）")
        self.assertEqual(
            bad, [],
            "索引在教用户敲正文不认的子命令：\n  " + "\n  ".join(bad))

    def test_the_reverse_check_can_actually_fail(self):
        """变异内建：伪造一条索引有、正文无的敲法，两条都要抓得到。"""
        body = "这份正文里只认 --all。"
        self.assertTrue(
            [f for f in re.findall(r"--[a-z-]+", "/job-x --nope") if f not in body],
            "开关方向抓不到")
        head = re.split(r"[（(]", "/job-x 假子命令（说明）")[0].strip()
        m = re.fullmatch(r"/job-x\s+(\S+)", head)
        self.assertIsNotNone(m, "子命令没解析出来")
        self.assertNotIn(m.group(1), body, "子命令方向抓不到")


class NaturalLanguageTriggersAreHumanSpeech(unittest.TestCase):
    """索引里的「直接说…」是给人念的，不能是技术词。

    实测漏出来的：「初始化」。求职者不会对着工具说「初始化」——
    本仓库自己的「内部词不要搬到台面上」那条管的正是这个，却漏扫了索引。
    """

    JARGON = ["初始化", "配置", "执行", "同步数据", "重置", "实例化"]

    def test_no_jargon_triggers(self):
        bad = []
        for g in ex.parse_commands():
            for it in g["items"]:
                for e in it["examples"]:
                    if e.startswith("/"):
                        continue
                    for w in self.JARGON:
                        if w in e:
                            bad.append(f"{it['name']}：「{e}」含技术词「{w}」")
        self.assertEqual(bad, [],
                         "「直接说…」要用求职者自己的话：\n  " + "\n  ".join(bad))

    def test_the_detector_can_fail(self):
        self.assertTrue(any(w in "初始化" for w in self.JARGON))
        self.assertFalse(any(w in "我要开始用" for w in self.JARGON))


class TheTitleAgreesWithTheIndexRow(unittest.TestCase):
    """第三个漂移方向：**工作流自己的第一行**。

    上面两个类管的都是索引与正文里的**敲法**（`--flag`、子命令）。而每条命令
    还有第三份自我介绍：工作流文件的 H1。它没人看着，于是 2026-08-27 全量审计
    一次扫出两处，**两处都不是措辞差异，是说的不是同一件事**：

    - `/job-auto` 标题写「评分 → 出材料」，索引与 README 都写「抓岗 → 评分 →
      出材料」。少掉的那一段在正文里是**一整节补货** + `--no-scrape` /
      `--no-browser` 两面旗子 —— 恰恰是用户最想先知道「它会不会动我账号」的
      那一段。当时的命令 stub 逐字抄了同一个标题，于是一起错（那层抄件已随
      `.claude/commands/` 一起删掉，见下面退休说明）。
    - `/job-upskill` 标题写「按你**投**的岗算」，而正文明写那一档
      **不设成默认**（新用户投递记录是空的，拿它当默认这条命令对新人直接失效）。
      裸命令用的是所有**评过分**的岗，差着一个数量级的语料。

    第二处 2026-08-21 就发现过，当时只改了索引表的第一、四列 —— 同一句话的
    第三份抄件漏了。**「找到一个先问它有几个兄弟」，H1 就是那个没人问起的兄弟。**

    ## 那第三份抄件现在在哪儿

    它当时是命令 stub 的第一行，逐字抄工作流的 H1。19 份 stub 已整体删除（入口改成
    `tools/gen_entries.py` 从索引派生的两族技能壳），**手抄的那一层没有了，这个漂移
    方向也就不存在对象** —— 原先钉它的那条测试自己带了「扫不到 15 份就报红」的探针，
    删完 stub 当天就如实报了红。它管的三件事分别落到：
    工作流 H1 ↔ 索引第一列（本文件
    `test_an_arrow_chain_in_the_title_matches_the_index`）、
    壳里每一个字 ↔ 索引（`tests/test_generated_entries_are_current.py`）、
    壳名 ↔ 工作流文件名（`tests/test_docs_accuracy.py` 的
    `test_shell_name_matches_its_workflow`）。三头都是派生或机械比对，不再有需要人
    记着的第二处。
    """

    def setUp(self):
        self.cmds = {it["name"]: it
                     for g in ex.parse_commands() for it in g["items"]}
        self.assertGreaterEqual(len(self.cmds), 15, "索引像是没解析出来")

    @staticmethod
    def _stages(text):
        """标题里那条箭头链（`抓岗 → 评分 → 出材料`）。没有就返回 None。"""
        m = re.search(r"([^\s，。：]+(?:\s*→\s*[^\s，。：]+)+)", text)
        return [s.strip() for s in re.split(r"→", m.group(1))] if m else None

    def test_an_arrow_chain_in_the_title_matches_the_index(self):
        """标题里写了几段，索引第一列就得是同样那几段。

        **少写一段不是简写，是漏掉一件它真会做的事。** 这条是机械判据：
        两边都出现箭头链时逐段比，任何一边没有链就不管。
        """
        bad = []
        for name, it in sorted(self.cmds.items()):
            f = ROOT / "workflows" / f"{name}.md"
            if not f.is_file():
                continue
            title = self._stages(f.read_text(encoding="utf-8").splitlines()[0])
            idx = self._stages(it["does"])
            if title and idx and title != idx:
                bad.append(f"{name}：标题 {'→'.join(title)} / 索引 {'→'.join(idx)}")
        self.assertEqual(bad, [],
                         "工作流标题与索引第一列说的段数对不上：\n  " + "\n  ".join(bad))

    def test_the_arrow_check_can_actually_fail(self):
        self.assertEqual(self._stages("一条命令跑完：抓岗 → 评分 → 出材料，中途…"),
                         ["抓岗", "评分", "出材料"])
        self.assertIsNone(self._stages("审一遍你的主简历，只报问题"))
        self.assertNotEqual(self._stages("评分 → 出材料"),
                            self._stages("抓岗 → 评分 → 出材料"))

    def test_upskill_title_names_the_default_corpus(self):
        """标题不许把 `--applied` 那一档说成默认。

        判据取索引第四列（「不给参数时」）—— 它是这条命令默认干什么的正本。
        它说默认是「所有评过分的」，标题就不能说「按你投的岗」。
        """
        bare = self.cmds["job-upskill"]["bare"]
        self.assertIn("评过分", bare, "索引第四列改了，这条测试要跟着改")
        self.assertIn("--applied", bare, "投过的那批本该是 flag 才到达的一档")
        h1 = (ROOT / "workflows" / "job-upskill.md").read_text(
            encoding="utf-8").splitlines()[0]
        self.assertNotIn("按你投的岗", h1,
                         "标题把 --applied 那一档说成了默认——差着一个数量级的语料")
        self.assertIn("评过", h1, "标题没说清默认拿哪批岗算")


if __name__ == "__main__":
    unittest.main()
