# autopkg_runner.spec
# PyInstaller spec for the AutoPkg Runner .app bundle.
#
# Build with:
#   pyinstaller autopkg_runner.spec --clean
#
# Output: dist/AutoPkg Runner.app
# Binary: dist/AutoPkg Runner.app/Contents/MacOS/autopkg-runner

from PyInstaller.utils.hooks import collect_data_files, collect_submodules
import importlib.util, pathlib

# Read version from __info__.py without importing the whole package
_info_path = pathlib.Path(SPECPATH) / '__info__.py'
_spec = importlib.util.spec_from_file_location('__info__', _info_path)
_info = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_info)
APP_VERSION = _info.APP_VERSION_STR

block_cipher = None

# ---------------------------------------------------------------------------
# Data files — non-Python assets that must be present inside the bundle
# ---------------------------------------------------------------------------
datas = []

# Third-party packages that ship their own templates / static / locale data
datas += collect_data_files('django')
datas += collect_data_files('rest_framework')
datas += collect_data_files('django_apscheduler')
datas += collect_data_files('whitenoise')
datas += collect_data_files('certifi')  # CA bundle for TLS in frozen bundle

# Project assets
# Strip any SQLite files collected by third-party hooks — the database lives
# in Application Support at runtime, never inside the bundle.
datas = [(s, d) for s, d in datas
         if not s.endswith(('.sqlite3', '.sqlite3-journal', '.db'))]

datas += [
    ('webapp/templates',    'webapp/templates'),
    ('webapp/static',       'webapp/static'),
    ('webapp/translations', 'webapp/translations'),
    ('webapp/migrations',   'webapp/migrations'),
    ('webapp/management',   'webapp/management'),
    ('api',                 'api'),
    ('resources',           'resources'),
    ('stages',              'stages'),
    ('notifiers',           'notifiers'),
    ('libs',                'libs'),
    ('autopkgrunner',       'autopkgrunner'),
]

# ---------------------------------------------------------------------------
# Hidden imports — modules that PyInstaller's static analysis misses
# ---------------------------------------------------------------------------
hidden_imports = (
    collect_submodules('django')
    + collect_submodules('rest_framework')
    + collect_submodules('django_apscheduler')
    + collect_submodules('whitenoise')
    + collect_submodules('logbook')
    + collect_submodules('cryptography')
    + collect_submodules('zeroconf')
    + collect_submodules('gunicorn')
    + collect_submodules('argon2')
    + collect_submodules('dns')
    + collect_submodules('webapp')
    + collect_submodules('api')
    + collect_submodules('stages')
    + collect_submodules('notifiers')
    + collect_submodules('libs')
    + [
        # Project modules that are loaded dynamically
        'autopkgrunner.settings',
        'autopkgrunner.wsgi',
        'autopkgrunner.urls',
        'libs.bundled_config',

        # Django internals missed by analysis
        'django.template.defaulttags',
        'django.template.defaultfilters',
        'django.template.loader_tags',
        'django.contrib.admin.apps',
        'django.contrib.auth.backends',

        # Third-party
        'psutil',
        'pywebpush',
        'pip_system_certs',
        'plistlib',
        'apscheduler',
        'apscheduler.schedulers.background',
        'apscheduler.jobstores.sqlalchemy',
        'apscheduler.executors.pool',
    ]
)

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
a = Analysis(
    ['run.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'test', 'unittest'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='autopkg-runner',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='autopkg-runner',
)

app = BUNDLE(
    coll,
    name='AutoPkg Runner.app',
    icon='resources/macos_iconset/AppIcon.icns',
    bundle_identifier='com.bytefloater.autopkg-runner',
    info_plist={
        'CFBundleName': 'AutoPkg Runner',
        'CFBundleDisplayName': 'AutoPkg Runner',
        'CFBundleIdentifier': 'com.bytefloater.autopkg-runner',
        'CFBundleVersion': APP_VERSION,
        'CFBundleShortVersionString': APP_VERSION,
        # LSUIElement=False: show in Dock/app-switcher when the GUI dialog appears.
        # Set to True if you want a fully background (menu-bar-less) app.
        'LSUIElement': False,
        'NSHighResolutionCapable': True,
        'CFBundleExecutable': 'autopkg-runner',
        # Asset catalog icon name — macOS uses this to pick the correct appearance
        # variant (Default, Dark, Tinted, Clear) from the compiled Assets.car.
        # build.sh injects Assets.car and sets this key post-build; declaring it
        # here ensures Info.plist is valid even if that step is skipped.
        'CFBundleIconName': 'AppIcon',
        # Privacy usage strings — required for apps accessing restricted paths
        'NSSystemAdministrationUsageDescription': (
            'AutoPkg Runner requires Full Disk Access to read AutoPkg receipts '
            'and managed software caches.'
        ),
    },
)
