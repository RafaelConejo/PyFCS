# -*- mode: python ; coding: utf-8 -*-

import os

# PyFCS one-file build recipe.
# Run from the project root with:
#     pyinstaller --noconfirm --clean PyFCS.spec

project_root = os.path.abspath(globals().get('SPECPATH', os.getcwd()))

icon_dir = os.path.join(project_root, 'Source', 'external', 'icons')
default_cns = os.path.join(
    project_root,
    'fuzzy_color_spaces',
    'cns',
    'ISCC_NBS_BASIC.cns',
)

# These are bundled read-only resources. At runtime PyInstaller extracts them
# under sys._MEIPASS and UtilsTools.get_resource_path() resolves them there.
datas = [
    (icon_dir, os.path.join('Source', 'external', 'icons')),
    (default_cns, os.path.join('fuzzy_color_spaces', 'cns')),
]

hiddenimports = [
    'Source.input_output.InputCNS',
    'Source.input_output.InputFCS',
]

excludes = [
    'PyQt6',
    'PySide6',
    'PySide2',
]

a = Analysis(
    ['Source/interface/mainInterface.py'],
    pathex=[project_root],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# If a Windows .ico is present, PyInstaller will use it. 
# Otherwise the EXE is generated with the default executable icon; 
# PyFCS still uses logo.png inside the running Tk window.
exe_icon = os.path.join(icon_dir, 'logo.ico')
if not os.path.isfile(exe_icon):
    exe_icon = None

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PyFCS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=exe_icon,
)
