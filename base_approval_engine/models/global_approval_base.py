from lxml import etree

from odoo import _, api, models
from odoo.exceptions import UserError


class GlobalApprovalBase(models.AbstractModel):
    _inherit = "base"

    @api.model
    def get_view(self, view_id=None, view_type="form", **options):
        result = super().get_view(view_id=view_id, view_type=view_type, **options)
        if view_type != "form" or not self._approval_should_inject_for_model():
            return result
        arch = result.get("arch")
        if not arch:
            return result
        doc = etree.XML(arch)
        header = doc.xpath("//form/header")
        if not header:
            sheet = doc.xpath("//form/sheet")
            if not sheet:
                return result
            header_node = etree.Element("header")
            sheet[0].addprevious(header_node)
            header = [header_node]

        self._ensure_button(header[0], "action_submit_for_approval", _("Submit for Approval"), "btn-primary")
        self._ensure_button(header[0], "action_approve_document", _("Approve"), "btn-primary")
        self._ensure_button(header[0], "action_open_approval_reject_wizard", _("Reject"), "btn-secondary")
        self._ensure_button(header[0], "action_open_approval_requests", _("Approval Requests"), "btn-secondary")

        result["arch"] = etree.tostring(doc, encoding="unicode")
        return result

    @api.model
    def _approval_should_inject_for_model(self):
        if self._name.startswith("approval.") or self._name in ("ir.model", "ir.ui.view"):
            return False
        return bool(self.env["approval.workflow"].sudo().search_count([
            ("active", "=", True),
            ("model_name", "=", self._name),
        ]))

    @api.model
    def _ensure_button(self, header_node, name, label, css_class):
        if header_node.xpath(f"./button[@name='{name}']"):
            return
        button = etree.Element("button")
        button.set("name", name)
        button.set("type", "object")
        button.set("string", label)
        button.set("class", css_class)
        header_node.append(button)

    def action_submit_for_approval(self):
        request_model = self.env["approval.request"]
        for record in self:
            workflow = self.env["approval.workflow"].sudo().get_applicable_workflow(record)
            if not workflow:
                continue
            request = request_model.create_request_from_workflow(workflow, record)
            request.action_submit()
            if hasattr(record, "_approval_submit_hook"):
                record._approval_submit_hook(request)
        return True

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

    def action_approve_document(self):
        for record in self:
            request = self.env["approval.request"].search([
                ("res_model", "=", record._name),
                ("res_id", "=", record.id),
                ("state", "=", "pending"),
            ], order="id desc", limit=1)
            if not request:
                raise UserError(_("No pending approval request found."))
            request.action_approve()
        return True

    def action_reject_document(self, reason):
        for record in self:
            request = self.env["approval.request"].search([
                ("res_model", "=", record._name),
                ("res_id", "=", record.id),
                ("state", "=", "pending"),
            ], order="id desc", limit=1)
            if not request:
                raise UserError(_("No pending approval request found."))
            request.action_reject(reason)
        return True
