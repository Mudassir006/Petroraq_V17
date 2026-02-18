from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pr_default_department_id = fields.Many2one(
        "hr.department",
        string="Default PR Department",
        config_parameter="custom_user_portal.pr_default_department_id",
        help="Used as fallback department when requester has no department set.",
    )
    pr_default_supervisor_id = fields.Many2one(
        "hr.employee",
        string="Default PR Supervisor",
        config_parameter="custom_user_portal.pr_default_supervisor_id",
        help="Used as fallback supervisor when requester has no direct manager.",
    )
