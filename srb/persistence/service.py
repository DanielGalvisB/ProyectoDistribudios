"""Servicio de Persistencia: REP sobre SQLite.  python -m persistence.service"""
import json
import zmq
from common.config import load_config
from common.log import get_logger
from persistence import db

log = get_logger("PERSIST")


def handle(conn, m):
    op = m["op"]
    if op == "consultar":
        return db.consultar(conn, m["mes"])
    if op == "disponibilidad":
        return db.disponibilidad(conn, m["evento_id"], m["ocurrencia"])
    if op == "reservar":
        return db.reservar(conn, m["evento_id"], m["ocurrencia"], m["asientos"], m.get("cliente_id"))
    if op == "modificar":
        return db.modificar(conn, m["reserva_id"], m.get("nueva_ocurrencia"), m.get("nuevos_asientos"))
    if op == "liberar":
        return db.liberar(conn, m["reserva_id"])
    return {"status": "error", "motivo": f"op desconocida: {op}"}


def main():
    cfg = load_config()
    conn = db.connect(cfg["persistence"]["db_path"])
    sock = zmq.Context().socket(zmq.REP)
    sock.bind(cfg["persistence"]["bind"])
    log.info("escuchando en %s (db=%s)", cfg["persistence"]["bind"], cfg["persistence"]["db_path"])
    while True:
        m = json.loads(sock.recv())
        try:
            rep = handle(conn, m)
        except Exception as e:  # nunca dejar el REP sin responder
            rep = {"status": "error", "motivo": str(e)}
        log.info("%s %s -> %s", m["op"], {k: v for k, v in m.items() if k != "op"},
                 rep["status"] + (f" ({rep['motivo']})" if "motivo" in rep else ""))
        sock.send_json(rep)


if __name__ == "__main__":
    main()
