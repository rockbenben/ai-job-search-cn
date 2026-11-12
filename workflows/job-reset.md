# /job-reset —— 清空个人数据重新开始

你现在要把这套求职框架的一部分**清回空白状态**，让用户跑一次 `/job-setup` 从头开始。

**这条命令是破坏性的。** **用户明确确认之前，一个字节都不许删。** 下面几步**严格按顺序**走。

---

## Step 0：从参数里解析出范围

看用户跟命令一起给的输入里有没有范围关键字：

- `profile` —— **只**清个人资料（候选人资料那几个文件里的内容）
- `documents` —— **只**删他自己放进 `documents/` 的那些文件
- `all` —— 上面两样都做

输入是空的、或者里面没有认得出的范围关键字，就问一句：

> **你想重置哪一部分？**
>
> - **`profile`** —— 清空你的个人资料（候选人资料、行为特质、面试案例），
>   框架结构与写作规则保留。想从头重跑一次 `/job-setup` 就选它。
>
> - **`documents`** —— 删掉你放进 `documents/` 的所有文件（简历 PDF、领英导出、
>   学历证明、推荐信、以往投递材料）。目录结构和 `README.md` 保留。
>
> - **`all`** —— 上面两样都做。
>
> 回复 `profile`、`documents` 或 `all`。

**等他回答，回答之前不许往下走。**

---

## Step 1：把要清掉的东西一条不落地摆出来

**动手之前**，把到底会清掉什么**精确地**摆给他看。

### 范围里含 `profile` 时：

读一下这几个文件现在的状态（路径都是**活动用户的**，解析到 `users/<活动用户>/` 下——
见 `AGENTS.md`「活动用户与多用户」；下面提到的 `profile.example/` 是**共享的、进版本库的**
模板目录，不按用户分），逐个报出它是**有内容**还是**本来就空**：

- `profile/candidate.md`
- `profile/behavioral.md`
- `profile/interview-star.md`
- `profile/search-queries.md`

按这个样子摆出来：

```
## 这次会清空的个人资料：

- profile/candidate.md —— [有内容 / 本来就空]
  内容会被 `profile.example/candidate.md` 这份模板替换掉。

- profile/behavioral.md —— [有内容 / 本来就空]
  内容会被 `profile.example/behavioral.md` 这份模板替换掉。

- profile/interview-star.md —— [有内容 / 本来就空]
  内容会被 `profile.example/interview-star.md` 这份模板替换掉。

- profile/search-queries.md —— [有内容 / 本来就空]
  内容会被 `profile.example/search-queries.md` 这份模板替换掉。

以下文件不会被动（它们是框架规则，不含你的个人数据）：
  - workflows/reference/03-writing-style.md
  - workflows/reference/04-job-evaluation.md
  - workflows/reference/05-cv-templates.md
  - workflows/reference/06-outreach-templates.md
  - workflows/reference/07-interview-prep.md
```

### 同时必须列出「**没有**被清掉的个人数据」——这一段不许省

`AGENTS.md` 的个人数据枚举有 11 类，本命令的 `profile` 范围只覆盖其中 1 类。
剩下的都留在盘上，而用户会合理地以为「重置个人数据」= 清干净了。**最要紧的是
`resume/main.typ` 里内联着姓名、手机号、邮箱**，`reports/` 里的面板 HTML 则含
全部职位与评分。不说清楚，就是给了一个假的安心。

逐项检查存在与否，存在的照下面列出来（不存在的不必提）：

```
## 以下个人数据**不在本次重置范围内**，仍留在盘上：

- resume/main.typ —— **内含你的姓名、手机号、邮箱**，要清请手动改或删
- cover_letter/main.typ —— 同上
- job_scraper/seen_jobs.json —— 抓到的职位与评分（评分是按旧资料算的，
  换了资料之后这些分不再作数，建议一并清掉重跑 /job-rank）
- job_search_tracker.csv —— 投递记录
- reports/ —— 已生成的总览页（HTML 里嵌着上面这些数据的快照）
- upskill/、gmail_sync/ —— 学习计划与邮件同步状态
- templates/active-cv.md、templates/active-cover-letter.md —— 你选的模板

要连这些一起清掉，最干净的做法是删掉整个 `users/<你的用户名>/` 再跑 `/job-setup`
（或用 `/job-user` 删除该用户后重建）。
```

