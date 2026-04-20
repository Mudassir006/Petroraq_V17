from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ApprovalRequest(models.Model):
    _name = "approval.request"
    _description = "Approval Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"

    name = fields.Char(default=lambda self: _("New"), copy=False, readonly=True, index=True)
    workflow_id = fields.Many2one("approval.workflow", required=True, ondelete="restrict")
    res_model = fields.Char(required=True, index=True)
    res_id = fields.Integer(required=True, index=True)
    resource_ref = fields.Reference(
        selection="_referenceable_models",
        string="Document",
        compute="_compute_resource_ref",
        store=False,
    )
    company_id = fields.Many2one("res.company", required=True, index=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        tracking=True,
        required=True,
    )
    requested_by = fields.Many2one("res.users", required=True, default=lambda self: self.env.user, tracking=True)
    requested_date = fields.Datetime(readonly=True, tracking=True)
    current_sequence = fields.Integer(readonly=True, tracking=True)
    final_approved_by = fields.Many2one("res.users", readonly=True, tracking=True)
    final_approved_date = fields.Datetime(readonly=True, tracking=True)
    rejection_reason = fields.Text(readonly=True, tracking=True)
    line_ids = fields.One2many("approval.request.line", "request_id", copy=False)
    pending_line_ids = fields.One2many("approval.request.line", "request_id", compute="_compute_pending_line_ids")

    @api.depends("res_model", "res_id")
    def _compute_resource_ref(self):
        for req in self:
            req.resource_ref = f"{req.res_model},{req.res_id}" if req.res_model and req.res_id else False

    @api.depends("line_ids.status", "line_ids.sequence")
    def _compute_pending_line_ids(self):
        for req in self:
            req.pending_line_ids = req.line_ids.filtered(lambda l: l.status == "pending")

    @api.model
    def _referenceable_models(self):
        models = self.env["ir.model"].sudo().search([])
        return [(m.model, m.name) for m in models]

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = sequence.next_by_code("approval.request") or _("New")
            if vals.get("state", "draft") == "pending":
                existing = self.search_count([
                    ("res_model", "=", vals.get("res_model")),
                    ("res_id", "=", vals.get("res_id")),
                    ("state", "=", "pending"),
                ])
                if existing:
                    raise ValidationError(_("A pending approval request already exists for this document."))
        return super().create(vals_list)


    @api.model
    def create_request_from_workflow(self, workflow, record):
        pending = self.search_count([
            ("res_model", "=", record._name),
            ("res_id", "=", record.id),
            ("state", "=", "pending"),
        ])
        if pending:
            raise ValidationError(_("A pending approval request already exists for this document."))

        request = self.create({
            "workflow_id": workflow.id,
            "res_model": record._name,
            "res_id": record.id,
            "company_id": getattr(record, "company_id", self.env.company).id,
        })

        line_vals = []
        for line in workflow.line_ids.sorted(key=lambda x: (x.sequence, x.id)):
            users = line._resolve_approvers(record)
            if not users and line.required:
                raise ValidationError(_("No approver resolved for step '%s'.") % line.name)
            for user in users:
                line_vals.append({
                    "request_id": request.id,
                    "sequence": line.sequence,
                    "approver_id": user.id,
                    "source_type": line.approver_type,
                    "required": line.required,
                })
        if not line_vals:
            raise ValidationError(_("No approvers resolved from workflow '%s'.") % workflow.name)
        self.env["approval.request.line"].create(line_vals)
        return request

    def action_submit(self):
        for request in self:
            if request.state != "draft":
                continue
            if not request.line_ids:
                raise ValidationError(_("Approval request requires at least one approver line."))
            first_seq = min(request.line_ids.mapped("sequence"))
            request.write({
                "state": "pending",
                "requested_date": fields.Datetime.now(),
                "current_sequence": first_seq,
            })
            request._activate_current_stage_activities()
            request._message_record(_("Approval request %s submitted.") % request.name)

    def action_cancel(self):
        for request in self:
            if request.state in ("approved", "rejected", "cancelled"):
                continue
            request.state = "cancelled"
            request.activity_unlink(["mail.mail_activity_data_todo"])

    def action_approve(self, comment=False):
        for request in self:
            request._check_user_can_approve()
            lines = request._current_user_pending_lines()
            if not lines:
                raise UserError(_("No pending approval line assigned to current user."))
            now = fields.Datetime.now()
            lines.write({
                "status": "approved",
                "action_date": now,
                "comment": comment or False,
            })
            request._advance_or_complete()

    def action_reject(self, reason):
        if not reason:
            raise ValidationError(_("Rejection reason is required."))
        for request in self:
            request._check_user_can_approve()
            lines = request._current_user_pending_lines()
            if not lines:
                raise UserError(_("No pending approval line assigned to current user."))
            now = fields.Datetime.now()
            lines.write({
                "status": "rejected",
                "action_date": now,
                "comment": reason,
            })
            request.write({"state": "rejected", "rejection_reason": reason})
            request.activity_unlink(["mail.mail_activity_data_todo"])
            request._message_record(_("Approval request rejected: %s") % reason)
            request._notify_document_rejected(reason)

    def _check_user_can_approve(self):
        self.ensure_one()
        if self.state != "pending":
            raise UserError(_("Only pending requests can be approved/rejected."))
        if self.env.user.has_group("base_approval_engine.group_approval_engine_admin"):
            return True
        return bool(self._current_user_pending_lines())

    def _current_user_pending_lines(self):
        self.ensure_one()
        return self.line_ids.filtered(
            lambda l: l.status == "pending"
            and l.sequence == self.current_sequence
            and l.approver_id == self.env.user
        )

    def _advance_or_complete(self):
        self.ensure_one()
        current_lines = self.line_ids.filtered(lambda l: l.sequence == self.current_sequence)
        required_pending = current_lines.filtered(lambda l: l.required and l.status == "pending")
        if required_pending:
            return

        next_lines = self.line_ids.filtered(
            lambda l: l.status == "pending" and l.sequence > self.current_sequence
        )
        if next_lines:
            self.current_sequence = min(next_lines.mapped("sequence"))
            self._activate_current_stage_activities()
            self._message_record(_("Approval moved to sequence %s.") % self.current_sequence)
            return

        self.write({
            "state": "approved",
            "final_approved_by": self.env.user,
            "final_approved_date": fields.Datetime.now(),
        })
        self.activity_unlink(["mail.mail_activity_data_todo"])
        self._message_record(_("Approval request fully approved."))
        self._notify_document_approved()

    def _activate_current_stage_activities(self):
        self.ensure_one()
        self.activity_unlink(["mail.mail_activity_data_todo"])
        pending_users = self.line_ids.filtered(
            lambda l: l.status == "pending" and l.sequence == self.current_sequence
        ).mapped("approver_id")
        for user in pending_users:
            self.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=user.id,
                summary=_("Approval needed"),
                note=_("Please review approval request %s") % self.name,
            )

    def _message_record(self, body):
        self.ensure_one()
        self.message_post(body=body)
        target = self._get_target_record()
        if target and hasattr(target, "message_post"):
            target.message_post(body=body)

    def _get_target_record(self):
        self.ensure_one()
        if not self.res_model or not self.res_id:
            return False
        return self.env[self.res_model].browse(self.res_id).exists()

    def _notify_document_approved(self):
        self.ensure_one()
        target = self._get_target_record()
        if target and hasattr(target, "_approval_final_approve_hook"):
            target._approval_final_approve_hook(self)

    def _notify_document_rejected(self, reason):
        self.ensure_one()
        target = self._get_target_record()
        if target and hasattr(target, "_approval_reject_hook"):
            target._approval_reject_hook(self, reason)


class ApprovalRequestLine(models.Model):
    _name = "approval.request.line"
    _description = "Approval Request Line"
    _order = "sequence, id"

    request_id = fields.Many2one("approval.request", required=True, ondelete="cascade")
    sequence = fields.Integer(required=True, default=10)
    approver_id = fields.Many2one("res.users", required=True)
    status = fields.Selection(
        [
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("skipped", "Skipped"),
        ],
        default="pending",
        required=True,
        tracking=True,
    )
    action_date = fields.Datetime()
    comment = fields.Text()
    source_type = fields.Selection(
        [
            ("user", "Specific User"),
            ("group", "Group"),
            ("field_user", "Field User"),
            ("manager", "Manager"),
            ("related_user", "Related User"),
        ],
        required=True,
    )
    required = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "approval_request_line_unique",
            "unique(request_id, sequence, approver_id)",
            "Approver cannot be duplicated in the same stage.",
        )
    ]
