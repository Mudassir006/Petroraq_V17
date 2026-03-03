from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ExpenseBucket(models.Model):
    _name = "pr.expense.bucket"
    _description = "PR Expense Bucket"

    name = fields.Char(required=True)
    scope = fields.Selection(
        [("department", "Department"), ("project", "Project")],
        string="Applies To",
        required=True,
        default="department",
    )
    expense_type = fields.Selection(
        [("opex", "Opex"), ("capex", "Capex")],
        string="Expense Type",
        required=True,
    )
    department_id = fields.Many2one("hr.department", string="Department")
    project_id = fields.Many2one("project.project", string="Project")
    budget_amount = fields.Float(string="Bucket Budget", required=True)
    cost_center_ids = fields.One2many(
        "account.analytic.account",
        "expense_bucket_id",
        string="Cost Centers",
    )
    cost_center_budget_total = fields.Float(
        string="Cost Center Budget Total",
        compute="_compute_cost_center_budget_total",
    )
    budget_left = fields.Float(
        string="Budget Left",
        compute="_compute_budget_left",
    )

    @api.depends("cost_center_ids", "cost_center_ids.budget_allowance")
    def _compute_cost_center_budget_total(self):
        for rec in self:
            rec.cost_center_budget_total = sum(rec.cost_center_ids.mapped("budget_allowance"))

    @api.depends("budget_amount", "cost_center_budget_total")
    def _compute_budget_left(self):
        for rec in self:
            rec.budget_left = (rec.budget_amount or 0.0) - (rec.cost_center_budget_total or 0.0)

    @api.onchange("scope")
    def _onchange_scope(self):
        for rec in self:
            if rec.scope == "department":
                rec.project_id = False
            else:
                rec.department_id = False

    @api.constrains("scope", "department_id", "project_id")
    def _check_scope_target(self):
        for rec in self:
            if rec.scope == "department" and not rec.department_id:
                raise ValidationError("Department is required when scope is Department.")
            if rec.scope == "project" and not rec.project_id:
                raise ValidationError("Project is required when scope is Project.")
