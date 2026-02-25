from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class RFQComparisonWizard(models.TransientModel):
    _name = "rfq.comparison.wizard"
    _description = "RFQ Quotation Comparison"

    rfq_id = fields.Many2one("purchase.order", string="RFQ", required=True, readonly=True)
    line_ids = fields.One2many(
        "rfq.comparison.wizard.line",
        "wizard_id",
        string="Comparison Lines",
    )

    def _prepare_comparison_lines(self):
        self.ensure_one()
        quotations = self.env["purchase.quotation"].search(
            [("rfq_origin", "=", self.rfq_id.name)]
        )
        if not quotations:
            raise UserError(_("No quotations were found for RFQ %s.") % self.rfq_id.name)

        grouped_lines = defaultdict(list)
        for quotation in quotations:
            for line in quotation.line_ids:
                product_key = (line.name or line.description or "").strip()
                if not product_key:
                    continue
                grouped_lines[product_key].append((quotation, line))

        if not grouped_lines:
            raise UserError(_("No quotation lines are available for comparison."))

        line_commands = []
        for product_name, quote_lines in grouped_lines.items():
            best_quotation, best_line = min(quote_lines, key=lambda item: item[1].price_unit)
            line_commands.append(
                (
                    0,
                    0,
                    {
                        "product_name": product_name,
                        "quantity": best_line.quantity,
                        "unit": best_line.unit,
                        "type": best_line.type,
                        "cost_center_id": best_line.cost_center_id.id,
                        "best_vendor_id": best_quotation.vendor_id.id,
                        "best_price": best_line.price_unit,
                        "selected_vendor_id": best_quotation.vendor_id.id,
                        "selected_price": best_line.price_unit,
                        "vendor_offer_json": "|".join(
                            [
                                f"{quotation.vendor_id.id}:{line.price_unit}"
                                for quotation, line in quote_lines
                                if quotation.vendor_id
                            ]
                        ),
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
        selected_lines = self.line_ids.filtered(lambda line: line.is_selected and line.selected_vendor_id)
        if not selected_lines:
            raise UserError(_("Please select at least one product line and vendor."))

        grouped_by_vendor = defaultdict(list)
        for line in selected_lines:
            grouped_by_vendor[line.selected_vendor_id].append(line)

        purchase_orders = self.env["purchase.order"]
        for vendor, vendor_lines in grouped_by_vendor.items():
            po_vals = {
                "origin": self.rfq_id.name,
                "partner_id": vendor.id,
                "partner_ref": self.rfq_id.partner_ref,
                "date_planned": fields.Datetime.now(),
                "state": "pending",
                "pr_name": self.rfq_id.pr_name,
                "requested_by": self.rfq_id.requested_by,
                "department": self.rfq_id.department,
                "supervisor": self.rfq_id.supervisor,
                "supervisor_partner_id": self.rfq_id.supervisor_partner_id,
                "custom_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": line.product_name,
                            "quantity": line.quantity,
                            "type": line.type,
                            "unit": line.unit,
                            "price_unit": line.selected_price,
                            "cost_center_id": line.cost_center_id.id,
                        },
                    )
                    for line in vendor_lines
                ],
            }
            purchase_orders |= self.env["purchase.order"].sudo().create(po_vals)

        quotations = self.env["purchase.quotation"].search([( "rfq_origin", "=", self.rfq_id.name)])
        quotations.write({"status": "po"})

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

    wizard_id = fields.Many2one("rfq.comparison.wizard", required=True, ondelete="cascade")
    is_selected = fields.Boolean(string="Select", default=True)
    product_name = fields.Char(string="Product", readonly=True)
    quantity = fields.Float(string="Qty", readonly=True)
    unit = fields.Char(string="Unit", readonly=True)
    type = fields.Selection(
        [("material", "Material"), ("service", "Service")],
        string="Type",
        readonly=True,
    )
    cost_center_id = fields.Many2one("account.analytic.account", string="Cost Center", readonly=True)
    best_vendor_id = fields.Many2one("res.partner", string="Best Vendor", readonly=True)
    best_price = fields.Float(string="Best Price", readonly=True)
    selected_vendor_id = fields.Many2one("res.partner", string="Selected Vendor")
    selected_price = fields.Float(string="Selected Price")
    vendor_offer_json = fields.Char(string="Vendor Offers", readonly=True)
    offer_summary = fields.Char(string="All Vendor Offers", compute="_compute_offer_summary")
    possible_vendor_ids = fields.Many2many(
        "res.partner",
        compute="_compute_possible_vendor_ids",
        string="Available Vendors",
    )


    @api.depends("vendor_offer_json")
    def _compute_possible_vendor_ids(self):
        for line in self:
            vendor_ids = []
            if line.vendor_offer_json:
                for pair in [entry for entry in line.vendor_offer_json.split("|") if entry]:
                    parts = pair.split(":")
                    if len(parts) == 2:
                        vendor_ids.append(int(parts[0]))
            line.possible_vendor_ids = [(6, 0, vendor_ids)]

    @api.depends("vendor_offer_json")
    def _compute_offer_summary(self):
        vendor_map = {}
        for line in self:
            line.offer_summary = ""
            if not line.vendor_offer_json:
                continue
            pairs = [entry for entry in line.vendor_offer_json.split("|") if entry]
            labels = []
            for pair in pairs:
                parts = pair.split(":")
                if len(parts) != 2:
                    continue
                vendor_id, price = parts
                if vendor_id not in vendor_map:
                    vendor_map[vendor_id] = self.env["res.partner"].browse(int(vendor_id)).display_name
                labels.append(f"{vendor_map[vendor_id]}: {price}")
            line.offer_summary = " | ".join(labels)

    @api.onchange("selected_vendor_id")
    def _onchange_selected_vendor_id(self):
        for line in self:
            if not (line.selected_vendor_id and line.vendor_offer_json):
                continue
            pairs = [entry for entry in line.vendor_offer_json.split("|") if entry]
            for pair in pairs:
                vendor_id, price = pair.split(":")
                if int(vendor_id) == line.selected_vendor_id.id:
                    line.selected_price = float(price)
                    break
