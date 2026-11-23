"""Muestra el estado de la BD (para la sustentación).  python -m persistence.show [--solo-cambios]"""
import argparse
from common.config import load_config
from persistence import db

ap = argparse.ArgumentParser()
ap.add_argument("--solo-cambios", action="store_true", help="solo eventos con asientos ocupados")
a = ap.parse_args()
conn = db.connect(load_config()["persistence"]["db_path"])
print(f"{'evento':8}{'ocurr':6}{'fecha':12}{'libres':8}{'ocupados':8}")
for r in conn.execute("SELECT evento_id, ocurrencia, fecha, libres, ocupados FROM eventos "
                      "ORDER BY CAST(SUBSTR(evento_id,2) AS INTEGER), ocurrencia"):
    if a.solo_cambios and r[4] == 0:
        continue
    print(f"{r[0]:8}{r[1]:<6}{r[2]:12}{r[3]:<8}{r[4]:<8}")
tot = conn.execute("SELECT COUNT(*), COALESCE(SUM(asientos),0) FROM reservas WHERE estado='activa'").fetchone()
print(f"\nReservas activas: {tot[0]} ({tot[1]} asientos)")
