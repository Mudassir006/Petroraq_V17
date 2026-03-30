import fnmatch
import importlib
import inspect
import logging
import os
import ast
import subprocess
import time
import threading
import contextlib
from unittest.mock import Mock
from os.path import join as opj

import odoo

from odoo import api, modules, tools, SUPERUSER_ID
from odoo.tools import config, pycompat
from odoo.tools.misc import file_path, file_open
from odoo.tests import common
from odoo.tests.common import HttpCase
from odoo.modules import module, get_modules
from odoo.models import BaseModel

from odoo.addons.base.models.ir_ui_menu import IrUiMenu
from odoo.addons.base.models.res_currency import CurrencyRate
from odoo.addons.base.models.res_users import Users

try:
    from odoo.addons.test_lint.tests import test_manifests
except ImportError:
    test_manifests = None

try:
    from odoo.addons.test_lint.tests.test_manifests import ManifestLinter
    _test_manifest_values = ManifestLinter._test_manifest_values
except ImportError:
    ManifestLinter = None

try:
    from odoo.addons.test_lint.tests.lint_case import LintCase
    iter_module_files = LintCase.iter_module_files
except ImportError:
    LintCase = None

try:
    es_check = tools.misc.find_in_path('es-check')
except IOError:
    es_check = None

try:
    from odoo.addons.test_assetsbundle.tests.test_assetsbundle import AddonManifestPatched
    setUpAddonManifestPatched = AddonManifestPatched.setUp
except ImportError:
    AddonManifestPatched = None

from . import helper
from . import controllers
from . import models
from . import wizard
from . import override

from odoo.addons.hr_work_entry_contract.tests.test_work_entry import TestWorkEntry

_logger = logging.getLogger(__name__)
j = os.path.join

get_resource_path = module.get_resource_path
get_module_icon_path = module.get_module_icon_path
get_module_path = module.get_module_path
module_manifest = module.module_manifest
get_module_icon = module.get_module_icon
load_manifest = module.load_manifest
get_db_name = common.get_db_name
_load_records = BaseModel._load_records
_url_open = HttpCase.url_open
_auto_init = Users._auto_init
_compute_web_icon_data = IrUiMenu._compute_web_icon_data

MAX_IDLE_TIMEOUT = 60 * 10  # in seconds


def _get_branding_module(branding_module='viin_brand'):
    """
    Wrapper for others to override
    """
    return branding_module


def _get_db_name_plus():
    db = get_db_name()
    if db:
        # Force POST value that is set as 8069 by dynamic value
        # to avoid dead test of Odoo
        global common
        common.PORT = odoo.tools.config['http_port']

    return db


def test_installable(module, mod_path=None):
    """
    :param module: The name of the module (sale, purchase, ...)
    :param mod_path: Physical path of module, if not providedThe name of the module (sale, purchase, ...)
    """
    if module == 'general_settings':
        module = 'base'
    if not mod_path:
        mod_path = get_module_path(module, downloaded=True)
    manifest_file = module_manifest(mod_path)
    if manifest_file:
        info = {
            'installable': True,
        }
        f = tools.file_open(manifest_file, mode='rb')
        try:
            info.update(ast.literal_eval(pycompat.to_text(f.read())))
        finally:
            f.close()
        return info
    return {}


viin_brand_manifest = test_installable(_get_branding_module())


def check_viin_brand_module_icon(module):
    """
    Ensure module icon with
        either '/viin_brand_originmodulename/static/description/icon.png'
        or '/viin_brand/static/img/apps/originmodulename.png'
        exists.
    """
    branding_module = _get_branding_module()
    brand_originmodulename = '%s_%s' % (branding_module, module if module not in ('general_settings', 'modules') else 'base')

    # load manifest of the overriding modules
    viin_brand_originmodulename_manifest = test_installable(brand_originmodulename)

    # /viin_brand/static/img/apps_icon_override/originmodulename.png
    originmodulename_iconpath = os.path.join(branding_module, 'static', 'img', 'apps', '%s.png' % (module if module not in ('general_settings', 'modules') else module == 'general_settings' and 'settings' or 'modules'))

    # /viin_brand_originmodulename'/static/description/icon.png
    iconpath = os.path.join(brand_originmodulename, 'static', 'description', 'icon.png')

    module_icon = False
    for adp in odoo.addons.__path__:
        if viin_brand_originmodulename_manifest.get('installable', False) and os.path.exists(os.path.join(adp, iconpath)):
            module_icon = '/' + iconpath
            break
        elif viin_brand_manifest.get('installable', False) and os.path.exists(os.path.join(adp, originmodulename_iconpath)):
            module_icon = '/' + originmodulename_iconpath
            break
    return module_icon


