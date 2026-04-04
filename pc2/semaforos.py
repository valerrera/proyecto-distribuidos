"""
semaforos.py
Servicio de Control de Semáforos — PC2.

Recibe comandos del servicio de analítica (PUSH/PULL)
y ejecuta los cambios de estado de los semáforos simulados.

Estados posibles: VERDE | ROJO  (sin amarillo, según enunciado)

Uso:
    python semaforos.py
"""

import zmq
import json
import logging
import threading
import sys
import os
import time
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, '..'))

from config.loader import cargar_config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [Semáforos] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('ControlSemaforos')


class ControlSemaforos:
    """
    Gestiona el estado simulado de todos los semáforos de la ciudad.
    Recibe comandos del servicio de analítica y actualiza el estado
    de cada intersección.
    """

    VERDE = 'VERDE'
    ROJO  = 'ROJO'

    def __init__(self):
        self.config  = cargar_config()
        self.context = zmq.Context()

        # Estado actual de cada semáforo: { 'INT_A1': 'ROJO', ... }
        self.estado: dict[str, str] = {}
        self._lock_estado = threading.Lock()

        # Timers activos por intersección para revertir estado
        self._timers: dict[str, threading.Timer] = {}

        self.pull_socket = None

        # Inicializar todos en ROJO
        self._inicializar_semaforos()

    def _inicializar_semaforos(self):
        """Pone todos los semáforos en ROJO al arrancar."""
        ciudad = self.config['ciudad']
        for fila in ciudad['filas']:
            for col in ciudad['columnas']:
                interseccion = f"INT_{fila}{col}"
                self.estado[interseccion] = self.ROJO
        logger.info(f"Semáforos inicializados: {len(self.estado)} intersecciones en ROJO")

    def iniciar(self):
        """Configura el socket PULL e inicia el loop de atención de comandos."""
        p = self.config['red']['puertos']

        self.pull_socket = self.context.socket(zmq.PULL)
        self.pull_socket.bind(f"tcp://*:{p['analitica_push_semaforos']}")
        logger.info(f"Esperando comandos en puerto :{p['analitica_push_semaforos']}")

        self._escuchar_comandos()

    def _escuchar_comandos(self):
        """Loop principal: recibe y ejecuta comandos de la analítica."""
        try:
            while True:
                comando = self.pull_socket.recv_json()
                logger.info(f"Comando recibido: {comando}")
                self._ejecutar_comando(comando)

        except KeyboardInterrupt:
            logger.info("Servicio detenido.")
        finally:
            self._cerrar()

    # ── Ejecución de comandos ─────────────────────────────────────────────────

    def _ejecutar_comando(self, comando: dict):
        """
        Despacha el comando al método correspondiente según la acción.
        Acciones soportadas:
          CICLO_NORMAL   → ciclo estándar rojo/verde
          EXTENDER_VERDE → mantener verde más tiempo (congestión)
          FORZAR_VERDE   → verde inmediato (priorización/ambulancia)
          FORZAR_ROJO    → rojo inmediato
          OLA_VERDE      → verde en todas las intersecciones de una vía
        """
        accion       = comando.get('accion')
        interseccion = comando.get('interseccion')
        tiempo       = comando.get('tiempo_seg',
                                   self.config['semaforos']['tiempo_verde_normal_seg'])
        origen       = comando.get('origen', 'automatico')

        if accion in ('CICLO_NORMAL', 'EXTENDER_VERDE', 'FORZAR_VERDE'):
            self.cambiar_estado(interseccion, self.VERDE, tiempo, origen)

        elif accion == 'FORZAR_ROJO':
            self.cambiar_estado(interseccion, self.ROJO, None, origen)

        else:
            logger.warning(f"Acción no reconocida: {accion}")

    def cambiar_estado(
        self,
        interseccion: str,
        nuevo_estado: str,
        duracion_seg: int | None,
        origen: str = 'automatico'
    ):
        """
        Cambia el estado del semáforo en la intersección indicada.
        Si se especifica duracion_seg, programa la reversión automática.

        Args:
            interseccion:  ID de la intersección (ej. 'INT_A1')
            nuevo_estado:  'VERDE' o 'ROJO'
            duracion_seg:  Segundos antes de revertir al estado opuesto
            origen:        'automatico' o 'manual'
        """
        with self._lock_estado:
            estado_anterior = self.estado.get(interseccion, 'DESCONOCIDO')
            self.estado[interseccion] = nuevo_estado

        icono = '🟢' if nuevo_estado == self.VERDE else '🔴'
        logger.info(
            f"{icono} [{interseccion}] {estado_anterior} → {nuevo_estado} "
            f"| duración: {duracion_seg}s | origen: {origen}"
        )

        # Cancelar timer anterior si existe
        if interseccion in self._timers:
            self._timers[interseccion].cancel()
            del self._timers[interseccion]

        # Programar reversión automática
        if duracion_seg:
            estado_reverso = self.ROJO if nuevo_estado == self.VERDE else self.VERDE
            timer = threading.Timer(
                duracion_seg,
                self._revertir_estado,
                args=[interseccion, estado_reverso]
            )
            timer.daemon = True
            timer.start()
            self._timers[interseccion] = timer

    def _revertir_estado(self, interseccion: str, estado: str):
        """Revierte el semáforo al estado opuesto tras la duración configurada."""
        with self._lock_estado:
            self.estado[interseccion] = estado
        icono = '🟢' if estado == self.VERDE else '🔴'
        logger.info(f"{icono} [{interseccion}] Reversión automática → {estado}")

    def ola_verde(self, via: str):
        """
        Activa verde en todas las intersecciones de una vía.
        via: fila ('A'–'D') o columna ('1'–'5')
        """
        ciudad = self.config['ciudad']
        filas  = ciudad['filas']
        cols   = [str(c) for c in ciudad['columnas']]
        tiempo = self.config['semaforos']['tiempo_verde_priorizacion_seg']

        if via in filas:
            intersecciones = [f"INT_{via}{c}" for c in cols]
        elif via in cols:
            intersecciones = [f"INT_{f}{via}" for f in filas]
        else:
            logger.warning(f"Vía no reconocida: {via}")
            return

        for inter in intersecciones:
            self.cambiar_estado(inter, self.VERDE, tiempo, 'manual')
        logger.warning(f"OLA VERDE activa en vía {via}: {intersecciones}")

    def obtener_estado(self) -> dict:
        """Retorna el estado actual de todos los semáforos."""
        with self._lock_estado:
            return dict(self.estado)

    def _ts(self) -> str:
        return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    def _cerrar(self):
        for timer in self._timers.values():
            timer.cancel()
        if self.pull_socket:
            self.pull_socket.close()
        self.context.term()
        logger.info("Recursos liberados.")


# ── Punto de entrada ──────────────────────────────────────────────────────────

if __name__ == '__main__':
    servicio = ControlSemaforos()
    servicio.iniciar()
