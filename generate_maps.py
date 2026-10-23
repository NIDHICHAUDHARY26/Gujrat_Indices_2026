"""Generate the static maps for the Netlify dashboard.

Run on your PC (needs Earth Engine access):

    python generate_maps.py                 # whole Gujarat, all months/indices in config.py
    python generate_maps.py --districts     # also one entry per district
    python generate_maps.py --months 9      # only September (re-run later for new months)
    python generate_maps.py --skip-existing # don't re-download PNGs that already exist

Output (config.OUTPUT_DIR, default "site"):
    site/data.json
    site/images/<region>/<MM>/<INDEX>.png

Then drag the whole `site` folder onto Netlify (index.html is already inside it).
"""
import argparse
import calendar
import json
import os
import re
import sys
import time
from pathlib import Path

import ee
import requests

import config


# --------------------------------------------------------------------------
# Earth Engine init
# --------------------------------------------------------------------------
def init_ee(key_file=None):
    """Service-account key file if given (or GEE_KEY_FILE env var), else local login."""
    key_file = key_file or os.environ.get("GEE_KEY_FILE")
    if key_file:
        creds = ee.ServiceAccountCredentials(config.SERVICE_ACCOUNT, key_file)
        ee.Initialize(creds, project=config.SERVICE_ACCOUNT_PROJECT)
        return
    try:
        ee.Initialize(project=config.LOCAL_PROJECT)
    except Exception:
        ee.Authenticate()
        ee.Initialize(project=config.LOCAL_PROJECT)


# --------------------------------------------------------------------------
# Sentinel-2 monthly composite + indices
# --------------------------------------------------------------------------
def _mask_clouds(img):
    scl = img.select("SCL")
    # 3 = cloud shadow, 8/9 = cloud medium/high, 10 = thin cirrus, 1 = saturated/defective
    bad = scl.eq(3).Or(scl.eq(8)).Or(scl.eq(9)).Or(scl.eq(10)).Or(scl.eq(1))
    return img.updateMask(bad.Not())


def monthly_composite(geom, month):
    start = ee.Date.fromYMD(config.YEAR, month, 1)
    end = start.advance(1, "month")
    col = (ee.ImageCollection(config.S2_COLLECTION)
           .filterBounds(geom)
           .filterDate(start, end)
           .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", config.MAX_CLOUDY_PERCENT))
           .select(config.S2_BANDS + ["SCL"])
           .map(_mask_clouds)
           .select(config.S2_BANDS))
    return col.median().multiply(0.0001), col.size()


def compute_indices(img):
    """Return an image with one band per index key in config.INDICES.

    NOTE: SI and SMI use common textbook formulas. If your gee_processing.py uses
    different ones, change them here (only these two lines).
    """
    blue, green, red = img.select("B2"), img.select("B3"), img.select("B4")
    re1, nir = img.select("B5"), img.select("B8")
    swir1, swir2 = img.select("B11"), img.select("B12")

    bands = {
        "EVI": nir.subtract(red).multiply(2.5).divide(
            nir.add(red.multiply(6)).subtract(blue.multiply(7.5)).add(1)),
        "GNDVI": nir.subtract(green).divide(nir.add(green)),
        "NDMI": nir.subtract(swir1).divide(nir.add(swir1)),
        "NDVI": nir.subtract(red).divide(nir.add(red)),
        "NDRE": nir.subtract(re1).divide(nir.add(re1)),
        "SI": green.multiply(red).sqrt(),
        "SMI": swir1.subtract(swir2).divide(swir1.add(swir2)),
        "SAVI": nir.subtract(red).multiply(1.5).divide(nir.add(red).add(0.5)),
        "NDWI": green.subtract(nir).divide(green.add(nir)),
    }
    return ee.Image.cat([bands[i["key"]].rename(i["key"]) for i in config.INDICES])


# --------------------------------------------------------------------------
# Regions
# --------------------------------------------------------------------------
def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_") or "region"


def region_fc(spec):
    fc = ee.FeatureCollection(spec["asset"])
    flt = spec.get("filter")
    if flt:
        fc = fc.filter(ee.Filter.eq(flt["field"], flt["value"]))
    return fc


def district_field(fc):
    field = config.DISTRICT_FIELD
    if field is None:
        return None
    if field != "auto":
        return field
    props = [p for p in ee.Feature(fc.first()).propertyNames().getInfo()
             if not p.startswith("system:")]
    lower = {p.lower(): p for p in props}
    for cand in ("district", "dist_name", "dtname", "dist_nm", "district_n",
                 "districtname", "name", "dist", "nam"):
        if cand in lower:
            return lower[cand]
    print(f"  ! Could not guess district column. Columns are: {props}. "
          f"Set DISTRICT_FIELD in config.py.")
    return None


