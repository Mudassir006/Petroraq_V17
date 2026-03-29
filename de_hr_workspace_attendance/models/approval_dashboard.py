from odoo import _, api, models
from odoo.tools.safe_eval import safe_eval


class HrApprovalDashboardService(models.AbstractModel):
    _name = "de.hr.approval.dashboard.service"
    _description = "HR Approval Dashboard Service"

    @api.model
    def _get_visible_approval_menus(self):
        parent = self.env.ref("de_hr_workspace.menu_my_employee_approvals", raise_if_not_found=False)
        if not parent:
            return self.env["ir.ui.menu"]

        menus = self.env["ir.ui.menu"].search([
            ("id", "child_of", parent.id),
            ("id", "!=", parent.id),
        ], order="sequence, id")
        return menus.filtered(lambda m: m.action)

    @api.model
    def _domain_from_action(self, action):
        domain_str = action.domain or "[]"
        eval_context = {
            "uid": self.env.uid,
            "user": self.env.user,
            "context": dict(self.env.context),
        }
        try:
            domain = safe_eval(domain_str, eval_context)
            return domain if isinstance(domain, (list, tuple)) else []
        except Exception:
            return []

    @api.model
    def _count_for_action(self, action):
        if action._name != "ir.actions.act_window" or not action.res_model:
            return 0
        try:
            domain = self._domain_from_action(action)
            return self.env[action.res_model].search_count(domain)
        except Exception:
            return 0


    @api.model
    def _style_for_menu(self, menu_name):
        name = (menu_name or "").lower()
        if "leave" in name:
            return "fa-calendar-check-o", "success"
        if "shortage" in name:
            return "fa-clock-o", "warning"
        if "account" in name:
            return "fa-money", "info"
        if "pay" in name:
            return "fa-file-text-o", "danger"
        if "sale" in name:
            return "fa-line-chart", "primary"
        if "recruit" in name:
            return "fa-users", "warning"
        if "purchase" in name:
            return "fa-shopping-cart", "primary"
        if "hr" in name:
            return "fa-id-badge", "info"
        return "fa-check-square-o", "primary"

    @api.model
    def get_tiles(self):
        tiles = []
        for menu in self._get_visible_approval_menus():
            action = menu.action
            count = self._count_for_action(action)
            icon, tone = self._style_for_menu(menu.name)
            tiles.append({
                "key": f"menu_{menu.id}",
                "name": menu.name or _("Approval"),
                "count": count,
                "icon": icon,
                "tone": tone,
                "action_id": action.id,
            })
        return tiles
