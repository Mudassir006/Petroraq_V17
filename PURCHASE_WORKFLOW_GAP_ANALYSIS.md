# Purchase Workflow Gap Analysis (against provided Procurement Process Flow Chart)

## Scope reviewed
- `custom_user_portal` purchase requisition, quotation, and purchase order workflow.
- `custom_pr_system` PR/GRN/SES and related approvals/notifications.
- `petroraq_sale_workflow` sale approval flow used as a reference baseline for staged approvals.

## 1) Completed (implemented and aligns with the diagram)

1. **PR creation and initial capture exist (portal + backend).**
   - Portal can create PRs and PR lines.
   - PR model has requester, department, supervisor, budget, notes, line items, totals.

2. **Budget check exists before PO/PR progression.**
   - Portal endpoint validates project + `budget_left`.
   - Quotation → PO creation blocks when budget is insufficient.

3. **PR approval state exists (`pending / approved / rejected`) with approver activity notifications.**
   - PR write syncs approval with related `custom.pr` and notifies procurement admins.

4. **RFQ/PO generation from PR exists.**
   - Normal PR can create RFQ.
   - Cash PR can create PO directly.

5. **PO staged approvals by amount thresholds exist (matches the budget bands in the diagram).**
   - Threshold logic implemented for: `<=10k`, `<=100k`, `<=500k`, `>500k`.
   - Confirm button visibility depends on required approvals by threshold.

6. **GRN/SES creation from approved PO exists (material/service split).**
   - GRN and/or SES records are generated from custom PO lines.

7. **GRN/SES has review + approval stages with role-based buttons.**
   - `pending -> reviewed -> approved` with QC and inventory admin actions.

## 2) Incorrect / inconsistent implementation

1. **GRN/SES report print check uses wrong field (`state`) instead of `stage`/`is_approved`.**
   - `print_grn_ses_report()` checks `rec.state` even though model defines `stage` and `is_approved`.

2. **Notification target group is missing in security data.**
   - Code references `custom_pr_system.inventory_approver`, but this group is commented out in security XML.

3. **PO status back-link on cash PR is misleading.**
   - `action_create_purchase_order()` sets PR status to `rfq` after creating and confirming a PO.

4. **Potentially unsafe duplication/typo in PR sync writes.**
   - Duplicate keys in dict literals (`{"approval": ..., "approval": ...}`) indicate copy/paste issue.

5. **`supervisor_partner_id` typed as `Char` while used as integer IDs in multiple places.**
   - Causes repeated int conversion logic and fragile error paths.

## 3) Missing compared to the diagram

1. **No explicit “department manager approval” stage as a separate gate before PR approval chain.**
   - Current logic uses generic PR approver/supervisor and not an explicit department-manager step.

2. **No explicit “PO not approved -> notify with comments -> revise -> resubmit loop” for each threshold stage.**
   - There is reject capability, but no structured revision loop/state machine with mandatory comments per rejection step.

3. **No explicit procurement “follow-up” stage/state.**
   - Activities exist, but there is no dedicated workflow state matching the chart’s follow-up block.

4. **Accounts invoice/payment path is not modeled in this custom purchase workflow.**
   - Diagram shows supplier invoice to accounts/payment, but module flow stops at PO + GRN/SES approval (no explicit custom account-stage orchestration).

5. **No warehouse issue/escalation loop from GRN approval decision into “relevant department” with tracked closure state.**
   - There is rejection/cancel logic, but not a dedicated issue lifecycle matching the flow chart’s “Issue -> Relevant Department -> SES/Approval” loop.

## 4) Needs to be done (recommended backlog)

1. **Fix hard bugs first**
   - Replace GRN report check with `if not rec.is_approved` or `rec.stage != 'approved'`.
   - Re-introduce/define `inventory_approver` group or change notification target to an existing group.

2. **Normalize workflow data model**
   - Change `supervisor_partner_id` to `Many2one('res.partner')`.
   - Add explicit PR/PO workflow states for diagram milestones (`dept_manager_review`, `follow_up`, `issues`, `closed`).

3. **Implement rejection/revision loop properly**
   - Add structured transitions: `pending_approval -> rejected_with_comments -> revised -> resubmitted`.
   - Enforce rejection reason/comments at every rejection action.

4. **Align PR status semantics**
   - Add statuses like `pr`, `rfq`, `po`, `completed` and set them consistently (especially cash PR flow).

5. **Add accounts + warehouse lifecycle integration points**
   - Add explicit activities/states for warehouse issue handling and accounts invoice/payment acknowledgment.
   - Optional: link vendor bill state to PO/GRN closure criteria.

6. **Harden server-side authorization**
   - In `action_approve`/`action_reject`, validate user group server-side (not only via button visibility).

## 5) Reference from sale workflow (what purchase can emulate)

- Sale workflow uses a **clear, explicit staged state machine** (`draft -> to_manager -> to_md -> approved/rejected`) and blocks confirmation until final approval.
- Purchase flow already has amount-based multi-stage approvals, but should add equivalent explicit transition rigor and rejection-cycle semantics for parity.
