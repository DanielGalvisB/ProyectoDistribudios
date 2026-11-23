"""Servicio de Cancelaciones y Notificaciones.
   Mensaje esperado: {op:'cancelacion', request_id, reserva_id, notify:'tcp://ip:puerto'}"""
import json
import zmq
from common.config import load_config
from common.log import get_logger

log = get_logger("CANCEL")


def new_persist_socket(ctx, endpoint):
    s = ctx.socket(zmq.REQ)
    s.setsockopt(zmq.LINGER, 0)
    s.connect(endpoint)
    return s


def call_persistence(ctx, persist, cfg, msg):
    persist.send_json(msg)
    if persist.poll(cfg["timeouts_ms"]["persistence"]):
        return persist.recv_json(), persist
    persist.close()
    return {"status": "error", "motivo": "persistencia no responde"}, new_persist_socket(
        ctx, cfg["persistence"]["connect"]
    )


def enviar_notificacion(ctx, endpoint, payload):
    s = ctx.socket(zmq.PUSH)
    s.setsockopt(zmq.LINGER, 2000)
    s.setsockopt(zmq.SNDTIMEO, 2000)
    s.connect(endpoint)
    try:
        s.send_json(payload)
        log.info("notificacion enviada a %s para req=%s (%s)", endpoint, payload["request_id"][:8], payload["status"])
    except zmq.Again:
        log.warning("cliente %s no alcanzable para notificacion req=%s", endpoint, payload["request_id"][:8])
    finally:
        s.close()


def main():
    cfg = load_config()
    ctx = zmq.Context()
    pull = ctx.socket(zmq.PULL)
    pull.bind(cfg["cancel"]["bind"])
    persist = new_persist_socket(ctx, cfg["persistence"]["connect"])
    log.info("escuchando en %s", cfg["cancel"]["bind"])

    while True:
        m = json.loads(pull.recv())
        reserva_id = m["reserva_id"]
        rep, persist = call_persistence(ctx, persist, cfg, {"op": "liberar", "reserva_id": reserva_id})
        log.info("liberar reserva %s -> %s", reserva_id, rep["status"])

        notify_url = m.get("notify")
        if notify_url:
            notif = {
                "request_id": m["request_id"],
                "reserva_id": reserva_id,
                "tipo": "notificacion",
                **rep,
            }
            enviar_notificacion(ctx, notify_url, notif)


if __name__ == "__main__":
    main()