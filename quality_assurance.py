from osv.osv import except_osv as ERPError
from osv import fields, osv, orm

POS_NEG_NA = (
    ('negative', 'Negative'),
    ('positive', 'Positive'),
    )

class QualityAssurance(osv.Model):
    _name = 'fnx.quality_assurance'
    _description = 'qa test'
    _inherit = []
    _inherits = {}
    _mirrors = {}
    _order = 'lot_no'

    _columns = {
        'product_id': fields.many2one('product.product', string='Product'),
        'lot_no': fields.char(string='Lot #', size=24, required=True),
        'test_date': fields.date('Test date', required=True),
        'result': fields.text('Final Result / Remark'),
        'salmonella': fields.selection(POS_NEG_NA, string='Salmonella'),
        'coliform_10': fields.char(size=12, string='coliform 1/10'),
        'coliform_100': fields.char(size=12, string='coliform 1/100'),
        'e_coli_10': fields.char(size=12, string='E.coli 1/10'),
        'e_coli_100': fields.char(size=12, string='E.coli 1/100'),
        'aerobic_plate_count_10': fields.char(size=12, string='Aerobic Plate Count 1/10'),
        'aerobic_plate_count_100': fields.char(size=12, string='Aerobic Plate Count 1/100'),
        'aerobic_plate_count_1000': fields.char(size=12, string='Aerobic Plate Count 1/1000'),
        'yeast_mold_10': fields.char(size=12, string='Yeast and Mold 1/10'),
        'yeast_mold_100': fields.char(size=12, string='Yeast and Mold 1/100'),
        'yeast_mold_1000': fields.char(size=12, string='Yeast and Mold 1/1000'),
        }

    _defaults = {
        'test_date': fields.date.today,
        }

    def name_get(self, cr, uid, ids, context=None):
        if isinstance(ids, (int, long)):
            ids = [ids]
        res = []
        for record in self.browse(cr, uid, ids, context=context):
            res.append((record.id, ' / '.join([record.product_id.name, record.lot_no, record.test_date])))
        return res


