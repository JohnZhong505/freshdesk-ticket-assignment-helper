# Freshdesk Ticket 分配助手

中文 | [English](./README.en.md)

这个仓库提供两个可独立安装的 Codex skill，面向 Freshdesk 的轻量统计、Ticket 分流与受控分配场景。

## Skill 列表

| Skill | 状态 | 用途 |
| --- | --- | --- |
| `freshdesk-needs-follow-up-ticket-numbers` | 已完成 | 轻量只读统计当前需要跟进的 Ticket，适合班次交接、值班快照、临时 staffing 判断 |
| `freshdesk-ticket-assignment-helper` | 可用（持续优化） | 支持技术客服与 CS 两种只读分流视角；经确认后，可按两个固定方向安全改派 Group |

## 当前推荐使用

当前稳定可用的是 `freshdesk-needs-follow-up-ticket-numbers`。

- 轻量统计 skill 最新版本：`v1.7.2`（2026-07-24）
- Ticket 分配助手最新版本：`v2.3`（2026-07-24）
- 仓库地址：[JohnZhong505/freshdesk-ticket-assignment-helper](https://github.com/JohnZhong505/freshdesk-ticket-assignment-helper)

`freshdesk-ticket-assignment-helper` 已可用于技术客服与 CS 的新 Ticket 初步分流，并提供严格确认后的固定方向 Group 改派。两个 skill 相互独立：分配助手不统计“需跟进 Ticket”数量，也不会影响已稳定运行的轻量统计 skill。

## 如何安装

如果是第一次使用 Codex，直接在对话里发送下面这段话即可：

```text
帮我安装这个 skill：GitHub: https://github.com/JohnZhong505/freshdesk-ticket-assignment-helper
Skill path: skills/freshdesk-needs-follow-up-ticket-numbers
```

如需安装另一个 skill，可将 `Skill path` 改为：

- `skills/freshdesk-needs-follow-up-ticket-numbers`
- `skills/freshdesk-ticket-assignment-helper`

本地脚本安装方式：

```bash
./install-skill.sh --skill freshdesk-needs-follow-up-ticket-numbers
./install-skill.sh --skill freshdesk-ticket-assignment-helper
```

## 运行前需要准备

- `FRESHDESK_DOMAIN`
- `FRESHDESK_API_KEY`
- Python 3
- 可访问 Freshdesk API 的网络环境

无人值守卡片模式还需要：已配置推理模型的 Hermes、DWS CLI `v1.0.52` 或更高版本，以及有效的 DWS 登录。消息目标已固定在 Cron driver 中且不能通过环境变量覆盖：技术客服视角及故障卡片发到群名精确为“测试”的群；CS 视角私信 Amber（CS客服）。Cron 不会在运行时搜索群或联系人。

Hermes 定时任务会过滤 API Key 环境变量，因此应通过权限受限的 `~/.config/freshdesk-ticket-assignment-helper/credentials.json` 提供 Freshdesk domain 与 API Key。该凭据文件和真实客户数据不得提交进仓库。

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

## Ticket 分配助手：默认只读分流

`freshdesk-ticket-assignment-helper` 用于早晨检查 Freshdesk 未分配的新 Ticket。默认只读取数据并给出分流建议；支持 Technical Service 与 Customer Service 两种视角。完成对应固定方向的 dry-run 后，用户直接回复“确认”即可改派当前预览批次，Agent 始终保持空。

默认筛选口径：

| 筛选项 | 口径 |
| --- | --- |
| Agent | `Unassigned` |
| Group | 技术客服视角默认：`Technical Service`、界面中的 `Unassigned`；显式使用 `--include-mx-support` 时再加入 `MX Support`；CS 视角：`Customer Service` |
| Status | `All unresolved`，即只包含 `Open` 和 `Pending`，排除 `Resolved` 和 `Closed` |
| Spam | 排除已经标记为 Spam 的 Ticket |
| Tags | 跳过带有 `Escalation` 或 `RMA` 标签的 Ticket，保留给人工完整审核 |

交互式会话首次运行技术客服视角时，如果用户尚未说明范围，skill 会先询问本次是否包含 `MX Support`；无人值守 Cron 不询问，并固定使用默认的不含 MX Support 口径。

判断时主要读取 `subject`、客户首封邮件 `description_text`、后续公开客户会话和附件元数据。自动回复只作为上下文，不作为主要分流依据；初筛阶段不下载附件。出现人名问候、`Re:`、延续旧沟通措辞，或同一 requester 在 30 分钟内连续提交空主题、同主题或相同正文 Ticket 时，才会限量检查近期 Ticket 元数据；碎片正文不设字数门槛，只允许后票建议合并到更早 Ticket，并保留目标 Ticket 的 Group 和 Agent。

输出按建议导向分别集中成表格。技术客服视角保留 `Technical Service` 与 `Technical Support` 的细分；CS 视角中所有技术问题统一导向 `Technical Service`。Ticket ID 直接使用脚本生成的数字 Markdown 链接，不读取网页标题；Merge 建议中的新旧 ID 都可直接点击。

当前明确归入 `Technical Service` 的场景还包括：Simpoyo/SIM 套餐问题、注册与登录、常规云平台后台操作，以及变砖、无法上电、疑似硬件损坏等硬件故障。小批量、电商渠道或运营报价类需求先归为 `CS`，由 CS 再决定是否转 Shopify。

### 无人值守卡片模式（v2.3）

`freshdesk_triage_cron.py` 将可脚本化步骤收口在确定性流程中：调用现有 GET-only inspector、校验分类 JSON、按视角排序、生成 DWS 流式卡片、去重并记录脱敏日志。外层 Hermes Cron 使用 `--no-agent --script`；内层只为本批 Ticket 发起一次无历史上下文的 `hermes chat -q --ignore-rules --quiet` 分类会话，仅启用 `todo` toolset，不获得终端、文件、浏览器、Computer Use、DWS 或 Freshdesk 工具。分类会话使用独立 source 标记，结束后自动软归档。

技术客服视角按 `CS → Spam → Sales → Technical Support → Merge → Manual Review → 保留 Technical Service` 展示；CS 视角按 `Technical Service → Sales → Spam → Merge → Manual Review → 保留 Customer Service` 展示。正常消息只包含非空的分流建议表格，长结果按字节上限完整分卡并记录已完成分段。最后一张卡片末尾固定显示跳过的 Escalation/RMA 数量和已判断 Ticket 总数；两个计数也参与同日去重。零 Ticket 和同日未变化结果不发钉钉卡片，但 no-agent stdout 会输出脱敏 JSON heartbeat，避免 Hermes 误判为 `SILENT`；结果变化后可再次发送。

Cron 路径始终只读 Freshdesk，不包含或调用改派脚本。外层 wrapper 只对读取、分类和 DWS 发送前检查这三类无副作用临时失败重试，最多 3 次，默认等待 60 秒和 120 秒；发送失败不重试，避免重复发卡。双视角使用独立状态文件和操作系统互斥锁，长任务不会被基于时间的“过期锁”抢占。故障卡片仅发往技术客服群目标。当前双向一键改派仍只允许在交互会话中完成 dry-run 并经用户确认后执行；Spam、Sales、Technical Support 和 Merge 等导向始终只是建议。

两条 Cron 每天触发，driver 使用 `Asia/Shanghai` 和随 Skill 发布的 `references/china-mainland-workdays-YYYY.json` 判断中国大陆真实工作日。调休周末正常执行；法定节假日和普通周末在读取凭据、加锁或调用 Freshdesk、Hermes、DWS 前以退出码 `0`、空 stdout 静默结束。年度文件缺失或无效时 fail-close，并只按既有边界向“测试”群尝试发送故障卡片。

```bash
hermes cron create "55 8 * * *" --name freshdesk-triage-technical-service --script hermes_cron_technical_service.py --no-agent --deliver local
hermes cron create "58 8 * * *" --name freshdesk-triage-customer-service --script hermes_cron_customer_service.py --no-agent --deliver local
```

每日调度不代表每天发卡；年度日历 gate 决定当天是否执行。新年度开始前，应根据国务院办公厅当年节假日安排新增对应 JSON，生产运行时不会联网查询或猜测工作日。

部署时必须先更新 Skill 并确认当年日历文件存在，再回读现有 Hermes Cron：应替换同名的旧工作日任务，不能新旧并存；同时确认调度器将 `08:55`、`08:58` 按 `Asia/Shanghai` 触发。创建后再次回读两个任务，并在已知工作日各运行一次 wrapper 验证。详细围栏见 Skill 的 `Hermes deployment checklist`。

交互会话需要把当前分流表发送到钉钉时，统一使用 `freshdesk_send_triage_cards.py`：默认只预览，当前用户明确授权发送后才加 `--send`。脚本复用相同的校验、排序、数字 Ticket 链接、分卡和断点续发逻辑；CS 视角固定私信 Amber，技术客服视角固定发送到“测试”群，不接受收件人参数，也不会运行时搜索联系人或群聊。

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
| 误报控制 | conversations 仅在必要时定向复核；排除内部发件人造成的 `Customer Responded` 误报，并将主动外发后客户已回或仍待客户的 Ticket 正确区分 |
| 输出与交接 | 默认输出精简表格、运行耗时和设备本地时区的结束时间；版本仅在 `SKILL.md` 声明，JSON 用法也不在每次表格中重复提示 |
| 运行稳定性 | 统一处理请求节流、SSL / EOF / IncompleteRead / 5xx 等瞬时错误；cache 使用原子写和中途 checkpoint |

### Ticket 分配助手优化点总结

| 优化点 | 详情 |
| --- | --- |
| 精确复刻与完整性 | 按所选视角的 Group/未解决状态组合执行 Freshdesk Search API 查询并按 Ticket ID 去重；总数缺失、移动视图重复不一致或超过 300 张 Search 上限时 fail-close，不返回截断结果 |
| 安全与最小读取 | 默认只使用 `GET`；排除 Resolved、Closed、Spam，并在读取 conversations 前跳过 `Escalation`、`RMA`；附件只取元数据、不下载；交互模式从环境变量读取 API Key，Cron 从权限受限的凭据文件读取 |
| 有效识别上下文 | 组合 subject、客户首封邮件和公开客户会话，自动回复仅作上下文；信息不足时保留在 Technical Service 继续排查 |
| Merge 窄范围检查 | 仅在存在人名问候、`Re:` 或延续沟通信号时，限量检查近期 Ticket 标题和元数据 |
| 分流规则校准 | 已纳入真实反馈；Simpoyo/SIM、注册登录、常规云后台操作及所有硬件故障归 Technical Service，认证和证据充分的高级问题再转 Technical Support |
| 可操作输出 | 先汇总识别数与标签跳过数，再按导向分表；Ticket ID 可点击；证据列固定为简短中文概述，可保留必要的英文产品名或报错关键词；结尾统计可改派 CS 数量并询问是否进入一键改派 |
| 双视角与 Merge | 支持技术客服/CS 两个未分配池；同一 requester 30 分钟内空主题、同主题或相同正文的碎片 Ticket 只允许后票指向更早 Merge 候选 |
| 克制的双向改派 | 只允许 TS→CS 与 CS→TS 两个固定方向；先 dry-run，确认后只写 `group_id`，逐张回读 Group 与空 Agent |
| Cron 与卡片通知 | 外层 no-agent、内层无上下文受限分类；消息目标固定且禁止运行期搜索；按视角隔离状态与锁，选择性重试无副作用阶段，并支持中国大陆工作日 gate、尾部数量汇总、会话归档、成功 heartbeat、同日去重、完整分卡与断点续发、脱敏故障通知和 fail-close 校验 |
| 交互式钉钉发送 | 使用固定脚本先预览再按当前授权发送；复用 Cron 的表格与链接校验，两个视角分别写死 Amber 和“测试”群，禁止临时搜索或覆盖目标 |

## 适合的使用场景

- 快速看各 Agent 当前待处理 workload
- 班次交接、值班快照、临时 staffing 判断
- Hermes / Codex / 定时任务式的轻量运行
- 早晨集中检查未分配的新 Ticket，并获得按导向分组的分流建议
- 在人工执行改派前，快速识别疑似 Spam、Merge、CS、Sales 或技术支持升级项
- 在远端 Hermes 环境中定时生成双视角分流卡片；仓库仅提供已验证脚本，不代表 Cron 已部署或正在运行

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
python3 skills/freshdesk-ticket-assignment-helper/scripts/freshdesk_readonly_ticket_inspector.py \
  --triage-view technical-service \
  --pretty
```

CS 视角使用：

```bash
python3 skills/freshdesk-ticket-assignment-helper/scripts/freshdesk_readonly_ticket_inspector.py \
  --triage-view customer-service \
  --pretty
```

预览选定 Ticket 改派至 CS（默认不写入）：

```bash
python3 skills/freshdesk-ticket-assignment-helper/scripts/freshdesk_assign_cs_group.py \
  --route technical-service-to-customer-service \
  --ticket-ids "136100,136101" \
  --pretty
```

核对预览后执行：

```bash
python3 skills/freshdesk-ticket-assignment-helper/scripts/freshdesk_assign_cs_group.py \
  --route technical-service-to-customer-service \
  --ticket-ids "136100,136101" \
  --execute \
  --confirm-ticket-ids "136100,136101" \
  --pretty
```

上述 `--confirm-ticket-ids` 是 CLI 内部防误操作参数。通过 Codex 使用时，用户只需对最近一次成功预览回复“确认”，无需手动复述 Ticket ID。

从 CS 改派至技术客服时，将 `--route` 改为 `customer-service-to-technical-service`。

## 安全边界

- 默认只使用 Freshdesk `GET` 接口；分流结果是辅助建议
- 无人值守 Cron 只读取 Freshdesk 并发送分流建议卡片，不执行任何 Ticket 改派
- 唯一允许的写入是经确认后，按 `Technical Service → Customer Service` 或 `Customer Service → Technical Service` 两个固定方向修改 `group_id`
- 来源必须符合所选固定方向；TS→CS 可接受 `Technical Service` 或空 Group，CS→TS 只接受 `Customer Service`；两者都要求 Agent 为空、Open/Pending、非 Spam 且无 `Escalation`/`RMA`
- 单次最多 20 张，逐张写入并回读；不使用批量接口，不设置 Agent，不改状态、标签、内容或联系人
- 交互脚本只通过 `FRESHDESK_API_KEY` 环境变量接收 API Key；无人值守 Cron 只读取权限受限的凭据文件；两者都不接受命令行 API Key
- 分流时可在内部处理客户正文，但面向用户只输出必要证据摘要；不应将 API key、webhook 或真实客户数据提交进仓库

## 版本与更新记录

### `freshdesk-needs-follow-up-ticket-numbers`

| 版本 | 更新日期 | 更新内容 |
| --- | --- | --- |
| v1.7.2 | 2026-07-24 | 修复 Freshdesk stats 将 `source=10` 主动外发票保留为 New 的误判：客户已回时转为 Customer Responded，仅我方外发时即使尚未 FR overdue 也排除；复核结果沿用现有 cache |
| v1.7.1 | 2026-07-22 | 在 `SKILL.md` 声明版本；表格及 JSON 输出运行耗时与设备本地时区的结束时间；cache 格式与统计口径不变 |
| v1.7 | 2026-07-15 | 增加 5 分钟 Customer Responded 发件人复核；分页选择最新公开会话；内部邮箱结果进入 cache；增加复核统计 |
| v1.6 | 2026-07-15 | 增加 `last_seen_at` 与默认 30 天 cache 保留期；兼容旧 cache；JSON 输出保留期和清理数量；保留原子写入与中途 checkpoint |
| v1.5 | 2026-07-10 | 完善请求节流、瞬时错误重试、cache 原子写与 checkpoint，并补齐 Python 3.9 兼容和命中率展示 |
| v1.3 | 2026-07-01 | 增加业务别名、真实 Agent 名称，并修正主动外发 Ticket 的 `FR overdue` 误报 |
| v1.0 | 2026-06-30 | 完成 group 选择、默认表格输出、基础统计口径与本地 cache |

### `freshdesk-ticket-assignment-helper`

| 版本 | 更新日期 | 更新内容 |
| --- | --- | --- |
| v2.3 | 2026-07-24 | 卡片末尾增加 Escalation/RMA 跳过数和已判断总数并纳入去重；Cron 改为每日触发，由仓库内中国大陆年度工作日日历决定调休执行和节假日静默，并补充 Hermes 时区、同名任务替换和部署后回读检查 |
| v2.2.2 | 2026-07-23 | 修复 macOS 最小 cron/SSH 环境中 DWS 的 `/usr/bin/env node` 找不到同目录 Node 的问题；仅为 DWS 子进程前置固定 DWS 所在目录，不修改 Hermes 配置 |
| v2.2.1 | 2026-07-23 | 将分流结果的证据列固定为简短中文概述；允许保留必要的英文产品名、报错或关键词，英文-only 证据会 fail-close 并触发重新分类 |
| v2.2 | 2026-07-23 | 修复 no-agent 成功结果被判为 `SILENT`；补齐同发件人 30 分钟内相同正文碎片的较早 Ticket Merge 候选；完整读取并分段发送全部结果；增加固定目标、预览优先且可断点续发的交互式钉钉发送入口，并补强 5xx 重试与 fail-close 校验 |
| v2.1 | 2026-07-22 | 合并 v2.0.1 与 Hermes 修复分支：内层分类改为无上下文 chat 会话并自动归档；增加选择性重试、双视角状态隔离和跨平台系统锁；固定消息目标并禁止运行期搜索；补强分类 JSON 与项目验证器的 fail-close 校验 |
| v2.0.1 | 2026-07-22 | 固定 Cron 消息目标为“测试”群和 Amber；技术客服视角默认排除 MX Support，并保留显式加入开关 |
| v2.0 | 2026-07-21 | 增加双视角无人值守 Cron 卡片流程：受限 Hermes 分类、视角排序、DWS 固定目标、同日去重、脱敏故障卡片与 fail-close 校验；保留交互式双向改派，Cron 不写 Freshdesk |
| v1.6 | 2026-07-21 | 增加 CS 分流视角及改派至 Technical Service；Ticket ID 固定为数字链接；加入同发件人 30 分钟碎片 Ticket Merge 识别 |
| v1.5 | 2026-07-21 | CS 改派允许直接确认当前 dry-run 批次；API Key 改为仅从环境变量读取；补充 Freshdesk 搜索 10 页边界、截断标记和客户正文隐私边界 |
| v1.4.1 | 2026-07-17 | 固定会话输出摘要：识别数、Escalation/RMA 跳过数、可改派 CS 数量及一键改派确认提示 |
| v1.4 | 2026-07-16 | skill 更名为 Ticket Assignment Helper；保留默认只读分流，并增加经 ID 二次确认、逐张写入和写后回读的 Customer Service Group 改派能力 |
| v1.3 | 2026-07-16 | Ticket ID 改为可点击链接；Simpoyo/SIM、注册登录、云后台操作及硬件故障归 Technical Service；物流通用模板与伪装短链归 Spam |
| v1.2 | 2026-07-15 | 加入真实案例规则、标签跳过、附件元数据、窄范围 Merge 检查及按导向分表输出 |
| v1.1 | 2026-07-14 | 增加未分配新 Ticket 只读筛选和 conversations 获取模式 |
| v1.0 | 2026-06-24 | 建立 Freshdesk 只读 Ticket、Agent 和 Group 检查能力 |
