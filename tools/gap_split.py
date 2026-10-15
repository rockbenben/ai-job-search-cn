#!/usr/bin/env python3
"""差距分四格：这到底是「学习问题」还是「选岗问题」。

## 为什么要它

`/job-upskill` 的默认动作是**开学习计划**。默认动作有默认动作的危险：不是所有差距都
该用学习解决，而一个只会开学习清单的命令，必然把选岗问题也答成学习任务。

同一份评估里的两笔分数说的是两件事（`04-job-evaluation.md`）：

- **专业能力**低 → 学得会的
- **业务域**低 → 要换赛道，或者干脆是**投错了地方**

实测某用户 96 份可回读的评估：「专业能力够、业务域对不上」20 个，
「业务域对口、专业能力不足」只有 6 个。直接出学习计划，等于让他花几周去学一批
本来就够格的东西，而真正的问题（投递方向）一个字没提。**跑错方向的代价是几周。**

四格是机械的，交给工具；怎么跟用户说、要不要照样出计划，交给 `/job-upskill`。

## 用法

    python tools/gap_split.py            # 四格分布 + 一句结论
    python tools/gap_split.py --list 选岗   # 列出某一格的岗位
    python tools/gap_split.py --applied     # 只算真投出去的那批

零依赖，只用标准库。只读，不写盘。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _cli  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

#: 四格的边界。取自 `04-job-evaluation.md` 各维自身的分档，不是从样本凑的：
#: 专业能力 60 = 「主要要求命中，1-2 个可学习的缺口」那一档的下沿；
#: 业务域 60 = 「相邻域，业务语言能迁移」那一档的下沿（同 SWEET_SPOT_DOMAIN）。
#:
#: ⚠️ **这里原来写的是 70，而且自称「取自框架的分档」—— 那张表根本没有 70。**
#: 它的分档是 80 / 60 / 40，60-79 是一整档（「主要要求命中」），70 只是它的腰。
#: 更巧的是：`04` 里有一整段专门讲这个数 —— 判词天花板第二版曾定成 70/50/30，
#: 「依据是用实测案例校准 —— **那是过拟合**……他的高分岗恰好落在 84/82/79，
#: 于是 70 看起来是个好切点」，后来改成 80/60/40，并立下规矩
#: 「**阈值要从框架自己的语义推，不能从某一个用户的样本分布拟合**」。
#: 这里用的正是它撤掉的那个数，还借了它的名义。
#:
#: **为什么落在 60 而不是 80。** 本工具问的是「这是学习问题还是选岗问题」，
#: 而框架对 60-79 这一档给的**动作**是「值得投 —— 投，在沟通中主动补缺口」。
#: 框架都说该去投了，专业能力就不是这个岗的拦路虎，它是选岗问题。
#: 落在 80 会把「主要要求命中、还差一两点」的岗都塞进学习计划 ——
#: 那正是本工具开头说的、它要防的那件事（「一个只会开学习清单的命令，
#: 必然把选岗问题也答成学习任务」）。
#:
#: 实测活动用户 2026-08-23（687 份可回读的评估），换过来之后：
#: 主场 41→69 · 可以靠学 66→38 · 选岗问题 186→260 · 两样都差 394→320。
#: **最大格仍是「两样都差」，那句结论不变**；变的是次一级的成分 ——
#: 而它恰好往「别把选岗问题答成学习任务」这个方向走。
STACK_OK = 60
DOMAIN_OK = 60

HOME = "主场"
PICK = "选岗问题"
LEARN = "可以靠学"
OFF = "两样都差"

LABELS = {
    HOME: "专业能力够 + 行业经验对口 —— 这类岗要多投",
    PICK: "专业能力够，行业经验对不上 —— 不缺技能，缺的是投对地方",
    LEARN: "行业经验对口，专业能力不足 —— 学习计划的正主",
    OFF: "两样都差 —— 不是这条赛道",
}


#: 打分算式：`专业能力 N×0.6 + 业务域 M×0.4`。**唯一定义在这里**，
#: `export_web_data._FORMULA` 直接 import 它。
#:
#: 两处各写一份是 2026-08-21 收拢掉的形状：一处是**回读那两个分**、
#: 一处是**从屏幕上剥掉算式**，用途不同但必须认同一批字 —— 不然会出现
#: 「算式剥得掉、两个分却读不出」的岗，它安静地掉出所有按分统计的口径
#: （主场、四格、中位数），而页面看着一切正常。
#: 收拢那次只是把文本抄了过去，抄件立刻就漏了一条（下面那句），
#: 所以现在是同一个对象，抄不动。
#:
#: **尾巴 `×0.4` 可选。** 存量里有写到第二个数就停的（`…×0.6+业务域65`），
#: 收窄成必填会让这些岗从四象限、简历-市场面板、投递摘要里**一起**静默消失。
#:
#: **裸的「专业」也要认。** 存量评估里大量写成 `技能 71（专业 72×0.6+行业经验 70×0.4）`
#: ——只列 `专业能力` 的后果不是少读两个分（那两个分在 `四维` 字段里，不受影响），
#: 而是 `strip_weights` **剥不掉这句**：2026-08-21 与 2026-08-27 两次实测都栽在这上面。
#: 前一次导出的 `data.json` 里有 42 处算式原样上屏，而 AGENTS.md 的措辞表明
#: 写着算式不能给用户看（「只留两个分：专业能力 88 · 行业经验 65」）。`/job-upskill --applied`
#: 那份清单是用户直接拿编辑器打开的，中间连显示层都没有。
#: 长的排前面：`专业能力` 必须在 `专业` 之前，否则永远只吃掉前两个字。
#:
#: **中间那一段也要认 ` · `，不只认 `×0.6+`。** 这条正则有两个用途，而
#: `strip_weights` 把算式**改写成** `专业能力 88 · 行业经验 65` 上屏 ——
#: 那正是 `AGENTS.md` 措辞表规定的给用户看的写法。于是照规矩写的评估
#: （`| 技能与经验 | 67 | 专业能力 75 · 行业经验 55 |`）**这条读不出来**：
#: 它读不回自己的输出。
#:
#: 上一轮为同一件事放宽过一次，只放宽了**词**（加 `行业经验`）、没放宽**分隔符** ——
#: 半个修法。后一次实测的代价：一轮 `/job-auto` 出了 6 份深评，3 份的 `四维`
#: 静默停在粗筛旧值（`70×0.6+55×0.4` 而深评写的是 75/55），
#: `test_skill_composition_is_computed` 报「算式算出 64 却写 61」——
#: 报的是那个**旧**拆解和**新**合成分对不上，看着像评估算错了，其实是没读进去。
FORMULA = re.compile(
    r"(?:专业能力|专业|技术栈)\s*(\d+)\s*"
    r"(?:[×xX*]\s*0\.6\s*\+|[·・･]|,|，|、)\s*"
    r"(?:业务域|业务领域|行业经验)\s*(\d+)(?:\s*[×xX*]\s*0\.4)?"
)


def read_pair(entry: dict):
    """回读 `专业能力 N×0.6+业务域 M×0.4`。读不出返回 None——**不猜**。

    「技术栈」是 3.7.1 之前的旧名（互联网行业词，对护士/律师读不通，已改名
    「专业能力」）。两种都认：存量评估里写的是旧名，别让一次改名把历史数据
    变成读不出来的。
    """
    b = entry.get("rank_breakdown") or {}
    m = FORMULA.search(b.get("四维", "") or "")
    if m:
        return int(m.group(1)), int(m.group(2))
    # 有些评估把两笔单列成字段
    st, dm = b.get("专业能力"), b.get("业务领域")
    if isinstance(st, int) and isinstance(dm, int):
        return st, dm
    return None


def quadrant(stack: int, domain: int) -> str:
    if stack >= STACK_OK:
        return HOME if domain >= DOMAIN_OK else PICK
    return LEARN if domain >= DOMAIN_OK else OFF


def split(seen: dict) -> dict:
    """`{格: [(专业能力, 业务域, 条目)…]}`。**语料 = 评过分、且他没点掉的岗。**

    ## 「已打分」不由 status 判

    原来这里写的是 `if e.get("status") != "ranked": continue`，注释说「只看已打分的」
    —— 可**「已打分」本来就由 `read_pair` 判**（读不出两笔就返回 None，下一行就是）。
    那句 status 过滤在偷偷多干两件事，一件对、一件错：

    - **对的**：把他点了「不投」的排掉（实测 80 个）。学习计划不该照着
      他明确拒绝的岗开 —— 那正是 `/job-upskill` 要回答的问题的反面。
    - **错的**：把**已下线**的也排掉了（实测 14 个）。岗位关了不等于那份
      技能需求消失 —— 上个月招 Dify 的岗今天下线了，市场依然在要 Dify。
      为一个「这个岗还能不能投」的状态丢掉市场信号，是把两件事搅在一起。

    所以判据改成按**意思**写：只排他点掉的。差额虽小（593 → 607），
    但这条过滤此前**说的和做的不是一回事**，而说的那件事根本不需要它。

    ## 和面板那个 687 不是一个数，这是对的

    `export_web_data.resume_insight` 用同一个 `read_pair`、不排任何状态，
    实测 687（= 593 ranked + 14 已下线 + 80 点掉的）。两边问的问题不同：

        这里（学什么）    他没拒绝的岗在要什么 —— 拒绝掉的不该进学习计划
        面板（市场怎么读你）  市场里有多大一块对得上你 —— 他拒不拒绝不影响市场

    **两个数都对，但两处不许都只说「可回读两笔分数的评估」** ——
    同一句话两个数，用户只会以为其中一个坏了。各自报出自己的口径。
    """
    out: dict = {k: [] for k in (HOME, PICK, LEARN, OFF)}
    for e in seen.values():
        if not isinstance(e, dict) or e.get("status") == "skipped":
            continue
        pair = read_pair(e)
        if not pair:
            continue
        out[quadrant(*pair)].append((*pair, e))
    return out


def off_direction_words(box: dict, floor: int | None = None, key: str = OFF) -> list:
    """哪几个查询词专门在往「两样都差」那一格里倒岗。

    `verdict` 的两条分支都把人送去改搜索词（「收窄 /job-scrape 的方向」、
    「先调 search-queries」），却**一个词都不说** —— 而判据就在手边：
    每条岗身上带着 `found_by`（是哪个词搜到的），`split` 又把整条 entry
    留在了元组里。

    实测（2026-08-23，活动用户，607 份语料、374 个「两样都差」）：

        AI工具    共 17   两样都差 16 (94%)   主场 0
        AI原生    共 15   两样都差 14 (93%)   主场 0
        AI赋能    共 25   两样都差 22 (88%)   主场 0
        …
        Agent产品经理  共 26  两样都差  3 (12%)  主场 5

    分离得很干净：几个词几乎只产不相干的岗，而 `Agent产品经理` 反过来。
    一句「收窄方向」要用户自己去猜是哪几个，这张表直接给出来。

    **和 `query_yield` 的「该停一停的词」不是同一件事。** 那边问「这个词
    出过可投的岗吗」（高匹配 0），这边问「这个词抓来的岗在不在他赛道上」。
    一个词可以大量产出「选岗问题」（专业对口、行业不对）—— 那些不可投，
    但也不算跑偏。实测两张单子 12 个 vs 8 个词，**只有 `AI工具` 重合**。

    翻页并回主词（`query_yield.base_query`）—— 同一个词拆成七八行，
    每行都不够门槛，就永远上不了这张表（那边踩过一次的坑）。
    最小样本沿用 `query_yield.DEAD_MIN_N`：「抓够这么多个才谈这个词」
    是同一个判断，不另立一个数。

    **只报数，不替他停。** 同 `query_yield` 那句「数给你，停不停你定 ——
    你比它更清楚自己这一行的词」。
    """
    from query_yield import DEAD_MIN_N, base_query
    if floor is None:
        floor = DEAD_MIN_N
    tally: dict = {}
    for k, rows in box.items():
        for *_pair, e in rows:
            fb = (e.get("found_by") or "").strip()
            if not fb:
                continue
            acc = tally.setdefault(base_query(fb), [0, 0])
            acc[0] += 1
            if k == key:
                acc[1] += 1
    # **一次都没命中的词不进这张表。** 原来只按「抓够 floor 个」过滤，
    # 于是命中 0 的词也带着 `off=0` 留在列表里 —— 调用方取前三名，
    # 真正命中的不足三个时，屏幕上就会出现「跑偏最多的几个词：某某（0/20 跑偏）」。
    # 眼下的语料里前三名都非零（所以从没露过面），但那是语料大，不是判据对。
    out = [(w, n, off) for w, (n, off) in tally.items()
           if n >= floor and off]
    # 按**命中的个数**排，不按比例：比例高但只有 3 个岗的词说明不了什么，
    # 而门槛已经把样本太小的挡在外面了。
    return sorted(out, key=lambda r: (-r[2], -r[1], r[0]))


def _off_hint(box: dict, top: int = 3, key: str = OFF) -> str:
    """把最该改的那几个词接在结论后面。没有就返回空串。

    **两条结论都把人送去改搜索词，而「改哪个」原来一个字都没说。**
    这一句让那条指令能照着做。取值与判据见 `off_direction_words`；
    只报数，不替他停。

    ## 但「改哪个」要跟着**那条结论的诊断**走

    这一句原来固定数「两样都差」，而它挂在两条结论后面：

        「两样都差」占多数        → 点名倒「两样都差」的词   ← 对得上
        「选岗问题」≥「可以靠学」  → 还是点名那批词           ← 对不上

    第二条的诊断是**「你不缺技能，缺的是投对地方」** —— 该改的是那些
    「专业对口、行业不对」（`PICK`）产得最多的词，它们正瞄着错的行业。
    而「两样都差」的词只是**烂词**，和这条诊断无关。

    实测活动用户 2026-08-27，两份名单**完全不重合**：

        两样都差： AI赋能 14/20 · AI原生 12/19 · AI工具 12/18
        选岗问题： Agent产品经理 24/33 · 企业AI应用 22/34 · AI应用产品经理 11/23

    而后一组正是他产出最多的几个主力词 —— 「改这几个」和「改 AI工具」
    是两条分量完全不同的指令。
    """
    words = off_direction_words(box, key=key)[:top]
    if not words:
        return ""
    # 措辞跟着格子走：「跑偏」说的是**两样都差**；
    # 「专业对口、行业不对」不算跑偏，那是投错了地方。
    what = "跑偏" if key == OFF else "行业对不上"
    body = "、".join(f"{w}（{off}/{n} {what}）" for w, n, off in words)
    return f"。{what}最多的几个词：{body} —— 数给你，停不停你定"


def verdict(box: dict) -> str:
    """一句话结论——`/job-upskill` 的 Step 4.5 据此决定怎么走。"""
    n_learn, n_pick, n_off = len(box[LEARN]), len(box[PICK]), len(box[OFF])
    total = sum(len(v) for v in box.values())
    if not total:
        return "没有可回读两笔分数的评估 —— 先跑 /job-rank，或这批评估用的是旧口径"
    if n_off > total * 0.6:
        return ("这批语料整体离你的方向很远（「两样都差」占多数）——"
                "学习计划会照着一堆不相干的岗开出来。先收窄搜索词："
                "跑 /job-setup --section search" + _off_hint(box))
    if n_pick == 0 and n_learn == 0:
        # 语料全落在「主场」格：方向和能力都对得上，没有要补的。原来这里会
        # 掉进末行打出「『可以靠学』(0) 是主要矛盾——照常出学习计划」，
        # 而 /job-upskill 按这句决定走向——对着 0 个缺口开学习计划。
        return ("这批评估里没有明显的缺口格（基本都是「主场」）——"
                "学习计划没有要补的，把精力放在投递和面试准备上")
    if n_pick >= max(n_learn, 1):
        return (f"「选岗问题」({n_pick}) ≥「可以靠学」({n_learn}) —— "
                "先别急着开学习清单：你不缺技能，缺的是把简历投到行业经验对得上的"
                "地方。先调搜索词更划算：跑 /job-setup --section search"
                + _off_hint(box, key=PICK))
    return f"「可以靠学」({n_learn}) 是主要矛盾 —— 照常出学习计划"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="差距分四格：学习问题还是选岗问题。")
    ap.add_argument("--list", metavar="格名",
                    help=f"列出某一格的岗位（{HOME}/{PICK}/{LEARN}/{OFF}）")
    ap.add_argument("--user", help=_cli.HELP_USER)
    ap.add_argument("--applied", action="store_true",
                    help="只算真投出去的那批（给 /job-upskill --applied 用）")
    args = ap.parse_args(argv)

    # 不判存在就直接 read_text 会在**全新 clone 上**抛 FileNotFoundError 栈回溯
    # ——新用户敲错顺序是常态，第一次撞见的不该是 traceback。
    user = _cli.pick_user(args.user or "", root=ROOT)
    p = ROOT / "users" / user / "job_scraper" / "seen_jobs.json"
    if not p.is_file():
        print(_cli.no_store(p, then="/job-scrape 与 /job-rank"))
        return 0
    # 两代格式都要认（正本 `_cli.seen_of`）：老库顶层直接就是岗位字典，
    # 写成 `.get("seen", {})` 的话它会安静地当成「一个岗都没有」。
    # 同日在 `doctor.py`、`build_dashboard.py` 各抓到一例，这是第三处。
    seen = _cli.seen_of(_cli.read_json(p))
    scope = ""
    if args.applied:
        # **别另写一套「哪些算投过的」。** 复用 `archive.collect_applied_keys`，
        # 它用的又是面板同一个 `match_tracker` —— 这个仓库为「同一个岗有多把钥匙」
        # 付过五次学费。
        from archive import collect_applied_keys
        keys = collect_applied_keys(user, seen)
        if not keys:
            print(f"{user} 还没有投出去的岗 —— `--applied` 没有语料可算。"
                  "去掉它就是拿所有评过分的岗算")
            return 0
        seen = {k: v for k, v in seen.items() if k in keys}
        scope = "（只算投过的那批）"
    box = split(seen)
    total = sum(len(v) for v in box.values())

    if args.list:
        rows = box.get(args.list)
        if rows is None:
            print(f"没有叫「{args.list}」的格。可选：{HOME}/{PICK}/{LEARN}/{OFF}")
            return 2
        print(f"{args.list}（{len(rows)} 个）——{LABELS[args.list]}\n")
        for st, dm, e in sorted(rows, key=lambda r: -r[0]):
            print(f"  专业能力 {st:>3} · 行业经验 {dm:>3}  "
                  f"{(e.get('title') or '')[:26]:<28} {(e.get('company') or '')[:16]}")
        return 0

    # **口径要自报。** 面板那边同一句话数出 687（它不排任何状态，问的是
    # 「市场里有多大一块对得上你」）。两个数都对，但两处都只说「可回读两笔
    # 分数的评估」的话，用户只会以为其中一个坏了。
    if not scope:
        scope = "（评过分、你没点掉的那些）"
    print(f"可回读两笔分数的评估：{total} 份（用户：{user}）{scope}")
    print(f"分界：专业能力 ≥{STACK_OK} · 行业经验 ≥{DOMAIN_OK}"
          "（取自框架各维自身的分档，不是从样本凑的）\n")
    for k in (HOME, LEARN, PICK, OFF):
        n = len(box[k])
        bar = "█" * round(n / max(total, 1) * 28)
        print(f"  {k:<6} {n:>3}  {bar}")
        print(f"         {LABELS[k]}")
    print(f"\n结论：{verdict(box)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
