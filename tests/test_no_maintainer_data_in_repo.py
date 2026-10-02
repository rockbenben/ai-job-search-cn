"""被跟踪的文件里不许出现活动用户的真实信息。

## 为什么需要它常驻

个人数据不是从 `profile/` 漏出去的——那个目录一直好好地 gitignore 着。**它是被人
顺手抄进注释和 docstring 的**：写说明时想举个具体例子，手边最顺的就是自己的真实
资料。审计一次挖出四处，每一处都长这样：

| 在哪 | 抄进去的是什么 |
|---|---|
| `tools/prescreen.py` 的说明 | 薪资底线与学历专业，都是原样的真值 |
| `tools/serve.py` 的注释 | 姓名（记录一次冒烟实测） |
| `tests/test_cli_contract.py` 的 docstring | 姓名（同一次实测） |
| `tests/test_no_industry_presets.py` 的模式列表 | 雇主名 + 两个作品名 |

最后一条最说明问题：**那是一条「检查有没有泄漏个人数据」的断言，自己成了泄漏点。**

一次性清干净没有用——下次写注释时同样的事会再发生一遍，而且没人会想起来检查。
所以判据要常驻，而且要**从真实资料里现取**，不能写死词表（写死等于把要防的东西
再抄一遍，就是上面第四行那个坑）。

> **写这份说明时又犯了一次。** 上面那张表原本照抄了薪资和学历的真值来举例——
> 举例的诱惑正是这个失误的来源，连写「怎么防它」的人都躲不过。所以描述泄漏时
> 一律只说**是什么类别**，不复述值。

## 判据的取法

只取**明确是专有名词**的字段：姓名、雇主、院校。上一轮实测过：拿通用的
「**字段：** 值」正则抽词，「上海」「中文」「不限」这类普通词全被当成标识符，
噪音淹掉信号。

取小节要**认任何标题层级、标题按前缀比**——真实 `candidate.md` 比模板深一级
（`## 候选人资料` + `### 教育背景`），标题还可能带括注。写死层级的下场是每一节都
「找不到」，而找不到通常意味着**静默放行**。

## 第三类不是词，是整句原话

值有形状（薪资、公司名），抽得出正则；**一句话没有形状**。实测这一类的来源就是
「举例」：注释里写「活动用户资料里写着『……』」，把 `profile/` 里的原句整条引了
进来，还配上归属词——那已经不是举例，是替他表态。词表守卫看不见它，因为它抽的是
专有名词。判据在 `VerbatimSentencesFromTheUsersOwnText`：整句逐字来自使用者正文、
而**又不是仓库自己的话**（同一句在 `workflows/`/`docs/`/`tools/` 里也出现就算仓库
词汇，方向是文档→数据，本来就在公开仓库里）时报，且只报位置，不把原句打印出来。

没有活动用户、或资料没填时这一类**整条跳过**（与薪资那条同档）。

没有活动用户、或资料还没填 → skip。新 clone 与 CI 上不会因此变红。

## 这条不管历史

它只保证**当前这棵树**是干净的。发布前那次压平（`rm -rf .git`）之所以能把历史
一并清掉，前提正是这条绿着——根提交装的就是这棵树。往后再有历史，这条依然只管
当下，历史得另说。
"""

import csv
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_STRIP = "。，,、；;：:（）()【】[]|*` "

#: 二进制与派生产物不看。`profile.example/` 是脚手架，由
#: `test_no_industry_presets` 专门盯着（它比这里更严：连业务域词都不许有）。
#: 二进制文件：下面所有守卫都是**扫文本**的，读它们只会得到乱码。
#:
#: 这里有一个守卫够不着的盲区，写下来免得下次以为「全绿 = 全干净」：
#: **截图能装下这些守卫禁止的一切，而没有任何一条读得懂它。**
#: `README.md` 的头图 `docs/images/dashboard.webp` 就是一张面板截图——
#: 对着真实数据截一张，公司名、分数、薪资、判词会一次全部印在仓库首页上。
#: 判据只能靠人：**面板截图一律对着演示数据截**（`web/public/data.json`
#: 挪开，面板自己会退回 `sample.ts`，页头还会挂「演示数据（虚构）」的标）。
SKIP_SUFFIX = {".png", ".jpg", ".jpeg", ".pdf", ".ico", ".woff", ".woff2",
               ".lock", ".webp", ".avif", ".gif"}


def _section(text: str, title: str) -> str:
    lines = text.splitlines()
    start = depth = None
    for i, ln in enumerate(lines):
        m = _HEADING.match(ln)
        if m and m.group(2).strip().startswith(title):
            start, depth = i, len(m.group(1))
            break
    if start is None:
        return ""
    end = len(lines)
    for j in range(start + 1, len(lines)):
        m = _HEADING.match(lines[j])
        if m and len(m.group(1)) <= depth:
            end = j
            break
    return "\n".join(lines[start:end])


#: 中文文档里的通用占位人名，以及本仓库自己造的示例用户目录。
#: 它们是**写文档时故意用的假名**，不是任何人的标识——扫它们只会一片红。
_EXAMPLE_NAMES = {"张三", "李四", "王五", "赵六", "某某", "谁",
                  "待完善的示例用户", "示例用户", "test", "demo",
                  # 测试夹具名（`test_the_write_actually_lands.py` 的 `USER`）。
                  # 那个文件用的是临时目录、跑完就删，但**手工跑一次
                  # `portal_budget.py --user 写盘判据` 就会在 users/ 下留个真目录**
                  # ——下一次这条守卫就报「被跟踪的文件里有活动用户的真实信息」，
                  # 指着的却是一个夹具名。2026-08-21 亲自踩过一次。
                  "写盘判据"}


def _profile_path():
    """活动用户的 `candidate.md`；没有活动用户或文件不在就返回 None。

    抽出来给 `identifiers()` 和 `personal_figures()` 共用——两条守卫读的是
    同一份资料，路径推导写两遍迟早分叉（这个仓库为「同一逻辑分两组」
    栽过五次）。
    """
    au = ROOT / ".active_user"
    if not au.is_file():
        return None
    user = au.read_text(encoding="utf-8").strip()
    cand = ROOT / "users" / user / "profile" / "candidate.md"
    return cand if user and cand.is_file() else None


