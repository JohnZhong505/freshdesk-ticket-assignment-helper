# Freshdesk Support Skills

## 中文说明

这个仓库提供两个可独立安装的 Codex skill，目录都在 `skills/` 下。

### Skills 列表

| Skill | 状态 | 作用 | 适用场景 |
| --- | --- | --- | --- |
| `freshdesk-readonly-ticket-inspector` | 正在开发 | 主 Freshdesk 技能，用于安全查看 Ticket、分配上下文和受控的单 Ticket 分配准备。 | 当你需要更完整的 Freshdesk 巡检或分析流程时使用。 |
| `freshdesk-needs-follow-up-ticket-numbers` | 已完成 | 轻量只读技能，只聚焦当前需要处理的 Ticket 统计。 | 当你只想快速看到每个 Agent 当前 `Need Follow Up`、`Customer Responded`、`New`、`FR overdue`、`Resolution overdue` 时使用。 |

### `freshdesk-needs-follow-up-ticket-numbers` 的口径

- `Need Follow Up`
  `New + Customer Responded`
- `Customer Responded`
  代表这个 Ticket 至少有过一次 agent 的公开回复，且目前最新一条公开往来是客户回复，agent 还没有对最新客户消息做新的公开回复
- `New`
  客户新发起的 Ticket，目前还没有 agent 的公开回复
- `FR overdue`
  `New` Ticket 的首次响应已超时
- `Resolution overdue`
  open Ticket 的解决时限已超时

另外，这个轻量 skill 现在对一类常见误报做了定向修正：

- 如果某个 Ticket 先被判成 `FR overdue`
- 且它是 `source = 10` 的 agent 主动外发 Ticket
- skill 才会额外调取这张票的 conversations 做复核
- 如果完全没有客户公开回复，这张票会从 `New` 和 `FR overdue` 中排除

### 组选择规则

- 先列出当前可用的 Freshdesk groups，再执行统计
- 人工交互运行时，应先让操作者明确选择要扫的 group
- 自动化运行时，必须显式传 `--group-id` 或 `--group-name`
- 不再默认无脑全量扫描所有 agent

### 内置组别别名

`freshdesk-needs-follow-up-ticket-numbers` 已内置下面几组常用映射：

- `技术客服`
- `技术客服组`
- `技术客服的数据`
  都映射到 `Technical Service`

- `CS客服`
- `CS客服组`
- `CS客服的数据`
  都映射到 `Customer Service` + `Amazon`

- `深圳团队`
  映射到 `Technical Service` + `Technical Support` + `Customer Service` + `Amazon`

- `墨西哥团队`
  映射到 `MX Support`

### 默认输出

默认输出是适合人看的 `table`，并且会直接在聊天里展示每个 Agent 的统计表。

列顺序固定为：

1. `Need Follow Up`
2. `Customer Responded`
3. `New`
4. `FR overdue`
5. `Resolution overdue`

表格只显示：

- `Group` 名称
- 每个 Agent 的统计行

不会再额外展示：

- `Group ID`
- group 级别总计统计

如果需要明细，可以改用 `--format json --pretty`。

### 性能与实现说明

- Freshdesk search 分页最多只到第 `10` 页
- 技能会先尝试一次 group 级 open-ticket 搜索
- 只有当某个 group 的 open Ticket 量超过单次搜索安全范围时，才会退回到该 group 内 agent 分批查询
- 不会去扫全账号所有 agent
- Ticket 分类优先复用本地 cache
- 未命中 cache 或 Ticket 已更新时，再调用 `GET /api/v2/tickets/[id]?include=stats`
- 只有 `source = 10` 的 `FR overdue` 候选票，才会额外调用 `GET /api/v2/tickets/[id]/conversations` 做误报排除
- 不再遍历每个 open Ticket 的所有 conversations

### 安装

仓库里的两个 skill 都可以单独安装。

直接从 GitHub 安装时，使用下面的 skill path：

- `skills/freshdesk-readonly-ticket-inspector`
- `skills/freshdesk-needs-follow-up-ticket-numbers`

本地脚本安装方式：

```bash
./install-skill.sh --skill freshdesk-readonly-ticket-inspector
./install-skill.sh --skill freshdesk-needs-follow-up-ticket-numbers
```

安装前需要准备：

- `FRESHDESK_DOMAIN`
- `FRESHDESK_API_KEY`
- 可访问 Freshdesk API 的网络环境
- Python 3

### 快速使用

先列 group：

```bash
python3 skills/freshdesk-needs-follow-up-ticket-numbers/scripts/freshdesk_needs_follow_up_ticket_numbers.py --list-groups
```

使用“技术客服”别名：

```bash
python3 skills/freshdesk-needs-follow-up-ticket-numbers/scripts/freshdesk_needs_follow_up_ticket_numbers.py \
  --group-name "技术客服的数据"
```

使用“CS客服组”别名：

```bash
python3 skills/freshdesk-needs-follow-up-ticket-numbers/scripts/freshdesk_needs_follow_up_ticket_numbers.py \
  --group-name "CS客服组"
```

使用“深圳团队”别名：

```bash
python3 skills/freshdesk-needs-follow-up-ticket-numbers/scripts/freshdesk_needs_follow_up_ticket_numbers.py \
  --group-name "深圳团队"
```

使用“墨西哥团队”别名：

```bash
python3 skills/freshdesk-needs-follow-up-ticket-numbers/scripts/freshdesk_needs_follow_up_ticket_numbers.py \
  --group-name "墨西哥团队"
```

输出 JSON 明细：

