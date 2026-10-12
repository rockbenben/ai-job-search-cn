# -*- coding: utf-8 -*-
"""评分里**不需要判断**的那几样：薪资维、综合分、判词。

## 为什么单独拿出来

`04-job-evaluation.md` 的四维里，只有三维要人（或 AI）读 JD 之后拿主意：
技能与经验、强度与公司性质、发展与风险。剩下的三样是**确定性函数**：

    薪资与职级 = f(薪资串, 薪数, 底线, 期望区间)      —— 查一张四行的表
    综合分     = Σ 维度 × 权重 + 调整                 —— 加权和
    判词       = min(分数档, 技能与经验的天花板)       —— 取小

**而它们此前和另外三维一样，由执行者逐个岗手算。** 实测活动用户 2026-08-29，
四维齐全、有分数的 728 个岗里：

    薪资维   错 89 个（12%）
    综合分   错 85 个（12%）
    判词     错  6 个（1%）

一个确定性函数被手算几百遍，错这些是必然的 —— 12% 不是谁马虎，是这个分工本身
放错了地方。此前的补救全是**事后**的：`audit_pipeline` 三条检查报出来、人再手工
订正。那是烟雾报警器，不是防火。

所以这个模块只做一件事：**把这三样从执行者手里拿走**。执行者只填要判断的那三维
加硬性条件与依据，剩下的 `score.py --apply` 现算。

## 为什么不放进 `audit_pipeline`

那边是**查**的一侧。查的和算的共用一份实现是对的，但让生产代码 import 检查器，
下一个人会为了理顺层次再抄一份 —— 这个仓库最贵的那类错误正是「同一份逻辑两处
实现」（`norm_url` 的 docstring 记着四次）。所以正本放在这里，两边都 import 它。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import _cli  # noqa: E402
import export_web_data as _ex  # noqa: E402

#: 四维的权重（`04-job-evaluation.md`「权重」）。地点是 Pass/Fail，不计权重。
DIM_WEIGHTS = {"技能与经验": .30, "薪资与职级": .25,
               "强度与公司性质": .20, "发展与风险": .25}

#: 判词的分数档（`04-job-evaluation.md`）。从高到低，取第一个够得着的。
VERDICT_BANDS = ((75, "强匹配"), (60, "值得投"), (45, "可以考虑"), (30, "不建议"))
#: 判词天花板：技能与经验这一维压得住判词，压不动分数。
#: 从 `_cli.CAP_BANDS` 推，**不另写一份** —— 那张表原样在这里抄过一遍，
#: 只是把两个字段调了个个儿（`("强匹配", 80)` → `(80, "强匹配")`）。
#: 同一组阈值两处各写一遍，调一处另一处不会红。2026-08-30 收成一处。
VERDICT_CEILINGS = tuple((n, v) for v, n in _cli.CAP_BANDS if n)
#: 档序，低→高。**不另写一份** —— `_cli.VERDICTS` 的注释自己写着「代码侧唯一
#: 定义」，而这里原来是它的手抄反序：同一张表两处各写一遍，改一处另一处不会红。
#: 2026-08-30 收成一处。
VERDICT_ORDER = tuple(reversed(_cli.VERDICTS))

#: 薪资维那张表的四个取值：到顶 / 落在期望区间 / 过底线 / 低于底线。
#: **这一维只有这四个数**，中间值一律是手算时发明出来的。
PAY_TOP, PAY_IN, PAY_OK, PAY_LOW = 90, 85, 55, 25
#: 薪数未知时按哪个薪数估「最乐观能不能过底线」。正本在 `_cli`。
OPTIMISTIC_MONTHS = _cli.OPTIMISTIC_MONTHS

#: 粗筛的强度/发展只许取这四档 —— 连 JD 都没读，给 62、58 是假精度。
COARSE_LEVELS = (30, 50, 70, 85)


def pay_dim(entry: dict, floor: float, expect) -> int | None:
    """薪资与职级该给几分。算不出返回 None（面议/未标，归「信息缺失」那条路）。

    折算走 `export_web_data.annual_package`（面板显示用的同一个实现），
    **比的是年包下沿** —— 上沿是给最理想候选人的，拿它打分等于按最好情况算。

    没写薪数时 `annual_package` 已按 12 薪保守折；12 薪够不着底线、按
    `OPTIMISTIC_MONTHS` 薪能够着 → `PAY_OK`，这是 04「有月薪、但没写几薪」
    那一条：**假设值可以让分保守，不可以让岗消失。**

    ⚠️ **底线用常规那个，不用「方向极对可以降到 X 谈」的弹性值** ——
    弹性是谈判姿态，不是打分输入（判据在 `audit_pipeline._annual_floor`）。
    """
    s = str(entry.get("salary") or "").strip()
    if not s or _cli.salary_unstated(s):
        return None
    pkg = _ex.annual_package(s, entry.get("salaryMonths"))
    if not pkg or pkg.get("low") is None:
        return None
    low = pkg["low"]
    if low >= expect[1]:
        return PAY_TOP
    if low >= expect[0]:
        return PAY_IN
    if low >= floor:
        return PAY_OK
    if pkg.get("assumed12") and low / 12 * OPTIMISTIC_MONTHS >= floor:
        return PAY_OK
    return PAY_LOW


def pay_note(entry: dict, floor: float, expect) -> str | None:
    """那一维的说明，按同一份查表现写。算不出返回 None。

    **和 `pay_dim` 共用一次折算**，不各算各的 —— 分和说明分头算就会出现
    「写着 55、解释的却是另一个数」，而那句话是要显示在总览页和评估文件里的
    （自检「薪资维和它自己的薪资串对不上」盯的就是这个）。
    """
    s = str(entry.get("salary") or "").strip()
    if not s or _cli.salary_unstated(s):
        return None
    pkg = _ex.annual_package(s, entry.get("salaryMonths"))
    if not pkg or pkg.get("low") is None:
        return None
    low, high = pkg["low"], pkg.get("high")
    span = f"{low:g}-{high:g} 万" if high else f"{low:g} 万"
    months = entry.get("salaryMonths")
    # 薪资串本身常常已经带着薪数（`35-40k·15薪`），再拼一次就成了
    # 「35-40k·15薪×15薪」—— 2026-08-29 第一版实测就是这样。
    disp = re.sub(r"[·・]\s*\d+\s*薪\s*$", "", s).strip()
    how = (f"{disp}×{months}薪 = 年包 {span}" if months
           else f"{disp}「没写几薪」，按 12 薪保守计年包 {span}")
    if low >= expect[1]:
        return f"{how}。下沿 {low:g} 万到了期望上沿 {expect[1]:g} 万之上"
    if low >= expect[0]:
        return (f"{how}。下沿 {low:g} 万落在期望 "
                f"{expect[0]:g}-{expect[1]:g} 万里")
    if low >= floor:
        return (f"{how}。下沿 {low:g} 万过了 {floor:g} 万底线，"
                f"还没进 {expect[0]:g}-{expect[1]:g} 万的期望区间")
    if pkg.get("assumed12") and low / 12 * OPTIMISTIC_MONTHS >= floor:
        return (f"{how}。12 薪下沿 {low:g} 万够不着 {floor:g} 万底线，"
                f"按 {OPTIMISTIC_MONTHS} 薪算 {low / 12 * OPTIMISTIC_MONTHS:.0f} 万才过"
                f"——所以这一项是「几薪」说了算")
    return f"{how}。下沿 {low:g} 万够不着 {floor:g} 万底线"


def band_of(score: float) -> str:
    for lo, v in VERDICT_BANDS:
        if score >= lo:
            return v
    return "跳过"


def ceiling_of(skill: float) -> str:
    for lo, v in VERDICT_CEILINGS:
        if skill >= lo:
            return v
    return "不建议"


def verdict_of(score: float, skill: float) -> str:
    """判词取「分数档」与「技能天花板」里**低**的那个。

    天花板那条是补「传导」用的：总分里薪资占 25%，钱给够就能把技能 28 的岗
    抬到 60 分。04 举过三个实测例子，其中「技能 28 · 总分 60 · 值得投」那个
    的原话是**「值得投三个字会让人真的去投、去定制材料、去准备面试」**。
    """
    return min(band_of(score), ceiling_of(skill), key=VERDICT_ORDER.index)


ADJUST_SUFFIX = ("减分", "加分")


def adjust_of(breakdown) -> dict:
    """把评分明细里四维之外的那几笔加减分捡出来。

    有两种写法，都要认：

    1. **顶层 `X减分` / `X加分` 键**（例：`"专业减分": -5`）—— 全库实际在用的
       就是这一种，2026-08-29 复查时 12 个岗带着它。
    2. `调整` 子字典 —— `composite` 的原始设计，语义相同。

    ⚠️ **这个函数是补一个真事故的**：`composite` 一直只读第 2 种，而全库一条
    都没用第 2 种。于是「专业清单不符 −5」那条裁定虽然老老实实写成了字段，
    重算时照样被丢掉 —— 2026-08-29 实测有 2 个岗的存档分已经等于纯四维和，
    减分没了。**存了字段不等于有人读它**；写入端与计算端要指向同一个名字。
    """
    if not isinstance(breakdown, dict):
        return {}
    out = {k: v for k, v in breakdown.items()
           if isinstance(v, (int, float)) and str(k).endswith(ADJUST_SUFFIX)}
    legacy = breakdown.get("调整")
    if isinstance(legacy, dict):
        out.update({k: v for k, v in legacy.items() if isinstance(v, (int, float))})
    return out


def composite(dims: dict, adjust=None) -> int:
    """四维加权和 + 四维之外的加减分（取值见 `adjust_of`）。

    那几笔必须是个**字段**，不能只写在依据的散文里 —— 否则没有任何工具查得出
    哪些岗带了减分，而那条裁定改过一次就翻案了 11 个岗。
    """
    extra = sum(v for v in adjust.values()
                if isinstance(v, (int, float))) if isinstance(adjust, dict) else 0
    return round(sum(dims[k] * w for k, w in DIM_WEIGHTS.items()) + extra)


def snap_coarse(v: int) -> int:
    """粗筛的强度/发展往低处靠到四档上。

    往低不往高：粗筛连细节都没看，**假设值可以让分保守，不可以让岗虚高**
    —— 与 `pay_dim` 里那条不对称原则同源。
    """
    return max([c for c in COARSE_LEVELS if c <= v] or [COARSE_LEVELS[0]])


#: 依据里那句「……这一维给 NN」。数改了句子不改，两边就自相矛盾
#: （`writeback._basis_is_stale` 盯的就是这个形状）。
SAID = re.compile(r"(给\s*)(\d{2})(\s*(?:并挂|，|。|$))")

#: 「给 NN」归哪一维 —— **正本在 `_cli.DIM_SAID`**，与 `writeback._basis_is_stale`
#: 判的是同一件事（两边都 import `_cli`，见那里为什么正本落在那儿）。
#:
#: **为什么必须认归属：`SAID` 一个人认不出来，而一段依据里从来不只谈钱。**
#: 逐库实测 2026-10-12：51 处「给 NN」里只有 7 处锚定在薪资维，另 11 处说强度、
#: 9 处说发展、24 处压根没点名维度（说「专业能力」「业务域」）。
_PAY_CONTEXT = re.compile(r"薪|年包|下沿|上沿|月薪|几薪")


def rewrite_pay_said(basis: str, pay: int) -> str:
    """把依据里**属于薪资维**的「给 NN」换成 `pay`，别的维度一个字不动。

    ## 为什么不能用 `SAID.sub` 直接全局替换

    实测代价（2026-10-12 一轮 `/job-auto`）：`score.py --apply` 把
    「强度与公司性质这一维给 50」「发展与风险这一维给 30」两句话里的数
    全改成了薪资维的值（55 / 25）。总览页上那格显示的就是这段解释 ——
    **用户读到的是一句话在说强度、给出的数是薪资的。**
    而本文件开头写着薪资维之外的三个判断维「不碰」：那三句被改，
    恰好是它承诺不碰的地方。

    逐库量过：51 处匹配里，**旧实现 100% 会改，其中只有 7 处该改**。

    ## 归属怎么判

    1. 句里有维度名（技能 / 薪资 / 强度 / 发展）→ **按名字认**。只有薪资
       才改；锚到别的维的一律不动。
    2. 没点名维度 → 看**所在分句**有没有谈钱信号（`_PAY_CONTEXT`）。
       有才改（实测那 14 处全是「按 16 薪估下沿 NN 万能过，这一维给 55 并挂
       「⚠ 先问几薪」」这一句），没有就不改。

    ## 为什么 2 要有，而不是一律不动

    04 的薪资维专门有一条「有月薪、但没写几薪」的 55 分规则，判据就是
    「按 16 薪估能过底线」——那一维的解释**必然**落在第 2 类里。
    一律不动等于薪资维改了而解释不改，`_basis_is_stale` 会一直报。
    """
    if not basis or not isinstance(pay, int):
        return basis
    anchored = {m.start(2): m.group(1) for m in _cli.DIM_SAID.finditer(basis)}

    def repl(m):
        dim = anchored.get(m.start(2))
        if dim is not None:
            if dim != "薪资":
                return m.group(0)          # 说的是强度/发展/技能 → 不碰
            return f"{m.group(1)}{pay}{m.group(3)}"
        # 没点名维度：只看它所在的那一分句
        lo = max(basis.rfind(c, 0, m.start()) for c in ("。", "；", "\n")) + 1
        if not _PAY_CONTEXT.search(basis[lo:m.end()]):
            return m.group(0)
        return f"{m.group(1)}{pay}{m.group(3)}"

    return SAID.sub(repl, basis)


def is_triage(breakdown: dict) -> bool:
    """这条是粗筛/预筛（可以机械重算），还是深评（正本在 evaluation.md）。

    **深评的不许在库里单边改。** `writeback --apply` 会从 `evaluation.md` 把
    分数和判词顶回来 —— 那是对的（存档是事实源），但它不碰 `硬性条件` 与
    `依据`，于是留下「硬门 FAIL 配判词值得投」的混合状态。
    2026-08-28 亲手撞过一次。
    **所以 `score.py --deep` 连 `evaluation.md` 一起改** —— 单边改的是做法，
    不是范围：薪资维按 04 就是一张查表，深评并不会让它变成判断。
    """
    return str((breakdown or {}).get("来源") or "").startswith(("粗筛", "预筛"))


def is_scoreless(entry: dict) -> bool:
    """这条岗**有意**没有分数：硬门 FAIL、预筛结案、已下线。

    它们的判词不是从分数档来的，按四维重算一个分给它们，等于把正确排除掉的
    岗复活。实测（2026-08-29 试运行）：不加这条，两个 `rank_score=None` 的岗
    被算成「跳过 → 强匹配」—— 一个判词是「已下线」，另一个是
    「硬门 FAIL (学历与院校)」。
    """
    if not isinstance(entry.get("rank_score"), (int, float)):
        return True
    return str(entry.get("rank_verdict") or "").startswith(
        ("硬门", "不满足", "已下线"))
