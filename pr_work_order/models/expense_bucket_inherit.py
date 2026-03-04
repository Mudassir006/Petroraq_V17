from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ExpenseBucket(models.Model):
    _inherit = "pr.expense.bucket"

    work_order_id = fields.Many2one("pr.work.order", string="Work Order", tracking=True)

    @api.onchange("scope")
    def _onchange_scope_work_order(self):
        for rec in self:
            if rec.scope == "department":
                rec.work_order_id = False
            if rec.scope == "project":
                rec.expense_type = "capex"

    @api.onchange("work_order_id")
    def _onchange_work_order_id(self):
        for rec in self:
            if rec.scope != "project" or not rec.work_order_id:
                continue

            rec.expense_type = "capex"
            allowed_cost_center_ids = rec.work_order_id.cost_center_ids.mapped("analytic_account_id").ids
            rec.line_ids = rec.line_ids.filtered(lambda line: line.cost_center_id.id in allowed_cost_center_ids)

    @api.constrains("scope", "work_order_id", "expense_type", "line_ids", "line_ids.cost_center_id")
    def _check_scope_target_work_order(self):
        for rec in self:
            if rec.scope == "project" and not rec.work_order_id:
                raise ValidationError(_("Work Order is required when scope is Project."))

            if rec.scope == "project" and rec.expense_type != "capex":
                raise ValidationError(_("Only Capex expense type is allowed when scope is Project."))

            if rec.scope != "project" or not rec.work_order_id:
                continue

            allowed_cost_center_ids = set(rec.work_order_id.cost_center_ids.mapped("analytic_account_id").ids)
            invalid_lines = rec.line_ids.filtered(lambda line: line.cost_center_id.id not in allowed_cost_center_ids)
            if invalid_lines:
                raise ValidationError(_(
                    "Selected cost centers must belong to the chosen Work Order."
                ))

    def write(self, vals):
        if "work_order_id" in vals:
            for rec in self:
                if rec.state == "approved":
                    raise ValidationError(_("Approved expense bucket cannot be edited."))
        return super().write(vals)