> **为什么不由本命令直接删这些**：`/job-reset profile` 的用途是「重填资料、重跑
> `/job-setup`」，多数时候用户并不想丢掉已经抓到的几百个职位和投递记录。范围小是
> 对的，**把范围说清楚才是必须的**——沉默地留下姓名手机号，才是这条命令最大的风险。

### 范围里含 `documents` 时：

用 Glob 把活动用户的 `documents/cv/`、`documents/linkedin/`、`documents/diplomas/`、`documents/references/`、`documents/postings/`、`documents/applications/` 里现有的文件全列出来，按这个格式摆：

> ⚠️ **六个，照着 `documents/README.md` 那张表写全** —— 与 Step 3 那条 `rm` 删的必须是同一批。
> 这里原来只列了五个，漏的是 `postings/`（他自己粘进来的职位页）。
> Step 3 底下那段警告记的是**同一课的上一次**（删的时候漏了它，已经补上），
> **而给他看的这张预览没跟** —— 于是 `postings/` 从没出现在他点头确认的
> 那张清单上，却照样被删。这条命令的整个安全设计就是「把要清掉的一条不落地
> 摆出来再要确认」；**预览少报一项，那次确认就是无效的**，
> 比 Step 3 漏删那次更糟。
> （同一课第三次：`/job-setup` 建的时候只建了一个 → Step 3 删的时候只删了五个
> → 这里预览只报五个。**枚举写在三处，就会各漏各的。**）

```
## 这次会删掉的文件：

documents/cv/
  - [文件名]，没有就写「（空）」

documents/linkedin/
  - [文件名]，没有就写「（空）」

documents/diplomas/
  - [文件名]，没有就写「（空）」

documents/references/
  - [文件名]，没有就写「（空）」

documents/postings/
  - [文件名]，没有就写「（空）」

documents/applications/
  - [子目录/文件名]，没有就写「（空）」

documents/README.md —— **不删**（那是说明文件）
```

各子目录本来就都是空的，就说「`documents/` 各子目录本来就是空的，没有要删的文件。」

⚠️ **此时跳过的只是 `documents` 这一部分的清单，不是 Step 2 的确认。**
scope 是 `all` 时，`documents` 空不代表 `profile` 也空——把整个 Step 2 跳过，
就等于**在没有任何确认的情况下清掉了用户的资料**。
只有当**本次 scope 内所有要动的东西都已经是空的**（即真的无事可做）时，
才可以直接结束并告知「没有要重置的内容」，此外一律走 Step 2。

---

## Step 2：必须拿到明确确认

给出确认提示：

> **这一步删掉的东西找不回来。**
>
> 输入 **`确认重置`** 继续，输入别的都算取消。
>
> （也接受全大写的 `RESET`——有些输入法状态下敲中文不方便。）

> **这句话原来是英文的：「This cannot be undone.」** 而它是这条命令确认提示里
> 最要紧的一句——整个仓库唯一会删数据的地方，告诉用户「回不去了」的就是它。
> `test_no_english_lines_spoken_to_the_user` 的判据里有一条「短于 26 个字符
> 不算话」，而这句去掉 `>` 和 `**` 之后是 **22 个字符**，差 4 个字躲过去了。
> 那条守卫的说明里本来就有一张「每收紧一次判据就冒出新一批」的表，这是第五行。
> （`RESET` 那个关键词留着——它是**要敲的字**不是话，理由上面写着。）

等用户回复。

- 用户输入 `确认重置` 或 `RESET`（区分大小写）：进入 Step 3。
- 输入其它任何内容：中止，并告诉他「已取消，什么都没有动。」

---

## Step 3：执行重置

### 清资料

