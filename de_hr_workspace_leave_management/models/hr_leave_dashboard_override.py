import pytz
from datetime import timedelta
from odoo import api, fields, models


class HrLeaveDashboardOverride(models.Model):
    _inherit = 'hr.leave'

    @api.model
    def _get_period_date_range(self, duration):
        today = fields.Date.context_today(self)
        if duration == 'today':
            return today, today
        if duration == 'this_week':
            start = today - timedelta(days=today.weekday())
            end = start + timedelta(days=6)
            return start, end
        if duration == 'this_year':
            start = today.replace(month=1, day=1)
            end = today.replace(month=12, day=31)
            return start, end
        start = today.replace(day=1)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end = start.replace(month=start.month + 1, day=1) - timedelta(days=1)
        return start, end

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
        current_employee = self.env.user.employee_id
        if not current_employee and self.env.context.get('employee_id'):
            current_employee = self.env['hr.employee'].browse(self.env.context['employee_id'])
        if not current_employee:
            return {}
        if self.env.context.get('show_all_leave_dashboard'):
            children = self.env['hr.employee'].sudo().search([('active', '=', True)])
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
            'children': [self._prepare_employee_data(child) for child in children],
        }

    @api.model
    def get_absentees(self):
        now = fields.Datetime.now()
        domain = [('state', '=', 'validate'), ('date_from', '<=', now), ('date_to', '>=', now)]
        if not self.env.context.get('show_all_leave_dashboard'):
            current_employee = self.env.user.employee_id
            if current_employee:
                domain.append(('employee_id', 'in', current_employee.child_ids.ids))
        leaves = self.env['hr.leave'].sudo().search(domain)
        return [{'employee_id': l.employee_id.id, 'name': l.employee_id.name, 'date_from': l.date_from, 'date_to': l.date_to} for l in leaves]

    @api.model
    def get_current_shift(self):
        current_employee = self.env.user.employee_id
        if not current_employee and self.env.context.get('employee_id'):
            current_employee = self.env['hr.employee'].browse(self.env.context['employee_id'])
        if not current_employee:
            return False
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
        employee_tz = self.env.user.employee_id.tz or self.env.context.get('tz')
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
            current_employee = self.env.user.employee_id
            if current_employee:
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

    @api.model
    def get_period_absentees(self, duration='this_month'):
        date_from, date_to = self._get_period_date_range(duration or 'this_month')
        today = fields.Date.context_today(self)
        if date_from > today:
            return []
        date_to = min(date_to, today)
        employees = self.env['hr.employee'].sudo().search([('active', '=', True)])
        holidays = self.env['hr.public.holiday'].sudo().search([
            ('state', '=', 'active'),
            ('date_from', '<=', date_to),
            ('date_to', '>=', date_from),
        ])

        public_holiday_dates = set()
        for holiday in holidays:
            current = max(holiday.date_from, date_from)
            end = min(holiday.date_to, date_to)
            while current <= end:
                public_holiday_dates.add(current)
                current += timedelta(days=1)

        leave_days_map = {employee.id: set() for employee in employees}
        approved_leaves = self.env['hr.leave'].sudo().search([
            ('state', '=', 'validate'),
            ('employee_id', 'in', employees.ids),
            ('request_date_from', '<=', date_to),
            ('request_date_to', '>=', date_from),
        ])
        for leave in approved_leaves:
            current = max(leave.request_date_from, date_from)
            end = min(leave.request_date_to, date_to)
            while current <= end:
                leave_days_map.setdefault(leave.employee_id.id, set()).add(current)
                current += timedelta(days=1)

        attendance_days_map = {employee.id: set() for employee in employees}
        date_from_dt = fields.Datetime.to_datetime(date_from)
        date_to_dt = fields.Datetime.to_datetime(date_to) + timedelta(days=1)
        attendances = self.env['hr.attendance'].sudo().search([
            ('employee_id', 'in', employees.ids),
            ('check_in', '>=', date_from_dt),
            ('check_in', '<', date_to_dt),
        ])
        for attendance in attendances:
            attendance_days_map.setdefault(attendance.employee_id.id, set()).add(attendance.check_in.date())

        rows = []
        for employee in employees:
            calendar = employee.resource_calendar_id
            if calendar and calendar.attendance_ids:
                working_days = {int(a.dayofweek) for a in calendar.attendance_ids}
            else:
                working_days = {0, 1, 2, 3, 4}

            absent_count = 0
            current = date_from
            while current <= date_to:
                if (
                    current.weekday() in working_days
                    and current not in public_holiday_dates
                    and current not in leave_days_map.get(employee.id, set())
                    and current not in attendance_days_map.get(employee.id, set())
                ):
                    absent_count += 1
                current += timedelta(days=1)
            rows.append({
                'employee_id': employee.id,
                'employee_name': employee.name,
                'absent_days': absent_count,
            })
        return rows

    @api.model
    def get_period_leaves(self, duration='this_month', category=None):
        date_from, date_to = self._get_period_date_range(duration or 'this_month')
        domain = [
            ('state', 'in', ['confirm', 'validate']),
            ('request_date_from', '<=', date_to),
            ('request_date_to', '>=', date_from),
        ]
        leaves = self.env['hr.leave'].sudo().search(domain, order='request_date_from asc')
        rows = [{
            'employee_id': leave.employee_id.id,
            'employee_name': leave.employee_id.name,
            'leave_type': leave.holiday_status_id.name,
            'state': leave.state,
            'date_from': leave.request_date_from,
            'date_to': leave.request_date_to,
            'number_of_days': leave.number_of_days,
        } for leave in leaves]
        if not category:
            return rows

        def _category(value):
            name = (value or '').lower()
            if 'sick' in name:
                return 'sick'
            if 'annual' in name:
                return 'annual'
            return 'other'

        return [row for row in rows if _category(row.get('leave_type')) == category]

    @api.model
    def get_period_leave_type_metrics(self, duration='this_month'):
        metrics = {}
        for leave in self.get_period_leaves(duration):
            leave_type = leave['leave_type'] or 'Unknown'
            if leave_type not in metrics:
                metrics[leave_type] = {
                    'leave_type': leave_type,
                    'approved_days': 0.0,
                    'approved_count': 0,
                    'pending_count': 0,
                    'refused_count': 0,
                }
            if leave['state'] == 'validate':
                metrics[leave_type]['approved_days'] += leave['number_of_days'] or 0.0
                metrics[leave_type]['approved_count'] += 1
            elif leave['state'] == 'confirm':
                metrics[leave_type]['pending_count'] += 1
            elif leave['state'] == 'refuse':
                metrics[leave_type]['refused_count'] += 1
        return list(metrics.values())

    @api.model
    def get_period_dashboard_data(self, duration='this_month'):
        return {
            'duration': duration,
            'absentees': self.get_period_absentees(duration),
            'sick_leaves': self.get_period_leaves(duration, 'sick'),
            'annual_leaves': self.get_period_leaves(duration, 'annual'),
            'other_leaves': self.get_period_leaves(duration, 'other'),
            'leave_type_metrics': self.get_period_leave_type_metrics(duration),
        }
