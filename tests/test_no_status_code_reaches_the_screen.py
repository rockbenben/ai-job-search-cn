# -*- coding: utf-8 -*-
"""「这个岗你已经投过……状态 applied」—— 那个 `applied` 直接印在总览页上。

`AGENTS.md`「给用户看的措辞」那张表把状态码逐个列了出来：

    expired / skipped / ranked（状态码） → 已下线 / 不投 / 已评分

而 `tracker.say()` 就是为这件事存在的，全仓到处在用（`applied_jds`、
`export_web_data`、`serve.py`）—— **只有预筛那两条规则没走它**：

    这家的这个岗你已经投过：2026-08-13 投的「…」，状态 applied，原投递：…
    这家你 2026-08-13 投过「…」（状态 applied），这个岗不是同一个，先排队尾

第一句进 `skipReason`，直接渲染在「不投的岗位」那一行上；同一句还经
`rank_breakdown.依据` 进 `skillWhy`（短名单那一列的悬浮说明）。
实测 2026-08-31：**9 个岗、18 处**。

## 这一条守在面板那一层，不守在写的那一处

改一处 `prescreen` 只治这一次。而状态码有十来种、能写进面板文字的路径也不止
一条（预筛、写回、Gmail 同步、审计的说明），所以判据落在**导出的成品**上：
`data.json` 里给人读的字段，一个裸状态码都不许有。

## 枚举字段不算

`status` / `value` / `then` / `funnels` 这几个存的**就是**那个码 —— 前端按它
分支、按它上色，那是数据不是文案（`Materials.counterpart` 这类同理）。
所以下面那张豁免表按**字段名**列，且只列真的是枚举的那几个。

依赖真实数据（`data.json` 不进版本库），CI 上会跳过 —— 与
`test_no_maintainer_data_in_repo` 同一档，本机跑那一遍才是这条的战场。

## 第二类：判定码占了一栏**地名**

状态码漏进句子之外，还有一处漏得更直的：总览页的**地点列**印的是 `PASS`。
实测 2026-10-02 有 8 个岗。根因不在写手，在 `workflows/job-rank.md` 的回传格式：
地点那道门的判定当初就叫 `location`，与职位记录里那栏**城市**同名，
照着键名回填就把「上海」挤成了 `PASS`。所以这一条守两头——

- 显示层：`short_location()` 认得判定码，认出来就当没填（**下面那组不依赖
  真实数据，CI 上真跑**）；
- 生成流程：回传格式里那个键已经改名，判定只住在 `hard_gates` 里
  （`TheKeyThatCollidedWithTheCityColumn` 钉住它不许长回来）。
"""
import json
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import export_web_data as ex  # noqa: E402
import tracker  # noqa: E402

#: 存的就是那个码的字段：前端按它分支/上色，不是给人读的句子。
ENUM_FIELDS = {
    "status",      # 投递状态本身
    "value",       # 按钮要写进去的值
    "then",        # 点完之后跳哪一步
    "funnels",     # 漏斗分档的键
    "verdict",     # 判词（中文，但可能含「已下线」这类词，另有守卫）
}

#: URL / 目录名 / 命令里出现这些词是正常的，不是文案。
PATHY_FIELDS = {"url", "source", "id", "jobId", "portal", "cmd", "command",
                "resumePdf", "pdf", "pdfLocal", "dir", "path", "key"}


#: 状态码里**同时也是中文求职圈日常词**的那几个。
#: `AGENTS.md` 自己就写「拿到 offer」「多个 offer 比较」，命令总览里也是
#: 「offer」—— 把它算成漏出来的码，报的全是噪音（实测 24 处里 6 处是它）。
#: 这张表只许因为「这个词中文里真这么说」而变长。
LOANWORDS = {"offer"}


def _codes() -> list:
    """所有会被写进 `status` 一列的码，长的排前面。"""
    got = (set(tracker.LABEL) | set(tracker.SAY_EXTRA)
           | set(tracker.FINAL_STATUSES)) - LOANWORDS
    return sorted(got, key=len, reverse=True)


def _leaks(data: dict) -> list:
    codes = _codes()
    pat = re.compile(r"(?<![A-Za-z_-])(" + "|".join(
        re.escape(c).replace(r"\ ", " ") for c in codes)
        + r")(?![A-Za-z_-])")
    out = []

    def walk(o, field):
        if isinstance(o, str):
            if field in ENUM_FIELDS or field in PATHY_FIELDS or len(o) < 8:
                return
            m = pat.search(o)
            if m:
                out.append((field, m.group(1),
                            o[max(0, m.start() - 34):m.start() + 20]))
        elif isinstance(o, dict):
            for k, v in o.items():
                walk(v, k)
        elif isinstance(o, list):
            for v in o:
                walk(v, field)

    for j in data.get("jobs") or []:
        for k, v in j.items():
            walk(v, k)
    for k, v in data.items():
        if k != "jobs":
            walk(v, k)
    return out


