import logging
from odoo import _, models, fields, api
from odoo.exceptions import ValidationError
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PurchaseCostCenterBudget(models.Model):
    _name = "purchase.cost.center.budget"
    _description = "Purchase Cost Center Budget"
    _rec_name = "code"

    code = fields.Char(string="Cost Center Code", required=True, index=True)
    name = fields.Char(string="Name")
    budget_type = fields.Selection(
        [("opex", "Opex"), ("capex", "Capex")],
        string="Budget Type",
        required=True,
    )
    budget_allowance = fields.Float(string="Budget Allowance", required=True)
    budget_spent = fields.Float(string="Budget Spent", compute="_compute_budget_spent", store=False)
    budget_left = fields.Float(string="Budget Left", compute="_compute_budget_spent", store=False)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "unique_budget_per_type_code",
            "unique(code, budget_type)",
            "Cost Center Code must be unique per Budget Type.",
        )
    ]

    @api.depends("budget_allowance")
    def _compute_budget_spent(self):
        PurchaseOrder = self.env["purchase.order"].sudo()
        for rec in self:
            pos = PurchaseOrder.search([
                ("budget_type", "=", rec.budget_type),
                ("budget_code", "=", rec.code),
                ("state", "in", ["purchase", "done"]),
            ])
            spent = sum(pos.mapped("grand_total"))
            rec.budget_spent = spent
            rec.budget_left = rec.budget_allowance - spent




