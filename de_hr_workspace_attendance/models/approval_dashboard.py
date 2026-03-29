from odoo import _, models


class HrApprovalDashboardService(models.AbstractModel):
    _name = "de.hr.approval.dashboard.service"
    _description = "HR Approval Dashboard Service"

    def _shortage_approval_domain(self):
        return [
            "|",
            "|",
            ("employee_manager_id.user_id", "=", self.env.user.id),
            ("hr_supervisor_ids", "in", self.env.user.id),
            ("hr_manager_ids", "in", self.env.user.id),
            ("approval_state", "in", ["draft", "manager_approve", "hr_supervisor"]),
        ]

    def _pr_supervisor_domain(self):
        return [
            ("approval", "=", "pending"),
            ("requested_user_id.supervisor_user_id", "=", self.env.user.id),
        ]

    def _po_approval_domain(self):
        user = self.env.user
        if user.has_group("pr_custom_purchase.project_engineer"):
            return [("state", "=", "pending"), ("subtotal", "<=", 10000), ("pe_approved", "=", False)]
        if user.has_group("pr_custom_purchase.project_manager"):
            return [("state", "=", "pending"), ("subtotal", ">", 10000), ("subtotal", "<=", 100000), ("pe_approved", "=", True), ("pm_approved", "=", False)]
        if user.has_group("pr_custom_purchase.operations_director"):
            return [("state", "=", "pending"), ("subtotal", ">", 100000), ("subtotal", "<=", 500000), ("pe_approved", "=", True), ("pm_approved", "=", True), ("od_approved", "=", False)]
        if user.has_group("pr_custom_purchase.managing_director"):
            return [("state", "=", "pending"), ("subtotal", ">", 500000), ("pe_approved", "=", True), ("pm_approved", "=", True), ("od_approved", "=", True), ("md_approved", "=", False)]
        return [("id", "=", 0)]

    def _expense_bucket_domain(self):
        user = self.env.user
        if user.has_group("pr_custom_purchase.managing_director"):
            return [("state", "=", "md_approval")]
        if user.has_group("account.group_account_manager") or user.has_group("account.group_account_user"):
            return [("state", "=", "accounts_approval")]
        if user.has_group("pr_custom_purchase.project_manager"):
            return [("state", "=", "pm_approval")]
        return [("state", "=", "pm_approval"), ("department_id.manager_id.user_id", "=", user.id)]

    def _budget_increase_domain(self):
        user = self.env.user
        if user.has_group("pr_custom_purchase.managing_director"):
            return [("state", "=", "md_approval")]
        if user.has_group("account.group_account_manager") or user.has_group("account.group_account_user"):
            return [("state", "=", "accounts_approval")]
        if user.has_group("pr_custom_purchase.project_manager"):
            return [("state", "=", "pm_approval")]
        return [("id", "=", 0)]

    def _build_tile(self, key, name, model, domain, action_xmlid, icon, tone):
        count = self.env[model].search_count(domain)
        return {
            "key": key,
            "name": name,
            "count": count,
            "icon": icon,
            "tone": tone,
            "action_xmlid": action_xmlid,
            "domain": domain,
        }

    def get_tiles(self):
        return [
            self._build_tile(
                key="shortage",
                name=_("Shortage Requests"),
                model="pr.hr.shortage.request",
                domain=self._shortage_approval_domain(),
                action_xmlid="de_hr_workspace_attendance.action_my_shortage_request_approvals",
                icon="fa-clock-o",
                tone="warning",
            ),
            self._build_tile(
                key="purchase_requisition",
                name=_("PR Supervisor Approval"),
                model="purchase.requisition",
                domain=self._pr_supervisor_domain(),
                action_xmlid="pr_custom_purchase.action_purchase_requisition_list",
                icon="fa-list-alt",
                tone="info",
            ),
            self._build_tile(
                key="purchase_order",
                name=_("Purchase Orders"),
                model="purchase.order",
                domain=self._po_approval_domain(),
                action_xmlid="purchase.purchase_form_action",
                icon="fa-shopping-cart",
                tone="primary",
            ),
            self._build_tile(
                key="expense_bucket",
                name=_("Expense Buckets"),
                model="pr.expense.bucket",
                domain=self._expense_bucket_domain(),
                action_xmlid="pr_custom_purchase.action_pr_expense_bucket",
                icon="fa-briefcase",
                tone="success",
            ),
            self._build_tile(
                key="budget_increase",
                name=_("Budget Increase"),
                model="budget.increase.request",
                domain=self._budget_increase_domain(),
                action_xmlid="pr_custom_purchase.action_budget_increase_request",
                icon="fa-line-chart",
                tone="danger",
            ),
        ]

    def open_tile(self, action_xmlid, domain=None):
        action = self.env["ir.actions.actions"]._for_xml_id(action_xmlid)
        action["domain"] = domain or []
        return action
