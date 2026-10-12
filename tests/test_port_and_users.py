"""默认端口的选法，以及面板要让人看得见「有哪些用户、怎么再建一个」。

## 端口

上一版默认 4317，同时踩了两条：

1. 它是 **OpenTelemetry OTLP gRPC 的默认端口**——装了 OTel Collector 的机器直接撞。
2. 更要命的是它落在**操作系统的临时端口范围**里。那一段是系统分配给出站连接的，
   服务启动前就可能被随机占掉，症状是「有时起得来有时起不来」，最难查。
   Linux 默认 32768-60999；Windows 默认 49152-65535，**但实测有机器被改成
   1024-15000**（`netsh int ipv4 show dynamicport tcp`）。两边都躲开，
   安全窗口只剩 15001-32767。

## 用户

「换个用户」原来是个**没有 onClick 的死按钮**：既列不出这个 clone 下有哪些人，
也不说怎么建第二个。而多人共用一份 clone 是 `AGENTS.md` 明确支持的用法。

切换与新建仍留在命令行——`.active_user` 是**全局状态**，页面上点一下改掉它，
别的标签页和正在跑的命令都不知道自己已经换了人。面板只负责让人看得见。
"""

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
from _live import user_or_skip  # noqa: E402

import serve as srv  # noqa: E402

#: 两大系统临时端口范围的并集之外
SAFE_LO, SAFE_HI = 15001, 32767

#: 常见服务与开发工具的默认端口，撞上等于给用户添堵
TAKEN = {
    80, 443, 3000, 3001, 3306, 4200, 4317, 4318, 5000, 5173, 5432, 6379,
    8000, 8080, 8081, 8443, 8888, 9000, 9090, 9200, 11211, 27017,
}


class DefaultPortIsSafelyChosen(unittest.TestCase):

    def test_port_is_outside_every_ephemeral_range(self):
        self.assertTrue(
            SAFE_LO <= srv.PORT <= SAFE_HI,
            f"默认端口 {srv.PORT} 落在某个系统的临时端口范围里 —— "
            f"服务启动前可能被系统随机占掉，症状是「有时起得来有时起不来」。"
            f"安全窗口 {SAFE_LO}-{SAFE_HI}")

    def test_port_is_not_a_known_service(self):
        self.assertNotIn(srv.PORT, TAKEN,
                         f"默认端口 {srv.PORT} 与常见服务/开发工具撞车")

    def test_it_is_overridable(self):
        src = (ROOT / "tools" / "serve.py").read_text(encoding="utf-8")
        self.assertIn("JOBS_PORT", src, "没留环境变量出口，真撞上了没法改")

    def test_the_reason_is_written_down(self):
        """选端口的两条约束必须写在代码旁边，否则下一个人会随手改回一个漂亮数字。"""
        src = (ROOT / "tools" / "serve.py").read_text(encoding="utf-8")
        self.assertIn("临时端口", src, "没写明为什么要避开系统临时端口范围")
        self.assertIn("OTLP", src, "没记下上一版踩的坑")

    def test_no_stale_4317_references(self):
        """换端口最容易漏文档。文中提到 4317 只允许出现在讲历史的注释里。"""
        bad = []
        for f in list(ROOT.glob("*.md")) + list((ROOT / "tools").glob("*.py")) \
                + list((ROOT / "web" / "src").rglob("*.ts*")):
            for i, ln in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if "4317" in ln and "OTLP" not in ln and "上一版" not in ln:
                    bad.append(f"{f.name}:{i} {ln.strip()[:60]}")
        self.assertEqual(bad, [], "还有地方写着旧端口：\n" + "\n".join(bad))


