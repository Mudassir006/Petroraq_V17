from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools import float_is_zero


class AccountMove(models.Model):
    _inherit = "account.move"

    retention_apply = fields.Boolean(string="Apply Retention", default=False)
    retention_type = fields.Selection(
        [("percent", "Percentage"), ("amount", "Fixed Amount")],
        string="Retention Type",
        default="percent",
    )
    retention_percent = fields.Float(string="Retention (%)", digits=(16, 2))
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
    amount_after_retention = fields.Monetary(
        string="Net After Retention",
        currency_field="currency_id",
        compute="_compute_amount_after_retention",
        store=True,
    )
    retention_id = fields.Many2one("pr.retention", string="Retention", ondelete="set null")

    @api.depends("retention_apply", "retention_type", "retention_percent", "retention_fixed_amount", "amount_total")
    def _compute_retention_amount(self):
        for move in self:
            if not move.retention_apply:
                move.retention_amount = 0.0
            elif move.retention_type == "percent":
                move.retention_amount = move.amount_total * (move.retention_percent or 0.0) / 100.0
            else:
                sign = -1.0 if move.amount_total < 0 else 1.0
                move.retention_amount = sign * (move.retention_fixed_amount or 0.0)

    @api.depends("amount_total", "retention_amount")
    def _compute_amount_after_retention(self):
        for move in self:
            move.amount_after_retention = move.amount_total - (move.retention_amount or 0.0)

    @api.onchange("sale_order_id")
    def _onchange_sale_order_id_retention(self):
        for move in self:
            if move.sale_order_id:
                move.retention_apply = move.sale_order_id.retention_apply
                move.retention_type = move.sale_order_id.retention_type
                move.retention_percent = move.sale_order_id.retention_percent
                move.retention_fixed_amount = move.sale_order_id.retention_fixed_amount

    def _get_or_create_retention(self):
        self.ensure_one()
        retention = self.retention_id
        if not retention:
            domain = []
            if self.sale_order_id:
                domain = [("sale_order_id", "=", self.sale_order_id.id)]
            elif self.work_order_id:
                domain = [("work_order_id", "=", self.work_order_id.id)]
            if domain:
                retention = self.env["pr.retention"].search(domain, limit=1)
        if not retention:
            base_amount = 0.0
            if self.sale_order_id:
                base_amount = self.sale_order_id.amount_total
            elif self.work_order_id:
                base_amount = self.work_order_id.contract_amount
            else:
                base_amount = self.amount_total
            retention = self.env["pr.retention"].create(
                {
                    "partner_id": self.partner_id.id,
                    "project_id": self.work_order_id.project_id.id if self.work_order_id else False,
                    "work_order_id": self.work_order_id.id,
                    "sale_order_id": self.sale_order_id.id,
                    "company_id": self.company_id.id,
                    "currency_id": self.currency_id.id,
                    "base_amount": abs(base_amount),
                    "retention_type": self.retention_type,
                    "retention_percent": self.retention_percent,
                    "retention_fixed_amount": abs(self.retention_fixed_amount),
                    "state": "active",
                }
            )
        self.retention_id = retention.id
        return retention

    def _create_retention_holdback(self):
        self.ensure_one()
        if not self.retention_apply:
            return False
        if self.move_type not in ("out_invoice", "out_refund"):
            return False
        retention = self._get_or_create_retention()
        existing = retention.holdback_line_ids.filtered(lambda line: line.invoice_id == self)
        if existing:
            if float_is_zero(self.retention_amount, precision_rounding=self.currency_id.rounding):
                existing.unlink()
                return False
            existing.write({"amount": self.retention_amount})
            return existing
        if float_is_zero(self.retention_amount, precision_rounding=self.currency_id.rounding):
            return False
        return self.env["pr.retention.holdback"].create(
            {
                "retention_id": retention.id,
                "invoice_id": self.id,
                "date": self.invoice_date or fields.Date.context_today(self),
                "amount": self.retention_amount,
            }
        )

    def action_post(self):
        res = super().action_post()
        for move in self:
            if move.state == "posted":
                move._create_retention_holdback()
        return res

    @api.constrains("retention_percent", "retention_fixed_amount")
    def _check_retention_inputs(self):
        for move in self:
            if move.retention_percent < 0 or move.retention_percent > 100:
                raise ValidationError(_("Retention percentage must be between 0 and 100."))
            if move.retention_fixed_amount < 0:
                raise ValidationError(_("Retention fixed amount cannot be negative."))
