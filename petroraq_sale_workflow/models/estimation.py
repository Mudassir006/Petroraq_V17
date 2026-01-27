from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


SECTION_TYPES = [
    ("material", "Material"),
    ("labor", "Labor"),
    ("equipment", "Equipment"),
    ("subcontract", "Sub Contract / TPS"),
]


class PetroraqEstimation(models.Model):
    _name = "petroraq.estimation"
    _description = "Estimation"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    approval_state = fields.Selection(
        [
            ("draft", "Draft"),
            ("to_manager", "Manager Approve"),
            ("to_md", "MD Approve"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        default="draft",
        tracking=True,
        copy=False,
    )
    approval_comment = fields.Text("Approval Comment", tracking=True)
    show_reject_button = fields.Boolean(compute="_compute_show_reject_button")

    name = fields.Char(
        string="Estimation",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("New"),
    )
    partner_id = fields.Many2one("res.partner", string="Customer", required=True, tracking=True)
    date = fields.Date(string="Date", default=fields.Date.context_today, tracking=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )
    line_ids = fields.One2many(
        "petroraq.estimation.line",
        "estimation_id",
        string="Estimation Lines",
    )
    material_line_ids = fields.One2many(
        "petroraq.estimation.line",
        "material_estimation_id",
        string="Material Lines",
    )
    labor_line_ids = fields.One2many(
        "petroraq.estimation.line",
        "labor_estimation_id",
        string="Labor Lines",
    )
    equipment_line_ids = fields.One2many(
        "petroraq.estimation.line",
        "equipment_estimation_id",
        string="Equipment Lines",
    )
    subcontract_line_ids = fields.One2many(
        "petroraq.estimation.line",
        "subcontract_estimation_id",
        string="Subcontract Lines",
    )
    sale_order_id = fields.Many2one("sale.order", string="Quotation", readonly=True, copy=False)

    material_total = fields.Monetary(
        string="Material Total",
        compute="_compute_totals",
        currency_field="currency_id",
        store=False,
    )
    labor_total = fields.Monetary(
        string="Labor Total",
        compute="_compute_totals",
        currency_field="currency_id",
        store=False,
    )
    equipment_total = fields.Monetary(
        string="Equipment Total",
        compute="_compute_totals",
        currency_field="currency_id",
        store=False,
    )
    subcontract_total = fields.Monetary(
        string="Sub Contract / TPS Total",
        compute="_compute_totals",
        currency_field="currency_id",
        store=False,
    )
    total_amount = fields.Monetary(
        string="Total",
        compute="_compute_totals",
        currency_field="currency_id",
        store=False,
    )
    overhead_percent = fields.Float(
        string="Over Head (%)",
        default=0.0,
        digits=(16, 2),
    )
    risk_percent = fields.Float(
        string="Risk (%)",
        default=0.0,
        digits=(16, 2),
    )
    profit_percent = fields.Float(
        string="Profit (%)",
        default=0.0,
        digits=(16, 2),
    )
    overhead_amount = fields.Monetary(
        string="Over Head Amount",
        compute="_compute_totals",
        currency_field="currency_id",
        store=False,
    )
    risk_amount = fields.Monetary(
        string="Risk Amount",
        compute="_compute_totals",
        currency_field="currency_id",
        store=False,
    )
    buffer_total_amount = fields.Monetary(
        string="Computed Total Amount",
        compute="_compute_totals",
        currency_field="currency_id",
        store=False,
        help="Total amount including overhead and risk (no profit).",
    )
    profit_amount = fields.Monetary(
        string="Profit Amount",
        compute="_compute_totals",
        currency_field="currency_id",
        store=False,
    )
    total_with_profit = fields.Monetary(
        string="Total With Profit",
        compute="_compute_totals",
        currency_field="currency_id",
        store=False,
    )

    @api.model
    def create(self, vals):
        if vals.get("name", _("New")) == _("New"):
            vals["name"] = self.env["ir.sequence"].next_by_code("petroraq.estimation") or _("New")
        return super().create(vals)

    @api.depends_context("uid")
    @api.depends("approval_state")
    def _compute_show_reject_button(self):
        user = self.env.user
        for record in self:
            record.show_reject_button = (
                (record.approval_state == "to_manager" and user.has_group(
                    "petroraq_sale_workflow.group_sale_approval_manager"))
                or
                (record.approval_state == "to_md" and user.has_group(
                    "petroraq_sale_workflow.group_sale_approval_md"))
            )

    @api.onchange("partner_id")
    def _onchange_partner_company(self):
        for record in self:
            if record.partner_id.company_id and record.partner_id.company_id != record.company_id:
                record.company_id = record.partner_id.company_id

    @api.depends(
        "material_line_ids.subtotal",
        "labor_line_ids.subtotal",
        "equipment_line_ids.subtotal",
        "subcontract_line_ids.subtotal",
        "overhead_percent",
        "risk_percent",
        "profit_percent",
    )
    def _compute_totals(self):
        for record in self:
            material_total = sum(record.material_line_ids.mapped("subtotal"))
            labor_total = sum(record.labor_line_ids.mapped("subtotal"))
            equipment_total = sum(record.equipment_line_ids.mapped("subtotal"))
            subcontract_total = sum(record.subcontract_line_ids.mapped("subtotal"))
            record.material_total = material_total
            record.labor_total = labor_total
            record.equipment_total = equipment_total
            record.subcontract_total = subcontract_total
            base_total = material_total + labor_total + equipment_total + subcontract_total
            overhead_amount = base_total * (record.overhead_percent or 0.0) / 100.0
            risk_amount = base_total * (record.risk_percent or 0.0) / 100.0
            buffer_total = base_total + overhead_amount + risk_amount
            profit_amount = buffer_total * (record.profit_percent or 0.0) / 100.0

            record.total_amount = base_total
            record.overhead_amount = overhead_amount
            record.risk_amount = risk_amount
            record.buffer_total_amount = buffer_total
            record.profit_amount = profit_amount
            record.total_with_profit = buffer_total + profit_amount

    @api.onchange("overhead_percent", "risk_percent", "profit_percent")
    def _onchange_percent_validation(self):
        for field in ("overhead_percent", "risk_percent", "profit_percent"):
            value = self[field]
            if value < 0:
                raise UserError(_("Percentage cannot be negative."))
            if value > 100:
                raise UserError(_("Percentage cannot exceed 100%."))

    @api.constrains("overhead_percent", "risk_percent", "profit_percent")
    def _check_percentages(self):
        for record in self:
            for field_name in ("overhead_percent", "risk_percent", "profit_percent"):
                value = record[field_name]
                if value < 0:
                    raise ValidationError(_("Percentage cannot be negative."))
                if value > 100:
                    raise ValidationError(_("Percentage cannot exceed 100%."))

    def action_create_sale_order(self):
        self.ensure_one()
        if self.approval_state != "approved":
            raise UserError(_("You can only create a quotation after final approval."))
        if not self.partner_id:
            raise UserError(_("Please set a customer before creating a quotation."))
        if self.sale_order_id:
            return {
                "type": "ir.actions.act_window",
                "name": _("Quotation"),
                "res_model": "sale.order",
                "res_id": self.sale_order_id.id,
                "view_mode": "form",
                "target": "current",
            }

        term = self.env.ref("petroraq_sale_workflow.payment_term_immediate", raise_if_not_found=False)
        company = self.company_id
        if self.partner_id.company_id:
            company = self.partner_id.company_id
        partner = self.partner_id.with_company(company)
        addresses = partner.address_get(["invoice", "delivery"])
        order_vals = {
            "partner_id": self.partner_id.id,
            "company_id": company.id,
            "currency_id": company.currency_id.id,
            "inquiry_type": "construction",
            "payment_term_id": term.id if term else False,
            "partner_invoice_id": addresses.get("invoice"),
            "partner_shipping_id": addresses.get("delivery"),
        }
        if self.order_inquiry_id:
            order_vals["order_inquiry_id"] = self.order_inquiry_id.id
        order = self.env["sale.order"].with_company(company).create(order_vals)

        self.sale_order_id = order.id

        return {
            "type": "ir.actions.act_window",
            "name": _("Quotation"),
            "res_model": "sale.order",
            "res_id": order.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_confirm_estimation(self):
        for record in self:
            if not (record.material_line_ids or record.labor_line_ids or record.equipment_line_ids
                    or record.subcontract_line_ids):
                raise UserError(_("Please add at least one estimation line."))
            record.approval_state = "to_manager"
            record.approval_comment = False

    def action_manager_approve(self):
        for record in self:
            if record.approval_state != "to_manager":
                raise UserError(_("This estimation is not awaiting manager approval."))
            record.approval_state = "to_md"

    def action_md_approve(self):
        for record in self:
            if record.approval_state != "to_md":
                raise UserError(_("This estimation is not awaiting MD approval."))
            record.approval_state = "approved"

    def action_reject(self):
        for record in self:
            if record.approval_state not in ("to_manager", "to_md", "draft"):
                raise UserError(_("Only waiting approvals can be rejected."))
            record.approval_state = "rejected"

    def action_reset_to_draft(self):
        for record in self:
            if record.approval_state == "rejected":
                record.approval_state = "draft"


class PetroraqEstimationLine(models.Model):
    _name = "petroraq.estimation.line"
    _description = "Estimation Line"
    _order = "section_type, id"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals = self._prepare_section_vals(vals)
        return super().create(vals_list)

    def write(self, vals):
        for line in self:
            line_vals = dict(vals)
            line_vals = line._prepare_section_vals(line_vals)
            super(PetroraqEstimationLine, line).write(line_vals)
        return True

    def _prepare_section_vals(self, vals):
        section_type = vals.get("section_type") or self.env.context.get("default_section_type") or self.section_type
        estimation_id = vals.get("estimation_id") or self.estimation_id.id
        section_field_map = {
            "material": "material_estimation_id",
            "labor": "labor_estimation_id",
            "equipment": "equipment_estimation_id",
            "subcontract": "subcontract_estimation_id",
        }
        for section, field_name in section_field_map.items():
            if vals.get(field_name):
                vals["estimation_id"] = vals[field_name]
                vals["section_type"] = section
                for other_field in section_field_map.values():
                    if other_field != field_name:
                        vals.setdefault(other_field, False)
                return vals
        if section_type:
            vals["section_type"] = section_type
        if section_type and estimation_id and not vals.get(section_field_map[section_type]):
            vals[section_field_map[section_type]] = estimation_id
        return vals

    estimation_id = fields.Many2one(
        "petroraq.estimation",
        string="Estimation",
        ondelete="cascade",
    )
    material_estimation_id = fields.Many2one(
        "petroraq.estimation",
        string="Material Estimation",
        compute="_compute_section_estimation_ids",
        inverse="_inverse_section_estimation_ids",
        store=True,
    )
    labor_estimation_id = fields.Many2one(
        "petroraq.estimation",
        string="Labor Estimation",
        compute="_compute_section_estimation_ids",
        inverse="_inverse_section_estimation_ids",
        store=True,
    )
    equipment_estimation_id = fields.Many2one(
        "petroraq.estimation",
        string="Equipment Estimation",
        compute="_compute_section_estimation_ids",
        inverse="_inverse_section_estimation_ids",
        store=True,
    )
    subcontract_estimation_id = fields.Many2one(
        "petroraq.estimation",
        string="Subcontract Estimation",
        compute="_compute_section_estimation_ids",
        inverse="_inverse_section_estimation_ids",
        store=True,
    )
    section_type = fields.Selection(
        SECTION_TYPES,
        string="Section",
        required=True,
        default=lambda self: self.env.context.get("default_section_type"),
    )
    product_id = fields.Many2one("product.product", string="Product")
    name = fields.Char(string="Description")
    # For Labor/Equipment the business wants: (count) * (days) * (8 hours/day) = qty (hours)
    resource_count = fields.Float(string="Count", default=1.0)
    days = fields.Float(string="Days", default=1.0)
    hours_per_day = fields.Float(string="Hours/Day", default=8.0)
    quantity_hours = fields.Float(
        string="Total Hours",
        compute="_compute_quantity_hours",
        store=False,
        readonly=True,
    )
    quantity = fields.Float(
        string="Quantity",
        default=1.0,
        help="Used for Material/Subcontract. For Labor/Equipment the quantity is computed as Total Hours.",
    )
    uom_id = fields.Many2one("uom.uom", string="Unit of Measure")
    currency_id = fields.Many2one(
        "res.currency",
        compute="_compute_currency_id",
        store=True,
        readonly=True,
    )
    unit_cost = fields.Monetary(string="Unit Cost", currency_field="currency_id")
    subtotal = fields.Monetary(
        string="Subtotal",
        currency_field="currency_id",
        compute="_compute_subtotal",
        store=False,
    )

    @api.depends(
        "estimation_id",
        "section_type",
        "material_estimation_id",
        "labor_estimation_id",
        "equipment_estimation_id",
        "subcontract_estimation_id",
    )
    def _compute_section_estimation_ids(self):
        for line in self:
            line.material_estimation_id = line.estimation_id if line.section_type == "material" else False
            line.labor_estimation_id = line.estimation_id if line.section_type == "labor" else False
            line.equipment_estimation_id = line.estimation_id if line.section_type == "equipment" else False
            line.subcontract_estimation_id = line.estimation_id if line.section_type == "subcontract" else False

    def _inverse_section_estimation_ids(self):
        for line in self:
            if line.material_estimation_id:
                line.estimation_id = line.material_estimation_id
                line.section_type = "material"
            elif line.labor_estimation_id:
                line.estimation_id = line.labor_estimation_id
                line.section_type = "labor"
            elif line.equipment_estimation_id:
                line.estimation_id = line.equipment_estimation_id
                line.section_type = "equipment"
            elif line.subcontract_estimation_id:
                line.estimation_id = line.subcontract_estimation_id
                line.section_type = "subcontract"

    @api.depends(
        "estimation_id",
        "material_estimation_id",
        "labor_estimation_id",
        "equipment_estimation_id",
        "subcontract_estimation_id",
    )
    def _compute_currency_id(self):
        for line in self:
            estimation = line.material_estimation_id or line.labor_estimation_id or line.equipment_estimation_id or \
                line.subcontract_estimation_id or line.estimation_id
            line.currency_id = estimation.currency_id if estimation else False

    @api.constrains("material_estimation_id", "labor_estimation_id", "equipment_estimation_id", "subcontract_estimation_id")
    def _check_single_section(self):
        for line in self:
            section_fields = [
                line.material_estimation_id,
                line.labor_estimation_id,
                line.equipment_estimation_id,
                line.subcontract_estimation_id,
            ]
            if sum(bool(field) for field in section_fields) > 1:
                raise ValidationError(_("Only one section reference can be set per estimation line."))

    @api.onchange("product_id")
    def _onchange_product_id(self):
        for line in self:
            if not line.product_id:
                continue
            line.name = line.product_id.display_name
            # For Labor/Equipment we always calculate in hours.
            if line.section_type in ("labor", "equipment"):
                hour_uom = self.env.ref("uom.product_uom_hour", raise_if_not_found=False)
                line.uom_id = hour_uom.id if hour_uom else line.product_id.uom_id
            else:
                line.uom_id = line.product_id.uom_id
            line.unit_cost = line.product_id.standard_price

    @api.onchange("section_type")
    def _onchange_section_type(self):
        """Keep labor/equipment aligned with the business rule: 8h/day fixed and UoM is Hours."""
        for line in self:
            if line.section_type in ("labor", "equipment"):
                line.hours_per_day = 8.0
                hour_uom = self.env.ref("uom.product_uom_hour", raise_if_not_found=False)
                if hour_uom:
                    line.uom_id = hour_uom.id

    @api.depends("section_type", "resource_count", "days", "hours_per_day")
    def _compute_quantity_hours(self):
        for line in self:
            if line.section_type in ("labor", "equipment"):
                line.quantity_hours = (line.resource_count or 0.0) * (line.days or 0.0) * (line.hours_per_day or 0.0)
            else:
                line.quantity_hours = 0.0

    @api.depends(
        "section_type",
        "quantity",
        "quantity_hours",
        "unit_cost",
    )
    def _compute_subtotal(self):
        for line in self:
            qty = line.quantity_hours if line.section_type in ("labor", "equipment") else (line.quantity or 0.0)
            line.subtotal = qty * (line.unit_cost or 0.0)
