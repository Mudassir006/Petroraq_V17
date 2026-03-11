from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class RFQComparisonWizard(models.TransientModel):
    _name = "rfq.comparison.wizard"
    _description = "RFQ Comparison"

    custom_rfq_id = fields.Many2one("purchase.order", string="RFQ", readonly=True)
    requisition_id = fields.Many2one("purchase.requisition", string="Purchase Requisition", readonly=True)
    line_ids = fields.One2many(
        "rfq.comparison.wizard.line",
        "wizard_id",
        string="Comparison Lines",
    )
    comparison_html = fields.Html(string="Comparison Matrix", compute="_compute_comparison_html", sanitize=False)

    @api.model
    def create_for_custom_rfq(self, rfq):
        """Build comparison from all quotations under the RFQ requisition."""
        wizard = self.create({
            "custom_rfq_id": rfq.id,
            "requisition_id": rfq.requisition_id.id if rfq.requisition_id else False,
        })
        wizard.write({"line_ids": wizard._prepare_comparison_lines()})
        return wizard

    def _prepare_comparison_lines(self):
        self.ensure_one()
        related_rfqs = self.env["purchase.order"]
        if self.requisition_id:
            related_rfqs = self.env["purchase.order"].search([("requisition_id", "=", self.requisition_id.id)])
            label = self.requisition_id.name
        elif self.custom_rfq_id and self.custom_rfq_id.requisition_id:
            related_rfqs = self.env["purchase.order"].search([("requisition_id", "=", self.custom_rfq_id.requisition_id.id)])
            label = self.custom_rfq_id.requisition_id.name
        elif self.custom_rfq_id:
            related_rfqs = self.custom_rfq_id
            label = self.custom_rfq_id.name
        else:
            label = _("Unknown")

        candidate_rfqs = related_rfqs.filtered(lambda r: r.id != self.custom_rfq_id.id and r.order_line and r.partner_id)
        if not candidate_rfqs:
            raise UserError(_("No RFQ lines were found for %s.") % label)

        all_offer_lines = []
        grouped_prices = defaultdict(list)
        for rfq in candidate_rfqs:
            for line in rfq.order_line:
                product_key = (line.name or "").strip()
                if not product_key:
                    continue
                grouped_prices[product_key].append(line.price_unit)
                all_offer_lines.append((product_key, rfq, line, line.analytic_distribution))

        if not all_offer_lines:
            raise UserError(_("No RFQ lines are available for comparison."))

        line_commands = []
        for product_key, rfq, line, analytic_distribution in all_offer_lines:
            min_price = min(grouped_prices[product_key]) if grouped_prices.get(product_key) else line.price_unit
            is_best = line.price_unit == min_price
            line_commands.append((0, 0, {
                "product_key": product_key,
                "product_name": product_key,
                "rfq_id": rfq.id,
                "vendor_id": rfq.partner_id.id,
                "quantity": line.product_qty,
                "unit": line.product_uom.name if line.product_uom else "",
                "type": "service" if (line.product_id and line.product_id.type == "service") else "material",
                "cost_center_id": self._extract_cost_center_from_distribution(analytic_distribution),
                "unit_price": line.price_unit,
                "is_best_line": is_best,
                "analytic_distribution": analytic_distribution or False,
                "is_selected": is_best,
            }))
        return line_commands

    @api.model
    def _extract_cost_center_from_distribution(self, analytic_distribution):
        if not analytic_distribution:
            return False
        try:
            analytic_account_id = int(next(iter(analytic_distribution.keys())))
        except (StopIteration, TypeError, ValueError, AttributeError):
            return False
        return analytic_account_id

    @api.depends("line_ids", "line_ids.product_name", "line_ids.vendor_id", "line_ids.unit_price", "line_ids.quantity")
    def _compute_comparison_html(self):
        for wizard in self:
            wizard.comparison_html = wizard._render_comparison_matrix_html()

    def _render_comparison_matrix_html(self):
        self.ensure_one()
        if not self.line_ids:
            return '<p class="text-muted">No comparison lines found.</p>'

        vendor_order = sorted(self.line_ids.mapped("vendor_id"), key=lambda v: (v.name or "").lower())
        grouped = {}
        for line in self.line_ids.sorted(key=lambda l: (l.product_name or "", l.vendor_id.name or "")):
            key = line.product_key or line.product_name
            if key not in grouped:
                grouped[key] = {
                    "product_name": line.product_name,
                    "unit": line.unit,
                    "qty": line.quantity,
                    "type": line.type,
                    "vendors": {},
                }
            grouped[key]["vendors"][line.vendor_id.id] = line

        vendor_header = "".join(
            f'<th colspan="2" style="text-align:center;background:#d9ead3;border:1px solid #8fbc8f;">{vendor.name}</th>'
            for vendor in vendor_order
        )
        vendor_subheader = "".join(
            '<th style="background:#d9ead3;border:1px solid #8fbc8f;">Cost Price</th>'
            '<th style="background:#d9ead3;border:1px solid #8fbc8f;">Total</th>'
            for _vendor in vendor_order
        )

        rows_html = []
        for sr_no, item in enumerate(grouped.values(), start=1):
            row = [
                f'<td style="border:1px solid #bbb;text-align:center;">{sr_no}</td>',
                f'<td style="border:1px solid #bbb;">{item["product_name"] or ""}</td>',
                f'<td style="border:1px solid #bbb;text-align:center;">{item["unit"] or ""}</td>',
                f'<td style="border:1px solid #bbb;text-align:right;">{item["qty"] or 0}</td>',
                f'<td style="border:1px solid #bbb;">{item["type"] or ""}</td>',
            ]
            available_prices = [offer.unit_price for offer in item["vendors"].values()]
            best_price = min(available_prices) if available_prices else False

            for vendor in vendor_order:
                offer = item["vendors"].get(vendor.id)
                if not offer:
                    row.append('<td style="border:1px solid #bbb;text-align:center;">-</td>')
                    row.append('<td style="border:1px solid #bbb;text-align:center;">-</td>')
                    continue

                highlight = "background:#fff176;" if best_price is not False and offer.unit_price == best_price else ""
                total = (offer.quantity or 0.0) * (offer.unit_price or 0.0)
                row.append(f'<td style="border:1px solid #bbb;text-align:right;{highlight}">{offer.unit_price:.2f}</td>')
                row.append(f'<td style="border:1px solid #bbb;text-align:right;{highlight}">{total:.2f}</td>')

            rows_html.append('<tr>' + ''.join(row) + '</tr>')

        return (
            '<div style="overflow:auto;max-width:100%;">'
            '<table style="border-collapse:collapse;width:100%;font-size:13px;">'
            '<thead>'
            '<tr>'
            '<th rowspan="2" style="background:#b6d7a8;border:1px solid #8fbc8f;">Sr No</th>'
            '<th rowspan="2" style="background:#b6d7a8;border:1px solid #8fbc8f;">Description</th>'
            '<th rowspan="2" style="background:#b6d7a8;border:1px solid #8fbc8f;">Unit</th>'
            '<th rowspan="2" style="background:#b6d7a8;border:1px solid #8fbc8f;">Qty</th>'
            '<th rowspan="2" style="background:#b6d7a8;border:1px solid #8fbc8f;">Type</th>'
            + vendor_header +
            '</tr>'
            '<tr>' + vendor_subheader + '</tr>'
            '</thead>'
            '<tbody>' + ''.join(rows_html) + '</tbody>'
            '</table>'
            '</div>'
        )

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        return defaults

    def action_create_selected_purchase_orders(self):
        self.ensure_one()
        selected_lines = self.line_ids.filtered(lambda line: line.is_selected and line.vendor_id)
        if not selected_lines:
            raise UserError(_("Please select at least one quotation line."))

        # one vendor offer per product in a single award run
        selected_by_product = defaultdict(list)
        for line in selected_lines:
            selected_by_product[line.product_key].append(line)

        duplicate_products = [
            key for key, lines in selected_by_product.items() if len(lines) > 1
        ]
        if duplicate_products:
            raise UserError(
                _("Please select only one vendor offer per product. Duplicates: %s")
                % ", ".join(duplicate_products)
            )

        grouped_by_vendor = defaultdict(list)
        for line in selected_lines:
            grouped_by_vendor[line.vendor_id].append(line)

        purchase_orders = self.env["purchase.order"]
        for vendor, vendor_lines in grouped_by_vendor.items():
            source_rfq = self.custom_rfq_id
            po_vals = {
                "name": self.env["ir.sequence"].sudo().next_by_code("purchase.order") or "PO0001",
                "origin": source_rfq.name if source_rfq else "",
                "partner_id": vendor.id,
                "partner_ref": source_rfq.origin if source_rfq else "",
                "date_planned": fields.Datetime.now(),
                "state": "pending",
                "pr_name": source_rfq.pr_name if source_rfq else "",
                "requested_by": source_rfq.requested_by if source_rfq else "",
                "department": source_rfq.department if source_rfq else "",
                "supervisor": source_rfq.supervisor if source_rfq else "",
                "supervisor_partner_id": source_rfq.supervisor_partner_id if source_rfq else "",
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "name": line.product_name,
                            "product_qty": line.quantity,
                            "price_unit": line.unit_price,
                            "date_planned": fields.Datetime.now(),
                            "analytic_distribution": line.analytic_distribution or False,
                        },
                    )
                    for line in vendor_lines
                ],
            }
            purchase_orders |= self.env["purchase.order"].sudo().create(po_vals)

        if self.custom_rfq_id:
            self.custom_rfq_id.sudo().write({"state": "done"})

        action = {
            "type": "ir.actions.act_window",
            "name": _("Created Purchase Orders"),
            "res_model": "purchase.order",
            "view_mode": "tree,form",
            "domain": [("id", "in", purchase_orders.ids)],
        }
        if len(purchase_orders) == 1:
            action.update({"view_mode": "form", "res_id": purchase_orders.id})
        return action


