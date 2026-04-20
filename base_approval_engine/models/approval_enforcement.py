from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression
from odoo.tools.safe_eval import safe_eval


class ApprovalEnforcementRule(models.Model):
    _name = "approval.enforcement.rule"
    _description = "Approval Enforcement Rule"
    _order = "sequence, id"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    model_id = fields.Many2one("ir.model", required=True, domain="[(\"transient\", \"=\", False)]")
    model_name = fields.Char(related="model_id.model", store=True, index=True)
    method_name = fields.Char(required=True, help="Technical method to protect, e.g. action_post, action_confirm")
    required_request_state = fields.Selection(
        [("approved", "Approved")],
        default="approved",
        required=True,
    )
    condition_domain = fields.Text(help="Optional domain expression to limit enforcement scope.")
    message = fields.Char(default="Approval is required before executing this action.")

    _sql_constraints = [
        (
            "approval_enforcement_rule_unique",
            "unique(model_id, method_name, sequence)",
            "Rule sequence must be unique per model and method.",
        )
    ]

    @api.constrains("condition_domain")
    def _check_condition_domain(self):
        for rule in self.filtered("condition_domain"):
            rule._safe_parse_domain(rule.condition_domain)

    def _safe_parse_domain(self, domain_text):
        safe_locals = {
            "user_id": self.env.user.id,
            "company_id": self.env.company.id,
            "today": fields.Date.context_today(self),
            "now": datetime.utcnow(),
        }
        try:
            parsed = safe_eval(domain_text, safe_locals, nocopy=True)
            expression.normalize_domain(parsed)
        except Exception as error:
            raise ValidationError(_("Invalid rule condition domain: %s") % error) from error
        if not isinstance(parsed, (list, tuple)):
            raise ValidationError(_("Rule condition domain must evaluate to a list/tuple."))
        return list(parsed)

    @api.model
    def check_method_call(self, records, method_name):
        if not records:
            return
        rules = self.sudo().search([
            ("active", "=", True),
            ("model_name", "=", records._name),
            ("method_name", "=", method_name),
        ], order="sequence, id")
        if not rules:
            return
        for record in records:
            for rule in rules:
                if not rule._record_matches(record):
                    continue
                if not self._record_has_required_approval(record, rule.required_request_state):
                    raise UserError(_(rule.message))

    def _record_matches(self, record):
        self.ensure_one()
        if self.model_name != record._name:
            return False
        if not self.condition_domain:
            return True
        domain = self._safe_parse_domain(self.condition_domain)
        return bool(record.sudo().search_count([("id", "=", record.id)] + domain))

    @api.model
    def _record_has_required_approval(self, record, required_state):
        workflow = self.env["approval.workflow"].sudo().get_applicable_workflow(record)
        if not workflow:
            return True
        request = self.env["approval.request"].sudo().search([
            ("res_model", "=", record._name),
            ("res_id", "=", record.id),
            ("workflow_id", "=", workflow.id),
        ], order="id desc", limit=1)
        return bool(request and request.state == required_state)
