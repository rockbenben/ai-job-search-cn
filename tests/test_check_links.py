# -*- coding: utf-8 -*-
"""链接复核：只把「页面明写下线」写回状态。

2026-11-13 用户当面纠正：猎聘那个 1 KB 通用落地页是**没权限**，不是下线。
此前一轮据此把 65 个岗标成已下线，全部回滚。这些测试钉死那次事故里
每一类假信号，以及「准确优先于覆盖率」的三道保险。
"""

import datetime
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import check_links as cl  # noqa: E402

URL = "https://jobs.example.test/job/1.shtml"

JD = """Title: 【上海 AI产品经理招聘】-某公司上海招聘信息-猎聘

AI产品经理 30-50k
上海-浦东新区 3-5年 本科 招1人 90天前更新
职位介绍
岗位职责：负责 AI 产品规划。
任职要求：3 年以上产品经验。
猎聘温馨提示
"""

GENERIC_LANDING = f"""Title: 猎聘
URL Source: {URL}
Final URL: https://wow.liepin.com/t1012695/4410f519.html
Markdown Content:
企业服务热线和举报投诉：400-6212-266
"""

RECOMMEND_ONLY = """Title: 【上海 AI产品经理招聘】-猎头顾问上海招聘信息-猎聘
[AI产品经理 【 上海-徐汇区 】 25-40k](https://jobs.example.test/job/2.shtml?d_sfrom=recom_jd)
示例公司甲 聊一聊
[AI产品经理 【 上海-浦东 】 30-50k](https://jobs.example.test/job/3.shtml?d_sfrom=recom_jd)
示例公司乙 聊一聊
"""

HARD_EXPIRED = """Title: 【上海 AI产品经理招聘】-某公司上海招聘信息-猎聘
该职位已暂停招聘
投递了该职位的人还查看了以下职位，快去看看吧
<div class="stop-apply job-expired">
[AI产品经理 【 上海 】 25-40k](...?d_sfrom=recom_jd)
"""

CAPTCHA = """Title: 安全中心-验证码
Final URL: https://safe.liepin.com/page/liepin/captchaPage_ip_PC?euuid=abc
请完成安全验证
"""


class ClassifyOnlyAdmitsPositiveEvidence(unittest.TestCase):
    """没有正向下线文案，就一律不许判下线。"""

    def test_generic_landing_page_is_no_permission_not_expired(self):
        """用户裁定：通用落地页 = 没权限。活岗也会落到这一页。"""
        st, why = cl.classify(GENERIC_LANDING,
                              "https://wow.liepin.com/t1012695/4410f519.html", "猎聘")
        self.assertEqual(st, cl.NO_PERMISSION)
        self.assertNotEqual(st, cl.EXPIRED)

    def test_recommend_only_page_is_not_expired(self):
        """同一个活岗在批量通道里可能只剩推荐位。"""
        st, _ = cl.classify(RECOMMEND_ONLY, "", "【上海 AI产品经理招聘】-猎头顾问上海招聘信息-猎聘")
        self.assertEqual(st, cl.UNKNOWN)

    def test_missing_jd_alone_is_never_evidence(self):
        st, _ = cl.classify("什么都没有的一小段", "", "猎聘")
        self.assertNotEqual(st, cl.EXPIRED)

    def test_captcha_is_no_permission(self):
        st, _ = cl.classify(CAPTCHA, CAPTCHA.split("Final URL: ")[1].split("\n")[0],
                            "安全中心-验证码")
        self.assertEqual(st, cl.NO_PERMISSION)

    def test_verification_page_is_no_permission(self):
        st, _ = cl.classify("Verification required", "", "Verification")
        self.assertEqual(st, cl.NO_PERMISSION)

    def test_boss_seo_aggregate_is_unknown(self):
        st, _ = cl.classify("一些职位卡片", "", "产品经理（智能体方向）是什么职位_示例公司2026年前景待遇-BOSS直聘")
        self.assertEqual(st, cl.UNKNOWN)

    def test_explicit_paused_wording_is_expired(self):
        st, why = cl.classify(HARD_EXPIRED, "", "【上海 AI产品经理招聘】-某公司")
        self.assertEqual(st, cl.EXPIRED)
        self.assertIn("暂停招聘", why)

    def test_51job_explicit_wording_is_expired(self):
        st, why = cl.classify("当前职位审核中或已下线\n重新搜索", "", "招聘 | 前程无忧")
        self.assertEqual(st, cl.EXPIRED)

    def test_offline_template_markup_without_jd_is_expired(self):
        st, _ = cl.classify("职位卡片 <div class='job-expired'>", "", "猎聘")
        self.assertEqual(st, cl.EXPIRED)

    def test_full_jd_vetoes_every_offline_hint(self):
        """活岗证据一票否决：拿得到完整 JD 就是还活着。"""
        st, _ = cl.classify(JD + "\n该职位已暂停招聘", "", "【上海 AI产品经理招聘】")
        self.assertEqual(st, cl.ALIVE)


