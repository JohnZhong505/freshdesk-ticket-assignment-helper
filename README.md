# Freshdesk Ticket 分配助手

中文 | [English](#english)

## 中文

这个仓库包含两个可独立安装的 Codex skill：

| Skill | 状态 | 用途 |
| --- | --- | --- |
| `freshdesk-needs-follow-up-ticket-numbers` | 已完成 | 轻量只读统计 skill，用于快速查看各组当前需要处理的 Ticket |
| `freshdesk-readonly-ticket-inspector` | 正在开发 | 更完整的 Freshdesk 巡检与操作辅助 skill |

### 适用场景

`freshdesk-needs-follow-up-ticket-numbers` 适合用于：

- 快速看各 Agent 当前待处理 workload
- 班次交接、值班快照、临时 staffing 判断
- Hermes / Codex / 定时任务式的轻量运行

### 当前输出口径

- `Need Follow Up` = `New + Customer Responded`
- `Customer Responded` = 客户最新回复后，Agent 还未再次公开回复
- `New` = 客户新建 Ticket，尚无 Agent 公开回复
- `FR overdue` = 首响超时
- `Resolution overdue` = 解决时限超时

### 主要优化点

| 优化点 | 详情 |
| --- | --- |
| 扫描范围 | 只扫描指定 group，不再全量扫所有 agent |
| 组选择流程 | 先列出 group，再明确选择后执行 |
| 停用账号 | 不将 deactivated 的 agent 作为有效扫描对象 |
| 小 cache | 增加本地缓存，减少重复请求、提升重复运行速度 |
| conversations 扫描 | 默认不全量扫描 conversations，仅在必要时定向复核 |
| 默认输出 | 默认输出为适合人阅读的表格，并直接在聊天中展示 |
| 表格精简 | 仅展示 Group Name 和每个 Agent 的关键数据 |
| 快速映射 | 支持“技术客服”“CS客服”“深圳团队”“墨西哥团队”等业务别名直跑 |
| README 文档 | README 提供中英文说明，便于协作与交接 |
| First Response Due 误报 | 主动外发 ticket 不再误计入真正需要处理的 `FR overdue` |
| Agent 名称显示 | 尽量显示真实姓名，避免只显示 `Agent <id>` |

### 内置业务别名

- `技术客服` / `技术客服组` / `技术客服的数据` => `Technical Service`
- `CS客服` / `CS客服组` / `CS客服的数据` => `Customer Service` + `Amazon`
- `深圳团队` => `Technical Service` + `Technical Support` + `Customer Service` + `Amazon`
- `墨西哥团队` => `MX Support`

### 默认输出格式

默认输出为表格，列顺序固定为：

1. `Need Follow Up`
2. `Customer Responded`
3. `New`
4. `FR overdue`
5. `Resolution overdue`

表格默认只展示：

- `Group Name`
- 每个 Agent 的统计行

如需 Ticket ID 明细，可使用 `--format json --pretty`。

### 安装

直接从 GitHub 安装时，使用以下路径：

- `skills/freshdesk-needs-follow-up-ticket-numbers`
- `skills/freshdesk-readonly-ticket-inspector`

本地安装脚本：

```bash
./install-skill.sh --skill freshdesk-needs-follow-up-ticket-numbers
./install-skill.sh --skill freshdesk-readonly-ticket-inspector
```

运行前需要：

- `FRESHDESK_DOMAIN`
- `FRESHDESK_API_KEY`
- Python 3
- 可访问 Freshdesk API 的网络环境

### 快速使用

先列 group：

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

### 安全边界

- 默认只使用 Freshdesk `GET` 接口
- 不做回复、分配、备注、联系人修改或批量写入
- 不应将 API key、webhook 或真实客户数据提交进仓库

## English

This repository contains two installable Codex skills:

| Skill | Status | Purpose |
| --- | --- | --- |
| `freshdesk-needs-follow-up-ticket-numbers` | Completed | Lightweight read-only workload counter for current actionable Freshdesk tickets |
| `freshdesk-readonly-ticket-inspector` | In Progress | Broader Freshdesk inspection and assisted operations skill |

### Best use

Use `freshdesk-needs-follow-up-ticket-numbers` for:

- fast agent workload snapshots
- shift handoff and duty review
- lightweight Hermes / Codex / scheduled runs

### Current metric

- `Need Follow Up` = `New + Customer Responded`
- `Customer Responded` = customer replied most recently and no newer public agent reply exists
- `New` = customer-created ticket with no public agent reply yet
- `FR overdue` = first response overdue
- `Resolution overdue` = resolution overdue

### Built-in aliases

- `技术客服` / `技术客服组` / `技术客服的数据` => `Technical Service`
- `CS客服` / `CS客服组` / `CS客服的数据` => `Customer Service` + `Amazon`
- `深圳团队` => `Technical Service` + `Technical Support` + `Customer Service` + `Amazon`
- `墨西哥团队` => `MX Support`

### Install

GitHub install paths:

- `skills/freshdesk-needs-follow-up-ticket-numbers`
- `skills/freshdesk-readonly-ticket-inspector`

### Safety

- Freshdesk `GET` only by default
- no replies, assignments, notes, contact edits, or bulk writes
- do not commit API keys, webhooks, or live customer data
