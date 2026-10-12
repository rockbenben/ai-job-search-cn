# -*- coding: utf-8 -*-
"""查登录态只能靠「跳不跳」，不能靠导航栏上写没写「登录/注册」。

## 事故

2026-10-12 一轮 `/job-auto`，账号全程登着，执行者连着判错三次：

    BOSS 直聘  导航栏显示「登录/注册」   → 判未登录 ❌  实际已登录
    智联招聘  导航栏显示「登录/注册」   → 判未登录 ❌  实际已登录
    前程无忧  导航栏显示「创建简历」     → 判未登录 ❌  实际已登录

代价是实打实的：用户被要求去登一个**已经登过**的账号，而真正的问题
（搜索结果页不出数据）从头到尾没人说。

## 为什么「顶上写没写登录」不成立

1. **同一格服务两种状态。** 未登录时是「登录/注册」，登进去之后往往还是
   同一个位置换成另一个词 —— 于是两边都能读成「没登」。
2. **页面没渲染出账号信息时最容易误判。** 实测里智联首页的视口只有
   650px 宽，账号那格被挤出屏幕外，于是判成未登录。
3. **它会反过来骗人。** 用户登完之后那一格未必立刻变（页面没重渲染），
   于是又判一次未登录 —— 用户第二次被要求登录同一���账号。

## 唯一不骗的判据

**开一个「不登录就跳走」的页面，看 URL 落没落到登录域名上。**
逐站的验证页面写在 `cdp-portals.md`「开跑前先查登录态」那张表里。

还有一条同样重要：**登录态对了，页面也未必给数据。**
2026-10-12 四家全登着，猎聘与 BOSS 的搜索结果页仍然只出空壳。
**「页面不出数据」不是「没登录」**，两者混着报，真正的原因就永远找不到。
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = ROOT / "workflows" / "reference" / "cdp-portals.md"

DOC_TXT = DOC.read_text(encoding="utf-8")


def _section(title):
    i = DOC_TXT.index(title)
    j = DOC_TXT.find("\n## ", i + 1)
    return DOC_TXT[i:j if j > 0 else len(DOC_TXT)]


class TheLoginCheckRedirectsInsteadOfReadingTheNav(unittest.TestCase):
    SEC = _section("## 开跑前先查登录态")

    def test_it_says_not_to_use_the_nav_wording(self):
        self.assertRegex(
            self.SEC, r"不要用「页面顶上有没有",
            "原来那条判据被撤了，但没写下来为什么 —— 下一个人会照旧用回去")

    def test_it_names_the_redirect_as_the_criterion(self):
        self.assertRegex(self.SEC, r"看 URL|跳不跳|不登录就跳走",
                         "没有把「跳转」写成判据")

    def test_each_site_has_a_page_to_probe(self):
        """没有那张表，执行者又要自己挑页面 —— 而挑的多半是不需要登录的那个。"""
        for host in ("login.51job.com", "passport.zhaopin.com"):
            self.assertIn(host, self.SEC,
                          f"没写 {host} 这个登录落点，判据落不到实处")
        for probe in ("/web/user/?intent=0", "c.liepin.com/resume/edit"):
            self.assertIn(probe, self.SEC, f"{probe} 没写进探针表")

    def test_it_does_not_say_all_four_redirect(self):
        """实测两家根本不动 URL —— 说成「看跳没跳」会把它们判反。"""
        self.assertRegex(
            self.SEC, r"URL 不动|URL 不会变",
            "没记下 BOSS 与猎聘不换地址：照抄「看跳没跳」会判反")

    def test_the_universal_criterion_is_the_account_marker(self):
        """四种表现（跳转/标题/表单/姓名）之下得有那一条共同的话。"""
        self.assertRegex(
            self.SEC, r"账号专属",
            "没把四种表现收成一条通则 —— 下一个人还是会照抄第一家")

    def test_the_three_real_mistakes_are_recorded(self):
        """实测数与日期要留在原地，不是留在 commit message 里。"""
        for w in ("BOSS 直聘", "智联招聘", "前程无忧"):
            self.assertIn(w, self.SEC, f"{w} 那一行实测没记")
        self.assertIn("2026-10-12", self.SEC, "实测日期没留在原地")

    def test_a_blank_page_is_not_read_as_logged_out(self):
        """这一次真正的问题就是它：登录态对了但页面不出数据。"""
        self.assertRegex(self.SEC, r"页面不出数据\s*≠\s*没登录|不出数据.*不是「没登录」",
                         "没把「页面不出数据 ≠ 没登录」写下来 —— "
                         "这两种混着报，真正的原因就永远找不到")


class TheOldCriterionIsGoneFromTheDoc(unittest.TestCase):
    def test_it_no_longer_teaches_the_nav_test(self):
        """正本里不许留着「页面顶部是不是『登录/注册』」当判据。"""
        body = "\n".join(ln for ln in _section(
            "## 开跑前先查登录态").splitlines()
            if not ln.strip().startswith(">"))
        self.assertNotIn("页面顶部是不是", body,
                         "正文仍在教用导航栏那一格判登录态")


if __name__ == "__main__":
    unittest.main()