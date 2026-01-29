from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools import float_is_zero


class PRRetention(models.Model):
    _name = "pr.retention"
    _description = "Construction Retention"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    name = fields.Char(
        string="Retention",
        required=True,
        readonly=True,
        copy=False,
        default=lambda self: _("New"),
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        default=lambda self: self.env.company.currency_id,
        required=True,
    )
    partner_id = fields.Many2one("res.partner", string="Customer", tracking=True)
    project_id = fields.Many2one("project.project", string="Project")
    work_order_id = fields.Many2one(
        "pr.work.order",
        string="Work Order",
        ondelete="set null",
    )
    sale_order_id = fields.Many2one(
        "sale.order",
        string="Sale Order",
        ondelete="set null",
    )
    retention_date = fields.Date(string="Retention Start Date", default=fields.Date.context_today)
    base_amount = fields.Monetary(
        string="Retention Base Amount",
        currency_field="currency_id",
        help="Contract value used to calculate retention percentage.",
        default=0.0,
    )
    retention_type = fields.Selection(
        [("percent", "Percentage"), ("amount", "Fixed Amount")],
        string="Retention Type",
        default="percent",
        required=True,
        tracking=True,
    )
    retention_percent = fields.Float(
        string="Retention (%)",
        digits=(16, 2),
    )
    retention_fixed_amount = fields.Monetary(
        string="Retention Fixed Amount",
        currency_field="currency_id",
    )
    retention_amount = fields.Monetary(
        string="Retention Amount",
        currency_field="currency_id",
        compute="_compute_retention_amount",
        store=True,
    )
    line_ids = fields.One2many(
        "pr.retention.line",
        "retention_id",
        string="Release Lines",
    )
    holdback_line_ids = fields.One2many(
        "pr.retention.holdback",
        "retention_id",
        string="Invoice Holdbacks",
    )
    amount_withheld = fields.Monetary(
        string="Amount Withheld",
        currency_field="currency_id",
        compute="_compute_withheld_amount",
        store=True,
    )
    amount_released = fields.Monetary(
        string="Amount Released",
        currency_field="currency_id",
        compute="_compute_release_amounts",
        store=True,
    )
    amount_remaining = fields.Monetary(
        string="Amount Remaining",
        currency_field="currency_id",
        compute="_compute_release_amounts",
        store=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("active", "Active"),
            ("closed", "Closed"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        tracking=True,
    )
    notes = fields.Text(string="Notes")

    @api.onchange("sale_order_id")
    def _onchange_sale_order_id(self):
        for rec in self:
            if rec.sale_order_id:
                rec.partner_id = rec.sale_order_id.partner_id
                rec.base_amount = rec.sale_order_id.amount_total

    @api.onchange("work_order_id")
    def _onchange_work_order_id(self):
        for rec in self:
            if rec.work_order_id:
                rec.partner_id = rec.work_order_id.partner_id
                rec.project_id = rec.work_order_id.project_id
                if rec.work_order_id.contract_amount:
                    rec.base_amount = rec.work_order_id.contract_amount

    @api.depends("retention_type", "retention_percent", "retention_fixed_amount", "base_amount")
    def _compute_retention_amount(self):
        for rec in self:
            if rec.retention_type == "percent":
                rec.retention_amount = (rec.base_amount or 0.0) * (rec.retention_percent or 0.0) / 100.0
            else:
                rec.retention_amount = rec.retention_fixed_amount or 0.0

    @api.depends("holdback_line_ids.amount")
    def _compute_withheld_amount(self):
        for rec in self:
            rec.amount_withheld = sum(rec.holdback_line_ids.mapped("amount"))

    @api.depends("line_ids.amount", "line_ids.state", "amount_withheld")
    def _compute_release_amounts(self):
        for rec in self:
            released = sum(rec.line_ids.filtered(lambda line: line.state == "released").mapped("amount"))
            rec.amount_released = released
            rec.amount_remaining = (rec.amount_withheld or 0.0) - released

    @api.constrains("retention_percent")
    def _check_retention_percent(self):
        for rec in self:
            if rec.retention_percent < 0 or rec.retention_percent > 100:
                raise ValidationError(_("Retention percentage must be between 0 and 100."))

    @api.constrains("retention_fixed_amount")
    def _check_retention_fixed_amount(self):
        for rec in self:
            if rec.retention_fixed_amount < 0:
                raise ValidationError(_("Retention fixed amount cannot be negative."))

    @api.constrains("base_amount")
    def _check_base_amount(self):
        for rec in self:
            if rec.base_amount < 0:
                raise ValidationError(_("Retention base amount cannot be negative."))

    def action_confirm(self):
        for rec in self:
            if rec.state == "draft":
                rec.state = "active"
        return True

    def action_close(self):
        for rec in self:
            if not float_is_zero(rec.amount_remaining, precision_rounding=rec.currency_id.rounding):
                raise ValidationError(_("Remaining retention must be 0 before closing."))
            rec.state = "closed"
        return True

    def action_cancel(self):
        self.write({"state": "cancelled"})
        return True

    def action_reset_draft(self):
        self.write({"state": "draft"})
        return True

    @api.model
    def create(self, vals):
        if vals.get("name", _("New")) == _("New"):
            vals["name"] = self.env["ir.sequence"].next_by_code("pr.retention") or _("New")
        return super().create(vals)


class PRRetentionLine(models.Model):
    _name = "pr.retention.line"
    _description = "Retention Release Line"
    _order = "release_date desc, id desc"

    retention_id = fields.Many2one(
        "pr.retention",
        string="Retention",
        required=True,
        ondelete="cascade",
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="retention_id.currency_id",
        store=True,
        readonly=True,
    )
    release_date = fields.Date(
        string="Release Date",
        default=fields.Date.context_today,
        required=True,
    )
    amount = fields.Monetary(
        string="Release Amount",
        currency_field="currency_id",
        required=True,
    )
    note = fields.Char(string="Release Note")
    state = fields.Selection(
        [("draft", "Draft"), ("released", "Released"), ("cancelled", "Cancelled")],
        string="Status",
        default="draft",
    )

    @api.constrains("amount")
    def _check_amount(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError(_("Release amount must be greater than zero."))

    def action_release(self):
        for rec in self:
            retention = rec.retention_id
            remaining = retention.amount_remaining
            if rec.amount > remaining:
                raise ValidationError(_("Release amount exceeds remaining retention."))
            rec.state = "released"
        return True

    def action_cancel(self):
        self.write({"state": "cancelled"})
        return True


class PRRetentionHoldback(models.Model):
    _name = "pr.retention.holdback"
    _description = "Retention Holdback Line"
    _order = "date desc, id desc"

    retention_id = fields.Many2one(
        "pr.retention",
        string="Retention",
        required=True,
        ondelete="cascade",
    )
    invoice_id = fields.Many2one(
        "account.move",
        string="Customer Invoice",
        domain="[('move_type', 'in', ('out_invoice', 'out_refund'))]",
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="retention_id.currency_id",
        store=True,
        readonly=True,
    )
    date = fields.Date(string="Date", default=fields.Date.context_today, required=True)
    amount = fields.Monetary(string="Withheld Amount", currency_field="currency_id", required=True)
    note = fields.Char(string="Note")

    @api.constrains("amount")
    def _check_amount(self):
        for rec in self:
            if float_is_zero(rec.amount, precision_rounding=rec.currency_id.rounding):
                raise ValidationError(_("Withheld amount must be non-zero."))
