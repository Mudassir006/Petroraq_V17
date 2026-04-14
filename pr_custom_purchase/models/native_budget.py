from odoo import fields, models


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
