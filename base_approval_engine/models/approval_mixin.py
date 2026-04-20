from lxml import etree

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ApprovalMixin(models.AbstractModel):
    _name = "approval.mixin"
    _description = "Approval Engine Mixin"

    approval_request_id = fields.Many2one("approval.request", copy=False, readonly=True)
    approval_engine_state = fields.Selection(
        [
            ("not_requested", "Not Requested"),
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("cancelled", "Cancelled"),
        ],
        default="not_requested",
        copy=False,
        tracking=True,
    )
    is_approval_required = fields.Boolean(compute="_compute_is_approval_required")
    can_current_user_approve = fields.Boolean(compute="_compute_can_current_user_approve")
    approval_request_count = fields.Integer(compute="_compute_approval_request_count")

    @api.model
    def get_view(self, view_id=None, view_type="form", **options):
        result = super().get_view(view_id=view_id, view_type=view_type, **options)
        if view_type != "form" or not self._approval_auto_buttons_enabled():
            return result
        arch = result.get("arch")
        if not arch:
            return result
        result["arch"] = self._approval_inject_buttons(arch)
        return result

    @api.model
    def _approval_auto_buttons_enabled(self):
        return True

    @api.model
    def _approval_inject_buttons(self, arch):
        doc = etree.XML(arch)
        header = doc.xpath("//form/header")
        if not header:
            sheet = doc.xpath("//form/sheet")
            if not sheet:
                return arch
            header_node = etree.Element("header")
            sheet[0].addprevious(header_node)
            header = [header_node]

        self._approval_add_header_button(
            header[0],
            "action_submit_for_approval",
            _("Submit for Approval"),
            "btn-primary",
            "not is_approval_required or approval_engine_state in ('pending','approved')",
        )
        self._approval_add_header_button(
            header[0],
            "action_approve_document",
            _("Approve"),
            "btn-primary",
            "approval_engine_state != 'pending' or not can_current_user_approve",
        )
        self._approval_add_header_button(
            header[0],
            "action_open_approval_reject_wizard",
            _("Reject"),
            "btn-secondary",
            "approval_engine_state != 'pending' or not can_current_user_approve",
        )
        self._approval_add_header_button(
            header[0],
            "action_reset_approval",
            _("Reset Approval"),
            "btn-secondary",
            "approval_engine_state == 'not_requested'",
        )

        if not header[0].xpath("./field[@name='approval_engine_state']"):
            state_field = etree.Element("field")
            state_field.set("name", "approval_engine_state")
            state_field.set("widget", "badge")
            state_field.set("decoration-warning", "approval_engine_state == 'pending'")
            state_field.set("decoration-success", "approval_engine_state == 'approved'")
            state_field.set("decoration-danger", "approval_engine_state == 'rejected'")
            header[0].append(state_field)

        for sheet in doc.xpath("//form/sheet"):
            button_box = sheet.xpath("./div[@name='button_box']")
            if not button_box:
                button_box_node = etree.Element("div")
                button_box_node.set("name", "button_box")
                button_box_node.set("class", "oe_button_box")
                sheet.insert(0, button_box_node)
                button_box = [button_box_node]
            if not button_box[0].xpath("./button[@name='action_open_approval_requests']"):
                smart = etree.Element("button")
                smart.set("name", "action_open_approval_requests")
                smart.set("type", "object")
                smart.set("class", "oe_stat_button")
                smart.set("icon", "fa-check-square-o")
                smart.set("invisible", "approval_request_count == 0")
                smart_field = etree.SubElement(smart, "field")
                smart_field.set("name", "approval_request_count")
                smart_field.set("widget", "statinfo")
                smart_field.set("string", "Approvals")
                button_box[0].append(smart)

        return etree.tostring(doc, encoding="unicode")

    @api.model
    def _approval_add_header_button(self, header_node, name, label, css_class, invisible_domain):
        if header_node.xpath(f"./button[@name='{name}']"):
            return
        button = etree.Element("button")
        button.set("name", name)
        button.set("type", "object")
        button.set("string", label)
        button.set("class", css_class)
        button.set("invisible", invisible_domain)
        header_node.append(button)

    def _compute_is_approval_required(self):
        for record in self:
            record.is_approval_required = bool(record._approval_get_applicable_workflow())

    def _compute_can_current_user_approve(self):
        for record in self:
            request = record.approval_request_id
            record.can_current_user_approve = bool(
                request
                and request.state == "pending"
                and request.line_ids.filtered(
                    lambda l: l.approver_id == self.env.user
                    and l.status == "pending"
                    and l.sequence == request.current_sequence
                )
            )

    def _compute_approval_request_count(self):
        model_name = self._name
        grouped = self.env["approval.request"].read_group(
            [("res_model", "=", model_name), ("res_id", "in", self.ids)],
            ["res_id"],
            ["res_id"],
        )
        count_by_id = {row["res_id"]: row["res_id_count"] for row in grouped}
        for record in self:
            record.approval_request_count = count_by_id.get(record.id, 0)

    def action_open_approval_requests(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Approval Requests"),
            "res_model": "approval.request",
            "view_mode": "tree,form",
            "domain": [("res_model", "=", self._name), ("res_id", "=", self.id)],
            "context": {"default_res_model": self._name, "default_res_id": self.id},
        }

    def action_open_approval_reject_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Reject"),
            "res_model": "approval.reject.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "active_model": self._name,
                "active_id": self.id,
            },
        }

    def action_submit_for_approval(self):
        for record in self:
            if not record._approval_requires_workflow():
                continue
            workflow = record._approval_get_applicable_workflow()
            if not workflow:
                continue
            request = record._approval_create_request(workflow)
            request.action_submit()
            record.write(
                {
                    "approval_request_id": request.id,
                    "approval_engine_state": "pending",
                }
            )
            if workflow.auto_lock_record:
                record._approval_lock_record()
            record._approval_submit_hook(request)
        return True

    def action_approve_document(self, comment=False):
        for record in self:
            request = record.approval_request_id
            if not request:
                raise UserError(_("No approval request found."))
            request.action_approve(comment=comment)
            record._sync_approval_state_from_request()
        return True

    def action_reject_document(self, reason):
        for record in self:
            request = record.approval_request_id
            if not request:
                raise UserError(_("No approval request found."))
            request.action_reject(reason)
            record._sync_approval_state_from_request()
        return True

    def action_reset_approval(self):
        for record in self:
            if record.approval_request_id and record.approval_request_id.state == "pending":
                record.approval_request_id.action_cancel()
            record.write({
                "approval_engine_state": "not_requested",
                "approval_request_id": False,
            })
        return True

    def _sync_approval_state_from_request(self):
        for record in self:
            request = record.approval_request_id
            if not request:
                record.approval_engine_state = "not_requested"
                continue
            mapping = {
                "draft": "not_requested",
                "pending": "pending",
                "approved": "approved",
                "rejected": "rejected",
                "cancelled": "cancelled",
            }
            record.approval_engine_state = mapping.get(request.state, "not_requested")

    def _approval_create_request(self, workflow):
        self.ensure_one()
        self._approval_validate_submission(workflow)

        request = self.env["approval.request"].create({
            "workflow_id": workflow.id,
            "res_model": self._name,
            "res_id": self.id,
            "company_id": getattr(self, "company_id", self.env.company).id,
        })

        line_vals = []
        for line in workflow.line_ids.sorted(key=lambda x: (x.sequence, x.id)):
            resolved_users = line._resolve_approvers(self)
            if not resolved_users and line.required:
                raise UserError(_("No approver resolved for step '%s'.") % line.name)
            for user in resolved_users:
                line_vals.append({
                    "request_id": request.id,
                    "sequence": line.sequence,
                    "approver_id": user.id,
                    "source_type": line.approver_type,
                    "required": line.required,
                })
        if not line_vals:
            raise UserError(_("No approvers could be materialized from workflow '%s'.") % workflow.name)
        self.env["approval.request.line"].create(line_vals)
        return request

    def _approval_validate_submission(self, workflow):
        self.ensure_one()
        if self.approval_request_id and self.approval_request_id.state == "pending":
            raise UserError(_("A pending approval request already exists."))
        if workflow.approval_mode != "sequential":
            raise UserError(_("Only sequential mode is supported in v1."))

    def _approval_get_applicable_workflow(self):
        self.ensure_one()
        workflows = self.env["approval.workflow"].sudo().search([
            ("active", "=", True),
            ("model_name", "=", self._name),
            "|",
            ("company_id", "=", False),
            ("company_id", "=", getattr(self, "company_id", self.env.company).id),
        ], order="sequence, id")
        return next((wf for wf in workflows if wf._matches_record(self)), False)

    def _approval_requires_workflow(self):
        self.ensure_one()
        return True

    def _approval_lock_record(self):
        """Optional model override for locking behavior."""

    def _approval_submit_hook(self, request):
        """Optional model override called after submission."""

    def _approval_final_approve_hook(self, request):
        self.ensure_one()
        self._sync_approval_state_from_request()

    def _approval_reject_hook(self, request, reason):
        self.ensure_one()
        self._sync_approval_state_from_request()
