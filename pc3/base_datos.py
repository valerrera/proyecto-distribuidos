"""
base_datos.py
Base de datos principal — PC3.

Recibe eventos del servicio de analítica (PUSH/PULL) y los persiste
en SQLite. También expone un endpoint de health check (REQ/REP)
para que analítica verifique si PC3 sigue en pie.

Uso:
    python base_datos.py
"""

import zmq
import json
import sqlite3
import logging
import threading
import sys
import os
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, '..'))

from config.loader import cargar_config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [BD-Principal] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('BDPrincipal')


class BaseDatos:
    """
    Base de datos principal en PC3.
    Persiste todos los eventos del sistema y responde health checks.
    """

    def __init__(self):
        self.config  = cargar_config()
        self.context = zmq.Context()

        db_dir  = os.path.join(BASE_DIR, '..', 'db')
        db_name = self.config['base_datos']['nombre_principal']
        self.db_path = os.path.join(db_dir, db_name)

        self.pull_socket   = None
        self.health_socket = None

    def iniciar(self):
        """Configura sockets e inicia listener y health check."""
        p = self.config['red']['puertos']

        # PULL — recibe eventos de analítica
        self.pull_socket = self.context.socket(zmq.PULL)
        self.pull_socket.bind(f"tcp://*:{p['bd_principal_pull']}")

        # REP — responde PINGs del health check
        self.health_socket = self.context.socket(zmq.REP)
        self.health_socket.bind(f"tcp://*:{p['health_check']}")

        if not os.path.exists(self.db_path):
            logger.error(
                f"BD principal no encontrada en {self.db_path}. "
                "Ejecute: python db/init_db.py --solo-principal"
            )
            sys.exit(1)

        logger.info(f"BD principal: {self.db_path}")
        logger.info(f"Escuchando PULL en :{p['bd_principal_pull']}")
        logger.info(f"Health check en :{p['health_check']}")

        # Hilo para health check
        hilo_hc = threading.Thread(target=self._responder_health_check, daemon=True)
        hilo_hc.start()

        self._escuchar()

    def _escuchar(self):
        """Loop principal: recibe y persiste eventos."""
        logger.info("BD principal lista. Esperando eventos...")
        try:
            while True:
                mensaje = self.pull_socket.recv_string()
                try:
                    datos = json.loads(mensaje)
                    self._persistir(datos)
                except json.JSONDecodeError as e:
                    logger.error(f"JSON inválido: {e}")

        except KeyboardInterrupt:
            logger.info("Servicio detenido.")
        finally:
            self._cerrar()

    def _responder_health_check(self):
        """Hilo: responde PING con PONG para el health check de analítica."""
        logger.info("Health check activo.")
        while True:
            try:
                msg = self.health_socket.recv_string()
                if msg == 'PING':
                    self.health_socket.send_string('PONG')
                    logger.debug("Health check: PING recibido → PONG enviado")
            except Exception as e:
                logger.error(f"Error en health check: {e}")

    def _persistir(self, datos: dict):
        """Persiste un evento en la BD principal e imprime un resumen detallado."""
        tipo = datos.get('tipo_sensor') or datos.get('tipo', '')
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        ts = datos.get('timestamp') or datos.get('timestamp_fin') or self._ts()

        try:
            if tipo == 'camara':
                cursor.execute(
                    """INSERT INTO eventos_sensores
                       (sensor_id, tipo_sensor, interseccion, timestamp,
                        volumen, velocidad_promedio,
                        vehiculos_contados, intervalo_segundos,
                        timestamp_inicio, timestamp_fin, nivel_congestion)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        datos.get('sensor_id'),
                        tipo,
                        datos.get('interseccion'),
                        ts,
                        datos.get('volumen'),
                        datos.get('velocidad_promedio'),
                        None, None, None, None, None
                    )
                )
                logger.info(
                    f"[BD] CAMARA  | {datos.get('interseccion'):8s} | "
                    f"sensor={datos.get('sensor_id')} | "
                    f"cola={datos.get('volumen')} veh | "
                    f"vel={datos.get('velocidad_promedio')} km/h | "
                    f"ts={ts}"
                )

            elif tipo == 'espira_inductiva':
                cursor.execute(
                    """INSERT INTO eventos_sensores
                       (sensor_id, tipo_sensor, interseccion, timestamp,
                        volumen, velocidad_promedio,
                        vehiculos_contados, intervalo_segundos,
                        timestamp_inicio, timestamp_fin, nivel_congestion)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        datos.get('sensor_id'),
                        tipo,
                        datos.get('interseccion'),
                        ts,
                        None, None,
                        datos.get('vehiculos_contados'),
                        datos.get('intervalo_segundos'),
                        datos.get('timestamp_inicio'),
                        datos.get('timestamp_fin'),
                        None
                    )
                )
                logger.info(
                    f"[BD] ESPIRA  | {datos.get('interseccion'):8s} | "
                    f"sensor={datos.get('sensor_id')} | "
                    f"conteo={datos.get('vehiculos_contados')} veh | "
                    f"intervalo={datos.get('intervalo_segundos')}s | "
                    f"ts={ts}"
                )

            elif tipo == 'gps':
                cursor.execute(
                    """INSERT INTO eventos_sensores
                       (sensor_id, tipo_sensor, interseccion, timestamp,
                        volumen, velocidad_promedio,
                        vehiculos_contados, intervalo_segundos,
                        timestamp_inicio, timestamp_fin, nivel_congestion)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        datos.get('sensor_id'),
                        tipo,
                        datos.get('interseccion'),
                        ts,
                        None,
                        datos.get('velocidad_promedio'),
                        None, None, None, None,
                        datos.get('nivel_congestion')
                    )
                )
                nivel = datos.get('nivel_congestion', '?')
                nivel_fmt = (
                    f"ALTA  " if nivel == 'ALTA'   else
                    f"NORMAL" if nivel == 'NORMAL' else
                    f"BAJA  "
                )
                logger.info(
                    f"[BD] GPS     | {datos.get('interseccion'):8s} | "
                    f"sensor={datos.get('sensor_id')} | "
                    f"vel={datos.get('velocidad_promedio')} km/h | "
                    f"congestion={nivel_fmt} | "
                    f"ts={ts}"
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
                    f"[BD] DECISION| {datos.get('interseccion'):8s} | "
                    f"condicion={datos.get('condicion'):12s} | "
                    f"accion={datos.get('accion')} | "
                    f"origen={datos.get('origen', 'automatico')} | "
                    f"ts={ts}"
                )

            else:
                logger.warning(f"[BD] Tipo de evento desconocido: '{tipo}' — ignorado")
                return

            conn.commit()

        except sqlite3.Error as e:
            logger.error(f"[BD] Error al persistir [{tipo}]: {e}")
            conn.rollback()
        finally:
            conn.close()

    def _ts(self) -> str:
        return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    def _cerrar(self):
        if self.pull_socket:
            self.pull_socket.close()
        if self.health_socket:
            self.health_socket.close()
        self.context.term()
        logger.info("Recursos liberados.")


if __name__ == '__main__':
    servicio = BaseDatos()
    servicio.iniciar()
