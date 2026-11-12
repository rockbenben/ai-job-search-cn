# -*- coding: utf-8 -*-
"""薪资小节里三个数、两种单位，而只有第一个标了单位。

国内的薪资是「月薪 × 薪数」，薪数在 13 到 20 之间浮动
（实测活动用户 2026-08-23 的库：13薪 17% · 14薪 19% · 15薪 35% · 16薪 19%），
所以「月薪」和「年包 ÷ 12」差得很远，**不能互相顶替**。

`profile.example/candidate.md` 的薪资小节原来是这样：

    - **当前薪资结构：** [...]（月薪 × 薪数，含奖金 / 股票）   ← 标了
    - **期望区间：** [...]                                   ← 没标
    - **可接受底线：** [...]                                 ← 没标

`/job-setup` 那一侧一模一样：前两问都说「按『月薪 × 薪数』描述」，
**底线那一问什么都没说**。

## 代价落在招聘平台的「期望薪资」那个框上

`job-resume.md` 2.6 让人「取值与 `profile/candidate.md` 保持一致」——
一致哪一个？拿年包 ÷ 12 冒充月薪填进去，实测同一份库 2564 个明写薪资的岗里
**337 个（13%）**会被一次筛光，而它们的年包本来都够得着底线——月薪看着不够，
乘上 14、15 薪就够了。**填高了是静默少掉一批，没有任何地方会提醒你。**

## 顺带补了一个字段：能松到哪儿

底线和筛选线**是两个数，两个用途**：底线用来淘汰
（`tools/prescreen.py --annual-floor`），能松到的那个数用来填平台上那个框。
原来只有一个字段，两条用途只能共用它。
"""
import json
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

TPL = (ROOT / "profile.example" / "candidate.md").read_text(encoding="utf-8")
SETUP = (ROOT / "workflows" / "job-setup.md").read_text(encoding="utf-8")
RESUME = (ROOT / "workflows" / "job-resume.md").read_text(encoding="utf-8")


def flat(s: str) -> str:
    s = " ".join(s.split())
    return re.sub(r"(?<=[一-鿿，。；：、（）「」])"
                  r" +(?=[一-鿿，。；：、（）「」])", "", s)


def tpl_salary() -> str:
    i = TPL.index("## 薪资")
    return TPL[i:TPL.index("## 教育背景", i)]


class EverySalaryLineNamesItsUnit(unittest.TestCase):
    """三行里有一行不标，就等着它被答成另一种单位。"""

    def test_all_three_say_monthly_times_months(self):
        for label in ("当前薪资结构", "期望区间", "可接受底线"):
            with self.subTest(label=label):
                line = next(l for l in tpl_salary().splitlines()
                            if label in l)
                self.assertIn("月薪 × 薪数", line, f"「{label}」那一行没标单位")

    def test_the_floor_asks_for_both_numbers(self):
        """只写一个数的话，读它的人还是得自己换算 —— 换算就是出错的地方。"""
        line = next(l for l in tpl_salary().splitlines() if "可接受底线" in l)
        self.assertIn("两个数都写出来", line)

    def test_the_comment_says_why_they_cannot_substitute(self):
        seg = flat(tpl_salary())
        self.assertRegex(seg, r"因为国内这两个数不能互相顶替")
        self.assertRegex(seg, r"13薪 17% · 14薪 19% · 15薪 35% · 16薪 19%")

    def test_the_comment_carries_the_cost(self):
        seg = flat(tpl_salary())
        self.assertRegex(seg, r"2564 个明写薪资的岗中有 337 个（13%）会被一次筛光")

    def test_the_example_does_not_carry_a_real_salary(self):
        """`test_no_maintainer_data_in_repo` 盯着这个：举例要说方法，
        不写某个人的数。第一版写的 `25-35k·14薪` 里那个 `35k`
        正好是资料里的取值，撞上归属词就是泄漏。"""
        seg = flat(tpl_salary())
        self.assertIn("月薪看着不够，乘上 14、15 薪就够了", seg)
        self.assertNotIn("25-35k", seg)
        self.assertRegex(seg, r"\*\*填高了是静默少掉一批。\*\*")
        self.assertIn("2026-08-23", seg)

    def test_the_comment_names_both_consumers(self):
        """一个用来淘汰、一个用来填筛选框 —— 不点名就会被合成一个数。"""
        seg = flat(tpl_salary())
        self.assertIn("workflows/job-resume.md", seg)
        self.assertIn("tools/prescreen.py --annual-floor", seg)


