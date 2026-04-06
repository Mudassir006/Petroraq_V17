{
    'name': 'Workspace Leave Management Dashboard',
    'version': '17.0.1.0.0',
    'summary': 'Management dashboard and reporting for all employees leave data',
    'description': 'Adds management leave dashboard and exportable leave analytics under Employee Workspace.',
    'author': 'Aual Faisal',
    'website': 'https://petroraq.com',
    'category': 'Human Resources',
    'depends': ['de_hr_workspace', 'pr_hr_holidays', 'gs_hr_attendance_sheet', 'report_xlsx', 'hr_leave_dashboard'],
    'data': [
        'security/ir.model.access.csv',
        'views/leave_management_views.xml',
        'report/leave_summary_reports.xml',
        'report/leave_summary_templates.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
