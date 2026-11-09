# -*- coding: utf-8 -*-
"""哪些判断现在不该信了 —— 该重跑一遍的岗，一条队列，两个理由。

    python tools/stale_materials.py           # 该重跑的（翻档的 + 当时没读全的）
    python tools/stale_materials.py --all     # 连只是分数变了的一起列

## 两个理由

- **翻档** —— 材料写的判定和职位库现在的判定不是同一档。口径变过，材料停在旧的。
- **当时没读全** —— 评估自己招了「本贴任职要求段未展示完」「没抓到正文」这类话。
  这一档实测命中 2/2：某连锁餐饮公司那个岗（同一份 JD 挂四处）读全后从「值得投」
  翻成硬门 FAIL，某高管岗从 70 分翻到 65 分换档 —— 两份评估的硬性条件表里
  都写着自己没读全，却照样给了 PASS。

  ⚠️ **「JD 未写年限下限」这类话不算**，尽管长得很像：那是**结论**（我读了，
  它没写），不是失明。第一版把 `audit_pipeline._NEGATIVE_CLAIM` 那一支抄了进来，
  于是报出 86 个，逐个查下来 **0 个是真的**。词表见 `_BLIND` 上面那段。

  ⚠️ **「旧」不能当判据。** 口径文件（`04-job-evaluation.md`、`tools/scoring.py`）
  改一次措辞就刷新时间戳，据此重判等于宣布全部 1800 个岗作废 —— 那不是队列，
  是弃疗。所以只收**有具体缺口**的那些。

  JD 在不在详情库里只影响**重跑时要不要先抓**（行末会写出来），不影响该不该重跑
  —— `/job-apply` 本来就会去抓。

## 重跑过的怎么出队

重跑完的评估里要有一行 `重跑日期：YYYY-MM-DD`，这里据它出队。

- **不能靠「说明里还提不提那句自陈」判**：翻案说明一般要引用原话，那样队列
  永远排不空，而排不空的队列就成了「等」（`AGENTS.md` 明禁）。
- **戳落在 `evaluation.md`，不落在职位库**：写它的是 `/job-apply`，
  而那条命令**不依赖 Python**（README 与 SETUP 都这么承诺），
  让它去改一份 JSON 就毁掉了那个承诺。这个文件本来就有
  `综合得分：` / `### 结论：` 两个结构化落点，这是第三个。

## 为什么需要它

判定口径会变：薪资维改成查表、专业减分补成字段、硬门名归正 —— 每一次改动都可能
让一个岗换档。而**材料是在改动之前出的**：`evaluation.md` 里那张表、那个综合分、
那句结论，全停在旧口径上。用户打开它，看到的是一份自洽但过时的判断。

已投的不算（发都发出去了，改它没有意义），已下线、标了不投的也不算。

## 判据：拿存档和库对，不解析订正注脚

`evaluation.md` 里的分与判词 vs 职位库里现在的 —— 两边不一致就是「材料按旧口径出的」。
不去 grep 依据里的「⚠️ 订正」那句话：那是**散文**，写法随人变，
而这两个数是结构化的。同一课 `scoring.adjust_of` 记过一次
（减分只写在散文里等于没减）。

⚠️ **翻了档的排在前面。** 82 → 79 只是数变了，材料照发无妨；
而「值得投 → 可以考虑」意味着这份材料本来就不该发 —— 两者不是一个紧急程度。
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
import build_dashboard as bd  # noqa: E402  深评的读法只有它那一份

#: 「综合分 / 结论怎么从深评里读出来」**这里原来自己写了一套**：
#: 四条正则（`_SCORE` / `_NOSCORE` / `_VERDICT` / `_VERDICT_INLINE`），
#: 说明里还记着「至少四代，只认第一种时 37 份读不出来」。
#:
#: 而 `build_dashboard.parse_evaluation` 学的是同一课、落在另外四种上，
#: 它的说明写着「这是同一类 bug 的第三次…解析器只认一种，一部分真实数据
#: 就静默解析成空」。**两边各认各的**，实测 2026-08-31：
#:
#:     综合分  3 份这边读不出、面板读得出（「约 62/100」、写成加权算式的）
#:     结论    5 份这边读不出、面板读得出
#:
#: 而读不出来在这里的后果是 `skip["评估文件读不出分或结论"] += 1; continue`
#: —— 那几个岗**静默掉出重跑队列**，材料翻了档也没人再提。
#: 2026-08-31 四条一起删，改走那一份（`writeback.py` 早就是这么做的：
#: 「解析走它，别造第二份」）。


#: 评估**自己招认**当时没读到 JD 的那些话。只认自陈，不去猜 ——
#: 「这份评估看着单薄」是判断，「本贴任职要求段未展示完」是事实。
#:
#: ⚠️ **「JD 未写年限下限」这类话不算，尽管它长得很像。** 那是**结论**
#: （我读了，它没写），不是失明；而且 JD 既然已经在详情库里，这个结论是**可核的**，
#: 更没有重跑的理由。第一版把 `audit_pipeline._NEGATIVE_CLAIM` 那一支抄了进来，
#: 于是 2026-08-30 报出 **86 个「当时没读全」，逐个查下来 0 个是真的** ——
#: 抄来的正则带着原处的形状，却在这里换了含义。
#:
#: 那一支在 `audit_pipeline` 里问的是**另一个方向**：「你说 JD 里没写，
#: 可库里根本没有这份 JD，你凭什么说」。JD 在库里时它就不成立了 ——
#: 同一个正则，两个方向，只有一个方向属于这里。
_BLIND = re.compile(
    r"未展示完|页面截断|截断未读|没抓到(?:正文|JD)|正文没抓|详情未取|未取到正文|"
    r"列表页信息")


#: 重跑过的标记。**落在 evaluation.md 里**，因为写它的 `/job-apply` 不依赖
#: Python —— 让它去改职位库那份 JSON 就毁掉了那个承诺。这个文件本来就有
#: `综合得分：` / `### 结论：` 两个结构化落点，这是第三个。
#:
#: ⚠️ **前缀里那个 `-` 是 2026-08-31 补的，此前不认。** 而 `- ` 正是这份
#: 文件里所有同类行的写法（`- 评估日期：`，`04` 的输出格式规定的）——
#: 写手照着旁边那行写成 `- 重跑日期：…`，这条就认不出来，于是那个岗
#: **永远出不了队**：`job-auto.md` 收尾自己写着那个症状「下一轮的第 0 小步
#: 会把同样几个岗原样再跑一遍，而且每一轮都会」，而它把病因归在
#: 「重跑完忘了留那一行」上 —— 留了也没用。
#:
#: 同一个坑 `_EVAL_DATE` 踩过一次并修好了（「3 份写了日期却没带列表符，
#: 当天新出的深评对所有按日期分析的检查全部隐形」），**这一行在它隔壁，
#: 没跟着改**。两处的前缀集合现在一样，由
#: `test_it_reads_the_same_shape_as_the_queue` 钉着。
_REREAD = re.compile(r"^[-*#\s]*重跑日期[：:]\s*\d{4}-\d{2}-\d{2}", re.M)


def in_file(text: str) -> tuple:
    """评估文件里写的 `(综合分, 结论)`。

    读不出分返回 `None` —— 但**硬门 FAIL 那一档本来就没有分**，
    那时返回的 `None` 是事实，不是解析失败；由调用方看结论那半边决定。
    """
    pe = bd.parse_evaluation(text)
    try:
        score = int(str(pe.get("score")).strip())
    except (TypeError, ValueError):
        score = None
    return score, (pe.get("verdict") or "").strip()


def _band(verdict: str) -> str:
    """判词里那个档名。认不出就原样返回（宁可报出来给人看，不静默当成一致）。"""
    v = _cli.strip_triage(verdict)
    for b in _cli.VERDICTS:
        if v.startswith(b):
            return b
    if v.startswith(("硬门", "不满足")):
        return "硬门 FAIL"
    return v


def plan(user: str, out_urls: set | None = None) -> tuple[list, dict]:
    """`out_urls` 给的是「已投 / 不投 / 已下线」那批的规范化链接。

    不给就自己去 `web/public/data.json` 里读 —— 命令行单跑时那是最省事的来源。
    **但导出器不能走那条**：它自己就是写这份文件的人，读它等于拿上一轮的结果
    算这一轮，而且成环。所以它把手里那份现算的集合传进来。
    """
    import build_dashboard as bd
    import jd_store
    _sj = ROOT / "users" / user / "job_scraper" / "seen_jobs.json"
    seen = _cli.seen_of(_cli.read_json(_sj))
    _cli.stop_on_unreadable_rows(seen, _sj)
    byurl = {_cli.norm_url(v.get("url") or ""): v for v in seen.values() if v.get("url")}
    if out_urls is None:
        out_urls = set()
        snap = _cli.dashboard_dir(user, ROOT) / "data.json"
        if snap.is_file():
            d = json.loads(snap.read_text(encoding="utf-8"))
            out_urls = {_cli.norm_url(j.get("url") or "") for j in d.get("jobs", [])
                        if j.get("applied") or j.get("skipped") or j.get("expired")}
    apps = ROOT / "users" / user / "documents" / "applications"
    rows, skip = [], {"已投/不投/已下线": 0, "评估文件读不出分或结论": 0,
                      "两边一致、也没自陈漏读": 0, "库里找不到": 0,
                      "自陈漏读、但已经重跑过": 0}
    for a in bd.find_applications(apps):
        f = apps / a["dir"] / "evaluation.md"
        if not (a.get("url") and f.is_file()):
            continue
        nu = _cli.norm_url(a["url"])
        if nu in out_urls:
            skip["已投/不投/已下线"] += 1
            continue
        v = byurl.get(nu)
        if v is None:
            skip["库里找不到"] += 1
            continue
        text = f.read_text(encoding="utf-8")
        fs, fv = in_file(text)
        ss = v.get("rank_score")
        sv = _cli.strip_triage(v.get("rank_verdict"))
        # 硬门 FAIL 那一档没有分，两边都该是 None —— 那不是「读不出」。
        if not fv or (fs is None and _band(fv) != "硬门 FAIL"):
            skip["评估文件读不出分或结论"] += 1
            continue
        # **只比档名，不比括注。** 一边写「跳过（这家的这个岗已经投过）」、
        # 另一边写「跳过」是同一个判定 —— 按整串比会把它报成翻档，
        # 而「翻档」这个词的全部价值就在于它意味着「这份材料本来不该发」。
        # 第二个入队的理由：评估自己招了当时没读到 JD。只数自陈，
        # 不去猜哪份看着单薄 —— 判据必须是可核的事实。
        blind = len(_BLIND.findall(text))
        # **重跑过的要出队。** 重跑时按 `job-apply.md` 要写翻案说明，而说明里
        # 一般会引用原来那句自陈 —— 于是同一个岗永远命中、面板上那个数永远不降。
        # 队列排不空比没有队列更糟（那就成了「等」，`AGENTS.md` 明禁）。
        # 判据是**结构化的一个字段**，不是去 grep 说明里的措辞：散文写法随人变，
        # 同一课 `scoring.adjust_of` 记过一次。
        if blind and _REREAD.search(text):
            blind = 0
            skip["自陈漏读、但已经重跑过"] += 1
        # JD 在不在库里只影响**重跑时要不要先抓**，不影响该不该重跑。
        # 第一版拿它当排除条件（理由写的是「重跑也读不到新东西」），那是
        # 一道自己发明的闸门：`/job-apply` 本来就会去抓 JD，
        # 而「浏览器不设任何自定的闸门」是 2026-08-27 的用户裁定。
        in_store = bool(blind) and jd_store.has_body(
            jd_store.load(user, a["url"], v.get("title") or ""))
        flip = _band(fv) != _band(sv)
        if fs == ss and not flip and not blind:
            skip["两边一致、也没自陈漏读"] += 1
            continue
        rows.append({"dir": a["dir"], "url": a["url"], "file": (fs, fv),
                     "store": (ss, sv), "flip": flip, "blind": blind,
                     "jdReady": in_store,
                     "why": "翻档" if flip else
                            (("当时没读全" if in_store else "当时没读全，得先抓 JD")
                             if blind else "只是分数变了"),
                     "title": (v.get("title") or "")[:26]})
    rows.sort(key=lambda r: (not r["flip"], -r["blind"], -(r["store"][0] or 0)))
    return rows, skip


def main(argv=None) -> int:
    import export_web_data as ex
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--all", action="store_true",
                    help="连只是分数变了的一起列")
    ap.add_argument("--user", default="", help=_cli.HELP_USER)
    a = ap.parse_args(argv)
    user = _cli.pick_user(a.user or "", root=ROOT)
    rows, skip = plan(user)
    # 默认只列**要动手的**：翻档的、当时没读全的。只是分数变了的照发无妨。
    show = rows if a.all else [r for r in rows if r["flip"] or r["blind"]]
    flip = [r for r in rows if r["flip"]]
    blind = [r for r in rows if r["blind"] and not r["flip"]]
    drift = len(rows) - len(flip) - len(blind)
    print(f"该重跑一遍的岗（用户：{user}）")
    ready = sum(1 for r in blind if r["jdReady"])
    print(f"  换了档的 {len(flip)} 个；当时没读全的 {len(blind)} 个"
          + (f"（{ready} 个 JD 已入库、直接重判，{len(blind) - ready} 个要先抓）"
             if blind else "")
          + (f"；另有 {drift} 个只是分数变了（--all 看）"
             if drift and not a.all else ""))
    print("  跳过：" + "、".join(f"{k} {n}" for k, n in skip.items() if n))
    if not show:
        print("\n没有要重跑的 —— 材料和现在的判断一致，也没有当时漏读的。")
        return 0
    print()
    for r in show:
        fs, fv = r["file"]
        ss, sv = r["store"]
        mark = "★" if r["flip"] else " "
        # 存盘值可能是「硬门 FAIL (…)」这类内部写法，上屏前过 ex.plain() 译成人话。
        if r["flip"] or fs != ss:
            tail = (f"材料写 {fs} {ex.plain(str(fv))}　→　"
                    f"现在 {ss} {ex.plain(str(sv))}")
        else:
            # 漏读那一档两边本来就一致 —— 再印一遍「63 → 63」是废话，
            # 用户要知道的是**漏了几处**、以及**现在判的是什么**。
            tail = (f"当时有 {r['blind']} 处没读到 JD"
                    + ("（库里有，直接重判）" if r["jdReady"] else "（还得先抓）")
                    + f"；现在判 {ss} {ex.plain(str(sv))}")
        print(f"  {mark} {r['title']:<28}{tail}")
    print("\n全部重跑一遍（判断和材料都会跟着重出）：")
    print("    /job-apply --stale")
    # **和自检那一档说的不是一件事，这里要说破。**
    #
    # 实测 2026-08-30：这批 7 个里 **6 个自检也点到了**（缺小节 / 没写投前必问），
    # 而自检收尾给的是「一次补完：`/job-apply 全部`」—— 那条走的是补漏那条路，
    # **只补缺的那一节**，判断原样留着。跑完它的人会以为这 6 个也处理了。
    #
    # 两个动作的差别不是措辞：那边补一节，这边要把职位描述读回来重判一遍。
    print("  ⚠ 这几个自检那一档多半也会点到（缺小节之类）。那边的"
          "「一次补完 /job-apply 全部」只补缺的那一节，判断原样留着 ——"
          "这里要的是整份重跑。")
    print("\n只想先看一个：")
    for r in show[:2]:
        print(f"    /job-apply {r['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli.run_cli(main))
