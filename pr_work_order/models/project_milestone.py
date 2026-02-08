from odoo import api, models, _
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare


class ProjectMilestone(models.Model):
    _inherit = "project.milestone"

    @api.constrains("sale_line_id", "quantity")
    def _check_sale_line_milestone_percentage(self):
        for milestone in self:
            sale_line = milestone.sale_line_id
            if not sale_line:
                continue
            total_percentage = sum(
                self.search([("sale_line_id", "=", sale_line.id)]).mapped("quantity")
            )
            if float_compare(total_percentage, 100.0, precision_digits=2) > 0:
                raise ValidationError(
                    _(
                        "The total milestone percentage for the sales order item '%(line)s' "
                        "cannot exceed 100%%. Current total: %(total).2f%%."
                    )
                    % {
                        "line": sale_line.display_name,
                        "total": total_percentage,
                    }
                )
