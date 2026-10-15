#!/usr/bin/env python3
"""预筛：用**已经存下来的字段**淘汰明显不合的职位，一个 JD 都不抓。

## 要解决什么

`/job-rank` 的旧 Step 1.7 只做**排序**，不做**淘汰**：把候选按 `fit` 和标题相关度排一排，
取前 12 个抓 JD，**剩下的全部标记为 deferred、留在 `new`**。于是 183 个待评职位要跑
16 轮才清得完，而每轮都要重新排一次——队列根本不会排空。

真正缺的是淘汰。但**不是每个字段都配结案**：薪资是算术，谁算都一样；
学历字段与 JD 正文实测 58% 对不上，标题更只是猜。能结案的只有前者，
其余只能降权排到队尾（见下面那张表）。

## 判断谁做，机械谁做

候选人的硬门取值写在 `profile/candidate.md` 里，是自然语言
（`可接受底线：<数字>k × <数字>薪`、`<学历>，<专业>`、`通勤可接受 <数字> 分钟内`）。
**这里不解析那份散文**——那正是这个仓库栽过四次的坑（AI 写的合法变体有很多种，
解析器只认一种，静默丢数据）。

所以：**阈值从命令行传进来**，由读得懂 profile 的一方给；这个工具只负责在 183 条
记录上把规则机械地跑一遍，并如实报告命中了什么。

## 用法

    python tools/prescreen.py                                  # 只看：字段全貌 + 各规则会命中多少
    python tools/prescreen.py --annual-floor 42 --apply         # 年包低于 42 万（可结案）
    python tools/prescreen.py --edu-floor 本科 --apply          # 学历字段（只降权）
    python tools/prescreen.py --off-track 算法,开发 --protect 产品经理 --apply  # 标题（只降权）

## 两档证据：能结案的只有一条

| 规则 | 证据 | 能做什么 |
|---|---|---|
| `--annual-floor` | 客观：薪资串折年包，谁算都一样 | **结案** |
| `--edu-floor` | 推断：列表页 `eduLevel` 字段，与 JD 正文实测 58% 对不上 | 只能**降权泊车** |
| `--off-track` | 推断：标题子串，取决于怎么断句 | 只能**降权泊车** |

两条推断同时命中也不结案——两个都不可靠的信号叠在一起不会变可靠。
降权的岗留在 `new`、写一个 `deprioritized` 标记、抓 JD 时排到队尾。

不加 `--apply` 一律是**试运行**：只打印会改什么，不写盘。

零依赖，只用标准库。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402

import export_web_data as ex  # noqa: E402  薪资折算复用它，别写第二份
import build_dashboard as bd  # noqa: E402  投递记录的读法与模糊匹配复用它
import tracker  # noqa: E402  状态码说成人话只有 `say()` 这一份

#: 学历阶梯。**只在要求严格高于底线时才淘汰**——同级不淘汰。
#: 「统招本科」与「本科」同级：候选人是不是「统招」往往有歧义（境外院校、专升本、
#: 非全日制都算不清），那属于判断，不属于机械匹配，这里只标注、不否掉。
EDU_LADDER = ["不限", "初中", "高中", "中专", "大专", "本科", "硕士", "博士"]


def edu_rank(text: str) -> int:
    """把平台给的学历串映射到阶梯上。认不出来返回 -1（= 不参与淘汰）。"""
    t = (text or "").strip()
    if not t:
        return -1
    if "博士" in t:
        return EDU_LADDER.index("博士")
    if "硕士" in t or "研究生" in t:
        return EDU_LADDER.index("硕士")
    if "本科" in t:
        return EDU_LADDER.index("本科")
    if "大专" in t or "专科" in t:
        return EDU_LADDER.index("大专")
    # 中专/技校/职高是同一档；写在「高中」之后判，因为「中专」串里不含「高中」
    if "中专" in t or "技校" in t or "职高" in t or "中职" in t:
        return EDU_LADDER.index("中专")
    if "高中" in t:
        return EDU_LADDER.index("高中")
    if "初中" in t:
        return EDU_LADDER.index("初中")
    if "不限" in t:
        return EDU_LADDER.index("不限")
    return -1


# 薪资折算**复用 `export_web_data.annual_package`**（见下面 annual_high_wan），
# 不写第二份。第一版自己写过一个折算：取区间下沿、只读 `salaryMonths` 字段，
# 两个错都踩了——薪数常常只存在于原始串里（`30-40K·15薪`），按 12 薪算会把
# 够线的岗误杀；拿下沿比底线却印成「上限」，显示与计算不一致。
# （这段教训原来包在一个只有 docstring 的空函数 `rule_annual_setup` 里，
# 谁也不调它——文档就写成注释，别写成永不执行的代码。）

#: 薪数未知时，按**最乐观**的薪数去估上沿再决定要不要淘汰。正本在 `_cli`
#: （那儿写着为什么是 16、以及为什么三处只能有一份）。
OPTIMISTIC_MONTHS = _cli.OPTIMISTIC_MONTHS


def annual_high_wan(entry: dict) -> tuple[float | None, bool]:
    """年包**上沿**（万），以及这个数是不是靠假设薪数估出来的。

    薪数未知时按 `OPTIMISTIC_MONTHS` 估，而不是按 12。原因是这里的用途是**淘汰**：

        `1.5-3万`（没写薪数）→ 按 12 薪是 36 万，低于 42 万底线 → 淘汰
                              → 但要是 16 薪就是 48 万，够得着 → **误杀**

    误杀的代价是一个好岗静默消失在流水线里；放过的代价只是多抓一次 JD。
    两边不对称，所以往放过那边偏。

    ## 2026-08-20 复核：这一锤下去就没有第二次机会

    上面那句「抓到 JD 再按正文判」在别的规则上成立，**在这条上不成立**。
    实测 615 个「列表页没标薪数、且已抓到 JD 正文」的岗：正文里写了薪数的
    **只有 2 个**（都 ≤13 薪）。平台不给，JD 也不给——这个数**下游补不回来**。

    所以 `OPTIMISTIC_MONTHS` 不是一个「先估着、回头修正」的初值，
    它就是最终值。改它等于直接改结案线。

    ## 16 是怎么来的（原来没写，看着像随手拍的）

    1329 个标了薪数的岗，分布是 13薪 17% · 14薪 19% · 15薪 35% · 16薪 19%，
    **超过 16 薪的只有 10.2%**（17–24 薪，最高 24）。所以 16 大致是第 90 百分位：
    再往上抬，换来的召回越来越薄。

    这条线对 `OPTIMISTIC_MONTHS` **很敏感**：在一份两千多个岗的真实库上，
    把它从 16 抬到合理上限 24，未标薪数而被结案的数量少掉约六成
    （灰区里的那些按 16 薪不够、按 24 薪够得着）。按上面 10.2% 的分布推算，
    灰区里真正够得着的约占一成。
    （具体数字取决于各人的底线，跑 `python tools/prescreen.py --annual-floor <你的数>`
    看自己的——**这里不写死任何人的取值**，阈值一律从命令行传进来。）

    ## 「放过只多抓一次 JD」这句现在要打折

    写它的时候还没有额度这回事。撞了猎聘风控之后，抓 JD 是**最稀缺、
    也最有封号风险**的资源（`portal_budget.py`：动作之间按轻重隔 8/4/3 秒，撞了才冷却）。
    把 16 抬到 24，多出来的 230 次抓取约等于四天的额度。

    不对称仍然成立（误杀是把一个好岗埋进两千行的搁置区，practically 找不回来），
    但代价那一侧不再是「顺手的事」。真要动这个数，两边都得重新称一次。

    ⚠️ 结案**是可逆的**：写的是 `status=ranked` + 判词「跳过」+ 依据，
    落进搁置区，面板给规则淘汰的岗留着「放回可以投」。这是这条规则敢有结案权的
    前提——那个按钮要是哪天没了，这条规则也就不该再结案。

    ⚠️ 这和显示口径**故意不一样**：页面上按 12 薪保守显示（并标「未标薪数」），
    那里的目的是不虚报；这里按 16 薪乐观估，目的是不误杀。同一个数字，两种用途，
    两个方向的保守——写清楚是为了下次有人来「统一」它们之前先看到这段。
    """
    pkg = ex.annual_package(entry.get("salary") or "", entry.get("salaryMonths"))
    if not pkg:
        return None, False
    if not pkg.get("assumed12"):
        return pkg["high"], False
    return pkg["high"] / 12 * OPTIMISTIC_MONTHS, True


def load(user: str) -> tuple[Path, dict, int]:
    """读职位库，**连版本戳一起返回**。

    写回时把戳带上（`atomic_write(..., expect=stamp)`）：这期间要是总览页那边
    点了按钮，就会抛 `StaleWrite` 而不是把用户那一下悄悄抹掉。
    """
    p = ROOT / "users" / user / "job_scraper" / "seen_jobs.json"
    if not p.is_file():
        raise SystemExit(_cli.no_store(p))
    data, stamp = _cli.load_json_stamped(p)
    return p, data, stamp


def candidates(seen: dict, user_state: dict | None = None) -> list[tuple[str, dict]]:
    """待评的：只有 `new`。

    **`skipped` 与已投的绝不碰**——那是用户明确表过态的，重新处理只会让它们冒出来
    （与 `/job-rank` Step 1.3 同一条规则）。

    ⚠️ **用户在总览页点的「不投」不在职位库里，在叠加层里**
    （`_cli.load_user_state`，2026-08-19 拆出去的）。不带上它，就会出现
    「页面上标了不投、命令行照样评它、评完又冒回名单里」——正是这个函数
    从一开始就要防的那件事，只是它藏在另一个文件里了。
    """
    st = user_state or {}
    return [(k, e) for k, e in seen.items()
            if _cli.decided_status(e, st.get(k)) == "new"]


def rule_edu(entry: dict, floor: str) -> str | None:
    """学历硬门。命中返回依据，不命中返回 None。

    **认不出候选人自己的学历时必须报错，不能静默放行。**
    阶梯原来只有「不限/大专/本科/硕士/博士」——一个中专学历的用户传
    `--edu-floor 中专`，`edu_rank` 返回 -1、这里 `have < 0` 直接 return None，
    于是这条规则**一条都不淘汰、也不说一句话**。本科用户享受得到的学历预筛，
    他拿到的是一个假装在跑的空规则。

    职位那一侧（`eduLevel`）认不出仍然按 -1 放过——那是平台给的串，
    五花八门是常态，宁可不淘汰。**两侧的处理必须不一样**：一侧是数据脏，
    另一侧是我们自己的取值域没覆盖到这个人。
    """
    have = edu_rank(floor)
    if have < 0:
        raise SystemExit(
            f"认不出学历「{floor}」——本工具的学历阶梯是："
            f"{' < '.join(EDU_LADDER)}。"
            "\n  用其中一个词重跑；你的学历不在里面就是这个工具的取值域漏了它，"
            "请提 issue，别让这条规则静默空转。")
    need = edu_rank(entry.get("eduLevel") or "")
    if need < 0 or need <= have:
        return None
    # **措辞不许写成「一票否决」。** 这条已经从「结案」降为「降权泊车」
    # （见 main() 里 OBJECTIVE / INFERRED 那段的实测数据）：`eduLevel` 是平台
    # 列表页字段，和 JD 正文对不上的概率超过一半。它只够把这个岗排到队尾，
    # 不够判死刑——依据里再写「一票否决」，复核的人会以为这是读过正文的结论。
    # 依据会**原样打到终端**，所以不要在这里写 Markdown 粗体——终端上就是两个星号
    # （`test_display_wording.TerminalOutputIsNotMarkdown` 扫的就是这个）。
    return (f"列表页字段写着{entry['eduLevel']}，高于候选人的{floor}"
            f"（未经 JD 正文复核，只降权不结案）")


def rule_annual(entry: dict, floor_wan: float) -> str | None:
    """年包明显低于底线。

    **比的是区间上沿**：连开到顶都够不着底线，才算「明显偏低」。拿下沿比会把
    `40-70k` 这种上半段完全达标的岗一起扫掉——淘汰要保守，宁可放过不可误杀。
    """
    high, assumed = annual_high_wan(entry)
    if high is None or high >= floor_wan:
        return None
    # **两个数不许印成一样。** 取整到万之后 44.8 和 45.0 都写作「45」，
    # 于是这句话变成「年包上沿约 45 万，低于底线 45 万」—— 自相矛盾，
    # 而这条规则**有结案权**（判了就进搁置区）。理由自己打自己的时候，
    # 用户没有办法判断是数据错了还是工具错了。
    # 实测活动用户 2026-08-23：635 条里 11 条这样（28k×16 = 44.8 万 撞 45 万底线），
    # 而这句话是存进 `rank_breakdown.依据`、原样显示在面板上的。
    # 只在撞上时补一位小数 —— 平时不该为了 1.7% 的情形给所有人加个小数点。
    dp = 1 if round(high) == round(floor_wan) else 0
    if not assumed:
        return (f"年包上沿约 {high:.{dp}f} 万，低于底线 {floor_wan:.{dp}f} 万"
                f"（原文：{entry['salary']}）")
    # **未标薪数这一支不许用断言的语气给出年包。** 这里按最乐观的 16 薪估
    # （为了不误杀），而面板薪资栏走 `export_web_data.annual_package`，未标薪数时
    # 按 12 薪保守折（为了不吹牛）。两个口径各自都对 —— 但**它们并排显示在同一行上**
    # （`Shortlist.tsx` 搁置区那一行：先渲染 `annual`，同一行的 `.shelf-why` 再渲染这句）。
    #
    # 实测 2026-08-26：这样的岗 178 个。那一行字面读作
    # 「… · 30-33.6万　年包上沿约 45 万，低于底线 45 万」—— 同一个岗两个年包，
    # 而「按 12 薪保守算」那句说明只在悬浮提示里。标了薪数的 119 个两边分毫不差，
    # 分叉只出在这一支。
    #
    # 修法不是去统一两个口径（淘汰要乐观、显示要保守，各自都对），而是让这一支
    # **说成条件句**：和薪资栏那个数并排时读作「就算按最乐观的算法也不够」，
    # 而不是第二个年包。
    return (f"未标薪数：按最乐观的 {OPTIMISTIC_MONTHS} 薪估，上沿也只有 "
            f"{high:.{dp}f} 万，仍低于底线 {floor_wan:.{dp}f} 万"
            f"（原文：{entry['salary']}）")


def rule_off_track(entry: dict, words: list[str],
                   protect: list[str] | None = None) -> str | None:
    """标题即显示是另一条职能线。

    ⚠️ **这不是硬门**，是方向不对——岗位本身没问题。所以判词给「跳过」而不是
    「硬门 FAIL」，两者在报告里是分开的两栏。

    ## `protect` 是必须的，不是可选优化

    中文岗位名把**职能放在尾部**、领域放在前面：`采购经理` 的职能是采购，
    `智能体开发产品经理` 的职能是产品经理、领域才是智能体开发。而这里是整个标题的
    子串匹配，看不出位置——于是「开发」把 `智能体开发产品经理` 当成了开发岗。

    实测代价：4 个「智能体开发产品经理」（年包 72-160 万，是这份数据里最对口也最贵的
    一批）死于标题含「开发」，**JD 一个字都没读过**；`AI大模型产品经理（算法平台）`
    死于「算法」。`rank.md` 早就写着「要格外克制，`AI产品经理（算法方向）` 含「算法」
    但未必不合适」——散文告诫拦不住，得有机制。

    所以：**标题里写着候选人目标职能的，off-track 一律不许杀**。这与框架的证据分级
    一致——标题这一层证据判不了死刑，让它活到读 JD 那一步再说。

    `protect` 同样由调用方从 `profile` 里读出来传进来，本工具不猜。
    """
    title = entry.get("title") or ""
    for p in (protect or []):
        if p and p in title:
            return None
    hit = [w for w in words if w and w in title]
    if not hit:
        return None
    return (f"标题含「{'、'.join(hit)}」，是另一条职能线，"
            f"与候选人方向根本性错配（技能与经验 0-39 档）")


def applied_rows(user: str) -> list:
    """投递记录里**真投出去过**的那些行。读法复用 `build_dashboard.load_tracker`。

    只收 `status` 非空的行（`applied` 及其之后的所有状态）；`company` 是脱敏串的
    一律不收 —— 「某知名公司」不是公司身份，拿它做键会一次性误杀一大批
    （判据与 `build_dashboard.match_tracker` 里那段同源）。
    """
    rows = bd.load_tracker(ROOT / "users" / user / "job_search_tracker.csv")
    return [r for r in rows
            if (r.get("status") or "").strip()
            and (r.get("company") or "").strip()
            and not _cli.is_anonymous_employer(r.get("company") or "")]


def rule_applied_same_role(entry: dict, rows: list) -> str | None:
    """**这家的这个岗你已经投过了。** 客观证据，直接结案。

    `job-rank.md` Step 1 第 2 条早就写着「投递记录里已有的『公司 + 岗位』一律不在
    范围内，任何参数都不能覆盖这一条」—— 而它**长期没有任何工具执行**，
    全靠执行者手工比对台账。

    2026-08-13 那次就漏了一个：台账里记着「一家券商系公司 / AI应用产品经理」，
    当天 `/job-auto` 又把同一家的「AI应用产品经理（**agent**）」当新岗评了一遍，
    花掉一次 JD 读取 + 一份深评 + 一份话术。本人当场指出：
    「一家券商系公司 之前投过的吧，这类信息也该落盘，避免后面重复获取」。

    **为什么不能靠 `build_dashboard.match_tracker` 代劳**：那个函数**故意**不让
    「已经钉在另一个 URL 上的投递记录行」去认同公司的新岗（它注释里记着
    「后端工程师」被「后端工程师（社招）」吞掉那次事故）。那条设计是对的 ——
    它防的是**把新岗静默标成已投**。这里要的是另一件事：不静默、不标已投，
    而是**结案并把原投递写进依据**，用户在总览页看得见、也翻得回来。
    """
    if _cli.is_anonymous_employer(entry.get("company") or ""):
        return None
    title = entry.get("title") or ""
    for r in rows:
        if not bd._fuzzy(r.get("company") or "", entry.get("company") or ""):
            continue
        if not bd._fuzzy(r.get("role") or "", title):
            continue
        when = (r.get("date") or "").strip() or "日期未记"
        src = (r.get("source") or "").strip()
        tail = ("，原投递：" + src) if src else ""
        # **状态要说成人话。** 这句话进 `skipReason`，直接印在总览页的
        # 「不投的岗位」那一行上 —— 而 `status` 一列存的是 `applied` 这样的
        # 英文码。原样拼出去就是 `AGENTS.md` 点名禁的「未解释的英文码」，
        # 实测 2026-08-31 导出的 `data.json` 里 8 处。
        # 措辞跟 `applied_jds.py` 那句一致（「，现在是「…」」），别另起一种。
        return ("这家的这个岗你已经投过：" + when + " 投的「"
                + (r.get("company") or "") + " / " + (r.get("role") or "")
                + "」，现在是「" + tracker.say(r.get("status")) + "」" + tail)
    return None


def rule_applied_same_company(entry: dict, rows: list) -> str | None:
    """**这家你投过别的岗。** 只降权泊车，不结案。

    同一家公司同时开几个不同的岗是常态，不能因为投过一个就把其余的全毙掉。
    但它值得排到队尾，也值得在名单上看得见 —— 抓 JD 的时间是有限的，
    而「这家已经在跟进了」是个真实的排序依据。
    """
    if _cli.is_anonymous_employer(entry.get("company") or ""):
        return None
    for r in rows:
        if bd._fuzzy(r.get("company") or "", entry.get("company") or ""):
            when = (r.get("date") or "").strip() or "日期未记"
            return ("这家你 " + when + " 投过「" + (r.get("role") or "")
                    + "」（现在是「" + tracker.say(r.get("status")) + "」），"
                    + "这个岗不是同一个，先排队尾")
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="用已存字段预筛待评职位，不抓 JD。不加 --apply 就是试运行。")
    ap.add_argument("--edu-floor", metavar="学历",
                    help="候选人的学历，如「本科」。岗位字段严格更高才命中。"
                         "只降权、不结案——这个字段与 JD 正文实测 58%% 对不上")
    ap.add_argument("--annual-floor", type=float, metavar="万",
                    help="年包底线（万）。拿薪资区间的「上沿」跟它比——连开到顶都"
                         "够不着底线才淘汰（拿下沿比会把 `40-70k` 这种上半段完全"
                         "达标的岗一起扫掉）。薪数未写时按最乐观的 16 薪估，"
                         "同样是为了不误杀。资料里若有两个数（常规底线 + "
                         "「方向极对可以降到 X」这类弹性条款），传低的那个："
                         "预筛只有标题和薪资串，判不了方向对不对，而这条又是"
                         "唯一能结案的（不可逆）")
    ap.add_argument("--off-track", metavar="词1,词2",
                    help="标题含这些词即判为另一条职能线（逗号分隔）。只降权，不结案")
    ap.add_argument("--protect", metavar="词1,词2",
                    help="候选人的目标职能（如「产品经理,产品负责人」）。标题里含这些词的，"
                         "off-track 一律不杀 —— 中文职能名在尾部，「智能体开发产品经理」"
                         "是产品岗不是开发岗。用 --off-track 时必须一起给")
    ap.add_argument("--apply", action="store_true", help="真的写回 seen_jobs.json")
    ap.add_argument("--user", help=_cli.HELP_USER)
    args = ap.parse_args(argv)

    # 不判存在就直接 read_text 会在**全新 clone 上**抛 FileNotFoundError 栈回溯
    # ——新用户敲错顺序是常态，第一次撞见的不该是 traceback。
    user = _cli.pick_user(args.user or "", root=ROOT)
    path, data, _stamp = load(user)
    _ustate = _cli.load_user_state(path)
    seen = _cli.seen_of(data)
    _cli.stop_on_unreadable_rows(seen, path)
    cands = candidates(seen, _ustate)
    if not cands:
        print("没有待评职位（status=new 的一个都没有）")
        return 0

    off_words = [w.strip() for w in (args.off_track or "").split(",") if w.strip()]
    protect = [w.strip() for w in (args.protect or "").split(",") if w.strip()]
    # 硬性要求，不是建议。原来 rank.md 里写着「--off-track 要格外克制」，是散文告诫，
    # 拦不住——实测 4 个年包 72-160 万的「智能体开发产品经理」死于标题含「开发」。
    # 光给淘汰词不给保护词，这里直接拒绝执行。
    if off_words and not protect:
        # 举例不写死职能名。**中文职能名的重心在标题尾部**，这是语言事实，与行业无关；
        # 而「X开发产品经理是产品岗」这种例子一旦写死，护士、教师、施工员读到这条帮助
        # 会当场认定这工具不是给他用的——那正是这个仓库反复在清的形状。
        print("--off-track 必须和 --protect 一起给。", file=sys.stderr)
        print("  中文职能名的重心在标题「尾部」：「A开发B经理」是 B 岗，不是 A 岗，"
              "只按淘汰词匹配会误杀。", file=sys.stderr)
        print("  从 profile 的期望岗位读出他自己的目标职能传进来，"
              "逗号分隔：--protect <职能1>,<职能2>", file=sys.stderr)
        return 2
    today = date.today().isoformat()

    # ---------- 规则按**证据类型**分组，不按重要性排序 ----------
    #
    # 这是本工具最要紧的一条结构约束，值得写清楚为什么。
    #
    # 两类证据的可复核性差着一个量级：
    #
    #   客观 —— 字段算术。`30-40K·15薪` 折成年包再和底线比，谁来算都是同一个数，
    #           判错了能当场指出错在哪一步。
    #   推断 —— 标题猜测。`智能体开发产品经理` 到底是产品岗还是开发岗，取决于
    #           读的人怎么断句；而工具只会做子串匹配，连断句都没有。
    #
    # 原来两类混在一张优先级表里，`第一条命中就结案`。于是**推断也能独自判死**：
    # 实测 53 个「另一条职能线」淘汰里，44 个只有标题这一个依据，年包中位 88 万、
    # 17 个 ≥100 万，全部永久结案且错误静默。
    #
    # 而这条权力本来就是多余的。标题相关度在 `/job-rank` 第 7b 步**已经**用于排序
    # （「按标题与 focus/profile 的相关度排序，取前 M 去抓」）——同一份证据在那里
    # 只决定抓取顺序、可逆、不下结论。7a 把它升格成判词，唯一多出来的作用是让
    # 「待评」的计数好看（`rank.md`：「只 defer 不淘汰的话队列永远排不空」）。
    # **那是记账问题，不该用判词解决。**
    #
    # 所以现在：客观证据才能结案；推断单独只能降权（留在 `new`、排到队尾）。
    # 两者同时命中才结案，且依据以客观那条为准——事后要能复核的是它。
    # 结案一律**不给分数**（`None`）。原来这里写常数 20 / 25，那是第三种东西——
    # 既不是判定也不是评分：
    #
    #   框架算总分是 技能×0.30 + 薪资×0.25 + 强度×0.20 + 发展×0.25。
    #   一个技能完全对口、但薪资低于底线的岗，框架算出来约 65（「值得投」档），
    #   预筛却写 25（「不建议」档）—— 差 40 分、差两个档位，而这个数会显示在
    #   面板上、参与排序。它不是保守，是另一个数字冒充同一个量。
    #
    # 预筛压根没算过四维（它连 JD 都没读），就不该产出总分。`None` 是诚实的：
    # 和硬门 FAIL 一样表示「已结案、未评分」，面板本来就认这个状态。
    # ── 学历为什么从「客观」降到「推断」 ──
    #
    # 它看起来最像客观证据：`eduLevel` 字段对着候选人学历比一下，谁比都是同一个数。
    # **算术没错，错的是输入。** `04-job-evaluation.md` 早就写过「判据只认 JD 正文，
    # 不认列表页字段」，但那句话没管到这里——工具照样拿字段结案。
    #
    # 实测（2026-08-10，一份 543 个岗的真实数据里，字段标「硕士/博士」且已抓到 JD 正文的
    # 那 12 个，逐条比对正文）：
    #
    #   正文确实硬性要求硕博           5
    #   正文写「本科及以上」            2   ← 其中一个年包 100-160 万
    #   正文根本没提学历               3
    #   正文写「可放宽至本科」/「或同等经验」 2
    #   —— 误杀 7/12，**58%**
    #
    # 一个超过半数会杀错的规则不配有结案权。降为推断之后它仍然有用：命中就排到队尾、
    # 留下标记，抓到 JD 再按正文判——那才是框架说的那条路。
    #
    # ## 2026-08-20 用 1485 份 JD 正文复核过一遍：58% → **60%**，结论不变
    #
    # 上面那个数出自 12 个岗。现在语料大了 17 倍（规则命中且有正文的 200 个），
    # 同一口径重算：
    #
    #   正文确实硬性要求硕博        80
    #   正文写「本科及以上」就行     20   ← 白纸黑字够得着
    #   正文明说可放宽 / 同等经验    10
    #   正文压根没写成硬性学历要求   90   ← 判不了，不是判过了
    #   —— 误杀 120/200，**60%**
    #
    # 小样本的结论站住了，这条规则继续只降权。
    #
    # ⚠️ **别用「字段与正文是否一致」去重测这件事。** 那个口径算出来是
    # **93% 一致**，看着像「字段挺准，可以结案了」——它只统计了双方都明确
    # 写了学历的那 811 个，把「正文根本没写」的 90 个（这里最大的一类）
    # 整个排除在分母外。要量的不是字段准不准，是**照它结案会杀掉多少能投的岗**：
    # 分母必须是「规则会命中的全部」，凡不能确认硬性要硕博的都算误杀。
    # 复核这条注释的人第一次就该看到这个坑——写这段的人自己先掉进去过。
    #
    # 薪资留在「客观」：`salary` 是平台展示给求职者看的那个串，详情页与列表页一致，
    # 没有「字段一套、正文另一套」的结构性分歧；而且规则比的是区间**上沿**、
    # 薪数未知时按最乐观的 16 薪估，方向本来就是宁可放过。
    OBJECTIVE, INFERRED = "客观", "推断"
    rules = []
    # **投过的排在最前面。** 台账是客观事实，不是推断——而且这一条不花任何参数，
    # 不需要用户先填资料就能生效。见 `rule_applied_same_role` 的说明。
    _applied = applied_rows(user)
    if _applied:
        rules.append((OBJECTIVE, "粗筛：跳过", None,
                      lambda e: rule_applied_same_role(e, _applied), "投递记录"))
        rules.append((INFERRED, "粗筛：跳过", None,
                      lambda e: rule_applied_same_company(e, _applied), "投递记录"))
    if args.edu_floor:
        rules.append((INFERRED, "粗筛：跳过", None,
                      lambda e: rule_edu(e, args.edu_floor), "学历字段"))
    if args.annual_floor is not None:
        rules.append((OBJECTIVE, "粗筛：跳过", None,
                      lambda e: rule_annual(e, args.annual_floor), "薪资算术"))
    if off_words:
        rules.append((INFERRED, "粗筛：跳过", None,
                      lambda e: rule_off_track(e, off_words, protect), "标题"))

    hits: list[tuple[str, dict, str, str, int | None]] = []
    # 每个岗把**所有**规则都跑一遍——要知道有没有第二个独立证据，就不能一命中就停。
    parked: list[tuple[str, dict, str]] = []
    for key, e in cands:
        obj = [(v, s, w) for kind, v, s, fn, _ in rules
               if kind == OBJECTIVE and (w := fn(e))]
        inf = [(v, s, w) for kind, v, s, fn, _ in rules
               if kind == INFERRED and (w := fn(e))]
        if obj:
            # 客观证据结案。依据以客观那条为准；推断只作补充，因为事后要复核的是前者。
            verdict, score, why = obj[0]
            if inf:
                # **整句拼进去，不要从里面抠词。** 原来这里用 `「([^」]+)」` 取推断
                # 理由里的第一个引号内容，再套一句「标题也含「X」」——那假设推断
                # 只有「标题」一种。学历降为推断之后，第一个引号里是「学历院校」，
                # 会拼出「标题也含「学历院校」」：一句读起来通顺、却完全错的依据。
                why = f"{why}｜另有推断信号：" + "；".join(w for _, _, w in inf)
            hits.append((key, e, verdict, why, score))
        elif inf:
            # 只有推断 → 降权泊车，留在 `new`。推断判不了死刑。
            parked.append((key, e, "；".join(w for _, _, w in inf)))

    # ---------- 报告 ----------
    print(f"待评职位 {len(cands)} 个（用户：{user}）")
    if not rules:
        print("\n没有给任何规则 —— 下面是可用字段的覆盖情况，据此决定传哪些阈值：\n")
        for f in ("eduLevel", "salary", "salaryMonths", "location",
                  "workYears", "compScale", "compIndustry"):
            n = sum(1 for _, e in cands if e.get(f) not in (None, "", "未知"))
            print(f"  {f:14} {n:3}/{len(cands)}")
        print("\n可用规则：--edu-floor / --annual-floor / --off-track")
        print("阈值请从 profile/candidate.md 读出来再传进来 —— 本工具不解析那份散文")
        return 0

    by_verdict: dict[str, int] = {}
    for _, _, v, _, _ in hits:
        by_verdict[v] = by_verdict.get(v, 0) + 1
    todo = len(cands) - len(hits) - len(parked)
    # 「降权泊车」是这个文件里的规则分组术语，写在流程里没问题——但**不能印给用户看**。
    # 需要当场解释的词，本身就说明它没在说人话（见 AGENTS.md 的措辞表）。
    # **「要读 JD 才能评」不等于「要去抓」。** 这句原来写的是「剩 N 个仍需抓 JD」，
    # 而其中多数的正文**详情库里早就有了**：实测活动用户 2026-08-23，
    # 待评 182 个里 126 个已有，真正要去抓的只有 56 个。
    #
    # 说贵了三倍不是措辞问题：抓取额度是这套系统里最稀缺的资源
    # （每次请求之间要隔 8/4/3 秒、撞了风控整站冷却 24 小时），而这句话正是用户决定
    # 「今天还抓不抓」时读到的那一句。判据借 `jd_store.status()`，不另数一遍。
    need = ""
    try:
        import jd_store
        st = jd_store.status(user)
        if st["new_total"]:
            need = f"（其中 {st['new_total'] - st['new_have']} 个还得先去抓正文）"
    except (Exception, SystemExit):
        # **`SystemExit` 也要接。** `jd_store._seen` 在没有职位库时抛的是它
        # （`BaseException` 的子类，`except Exception` 接不住），于是
        # 「少说这半句」变成了「把整条 prescreen 掀翻」—— 实测 2026-08-23 15 条测试当场红。
        # 这一处的全部意思就是「读不出就不说」，不该有任何能逃出去的异常。
        pass
    print(f"结案 {len(hits)} 个 · 先放一边 {len(parked)} 个 · "
          f"剩 {todo} 个要读 JD 才能评{need}\n")
    # 判词与依据**存盘用内部形态**（`硬门 FAIL (…)`，别的工具按它匹配），
    # **印给用户看之前一律过 `plain()`**——那正是它存在的理由。
    # 实测漏过：终端上直接印着「硬门 FAIL (学历院校)」，内部词加英文码一起上屏。
    # `test_display_wording` 扫的是 `print()` 里的**字面量**，而这里的词来自变量，
    # 它看不见——所以这条要靠人读出来，也因此值得写在这儿。
    for v, n in sorted(by_verdict.items()):
        print(f"  {ex.plain(v)}  {n} 个")
    print()
    for _, e, v, why, _ in hits[:12]:
        print(f"  [{ex.plain(v)}] {(e.get('title') or '')[:26]:28} {ex.plain(why)[:52]}")
    if len(hits) > 12:
        print(f"  …… 另有 {len(hits) - 12} 个")
    if parked:
        print(f"\n  只看了标题、先放一边（没有结案，只是排到队尾；"
              f"只有标题一个依据，判不了死刑）：")
        for _, e, why in parked[:8]:
            print(f"    {(e.get('title') or '')[:26]:28} {ex.plain(why)[:46]}")
        if len(parked) > 8:
            print(f"    …… 另有 {len(parked) - 8} 个")

    if not args.apply:
        print(chr(10) + _cli.DRY_RUN_NOTE)
        return 0

    # 这次实际生效的阈值，逐条记进每个被淘汰的岗。
    # 原来只写「标题含「采购」」，没记这轮传的是哪几个词——而词表是每次由调用方
    # 现给的，换一批词同一个岗可能活也可能死。事后既无法审计也无法复现，
    # 而 off-track 恰恰是最容易给错的那个参数。
    ruleset = {k: v for k, v in (
        ("学历下限", args.edu_floor),
        ("年包底线万", args.annual_floor),
        ("另一条职能线的词", "、".join(off_words) or None),
        ("受保护的目标职能", "、".join(protect) or None),
    ) if v is not None}

    for key, e, verdict, why, score in hits:
        entry = seen[key]
        entry["status"] = "ranked"
        entry["rank_verdict"] = verdict
        entry["rank_date"] = today
        entry["rank_score"] = score
        # 依据必须写下来：用户在总览页看到「跳过」时要能知道凭什么
        entry["rank_breakdown"] = {"依据": why, "来源": "预筛（未抓 JD）",
                                   "本轮规则": ruleset}
    for key, _, why in parked:
        entry = seen[key]
        # **status 保持 `new`** —— 这个岗没有结案，只是排到队尾。
        # 抓 JD 的额度有限，先花在没被降权的上面；额度富余时它照样会被抓。
        entry["deprioritized"] = {"依据": why, "日期": today, "本轮规则": ruleset}
    _cli.atomic_write(path, json.dumps(data, ensure_ascii=False, indent=1),
                      expect=_stamp)
    print(f"\n已写回 {path.relative_to(ROOT).as_posix()}："
          f"{len(hits)} 个结案 · {len(parked)} 个先放一边")
    print(f"  剩 {len(cands) - len(hits) - len(parked)} 个待抓 JD —— 跑 /job-rank 继续")
    return 0


if __name__ == "__main__":
    sys.exit(_cli.run_cli(main))
