{
    'name': "Base",

    'author': "Guess Who",
    'website': '',

    'category': 'Technical Settings',
    'version': '0.5.5',

    'depends': [
        'web',
        'base_setup',
        'mail'
    ],

    'data': [
        'data/base_data.xml',
        'data/res_company_data.xml',
        'views/res_company_views.xml',
        'views/ir_module_module_view.xml',
        'views/res_config_settings.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'or_base/static/src/webclient/**/*',
            'or_base/static/src/js/settings_page.js',
            'or_base/static/src/xml/settings_page.xml',
            'or_base/static/src/search_panel/search_panel.xml',
            'or_base/static/src/search_panel/search_panel.js',
            'or_base/static/src/search_panel/search_panel.scss',
        ],
        'web.tests_assets': [
            'or_base/static/tests/to_base_mock_server.js',
        ],
    },
    'demo': [
        'data/res_partner_category_demo_data.xml',
        'data/res_partner_demo_data.xml',
    ],
    'pre_init_hook': 'pre_init_hook',
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'post_load': 'post_load',
    'installable': True,
    'auto_install': ['web'],

}
