# -*- coding: utf-8 -*-
"""工作流正文里的英文散文只许减少，不许回涨。

## 为什么要盯这个

`workflows/` 是给 AI 的执行手册。英文指令本身 AI 读得懂，所以这件事一直没人管——
**代价出在下游**：周围一整片英文指令，模型写「照着念给用户」的那几行时就往英文飘。

`tests/test_no_english_lines_spoken_to_the_user.py` 里记着四轮修补，每一轮都只治症状：

| 轮次 | 漏掉的 |
|---|---|
| 第二次扫 | `/job-expand` 的「How would you like to proceed?」 |
| 第三次扫 | `/job-add-template` 的整段总结 |
| 第四次扫 | `/job-setup` **第一屏**的三条路径说明（新用户看到的第一段字） |

而 2026-08-20 实测：英文指令最多的三个文件正是 **job-setup（123 行）·
job-expand（46）· job-add-template（45）**。**不是巧合，是同一个源头。**

那一轮还翻出两处**直接印给用户的英文**，都在输出模板的围栏里、现有守卫看不见：
`job-setup.md` 的「I will read these and cross-reference before proposing any changes.」
和一处「Which is correct?」。围栏里的字是要照着打印的——它们不是指令，是台词。

## 判据：预算表，只许降

一次翻完 14 个文件不现实（685 行），所以判据不是「必须为零」，是**不许回涨**：
每个文件记一个当前值，超了就红。翻完一个文件就把它的数字改小；
**改大要在这里说明理由**——那等于宣布往回走。

`job-setup.md` 剩的 2 行是 `cv/`、`[AVOID_KEYWORD_OR_PHRASE_1]` 这类纯标识符列表，
不是散文；判据按「≥6 个拉丁词、整行无汉字、不在围栏里」算，它们恰好卡在门槛上。

## 翻的时候会踩的三个坑（都是实测踩出来的）

**① 措辞要用仓库已有的那个说法，不是另造一个。**
`test_every_command_has_a_default` 的 `DEFAULT_PAT` 认的是「**没给任何参数**」。
2026-08-20 我在 `job-outcome` 写成「什么都没给」、`job-upskill` 写成「没给参数」、
`job-interview` 又写成「没给参数」——**同一个错犯了三次**，三次都被那条测试顶红。
**正确的修法是改措辞去对齐，不是放宽正则**：那条正则守的正是「裸命令的行为要写清楚」，
为了让翻译过关去放宽它，等于把守卫拆了。同类还有 `workflows/INDEX.md` 索引第四列的「不给参数时」。

**② 数据值不许翻。** 写进 CSV / JSON 的状态码与判定码是**契约**：
`applied` / `in_progress` / `hired` / `rejected` / `no response` / `offer declined` /
`interview_only` / `withdrawn`，以及 `new` / `ranked` / `skipped` / `expired` 和
`PASS` / `FAIL` / `FLAG`。翻完逐个数一遍——`job-outcome` 那次 8 个码一个不少。

**③ 按英文短语定位的测试会跟着红，那是它在尽责。**
标题改中文、冒号改全角，都会让 `t.index("## Step 4:")` 这类锚点落空。
**改锚点，不要改判据**——`test_rank_documents_what_consumers_read` 的说明里写得很清楚：
「规范写在哪一步是有意义的」，把它松成全文搜索就白守了。
2026-08-20 这样跟进过 20 多处，每一处守的东西一个字没动。


## 围栏分两种，只有一种可以不管

带语言标签的围栏（```bash / ```json / ```markdown）里装的是命令与数据示例，
英文是它们本来的样子，不计入。**裸围栏（``` 后面什么都不写）不一样**——
这个仓库用它装**整段派给子代理的提示**，那是纯指令散文。

2026-08-20 实测撞到：`job-apply.md` 的审稿者提示块整个在一个裸围栏里，
**17 行英文，主判据一行都没数到**——而块里恰恰是最要紧的几条
（信任边界、调研只能从公司官网出发、事实落地核查的尺度）。
更隐蔽的是里面还嵌着 ```json，把奇偶数弄反，连块外的几行也一起漏了。

所以第二个计数器 `FENCE_BUDGET` 专盯裸围栏，判据同上、同样只许降。
带标签的围栏仍然不管——那里的台词由 `test_workflow_output_templates.py` 与
`test_no_english_lines_spoken_to_the_user.py` 负责。
"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import _entries  # noqa: E402  （只用来取「哪些是生成的壳」这份名册）

WF = ROOT / "workflows"

CJK = re.compile("[一-鿿]")

#: 每个文件当前的英文散文行数。**只许改小。**
#: 2026-08-20 一天之内把 14 份工作流全部翻完：**722 → 21**。
#:
#: 剩下的 21 行**一行散文都没有**，全是翻不得的东西——路径模板、占位符列表、
#: Gmail 搜索式、CSV 字段名。每一处都在表里注了理由。
#:
#: 翻译过程本身翻出四样东西（比译文更值钱，都已单独修掉并留了守卫）：
#:   · 两处**直接印给用户的英文**，藏在输出模板围栏里（`job-setup`）
#:   · 一整块**派给子代理的提示**从没被数过（`job-apply` 的裸围栏，17 行）
#:   · 一条**写坏了的断言**：`assertIn("two", t.lower() + "两次")` 只验了英文那一款
#:   · 一条**因翻译而失效的排除逻辑**：`AGENT_PROMPT` 只认 `^You are`
#:
#:
#: 翻 `job-outcome.md` 时有一条额外的纪律：**状态码是写进 CSV 的数据值，一个都不许翻**
#: （`applied` / `in_progress` / `hired` / `rejected` / `no response` /
#: `offer declined` / `interview_only` / `withdrawn`）。翻完逐个数过，一个不少。
#:
#:   INDEX.md        —— 实测 **0**（2026-09-29 建档当日复算）：索引表第三列的英文本来就该是
#:                      **要照着敲的原文**（`/job-scrape broad`、`--no-rank` 这类），
#:                      它们全在反引号里，判据的 `_CODE` 一步就把它们剥掉。留数 0 不是
#:                      「碰巧」，是**上限**：哪天有人把命令原文翻成中文、或把反引号剥了
#:                      写进散文，这一格先红——那时候修的是正文，不是这张表。
BUDGET = {
    "INDEX.md": 0,
    "job-add-portal.md": 0,
    "job-add-template.md": 0,
    "job-apply.md": 0,
    "job-auto.md": 0,
    "job-cv.md": 0,
    "job-dashboard.md": 0,
    "job-expand.md": 0,
    "job-gmail-sync.md": 0,
    "job-html-report.md": 0,
    "job-interview.md": 0,
    "job-notion-sync.md": 0,
    "job-offer.md": 0,
    "job-outcome.md": 0,
    "job-rank.md": 0,
    "job-reset.md": 0,
    "job-refresh.md": 0,
    "job-resume.md": 0,
    "job-scrape.md": 0,
    "job-setup.md": 0,
    "job-upskill.md": 0,
    "job-user.md": 0,
    "reference/03-writing-style.md": 0,
    "reference/04-job-evaluation.md": 0,
    "reference/05-cv-templates.md": 0,
    "reference/06-outreach-templates.md": 0,
    "reference/07-interview-prep.md": 0,
    "reference/cdp-portals.md": 0,
    "reference/search-queries.md": 0,
}


_CODE = re.compile(r"`[^`]*`")
_PLACEHOLDER = re.compile(r"\[[A-Z_0-9]+\]")
_URL = re.compile(r"https?://\S+")


def _prose_only(line: str) -> str:
    """剥掉反引号里的代码、`[PLACEHOLDER]`、URL 与路径分隔符。

    **不剥这些就会把中文句子误判成英文**：
    「（`tests/test_bash_permissions_use_the_prefix_form.py` 与 `lint_skills.py`
    现在都盯着）。」——一句纯中文，剥之前数出 12 个「拉丁词」。
    """
    t = _CODE.sub(" ", line)
    t = _PLACEHOLDER.sub(" ", t)
    t = _URL.sub(" ", t)
    return re.sub(r"[\[\]<>/\\.$-]", " ", t)


def _is_english_prose(line: str) -> bool:
    """剥完之后：≥6 个拉丁词，且拉丁词比汉字多。

    ## 为什么不是「整行没有汉字」

    那一版漏掉一整类：**英文为主、夹着几个中文词**的行。实测漏网的例子——
    `job-scrape.md` 的「If the user picks a number, run `/job-apply <该职位的 URL
    或粘贴 JD>` — that is the canonical application path…」：整段英文指令，
    只因为占位符里有五个汉字就被整行跳过。

    `lat > cjk` 这个比较是分界线：中文句子里塞再多路径，剥完代码之后拉丁词也归零；
    英文句子里夹一个中文词，拉丁词仍然远多于汉字。
    """
    t = _prose_only(line)
    return len(re.findall(r"[A-Za-z]{2,}", t)) >= 6 and \
        len(re.findall(r"[A-Za-z]{2,}", t)) > len(CJK.findall(t))


def _walk(text: str, want_bare_fence: bool):
    """按**外层围栏**遍历，不用奇偶开关。

    奇偶会被嵌套围栏带偏：`job-apply.md` 的提示块里套着 ```json，
    `job-scrape.md` 的输出模板里套着表格与说明。翻到最后奇偶正好反过来，
    **围栏外的真英文被当成围栏内跳过**——2026-08-20 实测因此少报了 15 行，
    而少报比没有判据更坏：它让人以为已经清干净了。

    只有**裸 ```** 闭合外层；带 info string 的一律当作嵌套开头。
    """
    out, depth, tag = [], 0, None
    for i, ln in enumerate(text.splitlines(), 1):
        st = ln.strip()
        if st.startswith("```"):
            info = st.lstrip("`").strip()
            if depth == 0:
                depth, tag = 1, info
            elif info == "":
                depth, tag = 0, None
            continue
        inside = depth > 0
        if want_bare_fence:
            if not inside or tag:
                continue
        elif inside:
            continue
        if st and _is_english_prose(st):
            out.append((i, st))
    return out


def english_prose_lines(text: str) -> list:
    """围栏之外的英文散文。"""
    return _walk(text, want_bare_fence=False)


def english_prose_in_bare_fences(text: str) -> list:
    """**裸**围栏（``` 后无语言标签）里的英文散文。

    带 ```bash / ```json 标签的跳过：那是命令与数据示例。
    裸围栏不一样——这个仓库用它装**整段派给子代理的提示**，那是纯指令散文。

    ⚠️ ```markdown 归下面那条管，不归这里 —— 见 `english_prose_in_doc_fences`。
    """
    return _walk(text, want_bare_fence=True)


def english_prose_in_doc_fences(text: str) -> list:
    """```markdown 围栏里的英文散文。

    ## 为什么它不能跟 ```bash 一起被跳过

    上面那条的原话是「带标签的（```bash / ```json / ```markdown）跳过：
    那是命令与数据示例」。**对 bash 成立，对 markdown 不成立**：这个仓库的
    ```markdown 围栏装的是**给用户读的文档模板**（归档 `job-outcome.md` 的格式、
    自定义模板的激活块），那是散文，不是代码。

    代价实测（2026-08-21 通读时抓到）：翻译**停在了围栏边界**。同一个块里
    `# 投递结果` `## 走到了哪几关` `- [ ] 在线测评` 全是中文，只剩
    `**Status:**` `**Date resolved:** … <- only when resolved` 两行英文；
    `job-add-template.md` 的激活块同样只剩 `**Page limit:**` 和一句
    `copy any class/font files …` 的尾巴。合计 11 处，跨 4 份工作流。

    ## 召回上限（**别把绿灯读成「清干净了」**）

    判据沿用 `_is_english_prose`（剥完 ≥6 个拉丁词且多于汉字），所以
    **中英混排的短尾巴抓不到**——`**Page limit:**` 只有两个英文词。
    拿今天修掉的 4 条原文回测，抓回 2 条。剩下那半只有通读能撞上。
    写在这里是因为「少报比没有判据更坏」：说清楚它量得到哪，绿灯才有意义。
    """
    out, depth, tag = [], 0, None
    for i, ln in enumerate(text.splitlines(), 1):
        st = ln.strip()
        if st.startswith("```"):
            info = st.lstrip("`").strip()
            if depth == 0:
                depth, tag = 1, info
            elif info == "":
                depth, tag = 0, None
            continue
        if depth > 0 and (tag or "").lower() in ("markdown", "md")                 and st and _is_english_prose(st):
            out.append((i, st))
    return out


#: ```markdown 围栏里剩下的英文行。**只许改小。**
#:
#: 留数的都不是散文，是模板里本来就该是英文的东西：
#:   job-add-template —— `typst compile` / `xelatex -interaction=nonstopmode` 编译命令
#:   job-outcome      —— 状态**值**（`in_progress | hired | …`），机器词汇，
#:                       权威在 `tools/tracker.py` 的 `NEXT`（标签已译成中文，值不译）
DOC_FENCE_BUDGET = {
    "job-add-template.md": 2,
    "job-outcome.md": 1,
}

#: 裸围栏里的英文散文。**只许改小。**
#:
#: 留数的这几个不是散文，是围栏里本来就该是英文/路径的东西：
#:   job-add-portal —— `Bash(node …cli.ts:*)` 权限串（契约）
#:   job-apply      —— `<OUTREACH_DRAFT file=…>` 标签、JSON 键、一条 `cp` 命令
#:   job-auto / job-reset —— 中文行里夹着长路径，剥完仍数出 6 个「词」
#:   job-outcome    —— CSV 表头
FENCE_BUDGET = {
    "job-add-portal.md": 2,
    "job-add-template.md": 0,
    "job-apply.md": 3,
    "job-auto.md": 1,
    "job-cv.md": 0,
    "job-dashboard.md": 0,
    "job-expand.md": 0,
    "job-gmail-sync.md": 0,
    "job-html-report.md": 0,
    "job-interview.md": 0,
    "job-notion-sync.md": 0,
    "job-offer.md": 0,
    "job-outcome.md": 1,
    "job-rank.md": 0,
    "job-reset.md": 1,
    "job-refresh.md": 0,
    "job-resume.md": 0,
    "job-scrape.md": 0,
    "job-setup.md": 0,
    "job-upskill.md": 0,
    "job-user.md": 0,
    "reference/03-writing-style.md": 0,
    "reference/04-job-evaluation.md": 0,
    "reference/05-cv-templates.md": 0,
    "reference/06-outreach-templates.md": 0,
    "reference/07-interview-prep.md": 0,
    "reference/cdp-portals.md": 0,
    "reference/search-queries.md": 0,
}

# ---------------------------------------------------------------------------
# 第三个计数器：**连续的英文句片**，不看整行中英比例
# ---------------------------------------------------------------------------
#
# 上面 `_is_english_prose` 的判据是「≥6 个拉丁词 **且** 拉丁词 > 汉字数」。
# 那个 `>` 是上一轮为了接住「英文为主、夹几个中文词」的行加的，但它同时留下了
# **反过来的那一类**：中文占多数、里面嵌着一整句英文指令。2026-08-20 实测漏掉 20 处，
# 其中最重的一条在 `job-rank.md`（批量打分的正文）：
#
#     - Pass each agent everything it needs **inline in the prompt** - the job list
#       (title, company, URL) and a compact rubric … —— **这份枚举必须与 …** …
#       Do **not** make agents re-read the profile files.
#
# 整条英文指令，只因为同一行里中文更多就被放过了。另外两种漏法：
# 接在中文句尾的英文句（`… 被哪些筛选排除。 Any 未知 hard gate a job carries is …`），
# 以及不足 6 词的英文小标题（`Rules for the presentation:`）。
#
# **所以这一条不数行，数「连续 ≥5 个英文词的片段」**——它对整行的中英比例免疫，
# 也不受 6 词下限限制（下限落在片段上，不落在行上）。
_RUN = re.compile(
    r"(?:\b[A-Za-z][A-Za-z'’\-]*\b[ ,.:;()\"'/\-]{1,3}){4,}\b[A-Za-z][A-Za-z'’\-]*\b")


def english_runs(text: str) -> list:
    """围栏外，连续 ≥5 个英文词的片段。返回 (行号, 片段)。"""
    out = []
    for i, ln in _walk_lines_outside_fences(text):
        for m in _RUN.finditer(_prose_only_keep_words(ln)):
            if len(m.group(0).split()) >= 5:
                out.append((i, m.group(0).strip()))
    return out


def _prose_only_keep_words(line: str) -> str:
    """跟 `_prose_only` 同样剥代码/占位符/URL，但**不打散路径分隔符**。

    `_prose_only` 会把 `/` `.` `-` 换成空格，那会把 `a/b/c.d-e` 这种路径
    炸成一串「词」，凑够 5 个就误报。这里只剥不炸。
    """
    t = _CODE.sub(" ", line)
    t = _PLACEHOLDER.sub(" ", t)
    t = _URL.sub(" ", t)
    return re.sub(r"\]\([^)]*\)", " ", t)


def _walk_lines_outside_fences(text: str):
    """跟 `_walk` 同一套外层围栏规则，但把原始行交出来（不做英文判定）。"""
    depth = 0
    for i, ln in enumerate(text.splitlines(), 1):
        st = ln.strip()
        if st.startswith("```"):
            info = st.lstrip("`").strip()
            if depth == 0:
                depth = 1
            elif info == "":
                depth = 0
            continue
        if depth == 0 and st:
            yield i, ln


#: 英文句片的留数。**只许改小。**
#:
#: 这几处**按规矩就该是英文**，翻了反而是错的：
#:   job-add-template —— 引用模板块自己写的那句 `where this block conflicts …`
#:   job-apply        —— ① 引用改掉之前的旧写法 `strong fit / moderate fit / weak fit`
#:                       ② 字体名 `Noto Sans SC / Noto Serif SC`
#:   job-gmail-sync   —— 拒信要匹配的**英文原句**（数据，不是散文）
#:   job-interview    —— 引用改掉之前的四个英文选项
#:   job-outcome      —— ① 状态码 `hired / rejected / …`（契约）② 文件名
#:   job-setup        —— 两处「这条原来写的是『…』」的引用
#:
#: **引用旧写法不许翻**：翻了就追不回当初错在哪，而那正是这些血泪注解存在的理由。
#:
#: ## 「只许改小」有一个例外，而它必须写下来
#:
#: `job-gmail-sync` 2026-08-24 从 1 调到 **3**。这是这份预算第一次往上调，
#: 所以判据要说清 —— 否则下次谁都能拿「我这条也是数据」推上去：
#:
#: - 那一格的豁免理由本来就是「**拒信要匹配的英文原句**（数据，不是散文）」；
#: - 新增的两句 `keep your resume on file` /
#:   `we'll be in touch if something opens up` 是**同一张表、同一列**里
#:   同一类东西 —— 那张表按设计中英双列（它自己的说明写着「这张表原来只有
#:   英文短语……一封中文拒信永远匹配不上」）；
#: - 只补中文半边会让新那一行成为整张表里唯一没有英文列的一行。
#:
#: **这条例外只对「同一张表里同类的匹配串」成立。** 散文一个字都没多 ——
#: 那才是这个棘轮真正拦的东西。
#:
#:   INDEX.md        —— 实测 **0**：索引表里要照敲的英文（`/job-scrape broad`、`health`
#:                      这类）全在反引号里，`_prose_only` 一步就剥掉，凑不出 ≥5 个连续词。
#:                      留数 0 同样是上限不是巧合——翻了，或把反引号剥了，这一格先红。
RUN_BUDGET = {
    "INDEX.md": 0,
    "job-add-portal.md": 0,
    "job-add-template.md": 1,
    "job-apply.md": 2,
    "job-auto.md": 0,
    "job-cv.md": 0,
    "job-dashboard.md": 0,
    "job-expand.md": 0,
    "job-gmail-sync.md": 3,
    "job-html-report.md": 0,
    "job-interview.md": 1,
    "job-notion-sync.md": 0,
    "job-offer.md": 0,
    "job-outcome.md": 2,
    "job-rank.md": 0,
    "job-reset.md": 0,
    "job-refresh.md": 0,
    "job-resume.md": 0,
    "job-scrape.md": 0,
    "job-setup.md": 2,
    "job-upskill.md": 0,
    "job-user.md": 0,
    "reference/03-writing-style.md": 0,
    "reference/04-job-evaluation.md": 0,
    "reference/05-cv-templates.md": 0,
    "reference/06-outreach-templates.md": 0,
    "reference/07-interview-prep.md": 0,
    "reference/cdp-portals.md": 0,
    "reference/search-queries.md": 0,
}


#: `workflows/` **之外**每份 md 的英文句片留数。**只许改小。**
#:
#: 这一张是 2026-08-20 晚补的，起因是 `templates/README.md`——**上半截英文、下半截中文**
#: 的半成品，用户跑 `/job-add-template` 就会读到它，而当时**没有任何判据在管
#: `workflows/` 以外的 md**。三个计数器都只扫工作流，它就这么活了下来。
#:
#: 留数的理由（同样只有三类）：
#:   .claude/skills/*  —— `allowed-tools:` 权限串（契约，翻了就失效）
#:   .github/PULL_REQUEST_TEMPLATE.md —— 一条要照敲的命令
#:   AGENTS.md         —— 被当作**反面例子引用**的那串英文码（SCRAPE / RANK / …）
#:   SETUP.md          —— 字体名 ×2，以及 Chrome 界面上那个复选框的**英文原文**
#:                        （用户要照着它在浏览器里找，翻了反而找不到）
#:                        2026-09-29 Task 9 往 §7 粘了一段要照着粘的 agy 权限片段，
#:                        留数**没动**（实测仍是 3）：那一段在 ```text 围栏里，
#:                        而 `english_runs` 只数围栏外的散文。要让它进计数器，
#:                        先得把围栏请掉 —— 那也正是这段该继续待在围栏里的理由。
#:   resume/ cover_letter/ README —— 字体名
DOC_RUN_BUDGET = {
    ".github/PULL_REQUEST_TEMPLATE.md": 1,
    "AGENTS.md": 1,
    "SETUP.md": 3,
    "cover_letter/README.md": 1,
    "resume/README.md": 1,
}

#: 技能壳：每份恰好一段英文，就是 `allowed-tools:` 那一行 —— 那是**契约值**
#: （权限串），正是这张表的说明里「可以留」三类中的第一类。
#:
#: 原来这里是三个壳名手写的（job-scrape 还写着 2，因为它带着两段解释散文）。
#: 2026-09-29 `tools/gen_entries.py` 把 21 条命令的壳同时落到 `.claude/` 与
#: `.agents/` 两处之后，手写名册只有两个下场：留着 → 40 份新壳全按预算 0 报，
#: 而红的理由是**生成器正常工作**；把它们一份份抄进表 → 又一处会与正本飘的抄件
#: （`AGENTS.md`「一条规则只贴在一个写手身上」）。名册因此改读
#: `_entries.shell_names()`，预算仍是 1，判据一条没松：
#: 壳里真多出散文英文（比如有人手工改了一份生成壳又没跑生成器），
#: 2 > 1 当场红，而 `tests/test_generated_entries_are_current.py` 也会一起红。
#:
#: 只登记**盘上存在**的那些：`.agents/` 那一份在 Task 4 入库前不跟随 clone，
#: 给不存在的路径留数就是 `test_the_budget_names_no_ghost` 要抓的幽灵。
for _fam in _entries.SHELL_FAMILIES:
    for _name in _entries.shell_names():
        _rel = f"{_fam}/skills/{_name}/SKILL.md"
        if (ROOT / _rel).is_file():
            DOC_RUN_BUDGET[_rel] = 1


def _shipped_markdown():
    """会进下一次提交的 md：已跟踪的，加上未跟踪但没被 ignore 的。

    用 `git ls-files` 而不是 `rglob`：后者会把 `node_modules/` 和构建产物一起扫进来，
    而那些不是这个仓库要负责的字。
    """
    import subprocess
    out = []
    for args in (["git", "ls-files", "*.md"],
                 ["git", "ls-files", "--others", "--exclude-standard", "*.md"]):
        r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8")
        out += r.stdout.split()
    return sorted({f for f in out if "node_modules" not in f})


class ShippedDocsAreChineseToo(unittest.TestCase):
    """`workflows/` 之外的 md 同样不许留英文句子。

    判据与工作流那三条同源（复用 `english_runs`），只是扫描范围不同——
    **一个概念一个实现**，不另写一套检测。
    """

    def test_every_shipped_doc_is_within_budget(self):
        over = []
        for rel in _shipped_markdown():
            if rel.startswith("workflows/"):
                continue                      # 那边由 RUN_BUDGET 管
            f = ROOT / rel
            if not f.is_file():
                continue
            hits = english_runs(f.read_text(encoding="utf-8"))
            budget = DOC_RUN_BUDGET.get(rel, 0)
            if len(hits) > budget:
                shown = "；".join(t for _, t in hits[:3])
                over.append(f"{rel}: {len(hits)} 段 > 预算 {budget} —— {shown}")
        self.assertEqual(
            over, [],
            "会进提交的 md 里英文句子变多了。**只有三类可以留**：契约值（权限串/"
            "状态码/字段名/文件名/字体名）、要照着找或照着敲的英文原文（界面标签、命令）、"
            "被当作反面例子引用的英文：\n  " + "\n  ".join(over))

    def test_the_budget_names_no_ghost(self):
        """留数表里不许有已经不存在的文件——否则它在替一个幽灵放行。"""
        gone = sorted(rel for rel in DOC_RUN_BUDGET if not (ROOT / rel).is_file())
        self.assertEqual(gone, [], f"DOC_RUN_BUDGET 里这些文件已经不在了：{gone}")

    def test_the_scan_actually_reaches_the_docs(self):
        """对照用例：`git ls-files` 真的列出了东西 —— 否则上面那条恒绿。"""
        found = _shipped_markdown()
        self.assertGreaterEqual(
            len(found), 40,
            f"只扫到 {len(found)} 份 md —— 大概是 git 没跑起来，而不是仓库真的只剩这么几份")


#: 整行没有汉字、剥完仍有 ≥2 个英文词的行 —— 每份文件允许几条。**只许改小。**
#:
#: 留数的都不是散文：
#:   job-expand      —— `### 1b. documents/linkedin/` 这类**目录名标题**
#:   job-html-report —— 配色表的**内部键**（`- Active: #3b82f6`）。
#:                      同一份文件第 174 行明写「都不该出现 `Active` /
#:                      `Interview` 这类内部码」——它们不上屏，是键。
BARE_LABEL_BUDGET = {
    "job-expand.md": 3,
    "job-html-report.md": 5,
}


class EnglishProseOnlyShrinks(unittest.TestCase):

    def test_every_workflow_is_within_budget(self):
        over = []
        for rel, budget in sorted(BUDGET.items()):
            f = WF / rel
            if not f.is_file():
                continue                      # 文件删了不是这条测试的事
            n = len(english_prose_lines(f.read_text(encoding="utf-8")))
            if n > budget:
                over.append(f"{rel}: {n} 行 > 预算 {budget}")
        self.assertEqual(over, [],
                         "工作流里的英文散文变多了 —— 它是「英文漏到用户面前」的上游"
                         "（见本文件说明里那四轮）：\n  " + "\n  ".join(over))

    def test_the_scan_actually_reaches_the_workflows(self):
        """对照用例：扫描真的够到了文件 —— 否则下面几条全是恒绿。

        2026-08-20 实测：把 `Path.rglob` 打成空之后，本文件 6 条全绿。
        `test_the_budget_covers_every_workflow` 算的是 `on_disk - BUDGET`，
        **扫不到文件时那个差集当然是空的**——判据的本意是「新工作流也要进表」，
        扫不到就等于不设防。

        这正是本文件一直在治的那个病的**元层**：判据自己漏，报出来的数偏小，
        而**少报比没有判据更坏**——它让人以为已经清干净了。
        所以这里钉一个下限：`workflows/` 下的 md 文件不该少于 20 个
        （实测 29 个：21 条命令 + INDEX + 7 份 reference）。
        """
        found = list(WF.rglob("*.md"))
        self.assertGreaterEqual(
            len(found), 20,
            f"只扫到 {len(found)} 份工作流 —— 判据大概是够不到文件了，"
            "而不是仓库真的只剩这么几份")

    def test_the_budget_covers_every_workflow(self):
        """新加的工作流也要进预算表，否则它可以整份是英文而无人察觉。"""
        on_disk = {str(f.relative_to(WF)).replace("\\", "/")
                   for f in WF.rglob("*.md")}
        missing = sorted(on_disk - set(BUDGET))
        self.assertEqual(missing, [],
                         f"这些工作流不在预算表里，等于不设防：{missing}")

    def test_setup_is_actually_translated(self):
        """`job-setup.md` 是新用户看到的第一个流程，它必须已经翻完。

        单独钉住，不只靠上面那张表：预算表可以被改大，这一条不行——
        它是本轮翻译的落点，也是那四轮英文泄漏里代价最大的一个文件。
        """
        n = len(english_prose_lines((WF / "job-setup.md").read_text(encoding="utf-8")))
        self.assertLessEqual(n, 2, "job-setup.md 又出现英文散文了")

    def test_bare_fences_are_within_budget(self):
        """派给子代理的提示块也要翻 —— 它是指令，不是命令示例。"""
        over = []
        for rel, budget in sorted(FENCE_BUDGET.items()):
            f = WF / rel
            if not f.is_file():
                continue
            n = len(english_prose_in_bare_fences(f.read_text(encoding="utf-8")))
            if n > budget:
                over.append(f"{rel}: {n} 行 > 预算 {budget}")
        self.assertEqual(over, [],
                         "裸围栏里的英文散文变多了 —— 那里装的是派给子代理的提示，"
                         "不是命令示例：\n  " + "\n  ".join(over))

    def test_no_bare_english_labels_are_left(self):
        """整行英文的小标签同样是漏译 —— 而前三个计数器一个都够不到它们。

        ## 它们为什么活到了今天

        这份文件已有三个计数器，门槛分别是：`_is_english_prose` 要 **≥6 个拉丁词
        且多于汉字**，`english_runs` 要 **≥5 个连续英文词**。
        而漏掉的是这种：

            Optional arguments:          ← 2 个词
            Then ask:                    ← 2 个词
            **If profile was reset:**    ← 4 个词
            - **Total applications**     ← 2 个词

        **短就躲得过。** 2026-08-21 通读 `/job-scrape` 时先撞见 `Optional arguments:`
        （它正压在一串中文参数说明的上面），顺着扫出 **24 处，跨 10 份工作流**——
        `job-add-template.md` 里 `- **Type:**`、`- **Page limit:**` 甚至和
        `- **字体：**` 同在一个列表里。

        ## 判据

        整行不含汉字、剥掉行内代码/链接/路径之后仍有 ≥2 个英文词 → 记一条。
        表格行、块引用、图片行跳过。留数按 `BARE_LABEL_BUDGET`。
        """
        import re

        cjk = re.compile(r"[\u4e00-\u9fff]")
        over = []
        for f in sorted(WF.rglob("*.md")):
            rel = f.relative_to(WF).as_posix()
            hits = 0
            for _i, ln in _walk_lines_outside_fences(f.read_text(encoding="utf-8")):
                st = ln.strip()
                if not st or cjk.search(st) or st.startswith(("|", ">", "!")):
                    continue
                bare = _prose_only_keep_words(st)
                # **门槛是 1 个词，不是 2。** 第一版取 2，于是 `Rules:` 这种
                # **单词独占一行**的标签从两条判据中间漏了过去：
                # 这一条嫌它词太少，下一条嫌它行里没有汉字。
                # 2026-08-21 通读 `/job-add-template` 撞见，降到 1 之后残留为 0。
                if len(re.findall(r"[A-Za-z][A-Za-z'-]+", bare)) >= 1:
                    hits += 1
            budget = BARE_LABEL_BUDGET.get(rel, 0)
            if hits > budget:
                over.append(f"{rel}: {hits} 行 > 预算 {budget}")
        self.assertEqual(
            over, [],
            "这些文件里有整行英文的小标签 —— 短到躲过了前三个计数器，"
            "但它压在中文正文里一样刺眼：" + " · ".join(over))

    def test_no_english_label_heads_a_chinese_line(self):
        """行首的英文标签 + 中文内容，同样是漏译 —— 而前四个计数器都够不到。

        ## 这是同一个盲区的第三种形态

        - `_is_english_prose`：要 ≥6 个拉丁词 → `Example:` 是 1 个词，躲过；
        - `english_runs`：要 ≥5 个连续英文词 → 同样躲过；
        - `test_no_bare_english_labels_are_left`：要**整行不含汉字** →
          而这一类的定义就是「英文标签 + **中文**内容」，天生躲过。

        2026-08-21 通读 `/job-gmail-sync` 撞见 `Example: `newer_than:30d …``，
        顺着扫出 8 处，其中最要紧的是 `job-setup.md` 里的 **`Path A/B/C`** ——
        那是**打招呼时直接给用户看的三条路线**，而同一份文件的小节标题
        写的是「## 路线 A」。**同一个东西两个名字，英文那个偏偏在用户眼前。**

        还有一处是**上午刚修过的那个列表**：`job-add-template.md` 的
        `- **Type:**` / `- **Page limit:**` 当时改了，`- **Engine:**` 没改 ——
        因为它那一行带中文（`` `typst`（默认） ``），逃过了「整行英文」的扫描。
        **同一个列表，两次扫描，两种漏法。**

        ## 判据

        剥掉列表符号与加粗之后，行首是 `英文单词[ 英文单词]*` 加冒号，
        且整行含汉字 → 记一条。留数为 0。
        """
        import re

        pat = re.compile(
            r"^(?:[-*]\s*|\d+\.\s*|>\s*)?(?:\*\*)?([A-Z][A-Za-z ]{2,24}?)"
            r"(?:\*\*)?\s*[:：]")
        cjk = re.compile(r"[\u4e00-\u9fff]")
        bad = []
        for f in sorted(WF.rglob("*.md")):
            for i, ln in _walk_lines_outside_fences(f.read_text(encoding="utf-8")):
                st = ln.strip()
                m = pat.match(st)
                if m and cjk.search(st):
                    bad.append(f"{f.name}:{i} 「{m.group(1).strip()}：」")
        self.assertEqual(
            bad, [],
            "这些行用英文标签领起一句中文 —— 前四个计数器都够不到它们："
            + " · ".join(bad))

    def test_step_headings_use_one_colon_per_file(self):
        """一份工作流里的 Step 标题只许用一种冒号 —— 混用是漏改的痕迹。

        ## 判据为什么是「一份文件内一致」，不是「全仓都用全角」

        实测（2026-08-21）全仓四份文件**整份**用半角
        （`job-add-portal` / `job-dashboard` / `job-offer` / `job-resume`），
        它们自洽，只是另一套约定；而按标点规则「**只在两侧是中文时才换全角**」，
        `Step 0: 解析参数` 的左边是数字，本来就不该被换。**两种都说得通。**

        说不通的是**同一份文件里两种都有**：`job-scrape.md` 九个 Step 标题里
        八个全角、只有 `### Step 4.5:` 是半角；`job-upskill.md` 九个里也恰好
        只有 `## Step 4.5:` 是半角。两处都是后补的小步，**补的时候没看邻居**。
        """
        bad = []
        for f in sorted(WF.rglob("*.md")):
            heads = [ln for ln in f.read_text(encoding="utf-8").splitlines()
                     if re.match(r"^#{2,4} Step [0-9.]+[:：]", ln)]
            if not heads:
                continue
            half = [h for h in heads if re.match(r"^#{2,4} Step [0-9.]+: ", h)]
            full = [h for h in heads if re.match(r"^#{2,4} Step [0-9.]+：", h)]
            if half and full:
                few = half if len(half) < len(full) else full
                bad.append(f"{f.name}: {len(half)} 半角 / {len(full)} 全角"
                           f"，少数那边是 {[h[:26] for h in few]}")
        self.assertEqual(
            bad, [],
            "这些文件的 Step 标题混用了两种冒号 —— 补新步骤时没看邻居："
            + " · ".join(bad))

    def test_doc_fences_are_within_budget(self):
        """```markdown 围栏里装的是给用户读的文档模板，同样要翻。

        **扫全部工作流，不只扫有预算的那几份** —— 只遍历预算表的话，
        新加一份文件就天然全绿（同文件里 `DOC_RUN_BUDGET` 已经是这个写法）。
        """
        over = []
        for f in sorted(WF.rglob("*.md")):
            rel = f.relative_to(WF).as_posix()
            budget = DOC_FENCE_BUDGET.get(rel, 0)
            n = len(english_prose_in_doc_fences(f.read_text(encoding="utf-8")))
            if n > budget:
                over.append(f"{rel}: {n} 行 > 预算 {budget}")
        self.assertEqual(
            over, [],
            "```markdown 围栏里的英文变多了 —— 那里是文档模板，不是命令示例；"
            "翻译最容易停在围栏边界：" + " · ".join(over))

    def test_the_doc_fence_check_can_fire(self):
        """变异内建：```markdown 要认，```bash 不认，纯中文模板不许误报。"""
        eng = ('- <pitfall and its fix, or "none recorded">, '
               "copy any class or font files into the output directory")

        def fence(tag, body):
            return "\n".join(["```" + tag, body, "```", ""])

        self.assertTrue(english_prose_in_doc_fences(fence("markdown", eng)),
                        "markdown 围栏里的英文没被认出来")
        self.assertFalse(english_prose_in_doc_fences(fence("bash", eng)),
                         "bash 围栏被算进来了 —— 那里本来就该是英文命令")
        self.assertFalse(
            english_prose_in_doc_fences(
                fence("markdown", "# 投递结果\n- [ ] 在线测评")),
            "中文模板被误报了")

    def test_english_runs_are_within_budget(self):
        """中文行里嵌着的英文句子同样算漏译 —— 这一条不看整行的中英比例。

        2026-08-20 实测：另外两个计数器都报 0 的时候，这一条扫出 20 处，
        最重的一条是 `job-rank.md` 里整条派活指令（「Pass each agent everything
        it needs …」）。**判据自己漏，比没有判据更坏**——它让人以为已经翻完了。
        """
        over = []
        for rel, budget in sorted(RUN_BUDGET.items()):
            f = WF / rel
            if not f.is_file():
                continue
            hits = english_runs(f.read_text(encoding="utf-8"))
            if len(hits) > budget:
                shown = "；".join(t for _, t in hits[:3])
                over.append(f"{rel}: {len(hits)} 段 > 预算 {budget} —— {shown}")
        self.assertEqual(
            over, [],
            "中文行里的英文句子变多了。**只有三类可以留**：引用改掉之前的旧写法、"
            "契约值（状态码/字段名/文件名/字体名）、要匹配的英文原文。"
            "其余一律翻：\n  " + "\n  ".join(over))

    def test_the_run_budget_covers_every_workflow(self):
        """新工作流也要进这张表，否则它天生免检。"""
        on_disk = {
            str(f.relative_to(WF)).replace("\\", "/")
            for f in WF.rglob("*.md")
        }
        missing = sorted(on_disk - set(RUN_BUDGET))
        self.assertEqual(missing, [],
                         f"这些工作流不在 RUN_BUDGET 里，等于不设防：{missing}")

    def test_the_run_counter_can_fail(self):
        """变异内建：要认得出嵌在中文里的英文句，也不能把零星英文词误报。"""
        mixed = "这一段是中文，但是 pass each agent everything it needs inline 然后继续。"
        self.assertEqual(len(english_runs(mixed)), 1, "中文行里的英文句没认出来")

        tail = "先想清楚它在面板哪个区。 Any gate a job carries is noted inline here."
        self.assertEqual(len(english_runs(tail)), 1, "接在中文句尾的英文句没认出来")

        # 零星专有名词不该报：不足 5 个连续英文词
        for ok in ("用 Claude Code 跑一遍就行。",
                   "字段名是 Notion MCP 那一套，别翻。",
                   "见 `tests/test_cli_contract.py` 的说明。"):
            with self.subTest(line=ok):
                self.assertEqual(english_runs(ok), [], f"零星英文词被误报：{ok}")

    def test_the_bare_fence_counter_can_fail(self):
        """变异内建：要认得出裸围栏，也不能把带标签的围栏算进来。"""
        bare = "\n".join(["```", "Plenty of English words inside a bare fence here.", "```"])
        tagged = "\n".join(["```bash", "node cli.ts search --query x --location y", "```"])
        self.assertEqual(len(english_prose_in_bare_fences(bare)), 1, "裸围栏没认出来")
        self.assertEqual(len(english_prose_in_bare_fences(tagged)), 0, "带标签的围栏被算进来了")

    def test_the_counter_can_fail(self):
        """变异内建：判据要认得出英文散文，也不能把中文行或围栏里的命令当英文。"""
        sample = "\n".join([
            "This line is unmistakably English prose with plenty of words.",
            "这一行是中文，不该被算进去。",
            "```",
            "node .agents/skills/liepin-search/cli/src/cli.ts search -q x -l y",
            "```",
            "`cv/`, `linkedin/`, `diplomas/`",
        ])
        hits = english_prose_lines(sample)
        self.assertEqual(len(hits), 1, f"判据认错了：{hits}")
        self.assertIn("unmistakably", hits[0][1])


if __name__ == "__main__":
    unittest.main()
