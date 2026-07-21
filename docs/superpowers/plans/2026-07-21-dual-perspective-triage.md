# Dual-Perspective Freshdesk Triage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic Ticket links, 30-minute fragment Merge detection, Customer Service triage, and guarded Customer Service-to-Technical Service assignment without weakening the existing flow.

**Architecture:** Keep the existing GET-only inspector and parameterize it with two fixed views. Reuse the current sequential assignment helper with two fixed route definitions; the CLI never accepts arbitrary Group or Agent values.

**Tech Stack:** Python standard library, Freshdesk API v2, assertion-based validation scripts.

---

### Task 1: Inspector contracts

**Files:**
- Modify: `validation/test_triage_helpers.py`
- Modify: `skills/freshdesk-ticket-assignment-helper/scripts/freshdesk_readonly_ticket_inspector.py`

- [ ] Add failing assertions for `ticket_link_markdown`, same-requester 30-minute fragment detection, earliest Merge target, and both view filters.
- [ ] Run `python validation/test_triage_helpers.py` and confirm the new assertions fail.
- [ ] Add the minimum timestamp and subject checks, preserving body length and target Group/Agent metadata.
- [ ] Run `python validation/test_triage_helpers.py` and confirm it passes.

### Task 2: Perspective-specific routing instructions

**Files:**
- Modify: `skills/freshdesk-ticket-assignment-helper/SKILL.md`
- Modify: `skills/freshdesk-ticket-assignment-helper/references/triage-routing-rules.md`
- Modify: `skills/freshdesk-ticket-assignment-helper/references/freshdesk-api-contract.md`
- Modify: `validation/test_triage_helpers.py`

- [ ] Add failing contract checks for the Customer Service buckets and deterministic link field.
- [ ] Document that Customer Service sends every technical issue to Technical Service, while Spam, Sales, Merge, Manual Review, protected tags, and privacy rules remain shared.
- [ ] Require grouped tables and a view-specific assignment count and confirmation prompt.
- [ ] Run `python validation/test_triage_helpers.py` and confirm it passes.

### Task 3: Fixed two-way assignment

**Files:**
- Modify: `skills/freshdesk-ticket-assignment-helper/scripts/freshdesk_assign_cs_group.py`
- Modify: `validation/test_cs_group_assignment.py`
- Modify: `skills/freshdesk-ticket-assignment-helper/SKILL.md`
- Modify: `skills/freshdesk-ticket-assignment-helper/references/freshdesk-api-contract.md`

- [ ] Add failing tests for the two fixed routes and rejection of mismatched source Groups.
- [ ] Replace hard-coded direction constants with a `--route` choice: `technical-service-to-customer-service` or `customer-service-to-technical-service`.
- [ ] Keep the request body exactly `{"group_id": target_id}`, require Agent empty, recheck before PUT, reread after PUT, and stop on first failure or ambiguity.
- [ ] Run `python validation/test_cs_group_assignment.py` and confirm it passes.

### Task 4: Verification and installation

**Files:**
- Modify: `skills/freshdesk-ticket-assignment-helper/agents/openai.yaml`
- Modify: `README.md`

- [ ] Run all four validation scripts and `git diff --check`.
- [ ] Copy the changed skill files to `C:/Users/Administrator/.codex/skills/freshdesk-ticket-assignment-helper`.
- [ ] Run GET-only `--limit 1` smoke checks for both views and compare installed/source hashes.
- [ ] Do not execute a live assignment and do not push GitHub.
