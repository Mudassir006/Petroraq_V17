# -*- coding: utf-8 -*-
{
    'name': "Sales Workspace - Self Service",
    'summary': """
        Self-Service Sales
    """,
    'description': """
         
    """,
    'author': 'Mudassir',
    'website': 'https://www.petroraq.com',
    'version': '0.1',
    'category': 'Human Resources',

    # any module necessary for this one to work correctly
    'depends': ['de_hr_workspace', 'pr_hr_account', 'eg_asset_management','pr_custom_purchase'],

    # always loaded
    'data': [
        'views/menus.xml',
        'views/sale_order.xml',
        'views/work_order.xml',
        'views/budget.xml',
    ],
    # only loaded in demonstration mode
    # 'demo': [
    #     'demo/demo.xml',
    # ],
    'license': 'LGPL-3',
    'images': ['static/description/banner.jpg'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
