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

- 轻量统计 skill 最新版本：`v1.7`（2026-07-15）
- readonly skill 当前阶段：`当前版`（2026-07-16）
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

输出按建议导向分别集中成表格：`CS`、`Sales`、`Technical Service`、`Technical Support`、`Spam`、`Merge` 和 `Manual Review`。所有 Ticket ID 都保留数字作为显示文本，并链接到对应 Freshdesk Ticket；Merge 建议中的新旧 ID 都可直接点击。

当前明确归入 `Technical Service` 的场景还包括：Simpoyo/SIM 套餐问题、注册与登录、常规云平台后台操作，以及变砖、无法上电、疑似硬件损坏等硬件故障。小批量、电商渠道或运营报价类需求先归为 `CS`，由 CS 再决定是否转 Shopify。

## 内置业务别名

- `技术客服` / `技术客服组` / `技术客服的数据` => `Technical Service`
- `CS客服` / `CS客服组` / `CS客服的数据` => `Customer Service` + `Amazon`
- `深圳团队` => `Technical Service` + `Technical Support` + `Customer Service` + `Amazon`
- `墨西哥团队` => `MX Support`

## 主要优化点

| 优化点 | 详情 |
| --- | --- |
| 范围与分组 | 只扫描选定 group；先列出 group 再执行，并支持“技术客服”“CS客服”“深圳团队”“墨西哥团队”等业务别名 |
| Agent 信息 | 排除 deactivated Agent，并尽量显示真实姓名而不是纯 ID |
| Cache 生命周期 | 本地缓存减少重复请求；默认保留最近 30 天、兼容旧格式，并展示命中率和清理数量 |
| 误报控制 | conversations 仅在必要时定向复核；排除内部发件人造成的 `Customer Responded` 误报和主动外发造成的 `FR overdue` 误报 |
| 输出与交接 | 默认输出精简表格；提供中英文入口和下游同步提醒 |
| 运行稳定性 | 统一处理请求节流、SSL / EOF / IncompleteRead / 5xx 等瞬时错误；cache 使用原子写和中途 checkpoint |

### Readonly skill 优化点总结

| 优化点 | 详情 |
| --- | --- |
| 精确复刻视图 | 按 3 个 Group 条件和 2 个未解决状态执行 Freshdesk Search API 查询，再在本地去重，不逐个轮询整个 Ticket 池 |
| 安全与最小读取 | 只使用 `GET`；排除 Resolved、Closed、Spam，并在读取 conversations 前跳过 `Escalation`、`RMA`；附件只取元数据、不下载 |
| 有效识别上下文 | 组合 subject、客户首封邮件和公开客户会话，自动回复仅作上下文；信息不足时保留在 Technical Service 继续排查 |
| Merge 窄范围检查 | 仅在存在人名问候、`Re:` 或延续沟通信号时，限量检查近期 Ticket 标题和元数据 |
| 分流规则校准 | 已纳入真实反馈；Simpoyo/SIM、注册登录、常规云后台操作及所有硬件故障归 Technical Service，认证和证据充分的高级问题再转 Technical Support |
| 可操作输出 | 各导向分别成表；当前和 Merge 目标 Ticket ID 均为可点击链接，最终仍由人工复核和执行 |

## 适合的使用场景

- 快速看各 Agent 当前待处理 workload
- 班次交接、值班快照、临时 staffing 判断
- Hermes / Codex / 定时任务式的轻量运行
- 早晨集中检查未分配的新 Ticket，并获得按导向分组的分流建议
- 在人工执行改派前，快速识别疑似 Spam、Merge、CS、Sales 或技术支持升级项

## 下游同步提醒

本仓库是 Need Follow Up 核心脚本的上游。共享脚本或 Skill 版本更新后，Workload 项目不会自动继承；AI / Codex 发布前请阅读并完成：[Follow Up 下游同步提醒](docs/downstream-workload-sync.md)。

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

## 版本与更新记录

### `freshdesk-needs-follow-up-ticket-numbers`

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

### `freshdesk-readonly-ticket-inspector`（内部简版）

仓库尚未为 readonly skill 建立独立数字版本或 tag，以下按 Git 证据记录阶段，不补造版本号。

| 版本/阶段 | 更新日期 | 更新内容 |
| --- | --- | --- |
| 当前版 | 2026-07-16 | Ticket ID 改为可点击链接；Simpoyo/SIM、注册登录、常规云后台操作及硬件故障明确归 Technical Service |
| 规则优化版 | 2026-07-15 | 加入真实案例规则、标签跳过、附件元数据、窄范围 Merge 检查及按导向分表输出 |
| Triage 初版 | 2026-07-14 | 增加未分配新 Ticket 只读筛选和 conversations 获取模式 |
| 初始版 | 2026-06-24 | 建立 Freshdesk 只读 Ticket、Agent 和 Group 检查能力 |
