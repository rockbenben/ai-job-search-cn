# 职位搜索查询策略

<!-- SETUP: 这些查询由 /job-setup --section search 根据你的技能、目标岗位和城市生成 -->
<!-- 落盘到 gitignore 的 profile/search-queries.md；本文件是不含真实数据的结构骨架 -->

## 已安装的 portal CLI（`/job-scrape` 的主路径）

`/job-scrape` 会自动发现 `.agents/skills/*/SKILL.md` 下的每个 portal 技能并优先调用其 CLI。
用 `/job-add-portal` 新增的技能会被同样自动纳入，不需要在下面补 `site:` 行。

下面的 `site:` 查询模板是 **网络搜索兜底路径** —— 用于没有 CLI 的站点、公司官网招聘页，
或 CLI 失败时。

## 搜索站点（含各家覆盖方式）

各渠道**覆盖方式不同**，`/job-scrape` 按渠道分级处理：

- **猎聘** — **CLI**（`liepin-search` 技能）。有可用的免登录 JSON API，覆盖大陆主要城市。
- **BOSS 直聘** / **智联招聘** / **前程无忧** — **走浏览器，够不着才退 `site:` 兜底**。
  这三家**没有可用的免登录 API**（具体实测见 `workflows/reference/cdp-portals.md`），
  所以**不建 CLI**（假 CLI 只会静默返回 0 结果）。浏览器按**三层顺位**取，
  **不要搞反**（完整说明见 `AGENTS.md`「取数渠道的顺位」）：

  | 顺位 | 用什么 |
  |---|---|
  | 1 | **你所在 AI 工具自带的浏览器能力** —— 驱动的就是你自己那个已登录的 Chrome，登录态天然带着，也不用装任何第三方东西 |
  | 2 | **`web-access` skill 的 CDP 代理** —— 只在没有第 1 层、或它够不着时才用；第三方全局技能，本项目不附带 |
  | 3 | **`site:` 域名限定搜索** —— 前两层都没有时的兜底，字段少得多，必须在覆盖报告里如实说明 |
  - **BOSS / 智联需要登录态**——登录后裸搜索页就已按站内「求职期望」过滤好岗位与城市。
  - **前程无忧未登录也能读**，但没有登录就没有个性化，必须自己带关键词。
- **目标公司官网招聘页 / 微信公众号招聘推文** — **`site:` 兜底**（网络搜索）。

## 目标城市

<!-- SETUP: 填入你实际考虑的城市，CLI 的 -l 参数直接用中文城市名 -->

- 主要：[YOUR_PRIMARY_CITY]
- 可接受：[YOUR_ACCEPTABLE_CITY_1]、[YOUR_ACCEPTABLE_CITY_2]
- 明确排除：[YOUR_EXCLUDED_CITY]

通勤判断按**通勤时长**而非直线距离：[YOUR_MAX_COMMUTE_MINUTES] 分钟以内可接受。
据 portal 的 location 字段精确到区判断。

## 查询分类

<!-- [CALIBRATION_LOG_PLACEHOLDER]：每轮校准后在此追加一行日志——日期、跑了多少组
     关键词/职位/详评，以及据此调整的优先级顺序和理由。不要在模板里预填具体数字。 -->

### 优先级 1：[PRIORITY_1_CATEGORY_NAME]（[PRIORITY_1_RATIONALE]）

```
-q "[QUERY_1]" -l "[YOUR_PRIMARY_CITY]"
-q "[QUERY_2]" -l "[YOUR_PRIMARY_CITY]"
```

### 优先级 2：[PRIORITY_2_CATEGORY_NAME]（[PRIORITY_2_RATIONALE]）

```
-q "[QUERY_3]" -l "[YOUR_PRIMARY_CITY]"
-q "[QUERY_4]" -l "[YOUR_PRIMARY_CITY]"
```

### 优先级 3：[PRIORITY_3_CATEGORY_NAME]（[PRIORITY_3_RATIONALE]）

```
-q "[QUERY_5]" -l "[YOUR_PRIMARY_CITY]"
-q "[QUERY_6]" -l "[YOUR_PRIMARY_CITY]"
```

### 优先级 4：兜底

```
-q "[FALLBACK_QUERY_1]" -l "[YOUR_PRIMARY_CITY]"
-q "[FALLBACK_QUERY_2]" -l "[YOUR_PRIMARY_CITY]"
```

### 实测低效、可跳过的关键词

- [LOW_YIELD_KEYWORD_1] —— [REASON_1]
- [LOW_YIELD_KEYWORD_2] —— [REASON_2]

### 需要主动规避的方向

<!-- 对应 profile/candidate.md 的「明确的能力边界」一节，逐条列出规避关键词。
     命中后应直接降级，不要勉强投递。 -->

- [AVOID_KEYWORD_OR_PHRASE_1]
- [AVOID_KEYWORD_OR_PHRASE_2]
- [AVOID_KEYWORD_OR_PHRASE_3]

## 时间过滤

只看 **14 天内更新** 的职位：CLI 传 `--jobage 14`。

注意 portal 的「更新时间」不等于「发布时间」——一个长期挂着的岗位可以有很新的更新
时间。判断职位是否真实在招，看 `04-job-evaluation.md` 的「职位真伪信号」一节，不要只看日期。

## 按焦点调整

用户指定焦点时（如 `/job-scrape <焦点词>`），从匹配的分类里选查询，并额外生成 2-3 条针对该
焦点的查询。
