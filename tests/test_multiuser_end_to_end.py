"""两个用户真跑一遍：导出的快照装的是谁的数据。

## 为什么现有覆盖不够

`test_cli_contract.py` 把多用户这件事验得很细——`--user` 有没有声明、未知用户会不会
被拒、指针会不会被挪、`serve` 有没有把用户传下去。但那些**全是契约层**：
查 AST、打桩、验判定函数。

而这一类缺陷的形状恰恰是「零件都对、装起来不对」。原始那个 bug
（`fix(cli): 工具不解析参数 —— --user 被静默吞掉`）就是：每个零件看着都没问题，
真跑起来端出的是**另一个人**的一整份职位数据。

所以这里不打桩：造一个临时用户，真跑 `export_web_data.py --user`，再打开
`web/public/data.json` 看里面装的是谁的岗。

> 这两条原来跑的是 `bundle_web.py`（单文件面板的打包器）。那条路已经删掉——
> 它在没有服务时会把状态按钮整排藏起来，只剩一个写不回盘的「不投这个岗」。
> 守卫本身仍然要在：**「标着甲、装着乙」的风险跟着数据走，不跟着渲染方式走**，
> 所以改指向导出器，它才是产生 `activeUser` 那一步。

## 两个场景

1. **给 B 出产物，不许混进 A 的数据，也不许动 A 的任何东西。**
2. **B 跑完之后 A 打开面板** —— 共享的 `web/public/data.json` 此刻装着 B 的数据，
   且比 A 的上游文件新。只比时间戳的话它会被判「不过期」原样端出去：时间对、
   人不对，页面上没有任何异常提示。这一条验的就是那道闸门**在真实路径上**管用。

`web/public/data.json` 是派生快照，两个场景都会重写它；跑完按原样还原。
"""

import json
import os
import shutil
import subprocess
import sys
import time
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))
from _live import keep_panel_snapshot  # noqa: E402
import _cli  # noqa: E402
TEMP_USER = "_多用户隔离测试"
DATA = _cli.dashboard_dir(TEMP_USER, ROOT) / "data.json"
AU = ROOT / ".active_user"
MARK = "测试公司甲"          # 只可能出现在临时用户的数据里


def _env():
    return {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}


def _make_temp_user(path: Path):
    shutil.rmtree(path, ignore_errors=True)
    (path / "job_scraper").mkdir(parents=True)
    (path / "profile").mkdir(parents=True)
    (path / "profile" / "candidate.md").write_text(
        "# 候选人资料\n\n## 身份\n- 城市：某市\n", encoding="utf-8")
    seen = {f"https://t/{i}": {
        "url": f"https://t/{i}", "title": f"测试岗{i}",
        "company": f"测试公司{'甲乙丙'[i]}", "status": "ranked",
        "rank_score": 80 - i, "rank_verdict": "值得投",
        "salary": "20-30k", "location": "某市"} for i in range(3)}
    (path / "job_scraper" / "seen_jobs.json").write_text(
        json.dumps({"seen": seen}, ensure_ascii=False), encoding="utf-8")


class Base(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not AU.is_file():
            raise unittest.SkipTest("这个 clone 里还没有活动用户")
        cls.real = AU.read_text(encoding="utf-8").strip()
        if not (ROOT / "users" / cls.real / "job_scraper" / "seen_jobs.json").is_file():
            raise unittest.SkipTest("活动用户还没有职位数据，比不出隔离")
        cls.udir = ROOT / "users" / TEMP_USER

    def setUp(self):
        self._au = AU.read_bytes()
        # 面板快照的还原走共享的那一个：它同时管「原来没有 → 跑完删掉」，
        # 而这里原来只管「原来有 → 写回去」（判据见
        # tests/test_a_probe_run_leaves_nothing_behind.py）。
        self._restore_snapshot = keep_panel_snapshot()
        _make_temp_user(self.udir)

    def tearDown(self):
        shutil.rmtree(self.udir, ignore_errors=True)
        AU.write_bytes(self._au)
        self._restore_snapshot()

    def _export_for_temp_user(self):
        r = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "export_web_data.py"),
             "--user", TEMP_USER],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=_env(), timeout=300)
        self.assertEqual(r.returncode, 0, f"给临时用户导出失败：\n{r.stdout}\n{r.stderr}")
        self.assertTrue(DATA.is_file(), "导出器没写出 data.json")
        return json.loads(DATA.read_text(encoding="utf-8"))


class TheSnapshotHoldsOnlyThatUsersData(Base):

    def test_it_contains_that_users_jobs_and_no_one_elses(self):
        data = self._export_for_temp_user()
        comps = {j.get("company") for j in data.get("jobs") or []}
        self.assertIn(MARK, comps, "快照里没有这个用户自己的岗")
        self.assertEqual(
            data.get("activeUser"), TEMP_USER,
            f"快照标着别人的名字：{data.get('activeUser')!r}")
        real_seen = json.loads(
            (ROOT / "users" / self.real / "job_scraper" / "seen_jobs.json")
            .read_text(encoding="utf-8")).get("seen", {})
        others = {e.get("company") for e in real_seen.values() if e.get("company")}
        leaked = sorted(comps & others)
        self.assertEqual(leaked, [], f"另一个用户的公司混进来了：{leaked}")

    def test_it_does_not_touch_the_other_user(self):
        self._export_for_temp_user()
        self.assertEqual(AU.read_bytes(), self._au,
                         "`--user` 把活动用户指针改掉了 —— 瞄一眼别人的进度不该换人")


class AFresherSnapshotIsNotEnoughItMustBeHis(Base):
    """B 跑完之后 A 打开面板 —— 共享快照此刻装着 B 的数据，而且比 A 的上游文件新。

    只比时间戳的话它会被判「不过期」原样端出去：**时间对、人不对**，页面上没有任何
    异常提示。`test_cli_contract` 验过那个判定函数本身；这一条验它**在真实路径上**
    真的拦得住。
    """

    def test_serving_regenerates_instead_of_handing_over_the_wrong_persons_data(self):
        staged = self._export_for_temp_user()
        self.assertEqual(staged.get("activeUser"), TEMP_USER,
                         "铺垫没成立：共享快照里装的不是临时用户的数据")

        port = 29041
        proc = subprocess.Popen(
            [sys.executable, str(ROOT / "tools" / "serve.py"), "--port", str(port)],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=_env())
        try:
            got = None
            for _ in range(40):
                try:
                    got = json.loads(urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/data.json", timeout=10).read().decode())
                    break
                except Exception:
                    time.sleep(0.5)
            self.assertIsNotNone(got, "服务没起来")
            self.assertEqual(
                got.get("activeUser"), self.real,
                "把另一个用户的整份职位数据端给了当前用户 —— "
                "快照比上游新就判「不过期」，时间对、人不对")
            self.assertNotIn(
                MARK, json.dumps(got, ensure_ascii=False),
                "端出来的数据里混着另一个用户的岗")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    unittest.main()
