from odoo import fields, models


class AccountPaymentTerm(models.Model):
    _inherit = "account.payment.term"

    petroraq_selectable = fields.Boolean(
        string="Selectable for Petroraq Sales",
        default=False,
    )
