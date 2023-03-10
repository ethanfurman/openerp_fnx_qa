{
   'name': 'Fnx Quality Assurance System',
    'version': '0.1',
    'category': 'Generic Modules',
    'description': """\
            Phoenix quality assurance system.
            """,
    'author': 'Emile van Sebille',
    'maintainer': 'Emile van Sebille',
    'website': 'www.openerp.com',
    'depends': [
        'base',
        'fnx',
        'fis_integration',
        'product',
        ],
    'js': [
        ],
    'css':[
        'static/src/css/fnx_qa.css',
        ],
    'update_xml': [
        'security/quality_assurance_security.xaml',
        'security/ir.model.access.csv',
        'quality_assurance_view.xaml',
        ],
    'test': [],
    'installable': True,
    'active': False,
}

