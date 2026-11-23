"""Carga inicial. Por defecto: 50 eventos (20 con 2 ocurrencias), 100 asientos.
   python -m persistence.seed                   # caso por defecto
   python -m persistence.seed --file caso.json  # caso del profesor"""
import argparse
from common.config import load_config
from persistence import db

ap = argparse.ArgumentParser()
ap.add_argument("--file")
ap.add_argument("--mes", default="2026-11")
a = ap.parse_args()
conn = db.connect(load_config()["persistence"]["db_path"])
if a.file:
    db.load_seed_file(conn, a.file)
else:
    db.load_seed(conn, db.seed_default(mes=a.mes))
print("BD cargada.")
