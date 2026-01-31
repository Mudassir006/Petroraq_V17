from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    retention_account_id = fields.Many2one(
        "account.account",
        string="Retention Account",
        help="Account used for retention withholding lines on progress invoices.",
    )


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    retention_account_id = fields.Many2one(
        related="company_id.retention_account_id",
        string="Retention Account",
        readonly=False,
    )
