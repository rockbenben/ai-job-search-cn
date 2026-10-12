# -*- coding: utf-8 -*-
"""一份岗一把钥匙：两份库都只许用一代键，且不许同一个岗两边各有一份。

## 钉的是什么

2026-10-12 那次问的是「有些岗是不是同时存在于热库和存档」。答是会，
而且原因不在归档那一侧：**查重按键比，而键换过三代没迁过**
（过程记在 `tools/rekey.py` 的 docstring 与
`tests/test_the_archive_is_not_invisible_to_the_dedupe.py`）。

修完之后这条不变量才说得出口：

1. 有链接的条目，键必须是 `stable_id(url, title)` —— 两边都是；
2. 面板那层叠加（`user_state.json`）的每个键还指得到一个岗；
3. 同一个岗（链接 + 职位名）**不许在两边都有**。

第 3 条是用户问的那件事本身。它以前只能靠事后审计发现
（`audit_pipeline`「同一个岗热库和存档各有一份」，只报不改），
这里把它抬成一条会红的守卫 —— 因为再发生一次的代价不是难看，
是**花额度把已经出局的岗重评一遍**，而那份旧记录还在存档里等着各自演化。

没有活动用户 / 没有库的时候整条 skip：这是真数据守卫，不是夹具测试。
"""
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import _cli  # noqa: E402


def real_stores():
    if not (ROOT / ".active_user").is_file():
        return None
    user = _cli.pick_user("", root=ROOT)
    base = _cli.store_dir(user, ROOT)
    sj = base / "seen_jobs.json"
    if not sj.is_file():
        return None
    hot = _cli.seen_of(json.loads(sj.read_text(encoding="utf-8")))
    return {"user": user, "sj": sj, "hot": hot, "cold": _cli.archived(user, root=ROOT)}


class OneKeyPerJob(unittest.TestCase):
    def setUp(self):
        self.s = real_stores()
        if not self.s:
            self.skipTest("没有活动用户或职位库")

    def test_every_row_uses_the_current_key(self):
        for name, rows in (("热库", self.s["hot"]), ("存档", self.s["cold"])):
            bad = [k for k, e in rows.items()
                   if isinstance(e, dict) and e.get("url") and _cli.job_key(e) != k]
            if bad:
                self.fail(f"{name}里 {len(bad)} 条的键不是当前这一代（例："
                          f"{'、'.join(str(k)[:40] for k in bad[:3])}）—— "
                          f"查重又会漏。修：python tools/rekey.py --apply")

    def test_the_panel_marks_still_point_at_a_job(self):
        st = _cli.load_user_state(self.s["sj"])
        keys = set(self.s["hot"]) | set(self.s["cold"])
        orphan = [k for k in st if k not in keys]
        if orphan:
            self.fail(f"{len(orphan)} 条「不投/已下线」标记指不到岗了（例："
                      f"{'、'.join(str(k)[:40] for k in orphan[:3])}）—— "
                      f"换键时没跟着换。修：python tools/rekey.py --apply")

    def test_no_job_lives_in_both_stores(self):
        """用户问的那件事。判据与查重同源：链接 + 职位名。"""
        hot = {_cli.job_token(e.get("url"), e.get("title"))
               for e in self.s["hot"].values()
               if isinstance(e, dict) and e.get("url")}
        cold = {_cli.job_token(e.get("url"), e.get("title"))
                for e in self.s["cold"].values()
                if isinstance(e, dict) and e.get("url")}
        both = hot & cold
        self.assertEqual(both, set(),
                         f"{len(both)} 个岗热库和存档各有一份。这里不代删——"
                         f"哪份新要看评分日期和有没有材料：/job-apply <职位链接>")


class TheRuleSaysIndexNotKeys(unittest.TestCase):
    """正本别再教回去比键 —— 那次就是这么漏掉 3040 条存档的。"""

    def test_scrape_step_uses_the_index(self):
        wf = (ROOT / "workflows" / "job-scrape.md").read_text(encoding="utf-8")
        self.assertIn("_cli.seen_index", wf)
        # 允许**引用**旧写法（那段历史正是这里的教训），不许再把它当**该敲的代码**给出去
        self.assertNotIn("seen_keys = set(seen)", wf,
                         "又教回并键查重了：旧键那 96% 的存档认不出来")

    def test_nobody_rebuilds_the_key_formula(self):
        """`stable_id` 的正本在 `_cli`；再出现第二份算式就是把同一件事抄两处。"""
        hits = [p.name for p in (ROOT / "tools").glob("*.py")
                if '{url}#{title}' in p.read_text(encoding="utf-8")]
        self.assertEqual(hits, ["_cli.py"], f"键的算式有第二份：{hits}")


if __name__ == "__main__":
    unittest.main()
