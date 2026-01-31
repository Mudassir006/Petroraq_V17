from odoo import models


class SaleAdvancePaymentInv(models.TransientModel):
    _inherit = "sale.advance.payment.inv"

    def _get_created_invoices_from_action(self, action):
        if not action:
            return self.env["account.move"]
        if action.get("res_id"):
            return self.env["account.move"].browse(action["res_id"])
        domain = action.get("domain")
        if domain:
            for item in domain:
                if (
                    isinstance(item, (list, tuple))
                    and len(item) == 3
                    and item[0] == "id"
                    and item[1] == "in"
                ):
                    return self.env["account.move"].browse(item[2])
        return self.env["account.move"]

    def create_invoices(self):
        action = super().create_invoices()
        invoices = self._get_created_invoices_from_action(action)
        if invoices:
            invoices._maybe_add_retention_line()
            return action
        orders = self.env["sale.order"].browse(self._context.get("active_ids", []))
        draft_invoices = orders.invoice_ids.filtered(
            lambda move: move.state == "draft" and move.move_type == "out_invoice"
        )
        draft_invoices._maybe_add_retention_line()
        return action
