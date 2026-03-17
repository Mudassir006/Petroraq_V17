from odoo import _, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    receipt_approval_state = fields.Selection(
        [
            ("pending", "Pending Approval"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        string="Receipt Approval",
        default="pending",
        copy=False,
        tracking=True,
    )
    receipt_rejection_reason = fields.Text(string="Rejection Reason", copy=False, readonly=True)

    def button_validate(self):
        for picking in self:
            if picking.picking_type_code != "incoming":
                continue
            if picking.receipt_approval_state != "approved":
                raise UserError(_("This receipt must be approved by Inventory Administration before validation."))
        return super().button_validate()

    def action_approve_receipt(self):
        group = self.env.ref("pr_custom_purchase.inventory_admin", raise_if_not_found=False)
        if group and self.env.user not in group.users:
            raise UserError(_("Only Inventory Administration can approve receipts."))
        for rec in self.filtered(lambda p: p.picking_type_code == "incoming"):
            rec.write({"receipt_approval_state": "approved", "receipt_rejection_reason": False})
        return True

    def action_open_receipt_reject_wizard(self):
        self.ensure_one()
        if self.picking_type_code != "incoming":
            raise UserError(_("Rejection is only available for incoming receipts."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Reject Receipt"),
            "res_model": "stock.picking.reject.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_picking_id": self.id},
        }


class StockPickingRejectWizard(models.TransientModel):
    _name = "stock.picking.reject.wizard"
    _description = "Stock Picking Rejection Wizard"

    picking_id = fields.Many2one("stock.picking", required=True)
    rejection_reason = fields.Text(string="Rejection Reason", required=True)

    def action_confirm_reject(self):
        self.ensure_one()
        group = self.env.ref("pr_custom_purchase.inventory_admin", raise_if_not_found=False)
        if group and self.env.user not in group.users:
            raise UserError(_("Only Inventory Administration can reject receipts."))
        if self.picking_id.picking_type_code != "incoming":
            raise UserError(_("Rejection is only available for incoming receipts."))
        self.picking_id.write({
            "receipt_approval_state": "rejected",
            "receipt_rejection_reason": self.rejection_reason,
        })
        return {"type": "ir.actions.act_window_close"}
