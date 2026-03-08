

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    keep_name_so = fields.Boolean(
        string="Use Same Enumeration",
        help="If this is unchecked, quotations use a different sequence from "
        "sale orders",
        default=True,
    )
    keep_name_po = fields.Boolean(
        string="Use Same Enumeration for Purchase",
        help="If this is unchecked, RFQs use a different sequence from "
        "purchase orders",
        default=True,
    )


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    keep_name_so = fields.Boolean(
        related="company_id.keep_name_so",
        readonly=False,
    )
    keep_name_po = fields.Boolean(
        related="company_id.keep_name_po",
        readonly=False,
    )
