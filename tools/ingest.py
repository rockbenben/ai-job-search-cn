#!/usr/bin/env python3
"""把这一轮抓到的候选写进职位库 —— **入库的唯一出口**。

## 为什么要有这个工具

整条流水线上每一步都有工具：额度 `portal_budget.py`、预筛 `prescreen.py`、
正文 `jd_store.py`、补抓 `fetch_details.py`、词表 `query_yield.py`、归档
`archive.py`、写回 `writeback.py`、现算 `score.py`、导出 `export_web_data.py`。

**唯独「把抓到的候选写进职位库」没有**——它是一段流程文档里的散文，
执行者读完自己往 `seen_jobs.json` 里塞。于是判重这一步是**手工**的。

实测代价（2026-10-12，活动用户）：一轮补货入库 362 个新岗，**58 个是热库与存档
同时已有的**，被当新岗插了回去。两份随后各自演化——同一份 JD，一份记
「硬门 FAIL」、一份记「55 可以考虑」，面板上哪个是真的看不出来。

而这**不是第一次**。`workflows/job-scrape.md` Step 4 记着同一形状的前五次：

    裸 URL vs `url#职位名`            30 条重复
    同公司同职位名撞进一个材料目录      催办清不掉
    协议不一致（http vs https）       20 个新岗里 4 个重复
    51job 同一职位号两种路径          9 组
    查重没连存档一起查                28 个已归档的岗被当新岗插回
    连存档一起查了，但比的是键          3.7%（键换过三代没迁过）

规则写得对，守卫也有，**但没有机制**——这正是本仓库反复记的那两课：
「注释不是机制」「规则在，没人验」。本工具把那句散文变成一个入口：
**要入库就走这里**，判重由 `_cli.seen_index` 做，不由执行者做。

## 三道去重，一道比一道宽

按 `job-scrape.md` Step 2 那三道，顺序不能换（宽的放前面会把窄的挡掉）：

1. **「链接 + 职位名」见过**（热库 ∪ 存档，判据是 `_cli.job_token`）
   → 已见过。**只更新 `date`**，别的字段一个字不动（Step 4 那条）。
2. **「公司 + 岗位名」见过**（换了链接的兜底）→ 跳过。
3. **「公司 + 岗位」投过了**（`job_search_tracker.csv`）→ 跳过。

### 第 2 道为什么是「跳过」而不是「当新岗」

**这是用户 2026-10-12 裁的**：同一家公司、同一个岗位名，**换了链接也跳过**。

它原来不是这样。Step 4 写着「同一个岗换了 URL 重新挂出的照旧当新岗处理」，
而 Step 2 写着「公司 + 岗位名已经在库里就跳过」——**同一份文档对同一个输入
给了两条相反的指令**，执行者只能猜。裁的是「宁可漏过一个重挂的岗，
也不要库里多一份说法不一的同一个岗」，与 `prescreen.py` 的「宁可放过不可误杀」
同一个取向。

### 第 3 道眼下从不单独触发，但它不能删

实测 2026-10-12：投递台账里 115 对「公司 + 岗位」，**115 对全都在热库**。
所以第 2 道永远先拦下，第 3 道一道也没独立命中过。

**它仍然要留着**，因为那个「全在」是**当前的巧合**，不是不变量：台账里的岗
一旦被 `archive.py` 收进存档，它就不在热库的 `公司+岗位` 集合里了 ——
而存档只读，第 2 道也就看不见它。届时的唯一拦它的地方就是这一道。
删掉它换来的只是一次「现在没有后果」的干净，赔上的是以后一次静默的重复。

判重时**比链接不比键**：键只是给机器记路的，身份在条目的 `url` + `title` 里。
按键比过一次，实测 2026-10-12（活动用户）：对存档 3156 条只认出 116 条
（`rekey.py` 之前）、**0 条**（换键之后）——那是 `job-scrape.md` Step 4
自己记的第六次事故。

## 新岗写什么

    {"url", "title", "company", "location", "salary", "salaryMonths",
     "eduLevel", "workYears", "compIndustry", "compScale", "compStage",
     "isHeadhunter", "recruiterTitle", "portal", "date", "first_seen",
     "status": "new", "found_by"}

`status` 一律 `new`：入库不做判断，判断是 `prescreen.py`（预筛）和
`/job-rank`（打分）的活。**这里下判断就是第二个真相。**

键是 `_cli.job_key(entry)`（= `stable_id(url, title)`），没有链接的走
`<渠道>_<公司>_<职位名>` 兜底。**两条岗算出同一个键时拒绝写盘**——
那条比任何一条规则都重要：写下去就是静默覆盖掉另一个岗。

## 用法

    python tools/ingest.py --input 本轮.json --query "Agent产品经理" --portal liepin-search
    python tools/ingest.py --input -            # 从标准输入读
    python tools/ingest.py --input 本轮.json ... # 试运行，不写盘

输入是一个 JSON 数组，每项至少要有 `url`、`title`、`company`。
缺 `url` 的走兜底键，但**第 1 道判重对它无效**（没有链接就没有身份）——
那种岗宁可多收一次，`seen_index` 的 docstring 写着同一条取舍。

零第三方依赖。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402

#: 原样搬进新条目的字段。**只搬这几个** —— 其余的一律不猜。
#:
#: 为什么列出来：写进去的东西日后会被 `prescreen.py` 当判据用
#: （`eduLevel` 比学历下限、`salary`/`salaryMonths` 算年包），
#: 漏一个字段的后果是**预筛判据整个失效**，而那不会报错。
#: 不在这张表里的字段要么是抓取当次没有，要么是不该由本工具编。
CARRY = ("url", "title", "company", "location", "salary", "salaryMonths",
         "eduLevel", "workYears", "compIndustry", "compScale", "compStage",
         "isHeadhunter", "recruiterTitle")

#: 「公司 + 岗位名」这一对怎么归一。两边都去空白、脱敏名照原样留着
#: ——`is_anonymous_employer` 的 docstring 记着拿脱敏串当键的后果。
def pair_key(company: str, title: str) -> str:
    return f"{(company or '').strip()}|{(title or '').strip()}"


def load_rows(src: str) -> list:
    """读这一轮的候选。`--input -` 从标准输入。

    **BOM 要剥，而且可能不止一个。** Windows 上 `... | python ingest.py --input -`
    喂进来的是带 BOM 的 UTF-8，实测（PowerShell 5.1 + `python -X utf8`）
    **开头是两个 `﻿`** —— 写一份的编码给一份的解码各加一次。
    JSON 解析器不认它，报出来的是
    `Unexpected UTF-8 BOM (decode using utf-8-sig)` —— 一句与「你喂的到底
    是什么形状的 JSON」毫无关系的话。文件那条用 `utf-8-sig` 读，
    标准输入这条原来只判了一个字符，于是同一个坑只在管道这一种用法上现形。
    `_cli.read_tracker_rows` 的 docstring 记着同一课（台账存成 Excel 导出的
    CSV 时带 BOM，`row.get("date")` 从此返回 `None`，**静默**）。
    """
    if src == "-":
        raw = sys.stdin.read().lstrip("﻿")
    else:
        p = Path(src)
        if not p.is_file():
            raise SystemExit(f"读不到输入文件：{src}")
        raw = p.read_text(encoding="utf-8-sig")
    try:
        rows = json.loads(raw)
    except ValueError as e:
        raise SystemExit(f"输入不是合法 JSON：{e}")
    if isinstance(rows, dict):                    # 容一个 {"jobs": [...]} 的外壳
        rows = rows.get("jobs") or rows.get("rows") or []
    if not isinstance(rows, list):
        raise SystemExit("输入应该是一个数组，或 {\"jobs\": [...]} 这样的外壳")
    return [r for r in rows if isinstance(r, dict)]


def store_path(user: str) -> Path:
    return _cli.store_dir(user, ROOT) / "seen_jobs.json"


def tracker_pairs(user: str) -> set:
    """投递台账里的「公司 + 岗位」对。读不到就当没投过（少跳过一个，
    多一个重复由 `audit_pipeline` 事后报出来 —— 比整轮抓取挂掉好）。

    列名是 `company` / `role`（`job_search_tracker.csv` 的实际表头，
    2026-10-12 实读确认；不是「公司」「岗位」—— 猜错的后果是**键全成
    `公司名|`**：岗位名那一截空着，于是这道门只对「连岗位名都没填」的
    候选生效，看起来在跑、实际几乎不拦）。
    """
    p = ROOT / "users" / user / "job_search_tracker.csv"
    if not p.is_file():
        return set()
    out = set()
    for r in _cli.read_tracker_rows(p):
        c = str(r.get("company") or "").strip()
        t = str(r.get("role") or "").strip()
        if c or t:
            out.add(pair_key(c, t))
    return out


def classify(row: dict, idx: dict, pairs: set, seen_pairs: set,
             batch_tokens: set) -> tuple:
    """这一条属于哪一类。返回 `(类别, 命中的键或 None)`。

    `idx` 是 `_cli.seen_index`：令牌 → **库键**（热库优先，冷库其次）。
    命中「见过」时返回的那个键可以直接拿去改条目。

    类别：`new` / `seen`（见过的，只刷 date）/ `same_pair`（换了链接的同岗）
    / `applied`（投过了）/ `dup_in_batch`（这一批自己里重复）
    """
    url = str(row.get("url") or "")
    title = str(row.get("title") or "")
    company = str(row.get("company") or "")
    if not title:
        return "no_title", None
    tok = _cli.job_token(url, title) if url else None
    if tok and tok in idx:
        return "seen", idx[tok]
    if tok and tok in batch_tokens:
        return "dup_in_batch", None
    pk = pair_key(company, title)
    if pk in seen_pairs:
        return "same_pair", pk
    if pk in pairs:
        return "applied", pk
    return "new", None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="把这一轮抓到的候选写进职位库。不加 --apply 就是试运行。")
    ap.add_argument("--input", metavar="文件",
                    help="这一轮抓到的候选（JSON 数组，或 {\"jobs\": [...]}）；"
                         "填 - 从标准输入读")
    ap.add_argument("--query", metavar="词", help="这批是哪个词搜到的，写进 found_by")
    ap.add_argument("--portal", metavar="渠道", help="内部渠道键（如 liepin-search）")
    ap.add_argument("--today", metavar="YYYY-MM-DD", help="今天（测试用），默认今天")
    ap.add_argument("--apply", action="store_true", help="真的写进 seen_jobs.json")
    ap.add_argument("--user", help=_cli.HELP_USER)
    args = ap.parse_args(argv)

    user = _cli.pick_user(args.user or "", root=ROOT)
    # `--input` **不设 required**：设了的话 `ingest.py --user 查无此人` 会先被
    # argparse 拦下（报「缺 --input」），那个不存在的用户**根本没被校验**——
    # 而「读不到数据 → 当成还没开始 → 导出一份空面板」正是
    # `test_cli_contract` 钉的那件事。先认用户，再问输入。
    if not args.input:
        ap.error("要入库得给 --input（候选文件，或 - 表示从标准输入读）")
    today = args.today or _dt.date.today().isoformat()
    path = store_path(user)
    if not path.is_file():
        raise SystemExit(_cli.no_store(path))
    data, stamp = _cli.load_json_stamped(path)
    seen = _cli.seen_of(data)
    _cli.stop_on_unreadable_rows(seen, path)

    rows = load_rows(args.input)
    if not rows:
        print("输入里一条候选都没有")
        return 0

    idx = _cli.seen_index(user, root=ROOT)
    # **公司名缺失的条目不进「公司+岗位」集合。** `|岗位名` 不是一家公司；
    # 拿它去挡别的候选，等于把两个只是同名、却可能毫无关系的岗当成同一个。
    # 批内新增那一侧也按同一条判据（见下面 `if company:`），两边必须对称。
    seen_pairs = {pair_key(v.get("company"), v.get("title"))
                  for v in seen.values()
                  if isinstance(v, dict) and (v.get("company") or "").strip()}
    pairs = tracker_pairs(user)

    tally = {"new": 0, "seen": 0, "same_pair": 0, "applied": 0,
             "dup_in_batch": 0, "no_title": 0}
    added: dict = {}                                  # 新键 → 条目
    touched: list = []                                # (键, 新的 date)
    batch_tokens: set = set()
    collide: list = []

    for row in rows:
        kind, key = classify(row, idx, pairs, seen_pairs, batch_tokens)
        tally[kind] = tally.get(kind, 0) + 1
        url = str(row.get("url") or "")
        title = str(row.get("title") or "")
        if kind == "seen":
            # Step 4：见过的岗**只更新 date**，别的字段一个字不动。
            # `key` 是库键；只在存档里的（idx 命中冷库）不写 —— 存档只读。
            d = str(row.get("date") or "")[:10]
            if not d or key not in seen:
                continue
            if str(seen[key].get("date") or "")[:10] < d:
                touched.append((key, d))
            continue
        if kind in ("same_pair", "applied", "dup_in_batch", "no_title"):
            continue

        entry = {k: row[k] for k in CARRY if k in row}
        entry["url"] = url
        entry["title"] = title
        entry.setdefault("company", str(row.get("company") or ""))
        entry["portal"] = args.portal or str(row.get("portal") or "")
        entry["date"] = str(row.get("date") or "")[:10]
        entry["first_seen"] = today
        entry["status"] = "new"
        if args.query:
            entry["found_by"] = args.query
        elif row.get("found_by"):
            entry["found_by"] = row["found_by"]
        new_key = _cli.job_key(entry)
        if new_key is None:
            new_key = f"{entry['portal'] or '未知渠道'}_{entry['company']}_{title}"
        if new_key in seen or new_key in added:
            collide.append((new_key, title or entry["company"]))
            continue
        added[new_key] = entry
        # **这一批里新加的也要进「公司+岗位」集合。** 只在开头读一次库存的话，
        # 同一个岗换个链接在同批出现两次，两条都会当新岗写进去。公司名缺失时
        # 不加：`|岗位名` 不是「同一家公司」，不能拿它去挡别的候选。
        company = (entry.get("company") or "").strip()
        if company:
            seen_pairs.add(pair_key(company, title))
        if url:
            batch_tokens.add(_cli.job_token(url, title))

    # query_log：跑过就要留痕，零产出尤其。
    if args.query or args.portal:
        ql = data.setdefault("query_log", [])
        ql.append({"query": args.query or "", "portal": args.portal or "",
                   "date": today, "rows": len(rows), "new": len(added)})

    print(f"候选 {len(rows)} 条 · 新增 {len(added)} · "
          f"见过（只刷 date）{tally['seen']} · 同公司同岗换链接 {tally['same_pair']} · "
          f"投过了 {tally['applied']} · 批内重复 {tally['dup_in_batch']} · "
          f"没有岗位名 {tally['no_title']}")
    if touched:
        print(f"  会更新 date 的 {len(touched)} 个："
              + "、".join(t[:28] for t, _d in touched[:3])
              + ("……" if len(touched) > 3 else ""))
    if collide:
        print(f"  ✗ {len(collide)} 条的新键与库里重了，已剔除（写下去就是覆盖掉另一个岗）：")
        for k, t in collide[:5]:
            print(f"      {k}  ←  {t}")
        return 1
    for k, e in list(added.items())[:8]:
        print(f"  + {k}  {e.get('company', '')} · {e.get('title', '')}")

    if not args.apply:
        print("\n" + _cli.DRY_RUN_NOTE)
        return 0

    seen.update(added)
    for k, d in touched:
        if k in seen and isinstance(seen[k], dict):
            seen[k]["date"] = d
    _cli.atomic_write(path, json.dumps(data, ensure_ascii=False, indent=1),
                      expect=stamp)
    print(f"\n已写进 {path.relative_to(ROOT).as_posix()}：新增 {len(added)} 个、"
          f"刷了 {len(touched)} 个 date")
    print("下一步：python tools/prescreen.py --annual-floor 42 --edu-floor 本科"
          "（判断交给它，这里不做）")
    return 0


if __name__ == "__main__":
    # 带戳写盘，撞车是**正常的**（抓取那几分钟里用户在总览页点一下很常见）。
    # 走 `_cli.run_cli`，撞车时是一句「再跑一遍」，不是几十行 Traceback。
    raise SystemExit(_cli.run_cli(main))