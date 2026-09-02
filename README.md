# Traditional Astrology Engine (v1.0.0)

An offline, standalone computational workstation engineered for traditional, medieval, and Hellenistic astrological analysis. Built on high-precision Swiss Ephemeris calculations, the engine eliminates external network telemetry and web-engine dependencies to provide immediate, deterministic chart delineation in an air-gapped desktop environment.

## Core Utility & Objectives

* **Zero-Telemetry Operation:** Native Qt desktop wrapper decoupling the application entirely from remote APIs, OS-level webview runtimes, and background data harvesting.
* **Historical Chronological Fidelity:** Native mathematical correction for historical Local Mean Time (LMT) based on geographic longitude, preventing standard regional timezone rounding errors across pre-modern eras.
* **Dual Calculation Layer:** Full simultaneous resolution of Whole Sign Houses alongside Alchabitius Semi-Arc quadrant cusps.

## Functional Capabilities

### 1. Astronomical Calculation & Astrometry
* **Ephemeris Precision:** Sub-arcsecond calculation of planetary longitudes, diurnal speeds, and lunar nodes.
* **Solar & Temporal Hour Diagnostics:** Determination of diurnal/nocturnal chart sect and calculation of unequal planetary days and hours derived from true local sunrise and sunset boundaries.
* **Prenatal Lunation (Syzygy):** Root-searched determination of the preceding conjunctional (New Moon) or preventional (Full Moon) syzygy, calculating its exact zodiacal degree, sect, and almuten.

### 2. Classical Dignity & Topical Delineation
* **5-Fold Essential Dignity Hierarchy:** Automated scoring across Domicile, Exaltation, Dorothean Triplicity (Day/Night/Participating), Egyptian Terms, and Chaldean Faces.
* **Accidental Dignity Framework:** Evaluation of Whole Sign angularity, planetary joys, Hayz conditions, speed/motion anomalies (retrogradation, stationarity), and precise solar phases (cazimi, combustion, under the beams).
* **Classical Topical Matrices:** Integrated delineation tables implementing Masha'allah’s house-ruler placement matrix and Rhetorius/PN4 house-occupant condition synthesis.
* **Ptolemaic Aspect Engine:** Classical orb-based moiety evaluations enforcing strict whole-sign configuration boundaries (prohibiting out-of-sign aspects) while identifying application, separation, and sinister/dexter orientation.

### 3. Chronocrators (Time Lords)
* **Annual Profections:** Dynamic projection of the Ascendant through Whole Sign boundaries to establish the active *Lord of the Year*.
* **Distributions Through Bounds:** Degree-per-year progression of the Ascendant degree through the Egyptian Terms to identify the active *Distributor*.

### 4. Data & Chart Management
* **Embedded Offline Atlas:** Integrated SQLite gazetteer (`cities500`) supporting coordinate and timezone resolution for worldwide locations down to 500 population with zero network access.
* **Manual Coordinate Override:** Explicit numerical latitude and longitude inputs for unmapped historical, ancient, or rural locations.
* **Persistent Storage:** Local JSON chart management to save, load, and delete chart configurations across application sessions.

---

## Installation & Distribution Instructions

Because these binaries are distributed directly for academic use without third-party digital signature certificates, modern operating systems will enforce default execution guards. Follow the platform-specific instructions below to launch the software.

### Windows (10 / 11)
1. **Extract the Archive:** Extract the entire contents of `TraditionalAstrologyEngine-Windows.zip` to a local folder. 
   * *Critical:* Do not execute `TraditionalAstrologyEngine.exe` from inside the `.zip` preview window, and do not move the `.exe` away from its bundled directory.
2. **Launch Application:** Double-click `TraditionalAstrologyEngine.exe`.
3. **Bypass SmartScreen:**
   * A blue banner stating **"Windows protected your PC"** will appear.
   * Click **More info**.
   * Click the **Run anyway** button at the bottom.

### macOS (Sonoma / Sequoia)
1. **Extract Archive:** Double-click `TraditionalAstrologyEngine-macos.zip` to extract `TraditionalAstrologyEngine.app`. Move the `.app` into your `/Applications` directory.
2. **Initial Launch Attempt:** Double-click the app. macOS Gatekeeper will block execution with a warning dialog stating the developer cannot be verified. Click **Done** or **Cancel**.
3. **Whitelist in System Settings:**
   * Open **System Settings** -> **Privacy & Security**.
   * Scroll to the **Security** section near the bottom.
   * Locate the prompt stating the app was blocked from use.
   * Click **Open Anyway**.
   * Click **Open** again to confirm, and enter your macOS administrator password when prompted.
4. **Terminal Alternative (Power Users):**
   * Strip the Apple quarantine attribute directly:
     `xattr -cr /Applications/TraditionalAstrologyEngine.app`
