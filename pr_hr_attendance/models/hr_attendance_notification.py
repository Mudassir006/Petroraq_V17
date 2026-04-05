from odoo import models, fields, api, _
from odoo.tools import date_utils
from odoo.osv import expression
from dateutil.relativedelta import relativedelta
from odoo.exceptions import ValidationError, UserError
import re
import json
import math
from random import randint
import logging
from datetime import datetime, timedelta
import pandas as pd


_logger = logging.getLogger(__name__)


class HrAttendanceNotification(models.Model):
    """
    """
    # region [Initial]
    _name = 'pr.hr.attendance.notification'
    _description = 'Hr Attendance Notification'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = "id"
    # endregion [Initial]

    # region [Fields]

    name = fields.Char(string="Name")
    date = fields.Date(string="Date", required=True, default=fields.Date.today)
    company_id = fields.Many2one('res.company', string='Company', tracking=True, default=lambda self: self.env.company, required=True)
    att_sheet_ids = fields.One2many(comodel_name='attendance.sheet',
                                    string='Attendance Sheets',
                                    inverse_name='att_notification_id')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('gen', 'Notifications Generated'),
        ('sub', 'Notifications Submitted'),
        ('done', 'Sent')], default='draft', track_visibility='onchange',
        string='Status', required=True, readonly=True, index=True, )
    att_sheet_ids_count = fields.Integer(compute="_compute_att_sheet_ids_count")
    # endregion [Fields]

    @api.depends("att_sheet_ids")
    def _compute_att_sheet_ids_count(self):
        for notification in self:
            notification.att_sheet_ids_count = len(notification.att_sheet_ids)

    def open_related_attendance_sheets(self):
        self.ensure_one()
        form_id = self.env.ref('gs_hr_attendance_sheet.attendance_sheet_form_view').id
        list_id = self.env.ref('gs_hr_attendance_sheet.attendance_sheet_tree_view').id
        return {
            'type': 'ir.actions.act_window',
            'name': _('Attendance Sheets'),
            'res_model': 'attendance.sheet',
            'view_type': 'list',
            'view_mode': 'list',
            'views': [[list_id, 'list'], [form_id, 'form']],
            'domain': [('id', 'in', self.att_sheet_ids.ids)],
            'target': 'current'
        }


    @api.onchange("date")
    def _onchange_date(self):
        self.ensure_one()
        if self.date:
            self.name = f"Attendance Notifications For {self.date}"

    def action_att_gen(self):
        return self.write({'state': 'gen'})

    def gen_att_sheet(self):
        att_sheets = self.env['attendance.sheet']
        att_sheet_obj = self.env['attendance.sheet']
        for notification in self:
            date = notification.date
            employee_ids = self.env['hr.employee'].search(
                [
                    ('company_id', '=', notification.company_id.id),
                    ("active", "=", True),
                    ("compute_attendance", "=", True),
                    ("attendance_email_enabled", "=", True),
                ]
            )

            if not employee_ids:
                raise UserError(_("There is no  Employees In This Company"))
            for employee in employee_ids:
                # Add Custom Condition
                if not employee.contract_id or (employee.contract_id.state != "open"):
                    raise UserError(_(
                        "There is no  Running contracts for :%s " % employee.name))
                else:

                    new_sheet = att_sheet_obj.new({
                        'employee_id': employee.id,
                        'date_from': date,
                        'date_to': date,
                        'att_notification_id': notification.id
                    })
                    new_sheet.onchange_employee()
                    values = att_sheet_obj._convert_to_write(new_sheet._cache)
                    att_sheet_id = att_sheet_obj.create(values)

                    att_sheet_id.get_attendances()
                    att_sheets += att_sheet_id
            notification.action_att_gen()

    def submit_att_sheet(self):
        for notification in self:
            if notification.state != "gen":
                continue
            for sheet in notification.att_sheet_ids:
                if sheet.state == 'draft':
                    sheet.action_confirm()

            notification.write({'state': 'sub'})

    def action_done(self):
        for notification in self:
            if notification.state != "sub":
                continue
            for sheet in notification.att_sheet_ids:
                if sheet.state == 'confirm':
                    sheet._send_notification()
            notification.write({'state': 'done'})

    @api.model
    def cron_send_daily_attendance_notifications(self):
        """Send same-day attendance alerts, generating attendance sheets if missing."""
        today = fields.Date.context_today(self)
        companies = self.env['res.company'].search([])
        attendance_sheet_obj = self.env['attendance.sheet']
        for company in companies:
            notification = self.search(
                [('date', '=', today), ('company_id', '=', company.id)],
                order='id desc',
                limit=1,
            )
            if not notification:
                notification = self.create({
                    'name': f"Attendance Notifications For {today}",
                    'date': today,
                    'company_id': company.id,
                })

            if notification.state == 'done':
                continue

            today_sheets = attendance_sheet_obj.search([
                ('company_id', '=', company.id),
                ('date_from', '=', today),
                ('date_to', '=', today),
                ('employee_id.active', '=', True),
                ('employee_id.compute_attendance', '=', True),
                ('employee_id.attendance_email_enabled', '=', True),
                '|',
                ('att_notification_id', '=', False),
                ('att_notification_id', '=', notification.id),
            ])

            if today_sheets:
                today_sheets.write({'att_notification_id': notification.id})
            elif notification.state == 'draft':
                notification.gen_att_sheet()

            if notification.state == 'draft':
                notification.write({'state': 'gen'})
            if notification.state == 'gen':
                notification.submit_att_sheet()
            if notification.state == 'sub':
                notification.action_done()
