#!/usr/bin/env python3
"""职位详情库：抓回来的 JD **存下来**，不要用完就扔。

## 为什么要它

抓一个职位本来一趟就能拿全——详情接口返回的是搜索结果的**超集**：
`title`/`company`/`salary`/`salaryMonths`/`eduLevel`/`compScale`/… 全都有，
外加 `description`（JD 正文）。但现在拆成了两趟：

    /job-scrape  →  列表页字段，写进 seen_jobs.json
    /job-rank    →  抓 JD 正文，打完分**丢掉**

第二趟的结果不落盘。于是重跑一次 `/job-rank`、换个会话、或者进程中途挂掉，
已经抓过的全部要重抓。实测：一批 137 份 JD 抓完躺在系统临时目录里，
Windows 随时会清掉——那是 137 次请求、三分多钟节流等待的成果。

这个库把它接住：**抓过的就不再抓**。

## 存在哪、存什么

`users/<活动用户>/job_scraper/details/<id>.json`，一个职位一个文件。

- **`id` 用 `stable_id(url, title)`**，与导出给页面的 `id` 同一个函数。
  不用 URL 当文件名：51job 实测同一个 URL 下挂着两个不同职位，按 URL 存会互相覆盖。
- **一职位一文件**，不塞进 `seen_jobs.json`。后者每次改状态都要整体重写，
  塞进去会让它从 170 KB 涨到 1.6 MB，每标一个「不投」都重写一遍。

## 与 `seen_jobs.json` 的分工

详情里的**结构化字段**回填进 `seen_jobs.json`（打分要用），`description` 留在这里。
回填**只补空缺、不覆盖已有值**——两边不一致时如实报出来，让人看一眼，
不静默改写已经拿来打过分的数据。

零依赖，只用标准库。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import _cli  # noqa: E402,F401  import 即把管道输出定到 UTF-8（见 _cli.force_utf8_output）
import export_web_data as ex  # noqa: E402  复用 stable_id，别造第二套 id

#: 详情里值得回填进 seen_jobs 的字段。与 `scrape.md` Step 4 的 schema 同名。
#: `description` **不在**这里——它留在详情文件里，不进 seen_jobs。
MERGE_FIELDS = ("salary", "salaryMonths", "location", "workYears", "eduLevel",
                "compScale", "compIndustry", "compStage", "isHeadhunter",
                # 下面这几个是 2026-08-19 审计补的。它们的共同点是**有消费者**：
                #   employmentType → 04 的「外包/驻场/派遣」硬门要拿它当证据
                #   recruiter      → 话术判「猎头还是 HR 直招」
                #   benefits       → 薪资维要把非现金部分折进去
                #   date           → 判职位新鲜度
                # 抓取器现在多半还不填它们（详情库实测覆盖率接近 0），
                # 但**回填这一跳不能是断的**：源头一补上，下游立刻就能用。
                "employmentType", "recruiter", "benefits", "date",
                # `recruiterTitle` 与上面那几个断在不同的地方：源头**已经开始
                # 出值了**，而这一跳当时是断的。实测 2026-08-27：详情库 1547 份里
                # **31 份带着真值**（另有 1479 份那个键是 `null`，不算），
                # 而职位库 1847 条里 **0 条**有 —— 它当时没进这张表，`--merge`
                # 从来没搬过它。**下面紧接着的那一行就是把它接上的。**
                #
                # 消费者是现成的：`export_web_data` 拿
                # `_cli.counterpart_of(e.get("recruiterTitle"), …)` 判「对面是
                # HR 还是用人方本人」，`e` 就是职位库那条。读的是个永远为空的键，
                # 于是直招一律退回按 HR 那套写 —— 而 `counterpart_of` 的取样里，
                # 直招认得出职务的 20 张有 4 张对面是研发总监/运营经理/商务主管/
                # 法人，**这五分之一当场就能拍板的人，被当成 HR 说话**。
                #
                # 接上之后当场只改了 **9 个岗**的判定（(空) → HR）：31 个里
                # 有 22 个是猎头岗，`isHeadhunter` 一个字段就已经定了档，
                # 轮不到职务说话。**如实记下这个数**——别把「接通了一条断管」
                # 说成「修好了 141 个岗」，那个 141 里绝大多数本来就是对的。
                #
                # 9 个不多，但补上它是一个词的事；而只要源头继续出值，
                # 这一跳通着就不用再想起它一次。
                "recruiterTitle",
                # `recruiterSurname` 断在完全相同的地方，而且是被**一句写给用户
                # 的指令**照出来的：自检那条「投递记录里有人读、没人写的列」
                # 让他「猎聘的岗库里就有（`recruiterSurname`），直接取」——
                # 而实测 2026-08-30 岗库 1839 条里 **0 条**有。
                # 详情库里真有值的 6 份（另有 44 份那个键是 `null`，不算），
                # 当时全因为这张表里没有它而搬不过去 —— 同样，下面那行接上了。
                #
                # 消费者是现成的：投递记录的 `contact_person` 有 5 处在读
                # （`followups.py` 与四份工作流），而 88 行里填了 **0 行**。
                # 6 个不多 —— 但「有就直接取」这句话得先是真的。
                "recruiterSurname")

#: 详情里叫 A、职位库里叫 B 的字段。**这类断链最难发现**——两边都「有」这个字段，
#: 只是名字不同，于是抓得到也永远接不上。
#:
#: `validThrough` / `deadline` 就是实测出来的一对：`job-scrape.md` 的抓取 schema 写
#: `validThrough`（schema.org 的 JobPosting 用这个名），而 `/job-rank` 的
#: 「截止日期 7 天内标 🔥、已过期转 expired」读的是 `deadline`。
#: 两条规则各自都对，中间没有任何一处把名字对上——那条 🔥 规则从上线起就没生效过。
MERGE_RENAME = {"validThrough": "deadline",
                # 同一个坑第二处：抓取 schema 用 schema.org 的 `datePosted`，
                # 而库里、面板上、新鲜度判断用的都是 `date`。
                "datePosted": "date"}


def store_dir(user: str) -> Path:
    return ROOT / "users" / user / "job_scraper" / "details"


def key_for(url: str, title: str) -> str:
    return ex.stable_id(url or "", title or "")


def load(user: str, url: str, title: str) -> dict | None:
    """取一份详情。没有就返回 None —— 调用方据此决定要不要抓。"""
    p = store_dir(user) / f"{key_for(url, title)}.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None          # 半截文件当作没有，重抓即可


def save(user: str, detail: dict) -> Path:
    """存一份详情。`detail` 至少要有 `url`，最好有 `title`。"""
    d = store_dir(user)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{key_for(detail.get('url') or '', detail.get('title') or '')}.json"
    _cli.atomic_write(p, json.dumps(detail, ensure_ascii=False, indent=1))
    return p


def has_body(detail: dict | None) -> bool:
    """有没有真正的 JD 正文。

    **只有 URL 和标题不算「抓过」**——那些字段列表页就有。判据是 `description`
    有实际内容；空的、几十个字的占位都不算，否则 `/job-rank` 会拿一句话去打分。
    """
    return bool(detail and len((detail.get("description") or "").strip()) >= _cli.JD_MIN_BODY)


def _seen(user: str) -> tuple[Path, dict]:
    p = ROOT / "users" / user / "job_scraper" / "seen_jobs.json"
    if not p.is_file():
        raise SystemExit(_cli.no_store(p))
    return p, json.loads(p.read_text(encoding="utf-8"))


def _seen_stamped(user: str):
    """读主库并带上版本戳；`merge_into_seen` 扫完全部详情后才写回。"""
    p = ROOT / "users" / user / "job_scraper" / "seen_jobs.json"
    if not p.is_file():
        raise SystemExit(_cli.no_store(p))
    data, stamp = _cli.load_json_stamped(p)
    return p, data, stamp


#: 分隔符写法不统一：列表页爱用 `·`，详情页爱用 `-`，还有全角空格。
#: 比前缀之前先抹平，否则 `上海·徐汇` 和 `上海-徐汇区…` 会被当成两个地方。
_SEPS = str.maketrans({c: "" for c in "·・-—–/ 　	"})


def is_refinement(field: str, old: str, new: str) -> bool:
    """两个值是不是「同一件事，详情页写得更细」，而不是互相矛盾。

    **这个判断决定一条冲突会不会被人看见。** 实测活动用户 2026-08-23 与 09-01：
    `--merge` 报「503 处两边不一致」，其中 **500 处是 location**，而那 500 处
    全是同一个地方的不同精度（`上海` → `上海徐汇万科`、`上海-黄浦区` →
    `上海-黄浦区大上海时代广场`）。真正互相矛盾的只有 **3 条薪资**，
    混在 500 行里滚过去，8 行样本里靠运气才露出 1 条。

    `location` 之所以特殊：它在框架里只服务**一道 Pass/Fail 的门**（跨城搬迁，
    见 `04-job-evaluation.md`）。同城内写得多细都不改判定；换了城市才改。
    所以同城 = 更精确，不同城 = 真矛盾。**按前两个字比城市**——三字市
    （哈尔滨 / 石家庄）比前两字也够分辨，且宁可多报不可漏报：多报只是
    多一行，漏报会把一个判错的门藏起来。

    其余字段没有这层语义，只认前缀（`30-40k` 与 `30-40k·15薪` 是同一件事）。

    **大小写不算不一致。** 薪资串里的 `k`/`K` 两个平台各写各的（BOSS 给 `40-60K`、
    猎聘给 `40-60k`），此前它们被当成一条**真冲突**报出来 —— 而两个数一模一样。
    实测 2026-09-01：29 条冲突里就有这么一条，白占一行，还把
    「噪音压倒真冲突」那个比值压下去了（`test_a_more_precise_address_is_not_a_conflict`
    的前提正是那个比值）。折成小写再比。
    """
    a, b = old.translate(_SEPS).lower(), new.translate(_SEPS).lower()
    if not a or not b:
        return False
    if a.startswith(b) or b.startswith(a):
        return True
    return field == "location" and a[:2] == b[:2]


def merge_into_seen(user: str, apply: bool) -> dict:
    """把详情里的结构化字段回填进 `seen_jobs.json`。

    **只补空缺**：已有值一律保留，冲突的如实报出来。详情页确实比列表页权威，
    但静默改写一份已经拿来打过分的数据，会让「分数为什么变了」无从追查。

    ## 「如实报出来」原来等于没报

    这份冲突清单**就是**「可能按旧值做过判定」的那批岗 —— 合并从不覆盖，
    所以任何判过的岗读到的一定是列表页那个旧值。它是这里最有用的产出。

    可实测活动用户 2026-08-23：报的是「**503 处**两边不一致」，其中
    **500 处是 location**，而那 500 处全是同一个地方的不同精度
    （`上海` → `上海徐汇万科`）。真正对不上的只有 **3 条薪资**，
    还都是详情页更高（`15-20k` / `30-40k` 差一倍）。样本只印 8 行，
    靠运气才露出 1 条 —— 而其中一条的判词是「粗筛：跳过」：
    列表页 15-20k 按最乐观 16 薪折 32 万、低于 42 万底线所以被扔了，
    而盘上存着的详情写的是 30-40k（64 万）。**一个岗按一份自己盘上
    已有更好版本的数字被丢掉了，而提示它的那行字被 500 行噪音埋着。**

    所以分两类报（判据见 `is_refinement`），并且给真冲突配一条能直接敲的命令
    —— 只报不给动作，看见了也只能干看着。**这一步不动数据**：改不改由人决定，
    和上面「不静默改写」是同一条原则。
    """
    path, data, stamp = _seen_stamped(user)
    seen = _cli.seen_of(data)
    filled: dict[str, int] = {}
    conflicts: list[dict] = []
    #: 「详情页写得更细」按字段计数就够，不占屏。判据见 `is_refinement`。
    refined: dict[str, int] = {}
    touched = 0
    for entry in seen.values():
        detail = load(user, entry.get("url") or "", entry.get("title") or "")
        if not detail:
            continue
        changed = False
        for f in (*MERGE_FIELDS, *MERGE_RENAME):
            new = detail.get(f)
            if new in (None, "", []):
                continue
            f = MERGE_RENAME.get(f, f)      # 详情里的名字 → 职位库里的名字
            old = entry.get(f)
            if old in (None, "", []):
                entry[f] = new
                filled[f] = filled.get(f, 0) + 1
                changed = True
            elif old != new:
                if is_refinement(f, str(old), str(new)):
                    refined[f] = refined.get(f, 0) + 1
                    continue
                # **判过没有**要一起带出来 —— 这条冲突值不值得管全看它。
                # 判据不是 `status`，是「有没有判词」：合并从不覆盖已有值，
                # 所以任何判过的岗读到的**一定**是列表页那个旧值，与它现在
                # 处在哪个状态无关。实测那 3 条薪资里，一条的判词是
                # 「粗筛：跳过」—— 列表页 15-20k 按最乐观 16 薪折 32 万、
                # 低于 42 万底线所以扔了，而盘上存着的详情写的是 30-40k（64 万）。
                conflicts.append({
                    "title": (entry.get("title") or "")[:18],
                    "field": f, "old": old, "new": new,
                    "judged": bool(entry.get("rank_verdict")
                                   or entry.get("prev_verdict")),
                    "url": entry.get("url") or "",
                })
        touched += changed
    if apply and touched:
        _cli.atomic_write(path, json.dumps(data, ensure_ascii=False, indent=1),
                          expect=stamp)
    return {"entries": touched, "filled": filled, "conflicts": conflicts,
            "refined": refined}


def save_from_text(user: str, url: str, body: str, apply: bool) -> dict:
    """把刚在浏览器里读到的一份 JD 正文**一步存进库**。

    ## 为什么要有这条路

    在这之前，落库只有 `--import-from <目录>` 一条路：先把详情拼成 JSON、
    写到某个临时目录、再收一次。读页面的人手上只有一段正文，为了存它要先
    造一个文件。**摩擦大的规则不会被执行** —— 全库实测（2026-08-26）：
    191 个岗的判词写着读过 JD 正文，而库里查不到，按渠道是猎聘 113、
    BOSS 48、智联 14、前程 10。同一天的一轮 `/job-auto` 评了 13 个岗，
    落库 4 个（正好是当轮要出材料的那 4 个），另外 9 个照旧只读不存。

    不落库的代价不是「少个缓存」：出材料时要用同一份正文，那时得**再开一次
    页面**。而渠道撞限流的时候，那一次往往就开不出来了。

    ## 标题不让调用方给

    库里的键是 `stable_id(url, title)`。标题差一个字，存进去的这份就再也
    读不回来 —— 而它**看起来是成功的**（写盘了、有文件、没报错）。所以这里
    只收链接，标题连同已有的结构化字段一起从 `seen_jobs.json` 那条取。
    链接对不上任何一条就直接停，并说出该敲什么。

    ## 正文太短的不收

    判据与 `--import-from` 同源（`has_body`）：几十个字的占位收进来，
    `/job-rank` 会以为抓过了，然后拿一句话去打分 —— 比没有更糟。
    """
    _, data = _seen(user)
    seen = _cli.seen_of(data)
    want = _cli.norm_url(url or "")
    hit = next((e for e in seen.values()
                if isinstance(e, dict) and _cli.norm_url(e.get("url") or "") == want), None)
    if hit is None:
        raise SystemExit(
            f"职位库里没有这条链接：{url}\n"
            f"  存不进去 —— 库里的键要拿那条记录的标题一起算。\n"
            f"  先把它抓进库：/job-scrape，或者确认链接抄全了没有")
    detail = {f: hit[f] for f in ("title", "company") + MERGE_FIELDS
              if hit.get(f) is not None}
    detail["url"] = hit.get("url") or url
    detail["description"] = (body or "").strip()
    if not has_body(detail):
        raise SystemExit(
            f"正文只有 {len(detail['description'])} 字，不到 {_cli.JD_MIN_BODY} 字，不收。\n"
            f"  收了会让 /job-rank 以为抓过 —— 然后拿这一句话去打分。\n"
            f"  判据与 --import-from 同源；页面没读全就重读一次")
    if apply:
        save(user, detail)
    return {"title": detail.get("title") or "", "chars": len(detail["description"]),
            "fields": sorted(k for k in detail if k not in ("url", "description"))}


def import_dir(user: str, src: Path, apply: bool) -> dict:
    """把一目录已抓好的详情 JSON 收进库里。

    用于接住散落在临时目录里的成果——那是真金白银的请求次数，
    Windows 清一次临时目录就没了。
    """
    if not src.is_dir():
        raise SystemExit(f"目录不存在：{src}")
    ok, skipped, nobody = 0, 0, 0
    for p in sorted(src.iterdir()):
        if p.suffix == ".err" or not p.is_file():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            skipped += 1
            continue
        if not isinstance(d, dict) or not d.get("url"):
            skipped += 1
            continue
        if not has_body(d):
            nobody += 1          # 没正文的不收——收了会让 /job-rank 以为抓过了
            continue
        if apply:
            save(user, d)
        ok += 1
    return {"imported": ok, "skipped": skipped, "no_body": nobody}


def status(user: str) -> dict:
    _, data = _seen(user)
    seen = _cli.seen_of(data)
    have = sum(1 for e in seen.values()
               if has_body(load(user, e.get("url") or "", e.get("title") or "")))
    new_have = sum(1 for e in seen.values() if e.get("status") == "new"
                   and has_body(load(user, e.get("url") or "", e.get("title") or "")))
    new_total = sum(1 for e in seen.values() if e.get("status") == "new")
    return {"total": len(seen), "have": have,
            "new_total": new_total, "new_have": new_have}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="职位详情库：抓过的 JD 存下来，不重抓")
    ap.add_argument("--import-from", metavar="目录",
                    help="把这个目录里已抓好的详情 JSON 收进库")
    ap.add_argument("--save", metavar="职位链接",
                    help="把一份 JD 正文存进库，正文从标准输入读。"
                         "标题与结构化字段从 seen_jobs.json 那条取——"
                         "库里的键是拿标题一起算的，给错了存进去也读不回来")
    ap.add_argument("--show", metavar="职位链接",
                    help="把库里这份 JD 的正文印出来。存得进读不出的话，"
                         "重判一个岗就还得再开一次页面——那正是这个库要省掉的事")
    ap.add_argument("--merge", action="store_true",
                    help="把详情里的结构化字段回填进 seen_jobs.json（只补空缺）")
    ap.add_argument("--apply", action="store_true", help=_cli.help_apply())
    ap.add_argument("--user", help=_cli.HELP_USER)
    args = ap.parse_args(argv)

    # 经 pick_user 验存在性：拼错用户名时退出并列出现有用户，而不是先在
    # users/<拼错名>/ 下静默建目录写一堆详情文件、末尾才报「没有 seen_jobs.json」
    # ——错误指错方向，还凭空造出一个幽灵用户目录。
    user = _cli.pick_user(args.user or "", root=ROOT)
    did = False

    if args.save:
        r = save_from_text(user, args.save, sys.stdin.read(), args.apply)
        print(f"存下：{r['title'][:40]} · 正文 {r['chars']} 字"
              f" · 带上 {len(r['fields'])} 个已有字段")
        did = True

    if args.show:
        # 键是拿标题一起算的，所以要先从 seen_jobs 里把标题找回来——
        # 传空标题会算出另一个键，然后报「没抓过」。这个坑本会话踩过一次，
        # 当时把 281 份有正文的详情全报成了「没有 JD」。
        _, seen = _seen(user)
        title = ""
        for v in _cli.seen_of(seen).values():
            if _cli.norm_url(v.get("url") or "") == _cli.norm_url(args.show):
                title = v.get("title") or ""
                break
        d = load(user, args.show, title)
        if not has_body(d):
            print(f"库里没有这份 JD 的正文（{args.show}）。"
                  f"抓一份存进来：python tools/jd_store.py --save {args.show} --apply")
            return 1
        print(f"# {d.get('title') or '(无标题)'} · {d.get('company') or '(无公司)'}")
        print(f"# {args.show}")
        print()
        print((d.get("description") or "").strip())
        did = True

    if args.import_from:
        r = import_dir(user, Path(args.import_from), args.apply)
        print(f"收录：{r['imported']} 份"
              f" · 跳过 {r['skipped']} 份（不是详情 JSON）"
              f" · 没正文 {r['no_body']} 份（不收，收了会让 /job-rank 以为抓过）")
        did = True

    if args.merge:
        r = merge_into_seen(user, args.apply)
        print(f"回填：{r['entries']} 个条目")
        for f, n in sorted(r["filled"].items()):
            print(f"    {f:14} 补了 {n} 个")
        if r["refined"]:
            n = sum(r["refined"].values())
            cols = "、".join(f"{f} {c}" for f, c in sorted(r["refined"].items()))
            print(f"  {n} 处只是详情页写得更细（{cols}），同一件事，不用管")
        if r["conflicts"]:
            # **不再和「写得更细」混报。** 原来两类合在一起报「503 处不一致」，
            # 而其中 500 处是同一个地址的不同精度；真矛盾的 3 条薪资混在里面，
            # 8 行样本里靠运气才露出 1 条。判据见 `is_refinement`。
            print(f"  ⚠ {len(r['conflicts'])} 处两边真的对不上，"
                  f"已有值原样保留、没有改写：")
            for c in r["conflicts"][:8]:
                print(f"    {c['title']} · {c['field']}："
                      f"已有 {c['old']!r} / 详情 {c['new']!r}")
            if len(r["conflicts"]) > 8:
                print(f"    …… 另有 {len(r['conflicts']) - 8} 处")
            # 这份清单**就是**「可能按旧值做过判定」的那批岗。不给动作的话
            # 它只是一行警告：看见了，然后呢？深评会直接读 JD 正文里的数，
            # 比整库重评便宜得多。
            done = [c for c in r["conflicts"] if c["judged"] and c["url"]]
            if done:
                print(f"    这 {len(done)} 个已经按旧值判过了。要复核就逐个跑"
                      f" /job-apply <职位链接>（深评直接读 JD 正文里的数）：")
                for c in done[:3]:
                    print(f"      /job-apply {c['url']}")
        did = True

    s = status(user)
    print(f"\n详情库：{s['have']}/{s['total']} 个职位有 JD 正文"
          f"（待评的 {s['new_total']} 个里有 {s['new_have']} 个已有，"
          f"还需新抓 {s['new_total'] - s['new_have']} 个）")
    print(f"  位置：{store_dir(user).relative_to(ROOT).as_posix()}/（已 gitignore）")
    if did and not args.apply:
        print(chr(10) + _cli.DRY_RUN_NOTE)
    return 0


if __name__ == "__main__":
    sys.exit(_cli.run_cli(main))
