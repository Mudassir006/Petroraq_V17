from odoo import models, fields

class Menu(models.Model):
    _inherit = 'ir.ui.menu'

    hidden_user_ids = fields.Many2many(
        'res.users',
        'res_users_ir_ui_menu_rel',
        'menu_id', 'user_id',
        string='Hidden for Users'
    )

    def _filter_visible_menus(self):
        menus = super()._filter_visible_menus()
        if self.env.user.hidden_menu_ids:
            menus = menus - self.env.user.hidden_menu_ids
        return menus