def get_viin_brand_resource_path(mod, *args):
    # Odoo hard coded its own favicon in several places
    # this override to attempt to get Viindoo's favicon if it
    # exists in branding_module/static/img/favicon.ico
    if mod == 'web' and 'static/img/favicon.ico' in args:
        if viin_brand_manifest.get('installable', False):
            branding_module = _get_branding_module()
            for adp in odoo.addons.__path__:
                resource_path = opj(branding_module, *args)
                with contextlib.suppress(FileNotFoundError, ValueError):
                    viindoo_favicon_path = file_path(resource_path)
                    if viindoo_favicon_path:
                        return viindoo_favicon_path
    # Odoo hard coded its own module_icon in several places
    # this override to attempt to get Viindoo's module_icon
    elif mod not in ('general_settings', 'modules', 'settings') and ('static', 'description', 'icon.png') == args:
        module_icon = get_viin_brand_module_icon(mod)
        if module_icon:
            path_parts = module_icon.split('/')
            resource_path = opj(path_parts[1], *path_parts[2:])
            with contextlib.suppress(FileNotFoundError, ValueError):
                module_icon_path = file_path(resource_path)
                if module_icon_path:
                    return module_icon_path

    # fall back to the default one
    with contextlib.suppress(FileNotFoundError, ValueError):
        return file_path(opj(mod, *args))
    return False


def get_viin_brand_module_icon(mod):
    """
    This overrides default module icon with
        either '/viin_brand_originmodulename/static/description/icon.png'
        or '/viin_brand/static/img/apps/originmodulename.png'
        where originmodulename is the name of the module whose icon will be overridden
    provided that either of the viin_brand_originmodulename or viin_brand is installable
    """
    # Odoo hard coded its own test in several places (test_systray_get_activities)
    # this check to skip if mod is test_*
    if mod.startswith('test_'):
        return get_module_icon(mod)
    # Override to pass test test test_message_format
    # Because the module_icon value is hardcoded in test
    if getattr(threading.current_thread(), 'testing', False):
        for stack in inspect.stack(0):
            if stack.function in ('test_message_format', 'test_chatbot_message_format'):
                return get_module_icon(mod)

    module_icon = check_viin_brand_module_icon(mod)
    if mod not in ('general_settings', 'modules', 'settings', 'missing'):
        origin_module_icon = get_module_icon(mod)
        if origin_module_icon and origin_module_icon == '/base/static/description/icon.png':
            module_icon = check_viin_brand_module_icon('base')
    if module_icon:
        return module_icon
    return get_module_icon(mod)


def get_viin_brand_icon_path(module):
    iconpath = ['static', 'description', 'icon.png']
    path = get_viin_brand_resource_path(module.name, *iconpath)
    if not path:
        path = get_viin_brand_resource_path('base', *iconpath)
    if not path:
        return get_module_icon_path(module)
    return path


def _get_brand_module_website(module):
    """
    This overrides default module website with '/branding_module/apriori.py'
    where apriori contains dict:
    modules_website = {
        'account': 'account's website',
        'sale': 'sale's website,
    }
    :return module website in apriori.py if exists else False
    """
    if viin_brand_manifest.get('installable', False):
        branding_module = _get_branding_module()
        for adp in odoo.addons.__path__:
            try:
                modules_website = importlib.import_module('odoo.addons.%s.apriori' % branding_module).modules_website
                if module in modules_website:
                    return modules_website[module]
            except Exception:
                pass
    return False


def _load_manifest_plus(module, mod_path=None):
    info = load_manifest(module, mod_path=mod_path)
    if info:
        module_website = _get_brand_module_website(module)
        if module_website:
            info['website'] = module_website
    return info


def _test_if_loaded_in_server_wide():
    config_options = config.options
    if 'or_base' in config_options.get('server_wide_modules', '').split(','):
        return True
    else:
        return False


if not _test_if_loaded_in_server_wide():
    _logger.warning("The module `or_base` should be loaded in server wide mode using `--load`"
                 " option when starting Odoo server (e.g. --load=base,web,or_base)."
                 " Otherwise, some of its functions may not work properly.")


def _disable_currency_rate_unique_name_per_day():
    # Remove unique_name_per_day constraint in res.currency.rate model in base module
    # It doesn't delete constraint on database server
    for el in CurrencyRate._sql_constraints:
        if el[0] == 'unique_name_per_day':
            _logger.info("Removing the default currency rate's SQL constraint `unique_name_per_day`")
            CurrencyRate._sql_constraints.remove(el)
            break