**`profile/candidate.md`**：用 `profile.example/candidate.md` 的内容整个覆盖它（读模板，然后**逐字**写进 `profile/candidate.md`）。

**`profile/behavioral.md`**：用 `profile.example/behavioral.md` 的内容整个覆盖它（读模板，然后**逐字**写进 `profile/behavioral.md`）。

**`profile/interview-star.md`**：用 `profile.example/interview-star.md` 的内容整个覆盖它。

**`profile/search-queries.md`**：用 `profile.example/search-queries.md` 的内容整个覆盖它。

注意：`07`（面试准备框架）是一份**方法文档**（STAR 格式讲解、难题、该问面试官什么、电话/视频提醒、跟进礼仪、模拟面规程）——**里面没有任何候选人数据，`/job-reset` 不碰它**。用户真实的 STAR 案例在 `profile/interview-star.md` 里，上面那一步已经清了。

### 清 documents

每个非空的子目录，用 `rm` 把里面的文件删掉。**目录本身不要删，`documents/README.md` 也不要删。**

**路径必须写全 `users/<活动用户>/`，不要照抄裸相对路径。** 仓库根也有一个
`documents/`——那是**共享框架目录**，里面只有 `README.md` 和各子目录的 `.gitkeep`。
在仓库根跑 `rm -f documents/cv/*`，通配符匹配不到任何东西（那个目录里只有 `.gitkeep`，
而 shell 通配符默认不展开点文件），`-f` 又把「没有匹配」这件事压成静默——
于是命令**报成功、什么也没删**，用户真正的投递材料一个都还在。
（确认：`rm -f cv/*` 删不掉 `.gitkeep`。所以危险不是「误删了框架文件」，
而是**该删的没删却报了成功**——用户以为清干净了。）

> ⚠️ **六个子目录一个都不能少，照着 `documents/README.md` 那张表写全。**
> 这里原来只有五个 —— 漏的是 `postings/`（用户自己粘进来的职位页）。
> 后果正是上面那段警告的形状：**命令报成功，而那个目录一个文件都没动**。
> `/job-setup` 那一侧早就为同一件事立过规矩（「**六个都要建，逐个写出来**」，
> 起因是含糊写成「`applications/` 等子目录」害得实现只建了一个）——
> **建的那一侧学会了，删的这一侧没有。**

```bash
U="users/$(cat .active_user)"
rm -f "$U"/documents/cv/* "$U"/documents/linkedin/* \
      "$U"/documents/diplomas/* "$U"/documents/references/* \
      "$U"/documents/postings/*
rm -rf "$U"/documents/applications/*/
```

---

## Step 4：报清楚做了什么，并给下一步

清完之后，报：

```
## 重置完成

### 已清空
[逐条列出真正被改动或清空的文件/目录]

### 没动
[列出本来就是空的、或有意保留的]
```

然后**按这次清了什么**告诉他下一步做什么：

### 收尾：刷新面板（无条件）

清完之后**必须跑一次**：

```bash
python tools/export_web_data.py
```

不刷的话，总览页还显示着刚被清掉的那些岗和材料——用户以为没清干净，
或者更糟：点开一个已经不存在的岗。清空这件事尤其不能只清盘不清屏。

（面板没在跑就不用管；跑着的话它自己会在下次取数时重导，但这一步不依赖那个自愈。）

---

**如果清的是个人资料：**
> 你的个人资料现在是空的。跑 `/job-setup` 重新填。它会自动看一眼 `documents/` 里有没有
> 文件、有就问你要不要从那里读；没有就带你走导入简历或逐项问答那条路。

**如果清的是 `documents/`：**
> `documents/` 现在是空的。把你的求职材料放进去，再跑 `/job-setup` 填资料。
> 哪类文件放哪个子目录，看 `documents/README.md`。

**如果两样都清了：**
> 个人资料和 `documents/` 现在都是空的。把材料放进 `documents/`（也可以跳过，
> 走导入简历或逐项问答那条路），然后跑 `/job-setup`。
