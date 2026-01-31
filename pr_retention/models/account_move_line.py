from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    is_retention_line = fields.Boolean(string="Retention Line", default=False)
