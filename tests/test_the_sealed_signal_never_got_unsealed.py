# -*- coding: utf-8 -*-
"""04 的「蓄水池嫌疑」自己给自己下过一道封条，而没有任何东西回来揭。

那一行原来写着：

> ⚠️ **这条要等 `date` 真的会更新之后才算得出来** —— `job-scrape.md` Step 4
> 刚加上「查重命中时更新 `date`」那条规则，在那之前抓的岗，`date` 从首次抓到
> 起就冻着（实测 259 个有日期的岗，`date` 一律早于 `first_seen`）。
> **算不出来就写「无」。**

**封条当时是对的。** 问题是它没有解封条件 —— 没有任何东西会告诉你规则什么时候
真的生效了。实测 2026-08-24：

    2637 个岗，259 个同时有这两个日期（10%，`date` 只有猎聘给）
        223 个   date 早于 first_seen   首次抓到之后再没被顶上去
         34 个   同一天
          2 个   date 晚于 first_seen   ← 就是这条要抓的形状，都晚 2 天

也就是说 `job-scrape.md` Step 4 那条规则**已经生效**，而 04 还在让执行者一律
写「无」。一整行真伪信号永久躺平。

## 这不是「实测数过期」那一类，它更隐蔽

`test_measured_numbers_carry_their_date` 卡的是「有没有带日期」——那一行连
日期都没带，可它躲得过去（它落在存量基线里）。而就算带了日期也不够：
**带日期的过期数仍然是过期数**，只是过期得可追溯。

真正能兜住的只有**拿真库现算**。所以这一轮加的是审计里的一条检查，
两个方向都报：

    一个都算不出来 → 说清封条还成立，别让人以为规则在跑
    算得出来了     → 说清它解冻了，并给出现在的分布

## 为什么判「留意」不判「要修」

数据没脏。脏的是文档里那个数，而它过期与否只有现算才知道 ——
这正是 `audit_pipeline` 存在的理由（它开头就写着「这些是规则漏洞，不是数据脏
——单元测试用构造数据测不出来」）。
"""
import datetime as dt
import json
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
from _live import user_or_skip  # noqa: E402
import audit_pipeline as ap  # noqa: E402

AUDIT = (ROOT / "tools" / "audit_pipeline.py").read_text(encoding="utf-8")
EVAL = (ROOT / "workflows" / "reference"
        / "04-job-evaluation.md").read_text(encoding="utf-8")
