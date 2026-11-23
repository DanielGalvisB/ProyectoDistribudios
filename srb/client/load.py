"""Generador de carga con N clientes (hilos REQ), parametrizable.
Ejemplos (Tabla 1):
  python -m client.load --clients 3 --solo-consulta 2 --rpm 30 --duration 120
  python -m client.load --clients 5 --solo-consulta 3 --rpm 30 --duration 120
  python -m client.load --clients 8 --solo-consulta 4 --rpm 30 --duration 120
Los clientes "mixtos" hacen --pct-consulta % consultas y el resto reservas/modificaciones."""
import argparse
import csv
import random
import statistics as st
import threading
import time
import uuid
import zmq
from common.config import load_config


def client_loop(cid, cfg, args, solo_consulta, results, stop_at):
    ctx = zmq.Context.instance()
    endpoint = args.gt or cfg["gt"]["frontend_connect"]
    timeout = cfg["timeouts_ms"]["client"]

    def new_sock():
        s = ctx.socket(zmq.REQ)
        s.setsockopt(zmq.LINGER, 0)
        s.connect(endpoint)
        return s

    sock = new_sock()
    rng = random.Random(args.seed + cid)
    interval = 60.0 / args.rpm
    next_t = time.monotonic()
    reservas_activas = []

    while time.monotonic() < stop_at:
        if solo_consulta or rng.random() * 100 < args.pct_consulta:
            op, msg = "consulta", {"mes": args.mes}
        else:
            if reservas_activas and rng.random() < args.pct_modificacion:
                op = "modificacion"
                rid_reserva = rng.choice(reservas_activas)
                if rng.random() < 0.5:
                    msg = {"reserva_id": rid_reserva, "nuevos_asientos": rng.randint(1, args.max_asientos)}
                else:
                    msg = {"reserva_id": rid_reserva, "nueva_ocurrencia": rng.choice([1, 2])}
            else:
                op = "reserva"
                ev_num = rng.randint(1, args.eventos)
                occ = rng.choice([1, 2]) if ev_num <= 20 else 1
                msg = {"evento_id": f"E{ev_num}", "ocurrencia": occ,
                       "asientos": rng.randint(1, args.max_asientos)}

        msg.update({"op": op, "request_id": str(uuid.uuid4()), "cliente_id": f"C{cid}"})
        t0 = time.monotonic()
        sock.send_json(msg)
        if sock.poll(timeout):
            rep = sock.recv_json()
            status = rep["status"]
            if op == "reserva" and status == "ok" and "reserva_id" in rep:
                reservas_activas.append(rep["reserva_id"])
        else:
            sock.close()
            sock = new_sock()
            status = "timeout"
        results.append((f"C{cid}", op, (time.monotonic() - t0) * 1000, status))
        next_t += interval
        time.sleep(max(0, next_t - time.monotonic()))


def main():
    cfg = load_config()
    ap = argparse.ArgumentParser()
    ap.add_argument("--clients", type=int, default=3)
    ap.add_argument("--solo-consulta", type=int, default=2, help="cuántos clientes solo consultan")
    ap.add_argument("--rpm", type=int, default=30, help="solicitudes por minuto por cliente (>=20)")
    ap.add_argument("--pct-consulta", type=float, default=50, help="%% consultas en clientes mixtos")
    ap.add_argument("--pct-modificacion", type=float, default=0.3, help="fracción de no-consultas que son modificación")
    ap.add_argument("--duration", type=int, default=120, help="segundos")
    ap.add_argument("--mes", default="2026-11")
    ap.add_argument("--eventos", type=int, default=50)
    ap.add_argument("--max-asientos", type=int, default=4)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--gt", help="override del endpoint del GT")
    ap.add_argument("--out", default="metrics_out/client_results.csv")
    args = ap.parse_args()

    results, threads = [], []
    stop_at = time.monotonic() + args.duration
    for i in range(args.clients):
        t = threading.Thread(target=client_loop,
                             args=(i + 1, cfg, args, i < args.solo_consulta, results, stop_at))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()

    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cliente", "op", "latency_ms", "status"])
        w.writerows(results)
    print(f"\n{len(results)} solicitudes, {args.clients} clientes, {args.duration}s")
    for op in ("consulta", "reserva", "modificacion"):
        lat = [r[2] for r in results if r[1] == op]
        if len(lat) > 0:
            tpm = len(lat) / (args.duration / 60)
            desv = st.stdev(lat) if len(lat) > 1 else 0.0
            print(f"{op:12} n={len(lat):5} media={st.mean(lat):8.2f} ms  desv={desv:8.2f} ms  TPM={tpm:7.1f}")


if __name__ == "__main__":
    main()