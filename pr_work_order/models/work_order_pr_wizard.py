from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class WorkOrderCreatePRWizard(models.TransientModel):
    _name = "pr.work.order.create.pr.wizard"
    _description = "Create PR from Work Order"

    work_order_id = fields.Many2one("pr.work.order", required=True, readonly=True)
    priority = fields.Selection(
        [("low", "Low"), ("medium", "Medium"), ("high", "High"), ("urgent", "Urgent")],
        string="Priority",
        required=True,
        default="medium",
    )
    notes = fields.Text(string="Notes")
    line_ids = fields.One2many(
        "pr.work.order.create.pr.wizard.line",
        "wizard_id",
        string="Products",
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)

        work_order_id = self.env.context.get("default_work_order_id")
        if not work_order_id:
            return values

        # Use sudo for BOQ preload so readonly wizard lines are fully populated
        # even when the opener has limited read rights on related models.
        work_order = self.env["pr.work.order"].sudo().browse(work_order_id)
        lines = []
        for boq_line in work_order.boq_line_ids.filtered(
            lambda l: l.display_type not in ("line_section", "line_note") and l.product_id and l.qty > 0
        ):
            cc = work_order.cost_center_ids.filtered(lambda c: c.section_name == boq_line.section_name)[:1]
            lines.append(
                (
                    0,
                    0,
                    {
                        "selected": False,
                        "cost_center_id": cc.analytic_account_id.id if cc and cc.analytic_account_id else False,
                        "quantity": boq_line.qty,
                        "unit_id": boq_line.uom_id.id,
                        "unit_price": boq_line.unit_cost,
                        "boq_line_id": boq_line.id,
                    },
                )
            )

        values["line_ids"] = lines
        return values

    def action_create_pr(self):
        self.ensure_one()

        if not self.env.user.has_group("pr_custom_purchase.group_custom_pr_end_user"):
            raise UserError(_("Only End Users can create PR from Work Order."))

        if self.work_order_id.state not in ["acc_approval", "final_approval", "approved", "in_progress", "done"]:
            raise UserError(_("PR can be created only after Operations approval."))

        selected_lines = self.line_ids.filtered("selected")
        if not selected_lines:
            raise ValidationError(_("Please select at least one product to create PR."))

        commands = []
        for line in selected_lines:
            product = line.product_id or line.boq_line_id.product_id
            if not product:
                raise ValidationError(
                    _("Selected line has no product. Please refresh and try again.")
                )
            if not line.cost_center_id:
                raise ValidationError(
                    _("Please set a Cost Center for product '%s'.") % product.display_name
                )
            commands.append(
                (
                    0,
                    0,
                    {
                        "description": product.id,
                        "cost_center_id": line.cost_center_id.id,
                        "quantity": line.quantity,
                        "unit": line.unit_id.id,
                        "unit_price": line.unit_price,
                    },
                )
            )

        custom_pr = self.env["custom.pr"].create(
            {
                "pr_type": "standard",
                "priority": self.priority,
                "notes": self.notes,
                "line_ids": commands,
            }
        )

        return {
            "type": "ir.actions.act_window",
            "name": _("Purchase Requisition"),
            "res_model": "custom.pr",
            "res_id": custom_pr.id,
            "view_mode": "form",
            "target": "current",
        }


class WorkOrderCreatePRWizardLine(models.TransientModel):
    _name = "pr.work.order.create.pr.wizard.line"
    _description = "Create PR from Work Order Line"

    wizard_id = fields.Many2one("pr.work.order.create.pr.wizard", required=True, ondelete="cascade")
    selected = fields.Boolean(string="Select")
    boq_line_id = fields.Many2one("pr.work.order.boq", string="BOQ Line", readonly=True, required=True)
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        related="boq_line_id.product_id",
        readonly=True,
    )
    cost_center_id = fields.Many2one("account.analytic.account", string="Cost Center", required=True)
    quantity = fields.Float(string="Quantity", required=True)
    unit_id = fields.Many2one("uom.uom", string="Unit", required=True)
    unit_price = fields.Float(string="Unit Cost", required=True)
