from odoo import api, fields, models, _


class AccountMove(models.Model):
    _inherit = "account.move"

    # -------------------------------------------------------------------------
    # RELATIONS
    # -------------------------------------------------------------------------

    sale_order_id = fields.Many2one(
        "sale.order",
        string="Sale Order",
        compute="_compute_sale_order_id",
        store=True,
        readonly=True,
    )

    retention_id = fields.Many2one(
        "pr.retention",
        string="Retention",
        ondelete="set null",
        copy=False,
    )

    # -------------------------------------------------------------------------
    # RETENTION FIELDS
    # -------------------------------------------------------------------------

    retention_amount = fields.Monetary(
        string="Retention Amount",
        currency_field="currency_id",
        compute="_compute_retention_amount",
        store=True,
    )

    # -------------------------------------------------------------------------
    # COMPUTES
    # -------------------------------------------------------------------------

    @api.depends("invoice_line_ids.sale_line_ids.order_id")
    def _compute_sale_order_id(self):
        for move in self:
            sale_orders = move.invoice_line_ids.sale_line_ids.order_id
            move.sale_order_id = sale_orders[:1].id if sale_orders else False

    @api.depends("invoice_line_ids.is_retention_line", "invoice_line_ids.price_subtotal")
    def _compute_retention_amount(self):
        for move in self:
            retention_lines = move.invoice_line_ids.filtered(lambda l: l.is_retention_line)
            move.retention_amount = sum(abs(line.price_subtotal) for line in retention_lines)

    # -------------------------------------------------------------------------
    # RETENTION RECORD HANDLING
    # -------------------------------------------------------------------------

    def _get_retention_sale_order(self):
        self.ensure_one()
        sale_orders = self.invoice_line_ids.sale_line_ids.order_id
        return sale_orders[:1] if sale_orders else False

    def _get_retention_base_amount(self):
        self.ensure_one()
        # Retention base is the untaxed subtotal of invoice lines excluding retention itself.
        base_lines = self.invoice_line_ids.filtered(
            lambda l: not l.display_type and not l.is_retention_line
        )
        return sum(base_lines.mapped("price_subtotal"))

    def _get_retention_account_id(self):
        self.ensure_one()
        if self.company_id.retention_account_id:
            return self.company_id.retention_account_id
        candidate = self.invoice_line_ids.filtered(
            lambda l: not l.display_type and not l.is_retention_line and l.account_id
        )[:1]
        return candidate.account_id if candidate else False

    def _ensure_retention_line(self, sale_order):
        self.ensure_one()
        if self.move_type != "out_invoice":
            return

        if not sale_order or not sale_order.retention_percent:
            return

        if self.invoice_line_ids.filtered("is_retention_line"):
            return

        base_amount = self._get_retention_base_amount()
        currency = self.currency_id or self.company_id.currency_id
        retention_amount = currency.round(
            (base_amount or 0.0) * (sale_order.retention_percent or 0.0) / 100.0
        )
        if currency.is_zero(retention_amount):
            return

        account_id = self._get_retention_account_id()
        if not account_id:
            return

        self.write(
            {
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": _("Retention (%s%%)") % (sale_order.retention_percent or 0.0),
                            "quantity": 1.0,
                            "price_unit": -retention_amount,
                            "account_id": account_id.id,
                            "tax_ids": [(6, 0, [])],
                            "is_retention_line": True,
                        },
                    )
                ]
            }
        )
