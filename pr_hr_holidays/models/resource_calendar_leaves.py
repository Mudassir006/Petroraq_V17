from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ResourceCalendarLeaves(models.Model):
    _inherit = "resource.calendar.leaves"

    approval_state = fields.Selection(
        [
            ("draft", "Draft"),
            ("to_approve", "To Approve"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        string="Approval Status",
        default="draft",
        tracking=True,
    )
    approved_by_id = fields.Many2one("res.users", string="Approved By", readonly=True, tracking=True)
    approved_on = fields.Datetime(string="Approved On", readonly=True, tracking=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("resource_id"):
                vals["approval_state"] = "approved"
                continue
            vals.setdefault("approval_state", "draft")
        return super().create(vals_list)

    def write(self, vals):
        if "approval_state" in vals and not self.env.user.has_group("hr.group_hr_manager"):
            raise UserError(_("Only HR Managers can change public holiday approval status."))
        return super().write(vals)

    def action_submit_public_holiday(self):
        for rec in self:
            if rec.resource_id:
                continue
            rec.approval_state = "to_approve"

    def action_approve_public_holiday(self):
        if not self.env.user.has_group("hr.group_hr_manager"):
            raise UserError(_("Only HR Managers can approve public holidays."))
        now = fields.Datetime.now()
        for rec in self:
            if rec.resource_id:
                continue
            rec.write({
                "approval_state": "approved",
                "approved_by_id": self.env.user.id,
                "approved_on": now,
            })

    def action_reject_public_holiday(self):
        if not self.env.user.has_group("hr.group_hr_manager"):
            raise UserError(_("Only HR Managers can reject public holidays."))
        for rec in self:
            if rec.resource_id:
                continue
            rec.write({
                "approval_state": "rejected",
                "approved_by_id": False,
                "approved_on": False,
            })
