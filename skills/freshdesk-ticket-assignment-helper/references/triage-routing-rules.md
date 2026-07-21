# Freshdesk Triage Routing Rules

Sources:

- DingTalk doc `new mail triage cases`.
- DingTalk doc `新邮件分配——Ticket分流规则`, an informal reference containing both routing hints and non-routing operating notes.

Newer confirmed rules take precedence over older or experience-based notes. Only group-routing signals are retained here; reply wording, urgency handling, named-person assignment, workload balancing, and other mail-processing procedures are excluded.

Use these rules after fetching the unassigned triage pool. Classify from `subject` plus customer-authored `triage_text`; ignore public auto-replies except as context.

## Customer Service Perspective

When `triage_view` is `customer-service`, use only these output buckets:

- `Stay in Customer Service`: orders, logistics, refunds, policy, ordinary ecommerce service, and small-batch quotations.
- `Technical Service`: every technical, product-use, configuration, account/login, cloud-platform, firmware, networking, diagnostic, certification, API, or hardware issue. Do not output `Technical Support`; Customer Service does not need to distinguish frontline from advanced technical handling.
- `Sales`, `Spam`, `Merge`, and `Manual Review`: apply the shared rules below unchanged.

A return or exchange request stays in Customer Service only when it is clearly about policy or logistics. Route it to Technical Service when the reason is a product symptom or technical fault. For a Technical Service assignment candidate, the current Group must be exactly `Customer Service` and the Agent must be empty.

## Output Buckets

- `CS`: customer-service or commerce-service handling.
- `Technical Service`: keep with the frontline technical-service team for normal intake, clarification, and common troubleshooting.
- `Technical Support`: escalate only after the issue is sufficiently evidenced and clearly needs advanced technical handling.
- `Spam`: mark as spam candidate for manual confirmation.
- `Merge`: duplicate or continuation candidate.
- `Sales`: large-volume or dedicated commercial-project handoff.
- `Manual Review`: not enough evidence or conflicting signals.

## Routing Precedence

Apply these checks in order:

1. `Merge` when the message continues an existing quotation, prior Ticket, or named colleague's active follow-up.
2. `Technical Service` when product fit, exact model, or technical feasibility must be confirmed before anyone quotes.
3. `Technical Support` for certification information or sufficiently evidenced advanced technical work.
4. `CS` for a confirmed product and small-batch ecommerce quotation; CS hands off to Shopify when appropriate.
5. `Sales` only for clearly large-volume or dedicated commercial projects.

## CS

Route to `CS` when the request is about order, shipping, return logistics, warranty policy, or another non-technical service or policy question.

Signals:

- Return request caused by logistics or non-product-use reasons.
- Warranty policy question with no technical troubleshooting.
- General commerce or support-policy question rather than product configuration, firmware, network, or device behavior.
- Requests for one or two sample units for a school, research, or similar small project.
- Confirmed-product quotations, ecommerce terms, and ordinary small-batch orders, including quantities around 50 units. From this Technical Service skill, route these to CS; CS hands off to Shopify when appropriate.
- Low-priced products ordered in roughly 100 to 200 units can also go to CS for direct ecommerce handling when the customer does not need channel maintenance.

Examples from source doc:

- Return request where the note says the reason is logistics, not a technical issue.
- Warranty policy question only, with no technical issue.
- Several additional CS examples without extra source notes.

Exception:

- Return/exchange request form Tickets should default to `Technical Service` first, because a human needs to judge the return/exchange reason. AI should summarize the reason, not auto-route it to CS.
- Do not route a generic delivery or damaged-package story to CS when it has no product, brand, or real order information and mainly pushes a shortened or disguised tracking link. Treat that pattern as `Spam` even when the logistics narrative is detailed and plausible.

## Spam

Route to `Spam` when the message is empty, clickbait-like, internal test noise, or mainly tries to drive the reader to an unrelated external link.

Signals:

