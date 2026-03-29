{
    'name': 'HR Recruitment Request',
    'version': '17.0.0.1',
    'category': 'Human Resources',
    'author': 'Petroraq',
    'website': 'https://www.petroraq.com',
    'license': 'LGPL-3',
    'summary': 'HR Recruitment Request',
    'depends': ['hr_recruitment','hr','mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/hr_recruitment_request_sequence.xml',
        'views/hr_recruitment_request_views.xml',
    ],
    'application': True,
    'installable': True
}