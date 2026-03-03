from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class CustomPurchaseRFQ(models.Model):
    _name = "custom.purchase.rfq"
    _description = "Custom RFQ"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(string="RFQ Number", readonly=True, copy=False, default="New", tracking=True)
    origin = fields.Char(string="Origin", tracking=True)
    partner_id = fields.Many2one("res.partner", string="Vendor", tracking=True)
    date_planned = fields.Date(string="Expected Arrival")
    state = fields.Selection([
        ("draft", "Draft"),
        ("sent", "RFQ Sent"),
        ("done", "Locked"),
        ("cancel", "Cancelled"),
    ], default="draft", tracking=True)
    project_id = fields.Many2one("project.project", string="Project")

    requisition_id = fields.Many2one("purchase.requisition", string="Source PR", readonly=True, ondelete="set null")
    pr_name = fields.Char(string="PR Number", readonly=True)
    date_request = fields.Date(string="Date of Request")
    requested_by = fields.Char(string="Requested By")
    department = fields.Char(string="Department")
    supervisor = fields.Char(string="Supervisor")
    supervisor_partner_id = fields.Char(string="Supervisor Partner")
    quotation_ids = fields.One2many("purchase.quotation", "custom_rfq_id", string="Submitted Quotations", readonly=True)
    quotation_count = fields.Integer(compute="_compute_quotation_count")
    line_ids = fields.One2many("custom.purchase.rfq.line", "rfq_id", string="RFQ Lines")

    @api.depends("quotation_ids")
    def _compute_quotation_count(self):
        for rec in self:
            rec.quotation_count = len(rec.quotation_ids)

    @api.model
    def create(self, vals):
        if not vals.get("name") or vals.get("name") == "New":
            vals["name"] = self.env["ir.sequence"].sudo().next_by_code("custom.purchase.rfq") or "CRFQ0001"
        return super().create(vals)

    def action_send_rfq_email(self):
        self.ensure_one()
        if not self.partner_id or not self.partner_id.email:
            raise UserError(_("Please set a vendor with an email before sending RFQ."))

        self.env["mail.mail"].sudo().create({
            "subject": _("RFQ %s") % (self.name or ""),
            "body_html": _(
                "<p>Dear %(vendor)s,</p>"
                "<p>Please submit your quotation for RFQ <b>%(rfq)s</b>.</p>"
                "<p>Regards,<br/>Procurement Team</p>"
            ) % {
                "vendor": self.partner_id.display_name,
                "rfq": self.name,
            },
            "email_to": self.partner_id.email,
        }).send()

        self.write({"state": "sent"})
        self.message_post(body=_("RFQ email sent to %s.") % self.partner_id.display_name)


    def action_open_rfq_comparison(self):
        self.ensure_one()
        if self.requisition_id:
            quotations = self.env["purchase.quotation"].search([("custom_rfq_id.requisition_id", "=", self.requisition_id.id)])
            label = self.requisition_id.name or self.pr_name
        else:
            quotations = self.env["purchase.quotation"].search([("custom_rfq_id", "=", self.id)])
            label = self.name
        if not quotations:
            raise UserError(_("No quotations are available for %s yet.") % label)
        wizard = self.env["rfq.comparison.wizard"].create_for_custom_rfq(self)
        return {
            "type": "ir.actions.act_window",
            "name": _("Quotation Comparison"),
            "res_model": "rfq.comparison.wizard",
            "view_mode": "form",
            "target": "new",
            "res_id": wizard.id,
        }

    def action_view_quotations(self):
        self.ensure_one()
        action = self.env.ref("pr_custom_purchase.action_purchase_quotation_list").read()[0]
        domain = [("custom_rfq_id", "=", self.id)]
        if self.requisition_id:
            domain = [("custom_rfq_id.requisition_id", "=", self.requisition_id.id)]
        action["domain"] = domain
        action["context"] = {
            "default_custom_rfq_id": self.id,
            "default_rfq_origin": self.name,
            "default_pr_name": self.pr_name,
            "default_requested_by": self.requested_by,
            "default_department": self.department,
            "default_supervisor": self.supervisor,
            "default_supervisor_partner_id": self.supervisor_partner_id,
            "group_by": "requisition_id",
        }
        return action


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