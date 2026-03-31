from odoo import models, fields, api, _
from odoo.tools import date_utils
from odoo.osv import expression
from dateutil.relativedelta import relativedelta
from odoo.exceptions import ValidationError
import re
import json
import math
from random import randint
import logging
from datetime import datetime, timedelta
import pandas as pd

_logger = logging.getLogger(__name__)


class HrAttendanceSheet(models.Model):
    """
    """
    # region [Initial]
    _inherit = 'attendance.sheet'
    # endregion [Initial]

    # region [Fields]

    att_notification_id = fields.Many2one(comodel_name='pr.hr.attendance.notification',
                                          string='Attendance Notification')
    tot_late_in_minutes = fields.Float(compute="_compute_sheet_total",
                                       string="Total Late In Minutes",
                                       readonly=True, store=True)
    tot_early_checkout = fields.Float(compute="_compute_sheet_total",
                                      string="Total Early Check Out",
                                      readonly=True, store=True)
    no_early_checkout = fields.Integer(compute="_compute_sheet_total",
                                       string="No of Early Check Out",
                                       readonly=True, store=True)
    tot_early_checkout_amount = fields.Float(compute="_compute_sheet_total",
                                             string="Total Early Check Out Amount",
                                             readonly=True, store=True)
    early_check_out_minutes = fields.Float(compute="_compute_sheet_total",
                                           string="Total Early Checkout Minutes",
                                           readonly=True, store=True)

    # endregion [Fields]

    # region [Compute Methods]

    @api.depends('line_ids.status',
                 'line_ids.day_amount',
                 'line_ids.overtime',
                 'line_ids.overtime_amount',
                 'line_ids.diff_time',
                 'line_ids.diff_amount',
                 'line_ids.late_in',
                 'line_ids.late_in_amount',
                 'line_ids.late_in_minutes',
                 'line_ids.absence_amount',
                 'line_ids.early_check_out',
                 'line_ids.early_check_out_minutes',
                 'line_ids.early_check_out_amount')
    def _compute_sheet_total(self):
        """
        """
        res = super()._compute_sheet_total()
        for sheet in self:
            # Compute Late In Minutes
            late_lines = sheet.line_ids.filtered(lambda l: l.late_in > 0)
            sheet.tot_late_in_minutes = sum(late_lines.mapped("late_in_minutes")) if late_lines else 0
            # Compute Total Early Check Out
            early_lines = sheet.line_ids.filtered(lambda l: l.early_check_out > 0)
            sheet.tot_early_checkout = sum([l.early_check_out for l in early_lines])
            sheet.tot_early_checkout_amount = sum([l.early_check_out_amount for l in early_lines])
            sheet.no_early_checkout = len(early_lines)
            sheet.early_check_out_minutes = sum(early_lines.mapped("early_check_out_minutes")) if early_lines else 0
        return res


    def _get_absence_grace_minutes(self):
        return int(self.env['ir.config_parameter'].sudo().get_param(
            'pr_hr_attendance.absence_grace_minutes',
            default='3'
        ))

    def _get_grace_adjust_minutes(self):
        return float(self.env['ir.config_parameter'].sudo().get_param(
            'pr_hr_attendance.grace_adjust_minutes',
            default='1'
        ))

    def _apply_late_cutoff_policy(self, line):
        """Apply grace-and-cutoff policy before late/shortage/overtime calculations."""
        if not line.ac_sign_in or not line.pl_sign_in:
            return
        if line.status in ('weekend', 'ph', 'leave'):
            return

        grace_minutes = self._get_absence_grace_minutes()
        adjust_minutes = self._get_grace_adjust_minutes()
        late_minutes = (line.ac_sign_in - line.pl_sign_in) * 60.0

        if late_minutes <= 0:
            return

        if late_minutes <= grace_minutes:
            normalized_sign_in = max(line.pl_sign_in - (adjust_minutes / 60.0), 0.0)
            sign_in_diff = line.ac_sign_in - normalized_sign_in
            line.ac_sign_in = normalized_sign_in
            if line.ac_sign_out:
                line.ac_sign_out = max(line.ac_sign_out - sign_in_diff, line.ac_sign_in)
            line.worked_hours = max((line.ac_sign_out or 0.0) - line.ac_sign_in, 0.0)
            line.late_in = 0.0
            line.late_in_minutes = 0.0
            return

        line.status = 'ab'
        line.ac_sign_in = 0.0
        line.ac_sign_out = 0.0
        line.worked_hours = 0.0
        line.act_overtime = 0.0
        line.overtime = 0.0
        line.late_in = 0.0
        line.late_in_minutes = 0.0
        line.early_check_out = 0.0
        line.early_check_out_minutes = 0.0
        line.diff_time = 0.0

    def get_attendances(self):
        res = super().get_attendances()
        for att_sheet in self:
            for line in att_sheet.line_ids:
                self._apply_late_cutoff_policy(line)
                if line.status == "ab":
                    continue
                if line.ac_sign_in:
                    if line.pl_sign_in != 0:
                        if line.pl_sign_in + 1 >= line.ac_sign_in >= line.pl_sign_in - 1:
                            line.late_in = 0
                            line.late_in_minutes = 0
                            # pl_sign_out_custom = line.ac_sign_in + 9
                            pl_sign_out_custom = line.ac_sign_in + (line.pl_sign_out - line.pl_sign_in)
                            if line.ac_sign_out < pl_sign_out_custom:
                                early_check_out = pl_sign_out_custom - line.ac_sign_out
                                line.early_check_out = early_check_out
                                line.early_check_out_minutes = early_check_out * 60
                            # Compute Overtime
                            elif line.ac_sign_out > pl_sign_out_custom and line.employee_id.add_overtime:
                                line.act_overtime = (line.ac_sign_out - pl_sign_out_custom - 2) if (
                                                                                                           line.ac_sign_out - pl_sign_out_custom) > 2 else 0
                                line.overtime = (line.ac_sign_out - pl_sign_out_custom - 2) if (
                                                                                                       line.ac_sign_out - pl_sign_out_custom) > 2 else 0

                        # # Ramadan
                        # if line.pl_sign_in >= line.ac_sign_in:
                        #     line.late_in = 0
                        #     line.late_in_minutes = 0
                        #     if line.ac_sign_out < line.pl_sign_out:
                        #         early_check_out = line.pl_sign_out - line.ac_sign_out
                        #         line.early_check_out = early_check_out
                        #         line.early_check_out_minutes = early_check_out * 60
                        #     # Compute Overtime
                        #     elif line.ac_sign_out > line.pl_sign_out and line.employee_id.add_overtime:
                        #         line.act_overtime = line.ac_sign_out - line.pl_sign_out - 2
                        #         line.overtime = line.ac_sign_out - line.pl_sign_out - 2
                        # elif line.ac_sign_in > (line.pl_sign_in + 1):
                        elif line.ac_sign_in > line.pl_sign_in + 1:
                            line.late_in = line.ac_sign_in - (line.pl_sign_in + 1)
                            line.late_in_minutes = (line.ac_sign_in - (line.pl_sign_in + 1)) * 60

                            # Early Checkout
                            pl_sign_out_custom = line.pl_sign_out + 1
                            if line.ac_sign_out < pl_sign_out_custom:
                                early_check_out = pl_sign_out_custom - line.ac_sign_out
                                line.early_check_out = early_check_out
                                line.early_check_out_minutes = early_check_out * 60
                            # Compute Overtime
                            elif line.ac_sign_out > pl_sign_out_custom and line.employee_id.add_overtime:
                                line.act_overtime = (line.ac_sign_out - pl_sign_out_custom - 2) if (
                                                                                                           line.ac_sign_out - pl_sign_out_custom) > 2 else 0
                                line.overtime = (line.ac_sign_out - pl_sign_out_custom - 2) if (
                                                                                                       line.ac_sign_out - pl_sign_out_custom) > 2 else 0


                        #############
                        elif line.ac_sign_in < line.pl_sign_in - 1:
                            line.late_in = 0
                            line.late_in_minutes = 0
                            # pl_sign_out_custom = line.ac_sign_in + 9
                            pl_sign_out_custom = line.pl_sign_out - 1
                            if line.ac_sign_out < pl_sign_out_custom:
                                early_check_out = pl_sign_out_custom - line.ac_sign_out
                                line.early_check_out = early_check_out
                                line.early_check_out_minutes = early_check_out * 60
                            # Compute Overtime
                            elif line.ac_sign_out > pl_sign_out_custom and line.employee_id.add_overtime:
                                line.act_overtime = (line.ac_sign_out - pl_sign_out_custom - 2) if (
                                                                                                           line.ac_sign_out - pl_sign_out_custom) > 2 else 0
                                line.overtime = (line.ac_sign_out - pl_sign_out_custom - 2) if (
                                                                                                       line.ac_sign_out - pl_sign_out_custom) > 2 else 0

                    # Compute Overtime If Employee Work In Weekend Or In Public Holiday
                    if line.ac_sign_in and line.pl_sign_in == 0:
                        line.act_overtime = line.ac_sign_out - line.ac_sign_in if (
                                                                                          line.ac_sign_out - line.ac_sign_in) > 0 else 0
                        line.overtime = line.ac_sign_out - line.ac_sign_in if (
                                                                                      line.ac_sign_out - line.ac_sign_in) > 0 else 0

                # Check Absence Before Weekend
                # if line.status == "weekend":
                #     line_before_id = att_sheet.line_ids.filtered(lambda l: (l.date == line.date - relativedelta(days=1)) and l.status == "ab")
                #     line_after_id = att_sheet.line_ids.filtered(lambda l: (l.date == line.date + relativedelta(days=1)) and l.status == "ab")
                #     if not line_after_id:
                #         line_after_id = att_sheet.line_ids.filtered(
                #             lambda l: (l.date == line.date + relativedelta(days=2)) and l.status == "ab")
                #     if line_before_id and line_after_id:
                #         line.status = "ab"
            # Check Leave Day Although Weekend
            leave_ids = self.env["hr.leave"].search([
                ("employee_id", "=", att_sheet.employee_id.id),
                ("state", "=", "validate"),
                ("request_date_from", "<=", att_sheet.date_to),
                ("request_date_to", ">=", att_sheet.date_from),
            ])
            for leave in leave_ids:
                # Convert the string dates to pandas datetime objects
                # start_date = pd.to_datetime(leave.request_date_from, format="%d/%m/%Y")
                start_date = pd.to_datetime(leave.request_date_from, dayfirst=True)
                # end_date = pd.to_datetime(leave.request_date_to, format="%d/%m/%Y")
                end_date = pd.to_datetime(leave.request_date_to, dayfirst=True)
                dates_between = pd.date_range(start=start_date, end=end_date)

                for date in dates_between:
                    date_line = date.date()
                    # if att_sheet.employee_id.id == 116:
                    #     print(222)
                    if date_line.weekday() not in [4, 5]:
                        filtered_line = att_sheet.line_ids.filtered(lambda l: l.date == date_line)
                        if filtered_line:
                            filtered_line.status = "leave"
        return res

    # endregion [Compute Methods]

    def _get_workday_lines(self):
        self.ensure_one()

        work_entry_obj = self.env['hr.work.entry.type']
        overtime_work_entry = work_entry_obj.search([('code', '=', 'ATTSHOT')])
        latin_work_entry = work_entry_obj.search([('code', '=', 'ATTSHLI')])
        early_work_entry = work_entry_obj.search([('code', '=', 'ATTSHECO')])
        absence_work_entry = work_entry_obj.search([('code', '=', 'ATTSHAB')])
        difftime_work_entry = work_entry_obj.search([('code', '=', 'ATTSHDT')])
        if not overtime_work_entry:
            raise ValidationError(_(
                'Please Add Work Entry Type For Attendance Sheet Overtime With Code ATTSHOT'))
        if not latin_work_entry:
            raise ValidationError(_(
                'Please Add Work Entry Type For Attendance Sheet Late In With Code ATTSHLI'))
        if not early_work_entry:
            raise ValidationError(_(
                'Please Add Work Entry Type For Attendance Sheet Early Check Out With Code ATTSHECO'))
        if not absence_work_entry:
            raise ValidationError(_(
                'Please Add Work Entry Type For Attendance Sheet Absence With Code ATTSHAB'))
        if not difftime_work_entry:
            raise ValidationError(_(
                'Please Add Work Entry Type For Attendance Sheet Diff Time With Code ATTSHDT'))

        overtime = [{
            'name': "Overtime",
            'code': 'OVT',
            'work_entry_type_id': overtime_work_entry[0].id,
            'sequence': 30,
            'number_of_days': self.no_overtime,
            'number_of_hours': self.tot_overtime,
        }]
        # if not self.overtime_approved:
        #     overtime = []

        absence = [{
            'name': "Absence",
            'code': 'ABS',
            'work_entry_type_id': absence_work_entry[0].id,
            'sequence': 35,
            'number_of_days': self.no_absence,
            'number_of_hours': self.tot_absence,
        }]
        late = [{
            'name': "Late In",
            'code': 'LATE',
            'work_entry_type_id': latin_work_entry[0].id,
            'sequence': 40,
            'number_of_days': self.no_late,
            'number_of_hours': self.tot_late,
        }]
        early_co = [{
            'name': "Early Check Out",
            'code': 'ECO',
            'work_entry_type_id': early_work_entry[0].id,
            'sequence': 40,
            'number_of_days': self.no_early_checkout,
            'number_of_hours': self.tot_early_checkout,
        }]
        difftime = [{
            'name': "Difference time",
            'code': 'DIFFT',
            'work_entry_type_id': difftime_work_entry[0].id,
            'sequence': 45,
            'number_of_days': self.no_difftime,
            'number_of_hours': self.tot_difftime,
        }]
        worked_days_lines = overtime + late + early_co + absence + difftime
        return worked_days_lines

    def _send_notification(self):
        for sheet in self:
            employee_id = sheet.employee_id
            employee_email = employee_id.work_email
            minutes = sheet.tot_late_in_minutes + sheet.early_check_out_minutes
            total_hours = minutes // 60
            total_minutes = minutes % 60
            no_absence = sheet.no_absence
            if not employee_email:
                raise ValidationError(f"The Employee {employee_id.name} Does Not Have Email, Please Check !!")
            if minutes > 0:
                # mail_server = self.env["ir.mail_server"]
                mail = self.env["mail.mail"]
                try:
                    # body_message = f"Hello {employee_id.name},\nWe Want To Inform You That: According To Your Attendance {sheet.date_from}\nWe Deduct From You {round(amount, 2)} SR\n\nThanks"
                    body_message = f"""
                                    Dear Mr/Mrs. {employee_id.name},<br/><br/>
    
    We wish to inform you that a discrepancy in your recorded work hours has been identified for <strong>{sheet.date_from}</strong>. On this date, your attendance reflects a shortage of <strong>{int(round(total_hours, 2))} hours </strong> and <strong>{int(round(total_minutes, 2))} minutes.</strong><br/><br/>
    
    Thank you for your attention to this matter.<br/><br/>
    Best regards,<br/>
    <strong>HR Department</strong><br/>
    Petroraq Engineering
    """
                    receivers_emails = [employee_email]
                    for receiver in receivers_emails:
                        # message = mail_server.build_email(
                        #     # email_from=self.env.company.email or self.env.user.company_id.email,
                        #     email_from="hr@petroraq.com",
                        #     subject=f"{employee_id.code} - Shortage Notifications Of {sheet.date_from} Attendance",
                        #     body=body_message,
                        #     subtype="html",
                        #     email_to=[receiver],
                        # )

                        message = {
                            # email_from=self.env.company.email or self.env.user.company_id.email,
                            "email_from": "hr@petroraq.com",
                            "subject": f"{employee_id.code} - Shortage Notifications Of {sheet.date_from} Attendance",
                            "body_html": body_message,
                            # "recipient_ids": [receiver],
                            "email_to": receiver,
                        }

                        # mail_server.send_email(message)
                        mail_id = mail.sudo().create(message)
                        if mail_id:
                            mail_id.sudo().send()
                except Exception as e:
                    _logger.error("Success email is not sent {}".format(e))
            elif no_absence > 0:
                mail = self.env["mail.mail"]
                try:
                    # body_message = f"Hello {employee_id.name},\nWe Want To Inform You That: According To Your Attendance {sheet.date_from}\nWe Deduct From You {round(amount, 2)} SR\n\nThanks"
                    body_message = f"""
                                                    Dear Mr/Mrs. {employee_id.name},<br/><br/>

                    We wish to inform you that a discrepancy in your recorded work hours has been identified for <strong>{sheet.date_from}</strong>. On this date, your attendance reflects an absence of <strong>{int(round(no_absence, 2))} days </strong>.</strong><br/><br/>

                    Thank you for your attention to this matter.<br/><br/>
                    Best regards,<br/>
                    <strong>HR Department</strong><br/>
                    Petroraq Engineering
                    """
                    receivers_emails = [employee_email]
                    for receiver in receivers_emails:
                        message = {
                            "email_from": "hr@petroraq.com",
                            "subject": f"{employee_id.code} - Shortage Notifications Of {sheet.date_from} Attendance",
                            "body_html": body_message,
                            "email_to": receiver,
                        }

                        mail_id = mail.sudo().create(message)
                        if mail_id:
                            mail_id.sudo().send()
                except Exception as e:
                    _logger.error("Success email is not sent {}".format(e))
            self.write({'state': 'done'})


