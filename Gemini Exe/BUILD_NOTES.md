# Packaging TraditionalAstrologyEngine as a portable desktop app

## Files
- `desktop_launcher.py` — spawns Streamlit headlessly, opens it in a pywebview window.
- `build.spec` — PyInstaller build configuration.
- `app.py` — your existing Streamlit script, bundled as a data file (not imported).

## 1. Test in dev mode first
Before packaging anything:
```
pip install pywebview
python desktop_launcher.py
```
This should open a native window showing your app. Fix any issues here —
they'll be much harder to debug once frozen.

## 2. Why onedir instead of onefile
PyInstaller's `--onefile` mode self-extracts to a temp directory on *every
launch*, adding a real startup delay, and its unsigned self-extracting
`.exe`s are flagged by antivirus heuristics far more often than a plain
folder of files. `build.spec` uses `--onedir` (via `COLLECT`) instead:

- **Windows:** you get a folder (`dist/TraditionalAstrologyEngine/`) containing
  `TraditionalAstrologyEngine.exe` plus its dependencies. Zip the folder — that *is* the
  portable, no-install form. Users unzip and double-click the `.exe`.
- **macOS:** the spec's `BUNDLE` step wraps that same folder into a proper
  `TraditionalAstrologyEngine.app`, which behaves as a single double-clickable icon even
  though it's technically a directory. Zip or `.dmg` it for distribution.

If startup-folder-of-files bothers you aesthetically, `--onefile` still
works fine for personal use — just change `EXE(..., exclude_binaries=True)`
to a single onefile `EXE(...)` per PyInstaller's docs and drop `COLLECT`.

## 3. Platform-specific requirements

### Windows
pywebview uses the **Edge WebView2** runtime. It ships pre-installed on
Windows 10 (recent updates) and Windows 11, so most users are covered with
zero extra steps. For older/locked-down machines, either point users to
Microsoft's WebView2 Evergreen Bootstrapper, or bundle the fixed-version
runtime — see pywebview's docs if you need this covered.

Unsigned `.exe`s trigger a Windows SmartScreen warning ("Windows protected
your PC"). Users can click **More info → Run anyway**. A proper fix requires
a code-signing certificate (~$100+/yr) — not necessary for personal/private
distribution.

### macOS
pywebview uses the built-in WebKit — no extra runtime needed, which is a
genuine advantage for portability here.

Unsigned `.app` bundles trigger Gatekeeper's "unidentified developer"
block. First run: **right-click the app → Open → Open** (this only needs
doing once). For wider distribution without this friction you'd need an
Apple Developer ID ($99/yr) and to notarize the build — out of scope unless
you're distributing beyond yourself/trusted users.

## 4. Gotchas specific to this app's dependencies

- **Bundled WebView2 runtime (Windows):** by default, pywebview relies on
  whatever WebView2 Runtime is already on the end user's system, which
  ships pre-installed on stock Windows 10/11 but can be missing on
  debloated/stripped installs, older systems, or locked-down corporate
  images. If you're distributing to people whose machines you don't
  control, download Microsoft's "Fixed Version" WebView2 Runtime from
  https://developer.microsoft.com/en-us/microsoft-edge/webview2/, extract
  it into a `webview2_runtime/` folder in the project root (`expand -F:*
  <file>.cab webview2_runtime` on Windows), and both `build.spec` and
  `desktop_launcher.py` will automatically detect and bundle/use it if
  present, falling back to the system's own WebView2 if the folder is
  absent. This adds roughly 150-250MB to the build. Note: fixed-version
  WebView2 has a documented Microsoft limitation where it won't run if the
  app is launched from a network location — local disk only.
- **pyswisseph / ephemeris precision:** `app.py` never calls
  `swe.set_ephe_path()`, so it already falls back to the built-in Moshier
  ephemeris (no external `.se1` files needed). This is arc-second-level
  precision, which is far finer than anything the app displays (minutes of
  arc) — no need to bundle Swiss Ephemeris data files unless you have a
  specific reason to want JPL-grade precision.
- **timezonefinder:** ships a sizeable internal dataset (tens of MB) that
  `collect_all("timezonefinder")` in `build.spec` should pull in
  automatically. This is the single biggest contributor to final build
  size. If you want a much smaller build and can tolerate coarser timezone
  boundaries, `TimezoneFinderL` is a lighter drop-in alternative — not
  something I'd swap in without you asking, since it trades accuracy for size.
- **geopy / Nominatim:** this requires live internet access at runtime —
  packaging doesn't make the app work offline, it just removes the need to
  install Python/dependencies. Keep that expectation in mind. Also, the
  public Nominatim endpoint has a fair-use policy (identifiable user-agent,
  reasonable request rate) — fine for personal use, worth reading their
  usage policy if you ever distribute this to many people.
- **certifi:** frozen builds sometimes fail geopy's HTTPS calls with SSL
  verification errors if certifi's CA bundle isn't bundled — `build.spec`
  includes it explicitly as a safeguard.

## 5. Building for both platforms without owning both machines
PyInstaller does not cross-compile — a build run on Linux/Mac cannot
produce a Windows `.exe`, and vice versa. If you don't have physical access
to both a Windows and a Mac machine, the standard solution is a CI matrix,
e.g. GitHub Actions with `runs-on: [windows-latest, macos-latest]`, each
job running `pip install -r requirements.txt pyinstaller
pyinstaller-hooks-contrib` then `pyinstaller build.spec`, uploading
`dist/` as a build artifact.

## 6. Debugging a frozen build that fails silently
Set `console=True` in `build.spec` temporarily — this gives you a terminal
window showing Streamlit's actual startup errors/tracebacks, which are
otherwise invisible with `console=False`. Switch back to `False` for the
release build once it's working.
