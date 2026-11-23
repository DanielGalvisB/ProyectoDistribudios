# SRB – Primera entrega (arquitectura base)

Python 3.10+ · ZeroMQ (pyzmq) · SQLite. Solo consulta y reserva (+ cancelación mínima).

## Instalación
    pip install -r requirements.txt

## Ejecución (un terminal por proceso, desde la raíz `srb/`)
    python -m persistence.seed            # caso por defecto (o --file caso_profesor.json)
    python -m persistence.service         # 1) persistencia
    python -m rmc.service                 # 2) RMC
    python -m cancel.service              # 3) cancelación (opcional en esta entrega)
    python -m gt.service                  # 4) gestor de transacciones
    python -m client.load --clients 3 --solo-consulta 2 --rpm 30 --duration 120
    python metrics.py                     # métricas medidas en el GT
    python -m persistence.show            # estado de la BD (antes/después)

## Despliegue en 3 máquinas
Edita las IPs `*_connect` de `config.yaml`:
- Máquina A: clientes · Máquina B: GT + RMC + cancelación · Máquina C: persistencia (+ BD).
Abre los puertos 5555, 5556, 5560 y 5570.

## Formato del caso de prueba (JSON)
    {"mes": "2026-11", "eventos": [
       {"evento_id": "E1", "ocurrencias": [{"fecha": "2026-11-03", "asientos": 100},
                                           {"fecha": "2026-11-17", "asientos": 100}]}]}
