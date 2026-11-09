# 工作流索引

21 条命令的正本。`tools/build_dashboard.py` 的 `parse_commands()` 解析这张表，
面板上那份帮助就是它；各 AI 工具的命令入口（各族技能壳与权限片段）由
`tools/gen_entries.py` 从这张表派生 —— 改完这里就跑一次它，别去手改那些生成物
（它的 `--check` 会红）。
改这里，两边一起变。

表里提到的 `profile/…`、`resume/main.typ` 这类个人数据路径，按 `AGENTS.md`
「活动用户与多用户」解析为 `users/<活动用户>/` 下的对应路径，不是仓库根相对路径。

## 工作流索引

第三列同时是**面板上那份帮助的正文**（`parse_commands` 解析这张表，`CommandBook`
渲染）。所以：举例只写**真实支持**的敲法，用 ` · ` 分隔，第一个是标准形式；
说明用内地求职者自己会说的话，别把「四维」「台账」这类内部词写进来。

**第四列「不给参数时」** 回答的是敲裸命令之前最想知道的那件事。写它的时候：

- **不要复述第一列**。「审你那份主简历，只报问题不改数字」对着说明
  「审一遍你的主简历，只报问题、不改你的数字」——一个字没多给。
  重复即噪音，`test_command_help_has_two_layers` 会按相似度拦下来。
- 该写的是**取值、范围、边界**：默认取哪个数、扫哪些文件、跑到什么时候停、
  写不写盘。例：「不设目标个数，跑到挖不动为止（连续两轮抓不到新的、或满 20 轮就停）」。
- 没有参数可给的命令（`/job-expand`）也要写——写它**动了什么**
  （「扫 `documents/` 下你放的全部文件」），那同样是用户想先知道的。
  > 这一条原来举的是 `/job-dashboard`，而它**有两个参数**
  > （`serve.py --help`：`--user` 服务另一个人的数据、`--port` 换端口，
  > `job-dashboard.md`「参数」也写着）。举例是规则的一部分 ——
  > 读规则的人会把这个假事实一起学走，而下面那张表里它的第三列
  > 也正因此只写了裸命令。2026-09-01 一并改。

