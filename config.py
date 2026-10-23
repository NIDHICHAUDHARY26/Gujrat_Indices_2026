"""Central configuration. Most future changes (regions, months, ranges) happen here only."""

# ---- Earth Engine -------------------------------------------------------
SERVICE_ACCOUNT = "gee-dashboard@agriculture-indices-dashboard.iam.gserviceaccount.com"
SERVICE_ACCOUNT_PROJECT = "agriculture-indices-dashboard"
LOCAL_PROJECT = "ee0-chaudharynidhi2309"        # used only for local `earthengine authenticate`

S2_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"
S2_BANDS = ["B2", "B3", "B4", "B5", "B8", "B11", "B12"]
MAX_CLOUDY_PERCENT = 70      # drop very cloudy scenes first (faster for a whole state)

# ---- Time ---------------------------------------------------------------
YEAR = 2026
AVAILABLE_MONTHS = [1, 2, 3, 4, 5, 6, 7, 8, 9]   # add 10, 11, 12 when data exists
ROTATION_SECONDS = 5                               # each map stays 5 seconds

# ---- Output (static site) -----------------------------------------------
OUTPUT_DIR = "site"          # the folder you deploy to Netlify: site/index.html, site/data.json, site/images/...
IMAGE_DIMENSION = 1800       # longest side of each PNG in pixels (lower = faster, e.g. 1200)

# ---- Page text ----------------------------------------------------------
PAGE_TITLE = f"SOIL AND VEGETATION INDICES - {YEAR}"
FOOTER_TEXT = "Anand Agricultural University"

# ---- Regions ------------------------------------------------------------
GUJ_ASSET = "projects/ee0-chaudharynidhi2309/assets/guj_dis"

# Whole-state entry. With `--districts`, one extra entry per district is generated
# using the district-name column of the asset (see DISTRICT_FIELD).
REGIONS = {
    "Gujarat": {"asset": GUJ_ASSET, "filter": None},
}
DEFAULT_REGION = "Gujarat"

# Column in guj_dis that holds the district name.
#   "auto"  -> script guesses (district / dist_name / dtname / name ...)
#   None    -> no per-district entries, only REGIONS above
#   "NAME"  -> your exact column name
DISTRICT_FIELD = "auto"

# ---- Indices (order = playback order) -----------------------------------
INDICES = [
    {"key": "EVI",   "name": "Enhanced Vegetation Index",                    "min": 0.0,  "max": 0.8},
    {"key": "GNDVI", "name": "Green Normalized Difference Vegetation Index", "min": 0.0,  "max": 0.8},
    {"key": "NDMI",  "name": "Normalized Difference Moisture Index",         "min": -0.3, "max": 0.5},
    {"key": "NDVI",  "name": "Normalized Difference Vegetation Index",       "min": 0.0,  "max": 0.9},
    {"key": "NDRE",  "name": "Normalized Difference Red Edge Index",         "min": 0.0,  "max": 0.6},
    {"key": "SI",    "name": "Salinity Index",                               "min": 0.05, "max": 0.35},
    {"key": "SMI",   "name": "Soil Moisture Index",                          "min": 0.0,  "max": 0.4},
    {"key": "SAVI",  "name": "Soil-Adjusted Vegetation Index",               "min": 0.0,  "max": 1.0},
    {"key": "NDWI",  "name": "Normalized Difference Water Index",            "min": -0.6, "max": 0.4},
]

# Same low->high ramp for all maps and legends (red -> yellow -> green).
PALETTE = ["a50026", "d73027", "f46d43", "fdae61", "fee08b", "ffffbf",
           "d9ef8b", "a6d96a", "66bd63", "1a9850", "006837"]