class ConfirmationAndGuards(unittest.TestCase):
    def test_expired_must_be_confirmed_twice(self):
        with mock.patch.object(cl, "fetch", side_effect=[(HARD_EXPIRED, "", ""),
                                                         (RECOMMEND_ONLY, "", "")]), \
             mock.patch.object(cl.time, "sleep"):
            r = cl.check_one(URL, base="", sleep=0)
        self.assertEqual(r["status"], cl.UNKNOWN)
        self.assertIn("两次不一致", r["evidence"])

    def test_two_hits_stay_expired(self):
        with mock.patch.object(cl, "fetch", side_effect=[(HARD_EXPIRED, "", ""),
                                                         (HARD_EXPIRED, "", "")]), \
             mock.patch.object(cl.time, "sleep"):
            r = cl.check_one(URL, base="", sleep=0)
        self.assertEqual(r["status"], cl.EXPIRED)

    def test_write_skips_existing_human_decision(self):
        """批量写不许覆盖用户亲手标的「不投」（10:44 那次事故）。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "users" / "u" / "job_scraper").mkdir(parents=True)
            seen_f = root / "users" / "u" / "job_scraper" / "seen_jobs.json"
            key = "j" + "a" * 9
            seen_f.write_text(json.dumps({"seen": {key: {"url": URL, "title": "某岗"}}}),
                              encoding="utf-8")
            (seen_f.parent / "user_state.json").write_text(json.dumps(
                {key: {"decision": "skipped", "date": "2026-08-21",
                       "reason": "在总览页标的不投"}}), encoding="utf-8")
            with mock.patch.object(cl, "ROOT", root):
                n = cl.write_expired("u", {key: {"url": URL}}, [URL],
                                     {URL: {"evidence": "页面明写「该职位已暂停招聘」"}})
            self.assertEqual(n, 0)
            st = json.loads((seen_f.parent / "user_state.json").read_text(encoding="utf-8"))
            self.assertEqual(st[key]["decision"], "skipped")

    def test_manual_confirm_can_override_skipped_but_records_it(self):
        """用户拿登录态页面明写的文案确认过，可以覆盖早先的「不投」，但要留痕。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "users" / "u" / "job_scraper").mkdir(parents=True)
            seen_f = root / "users" / "u" / "job_scraper" / "seen_jobs.json"
            key = "j" + "a" * 9
            seen_f.write_text(json.dumps({"seen": {key: {"url": URL, "title": "某岗"}}}),
                              encoding="utf-8")
            (seen_f.parent / "user_state.json").write_text(json.dumps(
                {key: {"decision": "skipped", "date": "2026-08-24",
                       "reason": "在总览页标的不投"}}), encoding="utf-8")
            with mock.patch.object(cl, "ROOT", root):
                n, miss = cl.confirm_manual(
                    "u", [{"url": URL, "evidence": "该职位已暂停招聘"}])
                self.assertEqual((n, miss), (1, 0))
                st = json.loads((seen_f.parent / "user_state.json").read_text(encoding="utf-8"))
                self.assertEqual(st[key]["decision"], "expired")
                self.assertIn("原为 skipped", st[key]["reason"])
                self.assertEqual(cl.undo("u"), 1)  # 人工确认写的也撤得回来

    def test_no_permission_is_not_cached_as_final(self):
        """没权限 = 漏标，每轮都得重查，不能被 max-age 挡掉。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            jd = root / "users" / "u" / "job_scraper"
            jd.mkdir(parents=True)
            (jd / "seen_jobs.json").write_text(json.dumps(
                {"seen": {"j" + "a" * 9: {"url": URL, "first_seen": "2026-01-01"}}}),
                encoding="utf-8")
            (jd / "link_check_state.json").write_text(json.dumps(
                {URL: {"linkStatus": cl.NO_PERMISSION,
                       "linkCheckedAt": datetime.date.today().isoformat()}}),
                encoding="utf-8")
            with mock.patch.object(cl, "ROOT", root):
                _, urls, _ = cl._candidates("u", None, 60, 7)
            self.assertIn(URL, urls)

    def test_write_then_undo_only_touches_own_rows(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "users" / "u" / "job_scraper").mkdir(parents=True)
            seen_f = root / "users" / "u" / "job_scraper" / "seen_jobs.json"
            k1, k2 = "j" + "a" * 9, "j" + "b" * 9
            seen_f.write_text(json.dumps({"seen": {
                k1: {"url": URL}, k2: {"url": URL + "2"}}}), encoding="utf-8")
            (seen_f.parent / "user_state.json").write_text(json.dumps(
                {k2: {"decision": "expired", "date": "2026-08-21"}}), encoding="utf-8")
            state = {URL: {"evidence": "页面明写「该职位已暂停招聘」"}}
            with mock.patch.object(cl, "ROOT", root):
                self.assertEqual(cl.write_expired("u", {k1: {"url": URL}}, [URL], state), 1)
                self.assertEqual(cl.undo("u"), 1)
            st = json.loads((seen_f.parent / "user_state.json").read_text(encoding="utf-8"))
            self.assertNotIn(k1, st)
            self.assertEqual(st[k2]["decision"], "expired")  # 人点的不动


if __name__ == "__main__":
    unittest.main()
