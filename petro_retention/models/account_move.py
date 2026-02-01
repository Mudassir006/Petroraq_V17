from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    retention_deduct_amount = fields.Monetary(
        string="Retention Deduction",
        currency_field="currency_id",
        readonly=True,
        copy=False,
        help="Retention amount withheld from this invoice (tracking only).",
    )
