import threading
import string
import openerp
from collections import defaultdict
from VSS.utils import translator, grouped
from openerp import SUPERUSER_ID
from openerp.exceptions import ERPError
from openerp.osv.orm import except_orm as ValidateError
from osv import fields, osv
from psycopg2 import ProgrammingError
from xaml import Xaml
from fnx_fs.fields import files

POS_NEG_NA = (
    ('negative', 'Negative'),
    ('positive', 'Positive'),
    )

class quality_assurance(osv.Model):
    _name = 'fnx.quality_assurance'
    _description = 'qa test'
    _inherit = ['fnx_fs.fs']
    _inherits = {}
    _mirrors = {}
    _order = 'lot_no'

    _fnxfs_path = 'fnx_qa'
    _fnxfs_path_fields = ['name']

    def __init__(self, pool, cr):
        'read extra_test table and add found records to this table'
        cr.execute('SELECT name from ir_model where model=%s', ('fnx.quality_assurance',))
        if cr.fetchone() is not None:
            self._add_extra_test(cr, mode='init')
        return super(quality_assurance, self).__init__(pool, cr)

    def _add_extra_test(self, cr, extra_fields=None, mode=None):
        # get our own cursor in case something fails
        db_name = threading.current_thread().dbname
        db = openerp.sql_db.db_connect(db_name)
        if not extra_fields:
            # this only runs during startup
            qa_cr = db.cursor()
            try:
                qa_cr.execute('SELECT name,field_name,field_type,dilution_10,dilution_100,dilution_1000,notes FROM fnx_quality_assurance_extra_test')
            except ProgrammingError:
                raise
            else:
                db_fields = qa_cr.dictfetchall()
                extra_fields = []
                for fields_dict in db_fields:
                    if fields_dict['field_type'] != 'dilution':
                        extra_fields.append(fields_dict)
                    else:
                        extra_fields.append(fields_dict.copy())
                        extra_fields[-1]['field_name'] += '_10'
                        extra_fields.append(fields_dict.copy())
                        extra_fields[-1]['field_name'] += '_100'
                        extra_fields.append(fields_dict.copy())
                        extra_fields[-1]['field_name'] += '_1000'
            finally:
                qa_cr.close()
        for extra_field in extra_fields:
            name = extra_field['name']
            field_name = extra_field['field_name']
            if mode == 'rename':
                old_field_name = extra_field['old_field_name']
            else:
                type = extra_field['field_type']
                note = extra_field['notes']
                args = ()
                kwds = {}
                if type == 'pass_fail':
                    field = fields.selection
                    args = (POS_NEG_NA, )
                    kwds = dict(string=name)
                    pg_type = 'VARCHAR'
                else:
                    field = fields.char
                    kwds = dict(size=12, string=name)
                    pg_type = 'VARCHAR(12)'
            # check that field doens't already exist
            if field_name in self._columns:
                if mode == 'init':
                    continue
                raise ERPError('Duplicate Field', 'Field "%s" (%s) already exists' % (name, field_name))
            if mode == 'rename':
                self._columns[field_name] = self._columns[old_field_name]
                self._all_columns[field_name] = self._all_columns[old_field_name]
                self._columns[field_name].string = name
                assert self._all_columns[field_name].column.string is name, '_column and _all_column.column are out of sync'
                # self._all_columns[field_name].string = name
                del self._columns[old_field_name]
                del self._all_columns[old_field_name]
                cr.execute(
                        """ALTER TABLE fnx_quality_assurance """
                        """RENAME %s TO %s""" % (old_field_name, field_name),
                        )
                cr.execute(
                        """UPDATE ir_model_fields """
                        """SET name=%s """
                        """WHERE model='fnx.quality_assurance' AND name=%s"""
                        ,
                        (field_name, old_field_name),
                        )
                old_field_name = 'field_' + self._table + '_' + old_field_name
                field_name = 'field_' + self._table + '_' + field_name
                cr.execute(
                        """UPDATE ir_model_data """
                        """SET name=%s """
                        """WHERE model='ir.model.fields' AND name=%s"""
                        ,
                        (field_name, old_field_name),
                        )
            else:
                col = field(*args, help=note, **kwds)
                self._columns[field_name] = col
                self._all_columns[field_name] = fields.column_info(field_name, col)
                if mode == 'init':
                    # columns updated, postgre tables already correct
                    continue
                cr.execute('ALTER TABLE "%s" ADD COLUMN "%s" %s' % (self._table, field_name, pg_type))

                cr.execute('select nextval(%s)', ('ir_model_fields_id_seq',))
                id = cr.fetchone()[0]
                cr.execute("SELECT id FROM ir_model WHERE model=%s", (self._name,))
                model_id = cr.fetchone()[0]
                cr.execute("""INSERT INTO ir_model_fields (
                    id, model_id, model, name, field_description, ttype,
                    relation, view_load, state, select_level, relation_field, translate, serialization_field_id
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                )""", (
                    id, model_id, self._name, field_name, name, col._type, '', False, 'base', 0, '', False, None,
                ))
                name1 = 'field_' + self._table + '_' + field_name
                # cr.execute("select name from ir_model_data where name=%s", (name1,))
                # if cr.fetchone():
                #     name1 = name1 + "_" + str(id)
                cr.execute("INSERT INTO ir_model_data (name,date_init,date_update,module,model,res_id) VALUES (%s, (now() at time zone 'UTC'), (now() at time zone 'UTC'), %s, %s, %s)", \
                    (name1, 'fnx_qa', 'ir.model.fields', id))

    def _get_name(self, cr, uid, ids, field_name, args, context=None):
        values = {}
        for record in self.browse(cr, uid, ids, context=context):
            values[record.id] = '%s - %s' % (record.lot_no, record.product_id.xml_id)
        return values

    def _remove_extra_test(self, cr, extra_fields):
        for extra_field in extra_fields:
            field_name = extra_field['field_name']
            del self._all_columns[field_name]
            del self._columns[field_name]
            cr.execute('SELECT id FROM ir_model WHERE model=%s', (self._name,))
            model_id = cr.fetchone()[0]
            cr.execute(
                    'SELECT id FROM ir_model_fields WHERE model_id=%s AND model=%s AND name=%s',
                    (model_id, self._name, field_name),
                    )
            res_id = cr.fetchone()[0]
            cr.execute('DELETE FROM ir_model_fields WHERE id=%s', (res_id, ))
            name1 = 'field_' + self._table + '_' + field_name
            cr.execute(
                    '''DELETE FROM ir_model_data WHERE module='fnx_qa' and model='ir.model.fields' AND name=%s AND res_id=%s''',
                    (name1, res_id),
                    )
            cr.execute('ALTER TABLE %s DROP COLUMN %s' % (self._table, field_name))

    _columns = {
        'name': fields.function(_get_name, arg=(), string='name', type='char', method=True, selectable=1,
            store={'fnx.quality_assurance': (lambda s, c, u, ids, ctx: ids, ['product_id', 'lot_no'], 20), }),
        'product_id': fields.many2one('product.product', string='Product', required=True),
        'lot_no': fields.char(string='Lot #', size=24, required=True),
        'test_date': fields.date('Test date/time', required=True),
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
        'docs': files('documents', string='Supporting documents'),
        }

    _defaults = {
        'test_date': fields.date.today,
        }

    def name_get(self, cr, uid, ids, context=None):
        if isinstance(ids, (int, long)):
            ids = [ids]
        res = []
        for record in self.browse(cr, uid, ids, context=context):
            res.append((record.id, ' / '.join(['['+record.product_id.xml_id+']', record.lot_no, record.test_date])))
        return res

    def onchange_dilution(self, cr, uid, ids, field_name, value, context=None):
        res = {}
        if value:
            value = value.strip()
            if not value.isdigit() and value.upper() not in ('<10', 'TNTC', 'HTR'):
                res['warning'] = {
                        'title': 'invalid dilution value',
                        'message': 'dilution value should be a number, or one of "<10", "TNTC", or "HTR"',
                        }
                res['value'] = {
                        field_name: '',
                        }
            else:
                res['value'] = {
                        field_name: value.upper()
                        }
        return res