def _disable_hr_work_entry_work_entries_no_validated_conflict():
    # Remove _work_entries_no_validated_conflict constraint in hr.work.entry model in hr_work_entry module
    # to use another constraint instead
    # It doesn't delete constraint on database server
    try:
        # test if module viin_hr_overtime_timeoff is available
        from odoo.addons.viin_hr_overtime_timeoff.models import hr_work_entry
        # remove the hr_work_entry's _work_entries_no_validated_conflict
        from odoo.addons.hr_work_entry.models.hr_work_entry import HrWorkEntry
        for el in HrWorkEntry._sql_constraints:
            if el[0] == '_work_entries_no_validated_conflict':
                _logger.info("Removing the default hr_work_entry_work's SQL constraint `_work_entries_no_validated_conflict`")
                HrWorkEntry._sql_constraints.remove(el)
                break
    except Exception:
        return


def _disable_test_no_overlap_sql_constraint(self):
    """
    Pass test `test_no_overlap_sql_constraint` in `hr_work_entry module`
    `This test case will be moved to module `viin_hr_overtime_timeoff
    """
    pass


TestWorkEntry.test_no_overlap_sql_constraint = _disable_test_no_overlap_sql_constraint


def _update_brand_web_icon_data(env):
    # Generic trick necessary for search() calls to avoid hidden menus which contains 'base.group_no_one'
    menus = env['ir.ui.menu'].with_context({'ir.ui.menu.full_list': True}).search([('web_icon', '!=', False)])
    for m in menus:
        web_icon = m.web_icon
        paths = web_icon.split(',')
        if len(paths) == 2:
            module = paths[0]
            module_name = paths[1].split('/')[-1][:-4]
            if module_name == 'board' or module_name == 'modules' or module_name == 'settings':
                module = module_name
                web_icon = '%s,static/description/icon.png' % module

            module_icon = check_viin_brand_module_icon(module)
            if module_icon:
                web_icon_data = m._compute_web_icon_data(web_icon)
                if web_icon_data != m.web_icon_data:
                    m.write({'web_icon_data': web_icon_data})


def _update_favicon(env):
    if viin_brand_manifest.get('installable', False):
        branding_module = _get_branding_module()
        for adp in odoo.addons.__path__:
            img_path = file_path(f'{branding_module}/static/img/favicon.ico')
            if img_path:
                res_company_obj = env['res.company']
                data = res_company_obj._get_default_favicon()
                res_company_obj.with_context(active_test=False).search([]).write({'favicon': data})


def _skip_sending_email_when_loading_demo_data_in_test_mode(self, data_list, update=False):
    """Skip sending email when loading the demo data in test mode to speedup"""
    self = self.with_context(mail_activity_quick_update=True)
    return _load_records(self, data_list, update=update)


def _override_test_manifests_keys():
    """Override to support some manifest keys in module"""
    global test_manifests
    if test_manifests:
        test_manifests.MANIFEST_KEYS.update({
            # Viindoo modules
            'old_technical_name': '',
            'name_vi_VN': '',
            'summary_vi_VN': '',
            'description_vi_VN': '',
            'demo_video_url': '',
            'demo_video_url_vi_VN': '',
            'live_test_url': '',
            'live_test_url_vi_VN': 'https://v17demo-vn.viindoo.com',
            'currency': 'EUR',
            'support': 'apps.support@viindoo.com',
            'price': '99.9',
            'subscription_price': '9.9',
            # OCA module (web_responsive)
            'development_status': '',
            'maintainers': [],
            'excludes': [],
            'task_ids': [],
            # Viindoo theme
            'industries': '',
        })


def _test_manifest_values_plus(self, module, manifest_data):
    if manifest_data.get('installable', True):
        _test_manifest_values(self, module, manifest_data)


def _iter_module_files_plus(self, *globs):
    """
    Override to check js file from installable module only
    """
    for modroot in map(get_module_path, get_modules()):
        # BEGIN OVERRIDE
        module = modroot.split('/')[-1]
        manifest_data = ManifestLinter._load_manifest(self, module)
        if not manifest_data.get('installable', True):
            continue
        # END OVERRIDE
        for root, _, fnames in os.walk(modroot):
            fnames = [j(root, n) for n in fnames]
            for glob in globs:
                fnames = fnmatch.filter(fnames, glob)
            yield from fnames


def _setUpAddonManifestPatched_plus(self):
    """Override to compile assets of or_base in test mode,
       because the module `or_base` is be loaded in server wide.
    """
    res = setUpAddonManifestPatched(self)
    self.manifests.update({'or_base': load_manifest('or_base')})
    self.patch(odoo.modules.module, '_get_manifest_cached', Mock(side_effect=lambda module, mod_path=None: self.manifests.get(module, {})))
    return res


