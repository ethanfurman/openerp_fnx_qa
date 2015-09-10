import threading
import string
import openerp
from collections import defaultdict
from fnx import translator, grouped
from openerp import SUPERUSER_ID
from osv.osv import except_osv as ERPError
from osv import fields, osv, orm
from psycopg2 import ProgrammingError
from xaml import Xaml

POS_NEG_NA = (
    ('negative', 'Negative'),
    ('positive', 'Positive'),
    )

class quality_assurance(osv.Model):
    _name = 'fnx.quality_assurance'
    _description = 'qa test'
    _inherit = []
    _inherits = {}
    _mirrors = {}
    _order = 'lot_no'

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
            except ProgrammingError, e:
                # if 'does not exist' in str(e):
                #     return
                raise
            else:
                db_fields = qa_cr.dictfetchall()
                extra_fields = []
                for fields_dict in db_fields:
                    if fields_dict['field_type'] != 'dilution':
                        extra_fields.append(fields_dict)
                    else:
                        if fields_dict['dilution_10']:
                            extra_fields.append(fields_dict.copy())
                            extra_fields[-1]['field_name'] += '_10'
                        if fields_dict['dilution_100']:
                            extra_fields.append(fields_dict.copy())
                            extra_fields[-1]['field_name'] += '_100'
                        if fields_dict['dilution_1000']:
                            extra_fields.append(fields_dict.copy())
                            extra_fields[-1]['field_name'] += '_1000'
            finally:
                qa_cr.close()
        for extra_field in extra_fields:
            print 'creating field', extra_field
            name = extra_field['name']
            field_name = extra_field['field_name']
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
            col = field(*args, help=note, **kwds)
            self._columns[field_name] = col
            self._all_columns[field_name] = fields.column_info(field_name, col)
            if mode == 'init':
                # columns updated, postgre tables already correct
                continue
            table = self._name.replace('.','_')
            cr.execute('ALTER TABLE "%s" ADD COLUMN "%s" %s' % (table, field_name, pg_type))

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
            cr.execute('ALTER TABLE "%s" DROP COLUMN "%s"' % (self._table, field_name))

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
        }

    def __init__(self, pool, cr):
        'read extra_test table and add found records to this table'
        print 'extra_test.__init__'
        res = super(extra_test, self).__init__(pool, cr)
        cr.execute("SELECT name from ir_model where model='fnx.quality_assurance.extra_test'")
        if cr.fetchone() is not None:
            print '  generating form'
            self._generate_form(cr, SUPERUSER_ID)
        return res

    def _generate_form(self, cr, uid, context=None):
        view = self.pool.get('ir.ui.view')
        dynamic_form = view.browse(cr, uid, [('name','=','fnx.quality_assurance.form.dynamic')], context=context)[0]
        extra_tests = self.read(
                cr, uid,
                fields=['name', 'field_name', 'field_type', 'dilution_10', 'dilution_100', 'dilution_1000', 'notes'],
                context=context)
        # sort the tests between count, dilution, and pass-fail
        count_tests = []
        dilution_tests = []
        pass_fail_tests = []
        for test in sorted(extra_tests, key=lambda t: t['field_name']):
            if test['field_type'] == 'pass_fail':
                pass_fail_tests.append(test)
            elif test['field_type'] == 'count':
                count_tests.append(test)
            else:
                dilution_tests.append(test)
        # combine records of same name but different dilution levels
        dilution_level = defaultdict(lambda: {'tenth':(False, None), 'hundreth':(False, None), 'thousandth':(False, None)})
        for test in dilution_tests:
            for possible_dilution, dilution_field, postfix in (
                    ('tenth', 'dilution_10', '_10'), ('hundreth', 'dilution_100', '_100'), ('thousandth', 'dilution_1000', '_1000')
                    ):
                if test[dilution_field]:
                    dilution_level[test['name']][possible_dilution] = (True, test['field_name']+postfix)
        doc = Xaml(dynamic_tests, grouped=grouped).document
        arch = doc.string(pass_fail_tests=pass_fail_tests, dilution_level=dilution_level, count_tests=count_tests)
        view.write(cr, uid, [dynamic_form.id], {'arch':arch}, context=context)

    def create(self, cr, uid, values, context=None):
        # calculate 'field_name' and create
        name = fix_field_name(values['name'].lower())
        field_type = values['field_type']
        tenth = values.get('dilution_10')
        hundreth = values.get('dilution_100')
        thousandth = values.get('dilution_1000')
        if field_type == 'dilution' and not (tenth or hundreth or thousandth):
            raise ERPError('missing dilution level', '1/10, 1/100, and/or 1/1000 must be selected for the dilution levels')
        if field_type != 'dilution' and (tenth or hundreth or thousandth):
            print "eek!  dilution levels present!! exterminating!!!"
            if tenth:
                del values['dilution_10']
            if hundreth:
                del values['dilution_100']
            if thousandth:
                del values['dilution_1000']
        if field_type in ('pass_fail', 'count'):
            new_fields = [(name, field_type)]
        elif field_type == 'dilution':
            new_fields = []
            if tenth:
                new_fields.append((name + '_10', field_type))
            if hundreth:
                new_fields.append((name + '_100', field_type))
            if thousandth:
                new_fields.append((name + '_1000', field_type))
        else:
            raise ERPError('logic failure', 'unknown test type: "%s"' % field_type)
        values['field_name'] = name
        new_id = super(extra_test, self).create(cr, uid, values, context=context)
        # add new type to quality_assurance
        extra_fields = []
        for field_name, field_type in new_fields:
            extra_fields.append({
                    'name': values['name'],
                    'field_name': field_name,
                    'field_type': field_type,
                    'notes': values.get('notes', ''),
                    })
        qa = self.pool.get('fnx.quality_assurance')
        qa._add_extra_test(cr, extra_fields)
        try:
            # update the fnx.quality_assurance.device.form.dynamic view to include the new field
            self._generate_form(cr, uid, context=context)
        except Exception, e:
            qa._remove_extra_test(cr, extra_fields)
            raise ERPError('Uh Oh!', str(e))
        return new_id

    def write(self, cr, uid, ids, values, context=None):
        if values and len(values.keys()) > 2 or 'notes' not in values:
            raise ERPError('Error', 'Only "notes" can be changed at this point.')
        result = super(extra_test, self).write(cr, uid, ids, values, context=context)
        # uncomment next two lines if we ever allow changes to 'name' or 'field_type'
        # if result:
        #     self._generate_form(cr, uid, context=context)
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
                for dilution_level, postfix in (('dilution_10', '_10'), ('dilution_100', '_100'), ('dilution_1000', '_1000')):
                    if record[dilution_level]:
                        names_to_remove.append(record.field_name + postfix)
            else:
                raise ERPError('Logic Error', 'unknown field type: "%s"' % record.field_type)
            for field_name in names_to_remove:
                if qa.search(cr, uid, [(field_name, '!=', False)], count=True):
                    raise ERPError('Field has data', 'Unable to remove field "%s" as some tests have data for that field' % record.name)
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
        self._generate_form(cr, uid, context=context)
        return result

