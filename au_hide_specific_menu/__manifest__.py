{
    'name': 'Hide Specific Menu',
    'version': '17.0.1.0.0',
    'summary': 'Hide specific menu items for selected users',
    'author': 'Mudassir Amin',
    'category': 'Tools',
    'website': 'mailto:mudassir.odoo@gmail.com',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_users_views.xml',
        'views/ir_ui_menu_views.xml',
    ],
    'installable': True,
    'application': False,
    # App store metadata:
    'images': ['static/description/icon.png'],
}