class TheNegotiableFloorIsItsOwnField(unittest.TestCase):
    def test_the_placeholder_exists(self):
        self.assertIn("[YOUR_SALARY_FLOOR_NEGOTIABLE]", tpl_salary())

    def test_it_hangs_under_the_floor_not_beside_it(self):
        """它是底线的一个变体，不是第四个独立概念 —— 缩进要说明这件事。"""
        line = next(l for l in tpl_salary().splitlines()
                    if "YOUR_SALARY_FLOOR_NEGOTIABLE" in l)
        self.assertTrue(line.startswith("  - "), f"缩进不对：{line!r}")

    def test_it_says_what_to_write_when_there_is_none(self):
        """留空和「不松」是两件事 —— 同硬门那条规矩。"""
        line = next(l for l in tpl_salary().splitlines()
                    if "YOUR_SALARY_FLOOR_NEGOTIABLE" in l)
        self.assertIn("没有就写「不松」", line)

    def test_the_two_uses_are_spelled_out(self):
        seg = flat(tpl_salary())
        self.assertRegex(seg, r"底线用来淘汰")
        self.assertRegex(seg, r"可谈到用来填平台上那个筛选框")

    def test_the_original_floor_field_survives(self):
        """新字段不能把旧的挤掉 —— 淘汰那一路还靠它。"""
        self.assertIn("[YOUR_SALARY_FLOOR]", tpl_salary())


class NothingInTheTemplateIsDeadOnArrival(unittest.TestCase):
    """模板里加了字段，就必须有人问它。"""

    def _placeholders(self) -> list:
        return sorted(set(re.findall(r"\[YOUR_[A-Z_]+\]", tpl_salary())))

    def test_there_are_placeholders_to_check(self):
        self.assertGreaterEqual(len(self._placeholders()), 4,
                                "抽不到占位符，这条判据失去来源")

    def test_every_one_is_asked_for_in_setup(self):
        missing = [ph for ph in self._placeholders() if ph not in SETUP]
        self.assertEqual(missing, [],
                         f"模板里有、`/job-setup` 不问：{missing}")

    def test_the_negotiable_one_has_its_own_question(self):
        self.assertIn("**问：能松到哪儿**", SETUP)
        self.assertIn("[YOUR_SALARY_FLOOR_NEGOTIABLE]", SETUP)

    def test_the_new_question_says_what_it_is_for(self):
        i = SETUP.index("**问：能松到哪儿**")
        seg = flat(SETUP[i:i + 900])
        self.assertRegex(seg, r"底线用来淘汰")
        self.assertRegex(seg, r"填低了只是多收几个招呼，填高了就再也看不见那批岗")

    def test_it_says_it_is_not_the_same_as_the_floor(self):
        i = SETUP.index("**问：能松到哪儿**")
        seg = flat(SETUP[i:i + 900])
        self.assertRegex(seg, r"\*\*不是一回事，用途也不同\*\*")


class TheSetupQuestionsAllNameTheUnit(unittest.TestCase):
    def _q(self, title: str) -> str:
        i = SETUP.index(title)
        return flat(SETUP[i:i + 700])

    def test_the_floor_question_now_names_it(self):
        self.assertIn("还是按「月薪 × 薪数」说", self._q("**问：可接受的底线**"))

    def test_the_first_two_still_name_it(self):
        """它们本来就是对的写法 —— 别被这次改动带走。"""
        self.assertIn("国内一般按「月薪 × 薪数」描述",
                      self._q("**问：当前薪资结构**"))
        self.assertIn("同样按「月薪 × 薪数」描述",
                      self._q("**问：期望薪资区间**"))

    def test_the_floor_question_records_what_went_wrong(self):
        seg = self._q("**问：可接受的底线**")
        self.assertRegex(seg, r"单位这句原来只有上面两问有，这一问没有")
        self.assertRegex(seg, r"同一小节里三个数，两种单位")

    def test_the_floor_is_still_private(self):
        """「不会主动亮给对方」是这一问的既有承诺，不能被顺手删掉。"""
        self.assertIn("不会主动亮给对方", self._q("**问：可接受的底线**"))

    def test_it_points_at_the_measurement_instead_of_copying_it(self):
        """判据只留一份 —— 这里指过去，不再抄一遍 337。"""
        seg = self._q("**问：可接受的底线**")
        self.assertIn("workflows/job-resume.md", seg)
        self.assertNotIn("337", seg, "又抄了一份实测数，两处早晚分叉")