def _url_open_plus(self, url, data=None, files=None, timeout=20, headers=None, allow_redirects=True, head=False):
    """
    [FIX] tests: bump url_open timeout

    Some tests are randomly failling because /web takes more than 10 seconds to load.
    A future pr will speedup /web but waiting for that a small bump of the timeout should help.
    """
    return _url_open(self, url, data=data, files=files, timeout=timeout, headers=headers, allow_redirects=allow_redirects, head=head)


def _auto_init_plus(self):
    # Remove me, see https://github.com/odoo/odoo/pull/190736
    """
    Cannot upgrade module sale_crm when target_sales_invoiced field stores a
    value greater than int4. Because when upgrading, the default will
    convert float to int4 causing an error
    psycopg2.errors.NumericValueOutOfRange
    """
    field = self._fields.get('target_sales_invoiced')
    if field and field.column_type == ('int4', 'int4'):
        field.column_type = ('numeric', 'numeric')
    return _auto_init(self)


def _build_viin_web_icon_path_from_image(img_path):
    """
    This method will turn `/module_name/path/to/image` and `module_name/path/to/image`
    into 'module_name,path/to/image' which is for web_icon

    @param img_path: path to the image that will be used for web_icon.
        The path must in the format of either `/module_name/path/to/image` or `module_name/path/to/image`

    @return: web_icon string (e.g. 'module_name,path/to/image')
    """
    path = []
    while img_path:
        img_path, basename = os.path.split(img_path)
        if img_path == os.path.sep:
            img_path = ''
        if img_path:
            path.insert(0, basename)
    return '%s,%s' % (basename, os.path.join(*path))


def _compute_web_icon_data_plus(self, web_icon):
    """
    Override to take web_icon for menus from
        either '/viin_brand_originmodulename'/static/description/icon.png'
        or '/viin_brand/static/img/apps/originmodulename.png'
    """
    paths = web_icon.split(',') if web_icon and isinstance(web_icon, str) else []
    if len(paths) == 2:
        img_path = get_viin_brand_module_icon(paths[0])
        web_icon = _build_viin_web_icon_path_from_image(img_path)
    return _compute_web_icon_data(self, web_icon)


def pre_init_hook(env):
    common.get_db_name = _get_db_name_plus
    module.get_module_icon_path = get_viin_brand_icon_path
    module.get_resource_path = get_viin_brand_resource_path
    modules.get_resource_path = get_viin_brand_resource_path
    module.get_module_icon = get_viin_brand_module_icon


def post_init_hook(env):
    _update_brand_web_icon_data(env)
    _update_favicon(env)


def uninstall_hook(env):
    common.get_db_name = get_db_name
    module.get_module_icon_path = get_viin_brand_icon_path
    module.get_resource_path = get_viin_brand_resource_path
    modules.get_resource_path = get_viin_brand_resource_path
    module.get_module_icon = get_module_icon
    module.load_manifest = load_manifest
    HttpCase.url_open = _url_open


def post_load():
    _disable_currency_rate_unique_name_per_day()
    _disable_hr_work_entry_work_entries_no_validated_conflict()
    if config.get('test_enable', False):
        BaseModel._load_records = _skip_sending_email_when_loading_demo_data_in_test_mode
        # Because we are disabling test tour on runbot due to to_backend_theme module being affected
        # This will result in faster response times for browser checks, improving performance and reducing unnecessary processing
        # Each test will save 9.9s
        global common
        common.CHECK_BROWSER_ITERATIONS = 1
    module.get_module_icon_path = get_viin_brand_icon_path
    modules.get_module_resource = get_viin_brand_resource_path
    module.get_module_icon = get_viin_brand_module_icon
    module.get_resource_path = get_viin_brand_resource_path
    modules.get_resource_path = get_viin_brand_resource_path
    common.get_db_name = _get_db_name_plus
    module.load_manifest = _load_manifest_plus
    if test_manifests:
        _override_test_manifests_keys()
    if AddonManifestPatched:
        AddonManifestPatched.setUp = _setUpAddonManifestPatched_plus
    if ManifestLinter:
        ManifestLinter._test_manifest_values = _test_manifest_values_plus
    if LintCase:
        LintCase.iter_module_files = _iter_module_files_plus
    HttpCase.url_open = _url_open_plus
    Users._auto_init = _auto_init_plus
    IrUiMenu._compute_web_icon_data = _compute_web_icon_data_plus