#: 判定码。**不借 `export_web_data._VERDICT_ONLY`** —— 拿实现自己的表去断言实现，
#: 那条测试只能证明它和自己一致。这一份是独立写出来的。
VERDICT_CODES = {"PASS", "FAIL", "FLAG", "满足", "不满足", "要留意", "未知", "不适用"}

RANK_DOC = ROOT / "workflows" / "job-rank.md"


def _verdict_in_a_city_column(data: dict) -> list:
    """地点栏里住着的判定码。整段相等才算 —— 「上海·徐汇区」里含个「未」不算。"""
    return [j.get("id") for j in data.get("jobs") or []
            if (j.get("location") or "").split("（")[0].strip().upper() in VERDICT_CODES]


def _rank_payload(text: str) -> str:
    """子代理那份回传格式（「每个代理返回一个 JSON 数组」后面的第一个围栏）。"""
    i = text.find("每个代理返回一个 JSON 数组")
    if i < 0:
        return ""
    m = re.search(r"```json\n(.*?)\n```", text[i:], re.S)
    return m.group(1) if m else ""


def _city_key_holding_a_verdict(block: str) -> list:
    """顶层键里「名字是地名、取值是判定码」的那几条。"""
    out = []
    for m in re.finditer(r'^  "([^"]+)"\s*:\s*(.*)$', block, re.M):
        key, val = m.group(1), m.group(2)
        if key.lower() in {"location", "city"} and re.search(r"\b(?:PASS|FAIL|FLAG)\b", val):
            out.append((key, val.strip()))
    return out


class TheRulerWouldLightUp(unittest.TestCase):
    """判据自检 —— 认不出码时下面那条在空集上永远绿。"""

    def test_it_catches_a_planted_one(self):
        got = _leaks({"jobs": [{"skipReason": "这个岗你已经投过，状态 applied"}]})
        self.assertEqual([g[1] for g in got], ["applied"])

    def test_it_leaves_the_enum_fields_alone(self):
        # **用长码做样本。** `applied` 只有 7 个字母，会先被「太短的不看」
        # 那一条挡掉 —— 于是把豁免表整个删掉这条也不红（变异照出来的）。
        self.assertEqual(_leaks({"jobs": [{"status": "interview_only"}]}), [])

    def test_it_leaves_urls_alone(self):
        self.assertEqual(
            _leaks({"jobs": [{"url": "https://x.com/applied-jobs/1"}]}), [])

    def test_it_does_not_split_a_longer_word(self):
        """`interview` 在 `interviewer` 里、在 `reinterview` 里都不算命中。

        **两头都要试。** 只给后缀那种（`interviewer`）时，把前面那个
        lookbehind 删掉照样绿 —— 拦住它的是后面那个 lookahead。
        """
        for s in ("他是 interviewer，不是候选人",
                  "这是 reinterview 的缩写，不是状态"):
            with self.subTest(s):
                self.assertEqual(_leaks({"jobs": [{"why": s}]}), [])

    def test_the_code_list_is_not_empty(self):
        self.assertGreater(len(_codes()), 6)

    def test_short_location_refuses_a_verdict(self):
        """判定码进不了地名栏 —— 这一条不依赖真实数据，CI 上真跑。"""
        for bad in ("PASS", "FAIL", "FLAG", "不满足", "PASS（不计权重）", "未知"):
            with self.subTest(bad):
                self.assertEqual(ex.short_location(bad), "")

    def test_short_location_still_cuts_a_real_address(self):
        """**反向控制。** 上面那条要是把整函数改成「一律返回空串」也照样绿。"""
        self.assertEqual(ex.short_location("上海-杨浦区民府路678号T2号楼"), "上海·杨浦区")
        self.assertEqual(ex.short_location("北京"), "北京")

    def test_the_city_column_ruler_catches_a_planted_one(self):
        got = _verdict_in_a_city_column(
            {"jobs": [{"id": "a", "location": "PASS"},
                      {"id": "b", "location": "上海·徐汇区"}]})
        self.assertEqual(got, ["a"])

    def test_the_payload_ruler_catches_a_planted_one(self):
        got = _city_key_holding_a_verdict('  "location": "PASS" | "FAIL" | "FLAG",\n')
        self.assertEqual([k for k, _ in got], ["location"])
        # **只看顶层。** 门名缩进两格，装判定码是天经地义的，别把它们一起报。
        self.assertEqual(_city_key_holding_a_verdict(
            '    "地点（跨城搬迁）": "PASS" | "FAIL" | "FLAG"\n'), [])