def build_regions(with_districts):
    """Return {display name: ee.Geometry/FeatureCollection-backed dict}."""
    regions = {}
    for name, spec in config.REGIONS.items():
        regions[name] = {"fc": region_fc(spec)}
    if with_districts:
        base = region_fc(next(iter(config.REGIONS.values())))
        field = district_field(base)
        if field:
            names = sorted(n for n in base.aggregate_array(field).distinct().getInfo() if n)
            for n in names:
                regions[str(n)] = {"fc": base.filter(ee.Filter.eq(field, n))}
            print(f"  + {len(names)} districts from column '{field}'")
    return regions


# --------------------------------------------------------------------------
# Download one PNG
# --------------------------------------------------------------------------
def download_png(image, bounds, path, retries=4):
    params = {
        "region": bounds,
        "dimensions": config.IMAGE_DIMENSION,
        "format": "png",
    }
    last = None
    for attempt in range(1, retries + 1):
        try:
            url = image.getThumbURL(params)
            r = requests.get(url, timeout=300)
            r.raise_for_status()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(r.content)
            return
        except Exception as e:  # noqa: BLE001
            last = e
            wait = 5 * attempt
            print(f"    retry {attempt}/{retries} in {wait}s ({str(e)[:90]})")
            time.sleep(wait)
    raise RuntimeError(f"Failed: {path} ({last})")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key-file", help="service account JSON key (or env GEE_KEY_FILE)")
    ap.add_argument("--districts", action="store_true", help="also render each district")
    ap.add_argument("--months", type=int, nargs="*", help="subset of months, e.g. --months 8 9")
    ap.add_argument("--regions", nargs="*", help="subset of region names")
    ap.add_argument("--skip-existing", action="store_true")
    args = ap.parse_args()

    init_ee(args.key_file)

    out = Path(config.OUTPUT_DIR)
    img_dir = out / "images"
    months = args.months or config.AVAILABLE_MONTHS

    print("Loading regions ...")
    regions = build_regions(args.districts)
    if args.regions:
        regions = {k: v for k, v in regions.items() if k in args.regions}
    if not regions:
        sys.exit("No regions to render.")

    manifest_path = out / "data.json"
    old = {}
    if manifest_path.exists():
        try:
            old = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            old = {}

    for rname, rinfo in regions.items():
        geom = rinfo["fc"].geometry()
        bounds = geom.bounds()
        rslug = slug(rname)
        print(f"\n=== {rname} ===")
        for m in months:
            mm = f"{m:02d}"
            comp, n_scenes = monthly_composite(geom, m)
            idx_img = compute_indices(comp)
            print(f"-- {calendar.month_name[m]} {config.YEAR}  (scenes: {n_scenes.getInfo()})")
            for ind in config.INDICES:
                path = img_dir / rslug / mm / f"{ind['key']}.png"
                if args.skip_existing and path.exists():
                    print(f"   {ind['key']}: exists, skipped")
                    continue
                vis = (idx_img.select(ind["key"])
                       .visualize(min=ind["min"], max=ind["max"], palette=config.PALETTE)
                       .clip(geom))
                t0 = time.time()
                download_png(vis, bounds, path)
                print(f"   {ind['key']}: ok ({time.time() - t0:.0f}s)")

    # ---- manifest (merge with previous run so partial runs keep older data) ----
    reg_list = {r["slug"]: r for r in old.get("regions", [])}
    for rname in regions:
        reg_list[slug(rname)] = {"slug": slug(rname), "name": rname}
    ordered = sorted(reg_list.values(),
                     key=lambda r: (r["name"] != config.DEFAULT_REGION, r["name"]))

    month_nums = sorted(set(old.get("monthNumbers", [])) | set(months))
    manifest = {
        "title": config.PAGE_TITLE,
        "footer": config.FOOTER_TEXT,
        "year": config.YEAR,
        "rotationSeconds": config.ROTATION_SECONDS,
        "defaultRegion": slug(config.DEFAULT_REGION),
        "monthNumbers": month_nums,
        "months": [{"value": f"{m:02d}", "label": f"{calendar.month_name[m]} {config.YEAR}"}
                   for m in month_nums],
        "regions": ordered,
        "indices": [{"key": i["key"], "name": i["name"]} for i in config.INDICES],
        "palette": ["#" + c for c in config.PALETTE],
    }
    out.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nDone. Wrote {manifest_path}. Deploy the '{out}' folder to Netlify.")


if __name__ == "__main__":
    main()
