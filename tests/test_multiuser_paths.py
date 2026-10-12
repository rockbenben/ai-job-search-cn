"""多用户路径口径的文档级检查。

`AGENTS.md` 的「活动用户与多用户」一节是所有命令/技能路径解析的单一来源：任何写个人
数据的目录只要没被它枚举，对应命令就会把数据落在仓库根，多人共用一份 clone 时互相
可见并覆盖。这里把「枚举完整」变成 CI 能抓到的属性。

风格参照 test_html_report_command.py：只断言真实仓库文件的属性。
"""

import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_MD = REPO_ROOT / "AGENTS.md"
GMAIL_SYNC_CMD = REPO_ROOT / "workflows" / "job-gmail-sync.md"

sys.path.insert(0, str(REPO_ROOT / "tools"))
import _entries  # noqa: E402  两族目录名的正本在派生器里，这里不另抄一份


def resolution_section() -> str:
    """AGENTS.md 里「## 活动用户与多用户」一节的正文（到下一个 ## 为止）。"""
    text = AGENTS_MD.read_text(encoding="utf-8")
    m = re.search(r"^## 活动用户与多用户\s*$(.*?)(?=^## )", text, re.M | re.S)
    assert m, "AGENTS.md 缺少「## 活动用户与多用户」一节"
    return m.group(1)


class ResolutionEnumerationTests(unittest.TestCase):
    def test_section_exists(self):
        self.assertTrue(resolution_section().strip())

    def test_enumerates_every_personal_data_dir(self):
        """写个人数据的路径必须全部在解析枚举里，否则会落到仓库根、跨用户泄漏。"""
        section = resolution_section()
        for path in ("profile/", "job_scraper/", "job_search_tracker.csv",
                     "documents/", "resume/main.typ", "reports/",
                     "gmail_sync/", "upskill/", "cover_letter/main.typ",
                     "templates/active-cv.md", "templates/active-cover-letter.md"):
            with self.subTest(path=path):
                self.assertIn(path, section)


class CommandPathIdiomTests(unittest.TestCase):
    """任何提到个人数据路径的命令/技能都必须点明「活动用户」口径。

    否则读者（和执行的模型）会把路径当成仓库根的相对路径——这正是 gmail_sync
    落到根目录的成因。
    """

    # 个人数据路径的字面标记（框架共享文件不在此列：template.typ、documents/README.md）
    PERSONAL_TOKENS = (
        "profile/candidate", "profile/behavioral", "profile/interview-star",
        "profile/search-queries", "job_scraper/seen_jobs", "job_scraper/notion_sync",
        "job_search_tracker.csv", "documents/applications", "resume/main.typ",
        "gmail_sync/state.json", "templates/active-cv", "templates/active-cover-letter",
    )

    def iter_docs(self):
        """两族都扫。`.agents/` 才是非 Claude 工具真正读进去的那一族，
        手写路由壳 `job-application-assistant` 不走生成器（CLAUDE.md：
        「改了它必须两族同步 —— 没人替你兜」），只扫 `.claude/` 等于把它放掉。

        `.claude/commands/` 2026-10-09 从这里删掉：命令 stub 早已整体删除，
        仓库里其它地方提到它都是「必须为空」的反向引用（lint_skills、
        docs/tool-entries.md）。扫一个被要求为空的目录，等于把守卫钉在一个
        刻意不存在的位置上。
        """
        roots = [REPO_ROOT / "workflows"]
        roots += [REPO_ROOT / fam / "skills" for fam in _entries.SHELL_FAMILIES]
        for d in roots:
            for path in sorted(d.rglob("*.md")):
                yield path

    def test_every_doc_citing_personal_paths_names_active_user(self):
        for path in self.iter_docs():
            text = path.read_text(encoding="utf-8")
            if not any(tok in text for tok in self.PERSONAL_TOKENS):
                continue
            with self.subTest(doc=str(path.relative_to(REPO_ROOT))):
                cited = sorted(t for t in self.PERSONAL_TOKENS if t in text)
                # assertIn 会把整份文件打进失败信息，这里只报路径清单
                self.assertTrue(
                    "活动用户" in text,
                    f"引用了个人数据路径 {cited} 却没写明是活动用户目录下的路径，"
                    "会被当成仓库根相对路径",
                )


class GmailSyncCommandTests(unittest.TestCase):
    def test_state_path_scoped_to_active_user(self):
        """/job-gmail-sync 的状态文件含邮件主题与 message id，必须按活动用户隔离。"""
        text = GMAIL_SYNC_CMD.read_text(encoding="utf-8")
        self.assertIn("gmail_sync/state.json", text)
        self.assertIn("活动用户", text)


if __name__ == "__main__":
    unittest.main()
