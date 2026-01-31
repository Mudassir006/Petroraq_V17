from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    retention_percent = fields.Float(string="Retention (%)", digits=(16, 2), default=0.0)
    retention_total = fields.Monetary(
        string="Retention Total",
        currency_field="currency_id",
        compute="_compute_retention_totals",
        store=True,
    )
    retention_withheld_total = fields.Monetary(
        string="Retention Withheld",
        currency_field="currency_id",
        compute="_compute_retention_totals",
        store=True,
    )
    retention_remaining = fields.Monetary(
        string="Retention Remaining",
        currency_field="currency_id",
        compute="_compute_retention_totals",
        store=True,
    )

    @api.depends(
        "amount_untaxed",
        "retention_percent",
        "invoice_ids.state",
        "invoice_ids.move_type",
        "invoice_ids.invoice_line_ids.is_retention_line",
        "invoice_ids.invoice_line_ids.price_subtotal",
    )
    def _compute_retention_totals(self):
        for order in self:
            currency = order.currency_id or order.company_id.currency_id
            retention_total = currency.round(
                (order.amount_untaxed or 0.0) * (order.retention_percent or 0.0) / 100.0
            )
            retention_lines = order.invoice_ids.filtered(
                lambda m: m.state == "posted" and m.move_type == "out_invoice"
            ).invoice_line_ids.filtered(lambda l: l.is_retention_line)
            withheld_total = sum(abs(line.price_subtotal) for line in retention_lines)
            withheld_total = currency.round(withheld_total)
            order.retention_total = retention_total
            order.retention_withheld_total = withheld_total
            order.retention_remaining = currency.round(retention_total - withheld_total)

    @api.constrains("retention_percent")
    def _check_retention_inputs(self):
        for order in self:
            if order.retention_percent < 0 or order.retention_percent > 100:
                raise ValidationError(_("Retention percentage must be between 0 and 100."))

    def _create_invoices(self, grouped=False, final=False, date=None):
        moves = super()._create_invoices(grouped=grouped, final=final, date=date)
        for move in moves:
            sale_order = move._get_retention_sale_order()
            if not sale_order or not sale_order.retention_percent:
                continue
            move._ensure_retention_line(sale_order)
        return moves

    def action_release_retention(self):
        self.ensure_one()
        currency = self.currency_id or self.company_id.currency_id
        remaining = currency.round(self.retention_remaining or 0.0)
        if currency.is_zero(remaining):
            raise UserError(_("No remaining retention to release."))

        return {
            "type": "ir.actions.act_window",
            "res_model": "pr.retention.release.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_sale_order_id": self.id,
                "default_amount": remaining,
            },
        }
