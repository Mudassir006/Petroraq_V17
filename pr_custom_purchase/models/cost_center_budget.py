from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class AccountAnalyticAccount(models.Model):
    _inherit = "account.analytic.account"

    budget_type = fields.Selection(
        [("opex", "Opex"), ("capex", "Capex")],
        string="Budget Type",
    )
    budget_code = fields.Char(string="Budget Code")
    budget_allowance = fields.Float(string="Budget Allowance")
    budget_spent = fields.Float(string="Budget Spent", compute="_compute_budget_metrics", store=False)
    budget_left = fields.Float(string="Budget Left", compute="_compute_budget_metrics", store=False)

    @api.depends("budget_allowance", "budget_code", "budget_type")
    def _compute_budget_metrics(self):
        PurchaseOrder = self.env["purchase.order"].sudo()
        for rec in self:
            spent = 0.0
            if rec.budget_code and rec.budget_type:
                pos = PurchaseOrder.search([
                    ("budget_type", "=", rec.budget_type),
                    ("budget_code", "=", rec.budget_code),
                    ("state", "in", ["purchase", "done"]),
                ])
                for po in pos:
                    spent += po.grand_total if "grand_total" in po._fields else po.amount_total

            rec.budget_spent = spent
            rec.budget_left = (rec.budget_allowance or 0.0) - spent

    @api.model
    def get_cost_center_budget(self, budget_type, budget_code):
        if not budget_type or not budget_code:
            return False

        return self.sudo().search([
            ("budget_type", "=", budget_type),
            ("budget_code", "=", budget_code),
        ], limit=1)

    @api.model
    def validate_budget_or_raise(self, budget_type, budget_code, required_amount=0.0):
        rec = self.get_cost_center_budget(budget_type, budget_code)
        if not rec:
            raise ValidationError(_("No cost center found for the selected budget type/code."))

        if rec.budget_left <= 0:
            raise ValidationError(_("No budget left for cost center %s.") % (rec.budget_code or rec.display_name))

        if required_amount and rec.budget_left < required_amount:
            raise ValidationError(
                _("Insufficient budget for cost center %s. Remaining: %s, Required: %s")
                % (rec.budget_code or rec.display_name, rec.budget_left, required_amount)
            )

        return rec

