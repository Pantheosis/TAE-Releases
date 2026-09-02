import swisseph as swe

print("=== swe.rise_trans docstring ===")
print(swe.rise_trans.__doc__)
print()
print("=== Module version ===")
print("pyswisseph version:", getattr(swe, "__version__", "unknown"))
print()
print("=== Live test call ===")
# Florence, Italy roughly -- same test coordinates used earlier in this project
lat, lon = 43.7698, 11.2556
jd_now = swe.julday(2024, 6, 21, 12.0)  # noon UTC, summer solstice, easy to sanity-check
try:
    result = swe.rise_trans(jd_now, swe.SUN, swe.CALC_RISE, (lon, lat, 0.0))
    print("4-arg call (no atpress/attemp) SUCCEEDED:")
    print(" ", result)
except TypeError as e:
    print("4-arg call FAILED:", e)
    try:
        result = swe.rise_trans(jd_now, swe.SUN, swe.CALC_RISE, (lon, lat, 0.0), 0, 0)
        print("6-arg call (with atpress/attemp) SUCCEEDED:")
        print(" ", result)
    except TypeError as e2:
        print("6-arg call ALSO FAILED:", e2)