class extra_test(osv.Model):
    _name = 'fnx.quality_assurance.extra_test'
    _description = 'additional test type'
    _order = 'name'

    _columns = {
        'name': fields.char('Test', size=32, required=True),
        'field_name': fields.char('Field name', size=37),
        'field_type': fields.selection(
            (('pass_fail', 'Pass/Fail'), ('count', 'Count'), ('dilution','Dilution')),
            string='Test type',
            required=True
            ),
        'dilution_10': fields.boolean('1/10'),
        'dilution_100': fields.boolean('1/100'),
        'dilution_1000': fields.boolean('1/1000'),
        'notes': fields.text(string='Notes about test'),
        'visible': fields.boolean('Visible'),
        }

    def _post_init(self, pool, cr):
        'read extra_test table and add found records to this table'
        res = super(extra_test, self)._post_init(pool, cr)
        cr.execute('UPDATE fnx_quality_assurance_extra_test SET visible=true WHERE visible is null;')
        cr.execute("SELECT name from ir_model where model='fnx.quality_assurance.extra_test'")
        if cr.fetchone() is not None:
            self._generate_form(cr)
        return res

    def _generate_form(self, cr, context=None):
        view = self.pool.get('ir.ui.view')
        dynamic_form = view.browse(cr, SUPERUSER_ID, [('name','=','fnx.quality_assurance.form.dynamic')], context=context)[0]
        extra_tests = self.read(
                cr, SUPERUSER_ID,
                fields=[
                    'name', 'field_name', 'field_type',
                    'dilution_10', 'dilution_100', 'dilution_1000',
                    'notes', 'visible',
                    ],
                context=context)
        extra_tests.append({
            'name': 'Salmonella',
            'field_name': 'salmonella',
            'field_type': 'pass_fail',
            'dilution_10': False,
            'dilution_100': False,
            'dilution_1000': False,
            'notes': False,
            'visible': True,
            })
        # sort the tests between count, dilution, and pass-fail
        other_tests = []
        dilution_tests = []
        for test in sorted(extra_tests, key=lambda t: t['name']):
            if test['field_type'] == 'dilution':
                dilution_tests.append(test)
            else:
                other_tests.append(test)
        # combine records of same name but different dilution levels
        dilution_level = defaultdict(lambda: {'tenth':(False, None), 'hundreth':(False, None), 'thousandth':(False, None)})
        for test in dilution_tests:
            for possible_dilution, dilution_field, postfix in (
                    ('tenth', 'dilution_10', '_10'), ('hundreth', 'dilution_100', '_100'), ('thousandth', 'dilution_1000', '_1000')
                    ):
                dilution_level[test['name']][possible_dilution] = (test[dilution_field], test['field_name']+postfix)
        doc = Xaml(dynamic_tests, grouped=grouped).document.pages[0]
        arch = doc.string(other_tests=other_tests, dilution_level=dilution_level)
        view.write(cr, SUPERUSER_ID, [dynamic_form.id], {'arch':arch}, context=context)

    def create(self, cr, uid, values, context=None):
        # calculate 'field_name' and create
        name = fix_field_name(values['name'])
        field_type = values['field_type']
        tenth = values.get('dilution_10')
        hundreth = values.get('dilution_100')
        thousandth = values.get('dilution_1000')
        if field_type == 'dilution':
            if not (tenth or hundreth or thousandth):
                raise ERPError('missing dilution level', '1/10, 1/100, and/or 1/1000 must be selected for the dilution levels')
            else:
                new_fields = []
                new_fields.append((name + '_10', field_type, tenth))
                new_fields.append((name + '_100', field_type, hundreth))
                new_fields.append((name + '_1000', field_type, thousandth))
        elif tenth or hundreth or thousandth:
            raise ERPError('invalid dilution level', '1/10, 1/100, and/or 1/1000 cannot be selected for fields of type %r' % (field_type,))
        elif field_type in ('pass_fail', 'count'):
            new_fields = [(name, field_type, True)]
        else:
            raise ERPError('logic failure', 'unknown test type: %r' % (field_type,))
        values['field_name'] = name
        values['visible'] = True
        new_id = super(extra_test, self).create(cr, uid, values, context=context)
        # add new type to quality_assurance
        extra_fields = []
        for field_name, field_type, visible in new_fields:
            extra_fields.append({
                    'name': values['name'],
                    'field_name': field_name,
                    'field_type': field_type,
                    'notes': values.get('notes', ''),
                    'visible': visible,
                    })
        qa = self.pool.get('fnx.quality_assurance')
        qa._add_extra_test(cr, extra_fields)
        # update the fnx.quality_assurance.device.form.dynamic view to include the new field
        self._generate_form(cr, context=context)
        return new_id

    def write(self, cr, uid, ids, values, context=None):
        if isinstance(ids, (int, long)):
            ids = [ids]
        qa = self.pool.get('fnx.quality_assurance')
        if values:
            for forbidden in ('field_type', ):
                if forbidden in values:
                    raise ERPError('Error', 'Test type cannot be changed.')
        extra_fields = []
        if 'name' in values:
            if len(ids) > 1:
                raise ERPError('Error', 'Cannot change multiple records to the same name')
            name = fix_field_name(values['name'])
            values['field_name'] = name
            # get previous values
            previous_records = self.read(cr, uid, ids, context=context)
            for record in previous_records:
                old_name = record['field_name']
                if record['field_type'] == 'dilution':
                    extra_fields.extend([
                        {
                            'name': values['name'],
                            'old_field_name': old_name+'_10',
                            'field_name': name+'_10',
                            },
                        {
                            'name': values['name'],
                            'old_field_name': old_name+'_100',
                            'field_name': name+'_100',
                            },
                        {
                            'name': values['name'],
                            'old_field_name': old_name+'_1000',
                            'field_name': name+'_1000',
                            },
                        ])
                else:
                    extra_fields.append({
                        'name': values['name'],
                        'old_field_name': old_name,
                        'field_name': name,
                        })
            # update auxillary models and postgres tables
            qa._add_extra_test(cr, extra_fields, mode='rename')
        # update current model
        result = super(extra_test, self).write(cr, uid, ids, values, context=context)
        try:
            self._generate_form(cr, context=context)
        except ValidateError:
            if extra_fields:
                for f in extra_fields:
                    f['field_name'], f['old_field_name'] = f['old_field_name'], f['field_name']
                qa._add_extra_test(cr, extra_fields, mode='rename')
            raise
        return result

    def unlink(self, cr, uid, ids, context=None):
        qa = self.pool.get('fnx.quality_assurance')
        if isinstance(ids, (int, long)):
            ids = [ids]
        for record in self.browse(cr, uid, ids, context=context):
            names_to_remove = []
            if record.field_type in ('pass_fail', 'count'):
                names_to_remove.append(record.field_name)
            elif record.field_type == 'dilution':
                for postfix in ('_10', '_100', '_1000'):
                    names_to_remove.append(record.field_name + postfix)
            else:
                raise ERPError('Logic Error', 'unknown field type: %r' % (record.field_type,))
            for field_name in names_to_remove:
                if qa.search(cr, uid, [(field_name, '!=', False)], count=True, context=context):
                    raise ERPError('Field has data', 'Unable to remove field %r as some tests have data for that field' % (record.name,))
            extra_fields = []
            for field_name in names_to_remove:
                extra_fields.append({
                        'name': record.name,
                        'field_name': field_name,
                        'field_type': record.field_type,
                        'notes': record.notes,
                        })
            qa._remove_extra_test(cr, extra_fields)
        result = super(extra_test, self).unlink(cr, uid, ids, context=context)
        self._generate_form(cr, context=context)
        return result

