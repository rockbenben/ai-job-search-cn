"""Candidate salary inputs shared by scoring and audit tools."""
import re

def annual_floor(user, root):
    """`candidate.md` 薪资小节里的「可接受底线」年包（万）。读不出返回 None。

    自由文本，只认最稳的写法（「可接受底线」那一行里的「年包 N 万」），
    读不出就如实说没查 —— 同 `_candidate_years`。

    ## 这个数和预筛传给 `prescreen.py --annual-floor` 的**有意不同**，别去统一

    资料里常有两个数：常规的「可接受底线」，加一句「方向极对的岗可以降到 X 谈」。

    - **这里读常规那个（高的）。** 用途是**打分**：`04-job-evaluation.md` 的
      「有月薪、但没写几薪」拿它当基准分档。弹性是谈判姿态，不是打分输入。
    - **预筛传最宽那个（低的）。** 用途是**淘汰**，而且是四条规则里唯一能结案
      的（不可逆）；预筛只有标题和薪资串，判不了方向极不极对，用常规底线误杀的
      恰好是弹性条款要保护的那批（判据在 `job-auto.md` 的参数出处表）。

    两个用途的错误代价方向相反：打分错了还能重评，结案错了那个岗就没了。
    所以**看到两处数字不一样不是 bug**，把它们改成同一个才是。
    """
    if not user:
        return None
    p = root / "users" / user / "profile" / "candidate.md"
    if not p.is_file():
        return None
    for line in p.read_text(encoding="utf-8").splitlines():
        if "可接受底线" not in line:
            continue
        m = re.search(r"年包\s*[*]*\s*([\d.]+)\s*万", line)
        if m:
            return float(m.group(1))
    return None


def annual_expect(user, root):
    """`candidate.md` 薪资小节里的「期望区间」年包（万），返回 `(下沿, 上沿)`。

    读不出返回 None —— 同 `_annual_floor` / `_candidate_years`：**「没查」和
    「查过没有」是两件事**，读不出就如实说没查，不拿一个默认值顶上。

    只认最稳的写法（「期望区间」那一行里的「年包…N-M 万」）。这个数是
    `04-job-evaluation.md`「打分口径：比的是够不够」那张表的两个上档边界，
    和 `_annual_floor()` 的底线一起，把薪资维的取值锁死成四个数。
    """
    if not user:
        return None
    p = root / "users" / user / "profile" / "candidate.md"
    if not p.is_file():
        return None
    for line in p.read_text(encoding="utf-8").splitlines():
        if "期望区间" not in line:
            continue
        m = re.search(r"年包[^\d]{0,4}([\d.]+)\s*-\s*([\d.]+)\s*万", line)
        if m:
            lo, hi = float(m.group(1)), float(m.group(2))
            return (min(lo, hi), max(lo, hi))
    return None

