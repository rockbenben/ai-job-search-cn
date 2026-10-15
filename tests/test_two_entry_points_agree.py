# -*- coding: utf-8 -*-
"""自检和面板不能给出相反的建议，也不能给出不同的数。

2026-08-13 实测，同一时刻：

    自检：投出去了，在等回复。下一步：跑 /job-scrape 补充名单
    面板：还有 107 个岗材料就绪但没投

**两条建议方向相反**——一个说去抓新岗，一个说把手上的发掉。而当时刚跑完三轮
补货、证明词表在这些渠道上挖空了，正确的是面板那条。根因是 `doctor.next_step`
最后那条分支只看「投过没」，从不检查还有没有备好没发的材料。

修的过程里又撞了一次同类问题：给 doctor 补计数时**把面板的匹配规则抄了一遍**，
先按公司名匹配（101 vs 107），改 URL 精确匹配（132 vs 107）——两版都不对，
错的方向还相反。差的 25 个是 18 个重复挂牌 + 7 个已下线，那套归并判据只有导出器有。
最后改成 doctor 优先读面板快照，抄不动的就别抄。
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import doctor  # noqa: E402


class SendBeforeScrape(unittest.TestCase):

    def test_ready_materials_outrank_scraping(self):
        """有备好没发的材料时，下一步必须是「发」，不能是「抓」。"""
        st = {"in_repo": True, "user": "x", "profile_ok": True, "scraped": 50,
              "ranked": 50, "materials": 20, "applied": 3, "ready": 12,
              "interviewing": 0, "offers": 0}
        lines = doctor.next_step({}, st)
        self.assertIn("12 个岗材料备好了还没发", lines[0],
                      "第一行不是「去发」——用户只读第一行")
        # 正文里提一句「名单见底了再去 /job-auto 补货」是对的（那是之后的事），
        # 不许的是把抓取摆成**这一步**该做的事。所以只看它出现在哪：
        # 必须跟在「再去」后面，不能自成一条建议。
        #
        # **盯的是 `/job-auto` 而不是 `/job-scrape`（2026-10-14）。**
        # 原来这里扫的是 `/job-scrape`，而自检里那一条已经被换掉两次
        # （2026-08-29、2026-10-14），换到最后自检的「下一步」里一个
        # `/job-scrape` 都不剩了 —— **扫的东西没了，这条守卫就空转**。
        # 抓取那条命令现在是 `/job-auto`，它才该被盯住。
        for ln in lines:
            if "/job-auto" in ln:
                self.assertIn("再去", ln,
                              f"抓取被当成了这一步的建议：{ln.strip()}")

    def test_scraping_comes_back_when_nothing_is_pending(self):
        """发完了才该去补货——这条分支不能被上一条吃掉。"""
        st = {"in_repo": True, "user": "x", "profile_ok": True, "scraped": 50,
              "ranked": 50, "materials": 20, "applied": 20, "ready": 0,
              "interviewing": 0, "offers": 0}
        out = "\n".join(doctor.next_step({}, st))
        # 2026-08-29 用户裁定（`AGENTS.md`「跟进归用户，工具不催」）：「有材料没发 → 先发；没有 → `/job-auto` 接着抓」
        # —— 补货那条命令由那句话点名，不再是 `/job-scrape`。
        self.assertIn("/job-auto", out)

    def test_interview_still_wins(self):
        """面试比发材料更要紧，顺序不能被这次改动打乱。"""
        st = {"in_repo": True, "user": "x", "profile_ok": True, "scraped": 50,
              "ranked": 50, "materials": 20, "applied": 3, "ready": 12,
              "interviewing": 2, "offers": 0}
        out = "\n".join(doctor.next_step({}, st))
        self.assertIn("/job-interview", out)


class TheNumberComesFromOnePlace(unittest.TestCase):

    def test_doctor_prefers_the_panel_snapshot(self):
        """别把导出器的归并逻辑抄第二遍——抄了就会飘。"""
        src = (ROOT / "tools" / "doctor.py").read_text(encoding="utf-8")
        self.assertIn("data.json", src)
        self.assertIn("activeUser", src, "读快照却不校验是谁的，会串用户")
        self.assertIn("dupOf", src, "快照口径没排掉重复挂牌")

    def test_they_agree_on_the_real_data(self):
        """控制用例：这台机器上两边真的报同一个数。

        `count_ready` 2026-08-13 起返回 `(总数, 其中可以直接发的)` 两个数
        （「可以考虑」那一档按框架是「先问清楚再决定」，不能和「值得投」加在一起
        催人发，见 `test_ready_is_split_by_verdict.py`）。**两个都要对得上**——
        只比总数的话，分档那个数飘了这条守卫看不见。
        """
        snap = ROOT / "web" / "public" / "data.json"
        ptr = ROOT / ".active_user"
        if not (snap.is_file() and ptr.is_file()):
            self.skipTest("没有面板快照，跳过")
        user = ptr.read_text(encoding="utf-8").strip()
        d = json.loads(snap.read_text(encoding="utf-8"))
        if (d.get("activeUser") or "") != user:
            self.skipTest("快照过期")
        # **口径走 `export_web_data.funnels_of`，别在这儿再写一份。**
        #
        # 原来这里是手写的五个条件（materials / not applied / not dupOf /
        # not skipped / not expired）。2026-08-26 它和导出器差了 1 ——
        # 导出器那份还排掉「判词出局」的岗（`is_out_verdict`）和三类搁置
        # （`is_parked`），而手写这份没有。当天正好出现一个：材料做完之后
        # 才发现同一家的这个岗早就投过，判词改成「跳过」，
        # 导出器不数它（对），这条判据照数（错），于是 63 != 64。
        #
        # 那一刻这条守卫报的是**它自己的**分歧，不是被守的两个入口的分歧 ——
        # 而这个仓库为「同一个判据两份实现」付过的学费，正本就写在
        # `funnels_of` 的说明里。所以这里改成调用它。
        import export_web_data as ex
        live = [j for j in d.get("jobs", [])
                if "materials" in ex.funnels_of(j) and not j.get("applied")]
        panel = len(live)
        panel_strong = sum(1 for j in live if doctor._re_strong(j.get("verdict") or ""))
        mine, mine_strong, mine_asked = doctor.count_ready(
            ROOT / "users" / user, {})
        self.assertEqual(mine, panel,
                         f"自检数 {mine}、面板数 {panel} —— 又飘了")
        self.assertEqual(mine_strong, panel_strong,
                         f"能直接发的：自检 {mine_strong}、面板 {panel_strong} —— 飘了")
        # 第三个数同样两边要一致：终端那句「只有 N 个真列了问题」和面板上
        # 那两枚章（`askBefore` 有没有）说的必须是同一批岗。
        panel_asked = sum(1 for j in live
                          if not doctor._re_strong(j.get("verdict") or "")
                          and j.get("askBefore"))
        self.assertEqual(mine_asked, panel_asked,
                         f"真列了问题的：自检 {mine_asked}、面板 {panel_asked} —— 飘了")


if __name__ == "__main__":
    unittest.main()


class TheRerunCountComesFromOnePlace(unittest.TestCase):
    """「该重跑一遍的有几个」也有两个入口，也得说同一个数。

    终端那句（`stale_materials.py` 印的「当时没读全的 N 个」）和面板上那枚
    `restaleCount`，判据同出一处（`stale_materials.plan`）——`mark_restale`
    的说明里写着「这里只贴标不重算」。**但两边喂给它的「已经出局」那批不是
    同一份**：命令行侧从 `data.json` 现读，导出器从手上这份 `jobs` 现算
    （它正要写的就是那个文件，回头去读等于读上一轮的）。

    也就是说，判据没有第二份实现，**输入却有两条路**——这正是这个仓库反复
    栽的那个形状。上面 `TheNumberComesFromOnePlace` 守的是三个数，这里补第四个。
    """

    def test_they_agree_on_the_real_data(self):
        snap = ROOT / "web" / "public" / "data.json"
        ptr = ROOT / ".active_user"
        if not (snap.is_file() and ptr.is_file()):
            self.skipTest("没有面板快照，跳过")
        user = ptr.read_text(encoding="utf-8").strip()
        d = json.loads(snap.read_text(encoding="utf-8"))
        if (d.get("activeUser") or "") != user:
            self.skipTest("快照过期")
        import stale_materials as sm
        rows, _ = sm.plan(user)
        # 面板贴标的判据是 `flip or blind`（见 `mark_restale`）。这里照抄一遍
        # 反而是新增第二份实现 —— 但它就是那三个字，且两边一飘这条就红，
        # 抄的成本远低于「把 rows 过滤也搬进正本再让两处都调」。
        mine = sum(1 for r in rows if r["flip"] or r["blind"])
        panel = d.get("restaleCount")
        self.assertEqual(
            mine, panel,
            f"该重跑的：命令行 {mine}、面板 {panel} —— 飘了。"
            "面板上那枚数是 mark_restale 贴的，判据同出 stale_materials.plan，"
            "两边差了说明喂进去的「已经出局」那批对不上")

    def test_the_panel_does_not_recompute_the_rule(self):
        """判据只有一份：导出器不许自己再写一遍「什么叫该重跑」。"""
        src = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
        i = src.index("def mark_restale")
        body = src[i:i + 4000]
        self.assertIn("stale_materials", body, "贴标却不问判据的正本")
