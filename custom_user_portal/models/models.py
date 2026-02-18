import logging
from odoo import _, models, fields, api
from odoo.exceptions import ValidationError
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta

_logger = logging.getLogger(__name__)


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
    required_date = fields.Date(string="Required Date", readonly=True)
    priority = fields.Selection(
        [("low", "Low"), ("medium", "Medium"), ("high", "High"), ("urgent", "Urgent")],
        string="Priority",
        required=True,
        default="medium",
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
        string="Can Approve",
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

    def _required_date_from_priority(self, priority):
        today = fields.Date.context_today(self)
        offsets = {
            "low": 30,
            "medium": 10,
            "high": 3,
            "urgent": 0,
        }
        return today + relativedelta(days=offsets.get(priority, 0))

    @api.onchange("priority")
    def _onchange_priority_set_required_date(self):
        for rec in self:
            if rec.priority:
                rec.required_date = rec._required_date_from_priority(rec.priority)

    @api.model
    def create(self, vals):
        if vals.get("priority"):
            vals["required_date"] = self._required_date_from_priority(vals["priority"])
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

    # Checking when PR is approved
    def write(self, vals):
        if vals.get("priority"):
            vals["required_date"] = self._required_date_from_priority(vals["priority"])

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
            approver_users = self.env["res.users"]
            group = self.env.ref("custom_pr_system.group_pr_approver", raise_if_not_found=False)
            if group:
                approver_users = self.env["res.users"].sudo().search(
                    [("groups_id", "in", group.id)]
                )

            if self.supervisor_partner_id and str(self.supervisor_partner_id).isdigit():
                partner_id = int(self.supervisor_partner_id)
                supervisor_user = (
                    self.env["res.users"]
                    .sudo()
                    .search([("partner_id", "=", partner_id)], limit=1)
                )
                if supervisor_user:
                    approver_users |= supervisor_user

            approver_users = approver_users.filtered(lambda u: u.active)
            if not approver_users:
                _logger.warning("No PR approver users found for PR=%s", self.name)
                return

            for approver in approver_users:
                self.activity_schedule(
                    activity_type_id=self.env.ref("mail.mail_activity_data_todo").id,
                    user_id=approver.id,
                    summary="Review New PR",
                    note=_("Please review the new Purchase Requisition: <b>%s</b>.")
                    % self.name,
                )

            _logger.info("Activity created for %s approver(s) on PR=%s", len(approver_users), self.name)

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
            except (ValueError, TypeError):
                supervisor_partner_id = 0

            current_user = rec.env.user
            current_partner_id = current_user.partner_id.id if current_user.partner_id else 0
            has_approver_group = current_user.has_group("custom_pr_system.group_pr_approver")

            rec.is_supervisor = has_approver_group or (
                supervisor_partner_id == current_partner_id
            )


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

    @api.constrains("quantity", "unit_price")
    def _check_non_negative_values(self):
        for rec in self:
            if rec.quantity < 0:
                raise ValidationError("Quantity cannot be negative.")
            if rec.unit_price < 0:
                raise ValidationError("Unit Price cannot be negative.")


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

    @api.constrains("quantity", "price_unit")
    def _check_non_negative_subtotal_inputs(self):
        for line in self:
            if line.quantity < 0:
                raise ValidationError("Quantity cannot be negative.")
            if line.price_unit < 0:
                raise ValidationError("Unit Price cannot be negative.")