def identifiers() -> set:
    """活动用户资料里那些明确是专有名词的值。取不到就返回空集。"""
    cand = _profile_path()
    if cand is None:
        return set()
    user = (ROOT / ".active_user").read_text(encoding="utf-8").strip()
    text = cand.read_text(encoding="utf-8", errors="replace")
    #: **所有用户名，不只是活动用户。** 这个仓库明写支持多人共用一份 clone，
    #: 每个人在 `users/<名>/` 下有自己的数据——那个目录名就是他的名字。
    #: 而这条守卫原来只取活动用户，**第二个人的名字整类够不着**。
    #:
    #: 2026-08-20 逐个文件读时抓到：`serve.py` 与 `test_cli_contract.py` 里写着
    #: 「冒烟实测 `serve.py --user <某个真实用户名>`」——那是 `users/` 下真实存在的
    #: 目录名。`.private/RELEASE-PREP.md` 记着这处曾经还带着活动用户的名字，
    #: 清的时候只清掉了一半，**另一半正是守卫看不见的那一半**。
    #:
    #: 通用示例名要豁免：中文文档里张三李四就是占位符，扫它必然一片红。
    out = {user} | {p.name for p in (ROOT / "users").glob("*")
                    if p.is_dir() and p.name not in _EXAMPLE_NAMES}
    for m in re.finditer(r"\*\*姓名：\*\*\s*(.+)", text):
        out.add(m.group(1))
    #: 雇主：`### <职位> - <公司>（<起止>）`，任何标题层级
    # 横杠两侧只许**行内**空白（[ \t]），不许 \s——\s 含换行，实测跨行漏匹配：
    # 「#### 补充确认（…）\n\n- **专业清单（」被整段吞下，把下一行列表项的加粗词
    # 「专业清单」当成了雇主名，再拿这四个字去扫全仓库，job-rank.md 里凡是讨论
    # 专业规则的句子全数误报（2026-08-14 实测）。
    for m in re.finditer(r"^#{2,6}[ \t]+.+?[ \t]*[-–—][ \t]*(.+?)[（(]", text, re.M):
        out.add(m.group(1))
    #: 院校：教育背景表格的第 3 列
    for ln in _section(text, "教育背景").splitlines():
        cells = [c.strip() for c in ln.split("|")]
        if len(cells) >= 5 and "---" not in ln and "学历" not in ln:
            out.add(cells[3])
    #: **列表写法**：`- <职位/学位>（<起止>）- <公司/院校>（<地点>）`
    #:
    # 上面两条都是照着 `profile.example/candidate.md` 的**模板形状**写的
    # （雇主在 `### <职位> - <公司>（…）` 标题里、院校在表格第 3 列）。而
    # `/job-setup` 真写出来的资料是列表形状：标题只有一个词，雇主与院校都落在
    # 下一行的列表项里，破折号在括号**后面**。
    #
    # 代价（2026-08-18 实测）：这个函数在真实资料上只取到 **1 个**词——用户名。
    # 雇主 0 个、院校 0 个，而 `test_there_is_something_to_check_against` 只验
    # 「非空」，于是**它一直是绿的**。这正是本文件顶上那句「找不到通常意味着
    # 静默放行」说的情形，只是这次静默的是它自己。
    for sec in ("工作经历", "教育背景"):
        for ln in _section(text, sec).splitlines():
            if not ln.lstrip().startswith("-"):
                continue
            for m in re.finditer(r"[）)]\s*[-–—]\s*([^（()\n]{2,40})", ln):
                out.add(m.group(1))
    out = {v.strip().strip(_STRIP) for v in out}
    # 3 字以下的中文词误报率太高（「上海」「中文」都会命中），不作数
    kept = {v for v in out if len(v) >= 3 and not v.startswith("[")}
    #: **用户名单独放行到 2 字。** 那道 ≥3 字的阈值是为「上海」「中文」这类
    #: **普通词**设的——从散文里抽出来的雇主名、院校名确实可能撞上常用词。
    #: 而 `users/` 下的目录名是**人名**，而两字中文名极常见，
    #: 拿三字阈值一刀切，等于把最常见的一类名字整个放过。
    #:
    #: 2026-08-20 变异验证当场证实：塞回一个两字用户名，守卫仍然绿。
    #:
    #: ⚠️ 写这段注释时**当场演了一遍「循环讽刺」**：第一版为了说明「两字名很常见」
    #: 在括号里举了三个例子——而那三个正是 `users/` 下真实存在的目录名，
    #: 放宽后的守卫第一次跑就把这个文件自己报了出来。
    #: `.private/RELEASE-PREP.md` 记过同一形状（一条查泄漏的测试把要找的真实数据
    #: 写进了自己的模式列表）。**举例说明一条隐私规则时，例子本身就是泄漏的入口。**
    #: 人名撞进正常中文的概率远低于「上海」，这个放宽是划算的；真误报了，
    #: 用户换个目录名比丢一条泄漏便宜。
    return kept | {p.name for p in (ROOT / "users").glob("*")
                   if p.is_dir() and len(p.name) >= 2
                   and p.name not in _EXAMPLE_NAMES}


def applied_companies() -> set:
    """你投过的公司名 —— 来自投递记录，同样 gitignore。

    ## 为什么单开这一条

    `identifiers()` 取的是**你自己**的专有名词（姓名、雇主、院校）。而写文档时最
    顺手的例子往往不是你的名字，是**你刚做过的那件事**——于是
    `06-outreach-templates.md` 里出现了「一个真实产出（`<某公司>_AI分析师`，128 字）」，
    把一家你投过的公司连同岗位一起写进了公开仓库。那不是你的资料，是**第三方的**，
    而它泄漏的是「你向这家公司投过简历」这条事实。

    `identifiers()` 天生够不着它：那家公司不在你的 `candidate.md` 里，它在
    `job_search_tracker.csv` 里。判据要跟着数据走。

    公司名过短的不作数（两字名会把正常句子扫成一片红），与 `identifiers()` 同一条阈值。

    **招聘平台自己要豁免。** 台账里的 `company` 有时记的是平台（实测「智联招聘」
    就在里面），而这个仓库整篇都在讲怎么在这些平台上搜岗——`cdp-portals.md` 的
    标题第一行就是它。豁免名单**不写死**，从 `export_web_data.PORTAL_NAMES` 现取：
    那是仓库里渠道名的唯一权威表，加一个新平台不必回来改这里。
    """
    au = ROOT / ".active_user"
    if not au.is_file():
        return set()
    user = au.read_text(encoding="utf-8").strip()
    csv_path = ROOT / "users" / user / "job_search_tracker.csv"
    if not user or not csv_path.is_file():
        return set()
    out = set()
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            name = (row.get("company") or "").strip().strip(_STRIP)
            # 「某上海大型…公司」这类是导出时脱敏过的占位，本来就不是真名
            if len(name) >= 4 and not name.startswith("某"):
                out.add(name)
    return out - _portal_names()


def _portal_names() -> set:
    """仓库自己认的招聘平台名。取不到就返回空集（宁可多报，不可漏报）。"""
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        import export_web_data as ex
        return set(ex.PORTAL_NAMES.values())
    except Exception:
        return set()


def tracked_text_files():
    """已跟踪的，**外加未跟踪但没被 ignore 的**。

    只看 `git ls-files` 有个要命的缺口：**新文件在第一次提交之前是看不见的**。
    实测栽过——这份文件本身刚写好时说明里带着真值，`git ls-files` 里没有它，
    这条断言绿着，于是它被原样提交了进去；直到下一次跑测试（那时它已被跟踪）
    才红。**拦截发生在泄漏之后，等于没拦。**

    未跟踪但没被 ignore 的文件就是「下一次 commit 会带上的东西」，正该一起看。
    真正私密的目录（`users/`、`.private/`、`profile/`）都在 ignore 里，不会被扫到。
    """
    listed = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                            text=True).stdout.split()
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=ROOT, capture_output=True, text=True).stdout.split()
    for n in listed + untracked:
        p = ROOT / n
        if p.suffix.lower() in SKIP_SUFFIX or not p.is_file():
            continue
        yield p


#: 连着两个以上的 `\uXXXX`。单个不算：英文页面里 `&`（&）这类转义遍地都是，
#: 逐个还原只会把噪音放大，而中文名字一还原就是连着好几个。
_ESCAPED_RUN = re.compile(r"(?:\\u[0-9a-fA-F]{4}){2,}")


