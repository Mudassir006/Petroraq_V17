from odoo import _, models
from odoo.exceptions import UserError


class ServiceReceiptNote(models.Model):
    _name = "service.receipt.note"
    _inherit = ["service.receipt.note", "approval.mixin"]

    def _approval_requires_workflow(self):
        self.ensure_one()
        return self.state in ("draft", "ready")

    def _approval_submit_hook(self, request):
        self.ensure_one()
        super()._approval_submit_hook(request)
        self.write({"approval_state": "pending", "rejection_reason": False})

    def _approval_final_approve_hook(self, request):
        self.ensure_one()
        super()._approval_final_approve_hook(request)
        self.write({"approval_state": "approved", "rejection_reason": False})

    def _approval_reject_hook(self, request, reason):
        self.ensure_one()
        super()._approval_reject_hook(request, reason)
        self.write({"approval_state": "rejected", "rejection_reason": reason})

    def action_validate(self):
        for rec in self:
            workflow = rec._approval_get_applicable_workflow()
            if workflow and rec.approval_engine_state != "approved":
                raise UserError(_("Approval Engine validation is required before SRN validation."))
        return super().action_validate()
