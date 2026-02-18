from odoo import models, fields, api, _
from odoo.exceptions import AccessError
from odoo.exceptions import UserError

import logging

_logger = logging.getLogger(__name__)


class PurchaseQuotation(models.Model):
    _name = "purchase.quotation"
    _description = "Purchase Quotation"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    # Basic Info
    vendor_id = fields.Many2one("res.partner", string="Vendor")
    rfq_origin = fields.Char(string="RFQ Origin")
    vendor_ref = fields.Char(string="Vendor Reference")
    pr_name = fields.Char(string="PR Name", readonly=True)
    notes = fields.Text(string="Notes")
    order_deadline = fields.Datetime(string="Deadline")
    expected_arrival = fields.Datetime(string="Quotation Date")

    # Supplier Info
    supplier_name = fields.Char(string="Supplier Name")
    contact_person = fields.Char(string="Contact Person")
    company_address = fields.Char(string="Company Address")
    phone_number = fields.Char(string="Phone Number")
    email_address = fields.Char(string="Email Address")
    supplier_id = fields.Char(string="Supplier ID")
    quotation_ref = fields.Char(string="Quotation Reference")
    # Reason tab field for end user/supervisor workflow
    rejection_reason = fields.Text(string="Reason for Rejection")

    # Payment Terms
    terms_net = fields.Boolean("Net")
    terms_30days = fields.Boolean("30 Days")
    terms_advance = fields.Boolean("Advance %")
    terms_advance_specify = fields.Char("Specify Advance Terms")
    terms_delivery = fields.Boolean("On Delivery")
    terms_other = fields.Boolean("Other")
    terms_others_specify = fields.Char("Specify Other Terms")

    # Production / Material Availability
    ex_stock = fields.Boolean("Ex-Stock")
    required_days = fields.Boolean("Production Required")
    production_days = fields.Char("Production Days Needed")

    # Delivery Terms
    ex_work = fields.Boolean("Ex-Works")
    delivery_site = fields.Boolean("Site Delivery")

    # Delivery Date Expected
    delivery_date = fields.Date("Expected Delivery Date")

    # Delivery Method
    delivery_courier = fields.Boolean("Courier")
    delivery_pickup = fields.Boolean("Pickup")
    delivery_freight = fields.Boolean("Freight")
    delivery_others = fields.Boolean("Other")
    delivery_others_specify = fields.Char("Specify Other Delivery")

    # Partial Order Acceptance
    partial_yes = fields.Boolean("Partial Order Acceptable")
    partial_no = fields.Boolean("Partial Order Not Acceptable")

    # total
    total_excl_vat = fields.Float(
        string="Total Amount", compute="_compute_totals", store=True
    )
    vat_amount = fields.Float(
        string="VAT Amount @ 15%", compute="_compute_totals", store=True
    )
    total_incl_vat = fields.Float(
        string="Total Amount Including VAT", compute="_compute_totals", store=True
    )
    is_best = fields.Boolean(
        string="Best Quotation", compute="_compute_is_best", store=True
    )
    is_best_badge = fields.Char(
        string="Best Quotation", compute="_compute_is_best_badge", store=False
    )

    # budget
    budget_type = fields.Selection(
        [("opex", "Opex"), ("capex", "Capex")],
        string="Budget Type",
    )
    budget_code = fields.Char(string="Budget Code")
    cost_center_id = fields.Many2one("account.analytic.account", string="Cost Center", compute="_compute_cost_center", store=False)
    project_budget_allowance = fields.Float(
        string="Budget Allowance",
        compute="_compute_cost_center",
        store=False,
    )
    budget_left = fields.Float(
        string="Budget Left", compute="_compute_cost_center", store=False
    )
    status = fields.Selection(
        [("quote", "Quote"), ("po", "Purchase")],
        default="quote",
        string="Status",
    )

    show_create_po_button = fields.Boolean(
        compute="_compute_button_visibility", store=False
    )
    #PR Info
    requested_by = fields.Char(string="Requested By")
    department = fields.Char(string="Department")
    supervisor = fields.Char(string="Supervisor")
    supervisor_partner_id = fields.Char(string="supervisor_partner_id")

    # Lines
    line_ids = fields.One2many(
        "purchase.quotation.line", "quotation_id", string="Quotation Lines"
    )


    @api.depends("budget_type", "budget_code")
    def _compute_cost_center(self):
        CostCenter = self.env["account.analytic.account"].sudo()
        for rec in self:
            cc = CostCenter.search([
                ("budget_type", "=", rec.budget_type),
                ("budget_code", "=", rec.budget_code),
            ], limit=1) if rec.budget_type and rec.budget_code else False
            rec.cost_center_id = cc.id if cc else False
            rec.project_budget_allowance = cc.budget_allowance if cc else 0.0
            rec.budget_left = cc.budget_left if cc else 0.0

    @api.depends("line_ids.price_unit", "line_ids.quantity")
    def _compute_totals(self):
        for record in self:
            total_excl = sum(
                line.price_unit * line.quantity for line in record.line_ids
            )
            record.total_excl_vat = total_excl
            record.vat_amount = total_excl * 0.15
            record.total_incl_vat = total_excl + record.vat_amount

    @api.depends("rfq_origin", "total_excl_vat")
    def _compute_is_best(self):
        """Ensure only the quotation with the lowest total_excl_vat per RFQ is marked as best."""
        # Fetch all relevant rfq_origin values in current batch
        rfq_origins = self.mapped("rfq_origin")
        if not rfq_origins:
            return

        # Fetch all quotations sharing those RFQs (even outside current batch)
        all_quotations = self.env["purchase.quotation"].search([("rfq_origin", "in", rfq_origins)])

        # Group them by rfq_origin
        rfq_groups = {}
        for rec in all_quotations:
            rfq_groups.setdefault(rec.rfq_origin, []).append(rec)

        # Determine the best for each group
        for group in rfq_groups.values():
            valid_records = [r for r in group if r.total_excl_vat > 0]
            if not valid_records:
                continue

            # Find the one with minimum total_excl_vat
            min_rec = min(valid_records, key=lambda r: r.total_excl_vat)

            # Reset all to False first
            for r in group:
                r.is_best = False

            # Then mark only the minimum one as True
            min_rec.is_best = True

    @api.depends("is_best")
    def _compute_is_best_badge(self):
        for rec in self:
            rec.is_best_badge = "Best" if rec.is_best else ""

    @api.depends("status")
    def _compute_button_visibility(self):
        """Button visible only if status is 'quote'
        AND no PO exists in pending/purchase state."""
        for rec in self:
            show_button = False
            if rec.status == "quote":
                po_exists = self.env["purchase.order"].search_count(
                    [
                        ("origin", "=", rec.rfq_origin),
                        ("state", "in", ["pending", "purchase"]),
                    ]
                )
                show_button = po_exists == 0
            rec.show_create_po_button = show_button

    # create purchase order
    def action_create_purchase_order(self):
        """Create Purchase Order from this Quotation in pending state with Custom Lines."""
        PurchaseOrder = self.env["purchase.order"]

        if self.budget_left < self.total_incl_vat:
            raise UserError(
                "Insufficient budget. You cannot proceed with Purchase Order creation."
            )

        for quotation in self:
            if not quotation.line_ids:
                raise UserError(
                    _("This Quotation has no line items to create a Purchase Order.")
                )

            cost_center = self.env["account.analytic.account"].sudo().search(
                [
                    ("budget_type", "=", quotation.budget_type),
                    ("budget_code", "=", quotation.budget_code),
                ],
                limit=1,
            )
            if not cost_center:
                raise UserError(_("No cost center found for this quotation budget type/code."))

            # Purchase Order values
            po_vals = {
                "origin": quotation.rfq_origin,
                "partner_id": quotation.vendor_id.id if quotation.vendor_id else False,
                "partner_ref": quotation.vendor_ref or "",
                "date_planned": quotation.delivery_date or fields.Datetime.now(),
                "budget_type": quotation.budget_type,
                "budget_code": quotation.budget_code,
                "custom_line_ids": [],
                "state": "pending",
                "pr_name": self.pr_name,
                "requested_by": quotation.requested_by,
                "department": quotation.department,
                "supervisor": quotation.supervisor,
                "supervisor_partner_id": quotation.supervisor_partner_id,

            }

            # Fill lines from Quotation Lines
            for line in quotation.line_ids:
                line_vals = (
                    0,
                    0,
                    {
                        "name": line.description or line.name,
                        "quantity": line.quantity,
                        "type": line.type,
                        "unit": line.unit,
                        "price_unit": line.price_unit,
                    },
                )
                po_vals["custom_line_ids"].append(line_vals)

            # Create Purchase Order
            po = PurchaseOrder.sudo().create(po_vals)
            quotation.status = "po"

            # Log in chatter
            quotation.message_post(
                body=_(
                    "Purchase Order %s created from this Quotation and populated in Custom Lines tab."
                )
                % po.name,
                message_type="notification",
            )

        # 🔥 Approval workflow: assign reviewers based on amount
        amount = quotation.total_incl_vat
        group_xml_ids = []

        if amount <= 10000:
            group_xml_ids = ["custom_user_portal.project_engineer"]
        elif amount <= 100000:
            group_xml_ids = [
                "custom_user_portal.project_engineer",
                "custom_user_portal.project_manager",
            ]
        elif amount <= 500000:
            group_xml_ids = [
                "custom_user_portal.project_engineer",
                "custom_user_portal.project_manager",
                "custom_user_portal.operations_director",
            ]
        else:
            group_xml_ids = [
                "custom_user_portal.project_engineer",
                "custom_user_portal.project_manager",
                "custom_user_portal.operations_director",
                "custom_user_portal.managing_director",
            ]

        for group_xml_id in group_xml_ids:
            group = self.env.ref(group_xml_id)
            for user in group.users:
                self.env["mail.activity"].create(
                    {
                        "res_model_id": self.env["ir.model"]._get("purchase.order").id,
                        "res_id": po.id,
                        "activity_type_id": self.env.ref(
                            "mail.mail_activity_data_todo"
                        ).id,
                        "summary": "Review Purchase Order",
                        "user_id": user.id,
                        "note": f"Please review the Purchase Order for {po.name}.",
                        "date_deadline": fields.Date.today(),
                    }
                )

        return {
            "type": "ir.actions.act_window",
            "name": "Purchase Order",
            "res_model": "purchase.order",
            "res_id": po.id,
            "view_mode": "form",
            "target": "current",
        }

    @api.model
    def create(self, vals):
        record = super(PurchaseQuotation, self).create(vals)

        # Always target procurement_admin group
        procurement_admin_group = self.env.ref(
            "custom_user_portal.procurement_admin", raise_if_not_found=False
        )

        if procurement_admin_group:
            for user in procurement_admin_group.users:
                record.activity_schedule(
                    "mail.mail_activity_data_todo",
                    summary="New Purchase Quotation Created",
                    note=f"A new purchase quotation (ID: {record.id}) has been created "
                    f"with a total amount of {record.total_incl_vat:.2f}.",
                    user_id=user.id,
                )

        return record


