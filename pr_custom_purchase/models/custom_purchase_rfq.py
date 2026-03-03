from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class CustomPurchaseRFQ(models.Model):
    _name = "custom.purchase.rfq"
    _description = "Custom RFQ"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(string="RFQ Number", required=True, readonly=True, copy=False, default="New")
    requisition_id = fields.Many2one("purchase.requisition", string="Source PR", readonly=True, ondelete="set null")
    origin = fields.Char(string="Origin")
    partner_id = fields.Many2one("res.partner", string="Preferred Vendor")
    pr_name = fields.Char(string="PR Number", readonly=True)
    date_planned = fields.Date(string="Expected Arrival")
    date_request = fields.Date(string="Date of Request")
    requested_by = fields.Char(string="Requested By")
    department = fields.Char(string="Department")
    supervisor = fields.Char(string="Supervisor")
    supervisor_partner_id = fields.Char(string="Supervisor Partner")
    project_id = fields.Many2one("project.project", string="Project")
    state = fields.Selection([
        ("draft", "Draft"),
        ("sent", "Sent"),
        ("done", "Done"),
        ("cancel", "Cancelled"),
    ], default="draft", tracking=True)

    line_ids = fields.One2many("custom.purchase.rfq.line", "rfq_id", string="RFQ Lines")
    quotation_ids = fields.One2many(
        "purchase.quotation", "custom_rfq_id", string="Submitted Quotations", readonly=True
    )
    quotation_count = fields.Integer(compute="_compute_quotation_count")

    @api.depends("quotation_ids")
    def _compute_quotation_count(self):
        for rec in self:
            rec.quotation_count = len(rec.quotation_ids)

    @api.model
    def create(self, vals):
        rec = super().create(vals)
        if rec.name == "New":
            rec.name = self.env["ir.sequence"].sudo().next_by_code("custom.purchase.rfq") or "CRFQ0001"
        return rec

    def action_mark_sent(self):
        self.write({"state": "sent"})

    def action_view_quotations(self):
        self.ensure_one()
        action = self.env.ref("pr_custom_purchase.action_purchase_quotation_list").read()[0]
        action["domain"] = [("custom_rfq_id", "=", self.id)]
        action["context"] = {
            "default_custom_rfq_id": self.id,
            "default_rfq_origin": self.name,
            "default_pr_name": self.pr_name,
            "default_requested_by": self.requested_by,
            "default_department": self.department,
            "default_supervisor": self.supervisor,
            "default_supervisor_partner_id": self.supervisor_partner_id,
        }
        return action

    def action_create_purchase_order_from_best_quote(self):
        self.ensure_one()
        best_quote = self.quotation_ids.sorted(lambda q: q.total_incl_vat)[:1]
        if not best_quote:
            raise UserError(_("Please submit at least one quotation first."))
        return best_quote.action_create_purchase_order()


class CustomPurchaseRFQLine(models.Model):
    _name = "custom.purchase.rfq.line"
    _description = "Custom RFQ Line"

    rfq_id = fields.Many2one("custom.purchase.rfq", string="RFQ", required=True, ondelete="cascade")
    name = fields.Char(string="Description", required=True)
    type = fields.Selection(
        [("material", "Material"), ("service", "Service")],
        string="Type",
        default="material",
        required=True,
    )
    quantity = fields.Float(string="Quantity", default=1.0)
    unit = fields.Char(string="Unit")
    price_unit = fields.Float(string="Estimated Unit Price")
    cost_center_id = fields.Many2one("account.analytic.account", string="Cost Center", required=True)
    subtotal = fields.Float(string="Subtotal", compute="_compute_subtotal", store=True)

    @api.depends("quantity", "price_unit")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.price_unit

    @api.constrains("quantity", "price_unit")
    def _check_non_negative_values(self):
        for line in self:
            if line.quantity < 0:
                raise ValidationError(_("Quantity cannot be negative."))
            if line.price_unit < 0:
                raise ValidationError(_("Unit Price cannot be negative."))
