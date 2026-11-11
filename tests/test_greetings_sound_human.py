# -*- coding: utf-8 -*-
"""开场白是发给活人的聊天消息，不许带框架腔。

## 为什么这条守卫此前不存在

`AGENTS.md`「给用户看的措辞」管的是**界面与终端**，`test_display_wording` /
`test_web_copy` / `test_workflow_output_templates` 三处都在扫那一侧。
**话术从来没人扫**——而它是这个仓库唯一**由用户原样转发给第三方**的产出：
内部词漏到界面上用户会皱眉，漏到开场白里是直接发给 HR 的。
这一层比界面更靠外，规则却比界面更松，是个反过来的口子。

## 实测漏出来的六种腔调

用户原话：「打招呼习惯应该用中文习惯，而且不该出现『这个差别先摆出来』这种，
明显不是正常招呼会用的」。查下来不止那一句，整段是「阅读理解腔」：

    这个差别先摆出来                  ← 框架指令词（「主动摆出来」是给 AI 的话）
    JD 里「多个智能体平台的深度使用与能力对比分析」…  ← 大段引用 JD 原文加引号
    三选一我占两项                    ← 对表打勾
    想先问两条 / 想先说清一条          ← 公文编号
    个人向工具 / 组织级推广 / 这一层    ← 内部生造词
    ……正是我这一年在做的事——发布了 40 个… ← 破折号串长从句

规则写在 `06-outreach-templates.md`「铁律 0」。

## 判据

只扫**开场白正文**（`## 打招呼开场白` 那一节），不扫自检节与头部——
那些是给写文件的人看的，出现框架词没问题。
"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

SPEC = ROOT / "workflows" / "reference" / "06-outreach-templates.md"

#: 框架指令词与内部生造词。这些出现在**发出去的正文**里就是 bug。
BANNED_TONE = [
    "先摆出来", "主动暴露", "占两项", "个人向", "组织级",
    "主战场", "这一层", "那一层", "能力边界", "硬门", "四维", "判词",
    # 内部味比喻与生造搭配（2026-08-17 普查补）：「手感」是圈内黑话，「重度实践者」
    # 没这个中文词（重度使用者/重度用户才有），「一手实践」不搭（一手经验才搭），
    # 「切进」是「切入」的走样。
    "手感", "重度实践者", "一手实践", "切进",
    # 「[一长串名词] + 判断词」这个句式。用户 2026-08-13：「很多都不是中文习惯」。
    # 中文里人说**自己干过什么**（动词），不给自己贴判断：
    #     Agent 产品定义与场景需求挖掘对得上   →  Agent 产品怎么定义、场景怎么挖，我都做过
    #     大模型的交付方案设计与落地是我的实践区 →  大模型的方案怎么设计、怎么落地，我做过
    # 实测 65 份开场白是同一个模子——它们全是从评估文档的措辞直译过来的，
    # 而评估文档本来就是写给 AI 看的名词化文体。
    "对得上", "实践区", "是我的主场", "是我的强区", "强命中", "逐条",
]
#: 公文编号：「想先问两条」这种。中文口语说「想问下」「有个问题」。
NUMBERED = re.compile(r"(?:先)?[问说][清楚]?\s*[一二三四五六七八九十两]\s*条")
#: 大段引用 JD 原文：一句话里塞两个及以上「」引用，就是在做阅读理解不是打招呼。
QUOTE_HEAVY = re.compile(r"[「『][^」』\n]{8,}[」』][^。！？\n]{0,12}[「『][^」』\n]{8,}[」』]")
#: 拿产量当卖点：「一年 40 个开源项目」。产量是产出速度，招聘方看不出好坏；
#: 同样的字数换成「开源项目累计 <N> 万+ stars、<N> 万+ 注册用户」才是市场验证过的结论。
#: 用户 2026-08-12 的意思：一年 N 个开源项目不够吸引人，star 数与注册用户数更有说服力。
VOLUME_BRAG = re.compile(r"\d{2,}\s*(?:个|款)\s*(?:开源)?(?:项目|产品|仓库|作品)")

#: 把 JD 复述给招聘方听。那段话是**他自己写的**，复述一遍既没有新信息，
#: 又暴露了这是照着文档拼的——读起来像机器在做比对。实测 97 份都这么开头。
#: 用户 2026-08-13：「这种表述多余，要符合中文的面试习惯」。
#: 只拦「复述」，不拦「问」——「想要一份完整 JD」「JD 写英语可作为工作语言，
#: 是指读写还是开会？」都是在向对方要东西，正当。
QUOTES_THE_JD = re.compile(
    r"JD\s*(?:里|中|上)?\s*(?:第\s*\d+\s*条)?\s*(?:说|写着|写道|写|明写|点名|提到|要求)")

#: 身份标签。用户 2026-08-13：「不要强调独立开发者身份，只表述自己做的产品，
#: 比如工作流/工具提效」。在国内招聘语境里「独立开发者」不是中性词——它暗示
#: 「没在组织里交付过、没带过团队」，等于开场第一句就摆出减分项，
#: 还盖住了真正的强项（有人用的产品、可核的数字）。实测 123 份开场白都这么开头。
IDENTITY_LABEL = "独立开发者"

#: 给短处加的引子。用户 2026-08-17 原话：「『先说清楚：』这种废话不该在开场白」。
#: 引子本身零信息——去掉它，那句话的意思一个字没变；代价却是把 200 字里最贵的
#: 那几个字花在「我接下来要讲个短处」这条元信息上。而它后面跟着的短处，按
#: 「通用要求」第 2 条多半根本不该进开场白（非一眼可见的缺口归 evaluation.md）。
#: 实测：153 份未投出的开场白里 44 份带引子、101 份主动报了非一眼可见的短处——
#: 规则 2026-08-12 就写了，没有守卫，五天后仍是 2/3 违规。
#: 第一版漏了三个变体（「得先说：」「要先说的是：」「想先跟您说清楚：」），
#: 实测各活着一份——引子的形态会变，判据不变：那半句删掉，意思一个字不少。
DISCLOSURE_LEAD = re.compile(
    r"(?:先说清楚|要说清楚的是|要说清楚|有一条要先说|有一点要先说|"
    r"两点先说清|两条先说清|先说明两点|先说清|坦白说|老实说|实话说|"
    r"得先说|要先说|[跟向]您说清楚)\s*[：:，]?")

#: 开场铺垫（用户 2026-08-17：「『这个岗我想聊一下』这种都是废话，没必要吧」）。
#: 四种形态说的都是对方已经知道的事：他自己写的岗位名、他自己发的招聘、
#: 以及「我想跟你聊」这个从你发消息本身就能推出来的事实。
#: 渠道 1 本来就写着「最硬的匹配点必须落在第一句，不许铺垫」——这些正是铺垫。
#: 实测 152 份里 142 份带，一句平均吃掉 15 字（200 字预算的 7.5%），信息量为零。
#: 「您好，」不在此列：中文里不打招呼直接说事是失礼。
OPENER_FLUFF = re.compile(
    r"^[您你]好[，,]\s*"
    r"(?:这个岗(?:位)?我(?:很)?想聊(?:一下)?"
    r"|看到[^。！？\n]{0,50}?(?:岗位?|职位)"
    r"|看到贵司(?:在)?招[^。！？\n]{0,50}"
    r"|我想应聘[^。！？\n]{0,50})"
    r"[。！]")

#: 求职状态（用户 2026-08-17：「『我目前离职随时到岗。』这不是很重要，没必要现在提」）。
#: 它和铺垫是同一类：占着 200 字里最贵的位置，说的却不是「这人能不能干」。
#: 到岗时间是对方决定往下谈之后才关心的事——他问了再答，比抢答有用。
#: ⚠ 这条**推翻**了同日早些时候写的「求职状态不算钱，照旧要说」——那是我加的
#: 折中，用户后来直接否掉了。规则以用户裁定为准，不以框架自洽为准。
AVAILABILITY = re.compile(
    r"(?:我)?(?:目前|现在)?(?:已)?离职[，,、]?\s*(?:随时|马上)?(?:能|可以)?到岗"
    r"|随时(?:能|可以)?(?:到岗|入职|到)"
    r"|(?:目前|现在)在职[，,]?\s*(?:需|要)?\d*\s*(?:周|天|个月)?(?:离职|交接)"
    r"|到岗时间")

#: 打招呼里一个字不提薪资（用户 2026-08-17：「这只是打招呼，不该谈薪资」）。
#: 打招呼是筛选场景，第一条消息只回答「这人能不能干」；先谈钱等于让对方在读完
#: 你能干什么之前就按价格分类。实测 33 份、36 句，四种形态：
#:   报自己期望 12 · 问对方几薪 10 · 点挂牌差距 13 · 拐着弯问定级 1
#: 这条推翻了框架自己定的两条旧规则（猎头主动报期望、面议必须问薪资），
#: 规则改在 06「渠道 1 · 铁律：打招呼里一个字都不提薪资」。
#: 只管渠道 1；邮件/网申/求职信照旧可以谈条件，那几节不在这个扫描范围里。
#: 「求职状态」不算钱——「我目前离职随时到岗」照旧放行。
SALARY_TALK = re.compile(
    r"\d+\s*[-–]\s*\d+\s*[kK]"              # 20-40k
    r"|\d+\s*[-–]\s*\d+\s*万"                # 30-45 万
    r"|几薪|按\s*\d+\s*薪|\d+\s*薪"           # 几薪 / 16 薪
    r"|薪资|年包|薪酬|待遇|薪水|package"       # 直呼其名
    r"|期望\s*\d|我的期望|期望在"              # 报期望
    r"|定级|职级")                            # 拐着弯问钱

#: 公式记法：「期望 45-60k×16 薪」。乘号是自己算年包用的数学记号，聊天里中国人说
#: 「45-60k、16 薪」。资料文件里写 × 没问题（`candidate.md` 就这么记），
#: 坏在把算账的写法原样粘进聊天框。整句现在已被 SALARY_TALK 全禁，
#: 这条保留作**第二道**——万一将来放开了某种薪资表述，记法这一条仍然成立。
FORMULA_SALARY = re.compile(r"[×x]\s*\d{1,2}\s*薪")

#: 自陈短处。只用来判**位置**（不判该不该写——那要读 JD 才知道是不是一眼可见）。
SELF_NEGATIVE = re.compile(
    r"(?:我)?(?:完全|确实|真的)?(?:没做过|没接触过|没搭过|没设计过|没经手过|没经手|"
    r"没带过|没扛过|没碰过|没系统做过|没完整背过|没正式做过|没在.{0,12}用过|"
    r"不是我的强项|不是强项|不擅长|谈不上熟|要从头学|都是空白|是空白|"
    r"没有科班|不是工程师出身|口语不行)")

#: 英式倒装的补充说明：「……我没做过，先说明。」是 just to be upfront 的直译。
#: 中文把事实说完就够了，尾巴上再补一句元评论既啰嗦又不像人话（用户原话：
#: 「这种倒装都是英语习惯，根本不符合中文」）。
#: 2026-08-12 实测 42 份开场白全带这个尾巴——同一个模子出来的，一犯就是一片。
INVERTED_TAG = re.compile(r"，\s*(?:先说明|这点先说明|先说透|这点先说透|先说清楚)\s*[。；，]")


#: 含着框架词、但**本身是地道中文**的说法，扫之前先剥掉。
#: 「硬门槛」——「这是硬门槛还是可以商量」是正常人说的话；
#: `export_web_data.INTERNAL_TERMS` 与 `test_workflow_output_templates.EXEMPT`
#: 早就给它开过同样的口子，这里不能比它们更严。
#: 「对不对得上」——「benchmark 跟真实样本对不对得上」是在说两份数据合不合，
#: 不是框架里那句「你的能力和这个岗对得上」。疑问/否定式根本没法当判词用，
#: 而它是描述比对结果时最自然的中文。2026-08-17 真实产出里撞出来的误杀。
EXEMPT = ("硬门槛", "对不对得上")


def _sent_urls() -> set:
    """已经投出去的岗。它们的开场白是**发出去内容的存档**，不扫也不许改。

    改一份已发出的话术等于篡改记录：两周后回看「我当时到底跟对方说了什么」，
    看到的会是一份从没发过的版本。规则变严只对**还没发出去的**生效。
    """
    f = ROOT / "web" / "public" / "data.json"
    if not f.is_file():
        ptr = ROOT / ".active_user"
        if ptr.is_file():
            user = ptr.read_text(encoding="utf-8").strip()
            dash_f = ROOT / "users" / user / "job_scraper" / "dashboard" / "data.json"
            if dash_f.is_file():
                f = dash_f
    if not f.is_file():
        return set()
    import json
    d = json.loads(f.read_text(encoding="utf-8"))
    return {j["url"] for j in d.get("jobs", []) if j.get("applied")}


def greetings():
    """(目录名, 开场白正文) —— 只取**还没投出去**的那些。

    用户目录从 `.active_user` 读，**不写死名字**：写死等于把维护者的真名钉进
    版本库（`test_no_maintainer_data_in_repo` 会抓，第一版就被它当场抓住），
    而且换个用户这条守卫就自动失效了。
    """
    ptr = ROOT / ".active_user"
    if not ptr.is_file():
        return []
    user = ptr.read_text(encoding="utf-8").strip()
    if not user:
        return []
    apps = ROOT / "users" / user / "documents" / "applications"
    if not apps.is_dir():
        return []
    sent = _sent_urls()
    out = []
    for d in sorted(x for x in apps.iterdir() if x.is_dir()):
        f = d / "outreach.md"
        if not f.is_file():
            continue
        raw = f.read_text(encoding="utf-8")
        u = re.search(r"职位链接\s*[：:]\s*(\S+)", raw)
        if u and u.group(1) in sent:
            continue
        # 标题有两种写法：新的「## 打招呼开场白（…）」和老的「## 渠道 1：打招呼开场白（…）」。
        # 原来只认前者，于是 2026-07 那批老文件**整份逃过全部检查**——
        # 一份带着「先说清楚」「这个岗我想聊一下」的开场白，谁也没扫到。
        # 判据放宽成「标题里带『打招呼开场白』」，下面的 test_every_greeting_is_scanned 兜底。
        m = re.search(r"##[^\n]*打招呼开场白[^\n]*\n+(.*?)(?=\n## |\Z)", raw, re.S)
        if m and m.group(1).strip():
            body = re.sub(r"^\s*>[^\n]*$", "", m.group(1), flags=re.M)  # 老文件的字数校验注脚
            out.append((d.name, body.strip()))
    return out


def sales_copy():
    """(目录名 / 小节名, 正文) —— **所有要发出去的文案**，不只是开场白。

    2026-08-19 补：`讲成绩用哪个数` 这条规则原来只被开场白扫到，而它在 06 里
    不带渠道限定（讲的是「自证用哪个数」）。当天新出的三份材料里开场白干干净净，
    **邮件与网申自评却各带一处产量自证**（「过去一年新建并发布 40 个开源仓库」）——
    规则对、扫描面不对，等于没有规则。

    `evaluation.md` 不在扫描面内：那是写给用户自己看的评估，
    陈述「一年 40 个仓库」是事实，不是拿去说服招聘方的自证。
    """
    ptr = ROOT / ".active_user"
    if not ptr.is_file():
        return []
    user = ptr.read_text(encoding="utf-8").strip()
    apps = ROOT / "users" / user / "documents" / "applications"
    if not user or not apps.is_dir():
        return []
    sent = _sent_urls()
    out = []
    for f in sorted(apps.glob("*/outreach.md")):
        raw = f.read_text(encoding="utf-8")
        u = re.search(r"职位链接\s*[：:]\s*(\S+)", raw)
        if u and u.group(1) in sent:
            continue
        for title in ("打招呼开场白", "邮件", "网申自评", "求职信"):
            m = re.search(r"##[^\n]*" + title + r"[^\n]*\n+(.*?)(?=\n## |\Z)", raw, re.S)
            if not m:
                continue
            body = re.sub(r"^\s*>[^\n]*$", "", m.group(1), flags=re.M)
            body = re.sub(r"^\s*不触发[^\n]*$", "", body, flags=re.M)
            if body.strip():
                out.append((f"{f.parent.name} / {title}", body.strip()))
    return out


def _unsent_files_with_a_greeting():
    """盘上有几份**未投出**的 outreach.md 真的带开场白——用来验 greetings() 没漏扫。"""
    ptr = ROOT / ".active_user"
    if not ptr.is_file():
        return []
    user = ptr.read_text(encoding="utf-8").strip()
    apps = ROOT / "users" / user / "documents" / "applications"
    if not user or not apps.is_dir():
        return []
    sent = _sent_urls()
    out = []
    for f in sorted(apps.glob("*/outreach.md")):
        raw = f.read_text(encoding="utf-8")
        u = re.search(r"职位链接\s*[：:]\s*(\S+)", raw)
        if u and u.group(1) in sent:
            continue
        if re.search(r"^##[^\n]*打招呼开场白", raw, re.M):
            out.append(f.parent.name)
    return out


def _own_words(t: str) -> str:
    """剥掉引号里的内容与豁免说法，只留**他自己说的话**。

    引用 JD 原文里的词不算内部词泄漏——智联那条 JD 自己就写着
    「熟悉 ChatGPT、Claude、DeepSeek 的能力边界」，照抄它不是把框架词
    搬给 HR。（引用得太多是另一个问题，由 QUOTE_HEAVY 单独管。）
    """
    s = re.sub(r"[「『][^」』\n]*[」』]", " ", t)
    for w in EXEMPT:
        s = s.replace(w, " ")
    return s


class TheSpecSaysSo(unittest.TestCase):
    """规则得先真写在框架里，否则这些断言拦的是不存在的规矩。"""

    def test_iron_rule_zero_exists(self):
        t = SPEC.read_text(encoding="utf-8")
        self.assertIn("铁律 0", t, "06 里没有「这是发给活人的话」那条铁律")
        self.assertIn("聊天框", t)
        for w in ("先摆出来", "占两项", "个人向"):
            with self.subTest(word=w):
                self.assertIn(w, t, f"铁律 0 的反例表里没有点名「{w}」")


class GreetingsAreChatNotReport(unittest.TestCase):

    def test_every_greeting_is_scanned(self):
        """盘上每一份未投出的开场白都要被扫到——漏一份，那一份就没有任何守卫。

        2026-08-17 实测：老格式的标题写作「## 渠道 1：打招呼开场白（…）」，
        而 `greetings()` 只认「## 打招呼开场白」，于是那份文件**整份**逃过了
        全部 16 条检查。这类洞不会自己暴露——它表现为「全绿」。
        """
        scanned = {n for n, _ in greetings()}
        on_disk = set(_unsent_files_with_a_greeting())
        if not on_disk:
            self.skipTest("这个 clone 里没有真实投递目录")
        missed = sorted(on_disk - scanned)
        self.assertEqual(missed, [],
                         "这些开场白在盘上，却没被任何一条守卫扫到"
                         "（多半是标题写法没被 greetings() 认出来）：\n  "
                         + "\n  ".join(missed))

    def test_there_are_greetings_to_check(self):
        """控制用例：真扫到了开场白，否则下面几条在空集上恒绿。"""
        g = greetings()
        if not g:
            self.skipTest("这个 clone 里没有真实投递目录")
        self.assertGreaterEqual(len(g), 3, f"只扫到 {len(g)} 条开场白，像是扫空了")

    def test_no_framework_words(self):
        bad = [f"{n}：「{w}」" for n, t in greetings()
               for w in BANNED_TONE if w in _own_words(t)]
        self.assertEqual(bad, [],
                         "开场白里出现框架词/内部生造词——这段是直接粘给 HR 的：\n  "
                         + "\n  ".join(bad))

    def test_no_bureaucratic_numbering(self):
        bad = [f"{n}：「{m.group(0)}」" for n, t in greetings()
               if (m := NUMBERED.search(t))]
        self.assertEqual(bad, [],
                         "「想先问两条」这类编号是公文腔，聊天里说「想问下」：\n  "
                         + "\n  ".join(bad))

    def test_not_a_reading_comprehension_exercise(self):
        """一句话里连着引两段 JD 原文 = 在做阅读理解，不是打招呼。"""
        bad = [f"{n}：{m.group(0)[:40]}…" for n, t in greetings()
               if (m := QUOTE_HEAVY.search(t))]
        self.assertEqual(bad, [],
                         "连续引用两段 JD 原文，读起来像念稿：\n  " + "\n  ".join(bad))

    def test_does_not_recite_the_jd(self):
        """别把招聘方自己写的 JD 复述给他听。"""
        bad = [f"{n}：「{m.group(0)}…」" for n, t in greetings()
               if (m := QUOTES_THE_JD.search(t))]
        self.assertEqual(bad, [],
                         "开场白在复述 JD——删掉「JD 里/说/写」直接说那件事"
                         "（见 06「不要把 JD 复述给招聘方听」）：\n  " + "\n  ".join(bad))

    def test_no_identity_label(self):
        """开场白不自报「独立开发者」，只说做出来的东西。"""
        bad = [n for n, t in greetings() if IDENTITY_LABEL in _own_words(t)]
        self.assertEqual(bad, [],
                         "开场白把身份标签当自我介绍了——改成说产品/工作流"
                         "（见 06「别自报『独立开发者』」）：\n  " + "\n  ".join(bad))

    def test_no_volume_bragging(self):
        """「一年 40 个开源项目」是产量，不是成绩。用 star 数和用户数。

        **扫全部要发出去的文案**（开场白 / 邮件 / 网申自评 / 求职信），不只是开场白：
        06 那条规则不带渠道限定，而 2026-08-19 漏掉的 6 处全在邮件和网申自评里。
        """
        bad = [f"{n}：「{m.group(0).strip()}」" for n, t in sales_copy()
               if (m := VOLUME_BRAG.search(_own_words(t)))]
        self.assertEqual(bad, [],
                         "拿产量自证——换成「累计 <N> 万+ stars / <N> 万+ 注册用户」"
                         "（见 06「讲成绩用哪个数」）：\n  " + "\n  ".join(bad))

    def test_no_inverted_disclosure_tag(self):
        """「……我没做过，先说明。」——英文倒装直译，中文把事实说完就行。"""
        bad = [f"{n}：「…{m.group(0)}」" for n, t in greetings()
               if (m := INVERTED_TAG.search(t))]
        self.assertEqual(bad, [],
                         "句尾的「，先说明」是英式补充说明，中文说完事实就够：\n  "
                         + "\n  ".join(bad))

    def test_no_disclosure_lead_in(self):
        """「先说清楚：」这类引子零信息，删掉句子意思一点不变。"""
        bad = [f"{n}：「{m.group(0).strip()}」" for n, t in greetings()
               if (m := DISCLOSURE_LEAD.search(t))]
        self.assertEqual(bad, [],
                         "开场白给短处加了引子——引子删掉，后面那句多半也不该留"
                         "（见 06 铁律 0「给自己加铺垫」与通用要求 2）：\n  "
                         + "\n  ".join(bad))

    def test_no_opener_fluff(self):
        """「您好，看到这个 X 的岗。」——岗位名是他自己写的，复述一遍等于没说。"""
        bad = [f"{n}：「{m.group(0)}」" for n, t in greetings()
               if (m := OPENER_FLUFF.match(t.strip()))]
        self.assertEqual(bad, [],
                         "开场白在铺垫——「您好，」之后直接进最硬的匹配点"
                         "（见 06 渠道 1「不许有开场铺垫」）：\n  " + "\n  ".join(bad))

    def test_no_availability_boilerplate(self):
        """「我目前离职随时到岗」——打招呼阶段不重要，对方问了再说。"""
        bad = [f"{n}：「{m.group(0)}」" for n, t in greetings()
               if (m := AVAILABILITY.search(t))]
        self.assertEqual(bad, [],
                         "开场白报了求职状态——那是对方问起才说的事，别占前两行"
                         "（见 06 渠道 1「不许有开场铺垫」）：\n  " + "\n  ".join(bad))

    def test_greeting_never_talks_money(self):
        """打招呼里一个字都不提薪资——报期望、问几薪、点挂牌差距、问定级，全禁。"""
        bad = [f"{n}：「{m.group(0)}」" for n, t in greetings()
               if (m := SALARY_TALK.search(_own_words(t)))]
        self.assertEqual(bad, [],
                         "开场白在谈钱——打招呼只回答「这人能不能干」，薪资留到对方回话之后"
                         "（见 06 渠道 1「打招呼里一个字都不提薪资」）：\n  "
                         + "\n  ".join(bad))

    def test_no_formula_salary_notation(self):
        """「45-60k×16 薪」是算账记号，聊天里说「45-60k、16 薪」。"""
        bad = [f"{n}：「{m.group(0)}」" for n, t in greetings()
               if (m := FORMULA_SALARY.search(t))]
        self.assertEqual(bad, [],
                         "开场白把算年包的乘号原样粘进了聊天框——改成顿号"
                         "（见 06 铁律 0「公式记法」）：\n  " + "\n  ".join(bad))

    def test_gap_is_not_the_opening(self):
        """短处不许排在匹配点前面——渠道 1 的硬约束是最硬的匹配点落在第一句。

        判据：剥掉开头那句纯招呼（「您好，看到这个 X 岗」）之后，
        **第一句正文**里不许出现自陈短处。对方在读到你能干什么之前
        先读到一条过滤理由，是把 200 字最贵的位置让给了减分项。
        """
        bad = []
        for n, t in greetings():
            sents = [s.strip() for s in re.split(r"[。！？\n]", t) if s.strip()]
            if sents and len(sents[0]) < 30 and re.match(r"^(您好|你好)", sents[0]) \
                    and not SELF_NEGATIVE.search(sents[0]):
                sents = sents[1:]           # 纯招呼那句不算正文
            if sents and (m := SELF_NEGATIVE.search(sents[0])):
                bad.append(f"{n}：正文第一句就是「…{m.group(0)}」")
        self.assertEqual(bad, [],
                         "开场白拿短处开头——差距该写就写，位置在匹配点与佐证之后"
                         "（见 06 通用要求 2 的执行细则）：\n  " + "\n  ".join(bad))

    def test_no_markdown_or_markers(self):
        """聊天框不渲染 markdown，`**` 与 `>` 会原样粘过去。"""
        bad = []
        for n, t in greetings():
            if re.search(r"\*\*[^*\n]+\*\*", t):
                bad.append(f"{n}：有 markdown 粗体")
            if any(ln.lstrip().startswith(">") for ln in t.splitlines()):
                bad.append(f"{n}：有引用标记 >")
        self.assertEqual(bad, [], "\n  ".join(bad))

    def test_within_length(self):
        bad = [f"{n}：{len(re.sub(r'\\s', '', t))} 字"
               for n, t in greetings() if len(re.sub(r"\s", "", t)) > 200]
        self.assertEqual(bad, [], "开场白超 200 字（聊天框里没人读长段）：\n  "
                         + "\n  ".join(bad))

    def test_the_detector_can_actually_fail(self):
        """变异内建：几个合成串必须被抓到，否则上面几条是摆设。"""
        self.assertTrue(any(w in "这个差别先摆出来" for w in BANNED_TONE))
        self.assertTrue(NUMBERED.search("想先问两条：地点在哪"))
        self.assertTrue(QUOTE_HEAVY.search(
            "JD 里「多个智能体平台的深度使用与能力对比分析」「有具体的项目产出证明」正是我"))
        # 反向：正常口语不许被误伤
        ok = "您好，我想应聘 AI 产品经理。想问下：这个岗主要负责哪块？"
        self.assertFalse(NUMBERED.search(ok))
        self.assertFalse(QUOTE_HEAVY.search(ok))
        self.assertTrue(INVERTED_TAG.search("医疗和患者管理这个场景我没做过，先说明。"))
        self.assertTrue(DISCLOSURE_LEAD.search("先说清楚：Docker 部署不是我的强项"))
        self.assertTrue(DISCLOSURE_LEAD.search("要说清楚的是：变现体系我没设计过"))
        self.assertTrue(DISCLOSURE_LEAD.search("坦白说 IP 情报我要从头学"))
        # 第一版漏掉的三个变体
        self.assertTrue(DISCLOSURE_LEAD.search("但有个实际问题得先说：挂的是 20-40k"))
        self.assertTrue(DISCLOSURE_LEAD.search("要先说的是：岗位写 1-3 年经验"))
        self.assertTrue(DISCLOSURE_LEAD.search("有两件事想先跟您说清楚：财务我是零基础"))
        for s in ("我目前离职随时到岗，期望 45-60k、16 薪。",
                  "另外 40-70k 是几薪？",
                  "方便同步下薪资带宽吗？",
                  "岗位挂 20-30k，和我的期望差距比较大。",
                  "想问下这个岗的定级还有多少空间？",
                  "岗位挂的是 <某区间>，我的期望在这个区间上沿以上。"):
            with self.subTest(s=s):
                self.assertTrue(SALARY_TALK.search(s), f"没抓住谈钱：{s}")
        for s in ("我目前离职，随时到岗。",            # 求职状态不是钱
                  "想问下这个岗第一年要拿出什么结果？",
                  "开源作品累计 3 万+ stars、7 万+ 注册用户。",   # 数字不是薪资（编的）
                  "某产品覆盖 18 国语言。",
                  "用 Claude Code 开发了 3-5 组 Agent Skills。"):
            with self.subTest(s=s):
                self.assertFalse(SALARY_TALK.search(s), f"误杀了正常句子：{s}")
        for s in ("您好，看到这个 AI 分析师的岗。Cursor 是我的日常",
                  "您好，这个岗我想聊一下。Agent 编排我天天在做",
                  "您好，看到贵司在招 AI 产品经理。我做过完整产品",
                  "您好，我想应聘 AI Manager 这个岗位。"):
            with self.subTest(s=s):
                self.assertTrue(OPENER_FLUFF.match(s), f"没抓住铺垫：{s}")
        for s in ("您好，Cursor、Claude Code 这类工具是我的日常。",
                  "您好，这个岗要设计 Harness 能力框架，任务拆解、工具选择这一串——",
                  "您好。"):
            with self.subTest(s=s):
                self.assertFalse(OPENER_FLUFF.match(s), f"误杀了正常开头：{s}")
        for s in ("我目前离职随时到岗。", "我目前离职，随时可以到岗。",
                  "我离职、随时到岗。", "随时能到。"):
            with self.subTest(s=s):
                self.assertTrue(AVAILABILITY.search(s), f"没抓住求职状态：{s}")
        for s in ("这套流程我随时能讲清楚。", "想问下这个岗第一年要拿出什么结果？"):
            with self.subTest(s=s):
                self.assertFalse(AVAILABILITY.search(s), f"误杀了正常句子：{s}")
        self.assertTrue(FORMULA_SALARY.search("期望 45-60k×16 薪"))
        self.assertFalse(FORMULA_SALARY.search("期望 45-60k、16 薪"),
                         "顿号的正确写法被当成公式误杀了")
        self.assertFalse(FORMULA_SALARY.search("挂 20-30k·20薪，年包 40 万"),
                         "引用挂牌薪资的「·」写法被误杀了")
        self.assertFalse(DISCLOSURE_LEAD.search("想问下这个岗前半年要拿出什么结果"),
                         "正常提问被当成引子误杀了")
        self.assertTrue(SELF_NEGATIVE.search("保险这块我完全没做过"))
        self.assertFalse(SELF_NEGATIVE.search("这套我做过不少，都是自用起家再产品化的"),
                         "正面陈述被当成短处误杀了")
        self.assertTrue(VOLUME_BRAG.search("独立开发者，一年 40 个开源项目"))
        self.assertTrue(QUOTES_THE_JD.search("JD 说要能独立完成 Demo"))
        self.assertFalse(QUOTES_THE_JD.search("想要一份完整 JD 看任职要求"),
                         "向对方要 JD 是正当的，不该被拦")
        self.assertIn(IDENTITY_LABEL, "我是独立开发者，开源作品 1 万+ stars")
        self.assertNotIn(IDENTITY_LABEL,
                         "我做的是一条把重复劳动做成工具的产品线，开源作品累计 3 万+ stars")
        self.assertTrue(VOLUME_BRAG.search("过去一年一共发了 40 个开源项目"))
        self.assertFalse(VOLUME_BRAG.search("开源项目累计 3 万+ stars，7 万+ 注册用户"),
                         "换成 star / 用户数的正确写法被误伤了")
        self.assertFalse(VOLUME_BRAG.search("某产品有 7 万+ 注册用户、18 国语言"),
                         "用户数被当成产量误杀了")
        self.assertFalse(INVERTED_TAG.search("医疗和患者管理这个场景我没做过。"),
                         "去掉尾巴的正常说法被误伤了")
        self.assertFalse([w for w in BANNED_TONE if w in _own_words(ok)])
        # 两处已知的误报必须放行
        keep = "想先问下：智能座舱行业经验是硬门槛，还是 Agent 能力也在考虑范围？"
        self.assertFalse([w for w in BANNED_TONE if w in _own_words(keep)],
                         "「硬门槛」是地道中文，被当成框架词「硬门」误杀了")
        quoted = "熟悉「ChatGPT、Claude 的能力边界」是我的日常"
        self.assertFalse([w for w in BANNED_TONE if w in _own_words(quoted)],
                         "引用 JD 自己的用词不算把框架词搬给 HR")
        matched = "benchmark 跟真实样本对不对得上这件事我做得多"
        self.assertFalse([w for w in BANNED_TONE if w in _own_words(matched)],
                         "「对不对得上」是在说两份数据合不合，"
                         "被当成判词「对得上」误杀了")
        # 但正牌的判词用法照旧要抓住，别把口子开成后门
        self.assertTrue([w for w in BANNED_TONE
                         if w in _own_words("我的能力和这个岗对得上")],
                        "豁免开过头了——判词式的「对得上」必须还能抓到")


if __name__ == "__main__":
    unittest.main()
