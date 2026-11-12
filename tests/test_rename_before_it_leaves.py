# -*- coding: utf-8 -*-
"""附件改名这条规矩，跟「有没有文件要交出去」走，不跟渠道走。

`resume.pdf` 是落盘用的名字。HR 一天下几十个附件，收件箱里躺着一堆同名文件；
不少网申系统还直接拿文件名做展示。国内的写法是 `<姓名>-<岗位>-简历.pdf`。

**规则原来只挂在渠道 2（邮件）底下** —— 而实测活动用户 2026-08-22：

    236 份产出里提到改名的        8 份（3%）
    归档里 17 份 PDF，叫 resume.pdf 的  15 份

他 85 个投递**全是平台投递，一封邮件都没有** —— 规则在，只是长在了一条他从不走
的渠道上。而网申表单要传附件、聊天框里也能发文件，对面看到的就是那个名字。

判据改成「这一次有没有文件要交出去」。**没有就删掉那一行** —— 留一条用不上的
提醒，下次真用得上时他也不会看了。
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TPL = (ROOT / "workflows" / "reference"
       / "06-outreach-templates.md").read_text(encoding="utf-8")


def _general() -> str:
    """「通用要求」那一节。"""
    i = TPL.index("## 通用要求")
    return TPL[i:TPL.index("\n## ", i + 4)]


class TheRuleIsChannelAgnostic(unittest.TestCase):
    def test_it_lives_in_the_general_requirements(self):
        """挂在某一个渠道底下，就只有走那条渠道的人看得到。"""
        self.assertRegex(_general(), r"有文件要离开这台机器",
                         "改名那条还只挂在某个渠道底下")

    def test_the_trigger_is_the_file_not_the_channel(self):
        seg = _general()
        for w in ("网申", "聊天"):
            with self.subTest(w=w):
                self.assertIn(w, seg, f"没把「{w}」这种传文件的场景算进来")

    def test_it_still_forbids_putting_it_in_the_message(self):
        """这句是给用户的操作备注 —— 写进话术小节就会被整段粘给对方。"""
        self.assertRegex(_general(), r"只许写在\s*`## 自检`\s*里",
                         "没挡住把操作备注粘给对方")

    def test_the_measurement_is_recorded(self):
        """确认改名规范写明了自检要求。"""
        self.assertIn("自检", _general())


class TheSelfCheckLineAdaptsToTheCase(unittest.TestCase):
    def test_the_line_no_longer_says_email_only(self):
        i = TPL.index("## 自检（不属于要发出去的内容")
        seg = TPL[i:i + 900]
        self.assertNotIn("发邮件前把附件改名", seg, "自检那一行还写着「发邮件前」")
        self.assertIn("有文件要交出去时", seg, "自检那一行没改成按文件判")

    def test_it_says_to_drop_the_line_when_unused(self):
        """一条用不上的提醒留在那儿，下次真用得上时他也不会看了。"""
        i = TPL.index("## 自检（不属于要发出去的内容")
        self.assertRegex(TPL[i:i + 900], r"没有文件要交出去就删掉这一行",
                         "没说清用不上时要删掉")

    def test_the_target_name_shape_is_unchanged(self):
        """`<姓名>-<岗位>-简历.pdf` 是国内的写法，别在改判据时顺手改掉它。"""
        self.assertIn("<姓名>-<岗位>-简历.pdf", TPL)


if __name__ == "__main__":
    unittest.main()
