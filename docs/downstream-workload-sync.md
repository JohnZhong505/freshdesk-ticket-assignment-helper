# Follow Up 下游同步提醒

> 面向维护 `freshdesk-needs-follow-up-ticket-numbers` 的 AI / Codex。本仓库是 Follow Up 核心脚本的 canonical upstream。

## 发布时不能遗漏的下游

下游项目：

- Repo：`https://github.com/JohnZhong505/realtime-monthly-workload-refresh`
- Vendored script：`scripts/freshdesk_needs_follow_up_ticket_numbers.py`
- 详细 SOP：[Freshdesk Follow Up 上游同步 SOP](https://github.com/JohnZhong505/realtime-monthly-workload-refresh/blob/main/docs/freshdesk-followup-upstream-sync.md)

Workload 项目固定使用已验证的上游 commit，**不会自动继承本仓库的更新**。生产 cron 也禁止在运行时自动更新代码。

## Release checklist

只要共享脚本改变或 Skill 升级版本：

1. 在本仓库完成代码、测试、Skill/API contract/README 更新。
2. Commit 并 push。
3. 记录完整 commit SHA：

```bash
git rev-parse HEAD
```

4. 计算共享脚本 SHA-256：

```bash
shasum -a 256 \
  skills/freshdesk-needs-follow-up-ticket-numbers/scripts/freshdesk_needs_follow_up_ticket_numbers.py
```

5. 切换到 Workload 项目，按其 SOP 用固定 SHA 和 checksum 运行同步工具。
6. 在 Workload 中完成 parity、单元测试、`--check-config`、diff review、commit 和 push。
7. 两边都发布后，再更新 Hermes 已安装 Skill 与本地 Workload checkout；保留 cache，验证脚本/manifest 一致并检查 cron，不默认触发 live write。

如果只发布本仓库、不做第 5～6 步，交互式 Skill 会更新，但 08:30 Workload cron 仍会运行旧 vendored script。
