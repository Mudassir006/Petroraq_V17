from odoo import fields, models
class Users(models.Model):
    _inherit = 'res.users'

    hidden_menu_ids = fields.Many2many(
        'ir.ui.menu',
        'res_users_ir_ui_menu_rel',
        'user_id', 'menu_id',
        string='Hidden Menus'
    )

    def write(self, vals):
        res = super().write(vals)
        if 'hidden_menu_ids' in vals:
            # Invalidate cache on ir.ui.menu or reload menus for current user
            self.env['ir.ui.menu'].clear_caches()
        return res