class PurchaseRequisition(models.Model):
    _name = "purchase.requisition"
    _description = "Purchase Requisition"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name desc"

    name = fields.Char(
        string="PR Number", required=True, copy=False, readonly=True, default="New"
    )
    date_request = fields.Date(
        string="Date of Request", default=fields.Date.context_today
    )
    requested_by = fields.Char(string="Requested By")
    department = fields.Char(string="Department")
    supervisor = fields.Char(string="Supervisor")
    supervisor_partner_id = fields.Char(string="supervisor_partner_id")
    required_date = fields.Date(string="Required Date")
    priority = fields.Selection(
        [("low", "Low"), ("medium", "Medium"), ("high", "High"), ("urgent", "Urgent")],
        string="Priority",
    )
    budget_type = fields.Selection(
        [("opex", "Opex"), ("capex", "Capex")], string="Budget Type"
    )
    budget_details = fields.Char(string="Cost Center Code")
    notes = fields.Text(string="Notes")
    approval = fields.Selection(
        [("pending", "Pending"), ("rejected", "Rejected"), ("approved", "Approved")],
        default="pending",
        string="Approval",
    )
    comments = fields.Text(string="Comments")
    vendor_id = fields.Many2one("res.partner", string="Preferred Vendor")
    total_excl_vat = fields.Float(
        string="Total Amount",
        compute="_compute_totals",
        store=True,
        currency_field="currency_id",
    )
    vat_amount = fields.Float(
        string="VAT (15%)",
        compute="_compute_totals",
        store=True,
        currency_field="currency_id",
    )
    total_incl_vat = fields.Float(
        string="Total Incl. VAT",
        compute="_compute_totals",
        store=True,
        currency_field="currency_id",
    )
    pr_type = fields.Selection(
        [
            ("pr", "PR"),
            ("cash", "Cash PR"),
        ],
        string="Type",
        default="pr",
    )
    is_supervisor = fields.Boolean(
        string="Is Supervisor",
        compute="_compute_is_supervisor",
    )
    status = fields.Selection(
        [("pr", "Pr"), ("rfq", "Rfq")],
        default="pr",
        string="PR Status",
    )
    line_ids = fields.One2many(
        "purchase.requisition.line", "requisition_id", string="Line Items"
    )

    # Computed fields for button visibility logic
    show_create_rfq_button = fields.Boolean(
        compute="_compute_button_visibility", store=False
    )
    show_create_po_button = fields.Boolean(
        compute="_compute_button_visibility", store=False
    )

    @api.model
    def create(self, vals):
        record = super().create(vals)
        if record.name == "New":
            if record.pr_type == "cash":
                record.name = (
                    self.env["ir.sequence"]
                    .sudo()
                    .next_by_code("cash.purchase.requisition")
                    or "CPR0001"
                )
            else:
                record.name = (
                    self.env["ir.sequence"].sudo().next_by_code("purchase.requisition")
                    or "PR0001"
                )
        record._notify_supervisor()
        return record

    @api.model
    def _get_budget_bucket(self, budget_type, budget_code):
        budget_code = (budget_code or "").strip()
        if not budget_type or not budget_code:
            return False

        cost_center_budget = self.env["purchase.cost.center.budget"].sudo().search([
            ("budget_type", "=", budget_type),
            ("code", "=", budget_code),
            ("active", "=", True),
        ], limit=1)
        if cost_center_budget:
            return {
                "source": "cost_center",
                "record": cost_center_budget,
                "budget_left": cost_center_budget.budget_left,
            }

        project = self.env["project.project"].sudo().search([
            ("budget_type", "=", budget_type),
            ("budget_code", "=", budget_code),
        ], limit=1)
        if project:
            return {
                "source": "project",
                "record": project,
                "budget_left": project.budget_left,
            }

        return False

    @api.model
    def validate_budget_for_amount(self, budget_type, budget_code, amount):
        bucket = self._get_budget_bucket(budget_type, budget_code)
        amount = float(amount or 0.0)

        if not budget_type or not (budget_code or "").strip():
            return {
                "success": False,
                "message": "Missing budget type or budget code.",
                "budget_left": 0.0,
                "source": False,
            }

        if not bucket:
            return {
                "success": False,
                "message": "No budget source found for given budget type and cost center code.",
                "budget_left": 0.0,
                "source": False,
            }

        budget_left = float(bucket["budget_left"] or 0.0)
        if budget_left < amount:
            return {
                "success": False,
                "message": f"Budget exceeded. Required {amount:.2f}, available {budget_left:.2f}.",
                "budget_left": budget_left,
                "source": bucket["source"],
            }

        return {
            "success": True,
            "message": f"Budget available: {budget_left}",
            "budget_left": budget_left,
            "source": bucket["source"],
        }

    # Checking when PR is approved
    def write(self, vals):
        approval_changed = "approval" in vals
        res = super().write(vals)

        if approval_changed:
            for requisition in self:
                new_approval = vals.get("approval", requisition.approval)
                custom_pr = (
                    self.env["custom.pr"]
                    .sudo()
                    .search([("name", "=", requisition.name)], limit=1)
                )

                if custom_pr:
                    # Sync approval → state
                    if new_approval == "approved" and custom_pr.approval != "approved":
                        custom_pr.write(
                            {"approval": "approved", "approval": "approved"}
                        )
                        self._notify_procurement_admins()

                    elif (
                        new_approval == "rejected" and custom_pr.approval != "rejected"
                    ):
                        custom_pr.write(
                            {"approval": "rejected", "approval": "rejected"}
                        )

                    elif new_approval == "pending" and custom_pr.approval != "pending":
                        custom_pr.write({"approval": "pending", "approval": "pending"})

        return res

    @api.depends("line_ids.total_price")
    def _compute_totals(self):
        for rec in self:
            total = sum(line.total_price for line in rec.line_ids)
            rec.total_excl_vat = total
            rec.vat_amount = total * 0.15
            rec.total_incl_vat = total + rec.vat_amount

    @api.depends("pr_type", "approval", "status")
    def _compute_button_visibility(self):
        """Compute button visibility based on PR type, approval, and status"""
        for rec in self:
            rec.show_create_rfq_button = (
                rec.pr_type != "cash"
                and rec.approval == "approved"
                and rec.status == "pr"
            )

            rec.show_create_po_button = (
                rec.pr_type == "cash"
                and rec.approval == "approved"
                and rec.status in ["pr", "rfq"]
            )

    # sending activity to specific manager when PR is created
    def _notify_supervisor(self):
        try:
            if self.supervisor_partner_id and self.supervisor_partner_id.isdigit():
                partner_id = int(self.supervisor_partner_id)

                supervisor_user = (
                    self.env["res.users"]
                    .sudo()
                    .search([("partner_id", "=", partner_id)], limit=1)
                )

                if not supervisor_user:
                    _logger.warning(
                        "Supervisor user not found for partner_id=%s", partner_id
                    )
                    return

                self.activity_schedule(
                    activity_type_id=self.env.ref("mail.mail_activity_data_todo").id,
                    user_id=supervisor_user.id,
                    summary="Review New PR",
                    note=_("Please review the new Purchase Requisition: <b>%s</b>.")
                    % self.name,
                )

                _logger.info(
                    "Activity created for supervisor user_id=%s on PR=%s",
                    supervisor_user.id,
                    self.name,
                )

        except Exception as e:
            _logger.error("Error creating activity for PR=%s: %s", self.name, str(e))

    # sending approved PR activity to procurment admin
    def _notify_procurement_admins(self):
        for pr in self:
            try:
                group = self.env.ref(
                    "custom_user_portal.procurement_admin"
                )  # 🔁 Replace
                procurement_users = (
                    self.env["res.users"].sudo().search([("groups_id", "in", group.id)])
                )
                activity_type_id = self.env.ref("mail.mail_activity_data_todo").id

                for user in procurement_users:
                    pr.activity_schedule(
                        activity_type_id=activity_type_id,
                        user_id=user.id,
                        summary="New Approved PR",
                        note=_(
                            "A new Purchase Requisition <b>%s</b> has been approved."
                        )
                        % pr.name,
                    )

                _logger.info(
                    "Activities scheduled for Procurement Admins on PR=%s", pr.name
                )

            except Exception as e:
                _logger.error(
                    "Error creating procurement admin activities for PR=%s: %s",
                    pr.name,
                    str(e),
                )

    # create RFQ PR
    # def action_create_rfq(self):
    #     """Create RFQ (purchase.order) from this PR and populate Custom Lines tab."""
    #     PurchaseOrder = self.env["purchase.order"]

    #     for pr in self:
    #         if not pr.line_ids:
    #             raise UserError(_("This PR has no line items to create an RFQ."))

    #         matched_project = self.env["project.project"].search(
    #             [
    #                 ("budget_type", "=", pr.budget_type),
    #                 ("budget_code", "=", pr.budget_details),
    #             ],
    #             limit=1,
    #         )

    #         # Create RFQ without normal order_line
    #         rfq_vals = {
    #             "origin": pr.name,
    #             "partner_id": pr.vendor_id.id if pr.vendor_id else False,
    #             'pr_name': self.name,
    #             "date_planned": pr.required_date,
    #             "project_id": matched_project.id if matched_project else False,
    #             "custom_line_ids": [],  # Populate custom tab instead
    #             "date_request": pr.date_request,
    #             "requested_by": pr.requested_by,
    #             "department": pr.department,
    #             "supervisor": pr.supervisor,
    #             "supervisor_partner_id": pr.supervisor_partner_id,
    #         }

    #         # Fill custom_line_ids from PR lines
    #         for line in pr.line_ids:
    #             line_vals = (
    #                 0,
    #                 0,
    #                 {
    #                     "name": line.description,
    #                     "quantity": line.quantity,
    #                     "type": line.type,
    #                     "unit": line.unit,  # ✅ Added this
    #                     "price_unit": line.unit_price,
    #                 },
    #             )
    #             rfq_vals["custom_line_ids"].append(line_vals)

    #         # Create RFQ
    #         rfq = PurchaseOrder.sudo().create(rfq_vals)

    #         # sequence for Rfq
    #         if rfq.state == "draft":
    #             rfq.name = (
    #                 self.env["ir.sequence"].next_by_code("purchase.order.rfq")
    #                 or "RFQ0001"
    #             )

    #         # Update PR status
    #         pr.status = "rfq"

    #         # Log in PR chatter
    #         pr.message_post(
    #             body=_("RFQ %s created from this PR and populated in Custom Lines tab.")
    #             % rfq.name,
    #             message_type="notification",
    #         )

    #     return {
    #         "type": "ir.actions.act_window",
    #         "name": _("Purchase Order"),
    #         "res_model": "purchase.order",
    #         "res_id": rfq.id,
    #         "view_mode": "form",
    #         "target": "current",
    #     }
    def action_create_rfq(self):
        """Create RFQ (purchase.order) from this PR and populate Custom Lines tab."""
        PurchaseOrder = self.env["purchase.order"]
        MailMessage = self.env["mail.message"]

        for pr in self:
            if not pr.line_ids:
                raise UserError(_("This PR has no line items to create an RFQ."))

            matched_project = self.env["project.project"].search(
                [
                    ("budget_type", "=", pr.budget_type),
                    ("budget_code", "=", pr.budget_details),
                ],
                limit=1,
            )

            # Create RFQ without normal order_line
            rfq_vals = {
                "origin": pr.name,
                "partner_id": pr.vendor_id.id if pr.vendor_id else False,
                "pr_name": pr.name,
                "date_planned": pr.required_date,
                "project_id": matched_project.id if matched_project else False,
                "custom_line_ids": [],  # Populate custom tab instead
                "date_request": pr.date_request,
                "requested_by": pr.requested_by,
                "department": pr.department,
                "supervisor": pr.supervisor,
                "supervisor_partner_id": pr.supervisor_partner_id,
            }

            # Fill custom_line_ids from PR lines
            for line in pr.line_ids:
                line_vals = (
                    0,
                    0,
                    {
                        # "name": line.description.display_name,
                        "name": line.description.name,
                        "quantity": line.quantity,
                        "type": line.type,
                        "unit": line.unit,
                        "price_unit": line.unit_price,
                    },
                )
                rfq_vals["custom_line_ids"].append(line_vals)

            # Create RFQ (use sudo if you want to bypass access issues)
            rfq = PurchaseOrder.sudo().create(rfq_vals)

            # Give proper sequence if needed
            if rfq.state == "draft":
                rfq_name = (
                    self.env["ir.sequence"].sudo().next_by_code("purchase.order.rfq")
                    or "RFQ0001"
                )
                # use write so rules are respected
                rfq.sudo().write({"name": rfq_name})

            # ---- NEW: remove default 'purchase order created' system message(s) on RFQ chatter ----
            try:
                msgs = MailMessage.sudo().search(
                    [("model", "=", "purchase.order"), ("res_id", "=", rfq.id)]
                )
                # narrow deletion only to messages that clearly look like "Purchase order ... created"
                msgs_to_unlink = msgs.filtered(
                    lambda m: m.body and "purchase order" in (m.body or "").lower() and "created" in (m.body or "").lower()
                )
                if msgs_to_unlink:
                    msgs_to_unlink.sudo().unlink()
            except Exception as e:
                _logger.exception(
                    "Failed to remove default purchase.order messages for RFQ %s: %s", rfq.id, e
                )

            # Post a clear RFQ message on the RFQ itself (so RFQ chatter shows RFQ created)
            rfq.sudo().message_post(
                body=_("RFQ %s Created")
                % rfq.name,
                message_type="notification",
            )
            # ---- END new logic ----

            # Update PR status
            pr.status = "rfq"

            # Log in PR chatter (keep PR message)
            pr.message_post(
                body=_("RFQ %s created from this PR and populated in Custom Lines tab.")
                % rfq.name,
                message_type="notification",
            )

        return {
            "type": "ir.actions.act_window",
            "name": _("Purchase Order"),
            "res_model": "purchase.order",
            "res_id": rfq.id,
            "view_mode": "form",
            "target": "current",
        }

    # create cash PR
    def action_create_purchase_order(self):
        """Create Purchase Order directly (confirmed) from this PR and populate Custom Lines tab."""
        PurchaseOrder = self.env["purchase.order"]

        for pr in self:
            if not pr.line_ids:
                raise UserError(
                    _("This PR has no line items to create a Purchase Order.")
                )

            matched_project = self.env["project.project"].search(
                [
                    ("budget_type", "=", pr.budget_type),
                    ("budget_code", "=", pr.budget_details),
                ],
                limit=1,
            )

            # Create PO values
            po_vals = {
                "origin": pr.name,
                "partner_id": pr.vendor_id.id if pr.vendor_id else False,
                "date_planned": pr.required_date,
                "project_id": matched_project.id if matched_project else False,
                "custom_line_ids": [],
                "date_request": pr.date_request,
                "requested_by": pr.requested_by,
                "department": pr.department,
                "supervisor": pr.supervisor,
                "supervisor_partner_id": pr.supervisor_partner_id,
            }

            # Fill custom_line_ids from PR lines
            for line in pr.line_ids:
                line_vals = (
                    0,
                    0,
                    {
                        # "name": line.description.display_name,
                        "name": line.description.name,
                        "quantity": line.quantity,
                        "type": line.type,
                        "unit": line.unit,
                        "price_unit": line.unit_price,
                    },
                )
                po_vals["custom_line_ids"].append(line_vals)

            # Create Purchase Order
            po = PurchaseOrder.sudo().create(po_vals)

            # Confirm it → changes state from draft (RFQ) to purchase
            po.button_confirm()
            # Update PR status
            pr.status = "rfq"
            # Log in PR chatter
            pr.message_post(
                body=_(
                    "Purchase Order %s created and confirmed from this PR (Custom Lines populated)."
                )
                % po.name,
                message_type="notification",
            )

        return {
            "type": "ir.actions.act_window",
            "name": _("Purchase Order"),
            "res_model": "purchase.order",
            "res_id": po.id,
            "view_mode": "form",
            "target": "current",
        }

    # check user if he/she is supervisor
    @api.depends("supervisor_partner_id")
    def _compute_is_supervisor(self):
        for rec in self:
            try:
                supervisor_partner_id = (
                    int(rec.supervisor_partner_id) if rec.supervisor_partner_id else 0
                )
            except ValueError:
                supervisor_partner_id = 0

            current_partner_id = (
                self.env.user.partner_id.id if self.env.user.partner_id else 0
            )

            rec.is_supervisor = supervisor_partner_id == current_partner_id


