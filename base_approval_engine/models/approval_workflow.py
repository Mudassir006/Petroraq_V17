from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.osv import expression
from odoo.tools.safe_eval import safe_eval


class ApprovalWorkflow(models.Model):
    _name = "approval.workflow"
    _description = "Approval Workflow"
    _order = "sequence, id"

    name = fields.Char(required=True, tracking=True)
    sequence = fields.Integer(default=10)
    model_id = fields.Many2one(
        "ir.model",
        required=True,
        domain="[(\"transient\", \"=\", False)]",
        ondelete="cascade",
    )
    model_name = fields.Char(related="model_id.model", store=True, index=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company")
    approval_mode = fields.Selection(
        [("sequential", "Sequential"), ("parallel", "Parallel (Reserved)")],
        default="sequential",
        required=True,
    )
    condition_domain = fields.Text(
        help=(
            "Optional domain expression evaluated safely.\n"
            "Examples:\n"
            "[('amount_total', '>', 1000)]\n"
            "[('partner_id.country_id.code', '=', 'SA')]\n"
            "[('user_id', '=', user_id), ('date_order', '&gt;=', today)]"
        )
    )
    allow_dynamic_approvers = fields.Boolean(default=True)
    auto_lock_record = fields.Boolean(default=True)
    notes = fields.Text()
    line_ids = fields.One2many(
        "approval.workflow.line",
        "workflow_id",
        string="Workflow Lines",
        copy=True,
    )

    _sql_constraints = [
        (
            "approval_workflow_name_company_model_unique",
            "unique(name, model_id, company_id)",
            "Workflow name must be unique per model/company.",
        )
    ]

    @api.constrains("condition_domain")
    def _check_condition_domain(self):
        for workflow in self.filtered("condition_domain"):
            workflow._safe_parse_domain(workflow.condition_domain)

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
            raise ValidationError(_("Invalid condition domain: %s") % error) from error
        if not isinstance(parsed, (list, tuple)):
            raise ValidationError(_("Condition domain must evaluate to a list/tuple domain."))
        return list(parsed)

    def _matches_record(self, record):
        self.ensure_one()
        if self.model_name != record._name:
            return False
        if self.company_id and hasattr(record, "company_id") and record.company_id != self.company_id:
            return False
        if not self.condition_domain:
            return True
        domain = self._safe_parse_domain(self.condition_domain)
        return bool(record.sudo().search_count([( "id", "=", record.id)] + domain))


class ApprovalWorkflowLine(models.Model):
    _name = "approval.workflow.line"
    _description = "Approval Workflow Line"
    _order = "sequence, id"

    workflow_id = fields.Many2one("approval.workflow", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)
    approver_type = fields.Selection(
        [
            ("user", "Specific User"),
            ("group", "User Group"),
            ("field_user", "User from Record Field"),
            ("manager", "Employee Manager"),
            ("related_user", "Related User Field"),
        ],
        required=True,
        default="user",
    )
    user_id = fields.Many2one("res.users")
    group_id = fields.Many2one("res.groups")
    field_name = fields.Char(help="Field on target record that returns res.users")
    related_path = fields.Char(help="Dotted path ending in res.users field. Example: employee_id.parent_id.user_id")
    required = fields.Boolean(default=True)
    min_approvers = fields.Integer(default=1)

    @api.constrains("min_approvers")
    def _check_min_approvers(self):
        for rec in self:
            if rec.min_approvers < 1:
                raise ValidationError(_("Minimum approvers must be at least 1."))

    @api.constrains("approver_type", "user_id", "group_id", "field_name", "related_path")
    def _check_line_configuration(self):
        for line in self:
            if line.approver_type == "user" and not line.user_id:
                raise ValidationError(_("Specific User approver requires User."))
            if line.approver_type == "group" and not line.group_id:
                raise ValidationError(_("Group approver requires Group."))
            if line.approver_type == "field_user" and not line.field_name:
                raise ValidationError(_("Field User approver requires field name."))
            if line.approver_type == "related_user" and not line.related_path:
                raise ValidationError(_("Related User approver requires path."))

    def _resolve_approvers(self, record):
        self.ensure_one()
        users = self.env["res.users"]
        if self.approver_type == "user":
            users = self.user_id
        elif self.approver_type == "group":
            users = self.group_id.users
        elif self.approver_type == "field_user":
            users = self._resolve_field_user(record)
        elif self.approver_type == "manager":
            users = self._resolve_manager(record)
        elif self.approver_type == "related_user":
            users = self._resolve_related_user(record)
        return users.filtered(lambda u: u.active)

    def _resolve_field_user(self, record):
        self.ensure_one()
        value = record[self.field_name] if self.field_name in record._fields else False
        if not value:
            return self.env["res.users"]
        if value._name == "res.users":
            return value
        if value._name == "hr.employee" and value.user_id:
            return value.user_id
        return self.env["res.users"]

    def _resolve_manager(self, record):
        employee = getattr(record, "employee_id", False)
        manager_user = employee.parent_id.user_id if employee and employee.parent_id else False
        if not manager_user and hasattr(record, "user_id"):
            manager_user = record.user_id.employee_id.parent_id.user_id
        return manager_user or self.env["res.users"]

    def _resolve_related_user(self, record):
        self.ensure_one()
        current = record
        for field_name in (self.related_path or "").split("."):
            if not field_name:
                continue
            if field_name not in current._fields:
                return self.env["res.users"]
            current = current[field_name]
            if not current:
                return self.env["res.users"]
        if getattr(current, "_name", "") == "res.users":
            return current
        return self.env["res.users"]
