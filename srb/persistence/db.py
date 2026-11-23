"""Acceso a SQLite y operaciones CRUD del servicio de persistencia."""
import json
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS eventos (
    evento_id  TEXT NOT NULL,
    ocurrencia INTEGER NOT NULL,
    mes        TEXT NOT NULL,          -- 'YYYY-MM'
    fecha      TEXT NOT NULL,
    libres     INTEGER NOT NULL CHECK (libres >= 0),
    ocupados   INTEGER NOT NULL CHECK (ocupados >= 0),
    PRIMARY KEY (evento_id, ocurrencia)
);
CREATE TABLE IF NOT EXISTS reservas (
    reserva_id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id TEXT,
    evento_id  TEXT NOT NULL,
    ocurrencia INTEGER NOT NULL,
    asientos   INTEGER NOT NULL,
    estado     TEXT NOT NULL DEFAULT 'activa'   -- activa | cancelada
);
"""


def connect(path):
    conn = sqlite3.connect(path, isolation_level=None)  # autocommit; BEGIN manual
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def seed_default(mes="2026-11", n_eventos=50, n_dobles=20, asientos=100):
    """50 eventos; 20 con 2 ocurrencias; 100 asientos por ocurrencia."""
    eventos = []
    for i in range(1, n_eventos + 1):
        ocurrs = [{"fecha": f"{mes}-{(i % 14) + 1:02d}", "asientos": asientos}]
        if i <= n_dobles:
            ocurrs.append({"fecha": f"{mes}-{(i % 14) + 15:02d}", "asientos": asientos})
        eventos.append({"evento_id": f"E{i}", "ocurrencias": ocurrs})
    return {"mes": mes, "eventos": eventos}


def load_seed(conn, data):
    """Reinicia la BD y carga el caso. `data` = dict (ver seed_default o JSON del profesor)."""
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("DELETE FROM reservas")
    conn.execute("DELETE FROM eventos")
    conn.execute("DELETE FROM sqlite_sequence WHERE name='reservas'")
    for ev in data["eventos"]:
        for n, oc in enumerate(ev["ocurrencias"], start=1):
            conn.execute(
                "INSERT INTO eventos VALUES (?,?,?,?,?,?)",
                (ev["evento_id"], n, data["mes"], oc["fecha"],
                 oc["asientos"] - oc.get("ocupados", 0), oc.get("ocupados", 0)))
    conn.execute("COMMIT")


def load_seed_file(conn, path):
    with open(path) as f:
        load_seed(conn, json.load(f))


# ---------- operaciones ----------
def consultar(conn, mes):
    rows = conn.execute(
        "SELECT evento_id, ocurrencia, fecha, libres, ocupados FROM eventos WHERE mes=? "
        "ORDER BY CAST(SUBSTR(evento_id,2) AS INTEGER), ocurrencia", (mes,)).fetchall()
    return {"status": "ok", "eventos": [
        {"evento_id": r[0], "ocurrencia": r[1], "fecha": r[2], "libres": r[3], "ocupados": r[4]}
        for r in rows]}


def disponibilidad(conn, evento_id, ocurrencia):
    r = conn.execute("SELECT libres, fecha FROM eventos WHERE evento_id=? AND ocurrencia=?",
                     (evento_id, ocurrencia)).fetchone()
    if r is None:
        return {"status": "rechazo", "motivo": "evento inexistente"}
    return {"status": "ok", "libres": r[0], "fecha": r[1]}


def reservar(conn, evento_id, ocurrencia, asientos, cliente_id=None):
    """Reserva atómica: el UPDATE condicional evita el doble booking."""
    if asientos <= 0:
        return {"status": "rechazo", "motivo": "numero de asientos invalido"}
    conn.execute("BEGIN IMMEDIATE")
    try:
        cur = conn.execute(
            "UPDATE eventos SET libres=libres-?, ocupados=ocupados+? "
            "WHERE evento_id=? AND ocurrencia=? AND libres>=?",
            (asientos, asientos, evento_id, ocurrencia, asientos))
        if cur.rowcount == 0:
            conn.execute("ROLLBACK")
            return {"status": "rechazo", "motivo": "sin disponibilidad o evento inexistente"}
        cur = conn.execute(
            "INSERT INTO reservas(cliente_id, evento_id, ocurrencia, asientos) VALUES (?,?,?,?)",
            (cliente_id, evento_id, ocurrencia, asientos))
        reserva_id = cur.lastrowid
        conn.execute("COMMIT")
        return {"status": "ok", "reserva_id": reserva_id}
    except Exception:
        conn.execute("ROLLBACK")
        raise


def modificar(conn, reserva_id, nueva_ocurrencia=None, nuevos_asientos=None):
    """Modifica una reserva activa: cambia asientos y/o ocurrencia del mismo evento y mes."""
    if nuevos_asientos is not None and nuevos_asientos <= 0:
        return {"status": "rechazo", "motivo": "numero de asientos invalido"}
    if nueva_ocurrencia is None and nuevos_asientos is None:
        return {"status": "rechazo", "motivo": "sin cambios solicitados"}

    conn.execute("BEGIN IMMEDIATE")
    try:
        res = conn.execute(
            "SELECT evento_id, ocurrencia, asientos, estado FROM reservas WHERE reserva_id=?",
            (reserva_id,),
        ).fetchone()
        if res is None or res[3] != "activa":
            conn.execute("ROLLBACK")
            return {"status": "rechazo", "motivo": "reserva inexistente o no activa"}

        evento_id, occ_actual, as_actual, _ = res
        occ_objetivo = nueva_ocurrencia if nueva_ocurrencia is not None else occ_actual
        as_objetivo = nuevos_asientos if nuevos_asientos is not None else as_actual

        ev_actual = conn.execute(
            "SELECT mes FROM eventos WHERE evento_id=? AND ocurrencia=?",
            (evento_id, occ_actual),
        ).fetchone()
        ev_objetivo = conn.execute(
            "SELECT mes, libres FROM eventos WHERE evento_id=? AND ocurrencia=?",
            (evento_id, occ_objetivo),
        ).fetchone()

        if ev_actual is None or ev_objetivo is None:
            conn.execute("ROLLBACK")
            return {"status": "rechazo", "motivo": "ocurrencia inexistente"}

        if ev_actual[0] != ev_objetivo[0]:
            conn.execute("ROLLBACK")
            return {"status": "rechazo", "motivo": "solo se permite modificar dentro del mismo mes"}

        if occ_objetivo == occ_actual:
            diff = as_objetivo - as_actual
            if diff == 0:
                conn.execute("COMMIT")
                return {
                    "status": "ok",
                    "reserva_id": reserva_id,
                    "evento_id": evento_id,
                    "ocurrencia": occ_objetivo,
                    "asientos": as_objetivo,
                }
            if diff > 0:
                cur = conn.execute(
                    "UPDATE eventos SET libres=libres-?, ocupados=ocupados+? "
                    "WHERE evento_id=? AND ocurrencia=? AND libres>=?",
                    (diff, diff, evento_id, occ_actual, diff),
                )
                if cur.rowcount == 0:
                    conn.execute("ROLLBACK")
                    return {"status": "rechazo", "motivo": "asientos insuficientes"}
            else:
                lib = -diff
                conn.execute(
                    "UPDATE eventos SET libres=libres+?, ocupados=ocupados-? "
                    "WHERE evento_id=? AND ocurrencia=?",
                    (lib, lib, evento_id, occ_actual),
                )
        else:
            cur = conn.execute(
                "UPDATE eventos SET libres=libres-?, ocupados=ocupados+? "
                "WHERE evento_id=? AND ocurrencia=? AND libres>=?",
                (as_objetivo, as_objetivo, evento_id, occ_objetivo, as_objetivo),
            )
            if cur.rowcount == 0:
                conn.execute("ROLLBACK")
                return {"status": "rechazo", "motivo": "sin disponibilidad en la ocurrencia destino"}
            conn.execute(
                "UPDATE eventos SET libres=libres+?, ocupados=ocupados-? "
                "WHERE evento_id=? AND ocurrencia=?",
                (as_actual, as_actual, evento_id, occ_actual),
            )

        conn.execute(
            "UPDATE reservas SET ocurrencia=?, asientos=? WHERE reserva_id=?",
            (occ_objetivo, as_objetivo, reserva_id),
        )
        conn.execute("COMMIT")
        return {
            "status": "ok",
            "reserva_id": reserva_id,
            "evento_id": evento_id,
            "ocurrencia": occ_objetivo,
            "asientos": as_objetivo,
        }
    except Exception:
        conn.execute("ROLLBACK")
        raise


def liberar(conn, reserva_id):
    """Cancelación: libera los asientos de una reserva activa."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        r = conn.execute("SELECT evento_id, ocurrencia, asientos FROM reservas "
                         "WHERE reserva_id=? AND estado='activa'", (reserva_id,)).fetchone()
        if r is None:
            conn.execute("ROLLBACK")
            return {"status": "rechazo", "motivo": "reserva inexistente o ya cancelada"}
        conn.execute("UPDATE eventos SET libres=libres+?, ocupados=ocupados-? "
                     "WHERE evento_id=? AND ocurrencia=?", (r[2], r[2], r[0], r[1]))
        conn.execute("UPDATE reservas SET estado='cancelada' WHERE reserva_id=?", (reserva_id,))
        conn.execute("COMMIT")
        return {"status": "ok", "liberados": r[2]}
    except Exception:
        conn.execute("ROLLBACK")
        raise