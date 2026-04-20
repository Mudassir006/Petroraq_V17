from odoo import _, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["sale.order", "approval.mixin"]

    def _approval_requires_workflow(self):
        self.ensure_one()
        return self.state in ("draft", "sent")

    def action_confirm(self):
        for order in self:
            workflow = order._approval_get_applicable_workflow()
            if workflow and order.approval_engine_state != "approved":
                raise UserError(
                    _("Approval is required before confirming this quotation. Submit and complete approval first.")
                )
        return super().action_confirm()

    # Backward compatibility with legacy buttons/methods from petroraq_sale_workflow
    def action_manager_approve(self):
        return self.action_approve_document()

    def action_md_approve(self):
        return self.action_approve_document()

    def action_reject(self):
        return self.action_open_approval_reject_wizard()

    def _approval_final_approve_hook(self, request):
        self.ensure_one()
        super()._approval_final_approve_hook(request)
        if "approval_state" in self._fields:
            self.approval_state = "approved"
        self.message_post(body=_("Sales approval completed by %s.") % request.final_approved_by.display_name)

    def _approval_submit_hook(self, request):
        self.ensure_one()
        super()._approval_submit_hook(request)
        if "approval_state" in self._fields and self.approval_state in ("draft", "rejected"):
            self.approval_state = "to_manager"

    def _approval_reject_hook(self, request, reason):
        self.ensure_one()
        super()._approval_reject_hook(request, reason)
        if "approval_state" in self._fields:
            self.approval_state = "rejected"
        if "approval_comment" in self._fields:
            self.approval_comment = reason
        self.message_post(body=_("Sales approval rejected: %s") % reason)
