from odoo import api, fields, models, _
from odoo.exceptions import UserError


class RetentionReleaseWizard(models.TransientModel):
    _name = "pr.retention.release.wizard"
    _description = "Release Retention"

    sale_order_id = fields.Many2one(
        "sale.order",
        string="Sale Order",
        required=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="sale_order_id.currency_id",
        readonly=True,
    )
    amount = fields.Monetary(
        string="Release Amount",
        currency_field="currency_id",
        required=True,
    )
    note = fields.Char(string="Note")

    @api.constrains("amount")
    def _check_amount(self):
        for wizard in self:
            if wizard.amount <= 0:
                raise UserError(_("Release amount must be greater than zero."))

    def action_release(self):
        self.ensure_one()
        order = self.sale_order_id
        currency = order.currency_id or order.company_id.currency_id
        remaining = currency.round(order.retention_remaining or 0.0)
        if currency.is_zero(remaining):
            raise UserError(_("No remaining retention to release."))
        if self.amount > remaining:
            raise UserError(_("Release amount exceeds remaining retention."))

        account = order.company_id.retention_account_id
        if not account:
            candidate = order.order_line.filtered(
                lambda l: not l.display_type and not l.is_downpayment
            )[:1]
            account = candidate._get_invoice_line_account_id() if candidate else False
        if not account:
            raise UserError(_("Please configure a retention account before releasing retention."))

        invoice_vals = order._prepare_invoice()
        invoice_vals["invoice_line_ids"] = [
            (
                0,
                0,
                {
                    "name": self.note or _("Retention Release"),
                    "quantity": 1.0,
                    "price_unit": self.amount,
                    "account_id": account.id,
                    "tax_ids": [(6, 0, [])],
                },
            )
        ]

        move = self.env["account.move"].create(invoice_vals)
        return {
            "type": "ir.actions.act_window",
            "name": _("Retention Release Invoice"),
            "res_model": "account.move",
            "res_id": move.id,
            "view_mode": "form",
            "target": "current",
        }
