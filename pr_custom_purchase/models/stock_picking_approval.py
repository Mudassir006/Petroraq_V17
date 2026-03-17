from odoo import _, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def button_validate(self):
        group = self.env.ref("pr_custom_purchase.inventory_admin", raise_if_not_found=False)
        for picking in self:
            if picking.picking_type_code != "incoming":
                continue
            if group and self.env.user not in group.users:
                raise UserError(_("Only Inventory Administration can validate incoming receipts."))
        return super().button_validate()

    def action_approve_receipt(self):
        group = self.env.ref("pr_custom_purchase.inventory_admin", raise_if_not_found=False)
        if group and self.env.user not in group.users:
            raise UserError(_("Only Inventory Administration can approve receipts."))
        for rec in self.filtered(lambda p: p.picking_type_code == "incoming"):
            rec.message_post(body=_("Receipt approved by Inventory Administration."))
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
        self.picking_id.message_post(body=_("Receipt rejected by Inventory Administration. Reason: %s") % self.rejection_reason)
        self.picking_id.action_cancel()
        return {"type": "ir.actions.act_window_close"}
