from osv.osv import except_osv as ERPError
from osv import fields, osv, orm

DILUTION_LEVELS = (
        ('10-1', '10-1'),
        ('10-2', '10-2'),
        ('10-3', '10-3'),
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
        'e_coli': fields.selection(DILUTION_LEVELS, string='E.coli'),
        'aerobic_plate_count': fields.selection(DILUTION_LEVELS, string='Aerobic Plate Count'),
        'yeast_mold': fields.selection(DILUTION_LEVELS, string='Yeast and Mold'),
        'salmonella': fields.selection(DILUTION_LEVELS, string='Salmonella'),
        'listeria': fields.selection(DILUTION_LEVELS, string='Listeria'),
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


