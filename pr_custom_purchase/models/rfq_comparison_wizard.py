from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class RFQComparisonWizard(models.TransientModel):
    _name = "rfq.comparison.wizard"
    _description = "RFQ Quotation Comparison"

    rfq_id = fields.Many2one("purchase.order", string="RFQ (Legacy)", readonly=True)
    custom_rfq_id = fields.Many2one("custom.purchase.rfq", string="RFQ", readonly=True)
    requisition_id = fields.Many2one("purchase.requisition", string="Purchase Requisition", readonly=True)
    line_ids = fields.One2many(
        "rfq.comparison.wizard.line",
        "wizard_id",
        string="Comparison Lines",
    )

    @api.model
    def create_for_rfq(self, rfq):
        """Legacy: build comparison from a purchase.order RFQ."""
        wizard = self.create({"rfq_id": rfq.id})
        wizard.write({"line_ids": wizard._prepare_comparison_lines()})
        return wizard

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
        if self.requisition_id:
            quotations = self.env["purchase.quotation"].search([
                ("custom_rfq_id.requisition_id", "=", self.requisition_id.id)
            ])
            label = self.requisition_id.name
        elif self.custom_rfq_id:
            quotations = self.env["purchase.quotation"].search([
                ("custom_rfq_id", "=", self.custom_rfq_id.id)
            ])
            label = self.custom_rfq_id.name
        elif self.rfq_id:
            quotations = self.env["purchase.quotation"].search([
                ("rfq_origin", "=", self.rfq_id.name)
            ])
            label = self.rfq_id.name
        else:
            quotations = self.env["purchase.quotation"]
            label = _("Unknown")

        if not quotations:
            raise UserError(_("No quotations were found for %s.") % label)

        all_offer_lines = []
        grouped_prices = defaultdict(list)
        for quotation in quotations:
            for line in quotation.line_ids:
                product_key = (line.name or line.description or "").strip()
                if not (product_key and quotation.vendor_id):
                    continue
                grouped_prices[product_key].append(line.price_unit)
                all_offer_lines.append((product_key, quotation, line))

        if not all_offer_lines:
            raise UserError(_("No quotation lines are available for comparison."))

        line_commands = []
        for product_key, quotation, line in all_offer_lines:
            min_price = min(grouped_prices[product_key]) if grouped_prices.get(product_key) else line.price_unit
            is_best = line.price_unit == min_price
            line_commands.append(
                (
                    0,
                    0,
                    {
                        "product_key": product_key,
                        "product_name": product_key,
                        "quotation_id": quotation.id,
                        "vendor_id": quotation.vendor_id.id,
                        "quantity": line.quantity,
                        "unit": line.unit,
                        "type": line.type,
                        "cost_center_id": line.cost_center_id.id,
                        "unit_price": line.price_unit,
                        "is_best_line": is_best,
                        "is_selected": is_best,
                    },
                )
            )
        return line_commands

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        rfq_id = self.env.context.get("default_rfq_id")
        if rfq_id:
            wizard = self.new({"rfq_id": rfq_id})
            defaults["line_ids"] = wizard._prepare_comparison_lines()
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
            source_rfq = self.custom_rfq_id or False
            po_vals = {
                "origin": (source_rfq.name if source_rfq else (self.rfq_id.name if self.rfq_id else "")),
                "partner_id": vendor.id,
                "partner_ref": (source_rfq.origin if source_rfq else (self.rfq_id.partner_ref if self.rfq_id else "")),
                "date_planned": fields.Datetime.now(),
                "state": "pending",
                "pr_name": (source_rfq.pr_name if source_rfq else (self.rfq_id.pr_name if self.rfq_id else "")),
                "requested_by": (source_rfq.requested_by if source_rfq else (self.rfq_id.requested_by if self.rfq_id else "")),
                "department": (source_rfq.department if source_rfq else (self.rfq_id.department if self.rfq_id else "")),
                "supervisor": (source_rfq.supervisor if source_rfq else (self.rfq_id.supervisor if self.rfq_id else "")),
                "supervisor_partner_id": (source_rfq.supervisor_partner_id if source_rfq else (self.rfq_id.supervisor_partner_id if self.rfq_id else "")),
                "custom_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": line.product_name,
                            "quantity": line.quantity,
                            "type": line.type,
                            "unit": line.unit,
                            "price_unit": line.unit_price,
                            "cost_center_id": line.cost_center_id.id,
                        },
                    )
                    for line in vendor_lines
                ],
            }
            purchase_orders |= self.env["purchase.order"].sudo().create(po_vals)

        selected_lines.mapped("quotation_id").write({"status": "po"})

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
    quotation_id = fields.Many2one("purchase.quotation", string="Quotation", readonly=True)
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
    is_best_line = fields.Boolean(string="Best Price", readonly=True)
    best_badge = fields.Char(string="Best", compute="_compute_best_badge")

    @api.depends("is_best_line")
    def _compute_best_badge(self):
        for line in self:
            line.best_badge = "Best" if line.is_best_line else ""