- `site.google.com` or similar suspicious hosted-page link with little useful support content.
- A button/link to an unusual URL, with empty or generic body text.
- Internal test messages that should not become support workload.
- Advertisements or templated partnership outreach with no concrete company, project, product, quantity, or cooperation details.
- Marketing or advertising outreach that describes only the sender's own company, services, contacts, website, revenue claims, or platform capabilities but does not mention GL.iNet, a GL.iNet product, our audience, or a concrete reason for contacting us.
- A message that could be sent unchanged to any company is mass-marketing Spam even when the sender provides real-looking company and contact information.
- Generic delivery, package-damage, or failed-delivery templates with no product, brand, or real order information, especially when they could be sent unchanged to any ecommerce site.
- Shortened or redirect links such as `tr.ee`, particularly when the visible link title is `Order Status`, tracking, delivery details, or another call to click. Do not open the link during triage; the disguised call-to-action plus missing GL.iNet-specific order context is a strong Spam signal.

Examples from source doc:

- Spam examples with sparse or irrelevant content.
- Empty/generic body that mainly pushes a button to a special URL.
- Internal test information; choose Spam.
- A detailed damaged-package story with an `Order Status` link pointing to `tr.ee`: classify as Spam because the story is generic and the link is designed to induce a click.

## Technical Service

Keep in `Technical Service` when frontline technical staff should first clarify the symptom, perform common troubleshooting, or collect evidence before any escalation.

Signals:

- The problem description is short or vague and does not establish the actual failure mode.
- No useful logs, diagnostics, reproduction steps, or other technical evidence are present.
- Attachments are non-diagnostic items such as an invoice, receipt, or ordinary screenshot. An invoice does not count as technical evidence.
- The customer proposes a feature request, UI improvement, usability change, or product suggestion rather than reporting a complex technical fault.
- The issue looks like a common setup, connectivity, or product-use question that frontline technical service can troubleshoot first.
- The customer mentions a possible purchase but does not yet understand the products well enough to confirm product fit, feasibility, or the correct model. Answer those questions before routing for a formal quotation.
- A third-party plugin has not yet been deployed and the customer only asks whether or how it can be used; keep frontline handling and direct them to community resources when appropriate.
- A VLAN request is only a simple planning question without a deployed scenario.
- The requested outcome is available in the GL.iNet GUI; prefer the supported GUI path before treating LuCI or SSH behavior as an advanced defect.
- A business customer has a simple question that frontline staff can answer without advanced investigation.
- SIM plan, activation, or account questions submitted from `simpoyo.com` belong to `Technical Service`.
- Registration and login questions should start with `Technical Service`, because they are commonly caused by misunderstanding or an operation error.
- Cloud-platform backend registration, whitelisting, and other routine backend operations belong to `Technical Service`; the team has permission to perform them and should first confirm the request.
- All reported hardware faults belong to `Technical Service`, including devices described as bricked, unable to power on, or likely to have a failed component. Frontline staff confirms the failure and handles the normal warranty/RMA path before any later escalation.

Examples:

- A device is described only as "offline" and the only attachment is an invoice: keep with Technical Service to clarify the symptom and collect logs.
- A customer asks to add or standardize green UI indicators: treat it as a feature request and keep with Technical Service.
- A prospective buyer compares several unfamiliar products and asks whether they can satisfy the use case: keep with Technical Service until the requirement and exact model are confirmed, even if a future purchase quantity is mentioned.
- A Simpoyo SIM-plan activation request: keep with Technical Service.
- A KVM registration or whitelist request, even with a log attachment: keep with Technical Service to verify the account, device, and required backend operation.
- A router described as bricked or unable to power on: keep with Technical Service as a common hardware-fault workflow.

## Technical Support

Route to `Technical Support` only when the issue is already specific enough, has useful technical evidence, or clearly requires advanced investigation beyond common frontline troubleshooting.

Do not use this bucket for registration/login requests, routine cloud-platform backend operations, or reported hardware faults such as bricked/no-power devices. Those remain with `Technical Service` under the newer confirmed rules.

Signals:

- Reproducible firmware behavior with version details, useful logs, diagnostics, or clear reproduction steps.
- Advanced OpenWrt, pull-request, developer, networking, VPN, or system-level questions.
- Explicit requests for regulatory certification, conformity approval, or authoritative certification lists; Technical Support owns this information when CS does not have it.
- Requests for official API documentation.
- GoodCloud Site to Site or S2S issues.
- A third-party plugin is already deployed and has a specific reproducible problem that the support team accepts for investigation.
- A VLAN request includes a concrete downstream-device requirement, topology, or deployed scenario.
- LuCI configuration or direct SSH commands fail, report errors, or appear buggy when the requested outcome cannot reasonably be completed through the supported GUI.
- Complex business-customer issues involving many devices, deployment context, or advanced investigation; simple business questions remain with Technical Service.
- A likely firmware regression, cross-device defect, or issue that remains after common troubleshooting.
- Technical diagnosis requests with sufficient evidence, even when they also mention order context.