dynamic_tests = '''\
!!! xml1.0
~data
    -if args.dilution_level:
        ~xpath expr="//div[@name='dilution_tests']/table" position='after'
            -for next_four in grouped(sorted(args.dilution_level.items()), 4):
                ~hr
                ~table attrs="{'invisible': [('lot_no','=',False)]}"
                    ~tr
                        ~th : Dilution
                        -for i, (name, tests) in enumerate(next_four):
                            ~th : =name
                        -for j in range(i+1, 4):
                            ~th
                    -for level,label in (('tenth', '1/10'), ('hundreth', '1/100'), ('thousandth', '1/1000')):
                        ~tr
                            ~th : =label
                            -for test_name, tests in next_four:
                                ~td
                                    -active, field_name = tests[level]
                                    -onchange = "onchange_dilution('%s', %s)" % (field_name, field_name)
                                    -# active lot_no+id  id/data   invisible
                                    -#   T         T       F          F   \
                                    -#   F         T       F          T    \
                                    -#   T         F       F          T    /
                                    -#   F         F       F          T   /
                                    -#             +       /
                                    -#   T         T       T          F
                                    -#   F         T       T          F
                                    -#   T         T       F          F
                                    -#   F         T       F          T
                                    -if active:
                                    -   field_op = '='
                                    -   sep_op = '!='
                                    -else:
                                    -   field_op = '!='
                                    -   sep_op = '='
                                    -field_attrs = xmlify("{'invisible': [('lot_no','%s',False),('%s','=',False)]}" % (field_op, field_name))
                                    ~field name=field_name on_change=onchange attrs=field_attrs placeholder='n/a'
                                    -sep_attrs = xmlify("{'invisible': ['|',('lot_no','%s',False),('%s','!=',False)]}" % (sep_op, field_name))
                                    ~separator attrs=sep_attrs
    -if args.other_tests:
        ~div @extra_tests position='inside'
            -mid = (len([t for t in args.other_tests if t['visible']]) + 1) // 2
            -count = index = 0
            ~group attrs="{'invisible': [('lot_no','=',False)]}"
                ~group
                    -for test in args.other_tests:
                        -index += 1
                        -field_name = test['field_name']
                        -active = test['visible']
                        -if active:
                        -   op = '='
                        -   count += 1
                        -else:
                        -   op = '!='
                        -string = xmlify(test['name'])
                        -attrs = xmlify("{'invisible': [('lot_no','%s',False),('%s','=',False)]}" % (op, field_name))
                        ~field name=field_name string=string attrs=attrs placeholder="n/a" .fnx_qa_one_four
                        -if count == mid:
                        -   break
                ~group
                    -for test in args.other_tests[index:]:
                        -field_name = test['field_name']
                        -active = test['visible']
                        -if active:
                        -   op = '='
                        -else:
                        -   op = '!='
                        -string = xmlify(test['name'])
                        -attrs = xmlify("{'invisible': [('lot_no','%s',False),('%s','=',False)]}" % (op, field_name))
                        ~field name=field_name string=string attrs=attrs placeholder="n/a" .fnx_qa_one_four
'''

_fix_field_name = translator(to='_', keep=string.lowercase+'-0123456789', compress=True)
def fix_field_name(name):
    name = name.replace('<=', '_le_').replace('>=', '_ge_').replace('<', '_lt_').replace('&', '_and_').replace('>', '_gt').replace('=', '_eq_').replace('!=', '_ne_')
    return _fix_field_name(name.lower())
