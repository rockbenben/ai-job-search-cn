#!/usr/bin/env python3
"""把投递目录里的深评结果机械地写回职位库——写回靠工具，不靠纪律。

## 要解决什么

同一个岗的分数存在两处：`documents/applications/<岗>/evaluation.md`（深评档案，
给人读）和 `job_scraper/seen_jobs.json`（库，给 `/job-rank` 选岗、预筛、`/job-upskill` 读）。
`apply.md` 要求深评产出后写回库，但那是**流程指令**——AI 漏一步，两处就分叉。

更糟的是兜底把分叉藏住了：`resolve_score` 让面板永远显示深评值（对的），
于是没人发现库里躺着旧粗筛分。实测 4 个 2026-07 底的目录分叉了四个月，
其中一个岗以「76/强匹配」在库里当了四个月的全库第一，深评实际是 62。
**两套真相各自都显得对，比单纯的错更难发现。**

所以：**发现交给导出器**（每次刷新面板自动对账、不一致就自嚷，见
`export_web_data.py`），**修复交给这里**（机械解析、幂等写回）。补账不再是人肉活。

## 它做什么

对每个带 `evaluation.md` + `posting.md` 的投递目录：

1. 用面板同一套解析（`build_dashboard.parse_evaluation` / `export_web_data.
   parse_dimensions`）读出分、判词、四维——**不写第二份解析器**，那正是分叉的来路。
2. 先做**判词天花板体检**（`04-job-evaluation.md`：技能 ≥80 才可强匹配，60-79 最高
   值得投，40-59 最高可以考虑，<40 最高不建议）。**文件自己违规的跳过并点名**，
   让人去改文件——文件是档案与事实源，工具不单边篡改它，也绝不把违规值写进库。
3. 与库比对：分、判词（剥「粗筛：」后比）、`evaluated`、**技能维**及其两笔拆解，
   任一不同即分叉。

   ⚠️ **只比技能维，不比另外三维，也不拿三维重算总分。** 这一句原来写的是
   「四维拆解」，与代码不符。实测 2026-10-13 踩到：把评估里 `薪资与职级`
   从 95 改成 90（年包算错了，见 `tests/test_the_annual_package_is_salary_times_months.py`），
   干跑**一条都不报** —— 因为综合得分那一行没动，分还是 75，库里也是 75，
   比对全过。而评估此刻已经自己不一致了：三维合出来是 73.8，它写着 75。
   **只改三维里的任何一维，都要连 `综合得分` 一起改**，否则这道闸门看不见。
4. `--apply` 写回；不加只报告（与 `prescreen.py` 同一惯例：试运行默认）。

顺带清两类库内残留（同一类账）：
- `evaluated` 条目还挂「粗筛：」前缀——深评结论没有粗筛这回事；
- 已评分（非 `new`）条目还挂 `deprioritized`——那是「待评时排队尾」用的。

**`依据` 只报不改。** 它是给人读的散文，重写要判断力 —— 试过按每一维的说明机械
重拼，实测**更差**：某个岗原来的依据点着 JD 原话（「具备互联网保险或保险科技公司的
业务背景……」）和一条专业不符的提醒，重拼之后全没了，换成一串维度名加冒号。
所以这里只**认出**它旧了并点名，改由写深评的那一步做（`/job-apply <职位链接>`）。

零第三方依赖；解析复用本仓库模块。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402
import archive  # noqa: E402  存档路径走它，别造第二份
import build_dashboard as bd  # noqa: E402  解析走它，别造第二份
import export_web_data as ex  # noqa: E402
import gap_split as _gs  # noqa: E402  算式解析走它，别造第二份

#: 判词天花板（`04-job-evaluation.md`「判词天花板」——边界即技能维自身的分档）。
# 词表与档位边界只在 `_cli` 定义一份（2026-08-20 收拢，此前这里自抄一套）。
CAP_BANDS = _cli.CAP_BANDS


def _verdict_moved(in_store, in_file) -> bool:
    """判词真的变了吗。**两边都是硬门 FAIL 就不算变。**

    ## 为什么不能整串比

    `build_dashboard.parse_evaluation` 对硬门 FAIL **只返回「硬门 FAIL」四个字** ——
    它自己的注释写着理由：「门名要 `parse_gates`（在导出器里，反向依赖会成环），
    所以这里只给到「硬门 FAIL」四个字；**带门名的完整写法由 `resolve_score`
    从库里补**」。也就是说**存档那一侧本来就不带门名，库才带**。

    整串比的后果不是误报一次，是 `--apply` 会拿存档的四个字**覆盖**库里
    「硬门 FAIL (候选人明确排除（行业背景硬要求）)」这种完整写法 ——
    **把更全的信息降级成更少的**，而这个仓库刚花了一整轮把那些门名和理由补上
    （`name_the_exclusion.py`）。2026-08-30 某连锁餐饮公司那份 JD（同一份挂了四处）一次翻案 4 个岗时撞见。

    其余情况照旧整串比 —— 一边是硬门 FAIL、另一边是「值得投」，那是真的变了。

    ## 但「两边都 FAIL」还要再分一次：门名变了算不算

    原来一律「不算漂移」，防的是拿存档那四个字覆盖库里带门名的完整写法。
    **而档位没变、门名变了的情况被一并挡掉了。** 实测 2026-10-15：一条深评
    从「年限门按领域限定不是门」重判之后，理由从
    `硬门 FAIL (工作年限)` 变成 `硬门 FAIL (候选人明确排除)` —— 档位相同、
    **理由整个换了**，而库里一直挂着旧的那个，读的人看到的是一条已经不成立
    的出局理由。

    **但「两边都带门名且不同」这一条要写准**：只有两边**都**带门名、比出来
    不同，才算换了理由。**一边带一边不带不算** —— 那是「更全」与「更少」，
    按 `tests/test_writeback_does_not_downgrade_the_store.py` 的原话，
    拿少的那份覆盖多的就是**降级**，而那一轮刚把门名与理由补回去过。
    """
    a = _cli.strip_triage(in_store)
    b = _cli.strip_triage(in_file)
    if a == b:
        return False
    fa = a.startswith(_cli.GATE_FAIL_PREFIXES)
    fb = b.startswith(_cli.GATE_FAIL_PREFIXES)
    if fa and fb:
        # 两边都判了硬门。档位相同不算漂移；门名**两边都有且不同**才算 ——
        # 一边有名字一边没有，是「更全 vs 更少」，不许拿少的盖多的。
        na, nb = _gate_name_of(a), _gate_name_of(b)
        return bool(na and nb and na != nb)
    return True


def _gate_name_of(verdict: str) -> str:
    """`硬门 FAIL (工作年限)` → `工作年限`；没有括号就返回空串。"""
    m = re.search(r"[（(]([^）)]*)[）)]", str(verdict or ""))
    return (m.group(1).strip() if m else "")


def cap_for(skill: int) -> str:
    for band, floor in CAP_BANDS:
        if skill >= floor:
            return band
    return "不建议"


def band_rank(v: str) -> int:
    order = _cli.VERDICTS                 # 顺序即档序，正本在 _cli
    return order.index(v) if v in order else len(order)


#: 「硬性条件没过」的判据——框架规定这类评估**不打分**，所以它没有综合得分是对的。
#: `read_dir` 对它返回 None（取不到整数分），但那不是「读不出来」，是「本来就没有分」。
#:
#: **判据只此一份，在 `build_dashboard` 里。** 这里原来自己写了一遍，于是
#: 面板那条路（`parse_evaluation`）压根不知道有「硬性条件没过」这种结论，
#: 把翻案说明里引用的旧判词当成了判词——两个工具对同一份存档给出不同结论，
#: 而 export 逐次催「跑 writeback 补账」、writeback 跑完说「一致」，用户在中间死循环。
is_gate_fail = bd.is_gate_fail


#: `依据` 里 ⚠ 开头的那几句**不是评估写的**，是别处加上去的提醒：竞业范围
#: （`job-rank.md` Step 2「加在 `依据` 的开头」）、同一家投过、这一维粗筛没信号
#: 深评必核。实测 2026-08-27：249 条深评条目里 110 条带着这类句子。
#: 重写 `依据` 时原样留在最前面 —— 评估正文未必重述它们。
_WARN = re.compile(r"⚠[^。]*。?")


#: 「`依据` 旧了」不能靠**字不一样**判 —— 库里那些依据是历次深评手写的正文，
#: 和按维度拼出来的说明本就不同字，拿「不同」当判据会把它们一次性抹平
#: （第一版试运行当场报出要改 249 条）。所以只认**能证明它旧了**的两种形状：
#:
#:   1. 它点名某一维给了多少分，而库里存的不是那个数；
#:   2. 它还写着「预筛 / 未抓 JD / 粗筛」，而 `来源` 已经标成深评回写 ——
#:      **且它自己一次都没提「深评」**。
#:
#: ⚠️ 最后那半句是复核那批 18 条时补的，补之前形状 2 **全是误报**。摊开逐条看：
#: **18 条全都含「深评」二字**，讲的正是深评与粗筛的关系 ——
#:
#:     深评翻案（粗筛 68 值得投 → 深评 67 可以考虑）。判词被技能 58 压下来。
#:     这家的工作强度粗筛没有信号，深评读完 JD 才补上。
#:
#: 那不是「残留的、抓 JD 之前的口径」，那**正是深评该写的东西**：
#: 它解释的就是面板上当前这个分怎么来的。而报文写着
#: 「用户读到的是在解释别的数字」—— 对这 18 条来说，那句话本身才是假的。
#:
#: 真正的残留长什么样：通篇按粗筛口径讲、**一次都没提深评**。
#: 收窄之后这一形状归零，检查只剩形状 1（点名某维给了多少分，而库里不是）。
#:
#: 实测活动用户 2026-08-27：249 条深评条目里，形状 1 有 1 条
#: （写「发展这一维给 85」，库里是 72）、形状 2 有 18 条。
#: 正本在 `_cli`（`scoring.rewrite_pay_said` 判同一件事，2026-10-12 那次事故之后
#: 两侧合成一份）。本模块的别名留着：下面那圈注释与它的 docstring 都指着这个名字。
_DIM_SAID = _cli.DIM_SAID
_DIM_FULL = _cli.DIM_FULL
_PRESCREEN_WORDS = re.compile(r"未抓 ?JD|预筛|粗筛")


def _basis_is_stale(old: str, b: dict) -> bool:
    for m in _DIM_SAID.finditer(old or ""):
        cur = b.get(_DIM_FULL[m.group(1)])
        if isinstance(cur, int) and cur != int(m.group(2)):
            return True
    return bool(_PRESCREEN_WORDS.search(old or "")
                and "深评" not in (old or "")
                and "writeback.py" in str(b.get("来源") or ""))


def read_dir(d: Path):
    """`(data, reason)` —— 读得全时 `data` 是 (url, score, verdict, dims, pair, notes)、
    `reason` 为空；读不全时 `data` 为 None、`reason` 一句话说清卡在哪一步。

    **为什么要回 reason。** 原来读不全一律裸返回 None，调用方只能印一句猜测
    「多半是缺 posting.md，或评估里没有综合得分/结论」——把四种毛病并成一句话，
    用户（和 AI）只能逐个目录手工排查。实测 2026-08-17：一轮报了 3 个目录读不出来，
    三个都是同一个毛病（分数行写成了 `72 − 5（专业减分）= 67/100`），
    但那句猜测把人先引去查 posting.md 了。**报错要指哪一步，不是列可能性。**

    硬门 FAIL 的评估按框架规定没有分数，但它**照样要写回**：score 为 None、
    判词为「硬门 FAIL (门名)」。原来这里对它返回 None，于是这种评估永远进不了库
    ——而 export 的分叉提醒照样逐次催「跑 writeback 补账」，本工具跑完却说
    「库与深评档案一致」：两个工具对同一个目录互相踢皮球，用户在中间死循环。
    """
    ev_f, po_f = d / "evaluation.md", d / "posting.md"
    if not ev_f.is_file():
        return None, "没有 evaluation.md"
    if not po_f.is_file():
        return None, "缺 posting.md（职位链接从那里取）"
    m = re.search(r"链接[：:]\s*(\S+)", po_f.read_text(encoding="utf-8"))
    if not m:
        return None, "posting.md 里找不到「原始链接：<URL>」那一行"
    text = ev_f.read_text(encoding="utf-8")
    if is_gate_fail(text):
        gate = next((g["name"] for g in ex.parse_gates(text)
                     if g.get("state") == "fail"), "")
        verdict = f"硬门 FAIL ({gate})" if gate else "硬门 FAIL"
        return (m.group(1), None, verdict, {}, None, {}), ""
    pe = bd.parse_evaluation(text)
    try:
        score = int(str(pe.get("score")).strip())
    except (ValueError, TypeError):
        return None, "evaluation.md 里读不出综合得分（那行要写成「综合得分：NN/100」）"
    verdict = (pe.get("verdict") or "").strip()
    if not verdict:
        return None, "evaluation.md 里读不出判词（结论段要出现五档中文之一）"
    rows = ex.parse_dimensions(text)
    dims = {x["name"]: x["score"] for x in rows
            if isinstance(x.get("score"), int)}
    notes = {x["name"]: (x.get("note") or "").strip() for x in rows}
    # **走 `gap_split.FORMULA`，不自己写第二份。** 本文件开头那句
    # 「读出分、判词、四维——**不写第二份解析器**，那正是分叉的来路」
    # 说的就是这里，而这一行原来正是那第二份，且比正本窄：
    #
    #     正本（gap_split.FORMULA）  专业能力 / 专业 / 技术栈  ×  业务域 / 业务领域 / 行业经验
    #     这里（2026-08-25 之前）    专业能力                ×  业务领域 / 业务域
    #
    # 差的那两组不是假想：`AGENTS.md`「给用户看的措辞」把打分算式的显示形态
    # 定成了「专业能力 88 · **行业经验** 65」，于是新写的深评自然往「行业经验」
    # 那个词飘 —— 而这一行读不出它，`四维` 就静默保持旧值。
    # 「技术栈」则是 3.7.1 之前的旧名，存量里还有。
    pair = _gs.FORMULA.search(text)
    return (m.group(1), score, verdict, dims, pair, notes), ""


def _gate_states(had: dict) -> dict:
    """库里 `rank_breakdown.硬性条件` 那些值 → 与 `parse_gates` 同一种状态键。

    库里存的是 `PASS` / `FAIL` / `FLAG` / `不适用`（`export` 的
    `gates_from_breakdown` 读的就是这几种），而 `parse_gates` 给的是
    `pass` / `fail` / `flag` / `na`。**两边不同形**，不归一就没法比。
    """
    out = {}
    for name, raw in (had or {}).items():
        t = re.sub(r"[*\s]", "", str(raw or ""))
        if t in ("PASS", "满足", "通过"):
            out[_cli.gate_of(name) or name] = "pass"
        elif t in ("FAIL", "不满足", "不通过"):
            out[_cli.gate_of(name) or name] = "fail"
        elif t in ("FLAG", "要留意"):
            out[_cli.gate_of(name) or name] = "flag"
        else:
            out[_cli.gate_of(name) or name] = "na"
    return out


#: `parse_gates` 的状态键 → 存盘那张表用的写法。**只用这四种**：
#: `export.gates_from_breakdown` 读的就是它们，写别的等于写一份读不出来的。
_GATE_TOKEN = {"pass": "PASS", "fail": "FAIL", "flag": "FLAG", "na": "不适用"}


def _gate_txt(gates: dict) -> str:
    """那张表印给人看的一行。`plain()` 收的是字符串，dict 得先摊开。"""
    return "；".join(f"{n} {ex.plain(str(v))}"
                     for n, v in sorted((gates or {}).items()))


def _gate_is_fail(raw) -> bool:
    """库里那张表的某一格是不是判了 FAIL（认两种写法：`FAIL` 与「不满足」）。"""
    t = re.sub(r"[*\s]", "", str(raw or ""))
    return t.startswith("FAIL") or t.startswith("不满足") or t.startswith("不通过")


def _eval_text(d) -> str:
    """这个投递目录里的 `evaluation.md` 全文。读不到返回空串。"""
    p = d / "evaluation.md"
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _total_years(user: str) -> int:
    """资料里的**总年限**。读不出当 0 —— 那时判据不会触发，而不是乱拒收。"""
    yrs = _cli.candidate_years(user, ROOT)
    return max(yrs) if yrs else 0


def pick_entry(cands: list, dirname: str):
    """一个 URL 下有多条时，靠目录名里的职位名认。返回 (条目, 说不清的原因)。"""
    if len(cands) == 1:
        return cands[0], ""
    hit = [c for c in cands if (c.get("title") or "").strip()
           and (c.get("title") or "").strip() in dirname]
    if len(hit) == 1:
        return hit[0], ""
    titles = "、".join((c.get("title") or "（无职位名）") for c in cands)
    return None, (f"这个链接下有 {len(cands)} 个岗（{titles}），"
                  f"从目录名认不出是哪一个——把目录名改成含完整职位名再跑")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="把深评结果从投递目录写回职位库。不加 --apply 就是试运行。")
    ap.add_argument("--apply", action="store_true", help="真的写回 seen_jobs.json")
    ap.add_argument("--user", help=_cli.HELP_USER)
    args = ap.parse_args(argv)

    user = _cli.pick_user(args.user or "", root=ROOT)
    p = ROOT / "users" / user / "job_scraper" / "seen_jobs.json"
    if not p.is_file():
        raise SystemExit(_cli.no_store(p))
    # 记下版本戳：写回前要确认这期间没人动过它（见 `_cli.atomic_write` 的 expect）
    store, _stamp = _cli.load_json_stamped(p)
    # 容忍老格式（顶层直接 {url: {...}}）——export 对同一文件就是这么宽容的，
    # 两个工具对一个文件的宽容度不一致，老库会在这里裸 KeyError。
    seen = _cli.seen_of(store)
    _cli.stop_on_unreadable_rows(seen, p)
    # **一个 URL 可能挂着多个岗。** 51job 实测同一详情 URL 下有两条不同职位，
    # 所以全仓的一对一键是 `stable_id(url, title)`，不是 url（`serve.find_entry`、
    # `jd_store.key_for`、`export_web_data.stable_id` 都这么算）。
    # 这里原来是 `by_url.setdefault(url, v)`——**只留第一条**，于是 B 岗的深评会被
    # 写到 A 岗身上，而 export 的漂移检查照旧报 B 没同步，两个工具从此互相打架。
    # 现在按 url 收成组，落到多条时不猜：用目录名（`<公司>_<岗位>`）里的职位名
    # 去认，认不出就拒收并说清楚，把静默写错换成一条能处理的提示。
    by_url: dict[str, list] = {}
    for v in seen.values():
        by_url.setdefault(v.get("url") or "", []).append(v)

    # **存档里也算「还在」。** 归档不是删除（`archive.py` 自己这么写），而这一格
    # 只查热库 —— 于是 `archive.py --apply` 归档掉的岗，它的材料目录立刻被报成
    # 「职位链接在库里找不到（可能岗位记录被删过）」。
    # 实测 2026-10-12：一轮收尾 `archive` 归了 817 个，紧接着 `writeback` 就开始
    # 报「记录被删过」。**没删，是搬走了，而那句话把归档说成了删除** ——
    # 用户按它去查「谁删了我的记录」，查不到，因为没人删。
    archived_urls = set()
    _sj, _arc = archive.paths(user)
    if _arc.is_file():
        _arc_seen = _cli.seen_of(
            json.loads(_arc.read_text(encoding="utf-8")))
        archived_urls = {_cli.norm_url(e.get("url") or "")
                         for e in _arc_seen.values() if e.get("url")}


    apps = ROOT / "users" / user / "documents" / "applications"
    drift, orphan, unreadable, gone = [], [], [], []
    #: 拒收有两种**互不相干**的原因：认不出是哪个岗（改目录名）与文件自己写高了
    #: （改评估文件）。**分开存** —— 原来共用一个 `refused`，而收尾只印了后者的
    #: 那句「评估文件自身把结论写高了」，于是另一种被指去了完全不对的方向。
    #: 实测 2026-10-15：活动用户 3 条拒收全是前者，而用户读到的是后者的指导。
    refused_ambiguous, refused_cap, refused_years = [], [], []
    if apps.is_dir():
        for d in sorted(x for x in apps.iterdir() if x.is_dir()):
            got, why = read_dir(d)
            if got is None:
                # **读不出来要说出来。** 原来这里是裸 continue，跳过的目录一个字
                # 都不提；全部跳过时还会打印「库与深评档案一致，没有要写回的」——
                # 把「我没看」说成了「都对得上」。实测批量产出的 5 个目录只有
                # evaluation.md 没有 posting.md，五个全被静默跳过，而工具报的是一致。
                # （硬门 FAIL 的评估现在由 read_dir 自己处理，不会走到这里；
                # 走到这里的都是真读不出来的——缺 posting.md 或评估里没有分/结论。）
                if (d / "evaluation.md").is_file():
                    unreadable.append((d.name, why))
                continue
            url, score, verdict, dims, pair, notes = got
            cands = by_url.get(url) or []
            if not cands:
                if _cli.norm_url(url) in archived_urls:
                    gone.append(d.name)       # 搬去了存档，不是「被删」
                else:
                    orphan.append(d.name)
                continue
            e, why_amb = pick_entry(cands, d.name)
            if e is None:
                refused_ambiguous.append(f"{d.name}：{why_amb}")
                continue
            skill = dims.get("技能与经验")
            # 文件自身违反天花板 → 拒收。把违规值写进库等于把病搬家。
            if isinstance(skill, int) and band_rank(verdict) < band_rank(cap_for(skill)):
                refused_cap.append(
                    f"{d.name}：文件写「{verdict}」，但技能 {skill} 这一档最高只到"
                    f"「{cap_for(skill)}」——先改评估文件，再跑本工具")
                continue
            # **年限门把「领域」当成年数判了 → 同样拒收。**
            # `04-job-evaluation.md`「年限门：那个数带不带领域限定」：引文是
            # 「N 年以上 <领域> 经验」而 N ≤ 他总年限时，那道门按总年限判就是过的
            # —— 缺的是那个领域，不是年数，该写进业务领域分，不该一票否决。
            #
            # **这一格原来不在，于是 14 份深评带着同一个错判词写进了库**
            # （实测 2026-10-14），而发现它的是审计——审计是**偶然**撞见的：
            # 它只扫库里的存量，写盘那一刻没人拦。
            # 只有**判了 FAIL** 才轮到那条判据说话 —— 判 PASS / FLAG 的照常写回，
            # 它引了带领域限定的原话是**正常的**（那本来就是原文）。
            _yv, _yr = _cli.years_row(_eval_text(d))
            is_domain, quote = (
                _cli.years_gate_is_domain_only(_yr, _total_years(user))
                if ("FAIL" in _yv and "FLAG" not in _yv) else (False, ""))
            if is_domain:
                refused_years.append(
                    f"{d.name}：工作年限判了「不满足」，可它引的是「{quote}」——"
                    f"那是领域要求，不是年数门槛（04「年限门：那个数带不带"
                    f"领域限定」）。缺的是那个领域，按 04 该写进业务领域分。"
                    f"先改评估文件，再跑本工具")
                continue
            changes = []
            if e.get("rank_score") != score:
                changes.append(f"分 {e.get('rank_score')} → "
                               f"{'无（硬性条件没过，不打分）' if score is None else score}")
            if _verdict_moved(e.get("rank_verdict"), verdict):
                # 存盘值可能是「硬门 FAIL (…)」这类内部写法——上屏前过 ex.plain()
                # 译成人话。词表守卫只扫 print 里的字面量，经变量漏出去它看不见
                # （prescreen 同一处坑的注释说的就是这个）。
                changes.append(f"结论 {ex.plain(e.get('rank_verdict') or '（还没有）')}"
                               f" → {ex.plain(verdict)}")
            if not e.get("evaluated"):
                changes.append("补标已深评")
            # **硬门表也要回写。** 库里那份 `rank_breakdown.硬性条件` 是面板 `gates`
            # 的直读来源，而这一格原来不在回写范围里 —— 于是「深评改了硬门结论、
            # 库没跟着改」会留下一个**自相矛盾**的条目：判词已经是「可以考虑」，
            # 硬门表里还挂着 FAIL，面板会同时印「有一条不满足就别投」和可投判词。
            #
            # 实测 2026-10-15：有一条重判（年限门按领域限定不是门）之后
            # 写回分数与判词都对，只有这张表停在旧的「工作年限: FAIL」，
            # 审计当场报「硬性条件不满足却仍判可投」。此前 464 份里硬门结论
            # 从没被改过，所以这一格第一次被撞上——**而撞上就是一条矛盾**。
            #
            # 口径：整张表按 `evaluation.md` 重放，不做逐门 diff —— 门名与判定
            # 都以那份文件为源（与上面分数、判词、四维分同一个源）。
            _gates_now = {g["name"]: g.get("state") for g in ex.parse_gates(_eval_text(d))}
            _gates_had = dict(e.get("rank_breakdown") or {}).get("硬性条件") or {}
            # **只修「库里说 FAIL、而深评不是 FAIL」的那几道门。**
            #
            # 整张表重放看着更彻底，实测会碰 **107 条**，而其中绝大多数只是
            # 措辞归一（库里 `外包驻场派遣` 满足、正本 `外包/驻场/派遣` PASS）——
            # 门名写法不同就让同一个判定比成了不同。把 107 条存量按一次有损解析
            # 重写，正是这个仓库反复在治的形状。
            #
            # **真正要修的只有一种**：库里挂着 FAIL、深评已经不判它，而判词又是
            # 可投的档 —— 那是**自相矛盾**（面板会同时印「有一条不满足就别投」和
            # 可投判词）。实测 2026-10-15，有一条重判（年限门按领域限定
            # 不是门）之后就是它。
            _flip = {}
            for gname, raw in _gates_had.items():
                canon = _cli.gate_of(gname) or gname
                now = _gates_now.get(canon)
                if now in ("pass", "flag") and _gate_is_fail(raw):
                    _flip[canon] = _GATE_TOKEN[now]
            if _flip:
                changes.append("硬门表 "
                               + "；".join(f"{k} {ex.plain(v)}"
                                          for k, v in sorted(_flip.items()))
                               + "（深评已改，库里还挂着）")
            # **`status` 也要比。** 原来只写分、判词和 `evaluated`，`status` 一直
            # 停在 `new` —— 而 `prescreen.py` 会把它推成 `ranked`。于是「只深评过、
            # 没走过预筛」的岗两边算的不是一回事：导出器按「有分或有判词就算结案」
            # 把它导出（`export_web_data.py`「有判词就是已结案，必须导出」），
            # 计数器和另外五个消费者按 `status == "ranked"` 数「已结案」，**不算它**。
            # 实测 2026-10-14：1353 与 1354 差的就是这一条，五个消费者
            # （`build_dashboard.py`、`audit_pipeline.py`、`fetch_details.py`、
            # `gap_split.py`、`_cli.py`）全都少算同一个岗。
            #
            # **放进比对而不是只放进写入** —— 只写的话这一条永远轮不到：它的分和
            # 判词都已经对得上，漂移检测报不出东西，而它恰恰是唯一错的那一格。
            # `skipped` / `expired` 是另外两种出局，深评不该把它们翻回 ranked。
            if e.get("status") not in ("ranked", "skipped", "expired"):
                changes.append(f"状态 {e.get('status')} → ranked")
            b = e.get("rank_breakdown") or {}
            if isinstance(skill, int) and b.get("技能与经验") != skill:
                changes.append(f"技能拆解 {b.get('技能与经验')} → {skill}")
            # **那两笔拆解也要比。**
            #
            # 本文件开头写着「与库比对：分、判词、`evaluated`、**四维拆解**，
            # 任一不同即分叉」—— 而这里此前只比了合成分（`技能与经验`），
            # 没比它是由哪两个数合成的。**合成分碰巧相等时就 `continue`，
            # 下面那行 `b["四维"] = …` 永远轮不到执行**，`四维` 停在旧值。
            #
            # 实测 2026-08-25：某个岗合成分已经是 74，而 `四维` 还写着
            # `专业能力75×0.6+业务域45×0.4`（算出来是 63）。面板剥掉权重后
            # 显示的就是那两个旧数，`gap_split` 的四格分析读的也是它们。
            # **检测器不看它自己要写的那个字段**，是这一类的通用形状。
            # **比解析出来的那两个数，不比字符串。**
            #
            # 第一版比的是字符串，当场把存量里更全的写法抹平了：
            # `专业能力82×0.6+业务域42×0.4+加分6` 被改写成没有 `+加分6` 的规范式
            # —— 那个后缀是评估里真实存在的信息，检测「不一致」不该顺手删信息。
            # 数没变就别动这一格。
            if pair:
                want = (int(pair.group(1)), int(pair.group(2)))
                have = _gs.read_pair(e)
                if have != want:
                    changes.append(f"两笔拆解 {have or '（还没有）'} → {want}")
            # **`依据` 也要比。** 上面那几项写回之后，`来源` 就写成
            # 「深评（writeback.py 从 evaluation.md 回写）」——而 `依据` 从来没被碰过，
            # 于是这一格标着深评出处、内容却是粗筛那一轮留下的。
            #
            # 实测 2026-08-27（跑 `/job-auto` 出完材料后查出来的）：249 条标着
            # 深评回写的条目里，**18 条**的 `依据` 还写着「预筛」「未抓 JD」「粗筛」，
            # **1 条**点名的维度分和库里存的直接打架（写「发展这一维给 85」，
            # 库里是 72）。这一格会过 `plain()` 进面板短名单行的悬浮提示 ——
            # 用户读到的是一段解释别的数字的话。
            #
            # **只在别的东西先变了时才重写。** 这一条不许自己当触发器：
            # 库里那 249 条的 `依据` 多半是历次深评手写的正文，而这里重建出来的是
            # 按维度拼的说明 —— 两者本就不同字，拿「不同」当分叉判据会把 249 条
            # 手写正文一次性抹平。第一版正是这样，试运行当场报出要改 249 条。
            # 「数没变就别动这一格」在上一条注释里已经写过一次，这里是同一条。
            if not changes:
                continue
            drift.append((d.name, changes))
            if args.apply:
                e["rank_score"], e["rank_verdict"] = score, verdict
                e["evaluated"] = True
                if e.get("status") not in ("skipped", "expired"):
                    e["status"] = "ranked"
                b = e.setdefault("rank_breakdown", {})
                for k in _cli.WEIGHTED_DIMS:      # 正本在 _cli，别造第二份
                    if isinstance(dims.get(k), int):
                        b[k] = dims[k]
                if pair:
                    b["四维"] = f"专业能力{pair.group(1)}×0.6+业务域{pair.group(2)}×0.4"
                b["来源"] = "深评（writeback.py 从 evaluation.md 回写）"
                # **硬门表跟着一张张表一起重放。** 少了这一格，库与深评文件会各说
                # 各的：判词已经是「可以考虑」，硬门表里还挂着 FAIL
                # （实测 2026-10-15，有一条重判之后）。
                #
                # **面板当下看不出来** —— `export_web_data` 优先读 `evaluation.md`
                # 那张表，库里这份只在**没有深评文件**时才被读到。所以它是个
                # 潜伏的不一致：深评一旦被删掉或归档，旧的 FAIL 立刻露出来，
                # 而那时没人会说这是哪来的。
                if _gates_now:
                    _b2 = dict(b.get("硬性条件") or {})
                    _b2.update(_flip)
                    b["硬性条件"] = _b2

    # 库内残留（与目录无关，也是「深评之后没人收尾」的账）
    n_prefix = n_park = 0
    stale_basis = []
    for v in seen.values():
        if _basis_is_stale(str((v.get("rank_breakdown") or {}).get("依据") or ""),
                           v.get("rank_breakdown") or {}):
            stale_basis.append((v.get("title") or "", v.get("url") or ""))
        if v.get("evaluated") and _cli.is_triage(v.get("rank_verdict")):
            n_prefix += 1
            if args.apply:
                v["rank_verdict"] = _cli.strip_triage(v["rank_verdict"])
        if v.get("deprioritized") and v.get("status") != "new":
            n_park += 1
            if args.apply:
                del v["deprioritized"]

    if args.apply and (drift or n_prefix or n_park):
        _cli.atomic_write(p, json.dumps(store, ensure_ascii=False, indent=1),
                          expect=_stamp)

    # ---------- 报告（给人看的措辞，不带内部码） ----------
    verb = "已写回" if args.apply else "待写回（加 --apply 生效）"
    if not (drift or refused_ambiguous or refused_cap or orphan or gone or n_prefix
            or n_park or unreadable or stale_basis):
        print("库与深评档案一致，没有要写回的。")
        return 0
    if unreadable:
        print(f"⚠ {len(unreadable)} 个目录有评估但读不出来，这次没管它们：")
        for name, why in unreadable:
            print(f"  {name}：{why}")
        print("  补齐后再跑一次。")
    if drift:
        print(f"{verb} {len(drift)} 个岗：")
        for name, changes in drift:
            print(f"  {name}：{'；'.join(changes)}")
    if n_prefix or n_park:
        print(f"{verb}的库内清理：结论前缀残留 {n_prefix} 条 · 排序标记残留 {n_park} 条")
    if stale_basis:
        # **只报不改** —— 理由见本文件开头「`依据` 只报不改」那一段。
        #
        # **点名要点还能动的那几个。** 这一段原来印的是名单里的头五个，
        # 命令给的是**第一个** —— 而那一个很可能已经投出去了（实测抽样 5 个：
        # 2 个已投、1 个标了不投、只有 2 个还能发）。指一条敲了也白敲的命令，
        # 比不指更坏：他敲一次、发现没意义，下次整条就不看了。
        # 判定走 `_cli.sendable_state`，和自检那几条同一个住址。
        where = _cli.sendable_state(user, seen)
        live = [(t, u) for t, u in stale_basis if where(u) == "还能发"]
        print(f"⚠ {len(stale_basis)} 个岗的岗位详情里那段解释和分数对不上"
              f"（它说的分不是现在这个数，或者还写着抓 JD 之前的口径）。"
              f"那段字会显示在总览页上，用户读到的是在解释别的数字。")
        show = live or stale_basis
        for t, u in show[:5]:
            print(f"  {ex.plain(t[:30])}")
        if len(show) > 5:
            print(f"  …另有 {len(show) - 5} 个")
        if live:
            print(f"  其中还没投、现在改还有意义的 {len(live)} 个"
                  f"（上面列的就是）。重写那一段：/job-apply {live[0][1]}")
        else:
            print("  这些都已经投出去、标了不投或下线了，改它没有意义。")
    if orphan:
        print(f"⚠ {len(orphan)} 个目录的职位链接在热库和存档里都找不到"
              f"（岗位记录可能被删过）："
              f"{'、'.join(orphan[:3])}{' 等' if len(orphan) > 3 else ''}")
    if gone:
        # **不是故障，但要说出它是什么。** 归档不是删除（`archive.py --apply` 的原话），
        # 而这一格以前把归档说成了「记录被删过」——用户照着去查谁删了记录，
        # 查不到，因为没人删。材料还在，只是那个岗已经出局、搬去存档了。
        print(f"ℹ {len(gone)} 个目录对应的岗已经归档（不是删除，材料还在）："
              f"{'、'.join(gone[:3])}{' 等' if len(gone) > 3 else ''}")
        print("  这些不用管。它们是出局两周以上的岗，存档里分数与结论都原样留着；"
              "想重新判定先跑 python tools/archive.py --revive --apply")
    if refused_ambiguous:
        # **这一支原来没有自己的收尾。** 它和「文件写高了」共用一个 refused，
        # 收尾只印了后者那句，于是这两种人被指去了同一个方向，而其中一个方向
        # 完全不对——认不出是哪个岗，要改的是**目录名**，不是评估文件的内容。
        print(f"✗ {len(refused_ambiguous)} 个目录认不出对应哪个岗，这次没写回：")
        for r in refused_ambiguous:
            print("  " + r)
        print("  改法：把目录名改成含完整职位名，再跑本工具。"
              "（同一个职位链接下挂了多个岗时，只有职位名能认出是哪一个；"
              "猜一个写进库，等于把深评挂到别人的岗位上。）")
    if refused_cap:
        print(f"✗ {len(refused_cap)} 个目录被拒收——评估文件自身把结论写高了：")
        for r in refused_cap:
            print("  " + r)
    if refused_years:
        print(f"✗ {len(refused_years)} 个目录被拒收——"
              "年限门把「领域要求」当成年数判了：")
        for r in refused_years:
            print("  " + r)
        print("  改法：那一条按 04「年限门：那个数带不带领域限定」重判——"
              "领域缺口写进业务领域分，不按硬性条件一票否决。改完再跑本工具。")
    if refused_ambiguous or refused_cap or refused_years:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_cli.run_cli(main))