Example from source doc:

- OpenWrt pull-request status question; source note says this is an advanced technical question.

## Merge

Flag as `Merge` when the triage pool contains duplicate Tickets or explicit continuation references.

Keep history lookup narrow: trigger it for a direct named salutation such as `Dear Ann`, a subject beginning with `Re:`, explicit continuation wording, or multiple Tickets from the same requester within 30 minutes whose subjects are both empty or normalize to the same text. Fragment body length is not a condition. Inspect at most 10 recent Tickets for that requester and compare metadata only; do not fetch old Ticket bodies or conversations.

For a fragment cluster, recommend the earliest created Ticket as the Merge target and preserve that target's existing Group and Agent. The Merge action itself remains manual.

Signals:

- Consecutive Tickets from the same requester with the same question.
- Subject starts with `Re:` and includes an existing Ticket ID.
- Body refers to a previous Ticket, reply, or same unresolved issue.
- Body says `follow-up`, `previous quotation`, `previously quoted`, names a prior contact, or asks whether earlier price and terms remain valid.

Example from source doc:

- Two consecutive Tickets from the same sender with the same question; merge candidate.
- A small-batch quotation follow-up already handled by a CS or Shopify colleague: merge into the earlier Ticket and preserve its existing Group and Agent instead of creating a new Sales handoff.

## Sales

Route to `Sales` only for a clearly large-volume order, distribution/reseller cooperation, partnership, customization that standard products cannot satisfy, or a dedicated commercial project. Clarify the use case, requirements, and quantity before routing vague customization requests. Do not use Sales merely because a customer mentions 50 units or asks for pricing. If product fit or the exact model is still unclear, keep the Ticket with Technical Service first. If the request follows an earlier quotation, use Merge first.

Quantity guidance from the informal reference is a signal, not a rigid threshold:

- Around 50 units is normally small-batch work routed from Technical Service to CS under the newer confirmed rule.
- Around 100 units or more can indicate Sales, especially for enterprise or long-term cooperation.
- High-priced cellular products can justify Sales at quantities of several dozen.
- Low-priced products at roughly 100 to 200 units can go to CS for a direct ecommerce order without channel maintenance.

## Manual Review

Use `Manual Review` when the routing signal depends on information outside the current Ticket or when older guidance may be stale. A KOL or marketing cooperation request belongs here only when it explicitly targets GL.iNet with a concrete product, audience, campaign idea, or collaboration rationale. Details about the sender's own company alone are not enough; generic or reusable marketing pitches remain Spam.

## Confidence

- `high`: one bucket has clear rule signals and no conflict.
- `medium`: likely bucket, but the text is short or partially overlaps another bucket.
- `low`: no rule match, unclear order scale, missing product knowledge, or needs human judgment.

Return the suggested bucket, confidence, short reason, and the exact evidence phrase or subject fragment that triggered the suggestion. Do not write to Freshdesk.

## Output Format

Group results by routing destination. Create a separate Markdown table for every non-empty bucket, with Ticket, confidence, reason, and evidence columns. Put `CS`, `Sales`, `Merge`, and Tickets that stay with `Technical Service` in their own tables. Do not emit one mixed table containing multiple routing destinations.

Use this order for the Technical Service view: `CS`, `Spam`, `Sales`, `Technical Support`, `Merge`, `Manual Review`, then retained `Technical Service`. Use this order for the Customer Service view: `Technical Service`, `Sales`, `Spam`, `Merge`, `Manual Review`, then retained `Customer Service`. Unattended DingTalk cards contain only these non-empty suggestion tables; they do not ask for assignment confirmation.

Render every current or referenced Ticket ID by copying the API output field `ticket_link_markdown` verbatim. Its visible text must remain the numeric ID; never fetch or substitute a webpage title such as `Loading...`. In Merge rows, use the same field for both the new Ticket ID and the recommended target Ticket ID.
