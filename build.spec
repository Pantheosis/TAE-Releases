# build.spec
#
# Build with:  pyinstaller build.spec
#
# Run this SEPARATELY on Windows (produces TraditionalAstrologyEngine.exe in dist/) and
# on macOS (produces TraditionalAstrologyEngine.app in dist/) -- PyInstaller bundles the
# native interpreter and platform libraries, so it cannot cross-compile.
#
# Before running: pip install pyinstaller pyinstaller-hooks-contrib
# (pyinstaller-hooks-contrib includes maintained hooks for Streamlit and
# several of its dependencies; without it you will likely need to add more
# --hidden-import / --collect-all entries by trial and error.)

import sys
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

block_cipher = None

datas = []
binaries = []
hiddenimports = []

# These packages ship data files, C extensions, or dynamic imports that
# static analysis alone won't find -- pull in everything for each.
# NOTE: "webview" (pywebview's actual import name -- not the "pywebview"
# distribution name) was MISSING from this list entirely in earlier
# versions of this spec. pywebview's platform backends (edgechromium.py,
# winforms.py, mshtml.py, cocoa.py, etc.) are imported dynamically inside
# functions in guilib.py, which PyInstaller's static analysis can't see --
# so without explicitly collecting them, some backends silently never
# make it into the bundle at all. That's what caused pywebview to keep
# falling through to the broken legacy WinForms/IE renderer even after
# explicitly forcing gui="edgechromium" in desktop_launcher.py: the
# edgechromium backend module itself wasn't present to import.
collect_pkgs = ["streamlit", "altair", "pyswisseph", "timezonefinder", "geopy", "certifi", "pytz", "webview"]
if sys.platform == "win32":
    # pywebview's modern EdgeChromium/WebView2 backend on Windows needs
    # pythonnet (the .NET/clr bridge). Without it bundled, pywebview
    # silently falls back to the legacy WinForms+IE renderer, which then
    # crashes on its own IE-compatibility-mode registry lookup.
    collect_pkgs += ["pythonnet", "clr_loader"]

for pkg in collect_pkgs:
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# Belt-and-suspenders on top of collect_all("webview") above: explicitly
# force in every submodule of webview by name, matching the exact fix
# used by other pywebview+PyInstaller projects that hit this same issue.
hiddenimports += collect_submodules("webview")
if sys.platform == "win32":
    hiddenimports += collect_submodules("clr_loader")

# Belt-and-suspenders: certifi's CA bundle is required for geopy's HTTPS
# calls to Nominatim to verify certificates correctly inside a frozen build.
datas += collect_data_files("certifi")

# app.py is loaded at runtime via _resource_path("app.py") in the launcher,
# not imported as a module -- bundle it as a plain data file alongside the
# executable rather than analyzing it as code.
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
    upx=False,      # UPX compression trips some antivirus heuristics; leave off
    console=False,  # set True temporarily if you need to see startup errors
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

# On macOS, wrap the onedir output into a proper double-clickable .app bundle.
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="TraditionalAstrologyEngine.app",
        icon=None,  # point this at an .icns file if you have one
        bundle_identifier="com.yourname.traditionalastrologyengine",
    )
