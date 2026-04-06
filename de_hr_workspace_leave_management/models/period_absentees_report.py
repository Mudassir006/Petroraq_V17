from odoo import models


class PeriodAbsenteesPdfReport(models.AbstractModel):
    _name = 'report.de_hr_workspace_leave_management.period_absentees_pdf'
    _description = 'Period Absentees PDF Report'

    def _get_report_values(self, docids, data=None):
        data = data or {}
        duration = data.get('duration', 'this_month')
        leaves = self.env['hr.leave'].with_context(show_all_leave_dashboard=True).get_period_absentees(duration)
        return {
            'doc_ids': docids,
            'doc_model': 'hr.leave',
            'docs': self.env['hr.leave'],
            'duration': duration,
            'leaves': leaves,
        }


class PeriodAbsenteesXlsxReport(models.AbstractModel):
    _name = 'report.de_hr_workspace_leave_management.period_absentees_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Period Absentees XLSX Report'

    def generate_xlsx_report(self, workbook, data, records):
        data = data or {}
        duration = data.get('duration', 'this_month')
        leaves = self.env['hr.leave'].with_context(show_all_leave_dashboard=True).get_period_absentees(duration)

        sheet = workbook.add_worksheet('Absentees')
        header = workbook.add_format({'bold': True, 'bg_color': '#D9E1F2'})
        cell = workbook.add_format({'text_wrap': True})

        columns = ['Employee', 'Leave Type', 'From', 'To', 'Days']
        for col, title in enumerate(columns):
            sheet.write(0, col, title, header)

        row = 1
        for leave in leaves:
            sheet.write(row, 0, leave.get('employee_name', ''), cell)
            sheet.write(row, 1, leave.get('leave_type', ''), cell)
            sheet.write(row, 2, str(leave.get('date_from', '')), cell)
            sheet.write(row, 3, str(leave.get('date_to', '')), cell)
            sheet.write(row, 4, leave.get('number_of_days', 0), cell)
            row += 1