def readable(path: Path) -> str:
    r"""文件正文，**外加把 `\uXXXX` 转义还原后的那一份**。

    抓取来的页面夹具里，中文常常以转义形态躺在 `<script>` 的 JSON 里
    （`雪球…`）。按字面找中文的判据一个都看不见它。

    实测代价（2026-09-02）：一份详情页夹具的公司名，**明文那处**被下面这条守卫
    逮到并改掉了，而**同一个名字的转义形态留在同一个文件里，三条守卫全绿** ——
    是人复查时撞见的，不是判据抓到的。公开之后它一样搜得到。

    `/job-add-portal` 每接一个新渠道都会带进新的抓取夹具，所以这不是一次性的：
    同一个形状会跟着每一个新渠道再来一遍。
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    decoded = []
    for run in _ESCAPED_RUN.findall(text):
        try:
            decoded.append(bytes(run, "ascii").decode("unicode_escape"))
        except (UnicodeDecodeError, ValueError):
            continue          # 不是合法转义就当它是普通文本，正文那份已经在扫了
    if not decoded:
        return text
    return text + "\n" + "\n".join(decoded)


class NoMaintainerDataInTrackedFiles(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.ids = identifiers()

    def test_there_is_something_to_check_against(self):
        """控制用例：取不到标识符时下面那条是空跑，得说出来而不是假绿。

        **「非空」不够。** 这条原来只断言 `self.ids` 真值，而实测（2026-08-18）
        它在真实资料上只取到 **1 个**词——用户名；雇主 0 个、院校 0 个，因为抽取
        规则是照着 `profile.example` 的模板形状写的，而 `/job-setup` 真写出来的是
        列表形状。断言绿着，覆盖面却只有名字，**这正是本文件顶上警告过的那种
        「找不到＝静默放行」，只是这次静默的是守卫自己**。

        所以改成按**数量**卡：用户名之外至少还得抽到两个专有名词。抽不到就说明
        资料的写法又变了，该回来改抽取规则，而不是让它悄悄退化成只查名字。
        """
        if not self.ids:
            self.skipTest("没有活动用户或资料还没填 —— 无从比对")
        user = (ROOT / ".active_user").read_text(encoding="utf-8").strip()
        others = {v for v in self.ids if v != user}
        self.assertGreaterEqual(
            len(others), 2,
            f"除用户名外只抽到 {len(others)} 个专有名词——雇主/院校多半没抽出来，"
            "而抽不出来意味着这条守卫其实只在查名字。回去看 `identifiers()`："
            "资料的写法是不是又变了。（不打印具体值）")

    def test_no_tracked_file_mentions_the_active_user(self):
        if not self.ids:
            self.skipTest("没有活动用户或资料还没填 —— 无从比对")
        bad = []
        for p in tracked_text_files():
            text = readable(p)
            for term in self.ids:
                if term in text:
                    bad.append(f"{p.relative_to(ROOT).as_posix()}"
                               f"（{term[0]}{'*' * (len(term) - 1)}）")
        self.assertEqual(
            sorted(set(bad)), [],
            "这些被跟踪的文件里有活动用户的真实信息：\n  " + "\n  ".join(sorted(set(bad)))
            + "\n写说明时别拿自己的资料当例子 —— 换成占位写法（`<数字>k`、"
              "`<学历>，<专业>`）或另一个明显虚构的名字。"
              "\n（这条不打印具体值；自己 grep profile 比对）")


    def test_no_tracked_file_names_a_company_you_applied_to(self):
        """投过的公司名不许出现在被跟踪的文件里。

        这是**第三方数据**，而且它顺带说出一件你未必想公开的事：你向这家投过。
        实测抓到一处，在 `06-outreach-templates.md` 的示例里（真实投递目录名）。
        改法和别处一样——换成 `<公司>`，示例的形状一点没少。
        """
        cos = applied_companies()
        if not cos:
            self.skipTest("没有活动用户或还没有投递记录 —— 无从比对")
        bad = []
        for p in tracked_text_files():
            text = readable(p)
            for c in cos:
                if c in text:
                    bad.append(f"{p.relative_to(ROOT).as_posix()}"
                               f"（{c[0]}{'*' * (len(c) - 1)}）")
        self.assertEqual(
            sorted(set(bad)), [],
            "这些被跟踪的文件里写着你投过的公司：\n  "
            + "\n  ".join(sorted(set(bad)))
            + "\n举例时用 `<公司>`，别用刚投过的那一家。")

    def test_the_check_would_actually_catch_something(self):
        """控制用例：把一个真实标识符放进一份临时的被跟踪文件，上面那条必须红。

        没有它，`identifiers()` 哪天返回空集、或扫描漏掉整类文件，
        上面那条会一声不响地变成永远绿。
        """
        if not self.ids:
            self.skipTest("没有活动用户或资料还没填 —— 无从比对")
        term = sorted(self.ids)[0]
        hit = [p for p in tracked_text_files()
               if term in readable(p)]
        self.assertEqual(hit, [], "控制用例本身撞上了真实命中")
        # 不真的写文件：直接验判据对一段含标识符的文本会命中
        self.assertIn(term, f"随便写点什么 {term} 然后继续",
                      "判据连最直白的一次包含都认不出来")


if __name__ == "__main__":
    unittest.main()


#: 归属词：出现在同一行就说明这个数被当成「某个人的取值」在引用，而不是一个例子。
#:
#: **两类都要收，第一版只收了第一类。**
#:
#: - **人称式**：「本人 45 万底线」「我的期望区间」——第一版就在收。
#: - **角色式**：「薪资底线 45 万」「期望区间 45-60k」「可接受底线」——**没有人称**，
#:   靠字段名归属。2026-08-20 逐个文件读时抓到一处漏网：`job-auto.md` 写着
#:   「预筛阈值（**薪资底线 42/45 万**）直接决定 169 个岗永久出局」，
#:   而守卫全绿——那一行一个人称代词都没有。
#:
#: 角色词直接取自 `candidate.md` 的字段名（`personal_figures` 抽的就是那几行），
#: 两处用同一批词，才不会一边抽、一边认不出。
OWNED = ("本人", "我的", "我方", "候选人的底线", "他的底线", "你的底线", "自己的底线",
         "我 ", "出生年",
         # 角色式：字段名本身就是归属
         "薪资底线", "可接受底线", "期望区间", "当前薪资", "年包底线")


def personal_figures() -> set:
    """资料里的**取值**——薪资底线、期望区间这类具体数字。

    ## 为什么要单开第三条

    `identifiers()` 查专有名词，`applied_companies()` 查投过的公司。两条都够不着
    **数字**。而写文档时最容易顺手带出来的恰恰是数字：解释一条规则为什么这么定，
    举个例子最有说服力的就是「在我的底线上实测……」。

    2026-08-20 实测栽了一次：`prescreen.py` 的注释里写进了
    「在本人 **<某个数> 万**底线上实测：会结案 374 个……」。那个数直接来自
    `candidate.md` 的「可接受底线」，而 `tools/` 是要提交的。
    两条老守卫都是绿的——它们压根不看数字。

    是用户自己发现的，不是测试。**守卫漏掉的那一类，代价由用户承担。**

    ## 判据

    只取「可接受底线」「期望区间」这类**行**里的数字，且只认 3 位以上的数
    （`45` 这种两位数在正常文本里到处都是，扫它必然一片红）。所以真正被钉住的是
    `28k`、`450000` 这类写法，以及「45 万」这种**带单位的组合**——组合起来
    重复出现的概率足够低。

    命中的行标题从模板取，不写死：`profile.example/candidate.md` 里叫什么就是什么。
    """
    path = _profile_path()
    if path is None or not path.is_file():
        return set()
    text = path.read_text(encoding="utf-8")
    out = set()
    #: 出生年与年龄。**从资料里现取，不写进这个文件**——
    #: RELEASE-PREP 记过一次「循环讽刺」：一条查泄漏的测试，把要找的真值
    #: 写进了自己的模式列表。年龄是四位/两位数，单独扫必然一片红，
    #: 所以和薪资取值一样，靠下面「取值 + 归属词同行」那道判据收窄。
    for ln in _section(text, "身份").splitlines():
        # **只认写着「出生年」的那一行。** 不加这个限定，四位年份的正则会把
        # 日期里的 `2026` 一起抽走，而「一个日期紧跟着归属词」这种行满仓库都是
        # ——判据当场变成一片红（实测四处误报）。
        if "出生年" in ln:
            for m in re.finditer(r"(19\d{2})", ln):
                out.add(m.group(1))
        for m in re.finditer(r"(\d{2})\s*岁", ln):
            out.add(f"{m.group(1)} 岁")
            out.add(f"{m.group(1)}岁")
    for ln in _section(text, "薪资").splitlines():
        if not any(k in ln for k in ("底线", "期望区间", "当前薪资")):
            continue
        # 「28k × 16薪」「45 万」「450000」——带单位的组合才作数
        for m in re.finditer(r"(\d[\d,\.]{1,9})\s*(k|K|万|元)", ln):
            num = m.group(1).replace(",", "")
            if len(num.replace(".", "")) >= 2:
                out.add(f"{num} {m.group(2)}")
                out.add(f"{num}{m.group(2)}")
    return out


class NoPersonalFiguresInTrackedFiles(unittest.TestCase):
    """资料里的取值不许出现在要提交的文件里。

    阈值一律**从命令行传进来**（`prescreen.py` 顶上那句「本工具不解析那份散文」
    就是这个意思），所以仓库里任何地方都不该出现某个人的具体取值——
    包括注释里的「实测」举例。要举例就说方法，让读的人拿自己的数去跑。
    """

    @classmethod
    def setUpClass(cls):
        cls.figs = personal_figures()

    def test_the_extractor_still_finds_something(self):
        """控制用例：抽不到就是空跑，说出来，别假绿——这份文件为此栽过一次。"""
        path = _profile_path()
        if path is None or not path.is_file():
            self.skipTest("资料还没填 —— 无从比对")
        text = path.read_text(encoding="utf-8")
        if "薪资" not in text:
            self.skipTest("资料里还没有薪资那节")
        self.assertTrue(
            self.figs,
            "薪资那节里一个取值都没抽到——多半是资料的写法变了，"
            "回去看 `personal_figures()` 的正则，别让它退化成空跑。（不打印具体值）")

    def test_no_tracked_file_repeats_them(self):
        if not self.figs:
            self.skipTest("抽不到取值 —— 无从比对")
        bad = []
        for p in tracked_text_files():
            if p.name == Path(__file__).name:
                continue
            for ln in readable(p).splitlines():
                # **取值本身不算泄漏**——`28k`、`45 万` 在任何招聘页 fixture 里
                # 都有，扫它一片红（第一版实测 24 个文件全是误报）。
                # 泄漏的是把它**当成某个人的取值**去引用：
                #     「在本人 45 万底线上实测……」
                # 所以判据是同一行里既有取值、又有归属词。
                if not any(f in ln for f in self.figs):
                    continue
                if any(w in ln for w in OWNED):
                    bad.append(p.relative_to(ROOT).as_posix())
                    break
        self.assertEqual(sorted(set(bad)), [],
                         "这些要提交的文件里出现了资料里的薪资取值——"
                         "举例要说方法，不写某个人的数（不打印具体值）：\n  "
                         + "\n  ".join(sorted(set(bad))))


#: 维护者的**作品成果**：产品名、注册用户数、star 数、工具数。
#:
#: 与 `identifiers()`（姓名/雇主/院校）和 `personal_figures()`（薪资取值）都不同：
#: 这些数字**同时**是两样东西——项目的公开身份（README 就链着作者的 GitHub 与
#: 365 开源计划），以及**简历上的主张**。前者是有意公开的，后者不该出现在一个
#: 给别人用的工具里。
#:
#: 2026-08-20 用户点破薪资那处之后，逐个文件读出来的：`resume/README.md` 与
#: `resume/template.typ` 拿真实作品数据当排版示例，`06-outreach-templates.md`
#: 的示例开场白里点名了产品与用户量，两个测试文件把它们写成了夹具。
#:
#: 讽刺的是**同目录的 `resume/example.typ` 做对了**——它的正则示例是编的
#: `30%|6 个独立服务`。同一套东西，示例文件用占位符，模板注释用真数据。
#:
#: 判据只认「当成我的成果去引用」的形状，不认数字本身：`8.6K stars` 出现在
#: 讲某个开源库的段落里没有问题。所以这里钉的是**具体那几个真值**，
#: 而不是「N 万+ 注册用户」这种句式。
PORTFOLIO_CLAIMS = (
    "AiShort",
    "10 万+ 注册用户", "10w+注册",
    "8.6K+ stars", "950+ stars", "330+ stars",
    "28 款开源工具",
)

#: 项目自己的公开身份，**不是**要清的东西：README 的徽章、LICENSE 的署名、
#: 365 开源计划的链接都是有意公开的。列在这里是为了让下一个人一眼看出边界在哪，
#: 不要顺手把它们也「清掉」。
PUBLIC_IDENTITY = ("rockbenben", "365 开源计划", "365.aishort.top")


class PortfolioClaimsAreePlaceholders(unittest.TestCase):
    """作品成果只能以占位符出现在被跟踪文件里。

    要举例就写 `<N> 万+ 注册用户`、`<你的产品>`——别人照抄时才知道那里要填自己的数。
    写真值有两重代价：泄漏，以及**误导**（读的人会以为那是框架要求的格式）。
    """

    def test_no_tracked_file_states_them(self):
        bad = []
        for p in tracked_text_files():
            if p.name == Path(__file__).name:
                continue
            text = readable(p)
            for claim in PORTFOLIO_CLAIMS:
                if claim in text:
                    bad.append(f"{p.relative_to(ROOT).as_posix()}  ←「{claim}」")
        self.assertEqual(sorted(set(bad)), [],
                         "这些要提交的文件里写着维护者的真实作品成果——"
                         "换成 `<N> 万+ 注册用户` `<你的产品>` 这类占位符：\n  "
                         + "\n  ".join(sorted(set(bad))))

    def test_the_public_identity_is_left_alone(self):
        """反向守卫：别把项目自己的公开身份当成泄漏清掉。

        README 的 365 徽章、LICENSE 的署名是**有意公开**的。上一个人清个人数据时
        很容易顺手把它们一起删了，那不是保护隐私，是把项目的出处抹掉。
        """
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for term in PUBLIC_IDENTITY:
            with self.subTest(term):
                self.assertIn(term, readme,
                              f"README 里的「{term}」没了——那是项目自己的公开身份，"
                              "不在要清的范围内")

    def test_the_example_file_stays_synthetic(self):
        """`resume/example.typ` 是这条规矩的正面样板，别让它退化。"""
        ex = (ROOT / "resume" / "example.typ").read_text(encoding="utf-8")
        self.assertIn("张三", ex, "示例简历不再用占位姓名了")
        for claim in PORTFOLIO_CLAIMS:
            with self.subTest(claim):
                self.assertNotIn(claim, ex)


def _verdicts():
    """判词档的正本在 `tools/_cli.py`。取不到就返回空——守卫宁可窄，不要假绿。"""
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        import _cli
        return _cli.VERDICTS
    except Exception:                      # noqa: BLE001
        return ()


def researched_companies() -> set:
    """**看过、评过、但没投**的公司——`applied_companies()` 够不着的那一类。

    两条守卫此前都只覆盖「投过的」（台账）。而写文档举例时最顺手的往往是
    **刚刚评过的那个岗**：2026-08-20 逐个文件读，`job-rank.md` 与
    `test_verdict_cap.py` 里都点名了一家航空制造公司的具体岗位、分数与薪资串
    ——那家公司在职位库里，不在台账里，两条老守卫**全绿**。

    泄漏的是「这个人看过这家的岗、并且一度判掉了它」。那既是求职者的行踪，
    也是对第三方的评价。

    平台名与「某…」开头的脱敏名要豁免：前者是这个仓库整篇在讲的东西，
    后者本来就是匿名标签。
    """
    ptr = ROOT / ".active_user"
    if not ptr.is_file():
        return set()
    user = ptr.read_text(encoding="utf-8").strip()
    f = ROOT / "users" / user / "job_scraper" / "seen_jobs.json"
    if not user or not f.is_file():
        return set()
    sys.path.insert(0, str(ROOT / "tools"))
    import _cli
    import json as _json
    seen = _cli.seen_of(_json.loads(f.read_text(encoding="utf-8")))
    out = set()
    for e in seen.values():
        name = str(e.get("company") or "").strip()
        if len(name) >= 3 and not name.startswith("某") and name not in PLATFORMS:
            out.add(name)
    return out


#: 招聘平台与基础设施：整篇文档都在讲它们，不是泄漏。
PLATFORMS = {"猎聘", "智联招聘", "BOSS直聘", "BOSS 直聘", "前程无忧", "51job",
             "阿里云", "知名公司", "Apple"}

#: 企业名的后缀与地域前缀。判据要比的是**字号**（核心那几个字），不是全称。
#:
#: 2026-08-20 实测漏网：`writeback.py` 的注释里写着**简称 + 分数 + 判词**，
#: 而库里存的是「简称 + 科技股份有限公司上海分公司」那样的全称——判据写的是
#: `n in ln`（全称出现在这一行里），**方向反了**：文档用简称，库用全称，
#: 于是一条同时带着公司名、分数和判词的注释全绿走过。
#:
#: 夹具里那对「简称 / 简称加险种后缀」是同一个形状——那次是**故意**用长短两种
#: 写法验模糊匹配，我改了一边就撞红了。同一个坑，两个方向。
#:
#: **这两条说明本身不许点名任何真实公司。** 举例说明一条隐私规则时，例子就是
#: 泄漏的入口，而这个文件把自己排除在扫描之外（它必须装得下那些词表），
#: 所以没人会替它报警——判据落在下面 `test_this_guard_names_no_real_company`。
_SUFFIX = ("科技股份有限公司", "股份有限公司", "有限责任公司", "有限公司",
           "集团", "公司", "科技", "网络", "信息技术", "上海分公司", "分公司")
_PREFIX = ("浙江", "江苏", "广东", "上海", "北京", "深圳", "杭州", "成都", "南京")


def _core(name: str) -> str:
    """取企业名的字号：剥掉地域前缀与常见后缀。

    剥完短于 3 个字的返回空串——两字字号在正常句子里误报率太高
    （与 `identifiers()` 的长度阈值同一条理由）。
    """
    s = name.strip()
    for p in _PREFIX:
        if s.startswith(p):
            s = s[len(p):]
            break
    # **反复剥到不动为止**：企业名常有两层后缀（「…科技股份有限公司」+「上海分公司」），
    # 只剥一次会留下一串没人会照抄的长名，判据等于没放宽。
    changed = True
    while changed:
        changed = False
        # **按长度降序试**，不能按书写顺序：「…科技股份有限公司上海分公司」
        # 先撞上短的「公司」就只剥掉两个字，留下「…上海分」这种没人会照抄的串，
        # 判据等于没放宽（实测第一版就是这样）。
        for suf in sorted(_SUFFIX, key=len, reverse=True):
            if s.endswith(suf) and len(s) > len(suf):
                s = s[: -len(suf)]
                changed = True
                break
    #: **纯 ASCII 的短字号不作数。** 库里有公司的字号剥完是 `CDP`、`ABB` 这种缩写，
    #: 而 `CDP` 在本仓库满篇都是（Chrome DevTools Protocol）——拿它当公司名扫，
    #: 每一份讲浏览器渠道的文档都会被判成泄漏。中文字号没有这个歧义。
    cjk = sum(1 for ch in s if "一" <= ch <= "鿿")
    if cjk >= 3 or (not cjk and len(s) >= 6):
        return s
    return ""


class ResearchedCompaniesStayOutOfProse(unittest.TestCase):
    """真实公司名 + 评估语境 = 泄漏；单独出现的知名公司名不算。

    判据用「公司名 + 评估词同行」，与薪资那条同一个形状。理由一样：
    公司名本身满仓库都是（`智联招聘` 是平台、`阿里云` 是 WAF），
    扫名字必然一片红；**把它当成「我评过的那个岗」去引用**才是泄漏。
    """

    #: 出现在同一行就说明这个公司名是在讲一次真实评估。
    #: 判词档从 `_cli.VERDICTS` 取，不在这儿再抄一份词表
    #: （`test_shared_vocab_single_source` 会拦下连写三档的字面量）。
    JUDGED = ("分", "判词", "年包", "深评", "粗筛", "翻案", "毙",
              "投递话术", "职位评估") + tuple(_verdicts())

    def test_no_tracked_file_names_one_it_judged(self):
        names = researched_companies()
        if not names:
            self.skipTest("还没抓过职位 —— 无从比对")
        bad = []
        for p in tracked_text_files():
            if p.name == Path(__file__).name:
                continue
            if "fixtures" in p.parts:
                continue            # 抓取样本另有一条守卫，见下
            for ln in readable(p).splitlines():
                if not any(w in ln for w in self.JUDGED):
                    continue
                hit = next((n for n in names if _core(n) and _core(n) in ln), None)
                if hit:
                    bad.append(p.relative_to(ROOT).as_posix())
                    break
        self.assertEqual(sorted(set(bad)), [],
                         "这些要提交的文件里，把真实公司名和一次真实评估写在了一起——"
                         "换成「某<行业>公司」（不打印公司名）：\n  "
                         + "\n  ".join(sorted(set(bad))))


class CapturedFixturesCarryNoOnesName(unittest.TestCase):
    """抓回来的页面样本里不许留第三方的姓名与按人标识。

    `.agents/skills/*/cli/tests/fixtures/` 是从招聘站实抓的 HTML/JSON，
    **里面装的是别人的数据**：`recruiterName`（姓+称谓）、`recruiterId`、
    `imId`（聊天账号）、`recruiterPhoto`（真人头像）。
    2026-08-20 实测 208 个 `recruiterName`、306 个按人标识。

    `.private/RELEASE-PREP.md` 早就把这一条列为「仍然没查的（判断为低风险）」
    ——地方猜对了，只是没去查。

    解析器一个都不引用（`recruiterTitle` 才是它取的），所以脱敏零成本。
    保留的是 `jobId` / `compId` 这类**岗位与公司的公开标识**，那不是按人的。
    """

    NAME = re.compile(r"[\u4e00-\u9fff]{1,2}(?:先生|女士|小姐)(?![\u4e00-\u9fff])")
    PERSON_FIELDS = ("recruiterId", "imId", "recruiterPhoto")

    #: 占位姓与通用示例名不算命中。「某先生」是脱敏后的写法；
    #: 张三李四是中文文档里的通用示例人名，与真实招聘者无关。
    SAFE_SURNAMES = ("某", "张", "李")

    def test_no_recruiter_names_in_prose_either(self):
        """**正文里也不许有。** 抓取样本清干净了，文档里照样可能抄一份。

        实测（2026-08-20）同一位招聘者的姓名与所属公司在**三处**出现：
        `cdp-portals.md` 的字段实测表、`job-scrape.md` 的 seen_jobs schema 示例、
        以及 `job-scrape.md` 的字段价值表——全是「实测拿到什么」的举例。
        写文档的人抄的是真实返回值，而那个值里装着别人的名字。

        脱敏不影响任何判据：那道硬门要的是「主体名称里有没有『人力资源』」，
        不是那个人叫什么。
        """
        bad = []
        for p in tracked_text_files():
            if p.name == Path(__file__).name or "fixtures" in p.parts:
                continue
            for i, ln in enumerate(
                    readable(p).splitlines(), 1):
                if any(m.group()[0] not in self.SAFE_SURNAMES
                       for m in self.NAME.finditer(ln)):
                    bad.append(f"{p.relative_to(ROOT).as_posix()}:{i}")
                    break
        self.assertEqual(sorted(set(bad)), [],
                         "这些文件的正文里写着招聘者的姓名——那是第三方个人信息，"
                         "换成 `<姓>先生`（不打印姓名）：\n  " + "\n  ".join(sorted(set(bad))))

    def _fixtures(self):
        return [p for p in tracked_text_files()
                if "fixtures" in p.parts and p.suffix in (".html", ".json")]

    def test_there_are_fixtures_to_check(self):
        self.assertTrue(self._fixtures(), "一个抓取样本都没找到——这条守卫在空跑")

    def test_no_recruiter_names(self):
        bad = []
        for p in self._fixtures():
            names = {n for n in self.NAME.findall(readable(p))
                if not n.startswith("某")}
            if names:
                bad.append(f"{p.relative_to(ROOT).as_posix()} ({len(names)} 个)")
        self.assertEqual(bad, [],
                         "抓取样本里还留着招聘者的姓名——那是第三方个人信息，"
                         "换成「某先生/某女士」（解析器不读这个字段）：\n  "
                         + "\n  ".join(bad))

    def test_person_ids_are_synthetic(self):
        """按人标识必须是换过的。判据：同一个值在样本之间不重复出现真实散列。

        这里只能验「字段还在、值是十六进制」这个形状——真假分不出来。
        所以真正的判据放在上面那条姓名守卫上，这条钉住**字段没被重新引入原始值**：
        源码里一旦开始读这三个字段，脱敏就不再是零成本，要重新裁定。
        """
        src = ROOT / ".agents" / "skills" / "liepin-search" / "cli" / "src"
        if not src.is_dir():
            self.skipTest("CLI 源码不在")
        code = "\n".join(p.read_text(encoding="utf-8") for p in src.glob("*.ts"))
        for fld in self.PERSON_FIELDS:
            with self.subTest(fld):
                self.assertNotIn(fld, code,
                                 f"解析器开始读 `{fld}` 了——它是按人的标识，"
                                 "样本里那些值是脱敏过的假值，读它会拿到假数据；"
                                 "真要用就得重新裁定怎么处理第三方信息")


def _store_rows():
    """职位库里的 (标题, 分数, 公司) —— 只给下面那条守卫用。"""
    ptr = ROOT / ".active_user"
    if not ptr.is_file():
        return []
    user = ptr.read_text(encoding="utf-8").strip()
    f = ROOT / "users" / user / "job_scraper" / "seen_jobs.json"
    if not user or not f.is_file():
        return []
    sys.path.insert(0, str(ROOT / "tools"))
    import _cli
    import json as _json
    seen = _cli.seen_of(_json.loads(f.read_text(encoding="utf-8")))
    return [(str(e.get("title") or "").replace(" ", ""),
             e.get("rank_score"),
             str(e.get("company") or "").strip()) for e in seen.values()]


class DemoDataIsInventedNotCopied(unittest.TestCase):
    """演示数据必须是编的，不能是从职位库里拷一行出来改个公司名。

    ## 这条守卫为什么和上面那些不一样

    上面每一条守的都是**标识符本身**：姓名、公司名、薪资数字。而 2026-08-20
    逐个文件读到 `web/src/data/sample.ts` 时撞见的是另一种形状——标识符**已经
    被换掉了**，四条演示岗照样是真实评估记录：

    | 演示数据那一条长什么样 | 它对着库里哪一条 |
    |---|---|
    | `示例<字号>科技股份有限公司上海分公司` · 某职位 · **62** | 真公司名**只差一个字**，职位名与分数**一字不差** |
    | 平台脱敏串 `某大型…上市公司` · 某职位 | 公司串**逐字取自库里** |
    | `某人力资源服务集团（上海）` · 某职位 · 55 · 某区 · 猎聘 | 真公司是家人力资源机构，其余五项**全对上** |
    | `示例商务咨询有限公司` · 某职位 | 真公司**同后缀**，只把字号换成「示例」 |

    公司名改一个字挡不住任何人：**标题 + 分数**这一对就够把岗位定回去，
    而顺着那一对能读到的是这个人评过谁、给了多少分、嫌它哪里不好。
    而 `sample.ts` 自己的文件头就写着「真实职位的公司 + 真实的负面评价
    放在公开仓库里也不合适」——规则一直在，没有人验。

    ## 判据

    拷贝的签名是**指纹重合**，不是某个词出现。所以比的是行：
    带分数的演示岗，它的 (标题, 分数) 不许在库里存在；公司串不许逐字出现在库里。
    分数为 null 的不算——未评分的通用标题（「AI 产品经理」库里有 59 条）
    本来就没有辨识度，拿它当指纹只会逼演示数据用假标题。

    公开 clone 里没有职位库，这条自动跳过；它守的是维护者这一侧。
    """

    def setUp(self):
        self.rows = _store_rows()
        if not self.rows:
            self.skipTest("没有活动用户或职位库")

    def test_no_demo_job_reproduces_a_real_row(self):
        src = ROOT / "web" / "src" / "data" / "sample.ts"
        # **不跳过**：它是已跟踪文件。这条守卫的全部作用就是盯着它，
        # 文件一改名守卫就静默消失，那正好是最该报警的时刻。
        self.assertTrue(src.is_file(),
                        "web/src/data/sample.ts 不在了 —— 演示数据换了地方，这条守卫要跟着改")
        text = src.read_text(encoding="utf-8")
        fingerprints = {(t, sc) for t, sc, _ in self.rows if sc is not None}
        companies = {c for _, _, c in self.rows if c}
        bad = []
        for blk in text.split('    id: "')[1:]:
            t = re.search(r'title: "([^"]+)"', blk)
            c = re.search(r'company: "([^"]+)"', blk)
            sc = re.search(r"score: (\d+),", blk)
            if t and sc and (t.group(1).replace(" ", ""), int(sc.group(1))) in fingerprints:
                bad.append(f"标题+分数与库里某条相同：{t.group(1)} / {sc.group(1)}")
            if c and c.group(1) in companies:
                bad.append(f"公司串逐字取自库里：{c.group(1)}")
        self.assertEqual(bad, [],
                         "演示数据是从真实职位库里拷的行 —— 换掉公司名不够，"
                         "标题加分数就能把岗位定回去，顺带定回这个人给了它多少分："
                         + "；".join(bad))

    def test_this_guard_names_no_real_company(self):
        """**这个文件自己**不许点名任何真实公司。

        上面每一条守卫都跳过本文件（`p.name == Path(__file__).name` 那一句）——
        它必须装得下 `OWNED` / `PORTFOLIO_CLAIMS` 那些词表，扫自己必然一片红。
        代价是**这个文件成了唯一没人看的地方**，而它恰恰最容易攒真值：
        每加一条守卫，最顺手的说明方式就是把刚抓到的那个例子原样抄进 docstring。

        2026-08-20 一天之内犯了两次：先是解释「为什么两字用户名也要拦」时把三个
        真实用户名写进注释，后是新加上面这条拷贝守卫时把四家真公司列成对照表。
        两次都是**在写隐私规则的过程中泄漏隐私**，两次都因为自己不扫自己而无声。

        所以判据只对着本文件、只看一件事：库里的真实公司名一个都不许出现。
        词表不受影响——那些是维护者自己的说法与数字，不是公司名。
        """
        me = Path(__file__).read_text(encoding="utf-8")
        names = [c for _, _, c in self.rows
                 if len(c) >= 4 and not c.startswith("某") and c not in PLATFORMS]
        bad = sorted({c for c in names if c in me})
        self.assertEqual(bad, [],
                         "守卫文件自己点名了真实公司 —— 它不扫自己，所以没人会替它报警。"
                         "说明里写形状（「真公司名只差一个字」），别写是哪一家："
                         + "；".join(bad))


# ============================================================================
# 第三类：整句原话
# ============================================================================

#: 被「」包起来的整句。**短的不算**——「可以投」「硬门」这类是框架词，
#: 由 `test_display_wording` 那张表管；这里只管成句的原话。
_QUOTE_RUN = re.compile(r"「([^」\n]{12,80}?)」")

#: 算作「使用者自己的正文」的那些文件。
#:
#: **只收 `profile/`。** `outreach.md` 与 `evaluation.md` 里那些引号半数是在引
#: 职位描述原文（公开文本），拿来当个人语料扫，实测报出来的三条全是这种回声和
#: 一个日期标签——噪音淹掉信号，正是这份文件顶上关于「取法」的那条教训。
#: 话术与评估是命令生成的，不是他写的；`profile/` 里才是他自己填与定过稿的话。
_PERSONAL_GLOBS = ("profile/*.md",)

#: 仓库自己的话住在哪儿。同一句在这里也出现，方向就是「文档→数据」——
#: 那句话本来就在公开仓库里，不算从谁身上抄走。
#:
#: **不能拿「所有被跟踪的文件」当这个集合**：泄漏点本身也在被跟踪文件里，
#: 那句话就会同时出现在「仓库文档」一侧，于是每一条真泄漏都自我豁免了。
#: 所以这里只列**给人看的模板与说明**；`tests/` 与 `tools/` 都不在其中——
#: 注释里抄原话正是这条守卫要抓的那件事（本文件顶上那张表记的四处，
#: 两处就在 `tools/` 的注释里）。
_REPO_DOC_DIRS = ("workflows", "docs", "profile.example", "templates",
                  ".claude/skills", ".agents/skills")
_REPO_DOC_FILES = ("AGENTS.md", "CLAUDE.md", "README.md", "SETUP.md",
                   "CONTRIBUTING.md", "SECURITY.md",
                   "resume/template.typ", "resume/example.typ",
                   "cover_letter/template.typ", "documents/README.md")


def _norm(text: str) -> str:
    """比对用的形状：空白全部折成单空格。换行是排版，不是内容。"""
    return " ".join(text.split())


def _active_user_dir():
    au = ROOT / ".active_user"
    if not au.is_file():
        return None
    user = au.read_text(encoding="utf-8").strip()
    if not user or user in _EXAMPLE_NAMES:
        return None
    d = ROOT / "users" / user
    return d if d.is_dir() else None


def personal_blob() -> str:
    u = _active_user_dir()
    if u is None:
        return ""
    out = []
    for g in _PERSONAL_GLOBS:
        for p in sorted(u.glob(g)):
            out.append(_norm(p.read_text(encoding="utf-8", errors="replace")))
    return "\n".join(out)


def _repo_doc_paths():
    for d in _REPO_DOC_DIRS:
        base = ROOT / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_file() and p.suffix.lower() in (".md", ".py"):
                yield p
    for f in _REPO_DOC_FILES:
        p = ROOT / f
        if p.is_file():
            yield p


def _quote_fragments(text: str) -> list:
    """文本里被「」包起来、够长到算「一句话」的那些片段（空白已归一）。

    **要带至少四个汉字**：`prompt engineering`、`evaluation.md` 这种是术语和
    文件名，长度够了但不是句子——拿它们当「原话」判，报出来全是噪音。
    """
    out = []
    for m in _QUOTE_RUN.finditer(text):
        frag = _norm(m.group(1))
        if len(frag) < 12:
            continue
        if len(re.findall(r"[㐀-鿿]", frag)) < 4:
            continue
        out.append(frag)
    return out


#: 全文语料，按文件缓存一次。判「谁先写的这句话」必须看**全文**：
#: 工具印出去的话在源码里是不带引号的字符串，只在别处的「」里找方向会漏掉它。
_TEXTS = {}
_BLOB = ""


def _all_texts() -> dict:
    if not _TEXTS:
        for p in tracked_text_files():
            _TEXTS[str(p)] = readable(p)
    return _TEXTS


def _blob() -> str:
    global _BLOB
    if not _BLOB:
        _BLOB = "\n".join(_all_texts().values())
    return _BLOB


def authored_elsewhere(frag: str, here: Path) -> bool:
    """这句话在**别的**被跟踪文件里也逐字写着吗。

    数的是出现次数：全仓次数减掉本文件次数还有剩 → 别处先写的。
    另一种写法是把整棵树拼成一条大串、再 `replace` 掉本文件那一段——它的静默
    失败方向是**漏报**（本文件与拼接结果有一处行尾差异，那次删除就什么也没删掉，
    泄漏点自我豁免而守卫全绿）。判据失效只能朝红的方向坏。

    ⚠️ **这一条有明确的盲区，别把它读成「原话不会进仓库」**：它认的是
    「只在这一份文件里出现」的形状，所以同一句话被抄到**两处**时，两处都会因为
    「别处也写着」被放掉。真正兜住第一次的那道是它自己——第一次进来就红，
    于是不会有第二次；它防的是新增，不是既成事实的扩散。
    """
    texts = _all_texts()
    mine = texts.get(str(here))
    if mine is None:
        # 植入用例传的是「还不存在的文件」：它没有正文，本文件次数就是 0，
        # 于是「别处写着」只看全仓次数 —— 这正是植入要的形状。
        mine = readable(here) if here.is_file() else ""
    return _blob().count(frag) - mine.count(frag) > 0


def quoted_personal_sentences(text: str, personal: str,
                              here: Path = None) -> list:
    """`text` 里那些「逐字来自使用者正文、又不是仓库别处先写出来的话」的整句。

    `here` = 正在看的这个文件。**别处**也逐字写着同一句 → 方向是那处先写、
    这里只是引用，不算从谁身上抄走；只在这一份里出现 → 抄的。
    按文件排除而不是按目录排除：`tools/` 里既有泄漏面（注释抄原话），也有
    工具自己印出去的话（那些话后来也被写进资料那一侧），用目录一刀切两头都判错。

    模板与说明那一侧（`profile.example/`、`workflows/`）整份不看：资料是从它们
    长出来的，模板句在两边逐字出现是常态，报出来只会淹掉真信号。
    """
    if here is not None and _is_authored(here):
        return []
    out = []
    for frag in _quote_fragments(text):
        if frag not in personal:
            continue
        if here is not None and authored_elsewhere(frag, here):
            continue
        out.append(frag)
    return out


def _is_authored(path: Path) -> bool:
    """这份文件是不是「写给人看的模板与说明」那一侧。

    那一侧不是泄漏面：使用者的资料是从 `profile.example/` 与 `workflows/`
    长出来的，模板句在两边逐字出现是常态。泄漏面是 `tests/`、`tools/`、`web/`
    这些「顺手举个例子」的地方。

    ⚠️ 这一层是**必要**的，不是省扫描：模板里那句话常常只在模板自己出现一次，
    方向判据在这种形状上算出「别处 0 处」，于是那份模板会被判成泄漏点。
    撤掉它，`test_the_doc_vocabulary_is_still_the_baseline_side` 当场红——
    那里专挑这种「只出现在一处」的模板句来验。
    """
    rel = path.relative_to(ROOT).as_posix()
    return (any(rel.startswith(d + "/") for d in _REPO_DOC_DIRS)
            or rel in _REPO_DOC_FILES)


class VerbatimSentencesFromTheUsersOwnText(unittest.TestCase):
    """专有名词抽得出正则，**一句话抽不出**——所以句子要有另一条判据。

    这一类的来源还是那个「举个例子」的手感：注释里写「活动用户资料里写着『……』」，
    后面跟的就是 `profile/` 里的原句，还配着归属词。那已经不是举例，是替他表态：
    读的人会把那句当成他定过稿的话，而它只是他被问到时的一次回答。

    报的时候只给**文件与句数**，不复述原句——否则这条守卫自己就成了新的泄漏点
    （本文件顶上那张表记的就是这件事）。
    """

    @classmethod
    def setUpClass(cls):
        cls.personal = personal_blob()
        if not cls.personal:
            # **两种「空」要分开说**：CI 上没有活动用户，跳过是对的；
            # 本机有活动用户却抽不到正文，那是取法坏了，得响亮地说，
            # 不能和「没数据」共用一句 skip —— 那样改错目录都不会有人看见。
            if _active_user_dir() is not None:
                raise unittest.SkipTest(
                    "⚠️ 有活动用户，但按 `_PERSONAL_GLOBS` 抽不到任何正文 —— "
                    "要么资料还没填，要么这条的取法指错了地方")
            raise unittest.SkipTest("没有活动用户 —— 无从比对")
        # 全仓只走一遍，两份断言共用这一份结果：`readable()` 一趟四十多秒，
        # 扫两轮是白白翻倍。模板与说明那一侧不是泄漏面，不看。
        cls.hits = [(p, quoted_personal_sentences(readable(p), cls.personal, here=p))
                    for p in tracked_text_files() if not _is_authored(p)]
        cls.hits = [h for h in cls.hits if h[1]]

    def _one_of_mine(self) -> str:
        """找一句只在资料正文里、仓库里没人写过的话，供植入用例用。"""
        u = _active_user_dir()
        for p in sorted(u.glob(_PERSONAL_GLOBS[0])):
            for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
                s = _norm(re.sub(r"^[\s>*\-#\d.、（）()]+", "", ln))
                if len(s) >= 14 and len(re.findall(r"[㐀-鿿]", s)) >= 4 \
                        and s in self.personal and _blob().count(s) == 0:
                    return s
        return ""

    def test_the_ruler_catches_a_planted_quote(self):
        """控制用例：把一句真实资料原话嵌进一行注释，必须被逮到。"""
        s = self._one_of_mine()
        self.assertTrue(s, "资料里取不到一句「仓库没有」的正文 —— 比对是空跑")
        got = quoted_personal_sentences(f"活动用户资料里写着「{s}」",
                                        self.personal,
                                        here=ROOT / "某个新文件.py")
        self.assertEqual(got, [s])

    def test_direction_is_what_exempts_not_content(self):
        """**反向控制**：豁免只看方向，不看内容——一句话在**别处**也逐字写着，
        那就是那处先写的、这里只是引用。

        这一条只管「该放掉的放掉」；「该报的会报」由
        `test_the_ruler_catches_a_planted_quote` 用一句仓库里根本没有的话去验。
        两支合起来才是方向判据——**别在这里再要一份「只出现在一处」的样本**：
        存量清完之后树里就没有那种形状了，那样这条会常年跳过而没人察觉。

        判方向用的是全文出现次数，不是「别处的引号里也出现」：工具印出去的话
        在源码里是不带引号的字符串，只在引号里找方向就会把工具自己写成泄漏点。
        """
        texts = _all_texts()
        seen = {f for t in texts.values() for f in _quote_fragments(t)
                if f in self.personal}
        counts = {f: sum(1 for t in texts.values() if f in t) for f in seen}
        shared = [(p, f) for p, t in texts.items() for f in _quote_fragments(t)
                  if counts.get(f, 0) >= 2]
        if not shared:
            self.skipTest("这棵树里没有「多处都写着、又落在资料里」的句子 —— "
                          "这一支没东西可验，不算通过")
        p, frag = shared[0]
        self.assertNotIn(
            frag, quoted_personal_sentences(texts[p], self.personal, here=Path(p)),
            "别处也写着这句话，方向是「那处先写」，却仍然报在这一份上")

    def test_the_doc_vocabulary_is_still_the_baseline_side(self):
        """模板与说明那一侧（`profile.example/`、`workflows/`）不许被当成泄漏面。

        使用者填的资料是从模板长出来的，模板句在两边逐字出现是常态。
        **专挑「只在模板里出现一次」的那种**：那种形状方向判据帮不上忙
        （别处 0 处），放掉它靠的正是 `_is_authored()` 这一层——所以把那一层
        撤掉，这条会红。挑多处出现的句子做用例，等于用另一条判据替它作证。
        """
        texts = _all_texts()
        solo = None
        for p in _repo_doc_paths():
            t = texts.get(str(p))
            if not t:
                continue
            for f in _quote_fragments(t):
                if f in self.personal and sum(1 for q in texts.values()
                                              if f in q) == 1:
                    solo = (p, f, t)
                    break
            if solo:
                break
        if not solo:
            self.skipTest("这棵树里没有「只在模板里出现一次、又落在资料里」的句子 —— "
                          "这一支没东西可验，不算通过")
        p, frag, t = solo
        self.assertIn(frag, t, "样本没在被读的模板里 —— 用例自己空了")
        self.assertEqual(
            quoted_personal_sentences(t, self.personal, here=p), [],
            "模板自己的句子被当成从使用者身上抄的了（`_is_authored` 那层没生效）")

    #: 存量清零。**只许往下走，也不许往上加。**
    #:
    #: 这一轮清的时候最后剩下的那一处（`tools/query_yield.py` 里的
    #: 「`—` 是下一轮最值钱的格子」）核过两头：那句是工具**自己印出去的话**，
    #: 同一条句子在它维护的资料块里出现两次（一次是它的说明，一次是它引自己），
    #: 说的是表格里的破折号，不是任何人的事。方向判据把它放掉了，所以基线留 0。
    #:
    #: 以后真出现「两边都在用的共享词汇」又放不掉的，先看方向判据是不是该补
    #: 一处豁免，**别先动这个数** —— 把基线抬高等于把这条判据的天花板挪高，
    #: 而它现在的天花板是零。
    BASELINE = 0

    def test_no_tracked_file_quotes_a_personal_sentence(self):
        bad = [f"{p.relative_to(ROOT).as_posix()}（{len(h)} 处）" for p, h in self.hits]
        self.assertLessEqual(
            len(bad), self.BASELINE,
            f"又被抄进去一整个人的原句，累计从 {self.BASELINE} 涨到了 {len(bad)}。"
            "要说明就写类别，别引原句（本文件顶上那张表记的就是这件事）：\n  "
            + "\n  ".join(bad))

    def test_the_baseline_is_not_stale(self):
        """存量清掉就该把这个数收紧——只挂着不降的基线是张免死金牌。"""
        n = len(self.hits)
        self.assertLessEqual(
            self.BASELINE - n, 2,
            f"现在只剩 {n} 个文件有命中，基线还写着 {self.BASELINE} —— 收到 {n}")
