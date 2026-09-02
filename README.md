# Traditional Astrology Engine

A desktop application for calculating natal charts using traditional, medieval, and Hellenistic methods — essential and accidental dignities, whole-sign topical delineation, classical time-lord techniques, and Ptolemaic aspects — built on the Swiss Ephemeris. Runs as a self-contained desktop app on Windows and macOS with no internet connection required: location lookup uses a bundled offline city database rather than a geocoding API, and there's no telemetry or update-check traffic of any kind.

## Features

**Astronomical calculation**
- Sun through Saturn plus the mean lunar node, via the Swiss Ephemeris
- Whole Sign houses and Alchabitius (quadrant) house cusps calculated simultaneously
- Correct Julian/Gregorian calendar handling for dates before the October 1582 reform, so historical charts aren't silently mis-dated
- Diurnal/nocturnal sect, and day/hour lords (chronocrators) derived from true local sunrise/sunset — falling back to the calendar weekday and equal hour division on dates/latitudes with no sunrise or sunset (circumpolar day/night)
- Prenatal syzygy (the New or Full Moon preceding birth), with its degree, sect, and almuten

**Dignity and delineation**
- Essential dignity scoring across domicile, exaltation, triplicity (day/night/participating), Egyptian terms, and Chaldean faces
- Accidental dignity: angularity, planetary joys, hayz, station/retrogradation, and solar phase (cazimi, combustion, under the beams)
- Via Combusta and welled/pitted degrees (sourced from Abu Ma'shar's *Great Introduction to Astrology*, cross-checked against al-Bīrūnī's *Kitāb al-Tafhīm*)
- House-ruler placement matrix (Masha'allah) and planets-in-houses delineation (Rhetorius/PN4)
- Ptolemaic aspects with classical orbs, enforced within whole-sign boundaries, noting application/separation

**Time lords**
- Annual profections (Lord of the Year)
- Ptolemaic distributions through the Egyptian terms (1° per year)

**Location and chart data**
- Offline gazetteer (GeoNames `cities500`, population ≥ 500) for coordinate and timezone lookup — no network access
- Manual latitude/longitude entry for locations not in the database, or for historical/ancient places
- Local Mean Time as a selectable alternative to modern timezone-based standard time, for dates before timezones existed
- Save, load, and delete chart configurations locally between sessions

## Installation

These binaries aren't signed with a paid code-signing certificate, so Windows and macOS will both show an unfamiliar-publisher warning on first launch. That's expected — follow the steps below to run it anyway.

### Windows (10 / 11)

1. Extract the full contents of `TraditionalAstrologyEngine-Windows.zip` to a folder on disk. Don't run the `.exe` straight out of the zip preview, and don't move it out of its extracted folder afterward.
2. Double-click `TraditionalAstrologyEngine.exe`.
3. Windows SmartScreen will show a blue "Windows protected your PC" banner. Click **More info**, then **Run anyway**.

### macOS (Sonoma / Sequoia)

1. Extract `TraditionalAstrologyEngine-macos.zip` and move `TraditionalAstrologyEngine.app` into `/Applications`.
2. Double-click the app. Gatekeeper will block it with an "unidentified developer" warning — dismiss it.
3. Open **System Settings → Privacy & Security**, scroll to **Security**, and click **Open Anyway** next to the blocked-app notice. Confirm with **Open**, entering your admin password if prompted.
4. Alternatively, from a terminal: `xattr -cr /Applications/TraditionalAstrologyEngine.app`

---

Astrological calculations powered by the [Swiss Ephemeris](https://www.astro.com/swisseph/). Offline gazetteer data from [GeoNames](https://www.geonames.org/), licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
