import swisseph as swe
import streamlit as st
import pandas as pd
from datetime import datetime, timezone, time, timedelta
from itertools import combinations
from timezonefinder import TimezoneFinder
import pytz
from pathlib import Path
import math
import json
import sqlite3

# ==========================================
# 0. SAVED CHART PERSISTENCE
# ==========================================
# Charts are saved as {name: {date_string, time_string, location_query}} in a
# small JSON file next to the script. Only the raw natal inputs are stored —
# the full chart is cheaply recomputed on load rather than serialized.
SAVED_CHARTS_PATH = Path(__file__).parent / "saved_charts.json"

def load_saved_charts():
    if SAVED_CHARTS_PATH.exists():
        try:
            return json.loads(SAVED_CHARTS_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}

def write_saved_charts(charts):
    try:
        SAVED_CHARTS_PATH.write_text(json.dumps(charts, indent=2))
        return True
    except OSError:
        return False

# ==========================================
# 1. CORE CALCULATION ENGINE
# ==========================================

def calculate_traditional_chart(dt_utc, lat, lon):
    year, month, day = dt_utc.year, dt_utc.month, dt_utc.day
    hour = dt_utc.hour + dt_utc.minute/60.0 + dt_utc.second/3600.0

    # CRITICAL: Python's datetime is always proleptic Gregorian, and
    # swe.julday() defaults to the Gregorian calendar flag. For dates before
    # the Gregorian reform (Oct 15, 1582), professional astrological software
    # (Solar Fire, Astro.com, etc.) interprets the same y/m/d digits as a
    # JULIAN calendar date. Using the wrong flag silently mis-dates historical
    # charts by several days (7 days in the 1200s, growing further back),
    # which cascades into large positional errors — the Moon alone drifts
    # ~13°/day, so a 7-day calendar error looks like a ~90° Moon error.
    is_gregorian_date = (year, month, day) >= (1582, 10, 15)
    cal_flag = swe.GREG_CAL if is_gregorian_date else swe.JUL_CAL
    jd = swe.julday(year, month, day, hour, cal_flag)

    targets = {
        'Sun': swe.SUN, 'Moon': swe.MOON, 'Mercury': swe.MERCURY,
        'Venus': swe.VENUS, 'Mars': swe.MARS, 'Jupiter': swe.JUPITER,
        'Saturn': swe.SATURN, 'North Node': swe.MEAN_NODE
    }
    
    planetary_data = {}
    for name, obj_id in targets.items():
        res, _ = swe.calc_ut(jd, obj_id)
        planetary_data[name] = {
            'longitude': res[0],
            'speed_in_lon': res[3]
        }

    cusps, ascmc = swe.houses(jd, lat, lon, b'B')
    ascendant = ascmc[0]
    mc = ascmc[1]
    descendant = (ascendant + 180.0) % 360.0
    ic = (mc + 180.0) % 360.0
    
    sun_long = planetary_data['Sun']['longitude']
    moon_long = planetary_data['Moon']['longitude']
    
    is_diurnal = (sun_long - ascendant) % 360 > 180.0
    sect = 'Diurnal' if is_diurnal else 'Nocturnal'
    
    lot_of_fortune = (ascendant + moon_long - sun_long) % 360 if is_diurnal else (ascendant + sun_long - moon_long) % 360

    return {
        'julian_day': jd,
        'planetary_data': planetary_data,
        'houses': cusps,
        'ascendant': ascendant,
        'descendant': descendant,
        'mc': mc,
        'ic': ic,
        'sect': sect,
        'lot_of_fortune': lot_of_fortune
    }

# ==========================================
# 2. HELPER FUNCTIONS & VARIATION-SELECTOR-FREE RENDERER
# ==========================================