class TheChecklistRowExists(unittest.TestCase):
    def _row(self) -> str:
        i = RESUME.index("| **期望薪资** |")
        return RESUME[i:RESUME.index("\n|", i + 5)]

    def test_salary_got_its_own_row(self):
        self.assertIn("| **期望薪资** |", RESUME)

    def test_the_other_two_stayed_together(self):
        self.assertIn("| **期望岗位 / 期望城市** |", RESUME,
                      "拆薪资的时候把另外两项也拆散了")

    def test_it_forbids_dividing_the_annual_by_twelve(self):
        self.assertIn("不要拿年包 ÷ 12 冒充月薪", flat(self._row()))

    def test_it_tells_you_to_look_at_the_box_first(self):
        """平台那个框要月薪还是年薪，这里不替它断言 —— 让执行者去看。"""
        self.assertIn("先看清平台那个框要的是月薪还是年薪", flat(self._row()))

    def test_it_carries_the_measurement(self):
        seg = flat(self._row())
        self.assertIn("月薪看着不够，乘上 14、15 薪就够了", seg)
        self.assertIn("按可谈的下限填，不按理想值填", seg)

    def test_it_states_both_sides_of_the_trade(self):
        """只说「填低了没事」是不诚实的 —— 那个数对方看得见。"""
        seg = flat(self._row())
        self.assertRegex(seg, r"填低了那个数对方看得见，有被往下压的一面")
        self.assertRegex(seg, r"填高了是\*\*静默\*\*少掉一批")

    def test_it_points_at_the_field_to_use(self):
        seg = flat(self._row())
        self.assertIn("「可谈到」那一行就是给这个框用的", seg)
        self.assertIn("profile.example/candidate.md", seg)

    def test_the_rest_of_the_checklist_survives(self):
        i = RESUME.index("| 要看什么 | 为什么它决定你会不会被搜到 |")
        seg = RESUME[i:RESUME.index("**报告里怎么写**", i)]
        for row in ("最近刷新/活跃时间", "简历公开范围", "求职状态",
                    "简历完整度", "屏蔽现任公司",
                    "在线简历和 PDF 说的是不是一回事"):
            with self.subTest(row=row):
                self.assertIn(row, seg)

    def test_the_read_only_rule_survives(self):
        """这一节全部在平台上、在登录态后面 —— 工具只读不改。"""
        self.assertIn("**不要动任何设置**", RESUME)


class TheSignalItLeansOnIsReal(unittest.TestCase):
    """有语料时验一次：那 337 个岗真的存在于两个数之间。"""

    def _seen(self):
        p = ROOT / ".active_user"
        if not p.is_file():
            self.skipTest("没有活动用户")
        u = p.read_text(encoding="utf-8").strip()
        f = ROOT / "users" / u / "job_scraper" / "seen_jobs.json"
        if not f.is_file():
            self.skipTest("没有职位库")
        return json.loads(f.read_text(encoding="utf-8"))["seen"]

    @staticmethod
    def _hi_month(s: str):
        s = (s or "").replace("K", "k")
        if "万" in s or "w" in s.lower():
            v = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*(?=[万wW])", s)]
            return max(v) * 10 if v else None
        v = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*k", s)]
        return max(v) if v else None

    def _band(self, lo: float, hi: float, floor_wan: float):
        n = 0
        for e in self._seen().values():
            if not isinstance(e, dict):
                continue
            s = e.get("salary") or ""
            if not re.search(r"\d", s):
                continue
            m = self._hi_month(s)
            if not m or m > 300:
                continue
            mm = e.get("salaryMonths")
            g = re.search(r"(\d{2})薪", s)
            months = mm if isinstance(mm, (int, float)) and mm else (
                int(g.group(1)) if g else 16)
            if m * months / 10 >= floor_wan and lo <= m < hi:
                n += 1
        return n

    def test_the_band_between_the_two_numbers_is_not_empty(self):
        """底线 42 万：按 15 薪折是 28k，按 12 个月折是 35k。"""
        n = self._band(28.0, 37.5, 42.0)
        self.assertGreater(n, 50,
                           f"两个数之间只有 {n} 个岗 —— 这条规则的依据变弱了，"
                           f"重新量一次")

    def test_the_months_really_vary(self):
        """薪数要是都一样，月薪和年包就能互换，整条规则不成立。"""
        got = set()
        for e in self._seen().values():
            if not isinstance(e, dict):
                continue
            g = re.search(r"(\d{2})薪", e.get("salary") or "")
            if g:
                got.add(int(g.group(1)))
        self.assertGreater(len(got), 3, f"薪数只见到 {sorted(got)}")


if __name__ == "__main__":
    unittest.main()
