"""
init_db.py
Inicializa la base de datos principal (PC3) y la réplica (PC2).
Ejecutar una vez antes de levantar el sistema.

Uso:
    python init_db.py                    # crea ambas BDs en ./db/
    python init_db.py --solo-replica     # solo réplica (para PC2)
    python init_db.py --solo-principal   # solo principal (para PC3)
"""

import sqlite3
import os
import sys
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, '..', 'config', 'config.json')
SCHEMA_PATH = os.path.join(BASE_DIR, 'schema.sql')


def cargar_config():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def inicializar_bd(ruta: str, nombre: str):
    """Crea la BD en la ruta indicada aplicando el schema."""
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    conn = sqlite3.connect(ruta)
    cursor = conn.cursor()

    with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
        schema = f.read()

    cursor.executescript(schema)

    # Poblar estado inicial de semáforos (todos en ROJO al arranque)
    config = cargar_config()
    filas = config['ciudad']['filas']
    columnas = config['ciudad']['columnas']
    from datetime import datetime, timezone

    ts = datetime.now(timezone.utc).isoformat()
    for fila in filas:
        for col in columnas:
            interseccion = f"INT_{fila}{col}"
            cursor.execute(
                """INSERT OR IGNORE INTO estado_semaforos
                   (interseccion, estado, razon, timestamp)
                   VALUES (?, 'ROJO', 'inicio_sistema', ?)""",
                (interseccion, ts)
            )

    conn.commit()
    conn.close()
    print(f"[OK] BD '{nombre}' inicializada en: {ruta}")


def main():
    config = cargar_config()
    db_cfg = config['base_datos']

    db_dir = os.path.join(BASE_DIR, '..', 'db')

    solo_replica    = '--solo-replica'    in sys.argv
    solo_principal  = '--solo-principal'  in sys.argv

    if solo_replica:
        ruta = os.path.join(db_dir, db_cfg['nombre_replica'])
        inicializar_bd(ruta, db_cfg['nombre_replica'])
    elif solo_principal:
        ruta = os.path.join(db_dir, db_cfg['nombre_principal'])
        inicializar_bd(ruta, db_cfg['nombre_principal'])
    else:
        ruta_p = os.path.join(db_dir, db_cfg['nombre_principal'])
        ruta_r = os.path.join(db_dir, db_cfg['nombre_replica'])
        inicializar_bd(ruta_p, db_cfg['nombre_principal'])
        inicializar_bd(ruta_r, db_cfg['nombre_replica'])

    print("[OK] Inicialización completa.")


if __name__ == '__main__':
    main()