class AttendanceSheetLine(models.Model):
    # region [Initial]
    _inherit = 'attendance.sheet.line'
    # endregion [Initial]

    # region [Fields]

    late_in_minutes = fields.Float("Late In Minutes", readonly=True)
    early_check_out_minutes = fields.Float("Early Checkout Minutes", readonly=True)
    early_check_out = fields.Float("Early Checkout", readonly=True)
    early_check_out_amount = fields.Float("Early Checkout Amount", readonly=True,
                                          compute="_compute_early_check_out_amount", store=True)

    # endregion [Fields]

    @api.depends("employee_id",
                 "early_check_out",
                 "date",
                 "pl_sign_in",
                 "pl_sign_out",
                 "employee_id.contract_id",
                 "employee_id.contract_id.gross_amount",
                 "att_sheet_id",
                 "att_sheet_id.att_policy_id",
                 "att_sheet_id.att_policy_id.early_rule_id",
                 )
    def _compute_early_check_out_amount(self):
        for line in self:
            if line.employee_id and line.date and line.early_check_out > 0:
                start_of_month = date_utils.start_of(line.date, 'month')
                end_of_month = date_utils.end_of(line.date, 'month')
                month_days = (end_of_month - start_of_month).days + 1
                net_salary_amount = line.employee_id.contract_id.gross_amount
                day_amount = net_salary_amount / month_days
                # hours_per_day = line.pl_sign_out - line.pl_sign_in
                hours_per_day = line.employee_id.contract_id.resource_calendar_id.hours_per_day
                line.early_check_out_amount = (line.early_check_out * day_amount) / hours_per_day
            else:
                line.early_check_out_amount = 0

                # early_check_out_policy = line.att_sheet_id.att_policy_id.early_rule_id if (line.att_sheet_id.att_policy_id and line.att_sheet_id.att_policy_id.early_rule_id) else False
                # if early_check_out_policy:
                #     early_check_out_line = early_check_out_policy.line_ids[0]
                #     minutes = early_check_out_line.time
                #     l_type = early_check_out_line.type
                #     rate = early_check_out_line.rate
                #     amount = early_check_out_line.amount
                #     if l_type == "fix":
                #         line.early_check_out_amount = (line.early_check_out * 60 * amount) / minutes
                #     elif l_type == "rate":
                #         line.early_check_out_amount = (line.early_check_out * day_amount) / hours_per_day
                #     else:
                #         line.early_check_out_amount = 0
                # else:
                #     line.early_check_out_amount = 0
