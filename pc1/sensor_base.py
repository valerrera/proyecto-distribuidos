"""
sensor_base.py
Clase base abstracta para todos los tipos de sensor del sistema.
Los sensores concretos (cámara, espira, GPS) heredan de esta clase.
"""

import zmq
import json
import time
import logging
import os
import sys
from abc import ABC, abstractmethod
from datetime import datetime, timezone

# Ajustar path para importar config
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, '..'))

from config.loader import cargar_config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)


class SensorBase(ABC):
    """
    Clase base para sensores de tráfico.
    Publica eventos al broker ZMQ usando el patrón PUB/SUB.
    """

    def __init__(self, sensor_id: str, interseccion: str, topico: str):
        """
        Args:
            sensor_id:    Identificador único del sensor (ej. 'CAM-A1')
            interseccion: Intersección donde está ubicado (ej. 'INT_A1')
            topico:       Tópico ZMQ al que publica ('camara','espira','gps')
        """
        self.sensor_id    = sensor_id
        self.interseccion = interseccion
        self.topico       = topico
        self.config       = cargar_config()
        self.logger       = logging.getLogger(sensor_id)

        self._intervalo   = self.config['sensores']['intervalo_segundos']
        self._broker_ip   = self.config['red']['pc1_ip']
        self._broker_port = self.config['red']['puertos']['broker_sub']

        self._context     = zmq.Context()
        self._socket      = None

    def conectar(self):
        """Crea el socket PUB y se conecta al broker."""
        self._socket = self._context.socket(zmq.PUB)
        direccion = f"tcp://{self._broker_ip}:{self._broker_port}"
        self._socket.connect(direccion)
        # Pequeña pausa para que ZMQ establezca la conexión (slow joiner)
        time.sleep(0.5)
        self.logger.info(f"Conectado al broker en {direccion} | tópico: {self.topico}")

    def timestamp_utc(self) -> str:
        """Retorna timestamp actual en formato ISO 8601 UTC."""
        return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    @abstractmethod
    def generar_evento(self) -> dict:
        """
        Genera y retorna un diccionario con el evento del sensor.
        Cada subclase implementa la lógica de generación de datos.
        """
        pass

    def publicar(self, evento: dict):
        """
        Serializa el evento a JSON y lo publica en el tópico correspondiente.
        Formato del mensaje: '<topico> <json_evento>'
        """
        mensaje = json.dumps(evento, ensure_ascii=False)
        self._socket.send_multipart([
            self.topico.encode('utf-8'),
            mensaje.encode('utf-8')
        ])
        self.logger.info(f"Publicado → {self.interseccion} | {mensaje}")

    def iniciar_loop(self):
        """Inicia el loop de generación y publicación de eventos."""
        self.conectar()
        self.logger.info(f"Iniciando loop cada {self._intervalo}s")
        try:
            while True:
                evento = self.generar_evento()
                self.publicar(evento)
                time.sleep(self._intervalo)
        except KeyboardInterrupt:
            self.logger.info("Sensor detenido por el usuario.")
        finally:
            self._socket.close()
            self._context.term()
