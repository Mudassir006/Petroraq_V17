from odoo import models, fields


class ResUsers(models.Model):
    _inherit = "res.users"

    supervisor_user_id = fields.Many2one(
        "res.users",
        string="Supervisor",
        domain="[(\'id\', \'!=\', id)]",
        help="Direct supervisor responsible for approving this user's PRs.",
    )

    def systray_get_activities(self):
        """Guard against orphan activities that reference models missing from the registry.

        Some databases can contain stale `mail.activity` rows (e.g., from older modules).
        Odoo's default implementation raises `KeyError` when such a row is read,
        which breaks the whole systray endpoint.
        """
        try:
            return super().systray_get_activities()
        except KeyError as err:
            missing_model = err.args[0] if err.args else False
            if missing_model:
                stale_activities = self.env["mail.activity"].sudo().search([
                    ("res_model", "=", missing_model),
                ])
                stale_activities.unlink()
            return super().systray_get_activities()
