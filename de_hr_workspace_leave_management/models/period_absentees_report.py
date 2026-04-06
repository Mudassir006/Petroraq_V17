from odoo import models


class PeriodAbsenteesPdfReport(models.AbstractModel):
    _name = 'report.de_hr_workspace_leave_management.period_absentees_pdf'
    _description = 'Period Absentees PDF Report'

    def _get_report_values(self, docids, data=None):
        data = data or {}
        duration = data.get('duration', 'this_month')
        dashboard_data = self.env['hr.leave'].with_context(show_all_leave_dashboard=True).get_period_dashboard_data(duration)
        return {
            'doc_ids': docids,
            'doc_model': 'hr.leave',
            'docs': self.env['hr.leave'],
            'duration': duration,
            'absentees': dashboard_data.get('absentees', []),
            'leaves': dashboard_data.get('leaves', []),
            'leave_type_metrics': dashboard_data.get('leave_type_metrics', []),
        }


class PeriodAbsenteesXlsxReport(models.AbstractModel):
    _name = 'report.de_hr_workspace_leave_management.period_absentees_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Period Absentees XLSX Report'

    def generate_xlsx_report(self, workbook, data, records):
        data = data or {}
        duration = data.get('duration', 'this_month')
        dashboard_data = self.env['hr.leave'].with_context(show_all_leave_dashboard=True).get_period_dashboard_data(duration)
        absentees = dashboard_data.get('absentees', [])
        leaves = dashboard_data.get('leaves', [])
        leave_type_metrics = dashboard_data.get('leave_type_metrics', [])

        sheet = workbook.add_worksheet('Leave Metrics')
        header = workbook.add_format({'bold': True, 'bg_color': '#D9E1F2'})
        cell = workbook.add_format({'text_wrap': True})
        title = workbook.add_format({'bold': True})

        row = 0
        sheet.write(row, 0, f'Period: {duration}', title)
        row += 2

        sheet.write(row, 0, 'Absentees (Approved Leaves)', title)
        row += 1
        columns = ['Employee', 'Leave Type', 'From', 'To', 'Days']
        for col, title in enumerate(columns):
            sheet.write(row, col, title, header)
        row += 1
        for leave in absentees:
            sheet.write(row, 0, leave.get('employee_name', ''), cell)
            sheet.write(row, 1, leave.get('leave_type', ''), cell)
            sheet.write(row, 2, str(leave.get('date_from', '')), cell)
            sheet.write(row, 3, str(leave.get('date_to', '')), cell)
            sheet.write(row, 4, leave.get('number_of_days', 0), cell)
            row += 1

        row += 2
        sheet.write(row, 0, 'All Leaves (Approved/Pending/Refused)', title)
        row += 1
        leave_columns = ['Employee', 'Leave Type', 'State', 'From', 'To', 'Days']
        for col, col_name in enumerate(leave_columns):
            sheet.write(row, col, col_name, header)
        row += 1
        for leave in leaves:
            sheet.write(row, 0, leave.get('employee_name', ''), cell)
            sheet.write(row, 1, leave.get('leave_type', ''), cell)
            sheet.write(row, 2, leave.get('state', ''), cell)
            sheet.write(row, 3, str(leave.get('date_from', '')), cell)
            sheet.write(row, 4, str(leave.get('date_to', '')), cell)
            sheet.write(row, 5, leave.get('number_of_days', 0), cell)
            row += 1

        row += 2
        sheet.write(row, 0, 'Leave Type Metrics', title)
        row += 1
        metric_columns = ['Leave Type', 'Approved Days', 'Approved', 'Pending', 'Refused']
        for col, col_name in enumerate(metric_columns):
            sheet.write(row, col, col_name, header)
        row += 1
        for metric in leave_type_metrics:
            sheet.write(row, 0, metric.get('leave_type', ''), cell)
            sheet.write(row, 1, metric.get('approved_days', 0), cell)
            sheet.write(row, 2, metric.get('approved_count', 0), cell)
            sheet.write(row, 3, metric.get('pending_count', 0), cell)
            sheet.write(row, 4, metric.get('refused_count', 0), cell)
            row += 1