| 任务 | 正文 | 怎么敲（举例） | 不给参数时 |
|---|---|--- | --- |
| 第一次用：填你的经历、期望薪资、硬性条件 | `workflows/job-setup.md` | `/job-setup` · `/job-setup --section search`（只补搜索词） · 「我要开始用」 | 从头问一遍，分四轮；已经填过的会先读出来只补缺的 |
| 抓新岗并自动评分：抓完直接排出可以投的，不停在「待评」 | `workflows/job-scrape.md` | `/job-scrape` · `/job-scrape 数据科学`（只抓这个方向） · `/job-scrape broad`（连上轮没产出的词也重抓一遍） · `/job-scrape --no-rank`（只抓不评） · `/job-scrape --no-browser`（这一趟不碰要你登录的三家，只抓猎聘） · `/job-scrape health`（只体检各渠道通不通，不抓岗） · 「找新职位」 | 全部方向都抓一轮（按实测产出剪掉挖空的词），抓完自动评分 |
| 给抓到还没评的岗批量打分，排出可以投的 | `workflows/job-rank.md` | `/job-rank` · `/job-rank 数据科学`（只评这个方向） · `/job-rank --all`（改完资料重评一遍） · `/job-rank --skip <职位链接>`（把这个标成不投） · `/job-rank --top 20`（可以投的那一节列 20 个，默认 5） · `/job-rank --fetch 30`（这一轮取详情深评 30 个；不给的话按通道算 ——免登录接口那条 12，走浏览器时更多） | 把还没评的**全部**评完，分批循环直到队列排空 |
| 一条命令跑完：抓岗 → 评分 → 出材料，一直跑到挖不动为止 | `workflows/job-auto.md` | `/job-auto` · `/job-auto --target 20`（攒够 20 个就收工） · `/job-auto --rank-only`（只评分不出材料） · `/job-auto --no-scrape`（不抓新岗，只处理手上的） · `/job-auto --no-browser`（这一轮不碰要你登录的网站，只抓猎聘） | 不设目标个数，跑到挖不动为止（连续两轮抓不到新的、或满 20 轮就停） |
| 深评一个岗：核对硬性条件、逐项打分、出打招呼话术 | `workflows/job-apply.md` | `/job-apply <职位链接>` · `/job-apply <整段职位描述>`（**猎头/HR 主动来找你时就走这条**：把他发来的那段粘进来） · `/job-apply --top 20`（只备分最高的 20 个） · `/job-apply 全部`（除了不投的都备好料） · `/job-apply 可以考虑`（只补这一档） · `/job-apply --stale`（重跑那些不该再信的判断：翻了档的，以及当时没读到职位描述、现在读得到的） · 「投这个岗」 | 「可以投」这一档全部出深评 + 开场白，不限量 |
| 特殊情况给某个岗出定制简历（平时直接发主简历就行） | `workflows/job-cv.md` | `/job-cv <公司>` · `/job-cv <职位链接>` · 「给这个岗定制简历」 | 先说清哪三种情况才需要定制，再列出有材料没投的岗让你挑 |
| 审一遍你的主简历，只报问题、不改你的数字 | `workflows/job-resume.md` | `/job-resume` · 「看看我简历」 | 审主简历 `resume/main.typ`，不是某次投递的定制版；还会对一遍你在招聘网站上那份在线简历（HR 主动搜的是它）。只出报告，一个字不改 |
| 把在线简历刷一遍，让 HR 搜得到你（一天一次） | `workflows/job-refresh.md` | `/job-refresh` · 「刷一下简历」 | 网页刷得了的那几家全刷一遍；今天刷过的会跳过，网页没有刷新按钮的（BOSS、前程无忧）如实告诉你要开 APP |
| 投完记一笔：约面了 / 挂了 / 没下文 | `workflows/job-outcome.md` | `/job-outcome <公司>` · `/job-outcome followup`（该催哪几个） | 列出还在跑的投递，问你要改哪一个 |
| 拿到 offer：谈薪、多个 offer 比较、背调红线 | `workflows/job-offer.md` | `/job-offer <公司>` · `/job-offer 比较` · 「拿到offer了」 | 列出已经到 offer 状态的岗；一个都没有会直接说 |
| 面试准备：这家会问什么、你怎么答 | `workflows/job-interview.md` | `/job-interview <公司>` | 列出约了面试、拿到 offer、或刚投出去的岗，问你准备哪个 |
| 从你的文档和公开主页里，挖还没写进资料的经历 | `workflows/job-expand.md` | `/job-expand` | 扫 `documents/` 下的简历、领英导出、学历证明、推荐信这四类，加上资料里的公开主页链接（`postings/` 里的职位描述不扫——那是别人写的，不是你的经历）；找到的先列出来给你确认，不直接写进资料 |
| 打开这一页（在本机起服务，数据不出这台机器） | `workflows/job-dashboard.md` | `/job-dashboard` · `/job-dashboard <名字>`（看另一个人的数据，不改当前是谁在用） · `/job-dashboard --port 8080`（端口被占时换一个） | 服务当前用户的数据，端口 29029，起完自动打开浏览器 |
| 投后分析：哪类岗回复率高、卡在哪一环 | `workflows/job-html-report.md` | `/job-html-report` · `/job-html-report ~/Desktop/report.html` · `/job-html-report --open`（出完直接打开） | 出到 `reports/application-dashboard.html` |
| 从 Gmail 认出面试邀请和拒信：证据确凿的直接回写（可撤销），含糊的列出来等你确认 | `workflows/job-gmail-sync.md` | `/job-gmail-sync` · `/job-gmail-sync <公司>`（只对一家） | 按上次同步到哪儿接着往后扫（第一次跑有默认回溯窗口） |
| 把岗位和投递记录推到 Notion 看板 | `workflows/job-notion-sync.md` | `/job-notion-sync` · `/job-notion-sync --all`（连旧的一起推） · `/job-notion-sync --rebuild`（看板重建一遍） · `/job-notion-sync --min-score 70`（改掉那条分数线） | 推 60 分以上的岗，加上全部投递记录（60 是分数线，不等于「值得投」那一档）|
| 算能力差距：你评过的岗都在要什么，你缺哪几项 | `workflows/job-upskill.md` | `/job-upskill` · `/job-upskill --applied`（只算投过的那批） · `/job-upskill <职位链接>`（只看这一个岗） | 汇总模式：拿**所有评过分**的岗一起算（新用户也有语料）；`--applied` 换成只算真投出去的那批；给一个岗的链接就只看那一个 |
| 教它去一个新的招聘网站搜岗 | `workflows/job-add-portal.md` | `/job-add-portal` · `/job-add-portal https://www.lagou.com` · `/job-add-portal --list`（看已装的） | 问你要接哪个招聘网站 |
| 换一套简历 / 求职信模板 | `workflows/job-add-template.md` | `/job-add-template` · `/job-add-template --list`（看有哪些模板） · `/job-add-template --use <模板名>` | 先列出已装的模板和当前用哪套，再问你是换一套还是加一套新的 |
| 清空个人数据重新开始 | `workflows/job-reset.md` | `/job-reset` · `/job-reset profile`（只清资料，留投递记录） | 先问你要清哪一部分，不直接动手 |
| 看现在是谁在用、切换 / 新建 / 删除用户 | `workflows/job-user.md` | `/job-user` · `/job-user <名字>`（切过去） · `/job-user --new <名字>` · `/job-user --remove <名字>`（删掉这个人的全部数据） | 列出所有用户，标出现在是谁在用 |
