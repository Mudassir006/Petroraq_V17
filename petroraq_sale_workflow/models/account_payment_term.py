from odoo import fields, models

from odoo.tools.float_utils import float_round, float_compare



class AccountPaymentTerm(models.Model):
    _inherit = "account.payment.term"

    petroraq_selectable = fields.Boolean(
        string="Selectable for Petroraq Sales",
        default=False,
    )


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _dp_paid_amount(self):
        """Total DP untaxed that was posted (positive DP invoices only)."""
        self.ensure_one()
        dp_line = self._dp_sale_line()
        if not dp_line:
            return 0.0

        amls = dp_line.invoice_lines.filtered(
            lambda l: l.move_id.state == "posted"
                      and l.move_id.move_type == "out_invoice"
                      and (l.price_subtotal or 0.0) > 0.0
        )
        return sum(amls.mapped("price_subtotal")) or 0.0

    def _dp_remaining_amount(self):
        """Remaining DP untaxed based on posted moves linked to dp SO line."""
        self.ensure_one()
        dp_line = self._dp_sale_line()
        if not dp_line:
            return 0.0

        amls = dp_line.invoice_lines.filtered(
            lambda l: l.move_id.state == "posted"
                      and l.move_id.move_type == "out_invoice"
        )

        paid = sum(l.price_subtotal for l in amls if (l.price_subtotal or 0.0) > 0.0)
        deducted = sum(abs(l.price_subtotal) for l in amls if (l.price_subtotal or 0.0) < 0.0)

        return max(0.0, paid - deducted)

    def _dp_sale_line(self):
        self.ensure_one()
        return self.order_line.filtered(lambda l: l.is_downpayment and not l.display_type)[:1]

    def _dp_deducted_qty(self):
        """
        How much of DP line (out of 1.0) has already been deducted in REGULAR invoices.
        We count only negative dp quantities from posted customer invoices.
        """
        self.ensure_one()
        dp_line = self._dp_sale_line()
        if not dp_line:
            return 0.0

        deducted = 0.0
        amls = dp_line.invoice_lines.filtered(
            lambda l: l.move_id.state == "posted"
                      and l.move_id.move_type == "out_invoice"
                      and (l.price_subtotal or 0.0) < 0  # only deduction lines
        )
        for aml in amls:
            deducted += abs(aml.quantity or 0.0)

        return max(0.0, min(1.0, float_round(deducted, precision_digits=6)))

    def _is_fully_delivered(self):
        """Final invoice if all stockable/consu lines are fully delivered."""
        self.ensure_one()
        lines = self.order_line.filtered(
            lambda l: not l.display_type and not l.is_downpayment and l.product_id
        ).filtered(lambda l: l.product_id.type in ("product", "consu"))

        if not lines:
            return False

        for l in lines:
            if float_compare(
                    l.qty_delivered, l.product_uom_qty,
                    precision_rounding=l.product_uom.rounding
            ) < 0:
                return False
        return True

    def _prepare_dp_deduction_line_vals(self, invoice, dp_line, amount):
        self.ensure_one()
        currency = self.currency_id or self.company_id.currency_id
        if currency.is_zero(amount):
            return {}

        product = dp_line.product_id
        accounts = product._get_product_accounts() if product else {}
        account = accounts.get("income") or product.property_account_income_id
        if not account and product:
            account = product.categ_id.property_account_income_categ_id
        if not account:
            account = self.company_id.account_default_sale_account_id

        taxes = dp_line.tax_id
        if not account:
            return {}

        return {
            "move_id": invoice.id,
            "name": dp_line.name or "Down Payment Deduction",
            "quantity": 1.0,
            "price_unit": -amount,
            "account_id": account.id,
            "tax_ids": [(6, 0, taxes.ids)] if taxes else False,
            "sale_line_ids": [(6, 0, dp_line.ids)],
        }

    def _get_invoice_order_base(self, invoice):
        self.ensure_one()

        base_lines = invoice.invoice_line_ids.filtered(
            lambda l: not l.display_type
                      and not l.is_downpayment
                      and self in l.sale_line_ids.order_id
        )
        return sum(base_lines.mapped("price_subtotal"))

    def _create_invoices(self, grouped=False, final=False, date=None):
        invoices = super()._create_invoices(grouped=grouped, final=final, date=date)

        for order in self:
            dp_percent = order.dp_percent or 0.0
            if not dp_percent:
                continue

            dp_line = order._dp_sale_line()
            if not dp_line:
                continue

            dp_paid = order._dp_paid_amount()
            if not dp_paid:
                continue  # no posted DP invoice yet

            remaining_dp_amount = order._dp_remaining_amount()
            currency = order.currency_id or order.company_id.currency_id
            if currency.is_zero(remaining_dp_amount):
                continue

            order_invoices = invoices.filtered(
                lambda move: move.move_type == "out_invoice"
                and order in move.invoice_line_ids.sale_line_ids.order_id
            )
            for invoice in order_invoices:
                existing = invoice.invoice_line_ids.filtered(
                    lambda l: dp_line in l.sale_line_ids
                    and not l.display_type
                    and (l.price_subtotal or 0.0) < 0.0
                )
                if existing:
                    continue

                invoice_base = order._get_invoice_order_base(invoice)
                if invoice_base <= 0:
                    continue

                target_amount = min(remaining_dp_amount, invoice_base * dp_percent)
                if currency.is_zero(target_amount) or target_amount <= 0:
                    continue

                vals = order._prepare_dp_deduction_line_vals(invoice, dp_line, target_amount)
                if not vals:
                    continue

                self.env["account.move.line"].create(vals)
                remaining_dp_amount -= target_amount

        return invoices
