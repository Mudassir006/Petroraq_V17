import pytz
from odoo import api, fields, models


class HrLeaveDashboardOverride(models.Model):
    _inherit = 'hr.leave'

    def _prepare_employee_data(self, employee):
        return {
            'id': employee.id,
            'code': employee.code,
            'name': employee.name,
            'job_id': employee.job_id.name,
            'approval_status_count': self.get_approval_status_count(employee.id),
        }

    @api.model
    def get_current_employee(self):
        current_employee = self.env.user.employee_ids
        if self.env.context.get('show_all_leave_dashboard'):
            children = self.env['hr.employee'].sudo().search([('active', '=', True), ('id', '!=', current_employee.id)])
        else:
            children = current_employee.child_ids
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
            'child_ids': children.ids,
            'child_all_count': len(children),
            'manager': self._prepare_employee_data(current_employee.parent_id) if current_employee.parent_id else {},
            'manager_all_count': len(current_employee.parent_id.ids),
            'children': [self._prepare_employee_data(child) for child in children if child != current_employee],
        }

    @api.model
    def get_absentees(self):
        now = fields.Datetime.now()
        domain = [('state', '=', 'validate'), ('date_from', '<=', now), ('date_to', '>=', now)]
        if not self.env.context.get('show_all_leave_dashboard'):
            current_employee = self.env.user.employee_ids
            domain.append(('employee_id', 'in', current_employee.child_ids.ids))
        leaves = self.env['hr.leave'].sudo().search(domain)
        return [{'employee_id': l.employee_id.id, 'name': l.employee_id.name, 'date_from': l.date_from, 'date_to': l.date_to} for l in leaves]

    @api.model
    def get_current_shift(self):
        current_employee = self.env.user.employee_ids
        employee_tz = current_employee.tz or self.env.context.get('tz')
        employee_pytz = pytz.timezone(employee_tz) if employee_tz else pytz.utc
        employee_datetime = fields.Datetime.now().astimezone(employee_pytz)
        hour = employee_datetime.strftime('%H')
        minute = employee_datetime.strftime('%M')
        day = employee_datetime.strftime('%A')
        time = hour + '.' + minute
        day_num = '0' if day == 'Monday' else '1' if day == 'Tuesday' else '2' if day == 'Wednesday' else '3' if day == 'Thursday' else '4' if day == 'Friday' else '5' if day == 'Saturday' else '6'
        for shift in current_employee.resource_calendar_id.attendance_ids:
            if shift.dayofweek == day_num and shift.hour_from <= float(time) <= shift.hour_to:
                return shift.name
        return False

    @api.model
    def get_upcoming_holidays(self):
        employee_tz = self.env.user.employee_ids.tz or self.env.context.get('tz')
        employee_pytz = pytz.timezone(employee_tz) if employee_tz else pytz.utc
        employee_datetime = fields.Datetime.now().astimezone(employee_pytz)
        holidays = self.env['hr.public.holiday'].sudo().search([('state', '=', 'active')])
        return [holiday.read()[0] for holiday in holidays if employee_datetime.date() < holiday.date_to]

    @api.model
    def get_approval_status_count(self, current_employee):
        return {
            'validate_count': self.env['hr.leave'].search_count([('employee_id', '=', current_employee), ('state', '=', 'validate')]),
            'confirm_count': self.env['hr.leave'].search_count([('employee_id', '=', current_employee), ('state', '=', 'confirm')]),
            'refuse_count': self.env['hr.leave'].search_count([('employee_id', '=', current_employee), ('state', '=', 'refuse')]),
        }

    @api.model
    def get_all_validated_leaves(self):
        domain = [('state', '=', 'validate')]
        if not self.env.context.get('show_all_leave_dashboard'):
            current_employee = self.env.user.employee_ids
            domain.append(('employee_id', 'in', current_employee.child_ids.ids))
        leaves = self.env['hr.leave'].sudo().search(domain)
        return [{
            'id': leave.id,
            'employee_id': leave.employee_id.id,
            'employee_name': leave.employee_id.name,
            'request_date_from': leave.request_date_from,
            'request_date_to': leave.request_date_to,
            'leave_type_id': leave.holiday_status_id.id,
            'leave_type': leave.holiday_status_id.name,
            'number_of_days': leave.number_of_days,
        } for leave in leaves]
