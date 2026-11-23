"""RMC: atiende consulta / reserva / modificacion (síncronas) del GT y habla con persistencia.
   python -m rmc.service   (se pueden lanzar varias instancias: todas se conectan al DEALER del GT)"""
import json
import os
import zmq
from common.config import load_config
from common.log import get_logger

cfg = load_config()
log = get_logger(f"RMC-{os.getpid()}")
ctx = zmq.Context()


def new_persist_socket():
    s = ctx.socket(zmq.REQ)
    s.setsockopt(zmq.LINGER, 0)
    s.connect(cfg["persistence"]["connect"])
    return s


persist = new_persist_socket()


def call_persistence(msg):
    """REQ con timeout; si expira recrea el socket (patrón Lazy Pirate)."""
    global persist
    persist.send_json(msg)
    if persist.poll(cfg["timeouts_ms"]["persistence"]):
        return persist.recv_json()
    persist.close()
    persist = new_persist_socket()
    return {"status": "error", "motivo": "persistencia no responde"}


def process(m):
    rid, op = m["request_id"], m["op"]
    if op == "consulta":
        rep = call_persistence({"op": "consultar", "mes": m["mes"]})
    elif op == "reserva":
        disp = call_persistence({"op": "disponibilidad", "evento_id": m["evento_id"],
                                 "ocurrencia": m["ocurrencia"]})
        if disp["status"] != "ok":
            rep = disp
        elif disp["libres"] < m["asientos"]:
            rep = {"status": "rechazo", "motivo": "asientos insuficientes"}
        else:  # la confirmación es atómica en persistencia (evita carreras entre RMC)
            rep = call_persistence({"op": "reservar", "evento_id": m["evento_id"],
                                    "ocurrencia": m["ocurrencia"], "asientos": m["asientos"],
                                    "cliente_id": m.get("cliente_id")})
    elif op == "modificacion":
        rep = call_persistence({
            "op": "modificar",
            "reserva_id": m["reserva_id"],
            "nueva_ocurrencia": m.get("nueva_ocurrencia"),
            "nuevos_asientos": m.get("nuevos_asientos"),
        })
    else:
        rep = {"status": "error", "motivo": f"op no soportada en RMC: {op}"}
    rep["request_id"] = rid
    return rep


def main():
    sock = ctx.socket(zmq.REP)
    sock.connect(cfg["gt"]["backend_connect"])
    log.info("conectado al GT en %s", cfg["gt"]["backend_connect"])
    while True:
        m = json.loads(sock.recv())
        rep = process(m)
        log.info("%s %s -> %s", m["op"], m.get("evento_id", m.get("reserva_id", m.get("mes"))), rep["status"])
        sock.send_json(rep)


if __name__ == "__main__":
    main()