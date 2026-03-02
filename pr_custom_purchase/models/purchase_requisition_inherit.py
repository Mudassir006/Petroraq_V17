from odoo import fields, models


class PurchaseRequisition(models.Model):
    _inherit = 'purchase.requisition'

    rejection_reason = fields.Text(string='Reason for Rejection')