class PurchaseQuotationLine(models.Model):
    _name = "purchase.quotation.line"
    _description = "Purchase Quotation Line"

    quotation_id = fields.Many2one(
        "purchase.quotation", string="Quotation", ondelete="cascade"
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
    tax_15 = fields.Float(string="15% Tax", compute="_compute_subtotal", store=True)
    grand_total = fields.Float(
        string="Grand Total", compute="_compute_subtotal", store=True
    )
    description = fields.Char(string="Description")

    @api.depends("quantity", "price_unit")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.price_unit
            line.tax_15 = line.subtotal * 0.15
            line.grand_total = line.subtotal + line.tax_15


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("sent", "RFQ Sent"),
            ("pending", "Pending Approval"),
            ("purchase", "Purchase Order"),
            ("done", "Locked"),
            ("cancel", "Cancelled"),
        ],
        string="Status",
        tracking=True,
    )
    project_id = fields.Many2one("project.project", string="Project")
    pe_approved = fields.Boolean(string="Approved", default=False)
    pm_approved = fields.Boolean(string="Approved", default=False)
    od_approved = fields.Boolean(string="Approved", default=False)
    md_approved = fields.Boolean(string="Approved", default=False)
    can_confirm_order = fields.Boolean(
        compute="_compute_can_confirm_order", store=False
    )
    # Computed fields for view visibility
    show_pe_approved = fields.Boolean(compute="_compute_show_approvals", store=False)
    show_pm_approved = fields.Boolean(compute="_compute_show_approvals", store=False)
    show_od_approved = fields.Boolean(compute="_compute_show_approvals", store=False)
    show_md_approved = fields.Boolean(compute="_compute_show_approvals", store=False)
    # Track which users already acted (approved/rejected) so we can hide buttons for them only
    approval_action_user_ids = fields.Many2many(
        "res.users",
        "purchase_order_approval_action_user_rel",
        "order_id",
        "user_id",
        string="Users Who Acted",
        copy=False,
    )
    current_user_has_acted = fields.Boolean(
        compute="_compute_current_user_has_acted", store=False
    )
    subtotal = fields.Float(
        string="Subtotal", compute="_compute_amount_untaxed_custom", store=True
    )
    tax_15 = fields.Float(
        string="15% Tax", compute="_compute_amount_untaxed_custom", store=True
    )
    grand_total = fields.Float(
        string="Grand Total", compute="_compute_amount_untaxed_custom", store=True
    )
    display_total = fields.Monetary(
        string="Total",
        currency_field="currency_id",
        compute="_compute_display_total",
        store=False,
    )
    vendor_ids = fields.Many2many("res.partner", string="All Vendors")
    custom_line_ids = fields.One2many(
        "purchase.order.custom.line", "order_id", string="Custom Lines"
    )
    date_request = fields.Date(
        string="Date of Request", default=fields.Date.context_today
    )
    requested_by = fields.Char(string="Requested By")
    department = fields.Char(string="Department")
    supervisor = fields.Char(string="Supervisor")
    supervisor_partner_id = fields.Char(string="supervisor_partner_id")
    grn_ses_button_type = fields.Selection(
        [
            ("grn", "GRN"),
            ("ses", "SES"),
            ("both", "GRN/SES"),
        ],
        string="GRN/SES Button Type",
        compute="_compute_grn_ses_button_type",
        store=False,
    )
    # Reason tab field (editable by specific groups via view)
    rejection_reason = fields.Text(string="Reason for Rejection")
    
    def _reload_action(self):
        """Return an action that reloads the current form to refresh button visibility."""
        return {
            "type": "ir.actions.act_window",
            "res_model": "purchase.order",
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }
    
    @api.depends("custom_line_ids.subtotal")
    def _compute_amount_untaxed_custom(self):
        for order in self:
            order.subtotal = sum(order.custom_line_ids.mapped("subtotal"))
            order.tax_15 = order.subtotal * 0.15
            order.grand_total = order.subtotal + order.tax_15

    # def button_confirm(self):
    #     for order in self:
    #         if order.state == "pending":
    #             order.write({"state": "purchase"})
    #         else:
    #             super(PurchaseOrder, order).button_confirm()

    def button_confirm(self):
        for order in self:
            # Preserve native confirm to keep purchase↔stock linkage
            if order.name.startswith("RFQ"):
                order.name = (
                    self.env["ir.sequence"].next_by_code("purchase.order") or "P0001"
                )

            if order.state == "pending":
                order.write({"state": "purchase"})
            else:
                super(PurchaseOrder, order).button_confirm()

            # After confirmation, ensure inventory receipt is created and validated from custom lines
            try:
                order._create_and_validate_receipt_from_custom_lines()
            except Exception as e:
                _logger.exception("Auto receipt creation failed for %s: %s", order.name, e)

    def _schedule_activity_for_group(self, group_xml_id, summary, note):
        group = self.env.ref(group_xml_id, raise_if_not_found=False)
        if not group:
            return
        for user in group.users:
            self.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=summary,
                note=note,
                user_id=user.id,
            )

    def _compute_current_user_has_acted(self):
        uid = self.env.user.id
        for order in self:
            order.current_user_has_acted = bool(order.approval_action_user_ids.filtered(lambda u: u.id == uid))

    # main approval logic
    def action_approve(self):
        self.ensure_one()
        amount = self.subtotal
        acting_user_id = self.env.user.id

        if amount <= 10000:
            if not self.pe_approved:
                self.write({"pe_approved": True})
                self.message_post(body="Approved by Project Engineer.")

        elif amount <= 100000:
            if not self.pe_approved:
                self.write({"pe_approved": True})
                self.message_post(body="Approved by Project Engineer.")
                self._schedule_activity_for_group(
                    "custom_user_portal.project_manager",
                    "Review Purchase Order",
                    f"PO {self.name} approved by PE. Please review.",
                )
            elif not self.pm_approved:
                self.write({"pm_approved": True})
                self.message_post(body="Approved by Project Manager.")

        elif amount <= 500000:
            if not self.pe_approved:
                self.write({"pe_approved": True})
                self.message_post(body="Approved by Project Engineer.")
                self._schedule_activity_for_group(
                    "custom_user_portal.project_manager",
                    "Review Purchase Order",
                    f"PO {self.name} approved by PE. Please review.",
                )
            elif not self.pm_approved:
                self.write({"pm_approved": True})
                self.message_post(body="Approved by Project Manager.")
                self._schedule_activity_for_group(
                    "custom_user_portal.operations_director",
                    "Review Purchase Order",
                    f"PO {self.name} approved by PM. Please review.",
                )
            elif not self.od_approved:
                self.write({"od_approved": True})
                self.message_post(body="Approved by Operations Director.")

        else:  # Above 500k
            if not self.pe_approved:
                self.write({"pe_approved": True})
                self.message_post(body="Approved by Project Engineer.")
                self._schedule_activity_for_group(
                    "custom_user_portal.project_manager",
                    "Review Purchase Order",
                    f"PO {self.name} approved by PE. Please review.",
                )
            elif not self.pm_approved:
                self.write({"pm_approved": True})
                self.message_post(body="Approved by Project Manager.")
                self._schedule_activity_for_group(
                    "custom_user_portal.operations_director",
                    "Review Purchase Order",
                    f"PO {self.name} approved by PM. Please review.",
                )
            elif not self.od_approved:
                self.write({"od_approved": True})
                self.message_post(body="Approved by Operations Director.")
                self._schedule_activity_for_group(
                    "custom_user_portal.managing_director",
                    "Review Purchase Order",
                    f"PO {self.name} approved by OD. Please review.",
                )
            elif not self.md_approved:
                self.write({"md_approved": True})
                self.message_post(body="Approved by Managing Director.")

        # Mark current user as having acted so their buttons hide
        self.sudo().write({"approval_action_user_ids": [(4, acting_user_id)]})
        return self._reload_action()

    # confirm order button visibility
    @api.depends(
        "state",
        "pe_approved",
        "pm_approved",
        "od_approved",
        "md_approved",
        "subtotal",
    )
    def _compute_can_confirm_order(self):
        for order in self:
            if order.state != "pending":
                order.can_confirm_order = False
                continue

            amt = order.subtotal
            if amt <= 10000:
                order.can_confirm_order = order.pe_approved
            elif amt <= 100000:
                order.can_confirm_order = order.pe_approved and order.pm_approved
            elif amt <= 500000:
                order.can_confirm_order = (
                    order.pe_approved and order.pm_approved and order.od_approved
                )
            else:
                order.can_confirm_order = (
                    order.pe_approved
                    and order.pm_approved
                    and order.od_approved
                    and order.md_approved
                )

    @api.depends("state")
    def _compute_show_approvals(self):
        """Compute visibility of approval fields based on user groups and state"""
        for order in self:
            user = self.env.user
            order.show_pe_approved = order.state == "pending" and user.has_group(
                "custom_user_portal.project_engineer"
            )
            order.show_pm_approved = order.state == "pending" and user.has_group(
                "custom_user_portal.project_manager"
            )
            order.show_od_approved = order.state == "pending" and user.has_group(
                "custom_user_portal.operations_director"
            )
            order.show_md_approved = order.state == "pending" and user.has_group(
                "custom_user_portal.managing_director"
            )

    def action_reject(self):
        for order in self:
            if not order.origin:
                raise UserError(_("This Purchase Order has no origin."))

            rejecting_user = self.env.user
            _logger.info(
                "Rejecting PO %s with origin: %s by %s",
                order.name,
                order.origin,
                rejecting_user.name,
            )

            # Record action for current user to hide buttons for them only
            order.sudo().write({"approval_action_user_ids": [(4, self.env.user.id)]})

            # Step 1: Find the PO with this origin
            parent_po = self.env["purchase.order"].search(
                [("name", "=", order.origin)], limit=1
            )
            if not parent_po:
                _logger.warning("No parent PO found for origin: %s", order.origin)
                order.state = "cancel"
                continue

            _logger.info(
                "Origin %s belongs to PO %s with origin: %s",
                order.origin,
                parent_po.name,
                parent_po.origin,
            )

            # Step 2: Get the PR number from the parent PO origin
            if not parent_po.origin:
                _logger.warning("Parent PO %s has no origin.", parent_po.name)
                order.state = "cancel"
                continue

            pr_record = self.env["purchase.requisition"].search(
                [("name", "=", parent_po.origin)], limit=1
            )
            if not pr_record:
                _logger.warning(
                    "No Purchase Requisition found with name: %s", parent_po.origin
                )
                order.state = "cancel"
                continue

            _logger.info("Found PR %s linked to PO %s", pr_record.name, parent_po.name)

            # Step 3: Get supervisor_partner_id and convert to int
            if not pr_record.supervisor_partner_id:
                _logger.warning("PR %s has no supervisor_partner_id.", pr_record.name)
                order.state = "cancel"
                continue

            try:
                supervisor_id_int = int(pr_record.supervisor_partner_id)
            except ValueError:
                _logger.error(
                    "Supervisor Partner ID in PR %s is not a valid integer: %s",
                    pr_record.name,
                    pr_record.supervisor_partner_id,
                )
                order.state = "cancel"
                continue

            # Step 4: Find partner
            supervisor_partner = self.env["res.partner"].browse(supervisor_id_int)
            if not supervisor_partner.exists():
                _logger.warning("No partner found with ID: %s", supervisor_id_int)
            else:
                _logger.info(
                    "Supervisor Partner for PR %s is %s with email: %s",
                    pr_record.name,
                    supervisor_partner.name,
                    supervisor_partner.email,
                )

                # Create activity for supervisor
                self.env["mail.activity"].create(
                    {
                        "res_model_id": self.env["ir.model"]._get_id("purchase.order"),
                        "res_id": order.id,
                        "activity_type_id": self.env.ref(
                            "mail.mail_activity_data_todo"
                        ).id,
                        "user_id": (
                            supervisor_partner.user_ids[:1].id
                            if supervisor_partner.user_ids
                            else False
                        ),
                        "note": _("Purchase Order %s was rejected by %s")
                        % (order.name, rejecting_user.name),
                    }
                )

                # Send email to supervisor
                if supervisor_partner.email:
                    mail_values = {
                        "subject": _("Purchase Order %s Rejected") % order.name,
                        "body_html": _(
                            "<p>Hello %s,</p>"
                            "<p>The Purchase Order <b>%s</b> has been rejected by <b>%s</b>.</p>"
                            "<p>Regards,<br/>%s</p>"
                        )
                        % (
                            supervisor_partner.name,
                            order.name,
                            rejecting_user.name,
                            rejecting_user.company_id.name,
                        ),
                        "email_to": supervisor_partner.email,
                    }
                    self.env["mail.mail"].create(mail_values).send()

            # Final step: reject the current PO
            order.state = "cancel"

    # PO send by Email in RFQ
    def action_rfq_send(self):
        """Override to include all vendors (partner_id + vendor_ids) in email wizard."""
        self.ensure_one()
        res = super(PurchaseOrder, self).action_rfq_send()

        # Collect all vendors: partner_id + vendor_ids
        all_vendors = self.vendor_ids.ids
        if self.partner_id:
            if self.partner_id.id not in all_vendors:
                all_vendors = [self.partner_id.id] + all_vendors

        # Update wizard context with all vendors
        if res and isinstance(res, dict):
            ctx = res.get("context", {})
            ctx.update({"default_partner_ids": all_vendors})
            res["context"] = ctx

        return res

    def unlink(self):
        # Before deleting, store PRs and Quotations linked to this PO
        prs_to_update = self.mapped("origin")  # origin = PR.name
        quotations_to_update = self.mapped(
            "origin"
        )  # origin also used for RFQ/Quotation

        res = super(PurchaseOrder, self).unlink()  # Delete the PO

        pr_model = self.env["purchase.requisition"]
        quotation_model = self.env["purchase.quotation"]

        # Update related PRs
        for pr_name in prs_to_update:
            pr = pr_model.search([("name", "=", pr_name)], limit=1)
            if pr:
                pr.status = "pr"
                pr.message_post(body=_("PO deleted, status reverted to PR."))

        # Update related Quotations
        for rfq_origin in quotations_to_update:
            quotation = quotation_model.search(
                [("rfq_origin", "=", rfq_origin)], limit=1
            )
            if quotation:
                # Only set back if no active PO exists anymore
                po_exists = self.env["purchase.order"].search_count(
                    [
                        ("origin", "=", quotation.rfq_origin),
                        ("state", "in", ["pending", "purchase"]),
                    ]
                )
                if po_exists == 0:
                    quotation.status = "quote"
                    quotation.message_post(
                        body=_("PO deleted, status reverted to Quote.")
                    )

        return res

    # def action_confirm(self):
    #     """Custom confirm: set state from pending → purchase"""
    #     for order in self:
    #         if order.state == "pending":
    #             order.state = "purchase"
    #         # Find the group
    #         group = self.env.ref("custom_pr_system.inventory_data_entry", raise_if_not_found=False)
    #         if group and group.users:
    #             for user in group.users:
    #                 order.activity_schedule(
    #                     'mail.mail_activity_data_todo',  # Default TODO activity
    #                     user_id=user.id,
    #                     summary="Purchase Order Approved",
    #                     note=f"Purchase Order {order.name} has been approved."
    #                 )
    #     return True
    
    # def action_confirm(self):
    #     """Custom confirm: set state from pending → purchase + create/update product & update stock (Odoo 17)."""
    #     for order in self:
    #         # --- existing logic: move to purchase & schedule activities ---
    #         if order.state == "pending":
    #             order.state = "purchase"
    #         # Find the group
    #         group = self.env.ref("custom_pr_system.inventory_data_entry", raise_if_not_found=False)
    #         if group and group.users:
    #             for user in group.users:
    #                 order.activity_schedule(
    #                     'mail.mail_activity_data_todo',  # Default TODO activity
    #                     user_id=user.id,
    #                     summary="Purchase Order Approved",
    #                     note=f"Purchase Order {order.name} has been approved."
    #                 )

    #         # --- gather lines to process ---
    #         if hasattr(order, "custom_line_ids") and order.custom_line_ids:
    #             lines = order.custom_line_ids
    #         else:
    #             lines = order.order_line

    #         aggregated = {}  # { product_name: { 'qty': total_qty, 'unit': custom_unit_record, 'sample_line': line } }
    #         for line in lines:
    #             # find a product name
    #             product_name = False
    #             for attr in ("name", "description", "product_name", "default_code"):
    #                 if getattr(line, attr, False):
    #                     product_name = getattr(line, attr)
    #                     break
    #             if not product_name and getattr(line, "product_id", False):
    #                 product_name = getattr(line.product_id, "name", False)

    #             # quantity
    #             qty = 0.0
    #             for qattr in ("quantity", "product_qty", "product_uom_qty", "qty"):
    #                 val = getattr(line, qattr, False)
    #                 if val:
    #                     try:
    #                         qty = float(val)
    #                         break
    #                     except Exception:
    #                         qty = 0.0

    #             custom_unit = getattr(line, "unit", False)

    #             if not product_name or qty <= 0:
    #                 continue

    #             key = str(product_name).strip()
    #             if key not in aggregated:
    #                 aggregated[key] = {"qty": qty, "unit": custom_unit, "sample_line": line}
    #             else:
    #                 aggregated[key]["qty"] += qty

    #         if not aggregated:
    #             continue

    #         env = self.env

    #         def _get_or_create_uom_from_custom_unit(cu):
    #             """Find or create a uom.uom matching custom.unit"""
    #             try:
    #                 if not cu:
    #                     return env.ref("uom.product_uom_unit")
    #                 name = cu.name if hasattr(cu, "name") else str(cu)
    #                 uom = env["uom.uom"].sudo().search([("name", "=", name)], limit=1)
    #                 if uom:
    #                     return uom
    #                 default_uom = env.ref("uom.product_uom_unit")
    #                 uom_vals = {
    #                     "name": name,
    #                     "category_id": default_uom.category_id.id,
    #                 }
    #                 return env["uom.uom"].sudo().create(uom_vals)
    #             except Exception:
    #                 return env.ref("uom.product_uom_unit")

    #         # decide stock location
    #         stock_location = env.ref("stock.stock_location_stock", raise_if_not_found=False)
    #         if not stock_location:
    #             stock_location = env["stock.location"].sudo().search([("usage", "=", "internal")], limit=1)
    #         if not stock_location:
    #             continue  # no internal stock location, skip

    #         # --- process each aggregated product ---
    #         for prod_name, info in aggregated.items():
    #             qty = info["qty"]
    #             custom_unit = info["unit"]

    #             # find or create product.template
    #             product_tmpl = env["product.template"].sudo().search([("name", "=", prod_name)], limit=1)
    #             if not product_tmpl:
    #                 uom = _get_or_create_uom_from_custom_unit(custom_unit)
    #                 try:
    #                     categ = env.ref("product.product_category_all")
    #                 except Exception:
    #                     categ = env["product.category"].sudo().search([], limit=1)

    #                 tmpl_vals = {
    #                     "name": prod_name,
    #                     "type": "product",  # storable product
    #                     "uom_id": uom.id if uom else env.ref("uom.product_uom_unit").id,
    #                     "uom_po_id": uom.id if uom else env.ref("uom.product_uom_unit").id,
    #                     "categ_id": categ.id if categ else False,
    #                     "list_price": info["sample_line"].price_unit or 0.0,   
    #                     "standard_price": info["sample_line"].price_unit or 0.0,  
    #                 }
    #                 product_tmpl = env["product.template"].sudo().create(tmpl_vals)

    #             product = product_tmpl.product_variant_id

    #             # update/create stock.quant
    #             quant = env["stock.quant"].sudo().search([
    #                 ("product_id", "=", product.id),
    #                 ("location_id", "=", stock_location.id),
    #             ], limit=1)

    #             if quant:
    #                 # quant.quantity += qty
    #                  quant.sudo().write({"quantity": quant.quantity + qty})
    #             else:
    #                 env["stock.quant"].sudo().create({
    #                     "product_id": product.id,
    #                     "location_id": stock_location.id,
    #                     "quantity": qty,
    #                 })

    #     return True
    def action_confirm(self):
        """Custom confirm: set state from pending → purchase and then create a validated receipt from custom lines."""
        for order in self:
            if order.state == "pending":
                order.state = "purchase"

            group = self.env.ref("custom_pr_system.inventory_data_entry", raise_if_not_found=False)
            if group and group.users:
                for user in group.users:
                    order.activity_schedule(
                        'mail.mail_activity_data_todo',
                        user_id=user.id,
                        summary="Purchase Order Approved",
                        note=f"Purchase Order {order.name} has been approved."
                    )

            try:
                order._create_and_validate_receipt_from_custom_lines()
            except Exception as e:
                _logger.exception("Auto receipt creation failed for %s: %s", order.name, e)

        return True

    def _create_and_validate_receipt_from_custom_lines(self):
        """Create and validate an incoming picking based on custom_line_ids to update on-hand quantities."""
        self.ensure_one()

        # Collect lines (prefer custom lines)
        src_lines = self.custom_line_ids or self.order_line
        if not src_lines:
            return True

        # Aggregate by product
        product_qty_map = {}
        for line in src_lines:
            # Skip services if present
            if hasattr(line, "type") and line.type == "service":
                continue

            qty = getattr(line, "quantity", 0.0) or getattr(line, "product_qty", 0.0) or 0.0
            if qty <= 0:
                continue

            product = getattr(line, "product_id", False)
            if not product:
                name_val = getattr(line, "name", "")
                if name_val:
                    product = self.env["product.product"].sudo().search([("name", "=", name_val)], limit=1)
            if not product:
                continue

            product_qty_map[product.id] = product_qty_map.get(product.id, 0.0) + qty

        if not product_qty_map:
            return True

        # Incoming picking type
        picking_type = self.env["stock.picking.type"].sudo().search([
            ("code", "=", "incoming"),
            ("company_id", "=", self.company_id.id),
        ], limit=1) or self.env["stock.picking.type"].sudo().search([("code", "=", "incoming")], limit=1)
        if not picking_type:
            return True

        # Locations
        suppliers_loc = self.env.ref("stock.stock_location_suppliers", raise_if_not_found=False)
        location_id = (picking_type.default_location_src_id and picking_type.default_location_src_id.id) or (suppliers_loc and suppliers_loc.id)

        dest_loc = picking_type.default_location_dest_id
        if not dest_loc:
            warehouse = self.env["stock.warehouse"].sudo().search([("company_id", "=", self.company_id.id)], limit=1)
            dest_loc = warehouse and warehouse.lot_stock_id or False
        location_dest_id = dest_loc and dest_loc.id or False
        if not location_id or not location_dest_id:
            return True

        # Create picking
        picking = self.env["stock.picking"].sudo().create({
            "picking_type_id": picking_type.id,
            "partner_id": self.partner_id.id,
            "origin": self.name,
            "company_id": self.company_id.id,
            "location_id": location_id,
            "location_dest_id": location_dest_id,
        })

        # Create moves
        Move = self.env["stock.move"].sudo()
        for product_id, qty in product_qty_map.items():
            product = self.env["product.product"].browse(product_id)
            if not product.exists():
                continue
            uom_id = (product.uom_po_id and product.uom_po_id.id) or product.uom_id.id
            Move.create({
                "name": product.display_name or product.name,
                "product_id": product.id,
                "product_uom": uom_id,
                "product_uom_qty": qty,
                "picking_id": picking.id,
                "location_id": location_id,
                "location_dest_id": location_dest_id,
                "company_id": self.company_id.id,
            })

        # Confirm, assign and set done qty
        picking.action_confirm()
        picking.action_assign()

        for move in picking.move_ids_without_package:
            if not move.move_line_ids:
                self.env["stock.move.line"].sudo().create({
                    "move_id": move.id,
                    "picking_id": picking.id,
                    "product_id": move.product_id.id,
                    "product_uom_id": move.product_uom.id,
                    "qty_done": move.product_uom_qty,
                    "location_id": move.location_id.id,
                    "location_dest_id": move.location_dest_id.id,
                    "company_id": self.company_id.id,
                })
            else:
                for ml in move.move_line_ids:
                    if not ml.qty_done:
                        ml.sudo().qty_done = ml.product_uom_qty or move.product_uom_qty

        # Validate picking
        picking.sudo()._action_done()
        return True



    def create_grn_ses(self):
        return {
            "name": "Add Remarks for GRN/SES",
            "type": "ir.actions.act_window",
            "res_model": "grn.ses.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"active_id": self.id},
        }

    @api.depends("state", "subtotal", "grand_total")
    def _compute_display_total(self):
        for order in self:
            if order.state == "purchase":
                order.display_total = order.grand_total
            else:
                order.display_total = order.subtotal

    @api.depends("custom_line_ids.type")
    def _compute_grn_ses_button_type(self):
        for order in self:
            line_types = set(order.custom_line_ids.mapped("type"))
            if not line_types:
                order.grn_ses_button_type = False
            elif line_types == {"material"}:
                order.grn_ses_button_type = "grn"
            elif line_types == {"service"}:
                order.grn_ses_button_type = "ses"
            else:
                order.grn_ses_button_type = "both"