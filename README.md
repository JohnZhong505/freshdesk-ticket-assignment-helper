# Freshdesk Ticket 分配助手

中文 | [English](./README.en.md)

这个仓库提供两个可独立安装的 Codex skill，面向 Freshdesk 的轻量统计与只读检查场景。

## Skill 列表

| Skill | 状态 | 用途 |
| --- | --- | --- |
| `freshdesk-needs-follow-up-ticket-numbers` | 已完成 | 轻量只读统计当前需要跟进的 Ticket，适合班次交接、值班快照、临时 staffing 判断 |
| `freshdesk-readonly-ticket-inspector` | 可用（持续优化） | 只读识别未分配的新 Ticket，按导向集中输出分流建议，最终由人工复核和执行 |

## 当前推荐使用

当前稳定可用的是 `freshdesk-needs-follow-up-ticket-numbers`。

- 最新版本：`v1.7`
- 更新日期：`2026-07-15`
- 仓库地址：[JohnZhong505/freshdesk-ticket-assignment-helper](https://github.com/JohnZhong505/freshdesk-ticket-assignment-helper)

`freshdesk-readonly-ticket-inspector` 已可用于日常新 Ticket 初步分流，并会继续根据人工复核结果迭代规则。两个 skill 相互独立：readonly skill 不统计“需跟进 Ticket”数量，也不会影响已稳定运行的轻量统计 skill。

## 如何安装

如果是第一次使用 Codex，直接在对话里发送下面这段话即可：

```text
帮我安装这个 skill：GitHub: https://github.com/JohnZhong505/freshdesk-ticket-assignment-helper
Skill path: skills/freshdesk-needs-follow-up-ticket-numbers
```

如需安装另一个 skill，可将 `Skill path` 改为：

- `skills/freshdesk-needs-follow-up-ticket-numbers`
- `skills/freshdesk-readonly-ticket-inspector`

本地脚本安装方式：

```bash
./install-skill.sh --skill freshdesk-needs-follow-up-ticket-numbers
./install-skill.sh --skill freshdesk-readonly-ticket-inspector
```

## 运行前需要准备

- `FRESHDESK_DOMAIN`
- `FRESHDESK_API_KEY`
- Python 3
- 可访问 Freshdesk API 的网络环境

Freshdesk API Key 官方说明：
[How To Find Your API Key](https://support.freshdesk.com/support/solutions/articles/215517-how-to-find-your-api-key)

## 当前输出口径

- `Need Follow Up` = `New + Customer Responded`
- `Customer Responded` = 客户最新回复后，Agent 还未再次公开回复；5 分钟内的可疑候选会核对最新公开邮件的真实发件人
- `New` = 客户新建 Ticket，尚无 Agent 公开回复
- `FR overdue` = 首响超时
- `Resolution overdue` = 解决时限超时

默认表格列顺序：

1. `Need Follow Up`
2. `Customer Responded`
3. `New`
4. `FR overdue`
5. `Resolution overdue`

## Readonly skill：新 Ticket 只读分流

`freshdesk-readonly-ticket-inspector` 用于早晨检查 Freshdesk 未分配的新 Ticket，先给出分流建议，再由人工确认并执行操作。它只读取数据，不会自动修改 Group、Agent、状态、标签或 Ticket 内容。

默认筛选口径：

| 筛选项 | 口径 |
| --- | --- |
| Agent | `Unassigned` |
| Group | `Technical Service`、Freshdesk 界面中的 `Unassigned`、`MX Support` |
| Status | `All unresolved`，即只包含 `Open` 和 `Pending`，排除 `Resolved` 和 `Closed` |
| Spam | 排除已经标记为 Spam 的 Ticket |
| Tags | 跳过带有 `Escalation` 或 `RMA` 标签的 Ticket，保留给人工完整审核 |

判断时主要读取 `subject`、客户首封邮件 `description_text`、后续公开客户会话和附件元数据。自动回复只作为上下文，不作为主要分流依据；初筛阶段不下载附件。只有出现明确的人名问候、`Re:` 标题或延续旧沟通的措辞时，才会限量检查同一 requester 的近期 Ticket 元数据，辅助判断是否需要 Merge。

输出按建议导向分别集中成表格：`CS`、`Sales`、`Technical Service`、`Technical Support`、`Spam`、`Merge` 和 `Manual Review`。小批量、电商渠道或运营报价类需求先归为 `CS`，由 CS 再决定是否转 Shopify。

## 内置业务别名

- `技术客服` / `技术客服组` / `技术客服的数据` => `Technical Service`
- `CS客服` / `CS客服组` / `CS客服的数据` => `Customer Service` + `Amazon`
- `深圳团队` => `Technical Service` + `Technical Support` + `Customer Service` + `Amazon`
- `墨西哥团队` => `MX Support`

## 主要优化点

| 优化点 | 详情 |
| --- | --- |
| 扫描范围 | 只扫描指定 group，不再全量扫所有 agent |
| 组选择流程 | 先列出 group，再明确选择后执行 |
| 停用账号 | 不将 deactivated 的 agent 作为有效扫描对象 |
| 小 cache | 增加本地缓存，减少重复请求、提升重复运行速度 |
| cache 自动清理 | 默认保留最近 30 天出现的条目，兼容旧 cache，并可通过 `--cache-retention-days` 调整 |
| cache 可视化 | 默认表格输出 cache 命中率和命中数量，例如 `90% (220/250)` |
| conversations 扫描 | 默认不全量扫描 conversations，仅在必要时定向复核 |
| Customer Responded 误报 | 仅复核 5 分钟内的可疑候选；若最新公开邮件来自 `support@gl-inet.com`、`support@glinet.biz` 或两个内部域名下的 `cs*` 邮箱，则排除 |
| 默认输出 | 默认输出适合人阅读的表格，并直接在聊天中展示 |
| 表格精简 | 仅展示 Group Name 和每个 Agent 的关键数据 |
| 快速映射 | 支持“技术客服”“CS客服”“深圳团队”“墨西哥团队”等业务别名直跑 |
| README 文档 | 提供中文主文档与英文跳转页，便于协作与交接 |
| First Response Due 误报 | 主动外发 ticket 不再误计入真正需要处理的 `FR overdue` |
| Agent 名称显示 | 尽量显示真实姓名，避免只显示 `Agent <id>` |
| 连接稳定性 | 补充瞬时断连重试，覆盖 `Remote end closed connection without response` 等场景 |
| Rate limit 缓冲 | 默认加入轻量请求节流，减少首次大批量运行时被 Freshdesk 直接掐连接的概率 |
| 运行稳定性 | 扩展 SSL / EOF / IncompleteRead / 5xx 重试，cache 改为原子写并增加中途 checkpoint |

### Readonly skill 优化点总结

| 优化点 | 详情 |
| --- | --- |
| 精确复刻视图 | 按 3 个 Group 条件和 2 个未解决状态执行 Freshdesk Search API 查询，再在本地去重，不逐个轮询整个 Ticket 池 |
| 人工审核保护 | 在读取 conversations 前跳过 `Escalation`、`RMA`，同时排除 Resolved、Closed 和已标记 Spam 的 Ticket |
| 有效识别文本 | 组合 subject、客户首封邮件和公开客户会话；弱化系统自动回复，避免依赖通常为空的人工 description 字段 |
| 附件最小读取 | 默认只读取附件名称、类型和大小，不下载附件；信息不足时倾向保留在 Technical Service 继续排查 |
| Merge 窄范围检查 | 仅在存在人名问候、`Re:` 或延续沟通信号时，限量检查近期 Ticket 标题和元数据 |
| 分流规则校准 | 已纳入功能建议、认证咨询、小批量报价、信息不足技术问题和营销 Spam 等真实案例反馈 |
| 分组输出 | 按 CS、Sales、Technical Service、Technical Support、Spam、Merge、Manual Review 分别输出表格，便于批量复核 |
| 只读安全 | 默认仅调用 Freshdesk `GET` 接口，不自动分配、改 Group、回复或更新 Ticket |

## 适合的使用场景

- 快速看各 Agent 当前待处理 workload
- 班次交接、值班快照、临时 staffing 判断
- Hermes / Codex / 定时任务式的轻量运行
- 早晨集中检查未分配的新 Ticket，并获得按导向分组的分流建议
- 在人工执行改派前，快速识别疑似 Spam、Merge、CS、Sales 或技术支持升级项

## 下游同步提醒

本仓库是 Need Follow Up 核心脚本的上游。共享脚本或 Skill 版本更新后，Workload 项目不会自动继承；AI / Codex 发布前请阅读并完成：[Follow Up 下游同步提醒](docs/downstream-workload-sync.md)。

## 版本与更新记录

| 版本 | 更新日期 | 更新内容 |
| --- | --- | --- |
| v1.7 | 2026-07-15 | 增加 5 分钟 Customer Responded 发件人复核；分页选择最新公开会话；内部邮箱结果进入 cache；增加复核统计 |
| v1.6 | 2026-07-15 | 增加 `last_seen_at` 与默认 30 天 cache 保留期；兼容旧 cache；JSON 输出保留期和清理数量；保留原子写入与中途 checkpoint |
| v1.5 | 2026-07-10 | 修复 Python 3.9 UTC 兼容问题；扩展瞬时错误重试；cache 原子写入与中途 checkpoint；默认输出 cache 命中率 |
| v1.4 | 2026-07-02 | 增加瞬时断连重试；默认加入轻量请求节流；提升 Hermes 大批量运行稳定性 |
| v1.3 | 2026-07-01 | 优化 agent 名称显示，尽量展示真实姓名而不是纯 ID |
| v1.2 | 2026-07-01 | 修正主动外发 ticket 的 `FR overdue` 误报 |
| v1.1 | 2026-07-01 | 增加“技术客服”“CS客服”“深圳团队”“墨西哥团队”等业务别名 |
| v1.0 | 2026-06-30 | 完成 group 选择、默认表格输出、基础统计口径与本地 cache |

## 快速使用

先列出 group：

```bash
python3 skills/freshdesk-needs-follow-up-ticket-numbers/scripts/freshdesk_needs_follow_up_ticket_numbers.py --list-groups
```

跑技术客服：

```bash
python3 skills/freshdesk-needs-follow-up-ticket-numbers/scripts/freshdesk_needs_follow_up_ticket_numbers.py \
  --group-name "技术客服组"
```

跑深圳团队：

```bash
python3 skills/freshdesk-needs-follow-up-ticket-numbers/scripts/freshdesk_needs_follow_up_ticket_numbers.py \
  --group-name "深圳团队"
```

输出 JSON 明细：

```bash
python3 skills/freshdesk-needs-follow-up-ticket-numbers/scripts/freshdesk_needs_follow_up_ticket_numbers.py \
  --group-name "Technical Service" \
  --format json \
  --pretty
```

运行未分配新 Ticket 只读分流：

```bash
python3 skills/freshdesk-readonly-ticket-inspector/scripts/freshdesk_readonly_ticket_inspector.py \
  --triage-unassigned-view \
  --limit 30 \
  --pretty
```

## 安全边界

- 默认只使用 Freshdesk `GET` 接口
- 不做回复、分配、备注、联系人修改或批量写入
- readonly skill 的分流结果是辅助建议，最终判断和操作仍由人工完成
- 不应将 API key、webhook 或真实客户数据提交进仓库
