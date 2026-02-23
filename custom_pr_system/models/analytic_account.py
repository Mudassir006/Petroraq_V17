from odoo import fields, models


class AccountAnalyticAccount(models.Model):
    _inherit = 'account.analytic.account'

    budget_type = fields.Selection(
        [("opex", "Opex"), ("capex", "Capex")],
        string="Budget Type",
        help="Default budget type used by Purchase Requisitions for this cost center.",
    )
