{
    'name': 'Custom PR System',
    # 'version': '17.0.1.0.1',   
    'version': '1.0',
    'category': 'Operations',
    'summary': 'Module for PR and Quotation submission',
    'description': 'Allows end-users and vendors to submit purchase requests and quotations.',
    'author': 'Your Name',
    'depends': ['base', 'stock', 'purchase', 'purchase_stock', 'account'],  # ensure purchase↔stock linkage
    'data': [
        'security/groups.xml',
        'security/record_rules.xml',
        'security/ir.ui.menu.xml',
        'security/ir.model.access.csv',

        # 'views/templates.xml',
        'views/views.xml',
        'views/inventory.xml',
        'views/remarks_popup.xml',
        'views/grn_report.xml',
        'views/remove_purchase_reports.xml',
        # 'views/quotations.xml',

        'data/ir_sequence_data.xml',

    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
