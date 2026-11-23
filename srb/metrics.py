"""Métricas desde el CSV del GT: media, desviación estándar y TPM por operación.
   python metrics.py [metrics_out/gt_metrics.csv]"""
import csv
import statistics as st
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "metrics_out/gt_metrics.csv"
rows = list(csv.DictReader(open(path)))
if not rows:
    sys.exit("CSV vacío")
t0 = min(float(r["t_in"]) for r in rows)
t1 = max(float(r["t_out"]) for r in rows)
minutos = max((t1 - t0) / 60, 1e-9)
for op in ("consulta", "reserva"):
    lat = [float(r["latency_ms"]) for r in rows if r["op"] == op]
    if len(lat) > 1:
        print(f"{op:9} n={len(lat):5} media={st.mean(lat):8.2f} ms  "
              f"desv={st.stdev(lat):8.2f} ms  TPM={len(lat) / minutos:7.1f}")