dynamic_tests = '''\
!!! xml1.0
%data
    -if args.pass_fail_tests:
        %div @extra_tests position='inside'
            %group
                -for test in args.pass_fail_tests:
                    %field name=`test['field_name']` placeholder="Not Applicable" .fnx_qa_one_four
    -if args.count_tests:
        %div @extra_tests position='inside'
            %group
                -for test in args.count_tests:
                    -field_name = test['field_name']
                    %field name=field_name placeholder="Not Applicable" .fnx_qa_one_four
    %hr
    -if args.dilution_level:
        %div @extra_tests position='inside'
            %div .fnx_qa
                -for next_four in grouped(sorted(args.dilution_level.items()), 4):
                    %table
                        %tr
                            %th : dilution
                            -for i, (name, tests) in enumerate(next_four):
                                %th : =name
                            -for j in range(i+1, 4):
                                %th
                        -for level,label in (('tenth', '1/10'), ('hundreth', '1/100'), ('thousandth', '1/1000')):
                            -if any(test[1][level][0] for test in next_four):
                                %tr
                                    %th : =label
                                    -for test_name, tests in next_four:
                                        %td
                                            -active, field_name = tests[level]
                                            -if active:
                                                -onchange = "onchange_dilution('%s', %s)" % (field_name, field_name)
                                                %field name=field_name placeholder='Not Applicable' on_change=onchange
                                            -else:
                                                %separator
                    %hr
'''

_fix_field_name = translator(to='_', keep=string.lowercase+'-', compress=True)
def fix_field_name(name):
    return _fix_field_name(name.lower())
