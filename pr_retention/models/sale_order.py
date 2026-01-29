from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    retention_apply = fields.Boolean(string="Apply Retention", default=False)
    retention_type = fields.Selection(
        [("percent", "Percentage"), ("amount", "Fixed Amount")],
        string="Retention Type",
        default="percent",
    )
    retention_percent = fields.Float(string="Retention (%)", digits=(16, 2))
    retention_fixed_amount = fields.Monetary(
        string="Retention Fixed Amount",
        currency_field="currency_id",
    )
    retention_amount = fields.Monetary(
        string="Retention Amount",
        currency_field="currency_id",
        compute="_compute_retention_amount",
        store=True,
    )

    @api.depends("retention_apply", "retention_type", "retention_percent", "retention_fixed_amount", "amount_total")
    def _compute_retention_amount(self):
        for order in self:
            if not order.retention_apply:
                order.retention_amount = 0.0
            elif order.retention_type == "percent":
                order.retention_amount = order.amount_total * (order.retention_percent or 0.0) / 100.0
            else:
                order.retention_amount = order.retention_fixed_amount or 0.0

    def _prepare_invoice(self):
        invoice_vals = super()._prepare_invoice()
        invoice_vals.update(
            {
                "retention_apply": self.retention_apply,
                "retention_type": self.retention_type,
                "retention_percent": self.retention_percent,
                "retention_fixed_amount": self.retention_fixed_amount,
            }
        )
        return invoice_vals

    @api.constrains("retention_percent", "retention_fixed_amount")
    def _check_retention_inputs(self):
        for order in self:
            if order.retention_percent < 0 or order.retention_percent > 100:
                raise ValidationError(_("Retention percentage must be between 0 and 100."))
            if order.retention_fixed_amount < 0:
                raise ValidationError(_("Retention fixed amount cannot be negative."))
