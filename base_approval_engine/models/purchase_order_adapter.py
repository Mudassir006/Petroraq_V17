from odoo import _, models
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _name = "purchase.order"
    _inherit = ["purchase.order", "approval.mixin"]

    def _approval_requires_workflow(self):
        self.ensure_one()
        return self.state in ("draft", "sent", "to approve")

    def button_confirm(self):
        for order in self:
            workflow = order._approval_get_applicable_workflow()
            if workflow and order.approval_engine_state != "approved":
                raise UserError(
                    _("Approval is required before confirming this purchase order. Submit and complete approval first.")
                )
        return super().button_confirm()

    def button_approve(self, force=False):
        for order in self:
            workflow = order._approval_get_applicable_workflow()
            if workflow and order.approval_engine_state != "approved":
                raise UserError(
                    _("Approval is required before approving this purchase order.")
                )
        return super().button_approve(force=force)
