from odoo import api, fields, models


class HrLeaveDashboardOverride(models.Model):
    _inherit = 'hr.leave'

    def _prepare_employee_data(self, employee):
        data = super()._prepare_employee_data(employee)
        if self.env.context.get('show_all_leave_dashboard'):
            data['approval_status_count'] = self.get_approval_status_count(employee.id)
        return data

    @api.model
    def get_current_employee(self):
        if not self.env.context.get('show_all_leave_dashboard'):
            return super().get_current_employee()

        current_employee = self.env.user.employee_ids
        all_employees = self.env['hr.employee'].sudo().search([
            ('active', '=', True),
            ('id', '!=', current_employee.id),
        ])
        return {
            'id': current_employee.id,
            'code': current_employee.code,
            'name': current_employee.name,
            'job_id': current_employee.job_id.id,
            'image_1920': current_employee.image_1920,
            'work_email': current_employee.work_email,
            'work_phone': current_employee.work_phone,
            'resource_calendar_id': current_employee.resource_calendar_id.name,
            'link': '/mail/view?model=%s&res_id=%s' % ('hr.employee.public', current_employee.id),
            'department_id': current_employee.department_id.name,
            'company': current_employee.company_id.name,
            'job_position': current_employee.job_id.name,
            'parent_id': current_employee.parent_id.ids,
            'child_ids': all_employees.ids,
            'child_all_count': len(all_employees),
            'manager': self._prepare_employee_data(current_employee.parent_id) if current_employee.parent_id else {},
            'manager_all_count': len(current_employee.parent_id.ids),
            'children': [self._prepare_employee_data(emp) for emp in all_employees],
        }

    @api.model
    def get_absentees(self):
        if not self.env.context.get('show_all_leave_dashboard'):
            return super().get_absentees()

        now = fields.Datetime.now()
        leaves = self.env['hr.leave'].sudo().search([
            ('state', '=', 'validate'),
            ('date_from', '<=', now),
            ('date_to', '>=', now),
        ])
        return [{'employee_id': l.employee_id.id, 'name': l.employee_id.name, 'date_from': l.date_from, 'date_to': l.date_to} for l in leaves]

    @api.model
    def get_approval_status_count(self, current_employee):
        if not self.env.context.get('show_all_leave_dashboard'):
            return super().get_approval_status_count(current_employee)

        return {
            'validate_count': self.env['hr.leave'].search_count([('employee_id', '=', current_employee), ('state', '=', 'validate')]),
            'confirm_count': self.env['hr.leave'].search_count([('employee_id', '=', current_employee), ('state', '=', 'confirm')]),
            'refuse_count': self.env['hr.leave'].search_count([('employee_id', '=', current_employee), ('state', '=', 'refuse')]),
        }