class PurchaseRequisitionLine(models.Model):
    _name = "purchase.requisition.line"
    _description = "Purchase Requisition Line"

    requisition_id = fields.Many2one(
        "purchase.requisition", string="Requisition", ondelete="cascade"
    )
    description = fields.Many2one(
        'product.product',
        string="Product",
        required=True,
        ondelete="restrict",
        context={'display_default_code': False},
    )

    type = fields.Char(string="Type")
    quantity = fields.Float(string="Quantity")
    unit = fields.Char(string="Unit")
    unit_price = fields.Float(string="Unit Price")
    total_price = fields.Float(string="Total", compute="_compute_total", store=True)

    @api.depends("quantity", "unit_price")
    def _compute_total(self):
        for rec in self:
            rec.total_price = rec.quantity * rec.unit_price


class PurchaseQuotation(models.Model):
    _inherit = "purchase.order"

    project_id = fields.Many2one("project.project", string="Project")
    budget_type = fields.Selection(
        [("opex", "Opex"), ("capex", "Capex")], string="Budget Type"
    )

    budget_code = fields.Char(string="Budget Code")
    project_id = fields.Many2one("project.project", string="Project")


class PurchaseOrderCustomLine(models.Model):
    _name = "purchase.order.custom.line"
    _description = "Custom Purchase Order Line"

    order_id = fields.Many2one(
        "purchase.order", string="Purchase Order", ondelete="cascade"
    )
    name = fields.Char(string="Description")
    quantity = fields.Float(string="Quantity")
    unit = fields.Char(string="Unit")
    type = fields.Selection(
        [
            ('material', 'Material'),
            ('service', 'Service')
        ],
        string="Type",
        default='material',
        required=True
    )
    price_unit = fields.Float(string="Unit Price")
    subtotal = fields.Float(string="Subtotal", compute="_compute_subtotal", store=True)

    @api.depends("quantity", "price_unit")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.price_unit
