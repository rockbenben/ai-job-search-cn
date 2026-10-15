"""浏览器渠道要提取的字段清单，必须和 seen_jobs 的 schema 一致。

## 为什么有这个测试

`test_scrape_schema_covers_scoring.py` 盯的是「schema 里有没有这些字段」。
schema 补齐了，猎聘 CLI 也跟上了——但**浏览器渠道照样在丢字段**，因为它照的不是
schema，是 `cdp-portals.md` 第 5 步那份**更短的**提取清单。

两份清单当时是这样的：

    scrape.md schema   : salary salaryMonths location workYears eduLevel
                         compScale compStage compIndustry isHeadhunter
    cdp-portals.md 第5步: 职位名 公司 薪资 经验要求 学历 地点 详情链接

少了薪数、行业、公司规模、是否猎头四项。实测后果（全量 55 个 CDP 职位）：

| 字段 | 覆盖 |
|---|---|
| `salary` | 53/55 |
| `location` | 54/55 |
| 其余六项 | **各 0/55** |

**照着一份不完整的清单认真做，得到的就是一份不完整的数据。** 而且这个洞藏得很深：
`scrape.md` 里当时写着「同期 CDP 渠道的 55 个几乎全有」，于是上一轮修复只盯猎聘，
根本没往这边看——**一句没复核的论断，让一个渠道多丢了半年的字段。**

所以这个测试盯两件事：
1. schema 里每个打分字段，`cdp-portals.md` 的提取清单里都要点名；
2. 两边字段名逐字一致（别一边 `salaryMonths` 一边「薪数」）。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRAPE = ROOT / "workflows" / "job-scrape.md"
PORTALS = ROOT / "workflows" / "reference" / "cdp-portals.md"

#: 打分与硬门真正用得上的字段。与 test_scrape_schema_covers_scoring.py 同源。
SCORING_FIELDS = {
    "salary": "薪资与职级 25%",
    "salaryMonths": "年包 = 月薪 × 薪数",
    "location": "硬门「通勤」",
    "workYears": "硬门「工作年限」",
    "eduLevel": "硬门「学历院校」",
    "compScale": "强度与公司性质 20%",
    "compIndustry": "强度与公司性质 20%",
    # 2026-08-19 补的四项。每一项都有框架里点名的消费方——它们不是「多存点」，
    # 是**已经写着要用、而 schema 一直没有**：
    "date": "第三步真伪信号「蓄水池嫌疑」的判据原文就是它",
    "benefits": "第 2 维「五险一金是基线，补充公积金是加分」「非现金部分逐条折算」",
    "addressDetail": "第 4.2 通勤提示：「你在 X，公司在 Y，约 N 分钟」",
    "recruiter": "信息可信度：谁在发这个岗（企业 HR / 猎头 / 人力资源机构）",
    # **2026-10-14 补进这份名单的。** 此前它们不在 `SCORING_FIELDS` 里，
    # 于是「两份清单逐字对应」这句话是假的，而守卫照样绿 —— 守的那份名单
    # 恰好漏掉了缺的那两项。实测：猎聘 CLI 上 `recruiterTitle` 覆盖 58%，
    # 三家浏览器通道 0-3%，而 `_cli.counterpart_of`（渠道判定）读它。
    "recruiterSurname": "台账 `contact_person` 列，三处读它：跟进称呼「<姓>女士」还是「团队」",
    "recruiterTitle": "渠道判定第三档：对面是 HR 还是用人方本人（`_cli.counterpart_of`）",
    "employmentType": "硬门「外包/驻场/派遣」判的就是用工形式本身",
    "validThrough": "/job-rank Step 3：截止 7 天内标 🔥、已过期转 expired",
}


def schema_fields() -> set:
    """scrape.md Step 4 那段 json 里出现的字段名。"""
    t = SCRAPE.read_text(encoding="utf-8")
    m = re.search(r'```json\s*\n\{\s*\n\s*"seen"\s*:(.*?)```', t, re.S)
    assert m, "scrape.md 里找不到 seen_jobs 的 schema 代码块"
    return set(re.findall(r'"([A-Za-z][A-Za-z0-9]*)"\s*:', m.group(1)))


def extraction_section() -> str:
    """cdp-portals.md 第 5 步（提取字段）到第 6 步之间的正文。

    按「小节从哪开始、到哪结束」来切，而不是取固定行数——文档一改行号就漂。
    """
    t = PORTALS.read_text(encoding="utf-8")
    start = t.find("从 DOM 提取职位卡")
    assert start != -1, "cdp-portals.md 里找不到第 5 步「从 DOM 提取职位卡」"
    tail = t[start:]
    end = re.search(r"\n6\.\s", tail)
    return tail[: end.start()] if end else tail


class ExtractionListCoversTheSchema(unittest.TestCase):
    def test_every_scoring_field_is_named_in_the_extraction_list(self):
        sec = extraction_section()
        missing = [f"{k}（{why}）" for k, why in SCORING_FIELDS.items()
                   if k not in sec]
        self.assertFalse(
            missing,
            "cdp-portals.md 第 5 步没要求提取这些字段，浏览器渠道抓到也不会存 → "
            f"打分时无依据：{missing}")

    def test_extraction_list_uses_the_schema_field_names(self):
        """两边必须是同一套名字，否则「对齐」只是看起来对齐。"""
        sec = extraction_section()
        named = set(re.findall(r"`([A-Za-z][A-Za-z0-9]*)`", sec))
        schema = schema_fields()
        unknown = sorted(f for f in named & set(SCORING_FIELDS) if f not in schema)
        self.assertFalse(unknown, f"这些字段名 schema 里没有，两边对不上：{unknown}")

    def test_the_loss_is_documented_so_the_list_is_not_shortened_again(self):
        """光补清单不够——要写清为什么，否则下次精简文档时又会被删回去。"""
        sec = extraction_section()
        self.assertRegex(
            sec, r"0/55|全是 0",
            "要留下实测数字，说明清单短了会丢多少数据")

    def test_scrape_md_no_longer_claims_cdp_had_the_fields(self):
        """那句错误论断本身是这次事故的成因，不能留在文档里。"""
        t = SCRAPE.read_text(encoding="utf-8")
        self.assertNotIn(
            "同期 CDP 渠道的 55 个几乎全有", t,
            "这句话是错的（实测 6 个字段各 0/55），留着会再次误导修复方向")


class RealDataShowsTheGap(unittest.TestCase):
    """控制测试：真有数据时，浏览器渠道不该整列为空。

    这条不是防未来，是防「文档改了但没人再抓一次」——只要重抓过，
    新条目就该带上这些字段。没有真实数据的 clone 直接跳过。
    """

    def test_browser_portal_entries_are_not_uniformly_empty(self):
        import json
        ptr = ROOT / ".active_user"
        if not ptr.is_file():
            self.skipTest("没有活动用户")
        user = ptr.read_text(encoding="utf-8").strip()
        sj = ROOT / "users" / user / "job_scraper" / "seen_jobs.json"
        if not sj.is_file():
            self.skipTest("这个 clone 里没有真实抓取数据")
        seen = json.loads(sj.read_text(encoding="utf-8"))["seen"]
        # 只看文档对齐之后抓的条目；之前的已经是既成事实，不因此报红
        #
        # ⚠️ **两种后缀都要认。** 这里原来只筛 `-cdp` —— 而渠道命名后来迁到了
        # `-browser`（`portal_budget` 的通道名就是 `boss-browser` 这一族）。
        # 实测 2026-09-02：库里 `-cdp` 只剩 **12 个**、最新一条停在 08-11，
        # 其中「对齐之后抓的」**3 个**；而 `-browser` 那边同期有 **716 个**。
        # 也就是说这条守卫一直在拿三周前的三条旧数据把关，
        # 当下每一轮抓回来的七百多个岗**一个都没查过** —— 它绿着，但看不见。
        fresh = [e for e in seen.values()
                 if (e.get("portal") or "").endswith(("-cdp", "-browser"))
                 and (e.get("first_seen") or "") > "2026-07-30"]
        if not fresh:
            self.skipTest("文档对齐后还没有用浏览器渠道重抓过")
        self.assertGreater(
            len(fresh), 50,
            f"只筛到 {len(fresh)} 个浏览器渠道职位 —— 渠道名多半又变了，"
            "而这条守卫会安静地退回去只查历史（2026-09-02 就这么绿过）")
        # **只钉这三项。** 同一批 716 个岗实测：`recruiter` 0、`validThrough` 0、
        # `employmentType` 4、`benefits` 2 —— 那几项确实没在抓，但那是**数据缺口**，
        # 归 `audit_pipeline` 的「字段：能取到，但一直没取」（留意档）跟。
        # 把它们塞进这条断言只会让整个套件长期红着，而红着的守卫等于没有守卫。
        for field in ("eduLevel", "workYears", "compIndustry"):
            got = sum(1 for e in fresh if e.get(field))
            self.assertTrue(
                got, f"{len(fresh)} 个新抓的浏览器渠道职位里，{field} 一个都没有——"
                     "第 5 步的字段表没被照做")


if __name__ == "__main__":
    unittest.main()