class TheTwoPrescreenRulesSayItInChinese(unittest.TestCase):
    """判据落在成品上，但这两条是它的由来 —— 单独钉住，构造数据也能验。"""

    ROWS = [{"company": "测试科技", "role": "AI产品经理",
             "date": "2026-08-13", "status": "applied",
             "source": "https://example.invalid/1"}]

    def _rules(self):
        import prescreen as ps
        return (
            ps.rule_applied_same_role(
                {"company": "测试科技", "title": "AI产品经理"}, self.ROWS),
            ps.rule_applied_same_company(
                {"company": "测试科技", "title": "另一个岗"}, self.ROWS),
        )

    def test_both_produce_something(self):
        for got in self._rules():
            self.assertTrue(got, "规则没命中 —— 下面那条就什么都没验")

    def test_neither_prints_the_raw_code(self):
        for got in self._rules():
            with self.subTest(got[:20]):
                self.assertNotIn("applied", got)

    def test_both_say_it_the_same_way(self):
        """措辞与 `applied_jds` 那句一致，别另起一种。"""
        for got in self._rules():
            with self.subTest(got[:20]):
                self.assertIn("现在是「我投了」", got)

    def test_a_terminal_status_is_said_too(self):
        import prescreen as ps
        got = ps.rule_applied_same_role(
            {"company": "测试科技", "title": "AI产品经理"},
            [dict(self.ROWS[0], status="no_response")])
        self.assertIn("没下文", got)
        self.assertNotIn("no_response", got)


class NoCodeReachesTheExportedPanel(unittest.TestCase):

    def setUp(self):
        p = ROOT / "web" / "public" / "data.json"
        if not p.is_file():
            self.skipTest("还没导出过面板数据 —— 这条这次什么都没验，不是通过")
        self.data = json.loads(p.read_text(encoding="utf-8"))

    def test_the_scan_sees_the_payload(self):
        self.assertGreater(len(self.data.get("jobs") or []), 20)

    #: 存量是 2026-08-31 修好之前落盘的几句：预筛把「状态 applied」写进了
    #: `rank_breakdown.依据`，同一句同时进 `skipReason` 与 `skillWhy`，所以
    #: 一个岗数出两处。**这个数只许往下走。** 改一处 `prescreen` 治不了已经
    #: 落盘的字（那要重跑那几个岗的判断），而为了清几行文字去动用户的数据
    #: 不划算 —— 它们会随着那几个岗归档自己消失。新写的一处当场把这条顶红。
    BASELINE = 2

    def test_no_prose_field_carries_a_status_code(self):
        leaks = _leaks(self.data)
        rows = sorted({f"{f}：…{ctx}…（{code}）" for f, code, ctx in leaks})
        self.assertLessEqual(
            len(leaks), self.BASELINE,
            f"给人读的字段里裸印状态码的从 {self.BASELINE} 涨到了 {len(leaks)}，"
            "说成人话走 `tracker.say()`：\n  " + "\n  ".join(rows[:8]))

    def test_the_baseline_is_not_stale(self):
        """存量清干净了就该把这个数收紧 —— 一个只挂着不降的基线是张免死金牌。"""
        n = len(_leaks(self.data))
        self.assertGreaterEqual(
            self.BASELINE, n,
            "基线比实际还小？")
        self.assertLessEqual(
            self.BASELINE - n, 4,
            f"实际只剩 {n} 处，基线还写着 {self.BASELINE} —— 把它收到 {n}")

    def test_the_location_column_never_shows_a_verdict(self):
        got = _verdict_in_a_city_column(self.data)
        self.assertEqual(got, [],
                         f"{len(got)} 个岗的地点列上印的是判定码：{got[:8]}")


class TheKeyThatCollidedWithTheCityColumn(unittest.TestCase):
    """生成流程那一头：回传格式里不许再有「地名键装判定码」。

    显示层挡住的是已经落盘的字，这一条挡的是**下一个岗还会不会这么写**。
    当初那个键就叫 `location`，写手照着它把判定回填进职位记录的同名字段，
    而那字段是城市。
    """

    def test_the_payload_says_nothing_about_a_city(self):
        block = _rank_payload(RANK_DOC.read_text(encoding="utf-8"))
        self.assertTrue(block, "没找到那份回传格式 —— 下面那条在空串上永远绿")
        self.assertEqual(_city_key_holding_a_verdict(block), [],
                         "回传格式里又有地名键装判定码了，写手会把它回填进城市栏")

    def test_the_location_gate_still_has_a_home(self):
        """删键不等于删那道门。判定必须有落点，否则「想 FAIL 也没地方填」。

        **认键名，不认这个名字出现在哪儿** —— 注释里也写着门名，
        拿 `assertIn` 断言的话，把键删了它照样绿（变异当场照出来过）。
        """
        block = _rank_payload(RANK_DOC.read_text(encoding="utf-8"))
        self.assertRegex(block, r'(?m)^\s+"地点（跨城搬迁）"\s*:')


if __name__ == "__main__":
    unittest.main()
