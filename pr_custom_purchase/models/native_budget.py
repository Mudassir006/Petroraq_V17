from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CrossoveredBudget(models.Model):
    _inherit = "crossovered.budget"

    expense_type = fields.Selection(
        [("opex", "Opex"), ("capex", "Capex")],
        string="Expense Type",
    )
    scope = fields.Selection(
        [("department", "Department"), ("project", "Project"), ("trading", "Trading")],
        string="Applies To",
    )
    sale_order_id = fields.Many2one("sale.order", string="Sale Order")
    work_order_id = fields.Many2one("pr.work.order", string="Work Order")
    source_budget_limit = fields.Float(string="Source Budget Limit")
    po_reference = fields.Char(string="PO Reference")
    approval_state = fields.Selection(
        [
            ("draft", "Draft"),
            ("pm_approval", "Pending Project Manager"),
            ("accounts_approval", "Pending Accounts"),
            ("md_approval", "Pending Managing Director"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        string="Approval Stage",
        default="draft",
        tracking=True,
    )
    can_pm_approve = fields.Boolean(compute="_compute_role_flags")
    can_accounts_approve = fields.Boolean(compute="_compute_role_flags")
    can_md_approve = fields.Boolean(compute="_compute_role_flags")

    @api.depends_context("uid")
    def _compute_role_flags(self):
        user = self.env.user
        is_pm = user.has_group("pr_custom_purchase.project_manager")
        is_accounts = user.has_group("account.group_account_manager") or user.has_group("account.group_account_user")
        is_md = user.has_group("pr_custom_purchase.managing_director")
        for rec in self:
            rec.can_pm_approve = is_pm
            rec.can_accounts_approve = is_accounts
            rec.can_md_approve = is_md

    def action_confirm(self):
        res = super().action_confirm()
        for rec in self:
            if rec.state == "confirm" and rec.approval_state == "draft":
                rec.approval_state = "pm_approval"
        return res

    def action_pm_approve(self):
        for rec in self:
            if rec.state != "confirm" or rec.approval_state != "pm_approval":
                continue
            if not rec.can_pm_approve:
                raise UserError(_("Only Project Manager can approve at this stage."))
            rec.approval_state = "accounts_approval"

    def action_accounts_approve(self):
        for rec in self:
            if rec.state != "confirm" or rec.approval_state != "accounts_approval":
                continue
            if not rec.can_accounts_approve:
                raise UserError(_("Only Accounts can approve at this stage."))
            rec.approval_state = "md_approval"

    def action_budget_validate(self):
        for rec in self:
            if rec.state == "confirm" and rec.approval_state != "md_approval":
                raise UserError(_("Budget requires PM, Accounts, and MD approvals before validation."))
        res = super().action_budget_validate()
        for rec in self:
            if rec.state in ("validate", "done"):
                rec.approval_state = "approved"
        return res

    def write(self, vals):
        if vals.get("state") == "draft" and "approval_state" not in vals:
            vals["approval_state"] = "draft"
        return super().write(vals)
