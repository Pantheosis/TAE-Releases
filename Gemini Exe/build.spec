import sys
import os
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

block_cipher = None

datas = []
binaries = []
hiddenimports = []

# Included PySide6 to bundle the Qt WebEngine libraries
collect_pkgs = ["streamlit", "altair", "pyswisseph", "timezonefinder", "geopy", "certifi", "pytz", "webview", "PySide6"]

for pkg in collect_pkgs:
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

hiddenimports += collect_submodules("webview")
datas += collect_data_files("certifi")
datas += [("app.py", ".")]

a = Analysis(
    ["desktop_launcher.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TraditionalAstrologyEngine",
    debug=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="TraditionalAstrologyEngine",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="TraditionalAstrologyEngine.app",
        icon=None,
        bundle_identifier="com.yourname.traditionalastrologyengine",
    )
