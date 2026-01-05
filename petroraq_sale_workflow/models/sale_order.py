from copy import deepcopy

from odoo import api, fields, models, _
from odoo.exceptions import UserError, AccessError
from odoo.tools import format_amount, html_escape
from odoo.tools.float_utils import float_round, float_compare
from odoo.tools import frozendict
from odoo.fields import Command


class SaleOrder(models.Model):
    _inherit = "sale.order"
    _description = "Quotation"

    approval_state = fields.Selection([
        ("draft", "Draft"),
        ("to_manager", "Manager Approve"),
        ("to_md", "MD Approve"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ], default="draft", tracking=True, copy=False)

    dp_percent = fields.Float(
        string="Down Payment %",
        copy=False,
    )

    section_subtotal_summary = fields.Html(
        string="Section Subtotals",
        compute="_compute_section_subtotal_summary",
        sanitize=False,
        help="Displays a summary of section subtotals and their grand total."
    )
    inquiry_type = fields.Selection([('construction', 'Contracting'), ('trading', 'Trading')], string="Inquiry Type",
                                    default="trading", )

    overhead_percent = fields.Float(
        string="Over Head (%)",
        default=0.0,
        digits=(16, 2),
        help="Percentage applied on the total amount to cover overhead costs."
    )
    overhead_amount = fields.Monetary(
        string="Over Head Amount",
        compute="_compute_buffer_amounts",
        currency_field="currency_id",
        store=False,
        help="Calculated overhead amount based on the total amount."
    )
    risk_percent = fields.Float(
        string="Risk (%)",
        default=0.0,
        digits=(16, 2),
        help="Percentage applied on the total amount to cover risk."
    )
    risk_amount = fields.Monetary(
        string="Risk Amount",
        compute="_compute_buffer_amounts",
        currency_field="currency_id",
        store=False,
        help="Calculated risk amount based on the total amount."
    )
    approval_comment = fields.Text("Approval Comment", tracking=True)

    buffer_total_amount = fields.Monetary(
        string="Computed Total Amount",
        compute="_compute_buffer_amounts",
        currency_field="currency_id",
        store=False,
        help="Total amount including overhead and risk percentages."
    )
    profit_percent = fields.Float(
        string="Profit (%)",
        default=0.0,
        digits=(16, 2),
        help="Percentage applied on the grand total to compute profit."
    )
    profit_amount = fields.Monetary(
        string="Profit Amount",
        compute="_compute_profit_amount",
        currency_field="currency_id",
        store=True,
        help="Calculated profit amount based on the grand total."
    )
    profit_grand_total = fields.Monetary(
        string="Great Grand Total",
        compute="_compute_profit_amount",
        currency_field="currency_id",
        store=True,
        help="Grand total including profit."
    )

    final_grand_total = fields.Monetary(
        string="Grand Taxed Total",
        compute="_compute_final_totals",
        currency_field="currency_id",
        store=True,
        help="Grand total including profit."
    )

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

    def _dp_deduction_account(self):
        self.ensure_one()
        dp_line = self._dp_sale_line()
        product = dp_line.product_id if dp_line else False
        account = False

        if product:
            accounts = product._get_product_accounts()
            account = accounts.get("income") or accounts.get("income_refund")

        account = account or getattr(self.company_id, "account_default_income_id", False)
        if not account:
            raise UserError(_("Please configure an income account for down payment deductions."))

        return account

    def _dp_invoice_base_for_move(self, move):
        self.ensure_one()
        base_lines = move.invoice_line_ids.filtered(
            lambda l: not l.display_type
            and l.sale_line_ids
            and self in l.sale_line_ids.order_id
            and not any(sl.is_downpayment for sl in l.sale_line_ids)
        )
        return sum(base_lines.mapped("price_subtotal")) or 0.0

    def _prepare_dp_deduction_line_vals(self, move, invoice_base):
        self.ensure_one()
        dp_percent = self.dp_percent or 0.0
        if not dp_percent:
            return False

        dp_paid = self._dp_paid_amount()
        if not dp_paid:
            return False

        remaining_dp_amount = self._dp_remaining_amount()
        currency = self.currency_id or self.company_id.currency_id
        if currency.is_zero(remaining_dp_amount):
            return False

        target_amount = min(remaining_dp_amount, invoice_base * dp_percent)
        target_amount = currency.round(target_amount)

        if currency.is_zero(target_amount):
            return False

        name = _("Down Payment Deduction")
        if len(move.invoice_line_ids.sale_line_ids.order_id) > 1:
            name = _("Down Payment Deduction (%s)") % self.name

        return {
            "name": name,
            "quantity": 1.0,
            "price_unit": -target_amount,
            "account_id": self._dp_deduction_account().id,
            "tax_ids": [Command.set([])],
        }

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

    def action_cancel(self):
        res = super(SaleOrder, self).action_cancel()
        for order in self:
            order.approval_state = "rejected"
        return res

    def _get_invoiceable_lines(self, final=False):
        return super()._get_invoiceable_lines(final=final)

    def _create_invoices(self, grouped=False, final=False, date=None):
        invoices = super()._create_invoices(grouped=grouped, final=final, date=date)

        for move in invoices:
            if move.move_type != "out_invoice":
                continue

            orders = move.invoice_line_ids.sale_line_ids.order_id
            for order in orders:
                dp_percent = order.dp_percent or 0.0
                if not dp_percent:
                    continue

                invoice_base = order._dp_invoice_base_for_move(move)
                if invoice_base <= 0:
                    continue

                vals = order._prepare_dp_deduction_line_vals(move, invoice_base)
                if not vals:
                    continue

                move.write({"invoice_line_ids": [Command.create(vals)]})

        return invoices

    @api.depends("order_line", "overhead_percent", "risk_percent", "profit_percent", "currency_id")
    def _compute_final_totals(self):
        for order in self:
            currency = order.currency_id or order.company_id.currency_id

            total = 0.0
            normal_lines = order.order_line.filtered(lambda l: not l.display_type and not l.is_downpayment)

            for line in normal_lines:
                qty = line.product_uom_qty or 0.0

                base = line.price_unit or 0.0
                oh = base * (order.overhead_percent or 0.0) / 100.0
                risk = base * (order.risk_percent or 0.0) / 100.0
                unit_or = base + oh + risk
                profit = unit_or * (order.profit_percent or 0.0) / 100.0
                final_unit = unit_or + profit

                # EXACTLY like QWeb:
                final_unit_r = currency.round(final_unit)
                line_total_r = currency.round(final_unit_r * qty)

                total += line_total_r

            vat_amt_r = currency.round(total * 0.15)
            order.final_grand_total = total + vat_amt_r

    def _costing_final_unit(self, base):
        """final_unit = base + oh + risk + profit(on unit_or)"""
        self.ensure_one()
        oh = base * (self.overhead_percent or 0.0) / 100.0
        risk = base * (self.risk_percent or 0.0) / 100.0
        unit_or = base + oh + risk
        profit = unit_or * (self.profit_percent or 0.0) / 100.0
        return unit_or + profit

    def _costing_total_no_vat(self):
        """Sum of rounded line totals: round(round(final_unit)*qty)."""
        self.ensure_one()
        currency = self.currency_id or self.company_id.currency_id

        total = 0.0
        lines = self.order_line.filtered(lambda l: not l.display_type and not l.is_downpayment)
        for l in lines:
            base = l.price_unit or 0.0
            qty = l.product_uom_qty or 0.0

            final_unit = self._costing_final_unit(base)
            final_unit_r = currency.round(final_unit)
            line_total_r = currency.round(final_unit_r * qty)

            total += line_total_r

        return total

    @api.depends("amount_total", "company_id")
    def _compute_require_two_step(self):
        for order in self:
            company = order.company_id
            amt_mgr = company.sale_mgr_approval_min_amount or 0.0
            amt_md = company.sale_md_approval_min_amount or 0.0
            order.require_two_step = order.amount_total >= max(amt_mgr, amt_md)

    show_reject_button = fields.Boolean(compute="_compute_show_reject_button")

    @api.model
    def translate_sale_name(self, name):
        if not name:
            return ""
        numerals_map = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
        return str(name).translate(numerals_map)

    @api.model
    def convert_phone_to_eastern_arabic_numerals(self, value):
        if not value:
            return ""
        numerals_map = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
        return str(value).translate(numerals_map)

    @api.depends_context("uid")
    @api.depends("approval_state")
    def _compute_show_reject_button(self):
        user = self.env.user

        for order in self:
            order.show_reject_button = (
                    (order.approval_state == "to_manager" and user.has_group(
                        "petroraq_sale_workflow.group_sale_approval_manager"))
                    or
                    (order.approval_state == "to_md" and user.has_group(
                        "petroraq_sale_workflow.group_sale_approval_md"))
            )

    def action_manager_approve(self):
        for order in self:
            if order.approval_state != "to_manager":
                raise UserError(_("This quotation is not awaiting manager approval."))

            order.approval_state = "to_md"
            order.locked = True

    def action_confirm_quotation(self):
        for order in self:
            if not order.order_line:
                raise UserError(_("Please add at least one line item to the quotation."))
        self.approval_state = "to_manager"
        self.state = "draft"
        self.approval_comment = False

    def action_md_approve(self):
        for order in self:
            if order.approval_state != "to_md":
                raise UserError(_("This quotation is not awaiting MD approval."))
            order.approval_state = "approved"

        return True

    def action_reject(self):
        for order in self:
            if order.approval_state not in ("to_manager", "to_md", "draft"):
                raise UserError(_("Only waiting approvals can be rejected."))
            order.approval_state = "rejected"
        return True

    def action_open_reject_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.order.reject.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_order_id": self.id,
            },
        }

    # @api.model_create_multi
    # def create(self, vals_list):
    #     orders = super().create(vals_list)
    #     auto_orders = orders.filtered(lambda o: o.approval_state == "draft")
    #     if auto_orders:
    #         # auto trigger approval request so process starts without manual action
    #         auto_orders.action_request_manager_approval()
    #     return orders

    def action_reset_to_draft(self):
        for order in self:
            if order.approval_state == "rejected":
                order.locked = False
                order.approval_state = "draft"

    @api.model
    def default_get(self, fields_list):
        """Set a sensible default payment term for new quotations (module-provided).
        Falls back to the regular default if the data record is not available.
        """
        defaults = super().default_get(fields_list)
        if "payment_term_id" not in defaults or not defaults.get("payment_term_id"):
            try:
                term = self.env.ref("petroraq_sale_workflow.payment_term_immediate")
                if term and term.id:
                    defaults["payment_term_id"] = term.id
            except ValueError:
                pass
        return defaults

    def action_quotation_send(self):
        for order in self:
            if order.approval_state != "approved":
                raise UserError(_("You can only send the quotation to the customer after final approval."))
        return super().action_quotation_send()

    def action_confirm(self):
        for order in self:
            if not order.order_line:
                raise UserError(_("Please add at least one line item to the quotation."))
            if order.approval_state != "approved":
                raise UserError(_("You cannot confirm the order before final approval."))

        locked_orders = self.filtered('locked')
        if locked_orders:
            locked_orders.action_unlock()

        try:
            res = super().action_confirm()
        finally:
            if locked_orders:
                locked_orders.action_lock()

        return res

    @api.depends("order_line", "overhead_percent", "risk_percent", "profit_percent", "currency_id")
    def _compute_buffer_amounts(self):
        for order in self:
            currency = order.currency_id or order.company_id.currency_id

            # (A) grand total WITHOUT VAT using same QWeb rounding
            grand_no_vat = order._costing_total_no_vat()

            # (B) compute buffer (base + OH + risk) also line-based & rounded
            base_total = 0.0
            oh_total = 0.0
            risk_total = 0.0

            lines = order.order_line.filtered(lambda l: not l.display_type and not l.is_downpayment)
            for l in lines:
                base = l.price_unit or 0.0
                qty = l.product_uom_qty or 0.0

                # base line: round(unit) then round(unit*qty)
                base_unit_r = currency.round(base)
                base_line_r = currency.round(base_unit_r * qty)
                base_total += base_line_r

                oh_unit_r = currency.round(base * (order.overhead_percent or 0.0) / 100.0)
                risk_unit_r = currency.round(base * (order.risk_percent or 0.0) / 100.0)

                oh_total += currency.round(oh_unit_r * qty)
                risk_total += currency.round(risk_unit_r * qty)

            buffer_total = base_total + oh_total + risk_total

            order.overhead_amount = oh_total
            order.risk_amount = risk_total
            order.buffer_total_amount = buffer_total

            # profit is the delta (rounded at currency precision)
            order.profit_grand_total = grand_no_vat
            order.profit_amount = currency.round(grand_no_vat - buffer_total)

    @api.depends(
        "buffer_total_amount",
        "amount_total",
        "amount_untaxed",
        "currency_id",
        "profit_percent",
    )
    def _compute_profit_amount(self):
        for order in self:
            currency = order.currency_id or order.company_id.currency_id

            base = (
                       order.buffer_total_amount
                       if order.buffer_total_amount is not False and order.buffer_total_amount is not None
                       else order.amount_untaxed
                   ) or 0.0

            profit_pct = order.profit_percent or 0.0

            profit_amount = base * profit_pct / 100.0
            grand_total = base + profit_amount

            if currency:
                profit_amount = currency.round(profit_amount)
                grand_total = currency.round(grand_total)

            order.profit_amount = profit_amount
            order.profit_grand_total = grand_total

    @api.depends(
        "amount_total",
        "currency_id",
        "overhead_percent",
        "risk_percent",
        "buffer_total_amount",
        "profit_percent",
        "profit_grand_total",
        "amount_untaxed",
    )
    def _compute_section_subtotal_summary(self):
        total_label = _("Total Amount")
        for order in self:
            currency = order.currency_id or order.company_id.currency_id
            total_value = order.profit_grand_total if order.profit_grand_total or order.profit_grand_total == 0.0 else order.buffer_total_amount or order.amount_untaxed
            if currency:
                total_display = format_amount(order.env, total_value or 0.0, currency)
            else:
                total_display = f"{(total_value or 0.0):.2f}"
            order.section_subtotal_summary = (
                "<div class='o_section_total_summary'>"
                f"<span class='o_section_total_label'>{html_escape(total_label)}</span>"
                f"<span class='o_section_total_value'>{html_escape(total_display)}</span>"
                "</div>"
            )

    @api.depends_context("lang")
    @api.depends("order_line.tax_id", "order_line.price_unit", "amount_total", "amount_untaxed", "currency_id")
    def _compute_tax_totals(self):
        super()._compute_tax_totals()
        for order in self:
            if not order.tax_totals:
                continue

            tax_totals = deepcopy(order.tax_totals)
            untaxed_label = _("Untaxed Amount")
            desired_label = _("Total Amount")
            removal_labels = {_("Tax 15%"), "Tax 15%"}

            # Rename the subtotal label in the widget output.
            for subtotal in tax_totals.get("subtotals", []):
                if subtotal.get("name") == untaxed_label:
                    subtotal["name"] = desired_label

            groups_by_subtotal = tax_totals.get("groups_by_subtotal") or {}
            for key, group_list in list(groups_by_subtotal.items()):
                filtered_groups = [
                    tax_group
                    for tax_group in group_list
                    if tax_group.get("tax_group_name") not in removal_labels
                ]
                groups_by_subtotal[key] = filtered_groups
                if key == untaxed_label:
                    groups_by_subtotal[desired_label] = filtered_groups

            subtotals_order = tax_totals.get("subtotals_order")
            if subtotals_order:
                tax_totals["subtotals_order"] = [
                    desired_label if name == untaxed_label else name
                    for name in subtotals_order
                ]

            order.tax_totals = tax_totals

    @api.constrains("payment_term_id")
    def _check_payment_term_selectable(self):
        for order in self:
            term = order.payment_term_id
            if not term:
                raise UserError(_("Please select a payment term before saving the quotation."))
            if not getattr(term, "petroraq_selectable", False):
                raise UserError(
                    _("The selected payment term is not allowed. Please choose one of the Petroraq payment terms."))


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    section_subtotal_amount = fields.Monetary(
        string="Section Subtotal",
        compute="_compute_section_subtotal_amount",
        store=False,
        currency_field="currency_id",
        help="Subtotal of the products within this section."
    )
    section_subtotal_display = fields.Html(
        string="Section Subtotal Display",
        compute="_compute_section_subtotal_amount",
        sanitize=False,
        help="Formatted subtotal snippet for section headers."
    )
    final_price_unit = fields.Float(
        string="Final Unit Price",
        compute="_compute_final_price_unit",
        store=True
    )

    @api.depends('price_unit', 'order_id.overhead_percent', 'order_id.risk_percent', 'order_id.profit_percent')
    def _compute_final_price_unit(self):
        for line in self:
            # skip sections/notes + down payments
            if line.display_type or getattr(line, "is_downpayment", False):
                line.final_price_unit = line.price_unit
                continue

            base = line.price_unit or 0.0
            overhead = base * (line.order_id.overhead_percent / 100.0)
            risk = base * (line.order_id.risk_percent / 100.0)
            unit_or = base + overhead + risk
            profit = unit_or * (line.order_id.profit_percent / 100.0)
            line.final_price_unit = unit_or + profit

    def _prepare_invoice_line(self, **optional_values):
        vals = super()._prepare_invoice_line(**optional_values)

        if not self.display_type and not self.is_downpayment:
            vals["price_unit"] = self.final_price_unit

        return vals

    @api.depends(
        "display_type",
        "price_subtotal",
        "sequence",
        "order_id.order_line.price_subtotal",
        "order_id.order_line.display_type",
        "order_id.order_line.sequence",
    )
    def _compute_section_subtotal_amount(self):
        label = _("Sub Total")
        for line in self:
            line.section_subtotal_amount = 0.0
            line.section_subtotal_display = False

        for order in self.mapped("order_id"):
            subtotal = 0.0
            current_section = None
            ordered_lines = order.order_line.sorted(key=lambda l: (l.sequence or 0, l.id or 0))
            for line in ordered_lines:
                if line.display_type == "line_section":
                    if current_section:
                        current_section._set_section_subtotal_values(subtotal, label)
                    current_section = line
                    subtotal = 0.0
                    line.section_subtotal_amount = 0.0
                    line.section_subtotal_display = False
                elif line.display_type:
                    continue
                else:
                    subtotal += line.price_subtotal
            if current_section:
                current_section._set_section_subtotal_values(subtotal, label)

    def _set_section_subtotal_values(self, amount, label):
        self.ensure_one()
        currency = self.order_id.currency_id or self.order_id.company_id.currency_id
        if currency:
            amount_display = format_amount(self.env, amount, currency)
        else:
            amount_display = f"{amount:.2f}"
        self.section_subtotal_amount = amount
        self.section_subtotal_display = (
            f"<span class='o_section_subtotal_chip_label'>{html_escape(label)}</span>"
            f"<span class='o_section_subtotal_chip_value'>{html_escape(amount_display)}</span>"
        )