def get_zodiac_sign(longitude):
    signs = ['Aries', 'Taurus', 'Gemini', 'Cancer', 'Leo', 'Virgo', 'Libra', 'Scorpio', 'Sagittarius', 'Capricorn', 'Aquarius', 'Pisces']
    return signs[int(longitude // 30)]

def get_glyph_degree_string(longitude):
    # \uFE0E (VS15) forces TEXT presentation on every glyph. Without it on all
    # twelve, most fonts/browsers fall back to colored emoji-style rendering
    # for the ones that lack the selector.
    signs_text = ['\u2648\uFE0E', '\u2649\uFE0E', '\u264A\uFE0E', '\u264B\uFE0E', '\u264C\uFE0E', '\u264D\uFE0E',
                  '\u264E\uFE0E', '\u264F\uFE0E', '\u2650\uFE0E', '\u2651\uFE0E', '\u2652\uFE0E', '\u2653\uFE0E']
    sign_idx = int(longitude // 30)
    deg = int(longitude % 30)
    minute = int((longitude % 1) * 60)
    return f"{deg:02d}° {signs_text[sign_idx]} {minute:02d}'"

def get_degree_string(longitude):
    sign = get_zodiac_sign(longitude)
    deg = int(longitude % 30)
    minute = int((longitude % 1) * 60)
    return f"{deg:02d}° {sign[:3]} {minute:02d}'"

def generate_hybrid_svg(chart_data, location_query, lat, lon, dt_local, tz_name):
    size = 900
    cx, cy = 450, 450
    r_outer = 410
    r_zodiac = 345
    r_houses = 210
    r_inner = 110
    
    asc = chart_data['ascendant']
    asc_sign_start = math.floor(asc / 30) * 30
    
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="100%" height="100%" style="background-color: #ffffff; color: #000000; font-family: \'Noto Sans Symbols\', \'Segoe UI Symbol\', \'DejaVu Sans\', sans-serif;">']
    
    svg.append(f'<circle cx="{cx}" cy="{cy}" r="{r_outer}" fill="none" stroke="#000000" stroke-width="3"/>')
    svg.append(f'<circle cx="{cx}" cy="{cy}" r="{r_zodiac}" fill="none" stroke="#000000" stroke-width="2"/>')
    svg.append(f'<circle cx="{cx}" cy="{cy}" r="{r_houses}" fill="none" stroke="#000000" stroke-width="1.5"/>')
    svg.append(f'<circle cx="{cx}" cy="{cy}" r="{r_inner}" fill="#ffffff" stroke="#000000" stroke-width="1.5"/>')

    def lon_to_angle(longitude):
        return (longitude - asc_sign_start + 180) % 360

    def polar_to_cartesian(r, angle_deg):
        rad = math.radians(angle_deg)
        return cx + r * math.cos(rad), cy - r * math.sin(rad)

    signs_text = ['\u2648\uFE0E', '\u2649\uFE0E', '\u264A\uFE0E', '\u264B\uFE0E', '\u264C\uFE0E', '\u264D\uFE0E',
                  '\u264E\uFE0E', '\u264F\uFE0E', '\u2650\uFE0E', '\u2651\uFE0E', '\u2652\uFE0E', '\u2653\uFE0E']

    # 1. Whole Sign Boundary Sectors with explicit text symbols
    for i in range(12):
        sign_start_lon = (asc_sign_start + i * 30) % 360
        angle_start = lon_to_angle(sign_start_lon)
        
        x1, y1 = polar_to_cartesian(r_houses, angle_start)
        x2, y2 = polar_to_cartesian(r_outer, angle_start)
        svg.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#000000" stroke-width="1.5"/>')

        mid_lon = sign_start_lon + 15
        mid_angle = lon_to_angle(mid_lon)
        
        lx, ly = polar_to_cartesian((r_outer + r_zodiac) / 2, mid_angle)
        sign_idx = int((sign_start_lon // 30))
        svg.append(f'<text x="{lx}" y="{ly}" text-anchor="middle" dominant-baseline="central" font-size="16" font-weight="bold" fill="#000000">{signs_text[sign_idx]}</text>')

        hx_lab, hy_lab = polar_to_cartesian((r_houses + r_inner + 30) / 2, mid_angle)
        svg.append(f'<text x="{hx_lab}" y="{hy_lab}" text-anchor="middle" dominant-baseline="central" font-size="13" font-weight="bold" fill="#000000">{i+1}</text>')

        for d in range(5, 30, 5):
            tick_lon = sign_start_lon + d
            t_angle = lon_to_angle(tick_lon)
            t1_x, t1_y = polar_to_cartesian(r_zodiac, t_angle)
            t2_x, t2_y = polar_to_cartesian(r_zodiac + 6, t_angle)
            svg.append(f'<line x1="{t1_x}" y1="{t1_y}" x2="{t2_x}" y2="{t2_y}" stroke="#000000" stroke-width="0.75"/>')

    # 2. Quadrant House Cusp Lines (Alchabitius)
    cusps = chart_data['houses']
    for i, cusp_lon in enumerate(cusps):
        c_angle = lon_to_angle(cusp_lon)
        hx, hy = polar_to_cartesian(r_inner, c_angle)
        hx_out, hy_out = polar_to_cartesian(r_houses, c_angle)
        svg.append(f'<line x1="{hx}" y1="{hy}" x2="{hx_out}" y2="{hy_out}" stroke="#a94442" stroke-width="1.5" stroke-dasharray="4"/>')
        
        px_t1, py_t1 = polar_to_cartesian(r_houses, c_angle)
        px_t2, py_t2 = polar_to_cartesian(r_houses - 6, c_angle)
        svg.append(f'<line x1="{px_t1}" y1="{py_t1}" x2="{px_t2}" y2="{py_t2}" stroke="#a94442" stroke-width="2"/>')

    glyph_map = {
        'Sun': '\u2609\uFE0E', 'Moon': '\u263D\uFE0E', 'Mercury': '\u263F\uFE0E', 'Venus': '\u2640\uFE0E',
        'Mars': '\u2642\uFE0E', 'Jupiter': '\u2643\uFE0E', 'Saturn': '\u2644\uFE0E', 'North Node': '\u260A\uFE0E',
        'Ascendant': 'Asc', 'Midheaven': 'MC', 'Descendant': 'Des', 'IC': 'IC',
        'Lot of Fortune': '\u2297\uFE0E'
    }

    p_data = chart_data['planetary_data']
    all_points = list({
        **p_data,
        'Ascendant': {'longitude': chart_data['ascendant'], 'speed_in_lon': 1.0},
        'Midheaven': {'longitude': chart_data['mc'], 'speed_in_lon': 1.0},
        'Descendant': {'longitude': chart_data['descendant'], 'speed_in_lon': 1.0},
        'IC': {'longitude': chart_data['ic'], 'speed_in_lon': 1.0},
        'Lot of Fortune': {'longitude': chart_data['lot_of_fortune'], 'speed_in_lon': 1.0}
    }.items())

    all_points.sort(key=lambda x: x[1]['longitude'])

    ANGLE_NAMES = {'Ascendant', 'Midheaven', 'Descendant', 'IC'}
    angle_colors = {'Ascendant': '#0000ff', 'Descendant': '#0000ff', 'Midheaven': '#228b22', 'IC': '#228b22'}

    # --- Anti-collision label layout --------------------------------------
    # Points within CLUSTER_GAP degrees of each other are grouped into a
    # cluster. Earlier this stacked members purely along the RADIUS — but
    # that barely separates labels near the Ascendant/Descendant side of
    # the wheel, where the ring runs almost horizontal on screen, so a 25px
    # radius change is nearly all sideways and almost no vertical (the
    # symptom: Asc's label piling directly on top of Lot of Fortune's).
    # Instead, each cluster's anchor member is placed at LAYER_TOP along
    # its true radial direction, and every subsequent member is stacked a
    # fixed number of *screen* pixels below the anchor — guaranteeing real
    # vertical separation no matter where on the ring the cluster sits.
    # Angles (Asc/MC/Des/IC) take priority for the anchor slot when they
    # share a cluster with a planet/node/Lot of Fortune, since they're
    # conventionally labeled right at the ring regardless of what else is
    # nearby.
    CLUSTER_GAP = 6.0
    LAYER_TOP = r_zodiac - 40
    STACK_DY = 30

    clusters = []
    for planet, data in all_points:
        lon_val = data['longitude']
        if clusters and (lon_val - clusters[-1][-1][1]['longitude']) < CLUSTER_GAP:
            clusters[-1].append((planet, data))
        else:
            clusters.append([(planet, data)])
    # Longitude wraps at 360°; merge the first/last cluster if they abut
    if len(clusters) > 1:
        first_lon = clusters[0][0][1]['longitude']
        last_lon = clusters[-1][-1][1]['longitude']
        if (first_lon + 360 - last_lon) < CLUSTER_GAP:
            clusters[0] = clusters[-1] + clusters[0]
            clusters.pop()

    label_pos = {}
    for cluster in clusters:
        cluster_sorted = sorted(cluster, key=lambda pd: 0 if pd[0] in ANGLE_NAMES else 1)
        anchor_angle = lon_to_angle(cluster_sorted[0][1]['longitude'])
        anchor_px, anchor_py = polar_to_cartesian(LAYER_TOP, anchor_angle)
        for i, (planet, data) in enumerate(cluster_sorted):
            label_pos[planet] = (anchor_px, anchor_py + i * STACK_DY)

    # Axis Highlights — stop just short of each label instead of running
    # the full way to the ring and straight through the text sitting on it.
    for pt_key, pt_lon, pt_color in [
        ('Ascendant', chart_data['ascendant'], angle_colors['Ascendant']),
        ('Midheaven', chart_data['mc'], angle_colors['Midheaven']),
        ('Descendant', chart_data['descendant'], angle_colors['Descendant']),
        ('IC', chart_data['ic'], angle_colors['IC']),
    ]:
        pt_angle = lon_to_angle(pt_lon)
        label_px, label_py = label_pos[pt_key]
        label_r = math.hypot(label_px - cx, label_py - cy)
        line_end_r = min(label_r + 20, r_zodiac)
        px1, py1 = polar_to_cartesian(r_inner, pt_angle)
        px2, py2 = polar_to_cartesian(line_end_r, pt_angle)
        svg.append(f'<line x1="{px1}" y1="{py1}" x2="{px2}" y2="{py2}" stroke="{pt_color}" stroke-width="2" stroke-dasharray="2"/>')

    for planet, data in all_points:
        lon_val = data['longitude']
        speed = data.get('speed_in_lon', 1.0)
        is_rx = speed < 0 and planet not in ({'Sun', 'Moon', 'North Node'} | ANGLE_NAMES)

        p_angle = lon_to_angle(lon_val)
        px, py = label_pos[planet]
        tz_x, tz_y = polar_to_cartesian(r_zodiac, p_angle)

        # Small dot marks the point's true position on the zodiac ring.
        # The leader line stops ~18px short of the label instead of
        # running all the way to it, so the line never cuts through text.
        svg.append(f'<circle cx="{tz_x}" cy="{tz_y}" r="3" fill="#000000"/>')
        dxv, dyv = px - tz_x, py - tz_y
        dist = math.hypot(dxv, dyv)
        if dist > 20:
            t = (dist - 18) / dist
            lx_end, ly_end = tz_x + dxv * t, tz_y + dyv * t
            svg.append(f'<line x1="{tz_x}" y1="{tz_y}" x2="{lx_end}" y2="{ly_end}" stroke="#999999" stroke-width="0.75" stroke-dasharray="2"/>')

        sign_idx = int(lon_val // 30) % 12
        deg = int(lon_val % 30)
        minute = int((lon_val % 1) * 60)
        rx_tag = " Rx" if is_rx else ""
        symbol = glyph_map.get(planet, planet[:3])

        if planet in ANGLE_NAMES:
            # Angle labels (Asc/MC/Des/IC) are short text abbreviations, not
            # single glyphs, so they get a modest size that matches the
            # planet glyphs visually instead of towering over them. They're
            # also nudged to the side of their own axis spoke (left-aligned,
            # offset right) rather than centered directly on top of it.
            label_color = angle_colors.get(planet, '#000000')
            svg.append(
                f'<text x="{px+10}" y="{py-6}" text-anchor="start" fill="{label_color}">'
                f'<tspan font-size="14" font-weight="bold">{symbol}</tspan></text>'
                f'<text x="{px+10}" y="{py+9}" text-anchor="start" fill="{label_color}">'
                f'<tspan font-size="11" font-weight="bold">{deg:02d}\u00b0 {signs_text[sign_idx]} {minute:02d}\'</tspan></text>'
            )
        else:
            # Two-line stacked label (glyph+degree over sign+minutes) is far
            # more compact than one long horizontal string, so clustered
            # points stay readable.
            svg.append(
                f'<text x="{px}" y="{py-6}" text-anchor="middle" fill="#000000">'
                f'<tspan font-size="19" font-weight="bold">{symbol}</tspan>'
                f'<tspan font-size="12" font-weight="bold" dx="3">{deg:02d}\u00b0</tspan></text>'
                f'<text x="{px}" y="{py+9}" text-anchor="middle" fill="#000000">'
                f'<tspan font-size="12" font-weight="bold">{signs_text[sign_idx]} {minute:02d}\'{rx_tag}</tspan></text>'
            )

    # Central Metadata Hub
    svg.append(f'<text x="{cx}" y="{cy - 55}" text-anchor="middle" font-size="13" font-weight="bold" fill="#000000">Whole-Sign Hybrid Chart</text>')
    svg.append(f'<text x="{cx}" y="{cy - 35}" text-anchor="middle" font-size="11" fill="#000000">{location_query}</text>')
    svg.append(f'<text x="{cx}" y="{cy - 20}" text-anchor="middle" font-size="10" fill="#000000">Lat: {lat:.4f}° | Lon: {lon:.4f}°</text>')
    svg.append(f'<text x="{cx}" y="{cy - 5}" text-anchor="middle" font-size="10" fill="#000000">{dt_local.strftime("%Y-%m-%d %H:%M")} [{tz_name}]</text>')
    svg.append(f'<text x="{cx}" y="{cy + 15}" text-anchor="middle" font-size="10" font-weight="bold" fill="#000000">Sect: {chart_data["sect"]}</text>')
    svg.append(f'<text x="{cx}" y="{cy + 30}" text-anchor="middle" font-size="10" fill="#000000">Layout: Whole Sign + Alchabitius Cusps</text>')
    svg.append(f'<text x="{cx}" y="{cy + 45}" text-anchor="middle" font-size="10" fill="#000000">Zodiac: Tropical</text>')
    
    svg.append('</svg>')
    return "".join(svg)

# ==========================================
# 3. DIGNITY & ASPECT EVALUATORS
# ==========================================

# --- Shared classical dignity reference tables --------------------------
# Pulled out to module level so both evaluate_essential_dignities() and the
# prenatal syzygy engine (which needs to look up dignities at an arbitrary
# degree, not just at a planet's own position) can use the same data.
DOMICILES = {'Sun': ['Leo'], 'Moon': ['Cancer'], 'Mercury': ['Gemini', 'Virgo'], 'Venus': ['Taurus', 'Libra'], 'Mars': ['Aries', 'Scorpio'], 'Jupiter': ['Sagittarius', 'Pisces'], 'Saturn': ['Capricorn', 'Aquarius']}
EXALTATIONS = {'Sun': ['Aries'], 'Moon': ['Taurus'], 'Mercury': ['Virgo'], 'Venus': ['Pisces'], 'Mars': ['Capricorn'], 'Jupiter': ['Cancer'], 'Saturn': ['Libra']}
DETRIMENTS = {'Sun': ['Aquarius'], 'Moon': ['Capricorn'], 'Mercury': ['Sagittarius', 'Pisces'], 'Venus': ['Scorpio', 'Aries'], 'Mars': ['Libra', 'Taurus'], 'Jupiter': ['Gemini', 'Virgo'], 'Saturn': ['Cancer', 'Leo']}
FALLS = {'Sun': ['Libra'], 'Moon': ['Scorpio'], 'Mercury': ['Pisces'], 'Venus': ['Virgo'], 'Mars': ['Cancer'], 'Jupiter': ['Capricorn'], 'Saturn': ['Aries']}
EGYPTIAN_TERMS = {'Aries': [(6, 'Jupiter'), (12, 'Venus'), (20, 'Mercury'), (25, 'Mars'), (30, 'Saturn')], 'Taurus': [(8, 'Venus'), (14, 'Mercury'), (22, 'Jupiter'), (27, 'Saturn'), (30, 'Mars')], 'Gemini': [(6, 'Mercury'), (12, 'Venus'), (17, 'Jupiter'), (24, 'Mars'), (30, 'Saturn')], 'Cancer': [(7, 'Mars'), (13, 'Venus'), (19, 'Mercury'), (26, 'Jupiter'), (30, 'Saturn')], 'Leo': [(6, 'Jupiter'), (11, 'Venus'), (18, 'Saturn'), (24, 'Mercury'), (30, 'Mars')], 'Virgo': [(7, 'Mercury'), (17, 'Venus'), (21, 'Jupiter'), (28, 'Mars'), (30, 'Saturn')], 'Libra': [(6, 'Saturn'), (14, 'Mercury'), (21, 'Jupiter'), (28, 'Venus'), (30, 'Mars')], 'Scorpio': [(7, 'Mars'), (11, 'Venus'), (19, 'Mercury'), (24, 'Jupiter'), (30, 'Saturn')], 'Sagittarius': [(12, 'Jupiter'), (17, 'Venus'), (21, 'Mercury'), (26, 'Saturn'), (30, 'Mars')], 'Capricorn': [(7, 'Mercury'), (14, 'Jupiter'), (22, 'Venus'), (26, 'Saturn'), (30, 'Mars')], 'Aquarius': [(7, 'Venus'), (13, 'Mercury'), (20, 'Jupiter'), (25, 'Mars'), (30, 'Saturn')], 'Pisces': [(12, 'Venus'), (16, 'Jupiter'), (19, 'Mercury'), (28, 'Mars'), (30, 'Saturn')]}
CHALDEAN_ORDER = ['Mars', 'Sun', 'Venus', 'Mercury', 'Moon', 'Saturn', 'Jupiter']

# Dorothean triplicity rulers, keyed by element, each with the Day/Night/
# Participating lord (classical reconstruction as used in medieval Abbasid
# practice — e.g. Dorotheus via al-Biruni/Abu Ma'shar).
TRIPLICITY = {
    'Fire':  {'Day': 'Sun',   'Night': 'Jupiter', 'Participating': 'Saturn'},
    'Earth': {'Day': 'Venus', 'Night': 'Moon',    'Participating': 'Mars'},
    'Air':   {'Day': 'Saturn','Night': 'Mercury', 'Participating': 'Jupiter'},
    'Water': {'Day': 'Venus', 'Night': 'Mars',    'Participating': 'Moon'},
}
SIGN_ELEMENT = {
    'Aries': 'Fire', 'Leo': 'Fire', 'Sagittarius': 'Fire',
    'Taurus': 'Earth', 'Virgo': 'Earth', 'Capricorn': 'Earth',
    'Gemini': 'Air', 'Libra': 'Air', 'Aquarius': 'Air',
    'Cancer': 'Water', 'Scorpio': 'Water', 'Pisces': 'Water',
}
# Inverse lookups: sign -> the single planet that has domicile/exaltation there
SIGN_TO_DOMICILE = {sign: planet for planet, signs in DOMICILES.items() for sign in signs}
SIGN_TO_EXALTATION = {sign: planet for planet, signs in EXALTATIONS.items() for sign in signs}

# Masha'allah's delineations for a topical house's lord, keyed by
# [placed_in_house][lord_of_house] (i.e. outer key = the WSH house the lord
# is physically placed in, inner key = the topical house it rules).
MASHAALLAH_LORDS = {
    1: {1: "Respected in family (subject to other conditions)", 2: "Work with own hands, blessed without searching and need", 3: "Good for siblings from native", 4: "Master of his family and their livelihood; charitable to parents", 5: "Blessed with children in youth, happy with children", 6: "Illness of nature of that planet; death of animals and servants", 7: "Good from women, success from them", 8: "Long lifespan (if good condition); frustration in seeking necessities", 9: "Of fine religion, good soul, knowing the Sunnah", 10: "Associate of authorities, proficient in work, Sultan comes to him", 11: "Successful, good livelihood and condition, glad", 12: "Unhappy, enemies multiply and are victorious, tribulation, belligerent"},
    2: {1: "Will corrupt assets; but if received, gains from sign essence", 2: "Livelihood from known source; if looked at by infortune, ruin", 3: "Siblings compete for assets; they will seek the native", 4: "Prosperous parents; native inherits and is distinguished among siblings", 5: "Children will have good livelihood", 6: "Livelihood from what slaves produce, and animals; lowly benefits", 7: "Corrupts assets due to conflict", 8: "Inheritance; sometimes do work for government/authority", 9: "Assets from foreign country, benefit from travel", 10: "Livelihood from government/authority figure; accumulates assets", 11: "Benefit and assets from friends", 12: "Shameful work, bad character and livelihood, with deception"},
    3: {1: "Siblings suitable, dependent on native; good/wicked mind based on aspects", 2: "Gain from travels and siblings; religion/gain if a fortune", 3: "Siblings are well known, will protect him, love him", 4: "Parents have hardship from siblings; parents like native better", 5: "Native's children named after his siblings; successful in travels", 6: "Siblings have defects/illness, or do the work of slaves", 7: "Brother marries native's women; hostility; native marries relative", 8: "Siblings have defects, chronic illness, diminished condition", 9: "Siblings marry foreign women; moves to another country", 10: "Few siblings, siblings ruined; many travels", 11: "Well-known siblings, condition good, esp. in youth", 12: "Siblings hostile to native, hardship from them"},
    4: {1: "Reverent to parents; hardship from ruler; gains from fathers if received", 2: "Livelihood relates to ancestors; thriving childhood home; devotion", 3: "Siblings steal parents' assets; recognized as thieves", 4: "Parents well known, good reputation; short life if harmed", 5: "Native's children are wretches; encounters hardship due to them", 6: "Native is child of slaves or those doing slave work", 7: "Marries someone from own house, spouse is well known and good", 8: "Fathers are foreigners or have defects/illness, short lifespans", 9: "Parents have hidden illnesses, die outside homeland", 10: "Parents known to rulers; hardship from rulers", 11: "Father has chronic illness, short life, diminished condition", 12: "Parents/family hostile to native; native destroys/leaves childhood home"},
    5: {1: "Happy with children (if unharmed)", 2: "Children have status, will gain good", 3: "Native has siblings abroad who travel and have children", 4: "Prosperous parents see successive generations; good increases", 5: "Native has well-known children who are happy", 6: "Children's upbringing hard, children have defect", 7: "Native marries younger spouse, well-known and virtuous", 8: "Children die early, or have power over others due to Sultan", 9: "Has children in foreign country, delighted; children religious/educated", 10: "Abundance of children; illness/death if harmed; hardship from Sultan", 11: "Delightful children, blessed with good and comfort", 12: "Children debased, sick, from low-status; disobedient/hostile"},
    6: {1: "Miserable, slave work; illness if received; literal slave if Moon corrupted", 2: "Livelihood from 6th-place things; disaster/hardship if not received", 3: "Siblings are hostile and crave his ruin", 4: "Parents unknown in country; aspecting planet shows good/bad", 5: "Fortunate children, but defects will appear in them", 6: "Native healthy, if lord of Ascendant does not look", 7: "Native associates with slave girls or women with defects", 8: "Calamities in slaves and riding animals; not blessed by them", 9: "Blessed with slaves/animals; travel brings illness or corrupts slaves", 10: "Short lifespan, itinerant, enslaves free people", 11: "Bad condition in livelihood, little good, creating discord", 12: "Saddened by slaves and riding animals, no good in them"},
    7: {1: "Native very eager; subordinate to spouse", 2: "Lower-status women; gain/lose money in marriage", 3: "Marries a relative; brothers hostile or marry his women", 4: "Marries relative, good rank; father hostile to native", 5: "Younger spouse; children hostile; deluded about women; servant children", 6: "Sick/slave spouse; low-status spouse; bad reputation due to spouse", 7: "Suitable marriage; spouse has rank of maternal relatives; well-known", 8: "Will inherit from spouse; native dies in exile", 9: "Foreign spouse; good character/pious if a fortune", 10: "Esteemed, well-known spouse; higher-status and connected", 11: "Loving, happy spouse; children and benefit from spouse", 12: "Low-status or sick spouse; spouse is hostile"},
    8: {1: "A wicked soul, much distress, faint-hearted", 2: "Livelihood from inheritance/dead; generous; assets taken if connecting to 8th", 3: "Brother's women will not survive or get inheritance", 4: "Diminishes father's lifespan; fear for native, mother dies in childbirth", 5: "Children premature or miscarried", 6: "Native healthy if lord of Ascendant does not look", 7: "Consumes inheritance of women; marries foreign woman", 8: "Native is healthy, illness insignificant, death will be light", 9: "Suffers robbery on journeys, eager in accumulating assets", 10: "Authority in youth, a follower who seeks leadership/boasts", 11: "Not well known/descended; does low work like commerce", 12: "Few enemies; many of native's slaves will die"},
    9: {1: "Remains in foreign land; travel; speaks knowledge; sensible if unharmed", 2: "Livelihood from travel, piety, religion", 3: "Siblings marry foreign women, live abroad", 4: "Unknown fathers who leave, with defects/bad death; bad faith", 5: "Has children abroad; they make native happy", 6: "Excellent intentions; illness while traveling, encounters hardship", 7: "Marries foreign woman given by her brother; native loves her", 8: "Bad thoughts and work; die in exile", 9: "Few journeys; upright in religion of fathers, good intention", 10: "Authority/leadership traveling abroad; offered the good", 11: "Good fortune abroad; happy until end of life", 12: "Siblings/native have hardship from enemies traveling; bad religion"},
    10: {1: "Interacting with Sultan, known by him, living due to Sultan", 2: "Livelihood from the Sultan", 3: "Death of siblings, jealousy and grudges", 4: "Fathers well known to Sultan", 5: "Defects and illnesses in children", 6: "Encounters hardship from the Sultan", 7: "Marriage to someone related to Sultan, fortunate woman, good from her", 8: "Native's ruin will be due to Sultan", 9: "Siblings marry better women or from Sultan's family; native is pious", 10: "Proficient in work, having influence, livelihood from work", 11: "Authority in friendship, Sultan will not be hostile", 12: "Hostility from Sultan and native's superiors; unhappy"},
    11: {1: "Good character, many friends, but harsh toward children/few children", 2: "Livelihood relates to friends/commerce; friends need native if Asc lord looks", 3: "Pious siblings known for that; reflects well on native", 4: "Short lifespan for father; bad condition unless received by fortune", 5: "Pleased by children and family; praise for him", 6: "Friends are not well known", 7: "Marries fertile woman, will love her, live in luxury because of her", 8: "Friends diminished; corrupts friendship; dies when condition is good", 9: "Pious friends, shared religious love; siblings marry foreign women", 10: "Friends benefit from native; child inherits assets from Sultan", 11: "Lives comfortable life, imputed with goodness, many friends, culture", 12: "Leaves goodness of friends; friends become enemies, unhappy"},
    12: {1: "Miserable, bad livelihood, enemies victorious; worse if bad connection", 2: "Life/livelihood from prisons, enemies; distressed and poor in soul", 3: "Hostile siblings; they get his authority and are superior", 4: "Parents are foreigners in exile; aspects show if good/bad for them", 5: "Children have defect/illness, will die; no children if unfortunate", 6: "Hostile to lower-status people; native sickly or ongoing health problems", 7: "Spouse has little esteem; hardship/hostility; secret relationships/cheating", 8: "Killing by enemies feared, or foolish people oppose him", 9: "Wicked intentions; corrupts religion, thinks he is right", 10: "Dispossessed by authorities; griefs; works with large animals/secrets", 11: "Little good, miserable life; few friends, many enemies", 12: "Few enemies, may not manifest; safe from them"}
}

# Delineations for a planet occupying a given Whole Sign House, keyed by
# [wsh_house][planet]['Good'|'Bad'] (Good/Bad selected by the planet's own
# net dignity score), synthesizing Rhetorius and PN4.
PLANETS_IN_HOUSES = {
    1: {'Saturn': {'Good': 'Eldest sibling; land ownership, building.', 'Bad': 'Sluggish, laborious; blamed.'}, 'Jupiter': {'Good': 'Glorious, in charge; celebrated, respected.', 'Bad': 'Decrease in assets, worries.'}, 'Mars': {'Good': 'Military, leader; successful, victorious.', 'Bad': 'Unstable, squandering; fugitive, misfortune.'}, 'Sun': {'Good': 'Noble, lucky; high rank, management.', 'Bad': 'Less noble, less benefit.'}, 'Venus': {'Good': 'Talented, friends of powerful; delight, clothing, sex.', 'Bad': 'Lustful, lower professions; disturbed life, quarrels.'}, 'Mercury': {'Good': 'Intellectual activities; status, praise.', 'Bad': 'Practical activities; loss in business.'}, 'Moon': {'Good': 'Increases of fortune, in charge.', 'Bad': 'Sailing, poor livelihood.'}},
    2: {'Saturn': {'Good': 'Slow increase, strong; unexpected source.', 'Bad': 'Loss, lazy, ill; abject sources.'}, 'Jupiter': {'Good': 'Good all around, inheritances; leisure.', 'Bad': 'Spending without enjoyment; distress.'}, 'Mars': {'Good': 'Military; enough; benefits from unexpected place.', 'Bad': 'Exile, dangers; squandering.'}, 'Sun': {'Good': 'Dignity, wealth; leisure.', 'Bad': 'Private property; negligence.'}, 'Venus': {'Good': 'Prosperous, pleasing, arts.', 'Bad': 'Disruption, corruption, stagnation.'}, 'Mercury': {'Good': 'Good at business/learning; partnerships.', 'Bad': 'Loss, downturn, blame, quarrels.'}, 'Moon': {'Good': 'Brilliant, conspicuous, extravagant.', 'Bad': 'Family/actions dispersed and divided.'}},
    3: {'Saturn': {'Good': 'Initiates, religious chiefs; travel for benefit.', 'Bad': 'Recluses, bad religious reputation, confused thinking.'}, 'Jupiter': {'Good': 'Balanced moderation; good religious reputation, delight in siblings.', 'Bad': 'Distress from siblings, negligence in religion.'}, 'Mars': {'Good': 'Glory with labor; strong in travel.', 'Bad': 'Bad death for father, evil reports, difficult travels.'}, 'Sun': {'Good': 'Good for marriage/religion; travel with good status.', 'Bad': 'Bad reputation, distress due to travel/relatives.'}, 'Venus': {'Good': 'Travel with good/status, benefit from brothers.', 'Bad': 'Bad reports/journeys, contention with brothers.'}, 'Mercury': {'Good': 'Divination, astrologers, good journeys/visions.', 'Bad': 'Priests, magicians; bad travels, religious doubts.'}, 'Moon': {'Good': 'Good religious activities (with Jupiter).', 'Bad': 'Ignoble mother; sacrilege.'}},
    4: {'Saturn': {'Good': 'Lots of wealth; owning property, building.', 'Bad': 'Destroys/threatens parents, illness; blamed.'}, 'Jupiter': {'Good': 'Commanders, jurists; respected, land/family assets.', 'Bad': 'Middling assets; worries from these topics.'}, 'Mars': {'Good': 'Generals, soldiers; successful, inspiring awe.', 'Bad': 'Sickly, surgery; misfortune for home/land.'}, 'Sun': {'Good': 'Increase in rank, commended, victory.', 'Bad': 'Annoyances, destroys livelihood.'}, 'Venus': {'Good': 'Fortunate over time, charming; delight in important people.', 'Bad': 'Loss of patrimony, widowhood; conflict in land/family.'}, 'Mercury': {'Good': 'Lots of money, initiates; status from Mercurial things/govt.', 'Bad': 'Forbidden mysteries; accusation, family quarrels.'}, 'Moon': {'Good': 'Honored mother, good living standard.', 'Bad': 'Lowborn mother, commerce.'}},
    5: {'Saturn': {'Good': 'Kingships/command over time; delight in friends.', 'Bad': 'Delayed, sluggish; distress from children/siblings.'}, 'Jupiter': {'Good': 'Fortunate, honored, healthy; blessed by children.', 'Bad': 'Lower-status activities; distressed by children.'}, 'Mars': {'Good': 'Good possessions, honor; increase in children/rank.', 'Bad': 'Harmful travel; distress/accidents in family/children.'}, 'Sun': {'Good': 'Honored, easy goals; delight/increase in children.', 'Bad': 'Moderate fortune, childless; distress due to children.'}, 'Venus': {'Good': 'Prize-fighters, victors; increase/delight in women/children.', 'Bad': 'Distress from women and children.'}, 'Mercury': {'Good': 'Wealth, managing money; befriend nobles, profit.', 'Bad': 'Squanders money; hostility, illness/death of children.'}, 'Moon': {'Good': 'Gracious, leaders, fortunate.', 'Bad': 'Foreign travel, parents estranged, orphans.'}},
    6: {'Saturn': {'Good': 'Moderate; slaves/animals recover.', 'Bad': 'No inheritance, dangers from slaves, chronic illness.'}, 'Jupiter': {'Good': 'Exposure, valuable materials; praise from subordinates.', 'Bad': 'Illnesses, distress from enemies/confinement.'}, 'Mars': {'Good': 'Healthy, victory over enemies.', 'Bad': 'Harms children, uneven life, illness.'}, 'Sun': {'Good': 'Mild-temperedness, safety; good fortune from parents.', 'Bad': 'Bad death for father; illness from heat, eye/head pain.'}, 'Venus': {'Good': 'Benefit from underclass/medicine.', 'Bad': 'Sex with low women, badly treated; pregnancy difficulties.'}, 'Mercury': {'Good': 'Advancement through speech/business.', 'Bad': 'Idle, evil; illness, arrested, confinement.'}, 'Moon': {'Good': 'Health and bodily stability.', 'Bad': 'Fluctuating health, bodily weakness.'}},
    7: {'Saturn': {'Good': 'Success after delay, long-lived; owning property.', 'Bad': 'Sickly, blamed/harmed.'}, 'Jupiter': {'Good': 'Long-lived, wealth later; praised, respected.', 'Bad': 'Moderate living; worries.'}, 'Mars': {'Good': 'Professions from fire/violence; successful, inspiring awe.', 'Bad': 'Violent, short-lived; illnesses, spending.'}, 'Sun': {'Good': 'Increase in rank/land; administrators.', 'Bad': 'Lower-status; harm, conflict.'}, 'Venus': {'Good': 'Age difference/delay in marriage; delight, increase in rank.', 'Bad': 'Lewdness; distress in sex/marriage.'}, 'Mercury': {'Good': 'Managing affairs of women; status from govt.', 'Bad': 'Accusation, loss in business, family quarrels.'}, 'Moon': {'Good': 'Changes, travel, better resources.', 'Bad': 'Foreign travel with dangers.'}},
    8: {'Saturn': {'Good': 'Assets over time/inheritance; good from dead.', 'Bad': 'Loss, bad death; squandering, distress.'}, 'Jupiter': {'Good': 'Acquisition, inheritance; leisure.', 'Bad': 'Spending without happiness; distress/fighting due to assets.'}, 'Mars': {'Good': 'Hot-heads, bright; benefit from dead/inheritance.', 'Bad': 'Patrimony spent, dangers; squandered assets.'}, 'Sun': {'Good': "Father's early death, healing; mild-temperedness.", 'Bad': 'Wealthy, benefit from death of women; negligence.'}, 'Venus': {'Good': 'Marry late; benefit from underclass/commerce.', 'Bad': 'STDs, seizures; negligence in assets, loss.'}, 'Mercury': {'Good': 'Money, management, inheritance; praised.', 'Bad': 'Ineffective, lazy; blamed, quarreling due to assets.'}, 'Moon': {'Good': 'Sudden inheritance, finding money.', 'Bad': 'Passive and sick.'}},
    9: {'Saturn': {'Good': 'Initiates, chief priests; travel for benefit.', 'Bad': 'Recluses, anger at gods; confused religious opinions.'}, 'Jupiter': {'Good': 'Predicting future, priesthood; good religious reputation.', 'Bad': 'Unsteady, false speech; negligence in religion.'}, 'Mars': {'Good': 'Glory, unpunished; strong in travel.', 'Bad': 'Evil reports, difficult travels, illness.'}, 'Sun': {'Good': 'Building sacred things, religious authority.', 'Bad': 'Harm in travels; bad reputation, distress.'}, 'Venus': {'Good': 'Divine men, gifts from temples; travel with status.', 'Bad': 'Demon-afflicted, illicit sex; bad reports/journeys.'}, 'Mercury': {'Good': 'Priests, wizards; good journeys, true visions.', 'Bad': 'Seers, sacrificers; defamed in religion, bad assets.'}, 'Moon': {'Good': 'Living abroad, notable; benefiting from temples.', 'Bad': 'Wandering and dangers; temple servants.'}},
    10: {'Saturn': {'Good': 'Leaders, farmers; agriculture, building.', 'Bad': 'Bunglers, sorrow; blamed, low work.'}, 'Jupiter': {'Good': 'Athletes, famous, trusted; celebrated, respected.', 'Bad': 'Handsome but unstable; decreased assets, worry.'}, 'Mars': {'Good': 'Unstable, fearsome leaders; successful, favored by Sultan.', 'Bad': 'No accomplishments, fugitives; misfortune, violence.'}, 'Sun': {'Good': 'Rulers, leaders, dignity; increased rank, victorious.', 'Bad': 'Success through violence; fear from Sultan.'}, 'Venus': {'Good': 'Honored, musicians; honored by Sultan, delight.', 'Bad': 'Blamed, burdened, indecent; bad reputation.'}, 'Mercury': {'Good': 'Admirable, trusted; status from writing.', 'Bad': 'Changes, living abroad; accusation, loss.'}, 'Moon': {'Good': 'Rulers, successful, trusted.', 'Bad': 'Hardship, unsteady, error.'}},
    11: {'Saturn': {'Good': 'Middling goods over time; delight in friends.', 'Bad': 'Distress from children/siblings.'}, 'Jupiter': {'Good': 'Fortunate, renowned, authority; good way of life.', 'Bad': 'Diminished effectiveness; worries, distressed by friends.'}, 'Mars': {'Good': 'Many goods, dignity; increase in children/rank.', 'Bad': 'Feuding with friends and brothers.'}, 'Sun': {'Good': 'Lucky, noble; good condition, delight in friends.', 'Bad': 'Harms children; distress due to friends.'}, 'Venus': {'Good': 'Powerful, trusted; increase/delight in friends.', 'Bad': 'Sterility, unusual sexuality; hostility to friends.'}, 'Mercury': {'Good': 'Ingenious, accounts; befriend nobles, profit.', 'Bad': 'Spending, agents; hostility from friends, illness of children.'}, 'Moon': {'Good': 'Rulers, favored, good from parents.', 'Bad': 'Living abroad, estrangements, orphanhood.'}},
    12: {'Saturn': {'Good': 'Victory over enemies.', 'Bad': 'Loss of inheritance, mental disturbance; hardship from prison.'}, 'Jupiter': {'Good': 'Praise from subordinates; fights against superiors.', 'Bad': 'Illnesses, distress from enemies/confinement.'}, 'Mars': {'Good': 'Safety from enemies.', 'Bad': 'Illness, injury, dangers from slaves/criminals; exile.'}, 'Sun': {'Good': 'Good reputation, safety.', 'Bad': 'Long illnesses, defects, slavery; distress due to enemies.'}, 'Venus': {'Good': 'Benefit from underclass.', 'Bad': 'Ruined by women; leisure time and illness, punishment.'}, 'Mercury': {'Good': 'Managing big affairs; benefit from low work.', 'Bad': 'Danger from slaves; arrested unfairly, confinement.'}, 'Moon': {'Good': 'Luckiness/authority (with fortunes).', 'Bad': 'Short life, humble; bad for patrimony/travel.'}}
}

def evaluate_essential_dignities(planetary_data, sect):
    """Full 5-fold essential dignity hierarchy (Domicile/Exaltation/
    Triplicity/Term/Face) plus major debilities (Detriment/Fall) and
    Peregrine. Reuses get_essential_rulers() so the exact same lordship
    logic backs both a planet's own dignity score and the syzygy-degree
    lookup used elsewhere."""
    triplicity_key = 'triplicity_day' if sect == 'Diurnal' else 'triplicity_night'
    results = {}
    for planet, data in planetary_data.items():
        if planet == 'North Node': continue

        lon = data['longitude']
        current_sign = get_zodiac_sign(lon)
        rulers = get_essential_rulers(lon)

        is_domicile = rulers['domicile'] == planet
        is_exalted = rulers['exaltation'] == planet
        is_triplicity = rulers[triplicity_key] == planet
        is_term = rulers['term'] == planet
        is_face = rulers['face'] == planet
        is_detriment = current_sign in DETRIMENTS.get(planet, [])
        is_fall = current_sign in FALLS.get(planet, [])

        has_positive = is_domicile or is_exalted or is_triplicity or is_term or is_face
        is_peregrine = not has_positive

        score = (is_domicile * 5 + is_exalted * 4 + is_triplicity * 3 + is_term * 2 + is_face * 1
                 - is_detriment * 5 - is_fall * 4 - is_peregrine * 5)

        labels = []
        if is_domicile: labels.append("Dom (+5)")
        if is_exalted: labels.append("Exalt (+4)")
        if is_triplicity: labels.append("Trip (+3)")
        if is_term: labels.append("Term (+2)")
        if is_face: labels.append("Face (+1)")
        if is_detriment: labels.append("Detriment (-5)")
        if is_fall: labels.append("Fall (-4)")
        if is_peregrine: labels.append("Peregrine (-5)")

        results[planet] = {
            'Essential Score': score,
            'Domicile': is_domicile, 'Exalt': is_exalted, 'Triplicity': is_triplicity,
            'Term': is_term, 'Face': is_face, 'Detriment': is_detriment, 'Fall': is_fall,
            'Peregrine': is_peregrine, 'Essential Labels': labels,
        }
    return results

# --- Accidental dignity reference tables ---------------------------------
JOY_HOUSES = {'Mercury': 1, 'Moon': 3, 'Venus': 5, 'Mars': 6, 'Sun': 9, 'Jupiter': 11, 'Saturn': 12}
DIURNAL_SECT_PLANETS = {'Sun', 'Jupiter', 'Saturn'}
NOCTURNAL_SECT_PLANETS = {'Moon', 'Venus', 'Mars'}
MASCULINE_SIGNS = {'Aries', 'Gemini', 'Leo', 'Libra', 'Sagittarius', 'Aquarius'}
FEMININE_SIGNS = {'Taurus', 'Cancer', 'Virgo', 'Scorpio', 'Capricorn', 'Pisces'}
# Mean daily motions (deg/day), used only to gauge "swift" vs. an average pace
AVERAGE_DAILY_MOTION = {'Sun': 0.9856, 'Moon': 13.1764, 'Mercury': 1.383, 'Venus': 1.2, 'Mars': 0.524, 'Jupiter': 0.083, 'Saturn': 0.034}
ANGLE_HOUSES = {1, 4, 7, 10}
SUCCEDENT_HOUSES = {2, 5, 8, 11}
CADENT_HOUSES = {3, 6, 9, 12}
MALEFIC_HOUSES = {6, 8, 12}  # override to -5 regardless of their normal angularity group
HOUSE_ORDINAL = {1: '1st', 2: '2nd', 3: '3rd', 4: '4th', 5: '5th', 6: '6th', 7: '7th', 8: '8th', 9: '9th', 10: '10th', 11: '11th', 12: '12th'}

def evaluate_accidental_dignities(planetary_data, natal_houses, sect):
    """Accidental dignity scoring: house angularity (Whole Sign, anchored to
    the Ascendant, with the 6/8/12 malefic-house override), planetary joys,
    sect/hayz, motion & speed, and solar phasing (cazimi/combust/under the
    beams)."""
    sun_lon = planetary_data['Sun']['longitude']
    ascendant = natal_houses[0]
    is_diurnal_chart = (sect == 'Diurnal')
    results = {}

    for planet, data in planetary_data.items():
        if planet == 'North Node': continue
        lon, speed = data['longitude'], data['speed_in_lon']
        labels = []
        score = 0

        # --- House angularity (Whole Sign) --------------------------------
        house_num = get_wsh_house(lon, ascendant)
        if house_num in MALEFIC_HOUSES:
            house_pts, house_label = -5, f"Malefic {HOUSE_ORDINAL[house_num]} (-5)"
        elif house_num in ANGLE_HOUSES:
            house_pts, house_label = 5, f"Angular {HOUSE_ORDINAL[house_num]} (+5)"
        elif house_num in SUCCEDENT_HOUSES:
            house_pts, house_label = 3, f"Succedent {HOUSE_ORDINAL[house_num]} (+3)"
        else:
            house_pts, house_label = -3, f"Cadent {HOUSE_ORDINAL[house_num]} (-3)"
        score += house_pts
        labels.append(house_label)

        # --- Planetary joy -------------------------------------------------
        is_joy = JOY_HOUSES.get(planet) == house_num
        if is_joy:
            score += 3
            labels.append("Joy (+3)")

        # --- Sect / Hayz -----------------------------------------------
        # All three must hold: the planet's own sect matches the chart's
        # sect, it's on its sect-favored side of the horizon, and it's in
        # a sign of its sect-favored gender. Mercury's own sect is derived
        # from its solar phase (morning riser = diurnal, evening star =
        # nocturnal) rather than being fixed.
        current_sign = get_zodiac_sign(lon)
        is_above_horizon = (lon - ascendant) % 360 > 180.0

        if planet == 'Mercury':
            signed = ((lon - sun_lon + 180.0) % 360.0) - 180.0
            planet_is_diurnal = signed < 0  # west of the Sun = morning star
        elif planet in DIURNAL_SECT_PLANETS:
            planet_is_diurnal = True
        elif planet in NOCTURNAL_SECT_PLANETS:
            planet_is_diurnal = False
        else:
            planet_is_diurnal = None

        is_hayz = False
        if planet_is_diurnal is not None:
            sect_match = (planet_is_diurnal == is_diurnal_chart)
            if planet_is_diurnal:
                horizon_ok = is_above_horizon
                gender_ok = current_sign in MASCULINE_SIGNS
            else:
                horizon_ok = not is_above_horizon
                gender_ok = current_sign in FEMININE_SIGNS
            is_hayz = sect_match and horizon_ok and gender_ok
        if is_hayz:
            score += 3
            labels.append("Hayz (+3)")

        # --- Motion & speed -------------------------------------------
        is_stationary = abs(speed) <= 0.003
        is_retrograde = speed < 0 and not is_stationary and planet not in ('Sun', 'Moon')
        avg_motion = AVERAGE_DAILY_MOTION.get(planet, 1.0)
        is_swift = (not is_stationary) and (not is_retrograde) and speed > avg_motion
        if is_stationary:
            score -= 2
            labels.append("Stationary (-2)")
        elif is_retrograde:
            score -= 5
            labels.append("Retrograde (-5)")
        elif is_swift:
            score += 2
            labels.append("Swift (+2)")

        # --- Solar phase: Cazimi / Combust / Under the Beams -----------
        is_cazimi = is_combust = is_under_beams = False
        if planet != 'Sun':
            dist = abs(lon - sun_lon)
            dist = dist if dist <= 180 else 360 - dist
            if dist <= (17 / 60):
                is_cazimi = True
                score += 5
                labels.append("Cazimi (+5)")
            elif dist <= 8.5:
                is_combust = True
                score -= 5
                labels.append("Combust (-5)")
            elif dist <= 15.0:
                is_under_beams = True
                score -= 2
                labels.append("Under Beams (-2)")

        results[planet] = {
            'Accidental Score': score, 'House': house_num, 'Joy': is_joy, 'Hayz': is_hayz,
            'Stationary': is_stationary, 'Retrograde': is_retrograde, 'Swift': is_swift,
            'Cazimi': is_cazimi, 'Combust': is_combust, 'UnderBeams': is_under_beams,
            'Accidental Labels': labels,
        }
    return results

# Whole-sign configuration allowed by classical Ptolemaic doctrine: how many
# signs apart the two bodies must be for a given aspect, and its exact angle.
ASPECT_BY_SIGN_COUNT = {
    0: ('Conjunction', 0.0),
    2: ('Sextile', 60.0),
    3: ('Square', 90.0),
    4: ('Trine', 120.0),
    6: ('Opposition', 180.0),
}

def evaluate_ptolemaic_aspects(planetary_data):
    orbs = {'Sun': 15.0, 'Moon': 12.0, 'Saturn': 9.0, 'Jupiter': 9.0, 'Mars': 8.0, 'Venus': 7.0, 'Mercury': 7.0}
    planets = [p for p in planetary_data.keys() if p != 'North Node']
    aspects = []

    for p1, p2 in combinations(planets, 2):
        lon1, v1 = planetary_data[p1]['longitude'], planetary_data[p1]['speed_in_lon']
        lon2, v2 = planetary_data[p2]['longitude'], planetary_data[p2]['speed_in_lon']

        # --- 1. Whole-sign configuration gate ---------------------------
        # Reject any pair whose SIGNS aren't in a valid Ptolemaic relationship
        # (0/2/3/4/6 signs apart) before ever looking at degree orbs — this
        # is what prohibits out-of-sign aspects regardless of how close the
        # raw degree separation happens to land.
        sign_idx1 = int(lon1 // 30)
        sign_idx2 = int(lon2 // 30)
        raw_signs_apart = abs(sign_idx1 - sign_idx2)
        signs_apart = min(raw_signs_apart, 12 - raw_signs_apart)
        if signs_apart not in ASPECT_BY_SIGN_COUNT:
            continue
        aspect_name, target = ASPECT_BY_SIGN_COUNT[signs_apart]

        # --- 2. Half-orb (moiety) sum orb check -------------------------
        raw_dist = abs(lon1 - lon2)
        dist = raw_dist if raw_dist <= 180.0 else 360.0 - raw_dist
        moiety1 = orbs.get(p1, 7.0) / 2.0
        moiety2 = orbs.get(p2, 7.0) / 2.0
        max_orb = moiety1 + moiety2
        deviation = dist - target  # signed distance from partile (exact)
        if abs(deviation) > max_orb:
            continue

        # --- 3. Faster planet (al-daf') vs Receiver ----------------------
        if abs(v1) >= abs(v2):
            fast_name, fast_lon, fast_speed = p1, lon1, v1
            slow_name, slow_lon, slow_speed = p2, lon2, v2
        else:
            fast_name, fast_lon, fast_speed = p2, lon2, v2
            slow_name, slow_lon, slow_speed = p1, lon1, v1

        # --- 4. Kinetic direction: Applying (ittisal) vs Separating (insiraf)
        # s = signed position of the faster body relative to the receiver,
        # wrapped to (-180, 180]. deviation = dist - target is how far off
        # from the exact aspect we currently are; its time-derivative is
        # sign(s) * delta_v. Deviation shrinking toward zero => Applying.
        s = ((fast_lon - slow_lon + 180.0) % 360.0) - 180.0
        sign_s = 1.0 if s >= 0 else -1.0
        delta_v = fast_speed - slow_speed
        rate = sign_s * delta_v
        motion = "Applying" if (deviation == 0 or deviation * rate < 0) else "Separating"

        # --- 5. Dexter / Sinister orientation ----------------------------
        # Conjunction and Opposition have no handedness. For the others: the
        # faster planet trailing the receiver (earlier in the zodiac, s<0)
        # casts a Dexter aspect; leading it (later in the zodiac, s>0)
        # casts a Sinister aspect.
        if aspect_name in ('Conjunction', 'Opposition'):
            orientation = "Direct"
        else:
            orientation = "Sinister" if s > 0 else "Dexter"

        # --- 6. Format remaining distance to the partile (exact) aspect --
        remaining = abs(deviation)
        dd = int(remaining)
        mm = int(round((remaining - dd) * 60))
        if mm == 60:
            dd += 1
            mm = 0
        orb_str = f"{dd:02d}\u00b0 {mm:02d}'"

        aspects.append({
            'Faster Planet': fast_name,
            'Aspect': aspect_name,
            'Receiver': slow_name,
            'Motion': motion,
            'Orientation': orientation,
            'Exact Orb Dist': orb_str,
        })

    return aspects

# --- Prenatal Lunation (Syzygy) — Abbasid / Medieval Method --------------

def get_house_number(longitude, cusps):
    """Given a longitude and 12 quadrant house cusps (in house-1..house-12
    order, as returned by swe.houses), return which house (1-12) it falls
    in. Each house spans from its own cusp forward to the next cusp."""
    for i in range(12):
        start = cusps[i]
        end = cusps[(i + 1) % 12]
        span = (end - start) % 360
        rel = (longitude - start) % 360
        if rel < span:
            return i + 1
    return 12

def get_wsh_house(longitude, ascendant_lon):
    """Whole Sign House: the Ascendant's sign is house 1 in its entirety,
    and each subsequent sign (in zodiacal order) is the next house — no
    quadrant cusp division within a sign."""
    asc_sign_idx = int(ascendant_lon // 30)
    target_sign_idx = int(longitude // 30)
    return ((target_sign_idx - asc_sign_idx) % 12) + 1

def get_essential_rulers(longitude):
    """Look up the classical essential dignities (domicile, exaltation,
    triplicity, term, face) ruling an arbitrary zodiacal degree — not tied
    to any specific planet's own position, unlike evaluate_essential_
    dignities(). Used to profile the prenatal syzygy degree itself."""
    sign = get_zodiac_sign(longitude)
    degree_in_sign = longitude % 30
    element = SIGN_ELEMENT[sign]
    triplicity = TRIPLICITY[element]
    term_lord = next((lord for limit, lord in EGYPTIAN_TERMS.get(sign, []) if degree_in_sign < limit), '-')
    face_lord = CHALDEAN_ORDER[int(longitude // 10) % 7]
    return {
        'sign': sign,
        'domicile': SIGN_TO_DOMICILE.get(sign, '-'),
        'exaltation': SIGN_TO_EXALTATION.get(sign, '-'),
        'triplicity_day': triplicity['Day'],
        'triplicity_night': triplicity['Night'],
        'triplicity_participating': triplicity['Participating'],
        'term': term_lord,
        'face': face_lord,
    }

def _sun_moon_signed_offset(jd, target_deg):
    """Sun/Moon longitudes and speeds at jd, plus the signed angular offset
    of (Moon - Sun) from target_deg, normalized to (-180, 180]. Positive
    means (Moon - Sun) has already passed target_deg going forward."""
    sun_res = swe.calc_ut(jd, swe.SUN)[0]
    moon_res = swe.calc_ut(jd, swe.MOON)[0]
    sun_lon, sun_speed = sun_res[0], sun_res[3]
    moon_lon, moon_speed = moon_res[0], moon_res[3]
    diff = (moon_lon - sun_lon) % 360
    offset = (diff - target_deg + 180) % 360 - 180
    rel_speed = moon_speed - sun_speed
    return sun_lon, moon_lon, offset, rel_speed

def calculate_prenatal_syzygy(jd_natal, lat, lon, natal_houses):
    """Find the most recent New or Full Moon before birth (the 'prenatal
    syzygy'), following the Abbasid/medieval method:

    - If the Moon is less than 180° ahead of the Sun at birth, the preceding
      syzygy was a conjunction (Coniunctio) — the birth is 'Conjunctional'.
    - Otherwise it was an opposition (Praeventio) — the birth is
      'Preventional', and per medieval practice the Syzygy degree is taken
      from whichever luminary was above the horizon (in the diurnal
      hemisphere) at that prenatal Full Moon, defaulting to the Moon if
      that can't be determined.

    The exact moment is located by a Newton-style root search on the
    Sun/Moon ephemeris (not just an average-synodic-month estimate), then
    the resulting degree is profiled for essential dignities and placed
    into the natal Whole Sign houses (anchored to the natal Ascendant).
    """
    sun_lon0 = swe.calc_ut(jd_natal, swe.SUN)[0][0]
    moon_lon0 = swe.calc_ut(jd_natal, swe.MOON)[0][0]
    diff0 = (moon_lon0 - sun_lon0) % 360

    if diff0 < 180.0:
        target = 0.0
        event_type = 'Conjunctional'
        event_label = 'Conjunctional (New Moon)'
    else:
        target = 180.0
        event_type = 'Preventional'
        event_label = 'Preventional (Full Moon)'

    # Initial guess via the average relative Moon-Sun speed (~12.19 deg/day),
    # then refine with Newton's method against the true ephemeris speed.
    AVG_REL_SPEED = 12.19075
    delta_back_deg = (diff0 - target) % 360
    jd_guess = jd_natal - delta_back_deg / AVG_REL_SPEED

    sun_lon, moon_lon = sun_lon0, moon_lon0
    for _ in range(15):
        sun_lon, moon_lon, offset, rel_speed = _sun_moon_signed_offset(jd_guess, target)
        if abs(offset) < 1e-6:
            break
        if abs(rel_speed) < 1e-6:
            rel_speed = AVG_REL_SPEED
        jd_guess -= offset / rel_speed

    jd_syzygy = jd_guess

    # Ascendant/houses at the syzygy moment (same natal location), needed
    # to determine (a) which luminary was above the horizon for a
    # Preventional birth, and (b) the sect of the syzygy chart itself for
    # triplicity assignment.
    _, ascmc_syzygy = swe.houses(jd_syzygy, lat, lon, b'B')
    asc_syzygy = ascmc_syzygy[0]
    sun_above_horizon = (sun_lon - asc_syzygy) % 360 > 180.0
    moon_above_horizon = (moon_lon - asc_syzygy) % 360 > 180.0
    is_diurnal_syzygy = sun_above_horizon

    if event_type == 'Conjunctional':
        syzygy_lon = sun_lon  # sun_lon == moon_lon at convergence
    else:
        if sun_above_horizon and not moon_above_horizon:
            syzygy_lon = sun_lon
        elif moon_above_horizon and not sun_above_horizon:
            syzygy_lon = moon_lon
        else:
            syzygy_lon = moon_lon  # ambiguous/edge case: default to the Moon

    natal_house = get_wsh_house(syzygy_lon, natal_houses[0])
    rulers = get_essential_rulers(syzygy_lon)

    active_triplicity_lord = rulers['triplicity_day'] if is_diurnal_syzygy else rulers['triplicity_night']
    active_triplicity_label = 'Day' if is_diurnal_syzygy else 'Night'

    # Almuten / Syzygy Lord: weighted score across the essential dignities
    # ruling this degree (only the sect-appropriate triplicity lord counts,
    # not the Participating ruler, matching standard almuten scoring).
    scores = {}
    def _add_score(planet, pts):
        if planet and planet != '-':
            scores[planet] = scores.get(planet, 0) + pts
    _add_score(rulers['domicile'], 5)
    _add_score(rulers['exaltation'], 4)
    _add_score(active_triplicity_lord, 3)
    _add_score(rulers['term'], 2)
    _add_score(rulers['face'], 1)
    almuten = max(scores, key=scores.get) if scores else '-'
    almuten_score = scores.get(almuten, 0)

    return {
        'jd_syzygy': jd_syzygy,
        'event_type': event_type,
        'event_label': event_label,
        'syzygy_longitude': syzygy_lon,
        'sect_diurnal': is_diurnal_syzygy,
        'natal_house': natal_house,
        'rulers': rulers,
        'active_triplicity_lord': active_triplicity_lord,
        'active_triplicity_label': active_triplicity_label,
        'almuten': almuten,
        'almuten_score': almuten_score,
    }

# --- Planetary Day & Hour (Chronocrats) ----------------------------------

DAY_LORD_BY_WEEKDAY = {0: 'Moon', 1: 'Mars', 2: 'Mercury', 3: 'Jupiter', 4: 'Venus', 5: 'Saturn', 6: 'Sun'}  # Python's date.weekday(): Monday=0..Sunday=6
CHALDEAN_HOUR_ORDER = ['Saturn', 'Jupiter', 'Mars', 'Sun', 'Venus', 'Mercury', 'Moon']

class _CircumpolarSunError(Exception):
    """Raised when swe.rise_trans reports no sunrise/sunset event exists
    for this date/location (res == -2: the Sun is circumpolar — polar day
    or polar night)."""
    pass

def _find_sun_event(jd_start, lat, lon, want_rise):
    """Wraps swe.rise_trans to find the next sunrise/sunset at or after
    jd_start. Signature confirmed directly against a real pyswisseph
    install (20230604): rise_trans(tjdut, body, rsmi, geopos, atpress=0.0,
    attemp=0.0, flags=FLG_SWIEPH) -> (res, tret), tret[0] = JD of event.
    res == -2 means the body is circumpolar (no event that day) -- this is
    a real condition for extreme-latitude locations, not just a hypothetical."""
    rsmi = swe.CALC_RISE if want_rise else swe.CALC_SET
    geopos = (lon, lat, 0.0)
    res, tret = swe.rise_trans(jd_start, swe.SUN, rsmi, geopos)
    if res != 0:
        raise _CircumpolarSunError(
            f"No {'sunrise' if want_rise else 'sunset'} event found near jd={jd_start:.4f} "
            f"at lat={lat}, lon={lon} (res={res}) — the Sun is circumpolar there on this date."
        )
    return tret[0]

def calculate_chronocrats(jd_utc, lat, lon, local_dt):
    """Planetary Day (from the astrological day, which begins at Sunrise —
    not the calendar weekday) and Planetary Hour (from the unequal/temporal
    hour system, bracketed by real sunrise/sunset times for this date and
    location). Falls back to calendar weekday + equal 2-hour divisions if
    the location has no sunrise/sunset that day (circumpolar)."""
    approximate = False
    try:
        # Bracket the birth moment with the nearest sunrise/sunset before
        # and after it. Forward-search from jd_utc for the "after" events,
        # then forward-search from just under 1.2 days before each "after"
        # event to find the immediately preceding one (a safe margin:
        # consecutive solar events are ~1.0 day apart, so 1.2 days
        # guarantees we land on exactly the previous one, not two cycles back).
        sunrise_after = _find_sun_event(jd_utc, lat, lon, True)
        sunset_after = _find_sun_event(jd_utc, lat, lon, False)
        sunrise_before = _find_sun_event(sunrise_after - 1.2, lat, lon, True)
        sunset_before = _find_sun_event(sunset_after - 1.2, lat, lon, False)

        # The astrological day strictly begins at Sunrise, not midnight. A
        # birth between midnight and sunrise still belongs to the PRECEDING
        # day's astrological date — e.g. 3:00 AM Wednesday is still ruled
        # by Tuesday's Day Lord. Step the local clock backward by the exact
        # elapsed time since the most recent sunrise to sample the correct
        # weekday.
        time_since_sunrise = jd_utc - sunrise_before
        true_day_dt = local_dt - timedelta(days=time_since_sunrise)
        day_lord = DAY_LORD_BY_WEEKDAY[true_day_dt.weekday()]

        is_diurnal_hour = sunrise_before > sunset_before
        if is_diurnal_hour:
            period_start, period_end = sunrise_before, sunset_after
        else:
            period_start, period_end = sunset_before, sunrise_after

        temporal_hour = (period_end - period_start) / 12.0
        elapsed = jd_utc - period_start
        hour_number = int(elapsed / temporal_hour) + 1 if temporal_hour > 0 else 1
        hour_number = min(max(hour_number, 1), 12)

        # The 24 planetary hours (12 day + 12 night) are one continuous
        # cycle of 7, starting with the Day Lord at day-hour 1; night-hour
        # 1 is the 13th step in that same cycle.
        cycle_offset = (hour_number - 1) if is_diurnal_hour else (12 + hour_number - 1)
    except _CircumpolarSunError:
        # No real sunrise/sunset exists at this date/location (polar day or
        # polar night) — there's no meaningful temporal-hour boundary to
        # anchor to, so fall back to the plain calendar weekday (no
        # astrological-day rollover correction) and an equal 2-hour
        # division of the 24-hour civil day, continuing the same 7-cycle.
        approximate = True
        day_lord = DAY_LORD_BY_WEEKDAY[local_dt.weekday()]
        cycle_offset = min(local_dt.hour // 2, 11)

    start_index = CHALDEAN_HOUR_ORDER.index(day_lord)
    hour_lord = CHALDEAN_HOUR_ORDER[(start_index + cycle_offset) % 7]

    return {'Day Lord': day_lord, 'Hour Lord': hour_lord, 'Approximate': approximate}

# --- Classical Lots (Arabic Parts) ---------------------------------------

def calculate_classical_lots(asc, sun, moon, sect):
    """Lots of Fortune, Spirit, Exaltation, and Basis, sect-flipped per
    medieval practice. Basis is placed the short angular distance between
    Fortune and Spirit away from the Ascendant."""
    is_diurnal = (sect == 'Diurnal')

    fortune = (asc + moon - sun) % 360.0 if is_diurnal else (asc + sun - moon) % 360.0
    spirit = (asc + sun - moon) % 360.0 if is_diurnal else (asc + moon - sun) % 360.0
    exaltation = (asc + 19.0 - sun) % 360.0 if is_diurnal else (asc + 33.0 - moon) % 360.0

    raw_dist = abs(fortune - spirit)
    dist = raw_dist if raw_dist <= 180.0 else 360.0 - raw_dist
    basis = (asc + dist) % 360.0

    lots = {
        'Lot of Fortune': fortune,
        'Lot of Spirit': spirit,
        'Lot of Exaltation': exaltation,
        'Lot of Basis': basis,
    }
    result = []
    for name, lon_val in lots.items():
        result.append({
            'Lot Name': name,
            'Position': get_degree_string(lon_val),
            'WSH House': get_wsh_house(lon_val, asc),
            'Sign Dispositor': SIGN_TO_DOMICILE.get(get_zodiac_sign(lon_val), '-'),
        })
    return result

# --- Special Degrees & Conditions ----------------------------------------

# Classical "pitted"/"welled" degrees (Bi'r) by sign, as supplied by the user.
WELLED_DEGREES = {
    'Aries': [6, 11, 16, 23, 29],
    'Taurus': [5, 12, 24, 25],
    'Gemini': [2, 12, 17, 26, 30],
    'Cancer': [12, 17, 23, 26, 30],
    'Leo': [6, 13, 15, 22, 23, 28],
    'Virgo': [8, 13, 16, 21, 22],
    'Libra': [1, 7, 20, 30],
    'Scorpio': [9, 10, 22, 23, 27],
    'Sagittarius': [7, 12, 15, 24, 27, 30],
    'Capricorn': [7, 17, 22, 24, 29],
    'Aquarius': [1, 12, 17, 22, 24, 29],
    'Pisces': [4, 9, 24, 27, 28],
}

def evaluate_special_degrees(planetary_data):
    """Flags planets in the Via Combusta (15 Libra-15 Scorpio) and/or a
    classical welled/pitted degree of their current sign."""
    results = []
    for planet, data in planetary_data.items():
        if planet == 'North Node': continue
        lon = data['longitude']
        conditions = []

        if 195.0 <= lon <= 225.0:
            conditions.append("Via Combusta")

        sign = get_zodiac_sign(lon)
        degree_1_based = int(lon % 30) + 1
        if degree_1_based in WELLED_DEGREES.get(sign, []):
            conditions.append("Welled Degree")

        if conditions:
            results.append({
                'Planet': planet,
                'Position': get_degree_string(lon),
                'Condition': ", ".join(conditions),
            })
    return results

def evaluate_house_lords(planetary_data, ascendant_lon):
    """For each Whole Sign topical house (1-12), find its domicile lord and
    the WSH house that lord is physically placed in, then look up
    Masha'allah's delineation for that [placed_in][ruled_house] pairing."""
    asc_idx = int(ascendant_lon // 30)
    results = []
    for house_i in range(1, 13):
        sign_idx = (asc_idx + house_i - 1) % 12
        cusp_sign = get_zodiac_sign(sign_idx * 30 + 15.0)  # mid-sign probe, sign is constant across the whole 30 deg
        domicile_lord = SIGN_TO_DOMICILE.get(cusp_sign)

        if domicile_lord not in ('Sun', 'Moon') and domicile_lord not in planetary_data:
            continue

        lord_lon = planetary_data[domicile_lord]['longitude']
        placed_in = get_wsh_house(lord_lon, ascendant_lon)
        text = MASHAALLAH_LORDS.get(placed_in, {}).get(house_i, '-')

        results.append({
            'Topical House': house_i,
            'Cusp Sign': cusp_sign,
            'Domicile Lord': domicile_lord,
            'Placed In (WSH)': placed_in,
            "Masha'allah Signification": text,
        })
    return results

def evaluate_planets_in_houses(planetary_data, essential, accidental, ascendant_lon):
    """For each of the 7 classical planets, determine its Whole Sign House
    placement and net dignity score, then look up the Rhetorius/PN4-derived
    delineation for that planet in that house under its Good/Bad condition."""
    results = []
    for planet, data in planetary_data.items():
        if planet == 'North Node': continue

        wsh_house = get_wsh_house(data['longitude'], ascendant_lon)
        net_score = essential[planet]['Essential Score'] + accidental[planet]['Accidental Score']
        condition = 'Good' if net_score >= 0 else 'Bad'
        delineation = PLANETS_IN_HOUSES[wsh_house][planet][condition]

        results.append({
            'Planet': planet,
            'Placed In (WSH)': wsh_house,
            'Net Score': net_score,
            'Condition': condition,
            'Classical Signification': delineation,
        })
    return results

# --- Chronocrator Matrix (Time Lords): Profections & Distributions -------

def calculate_time_lords(ascendant_lon, birth_date, target_date):
    """Annual Profection (Lord of the Year) and a simple Ptolemaic
    Distribution (1 degree = 1 year, Egyptian-term ruler of the directed
    Ascendant) for the given target date."""
    days_alive = (target_date - birth_date).days
    fractional_age = days_alive / 365.2425
    integer_age = int(fractional_age)

    # --- Annual Profection ---------------------------------------------
    natal_sign_idx = int(ascendant_lon // 30)
    profected_sign_idx = (natal_sign_idx + integer_age) % 12
    profected_sign = get_zodiac_sign(profected_sign_idx * 30.0 + 15.0)  # mid-sign probe
    lord_of_year = SIGN_TO_DOMICILE.get(profected_sign, '-')

    # --- Distribution (Ptolemaic Egyptian Terms) ------------------------
    directed_asc_lon = (ascendant_lon + fractional_age) % 360.0
    directed_sign = get_zodiac_sign(directed_asc_lon)
    degree_in_sign = directed_asc_lon % 30.0
    distributor = next((lord for limit, lord in EGYPTIAN_TERMS.get(directed_sign, []) if degree_in_sign < limit), '-')

    return [
        {
            'Technique': 'Annual Profection',
            'Active Point': profected_sign,
            'Active Ruler': lord_of_year,
            'Details': f"Age {integer_age} (1 Sign / Year)",
        },
        {
            'Technique': 'Distribution (Ptolemaic)',
            'Active Point': f"{get_degree_string(directed_asc_lon)}",
            'Active Ruler': distributor,
            'Details': "Egyptian Term (1\u00b0 / Year)",
        },
    ]

# ==========================================
# 4. STREAMLIT UI INTEGRATION
# ==========================================

st.set_page_config(page_title="Traditional Astrology Engine", layout="wide")

st.sidebar.header("Calculation Parameters")

if "saved_charts" not in st.session_state:
    st.session_state["saved_charts"] = load_saved_charts()

def _apply_selected_chart():
    """on_change callback: runs before the script reruns, so writing into
    these session_state keys here makes the widgets below pick up the
    loaded values on this same rerun."""
    name = st.session_state.get("chart_picker")
    if name and name != "-- New Chart --":
        entry = st.session_state["saved_charts"].get(name, {})
        if "date_string" in entry:
            st.session_state["date_input_key"] = entry["date_string"]
        if "time_string" in entry:
            try:
                h, m, s = (int(x) for x in entry["time_string"].split(":"))
                st.session_state["time_input_key"] = time(h, m, s)
            except (ValueError, KeyError):
                pass
        if "location_query" in entry:
            st.session_state["location_input_key"] = entry["location_query"]

chart_options = ["-- New Chart --"] + sorted(st.session_state["saved_charts"].keys())
load_col, del_col = st.sidebar.columns([3, 1])
load_col.selectbox("\U0001F4C2 Load Saved Chart", chart_options, key="chart_picker", on_change=_apply_selected_chart)
if del_col.button("\U0001F5D1", help="Delete the selected saved chart"):
    picked = st.session_state.get("chart_picker")
    if picked and picked != "-- New Chart --" and picked in st.session_state["saved_charts"]:
        del st.session_state["saved_charts"][picked]
        write_saved_charts(st.session_state["saved_charts"])
        st.rerun()

date_string = st.sidebar.text_input("Local Date (YYYY-MM-DD)", "1240-05-23", key="date_input_key")
try:
    parsed_datetime = datetime.strptime(date_string, "%Y-%m-%d")
    input_date = parsed_datetime.date()
except ValueError:
    st.sidebar.error("Invalid syntax. Enforce YYYY-MM-DD format (e.g., 1240-05-23).")
    st.stop()

input_time = st.sidebar.time_input("Local Time", time(14, 30), key="time_input_key")

st.sidebar.markdown("---")
st.sidebar.header("Location Data")

manual_coords = st.sidebar.checkbox("Manual Coordinate Entry")

if manual_coords:
    lat = st.sidebar.number_input("Latitude", value=43.7698, format="%.4f")
    lon = st.sidebar.number_input("Longitude", value=11.2556, format="%.4f")
    location_query = f"Manual [{lat:.4f}, {lon:.4f}]"
else:
    default_loc = st.session_state.get('location_input_key', 'Florence')
    city_search = st.sidebar.text_input("City Search", default_loc, key="location_input_key")

    if city_search:
        db_path = Path(__file__).parent / "atlas.db"
        if db_path.exists():
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT name, admin1, country, lat, lon
                    FROM cities
                    WHERE name LIKE ? COLLATE NOCASE OR ascii_name LIKE ? COLLATE NOCASE
                    ORDER BY population DESC
                    LIMIT 20
                """, (city_search + '%', city_search + '%'))
                matches = cursor.fetchall()

            if matches:
                options = {}
                for m in matches:
                    # Format: City, State/Admin (Country Code)
                    label = f"{m[0]}, {m[1]} ({m[2]})"
                    # Deduplicate identical names in the same region
                    if label in options:
                        label += f" [{m[3]:.4f}, {m[4]:.4f}]"
                    options[label] = (m[3], m[4])

                selected_label = st.sidebar.selectbox("Select specific location:", list(options.keys()))
                lat, lon = options[selected_label]
                location_query = selected_label
            else:
                st.sidebar.warning("No matches found in offline atlas.")
                lat, lon, location_query = None, None, None
        else:
            st.sidebar.error("`atlas.db` not found. Please ensure it is in the root directory.")
            lat, lon, location_query = None, None, None
    else:
        lat, lon, location_query = None, None, None

new_chart_name = st.sidebar.text_input("Chart Name (for saving)", value="", placeholder="e.g. Test Chart 1240")
if st.sidebar.button("\U0001F4BE Save This Chart"):
    trimmed_name = new_chart_name.strip()
    if trimmed_name:
        st.session_state["saved_charts"][trimmed_name] = {
            "date_string": date_string,
            "time_string": input_time.strftime("%H:%M:%S"),
            "location_query": location_query,
        }
        if write_saved_charts(st.session_state["saved_charts"]):
            st.sidebar.success(f"Saved '{trimmed_name}'.")
        else:
            st.sidebar.error("Could not write saved_charts.json to disk.")
    else:
        st.sidebar.warning("Enter a name before saving.")

st.sidebar.markdown("---")

target_date_string = st.sidebar.text_input("Target Date for Prediction (YYYY-MM-DD)", datetime.now().strftime("%Y-%m-%d"))
try:
    target_date = datetime.strptime(target_date_string, "%Y-%m-%d").date()
except ValueError:
    st.sidebar.error("Invalid Target Date syntax.")
    st.stop()

if location_query and lat is not None and lon is not None:
    st.sidebar.success(f"**Resolved:** {lat:.4f}, {lon:.4f}")

    tf = TimezoneFinder()
    tz_name = tf.timezone_at(lng=lon, lat=lat)
    
    if tz_name:
        local_tz = pytz.timezone(tz_name)
        local_dt = datetime.combine(input_date, input_time)
        localized_dt = local_tz.localize(local_dt)
        dt_utc = localized_dt.astimezone(pytz.utc)
        
        st.sidebar.info(f"**Timezone:** {tz_name}\n**UTC Offset:** {dt_utc.strftime('%H:%M:%S')} UTC")
        
        chart_data = calculate_traditional_chart(dt_utc, lat, lon)
        p_data = chart_data['planetary_data']
        sect = chart_data['sect']

        essential = evaluate_essential_dignities(p_data, sect)
        accidental = evaluate_accidental_dignities(p_data, chart_data['houses'], sect)
        aspects = evaluate_ptolemaic_aspects(p_data)
        syzygy = calculate_prenatal_syzygy(chart_data['julian_day'], lat, lon, chart_data['houses'])
        chronocrats = calculate_chronocrats(chart_data['julian_day'], lat, lon, local_dt)
        classical_lots = calculate_classical_lots(chart_data['ascendant'], p_data['Sun']['longitude'], p_data['Moon']['longitude'], sect)
        special_degrees = evaluate_special_degrees(p_data)
        house_lords_data = evaluate_house_lords(p_data, chart_data['ascendant'])
        planets_in_houses_data = evaluate_planets_in_houses(p_data, essential, accidental, chart_data['ascendant'])
        time_lords_data = calculate_time_lords(chart_data['ascendant'], input_date, target_date)

        svg_code = generate_hybrid_svg(chart_data, location_query, lat, lon, local_dt, tz_name)

        st.title("Traditional Astrological Engine")

        tab_wheel, tab_metrics = st.tabs(["Chart Wheel (WSH)", "Tables & Metrics"])

        with tab_wheel:
            st.components.v1.html(svg_code, height=720, scrolling=True)

        with tab_metrics:
            hdr1, hdr2, hdr3, hdr4 = st.columns(4)
            hdr1.metric("Calculated JD", f"{chart_data['julian_day']:.4f}")
            hdr2.metric("Sect", sect)
            hdr3.metric("Lord of the Day", chronocrats['Day Lord'])
            hdr4.metric("Lord of the Hour", chronocrats['Hour Lord'])
            if chronocrats.get('Approximate'):
                st.caption(
                    "\u26a0\ufe0f No sunrise/sunset exists for this date at this location (circumpolar "
                    "day/night) — Day and Hour Lord fall back to the plain calendar weekday and an "
                    "equal 2-hour division of the day, rather than true unequal temporal hours."
                )

            st.subheader("Chronocrator Matrix (Active Time Lords)")
            st.dataframe(pd.DataFrame(time_lords_data), hide_index=True, width='stretch')

            col1, col2 = st.columns(2)

            with col1:
                st.subheader("Planetary Positions")
                # True planets only — angles, nodes, and Lot of Fortune
                # now live in the "Calculated Points" table alongside it.
                pos_list = [{"Planet": p, "Position": get_degree_string(d['longitude'])} for p, d in p_data.items() if p != 'North Node']
                st.dataframe(pd.DataFrame(pos_list), hide_index=True, width='stretch')

                st.subheader("Calculated Points")
                north_node_lon = p_data['North Node']['longitude']
                south_node_lon = (north_node_lon + 180.0) % 360.0
                calculated_points = {
                    'Ascendant': chart_data['ascendant'],
                    'Midheaven': chart_data['mc'],
                    'Descendant': chart_data['descendant'],
                    'Imum Coeli': chart_data['ic'],
                    'North Node': north_node_lon,
                    'South Node': south_node_lon,
                    'Lot of Fortune': chart_data['lot_of_fortune'],
                }
                calc_list = [{"Point": name, "Position": get_degree_string(lon_val)} for name, lon_val in calculated_points.items()]
                st.dataframe(pd.DataFrame(calc_list), hide_index=True, width='stretch')

                st.subheader("Classical Lots")
                st.dataframe(pd.DataFrame(classical_lots), hide_index=True, width='stretch')

                st.subheader("House Cusps (Alchabitius)")
                house_list = [{"House": i+1, "Alchabitius Cusp": get_degree_string(chart_data['houses'][i])} for i in range(12)]
                st.dataframe(pd.DataFrame(house_list), hide_index=True, width='stretch')

            with col2:
                st.subheader("Planetary Dignity Evaluation")
                dignity_list = []
                for p in essential.keys():
                    ess = essential[p]
                    acc = accidental[p]

                    dignity_list.append({
                        "Planet": p,
                        "Net": ess['Essential Score'] + acc['Accidental Score'],
                        "Ess": ess['Essential Score'],
                        "Acc": acc['Accidental Score'],
                        "Essential Dignities": ", ".join(ess['Essential Labels']) if ess['Essential Labels'] else "-",
                        "Accidental Conditions": ", ".join(acc['Accidental Labels']) if acc['Accidental Labels'] else "-",
                    })

                df_dignity = pd.DataFrame(dignity_list).sort_values(by="Net", ascending=False)
                st.dataframe(df_dignity, hide_index=True, width='stretch')

                st.subheader("Lordship Mapping")
                triplicity_key = 'triplicity_day' if sect == 'Diurnal' else 'triplicity_night'
                lordship_list = []
                for p, data in p_data.items():
                    if p == 'North Node': continue
                    rulers = get_essential_rulers(data['longitude'])
                    lordship_list.append({
                        "Planet": p,
                        "Sign Dispositor": rulers['domicile'],
                        "Exaltation Lord": rulers['exaltation'],
                        "Triplicity Lord": rulers[triplicity_key],
                        "Term Lord": rulers['term'],
                        "Face Lord": rulers['face'],
                    })
                st.dataframe(pd.DataFrame(lordship_list), hide_index=True, width='stretch')

                st.subheader("Prenatal Lunation (Syzygy)")
                r = syzygy['rulers']
                triplicity_str = (
                    f"{syzygy['active_triplicity_lord']}\u2605 ({syzygy['active_triplicity_label']}) \u00b7 "
                    f"Day: {r['triplicity_day']} \u00b7 Night: {r['triplicity_night']} \u00b7 Part: {r['triplicity_participating']}"
                )
                syzygy_rows = [
                    {"Metric": "Event Type", "Value": syzygy['event_label']},
                    {"Metric": "Position", "Value": get_degree_string(syzygy['syzygy_longitude'])},
                    {"Metric": "Natal House", "Value": f"House {syzygy['natal_house']}"},
                    {"Metric": "Domicile Lord", "Value": r['domicile']},
                    {"Metric": "Exaltation Lord", "Value": r['exaltation']},
                    {"Metric": "Triplicity Lords", "Value": triplicity_str},
                    {"Metric": "Term Lord", "Value": r['term']},
                    {"Metric": "Face Lord", "Value": r['face']},
                    {"Metric": "Syzygy Lord (Almuten)", "Value": f"{syzygy['almuten']} (Score: {syzygy['almuten_score']})"},
                ]
                st.dataframe(pd.DataFrame(syzygy_rows), hide_index=True, width='stretch')

            st.subheader("Special Degrees & Conditions")
            if special_degrees:
                st.dataframe(pd.DataFrame(special_degrees), hide_index=True, width='stretch')
            else:
                st.write("No planets in anomalous degrees.")

            st.subheader("Topical Planets in Houses (Rhetorius & PN4)")
            st.dataframe(pd.DataFrame(planets_in_houses_data), hide_index=True, width='stretch')

            st.subheader("Ptolemaic Aspects")
            if aspects:
                st.dataframe(pd.DataFrame(aspects), hide_index=True, width='stretch')
            else:
                st.write("No traditional aspects formed within defined orbs.")

            st.subheader("Topical House Lords (Masha'allah)")
            st.dataframe(pd.DataFrame(house_lords_data), hide_index=True, width='stretch')
    else:
        st.sidebar.error("Timezone boundary not found for coordinates.")