class RFQComparisonWizardLine(models.TransientModel):
    _name = "rfq.comparison.wizard.line"
    _description = "RFQ Quotation Comparison Line"
    _order = "product_name, unit_price asc"

    wizard_id = fields.Many2one("rfq.comparison.wizard", required=True, ondelete="cascade")
    is_selected = fields.Boolean(string="Select")
    product_key = fields.Char(string="Product Key", readonly=True)
    product_name = fields.Char(string="Product", readonly=True)
    rfq_id = fields.Many2one("purchase.order", string="RFQ", readonly=True)
    vendor_id = fields.Many2one("res.partner", string="Vendor", readonly=True)
    quantity = fields.Float(string="Qty", readonly=True)
    unit = fields.Char(string="Unit", readonly=True)
    type = fields.Selection(
        [("material", "Material"), ("service", "Service")],
        string="Type",
        readonly=True,
    )
    cost_center_id = fields.Many2one("account.analytic.account", string="Cost Center", readonly=True)
    unit_price = fields.Float(string="Unit Price", readonly=True)
    analytic_distribution = fields.Json(string="Analytic Distribution", readonly=True)
    is_best_line = fields.Boolean(string="Best Price", readonly=True)
    best_badge = fields.Char(string="Best", compute="_compute_best_badge")

    @api.depends("is_best_line")
    def _compute_best_badge(self):
        for line in self:
            line.best_badge = "Best" if line.is_best_line else ""