```bash
python3 skills/freshdesk-needs-follow-up-ticket-numbers/scripts/freshdesk_needs_follow_up_ticket_numbers.py \
  --group-name "Technical Service" \
  --format json \
  --pretty
```

### 安全边界

- 仓库内 skill 默认只使用 Freshdesk `GET` 接口
- 不做 Ticket 回复、分配、备注、联系人修改或批量写入
- 不应把 API key、webhook 或真实客户数据提交进仓库

## English

This repository contains two installable Codex skills under `skills/`.

### Skills

| Skill | Status | Purpose | Best use |
| --- | --- | --- | --- |
| `freshdesk-readonly-ticket-inspector` | In Progress | Main Freshdesk operations skill for safe ticket inspection, assignment context, and controlled single-ticket assignment preparation. | Use this when you need the broader Freshdesk support workflow. |
| `freshdesk-needs-follow-up-ticket-numbers` | Completed | Lightweight read-only skill focused on current actionable ticket counts only. | Use this for fast per-agent snapshots of `Need Follow Up`, `Customer Responded`, `New`, `FR overdue`, and `Resolution overdue`. |

### Meaning of the lightweight metric

- `Need Follow Up`
  `New + Customer Responded`
- `Customer Responded`
  The ticket has at least one public agent reply in its history, and the most recent public exchange is now a customer reply that still lacks a newer public agent reply.
- `New`
  The ticket was created by the customer and still has no public agent reply.
- `FR overdue`
  The first-response deadline has passed for a `New` ticket.
- `Resolution overdue`
  The resolution deadline has passed for an open ticket.

The lightweight skill now also corrects one common false-positive case:

- if a ticket is first classified as `FR overdue`
- and it is an agent-initiated outbound email ticket with `source = 10`
- the skill performs one targeted conversations recheck
- if there is still no public customer reply, that ticket is excluded from `New` and `FR overdue`

### Group-selection rules

- List current Freshdesk groups before running the metric.
- In human-in-the-loop runs, require the operator to choose which group or groups to scan.
- In automation, always pass `--group-id` or `--group-name` explicitly.
- The lightweight skill no longer defaults to scanning every agent blindly.

### Built-in group aliases

The lightweight skill includes these alias mappings:

- `技术客服`
- `技术客服组`
- `技术客服的数据`
  map to `Technical Service`

- `CS客服`
- `CS客服组`
- `CS客服的数据`
  map to `Customer Service` + `Amazon`

- `深圳团队`
  maps to `Technical Service` + `Technical Support` + `Customer Service` + `Amazon`

- `墨西哥团队`
  maps to `MX Support`

### Default output

The default output format is a human-readable `table`, intended to be shown directly in chat.

The columns are always ordered as:

1. `Need Follow Up`
2. `Customer Responded`
3. `New`
4. `FR overdue`
5. `Resolution overdue`

The table shows only:

- the `Group` name
- one row per agent

It does not show:

- `Group ID`
- group-level aggregate totals

Use `--format json --pretty` when you need detailed ticket IDs and metadata.

### Performance notes

- Freshdesk search pagination stops at page `10`
- The skill tries a direct group-level open-ticket search first
- It falls back to agent-batched searches only when that group exceeds the safe search window
- The fallback remains inside the selected group
- Ticket classification reuses a local cache whenever possible
- Changed or uncached tickets are refreshed through `GET /api/v2/tickets/[id]?include=stats`
- Only outbound-email `FR overdue` candidates use an extra `GET /api/v2/tickets/[id]/conversations` recheck
- The skill no longer scans every conversation in every open ticket

### Installation

Both skills are independently installable.

When installing directly from GitHub, use these repo paths:

- `skills/freshdesk-readonly-ticket-inspector`
- `skills/freshdesk-needs-follow-up-ticket-numbers`

Local script install:

```bash
./install-skill.sh --skill freshdesk-readonly-ticket-inspector
./install-skill.sh --skill freshdesk-needs-follow-up-ticket-numbers
```

Required runtime inputs:

- `FRESHDESK_DOMAIN`
- `FRESHDESK_API_KEY`
- network access to the Freshdesk API
- Python 3

### Quick usage

List groups first:

```bash
python3 skills/freshdesk-needs-follow-up-ticket-numbers/scripts/freshdesk_needs_follow_up_ticket_numbers.py --list-groups
```

Technical Service via alias:

```bash
python3 skills/freshdesk-needs-follow-up-ticket-numbers/scripts/freshdesk_needs_follow_up_ticket_numbers.py \
  --group-name "技术客服的数据"
```

Customer Service plus Amazon via alias:

```bash
python3 skills/freshdesk-needs-follow-up-ticket-numbers/scripts/freshdesk_needs_follow_up_ticket_numbers.py \
  --group-name "CS客服组"
```

Shenzhen team via alias:

```bash
python3 skills/freshdesk-needs-follow-up-ticket-numbers/scripts/freshdesk_needs_follow_up_ticket_numbers.py \
  --group-name "深圳团队"
```

Mexico team via alias:

```bash
python3 skills/freshdesk-needs-follow-up-ticket-numbers/scripts/freshdesk_needs_follow_up_ticket_numbers.py \
  --group-name "墨西哥团队"
```

Full JSON detail:

```bash
python3 skills/freshdesk-needs-follow-up-ticket-numbers/scripts/freshdesk_needs_follow_up_ticket_numbers.py \
  --group-name "Technical Service" \
  --format json \
  --pretty
```

### Safety

- The skills in this repo use read-only Freshdesk `GET` calls by default
- They do not reply, reassign, add notes, edit contacts, or perform bulk writes
- API keys, webhooks, and live customer data should not be committed into the repo
