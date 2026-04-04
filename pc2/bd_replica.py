"""
bd_replica.py
Base de datos réplica — PC2.

Recibe eventos del servicio de analítica vía PUSH/PULL y los
persiste en una BD SQLite local. Actúa como backup ante falla de PC3.

También responde al health check desde analítica si PC3 falla
y este nodo asume el rol de BD principal temporalmente.

Uso:
    python bd_replica.py
"""

import zmq
import json
import sqlite3
import logging
import sys
import os
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, '..'))

from config.loader import cargar_config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [BD-Réplica] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('BDReplica')


class BDReplica:
    """
    Servicio de base de datos réplica en PC2.
    Mantiene sincronía con BD principal y puede asumir su rol
    ante una falla de PC3.
    """

    def __init__(self):
        self.config  = cargar_config()
        self.context = zmq.Context()

        db_dir  = os.path.join(BASE_DIR, '..', 'db')
        db_name = self.config['base_datos']['nombre_replica']
        self.db_path = os.path.join(db_dir, db_name)

        self.pull_socket       = None
        self.health_rep_socket = None

    def iniciar(self):
        """Configura sockets e inicia los listeners."""
        p   = self.config['red']['puertos']
        pc3 = self.config['red']['pc3_ip']

        # PULL — recibe eventos del servicio de analítica
        self.pull_socket = self.context.socket(zmq.PULL)
        self.pull_socket.bind(f"tcp://*:{p['analitica_push_replica']}")
        logger.info(f"Escuchando en puerto :{p['analitica_push_replica']}")

        # Verificar que la BD existe
        if not os.path.exists(self.db_path):
            logger.error(
                f"BD réplica no encontrada en {self.db_path}. "
                "Ejecute primero: python db/init_db.py --solo-replica"
            )
            sys.exit(1)

        logger.info(f"BD réplica: {self.db_path}")
        self._escuchar()

    def _escuchar(self):
        """Loop principal: recibe y persiste eventos."""
        logger.info("Réplica lista. Esperando eventos...")
        try:
            while True:
                mensaje = self.pull_socket.recv_string()
                try:
                    datos = json.loads(mensaje)
                    self._persistir(datos)
                except json.JSONDecodeError as e:
                    logger.error(f"JSON inválido: {e} | mensaje: {mensaje[:80]}")

        except KeyboardInterrupt:
            logger.info("Servicio detenido.")
        finally:
            self._cerrar()

    def _persistir(self, datos: dict):
        """
        Persiste un evento en la BD réplica según su tipo.
        Reutiliza la misma lógica que la BD principal.
        """
        tipo = datos.get('tipo_sensor') or datos.get('tipo', '')

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        ts = datos.get('timestamp') or datos.get('timestamp_fin') or self._ts()

        try:
            if tipo in ('camara', 'espira_inductiva', 'gps'):
                cursor.execute(
                    """INSERT INTO eventos_sensores
                       (sensor_id, tipo_sensor, interseccion, timestamp,
                        volumen, velocidad_promedio,
                        vehiculos_contados, intervalo_segundos,
                        timestamp_inicio, timestamp_fin, nivel_congestion)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        datos.get('sensor_id'),
                        datos.get('tipo_sensor'),
                        datos.get('interseccion'),
                        ts,
                        datos.get('volumen'),
                        datos.get('velocidad_promedio'),
                        datos.get('vehiculos_contados'),
                        datos.get('intervalo_segundos'),
                        datos.get('timestamp_inicio'),
                        datos.get('timestamp_fin'),
                        datos.get('nivel_congestion')
                    )
                )
                logger.debug(
                    f"Evento guardado [{tipo}] — {datos.get('interseccion')}"
                )

            elif tipo == 'decision':
                cursor.execute(
                    """INSERT INTO decisiones_analitica
                       (interseccion, condicion, accion, timestamp, origen)
                       VALUES (?,?,?,?,?)""",
                    (
                        datos.get('interseccion'),
                        datos.get('condicion'),
                        datos.get('accion'),
                        ts,
                        datos.get('origen', 'automatico')
                    )
                )
                logger.info(
                    f"Decisión guardada — "
                    f"{datos.get('interseccion')} | {datos.get('condicion')}"
                )

            conn.commit()

        except sqlite3.Error as e:
            logger.error(f"Error al persistir en réplica: {e}")
            conn.rollback()
        finally:
            conn.close()

    def _ts(self) -> str:
        return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    def _cerrar(self):
        if self.pull_socket:
            self.pull_socket.close()
        self.context.term()
        logger.info("Recursos liberados.")


# ── Punto de entrada ──────────────────────────────────────────────────────────

if __name__ == '__main__':
    servicio = BDReplica()
    servicio.iniciar()
