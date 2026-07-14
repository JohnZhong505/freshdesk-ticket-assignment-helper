# Freshdesk Triage Routing Rules

Source: DingTalk doc `new mail triage cases`.

Use these rules after fetching the unassigned triage pool. Classify from `subject` plus customer-authored `triage_text`; ignore public auto-replies except as context.

## Output Buckets

- `CS`: customer-service or commerce-service handling.
- `Technical Support`: technical-service handling.
- `Spam`: mark as spam candidate for manual confirmation.
- `Merge`: duplicate or continuation candidate.
- `Sales`: sales handoff candidate; no positive examples in the current source doc.
- `Manual Review`: not enough evidence or conflicting signals.

## CS

Route to `CS` when the request is about order, shipping, return logistics, warranty policy, or another non-technical service or policy question.

Signals:

- Return request caused by logistics or non-product-use reasons.
- Warranty policy question with no technical troubleshooting.
- General commerce or support-policy question rather than product configuration, firmware, network, or device behavior.

Examples from source doc:

- Return request where the note says the reason is logistics, not a technical issue.
- Warranty policy question only, with no technical issue.
- Several additional CS examples without extra source notes.

Exception:

- Return/exchange request form Tickets should default to `Technical Support` first, because a human needs to judge the return/exchange reason. AI should summarize the reason, not auto-route it to CS.

## Spam

Route to `Spam` when the message is empty, clickbait-like, internal test noise, or mainly tries to drive the reader to an unrelated external link.

Signals:

- `site.google.com` or similar suspicious hosted-page link with little useful support content.
- A button/link to an unusual URL, with empty or generic body text.
- Internal test messages that should not become support workload.

Examples from source doc:

- Spam examples with sparse or irrelevant content.
- Empty/generic body that mainly pushes a button to a special URL.
- Internal test information; choose Spam.

## Technical Support

Keep in `Technical Support` when the customer asks about device behavior, firmware, OpenWrt, networking, troubleshooting, product usage, or advanced technical/developer topics.

Signals:

- OpenWrt, pull requests, firmware behavior, logs, configuration, connectivity, router/VPN/network features.
- Any technical diagnosis request even if it also mentions order context.

Example from source doc:

- OpenWrt pull-request status question; source note says this is an advanced technical question.

## Merge

Flag as `Merge` when the triage pool contains duplicate Tickets or explicit continuation references.

Signals:

- Consecutive Tickets from the same requester with the same question.
- Subject starts with `Re:` and includes an existing Ticket ID.
- Body refers to a previous Ticket, reply, or same unresolved issue.

Example from source doc:

- Two consecutive Tickets from the same sender with the same question; merge candidate.

## Sales

No positive Sales examples are present in the current DingTalk source doc. For now, only suggest `Sales` with low confidence when the customer asks about bulk purchase, distribution/reseller cooperation, pricing quotation, partnership, or pre-sales business negotiation and there is no technical troubleshooting content.

## Confidence

- `high`: one bucket has clear rule signals and no conflict.
- `medium`: likely bucket, but the text is short or partially overlaps another bucket.
- `low`: no rule match, Sales without positive example support, or needs human judgment.

Return the suggested bucket, confidence, short reason, and the exact evidence phrase or subject fragment that triggered the suggestion. Do not write to Freshdesk.
