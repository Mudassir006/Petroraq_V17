from odoo import models, fields, api, _

from odoo.exceptions import ValidationError, UserError


class HrRecruitmentRequest(models.Model):
    _name = 'hr.recruitment.request'
    _description = 'HR Recruitment Request'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'approval.stage.mixin']
    _order = "id desc"

    name = fields.Char(string="Request Reference", required=True, copy=False, readonly=True, default="/")
    requested_by_id = fields.Many2one('res.users', string="Requested By", required=True, tracking=True,
                                      default=lambda self: self.env.user)
    employee_id = fields.Many2one(
        "hr.employee",
        string="Requester Employee",
        tracking=True,
        help="Employee who required this request",
    )
    department_id = fields.Many2one('hr.department', string='Department', tracking=True)
    department_manager_user_id = fields.Many2one(
        'res.users',
        string="Department Manager",
        compute="_compute_department_manager_user_id",
        store=True,
    )
    job_id = fields.Many2one(
        "hr.job",
        string="Existing Job Position",
        domain="[('department_id', '=', department_id)]",
    )
    is_new_position = fields.Boolean(string="New Position", )
    new_job_name = fields.Char('New Job Name')
    contract_type_id = fields.Many2one(
        "hr.contract.type",
        string="Employment Type",
    )

    job_salary = fields.Float(
        "Job Salary",
    )

    experience_years = fields.Integer(
        "Experience (Years)",
    )

    job_summary = fields.Html(
        string="Job Summary / Description",
    )

    requested_employees = fields.Integer(string="Number of Employees Required", required=True, default=1)
    expected_start_date = fields.Date(string="Expected Start Date", )
    justification = fields.Text(string="Justification/Description", )

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("dept_approval", "Department Manager Approval"),
            ("hr_approval", "HR Supervisor Approval"),
            ("md_approval", "MD Approval"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("done", "Done"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        tracking=True,
    )

    applicant_count = fields.Integer(
        "Applicants",
        compute="_compute_applicants",
        store=False,
    )
    hired_count = fields.Integer(
        "Hired Employees",
        compute="_compute_applicants",
        store=False,
    )
    hired_ratio = fields.Float(
        "Hiring % vs Requested",
        compute="_compute_applicants",
        store=False,
        help="(Hired / Requested) * 100",
    )
    created_job_id = fields.Many2one(
        "hr.job",
        string="Created Job (from request)",
        readonly=True,
    )
    department_approved_by_id = fields.Many2one("res.users", string="Department Approved By", readonly=True, copy=False)
    department_approved_date = fields.Datetime(string="Department Approved On", readonly=True, copy=False)
    hr_approved_by_id = fields.Many2one("res.users", string="HR Supervisor Approved By", readonly=True, copy=False)
    hr_approved_date = fields.Datetime(string="HR Supervisor Approved On", readonly=True, copy=False)
    md_approved_by_id = fields.Many2one("res.users", string="MD Approved By", readonly=True, copy=False)
    md_approved_date = fields.Datetime(string="MD Approved On", readonly=True, copy=False)
    is_department_manager_approver = fields.Boolean(compute="_compute_approval_permissions")
    is_hr_supervisor_approver = fields.Boolean(compute="_compute_approval_permissions")
    is_md_approver = fields.Boolean(compute="_compute_approval_permissions")

    @api.model
    def create(self, vals):
        if vals.get('name', '/') == '/':
            vals['name'] = self.env['ir.sequence'].next_by_code('pr.hr.recruitment.request') or '/'
        return super().create(vals)

    @api.depends('job_id', 'created_job_id')
    def _compute_applicants(self):
        applicant = self.env['hr.applicant']
        for rec in self:
            job = rec.job_id or rec.created_job_id
            if not job:
                rec.applicant_count = 0
                rec.hired_count = 0
                rec.hired_ratio = 0
                continue

            applicants = applicant.search([('job_id', '=', job.id)])
            rec.applicant_count = len(applicants)

            hired = applicants.filtered(lambda a: a.emp_id)
            rec.hired_count = len(hired)

            rec.hired_ratio = (
                (rec.hired_count / rec.requested_employees) * 100.0
                if rec.requested_employees
                else 0.0
            )

    @api.depends("department_id")
    def _compute_department_manager_user_id(self):
        for rec in self:
            rec.department_manager_user_id = rec.department_id.manager_id.user_id

    def _compute_approval_permissions(self):
        current_user = self.env.user
        is_hr_supervisor = current_user.has_group("hr_recruitment.group_hr_recruitment_manager")
        is_md = current_user.has_group("hr.group_hr_manager")
        for rec in self:
            rec.is_department_manager_approver = bool(rec.department_manager_user_id and rec.department_manager_user_id == current_user)
            rec.is_hr_supervisor_approver = is_hr_supervisor
            rec.is_md_approver = is_md

    def action_submit(self):
        for rec in self:
            if rec.requested_employees <= 0:
                raise UserError(_("Number of employees must be greater than 0"))

            if rec.is_new_position and not rec.new_job_name:
                raise UserError(_("New job name is required"))
            if not rec.is_new_position and not rec.job_id:
                raise UserError(_("Job position is required"))
            if not rec.department_manager_user_id:
                raise UserError(_("Please set a manager user on the selected department manager employee."))
            rec.write({"state": "dept_approval"})

    def _check_department_approver(self):
        self.ensure_one()
        if self.department_manager_user_id != self.env.user:
            raise UserError(_("Only the selected department's manager can perform this approval."))

    def _check_hr_supervisor_approver(self):
        if not self.env.user.has_group("hr_recruitment.group_hr_recruitment_manager"):
            raise UserError(_("Only HR Supervisor can perform this approval."))

    def _check_md_approver(self):
        if not self.env.user.has_group("hr.group_hr_manager"):
            raise UserError(_("Only MD (HR Manager) can perform this approval."))

    def _approval_get_state_field_name(self):
        self.ensure_one()
        return "state"

    def _approval_get_state_stages(self):
        self.ensure_one()
        return [
            {
                "state": "dept_approval",
                "next_state": "hr_approval",
                "label": "Department Manager",
            },
            {
                "state": "hr_approval",
                "group": "hr_recruitment.group_hr_recruitment_manager",
                "next_state": "md_approval",
                "label": "HR Supervisor",
            },
            {
                "state": "md_approval",
                "group": "hr.group_hr_manager",
                "next_state": "approved",
                "label": "MD",
            },
        ]

    def _approval_is_user_allowed_for_state_stage(self, stage, user):
        self.ensure_one()
        if stage["state"] == "dept_approval":
            return bool(self.department_manager_user_id and self.department_manager_user_id == user)
        return super()._approval_is_user_allowed_for_state_stage(stage, user)

    def _approval_apply_stage_audit(self, stage):
        self.ensure_one()
        now = fields.Datetime.now()
        if stage["state"] == "dept_approval":
            self.sudo().write({
                "department_approved_by_id": self.env.user.id,
                "department_approved_date": now,
            })
        elif stage["state"] == "hr_approval":
            self.sudo().write({
                "hr_approved_by_id": self.env.user.id,
                "hr_approved_date": now,
            })
        elif stage["state"] == "md_approval":
            self.sudo().write({
                "md_approved_by_id": self.env.user.id,
                "md_approved_date": now,
            })

    def _approval_apply_md_business_logic(self):
        self.ensure_one()
        HrJob = self.env["hr.job"]
        job = self.job_id
        if self.is_new_position:
            job_vals = {
                "name": self.new_job_name,
                "department_id": self.department_id.id,
                "no_of_recruitment": self.requested_employees,
                "contract_type_id": self.contract_type_id.id,
                "job_salary": self.job_salary,
                "experience_years": self.experience_years,
                "description": self.job_summary,
            }
            job = HrJob.create(job_vals)
            self.created_job_id = job
        else:
            if job:
                job.no_of_recruitment += self.requested_employees
            else:
                raise UserError(_("no job position is configured for this request"))

    def _approval_progress_state_chain(self, expected_state):
        for rec in self:
            if rec.state != expected_state:
                continue
            stages = rec._approval_get_state_stages()
            stage_idx = rec._approval_get_state_stage_index(stages, rec.state)
            if stage_idx is False:
                continue
            current_stage = stages[stage_idx]
            if not rec._approval_is_user_allowed_for_state_stage(current_stage, self.env.user):
                raise UserError(_("You can approve only your current approval stage."))

            last_idx = rec._approval_get_last_consecutive_stage_index(stages, stage_idx, self.env.user)
            for idx in range(stage_idx, last_idx + 1):
                stage = stages[idx]
                rec._approval_apply_stage_audit(stage)
                if stage["state"] == "md_approval":
                    rec._approval_apply_md_business_logic()

            rec.sudo().write({"state": stages[last_idx]["next_state"]})

    def action_approve_department(self):
        return self._approval_progress_state_chain("dept_approval")

    def action_approve_hr_supervisor(self):
        return self._approval_progress_state_chain("hr_approval")

    def action_approve_md(self):
        return self._approval_progress_state_chain("md_approval")

    def action_approve(self):
        return self.action_approve_md()

    def action_reject(self):
        for rec in self:
            rec.write({"state": "rejected"})

    def action_set_done(self):
        for rec in self:
            rec.write({"state": "done"})

    def action_cancel(self):
        for rec in self:
            rec.write({"state": "cancelled"})

    def action_reset_to_draft(self):
        self.write({"state": "draft"})

    def action_open_job(self):
        self.ensure_one()
        job = self.job_id or self.created_job_id
        if not job:
            raise UserError(_("No job position is configured for this request"))

        return {
            "type": "ir.actions.act_window",
            "res_model": "hr.job",
            "view_mode": "form",
            "res_id": job.id,
            "target": "current",
        }

    def action_open_applicants(self):
        self.ensure_one()
        job = self.job_id or self.created_job_id
        if not job:
            raise UserError(_("No job position is configured for this request"))

        return {
            "type": "ir.actions.act_window",
            "name": _("Applicants"),
            "res_model": "hr.applicant",
            "view_mode": "tree,form",
            "domain": [("job_id", "=", job.id)],
            "target": "current",
        }