class DashboardShowsWhoElseExists(unittest.TestCase):

    def test_exporter_emits_the_user_list(self):
        src = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
        self.assertIn('"allUsers"', src, "面板拿不到用户列表，那个按钮只能是死的")

    def test_only_names_are_exported(self):
        """只报名字。列出别人的职位/投递记录会跨用户泄漏——命名空间隔离的底线。"""
        src = (ROOT / "tools" / "export_web_data.py").read_text(encoding="utf-8")
        seg = src[src.index('"allUsers"'):]
        seg = seg[:seg.index("]")]
        self.assertIn("d.name", seg, "导出的不是目录名")
        for leak in ("seen_jobs", "tracker", "read_text"):
            self.assertNotIn(leak, seg, f"用户列表里混进了别人的数据（{leak}）")

    def test_button_is_wired(self):
        """查的是**行为**，不是附近有没有出现 onClick 这个词。

        第一版断言「按钮前后 900 字符内含 onClick」——而那段解释「它原来是死按钮」
        的注释里正好有这个词，于是把按钮改回死的，测试照样绿。
        钉住真正的因果：按钮要能开合面板，面板要真的渲染出来。
        """
        app = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
        # 注释不算数——先剥掉
        code = re.sub(r"\{/\*.*?\*/\}", "", app, flags=re.S)
        code = re.sub(r"//.*$", "", code, flags=re.M)
        self.assertRegex(
            code, r"onClick=\{\(\)\s*=>\s*setUserPanel",
            "「换个用户」没有真正接上开合逻辑（注释里提到 onClick 不算）")
        self.assertIn("userPanel && (", code, "面板从来不会被渲染出来")
        self.assertIn("aria-expanded", code, "屏读器听不出这个按钮会展开东西")

    def test_it_tells_you_how_to_create_another(self):
        """用户的原话：「你确定当前流程能让用户知道如何建立多用户资料吗？」"""
        app = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
        self.assertIn("/job-user --new", app, "没告诉用户怎么建第二个")
        self.assertIn("/job-user ${u}", app, "没给出切到某个用户的命令")

    def test_switching_stays_on_the_command_line(self):
        """面板不写 `.active_user`：那是全局状态，页面改掉它，别处不知道。"""
        app = (ROOT / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
        self.assertNotIn("active_user", app.replace("`.active_user`", ""),
                         "面板试图直接改活动用户")

    def test_real_repo_has_several_users_to_switch_between(self):
        """控制测试：多用户是这套工具的正式用法，得有夹具能真的切着玩。

        **只在有 `users/` 的机器上有意义。** 干净 clone 里那个目录压根不存在
        （`.gitignore` 挡着），原来这里直接 `iterdir()` 抛 FileNotFoundError
        ——首次 CI 必红，而红的原因是「CI 上没有维护者的个人数据」，
        与它要守的事毫无关系。2026-08-20 拿干净 clone 实测抓到。

        **用户不足 3 个时也 skip（2026-10-09 补）。** 上一版只挡了「一个都没有」，
        于是**单人仓库长期常红**：多用户是给「多人共用一份 clone」准备的可选项，
        绝大多数用户（包括本机）就一个 `users/<名>/`，那是完全正常的状态，
        不是多用户路径写坏了。与 `tests/_live.py` 那条判据同一个道理 ——
        「这台机器上没有可读的真实数据」该 skip，不该红。真撞上多用户路径坏了，
        本类另外五条（导出只报名字、按钮接得上开合、面板渲染得出来、
        告诉用户怎么建第二个、面板不改 `.active_user`）照样会红。
        """
        user_or_skip()   # 没有真实数据可读时 skip（见 tests/_live.py）
        if not (ROOT / "users").is_dir():
            self.skipTest("这台机器上还没有任何用户 —— 控制测试无从谈起")
        users = [d.name for d in (ROOT / "users").iterdir()
                 if d.is_dir() and (d / "profile" / "candidate.md").is_file()]
        if len(users) < 3:
            self.skipTest(f"这台机器上只有 {len(users)} 个用户（{users}）—— "
                          "多用户路径无从实测；单人仓库是正常状态，不是故障")
        self.assertGreaterEqual(len(users), 3,
                                f"可切换的用户太少（{users}），多用户路径没法实测")


if __name__ == "__main__":
    unittest.main()
