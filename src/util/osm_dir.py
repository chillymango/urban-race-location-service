import os


DATA_DIR = os.environ.get('DATA_DIR', os.path.join(os.getcwd(), "data"))
OSM_DIR = os.path.join(DATA_DIR, "osm_regions")
if not os.path.exists(DATA_DIR) or not os.path.exists(OSM_DIR):
    raise OSError(f"No data directory found at {DATA_DIR} or {OSM_DIR}")