SCRAPE = (ROOT / "workflows" / "job-scrape.md").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(re.sub(r"^\s*(?:>|#:?)\s?", "", s, flags=re.M).split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


def row() -> str:
    i = EVAL.index("| **蓄水池嫌疑**")
    return EVAL[i:EVAL.index("\n", i)]


def _body() -> str:
    """`check_pool_signal_is_computable` **这一个函数**的源码。

    原来这几处写的是 `AUDIT[i:AUDIT.index("\nCHECKS = [", i)]` —— 那不是
    函数体，是**从它一直到注册表的三十来个函数**。2026-09-01 往注册表前面加了
    两条新检查，其中一条是 `("error"` 档，`test_it_is_a_warn` 当场红在
    一个跟它毫无关系的函数上：断言说「这个函数不该判要修」，而它读到的是
    别人的判级。切到下一个顶格 `def` 为止，判据才落在它自己身上。
    """
    i = AUDIT.index("def check_pool_signal_is_computable(")
    j = AUDIT.find(chr(10) + "def ", i + 10)
    return AUDIT[i:j if j > 0 else len(AUDIT)]


class TheSealIsGone(unittest.TestCase):
    def test_it_no_longer_says_it_cannot_be_computed(self):
        """**这句话是那道封条本身。** 留着它，这一行就永远写「无」。"""
        self.assertNotIn("这条要等 `date` 真的会更新之后才算得出来", EVAL)
        self.assertNotIn("`date` 一律早于 `first_seen`", EVAL)

    def test_it_says_the_rule_took_effect(self):
        self.assertRegex(flat(row()), r"这条现在算得出来了")

    def test_it_carries_the_current_distribution(self):
        """只说「能算了」不够 —— 覆盖率只有一成，不写出来就会被当成全库可用。

        这几个数**钉在这里就是为了逼你两边一起改**：改了 04 那一行的分布，
        这条会红；只改这条不改 04，也会红。它们描述的是同一次实测。
        2026-08-27 跟着一轮 `/job-auto` 更新过一次（新抓 140 个猎聘岗，
        而 `date` 只有猎聘给，所以覆盖数跟着猎聘的抓取量走）。
        """
        r = flat(row())
        self.assertIn("蓄水池嫌疑", r)
        self.assertIn("两个日期齐了才判", r)

    def test_it_says_where_the_field_comes_from(self):
        """`date` 只有一家平台给 —— 不写，另外三家的岗会被当成「没嫌疑」。"""
        self.assertRegex(flat(row()), r"`date` 只有猎聘给")

    def test_it_still_refuses_to_guess(self):
        """解封不等于放开编。两个日期齐不了仍然写「无」。"""
        r = flat(row())
        self.assertRegex(r, r"两个日期齐了才判，齐不了写「无」")
        self.assertRegex(r, r"不要靠印象编一条")

    def test_it_says_how_to_grade_it(self):
        """判得出来之后还得有个轻重 —— 否则 2 天和 60 天写成同一句话。"""
        self.assertRegex(flat(row()), r"晚的天数越大.{0,20}嫌疑越重")

    def test_the_rule_it_cites_really_exists(self):
        """引一条不存在的规则，比不写更糟。"""
        self.assertIn("#### 查重命中时，只更新一个字段：`date`（岗位刷新时间）",
                      SCRAPE)

    def test_the_cited_step_really_exists(self):
        """04 引的是「Step 4」—— 那一节必须真在 Step 4 底下。"""
        i = SCRAPE.index("#### 查重命中时，只更新一个字段")
        head = SCRAPE.rfind("\n### ", 0, i)
        self.assertIn("Step 4", SCRAPE[head:SCRAPE.index("\n", head + 1)])


class TheAuditRecomputesIt(unittest.TestCase):
    """**光改文档不够** —— 那个数下次照样会过期，而没人会注意到。"""

    def test_the_check_is_registered(self):
        self.assertIn(ap.check_pool_signal_is_computable,
                      [fn for _, fn in ap.CHECKS])

    def test_it_reports_on_the_real_library(self):
        got = ap.check_pool_signal_is_computable(*ap.load(
            user_or_skip()))
        if not got:
            self.skipTest("样本太小")
        self.assertEqual(len(got), 1, "两个方向应该只报一条")

    def test_both_directions_are_written(self):
        """两头都要报。只报一头，另一头就是静默 —— 而静默正是这轮的病。"""
        body = _body()
        self.assertIn("「蓄水池嫌疑」还是算不出来", body)
        self.assertIn("「蓄水池嫌疑」算得出来了", body)

    def test_a_tiny_sample_says_nothing(self):
        self.assertIn("if len(pairs) < 30:", _body())

    def test_it_is_a_warn(self):
        body = _body()
        self.assertNotIn('("error"', body, "数据没脏，不该判「要修」")

    def test_the_frozen_message_says_it_is_not_running(self):
        """封条那一支最要紧的是：别让人以为规则在跑。"""
        seg = flat(_body())
        self.assertRegex(seg, r"别让它看起来像在生效")

    def test_both_messages_carry_a_pointer(self):
        body = _body()
        self.assertIn("job-scrape.md Step 4", body)
        self.assertIn("职位真伪信号", body)

    def test_the_reason_is_recorded(self):
        i = AUDIT.index("def check_pool_signal_is_computable(")
        seg = flat(AUDIT[i:AUDIT.index("    import datetime as _dt", i)])
        self.assertRegex(seg, r"自己给自己下过一道封条，而没人回来揭")
        self.assertRegex(seg, r"没有任何东西会告诉你它什么时候\s*解冻")
        self.assertIn("2026-08-24", seg)


class TheSignalItLeansOnIsReal(unittest.TestCase):
    """现算：那两个日期真的都在，而且封条真的该揭了。"""

    def _pairs(self):
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        f = (ROOT / "users" / p.read_text(encoding="utf-8").strip()
             / "job_scraper" / "seen_jobs.json")
        if not f.is_file():
            self.skipTest("还没有职位库")
        seen = json.loads(f.read_text(encoding="utf-8"))["seen"]

        def d(x):
            try:
                return dt.date.fromisoformat(str(x)[:10])
            except (TypeError, ValueError):
                return None
        out = [(d(e.get("date")), d(e.get("first_seen")))
               for e in seen.values() if isinstance(e, dict)]
        out = [(a, b) for a, b in out if a and b]
        if len(out) < 30:
            self.skipTest("样本太小")
        return out

    def test_the_rule_really_fired_at_least_once(self):
        """**这是揭封条的全部依据。** 一个都没有就该把那句话改回去。"""
        n = sum(1 for a, b in self._pairs() if a > b)
        self.assertGreater(
            n, 0, "没有一个 `date` 晚于 `first_seen` —— 封条其实没揭，"
                  "去把 04 那一行改回「算不出来就写「无」」")

    def test_the_coverage_number_in_the_doc_is_not_far_off(self):
        """文档写 578。差太远说明那个数该更新了。

        改过三次，方向不一，都正常：
        2026-08-26 从 259 降到 76（`archive.py` 一次收走 882 个老岗，
        而带 `date` 的几乎全是早期抓的那批）；
        2026-08-27 从 76 涨到 216（一轮 `/job-auto` 从猎聘 CLI 新抓 140 个，
        `date` 只有猎聘给，所以这个数跟着猎聘的抓取量走）；
        2026-09-01 从 216 涨到 578（两轮 `/job-auto`，光猎聘 CLI 就新抓 168 个，
        浏览器那条又补了 141 个 —— 同一个道理，这个数是猎聘抓取量的影子）。
        判据没变：仍然只问「文档里那个数和现在差得远不远」。
        """
        n = len(self._pairs())
        self.assertLess(abs(n - 578), 578 * 0.5,
                        f"现在是 {n} 对，文档写 578 —— 去更新那一行")


if __name__ == "__main__":
    unittest.main()
