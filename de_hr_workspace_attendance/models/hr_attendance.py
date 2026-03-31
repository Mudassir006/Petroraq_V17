from datetime import datetime, timedelta, timezone

from odoo import api, fields, models, _, SUPERUSER_ID
from odoo.tools import date_utils
from dateutil.relativedelta import relativedelta


class HrAttendance(models.Model):
    # region [Initial]
    _inherit = 'hr.attendance'
    # endregion [Initial]

    shortage_time = fields.Text(string="Shortage Time", compute="_compute_shortage_time_text")
    minute_rate = fields.Char(string="Minute Rate", compute="_compute_minute_rate_text")
    show_shortage_button = fields.Boolean(compute="_compute_shortage_time_text")

    def action_open_shortage_request(self):
        for rec in self:
            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
            url = f"{base_url}/shortage_request?check_in={rec.check_in}&check_out={rec.check_out}"
            if rec.shortage_time:
                url+= f"&shortage_text={rec.shortage_time}"
            action = {
                'type': 'ir.actions.act_url',
                'url': url,
                'target': 'new',
            }
            return action


    def _get_cutoff_policy_values(self):
        params = self.env['ir.config_parameter'].sudo()
        cutoff_hour = int(params.get_param('pr_hr_attendance.absence_cutoff_hour', default='9'))
        cutoff_minute = int(params.get_param('pr_hr_attendance.absence_cutoff_minute', default='0'))
        grace_minutes = int(params.get_param('pr_hr_attendance.absence_grace_minutes', default='0'))
        normalize_minute_delta = int(params.get_param('pr_hr_attendance.grace_normalize_minutes', default='1'))
        return cutoff_hour, cutoff_minute, grace_minutes, normalize_minute_delta

    def _apply_checkin_cutoff_policy(self, employee, check_in):
        """Return normalized check_in or False (reject attendance) based on cutoff policy."""
        if not employee or not check_in:
            return check_in

        cutoff_hour, cutoff_minute, grace_minutes, normalize_minute_delta = self._get_cutoff_policy_values()
        employee_tz = employee.tz or self.env.user.tz or 'UTC'
        local_check_in = fields.Datetime.context_timestamp(self.with_context(tz=employee_tz), check_in)
        local_cutoff = local_check_in.replace(
            hour=cutoff_hour,
            minute=cutoff_minute,
            second=0,
            microsecond=0,
        )

        if local_check_in <= local_cutoff:
            return check_in

        late_minutes = (local_check_in - local_cutoff).total_seconds() / 60.0
        if grace_minutes and late_minutes <= grace_minutes:
            normalized_local = local_cutoff - timedelta(minutes=normalize_minute_delta)
            return fields.Datetime.to_datetime(normalized_local.astimezone(timezone.utc).replace(tzinfo=None))

        return False

    @api.model_create_multi
    def create(self, vals_list):
        records = self.browse()
        for vals in vals_list:
            employee = self.env['hr.employee'].browse(vals.get('employee_id')) if vals.get('employee_id') else False
            if vals.get('check_in') and employee:
                check_in_dt = fields.Datetime.to_datetime(vals['check_in'])
                normalized_check_in = self._apply_checkin_cutoff_policy(employee, check_in_dt)
                if not normalized_check_in:
                    continue
                vals['check_in'] = fields.Datetime.to_string(normalized_check_in)
            records |= super(HrAttendance, self).create([vals])
        return records

    def write(self, vals):
        if vals.get('check_in'):
            for rec in self:
                employee = rec.employee_id
                check_in_dt = fields.Datetime.to_datetime(vals['check_in'])
                normalized_check_in = self._apply_checkin_cutoff_policy(employee, check_in_dt)
                if not normalized_check_in:
                    rec.unlink()
                    continue
                super(HrAttendance, rec).write({**vals, 'check_in': fields.Datetime.to_string(normalized_check_in)})
            return True
        return super().write(vals)

    @api.depends("employee_id", 'check_in', 'check_out', "worked_hours", "employee_id.resource_calendar_id")
    def _compute_shortage_time_text(self):
        for rec in self:
            today_date = fields.Date.today()
            pl_sign_in = rec.check_in.replace(hour=8, minute=0, second=0)
            pl_sign_out = rec.check_in.replace(hour=17, minute=0, second=0)

            late_in_minutes = 0
            early_check_out_minutes = 0
            if rec.check_in:
                check_in = rec.check_in + timedelta(hours=3)
                check_out = rec.check_out + timedelta(hours=3)
                if pl_sign_in + timedelta(hours=1) >= check_in >= pl_sign_in - timedelta(hours=1):
                    late_in = 0
                    late_in_minutes = 0
                    pl_sign_out_custom = check_in + (pl_sign_out - pl_sign_in)
                    if check_out < pl_sign_out_custom:
                        early_check_out = pl_sign_out_custom - check_out
                        early_check_out_minutes = early_check_out.total_seconds() / 60

                elif check_in > pl_sign_in + timedelta(hours=1):
                    late_in = check_in - (pl_sign_in + timedelta(hours=1))
                    late_in_minutes = late_in.total_seconds() / 60

                    # Early Checkout
                    pl_sign_out_custom = pl_sign_out + timedelta(hours=1)
                    if check_out < pl_sign_out_custom:
                        early_check_out = pl_sign_out_custom - check_out
                        early_check_out_minutes = early_check_out.total_seconds() / 60


                #############
                elif check_in < pl_sign_in - timedelta(hours=1):
                    late_in = 0
                    late_in_minutes = 0
                    pl_sign_out_custom = pl_sign_out - timedelta(hours=1)
                    if check_out < pl_sign_out_custom:
                        early_check_out = pl_sign_out_custom - check_out
                        early_check_out_minutes = early_check_out / 60

            if isinstance(late_in_minutes, timedelta):
                late_in_minutes = late_in_minutes.total_seconds() / 60 / 60
            if isinstance(early_check_out_minutes, timedelta):
                early_check_out_minutes = early_check_out_minutes.total_seconds() / 60
            all_shortage_minutes = late_in_minutes + early_check_out_minutes
            if all_shortage_minutes > 0:
                total_hours = all_shortage_minutes // 60
                total_minutes = all_shortage_minutes % 60
                rec.shortage_time = f"{round(total_hours, 2)} Hours And {round(total_minutes, 2)} Minutes"
                # if rec.check_in < (fields.Date.today() + relativedelta(days=1)):
                if rec.check_in.date() == today_date or today_date == (rec.check_in.date() + relativedelta(days=1)):
                    rec.show_shortage_button = True
                else:
                    rec.show_shortage_button = False
            else:
                rec.shortage_time = False
                rec.show_shortage_button = False

    @api.depends("employee_id", "check_in", "employee_id.contract_id", "employee_id.resource_calendar_id", "employee_id.resource_calendar_id.hours_per_day")
    def _compute_minute_rate_text(self):
        self = self.sudo()
        for rec in self:
            rec = rec.sudo()
            if rec.employee_id and rec.check_in:
                contract_id = rec.employee_id.contract_id.with_user(SUPERUSER_ID)
                resource_calendar_id = rec.employee_id.resource_calendar_id
                hours_per_day = resource_calendar_id.hours_per_day
                gross_salary = contract_id.sudo().gross_amount
                start_of_month = date_utils.start_of(rec.check_in, 'month')
                end_of_month = date_utils.end_of(rec.check_in, 'month')
                month_days = (end_of_month - start_of_month).days + 1
                day_amount = gross_salary / month_days
                hour_amount_rate = day_amount / hours_per_day
                rec.minute_rate = f"{round((hour_amount_rate / 60), 2)} SR"
            else:
                rec.minute_rate = False


