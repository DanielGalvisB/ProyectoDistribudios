"""Prueba end-to-end de cancelación asíncrona y notificación al cliente.
Uso:
  python -m client.cancel_notify_test --gt tcp://192.168.20.151:5555 --my-ip 192.168.20.89 --port 5581 --asientos 2"""
import argparse
import json
import socket
import uuid
import zmq
from common.config import load_config


def detectar_ip_local(destino_ip):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((destino_ip, 80))
        return s.getsockname()[0]
    finally:
        s.close()


def main():
    cfg = load_config()
    ap = argparse.ArgumentParser()
    ap.add_argument("--gt", default=None, help="Endpoint del GT, ej tcp://192.168.20.151:5555")
    ap.add_argument("--my-ip", default=None, help="IP de esta máquina alcanzable por el servicio de cancelación")
    ap.add_argument("--port", type=int, default=5581, help="Puerto local PULL para recibir notificaciones")
    ap.add_argument("--evento", default="E1")
    ap.add_argument("--ocurrencia", type=int, default=1)
    ap.add_argument("--asientos", type=int, default=2)
    ap.add_argument("--wait-sec", type=float, default=5.0)
    args = ap.parse_args()

    gt_url = args.gt or cfg["gt"]["frontend_connect"]
    host_destino = gt_url.replace("tcp://", "").split(":")[0]
    my_ip = args.my_ip or detectar_ip_local(host_destino)
    notify_url = f"tcp://{my_ip}:{args.port}"

    ctx = zmq.Context()
    pull_notif = ctx.socket(zmq.PULL)
    pull_notif.bind(f"tcp://*:{args.port}")

    req = ctx.socket(zmq.REQ)
    req.setsockopt(zmq.LINGER, 0)
    req.connect(gt_url)

    res_req = {
        "op": "reserva",
        "request_id": str(uuid.uuid4()),
        "cliente_id": "C_NOTIF",
        "evento_id": args.evento,
        "ocurrencia": args.ocurrencia,
        "asientos": args.asientos,
    }
    req.send_json(res_req)
    res_rep = req.recv_json()
    print("1) Respuesta reserva:", res_rep)
    if res_rep.get("status") != "ok":
        return

    cancel_req_id = str(uuid.uuid4())
    can_req = {
        "op": "cancelacion",
        "request_id": cancel_req_id,
        "reserva_id": res_rep["reserva_id"],
        "notify": notify_url,
    }
    req.send_json(can_req)
    can_rep = req.recv_json()
    print("2) Respuesta inmediata GT (cancelacion):", can_rep)

    poller = zmq.Poller()
    poller.register(pull_notif, zmq.POLLIN)
    socks = dict(poller.poll(int(args.wait_sec * 1000)))
    if pull_notif in socks:
        notif_msg = json.loads(pull_notif.recv())
        print("3) Notificacion recibida:", notif_msg)
    else:
        print("3) No llego notificacion dentro del tiempo de espera; revisa ruta/puerto", notify_url)


if __name__ == "__main__":
    main()