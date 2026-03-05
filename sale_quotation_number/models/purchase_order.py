from odoo import api, models, _
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if self.is_using_rfq_number(vals):
                company = self.env["res.company"].browse(vals.get("company_id")) if vals.get(
                    "company_id") else self.env.company
                seq = self.env["ir.sequence"].with_company(company).next_by_code("purchase.quotation")
                if not seq:
                    raise UserError(_("Missing sequence: purchase.quotation for company %s") % company.display_name)
                vals["name"] = seq
        return super().create(vals_list)

    @api.model
    def is_using_rfq_number(self, vals):
        company = self.env["res.company"].browse(vals.get("company_id")) if vals.get("company_id") else self.env.company
        return not company.keep_name_po

    def button_confirm(self):
        for order in self:
            if order.company_id.keep_name_po:
                continue
            if not order.name or "/RFQ/" not in order.name:
                continue
            if order.state not in ("draft", "sent", "to approve"):
                continue

            rfq_ref = (order.origin + ", " if order.origin else "") + order.name
            po_seq = self.env["ir.sequence"].with_company(order.company_id).next_by_code("purchase.custom.order")
            if not po_seq:
                raise UserError(_("Missing sequence: purchase.custom.order for company %s") % order.company_id.display_name)

            order.write({"origin": rfq_ref, "name": po_seq})

        return super().button_confirm()
