"""Gestor de Transacciones: ROUTER (clientes) <-> DEALER (RMC) + PUSH (cancelaciones).
   Registra timestamps por petición en un CSV para las métricas de la Tabla 1."""
import csv
import json
import os
import time
import zmq
from common.config import load_config
from common.log import get_logger

log = get_logger("GT")


def main():
    cfg = load_config()
    ctx = zmq.Context()
    fe = ctx.socket(zmq.ROUTER)
    fe.bind(cfg["gt"]["frontend_bind"])
    be = ctx.socket(zmq.DEALER)
    be.bind(cfg["gt"]["backend_bind"])
    push = ctx.socket(zmq.PUSH)          # canal asíncrono hacia cancelación
    push.connect(cfg["cancel"]["connect"])

    path = cfg["gt"]["metrics_csv"]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    f = open(path, "w", newline="")
    w = csv.writer(f)
    w.writerow(["request_id", "op", "t_in", "t_out", "latency_ms", "status"])

    def record(rid, op, t_in, status):
        t_out = time.time()
        w.writerow([rid, op, f"{t_in:.6f}", f"{t_out:.6f}", f"{(t_out - t_in) * 1000:.3f}", status])
        f.flush()

    poller = zmq.Poller()
    poller.register(fe, zmq.POLLIN)
    poller.register(be, zmq.POLLIN)
    pending = {}                          # request_id -> (op, t_in)
    log.info("frontend=%s backend=%s", cfg["gt"]["frontend_bind"], cfg["gt"]["backend_bind"])

    while True:
        socks = dict(poller.poll(1000))
        if fe in socks:
            frames = fe.recv_multipart()  # [client_id, b'', payload]
            t_in = time.time()
            m = json.loads(frames[-1])
            rid, op = m["request_id"], m["op"]
            if op == "cancelacion":       # canal asíncrono: ack inmediato + PUSH
                push.send_json(m)
                frames[-1] = json.dumps({"request_id": rid, "status": "aceptada"}).encode()
                fe.send_multipart(frames)
                record(rid, op, t_in, "aceptada")
                log.info("cancelacion %s aceptada (asíncrona)", rid[:8])
            elif op in ("consulta", "reserva", "modificacion"):   # canal síncrono hacia RMC
                pending[rid] = (op, t_in)
                be.send_multipart(frames)
            else:
                frames[-1] = json.dumps({"request_id": rid, "status": "error",
                                         "motivo": f"op desconocida: {op}"}).encode()
                fe.send_multipart(frames)
        if be in socks:
            frames = be.recv_multipart()
            rep = json.loads(frames[-1])
            fe.send_multipart(frames)     # el envelope del cliente viaja intacto
            op, t_in = pending.pop(rep["request_id"], ("?", time.time()))
            record(rep["request_id"], op, t_in, rep["status"])
            log.info("%s %s -> %s", op, rep["request_id"][:8], rep["status"])


if __name__ == "__main__":
    main()