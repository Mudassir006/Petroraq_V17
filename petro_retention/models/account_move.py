from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    retention_deduct_amount = fields.Monetary(
        string="Retention Deduction",
        currency_field="currency_id",
        compute="_compute_retention_deduct_amount",
        store=True,
        readonly=True,
        copy=False,
    )

    @api.depends(
        'invoice_line_ids.price_subtotal',
        'invoice_line_ids.is_downpayment',
        'invoice_line_ids.sale_line_ids.order_id.retention_percent',
    )
    def _compute_retention_deduct_amount(self):
        for move in self:
            if move.move_type != 'out_invoice':
                move.retention_deduct_amount = 0.0
                continue

            sale_orders = move.invoice_line_ids.sale_line_ids.order_id
            sale_orders = sale_orders.filtered(lambda so: so.retention_percent)
            if not sale_orders:
                move.retention_deduct_amount = 0.0
                continue

            so = sale_orders[0]

            # Exclude down payment lines from the retention base.
            valid_lines = move.invoice_line_ids.filtered(
                lambda l: not l.display_type and not l.is_downpayment
            )

            base = sum(valid_lines.mapped('price_subtotal'))

            move.retention_deduct_amount = move.currency_id.round(
                base * (so.retention_percent / 100.0)
            )
