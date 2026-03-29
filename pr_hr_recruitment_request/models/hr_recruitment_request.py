from odoo import models, fields, api, _

from odoo.exceptions import ValidationError, UserError


class HrRecruitmentRequest(models.Model):
    _name = 'hr.recruitment.request'
    _description = 'HR Recruitment Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
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
            ("to_approve", "To Approve"),
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

    def action_submit(self):
        for rec in self:
            if rec.requested_employees <= 0:
                raise UserError(_("Number of employees must be greater than 0"))

            if rec.is_new_position and not rec.new_job_name:
                raise UserError(_("New job name is required"))
            if not rec.is_new_position and not rec.job_id:
                raise UserError(_("Job position is required"))
            rec.write({"state": "to_approve"})

    def action_approve(self):
        HrJob = self.env["hr.job"]
        for rec in self:
            job = rec.job_id
            if rec.is_new_position:
                job_vals = {
                    "name": rec.new_job_name,
                    "department_id": rec.department_id.id,
                    "no_of_recruitment": rec.requested_employees,

                    # new fields
                    "contract_type_id": rec.contract_type_id.id,
                    "job_salary": rec.job_salary,
                    "experience_years": rec.experience_years,
                    "description": rec.job_summary,
                }

                job = HrJob.create(job_vals)
                rec.created_job_id = job

            else:
                if job:
                    job.no_of_recruitment += rec.requested_employees
                else:
                    raise UserError(_("no job position is configured for this request"))

            rec.write({"state": "approved"})

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
