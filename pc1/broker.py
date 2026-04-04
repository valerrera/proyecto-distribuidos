"""
broker.py
Broker ZeroMQ del PC1.
Actúa como intermediario entre los sensores (productores) y el
servicio de analítica en PC2 (consumidor).

Patrones usados:
  - SUB: recibe mensajes de los sensores (tópicos: camara, espira, gps)
  - PUB: reenvía los mensajes al servicio de analítica en PC2

Flujo:
  Sensores --[PUB/SUB]--> Broker --[PUB/SUB]--> Analítica (PC2)

Uso:
    python broker.py
"""

import zmq
import logging
import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, '..'))

from config.loader import cargar_config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [Broker] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('BrokerZMQ')

TOPICOS = ['camara', 'espira', 'gps']


class BrokerZMQ:
    """
    Broker ZeroMQ que desacopla sensores de consumidores.
    Suscribe a los tres tópicos de sensores y republica
    todos los mensajes hacia el servicio de analítica.
    """

    def __init__(self):
        self.config     = cargar_config()
        self.context    = zmq.Context()
        self.sub_socket = None   # Recibe de los sensores
        self.pub_socket = None   # Envía hacia analítica (PC2)

    def iniciar(self):
        """Configura los sockets y comienza el loop de reenvío."""
        puertos = self.config['red']['puertos']

        # Socket SUB — escucha mensajes de los sensores
        self.sub_socket = self.context.socket(zmq.SUB)
        self.sub_socket.bind(f"tcp://*:{puertos['broker_sub']}")

        # Suscribirse a los tres tópicos
        self.suscribir_topicos()

        # Socket PUB — reenvía mensajes hacia analítica en PC2
        self.pub_socket = self.context.socket(zmq.PUB)
        self.pub_socket.bind(f"tcp://*:{puertos['broker_pub']}")

        pc2_ip   = self.config['red']['pc2_ip']
        logger.info(
            f"Broker iniciado | "
            f"SUB en :{puertos['broker_sub']} | "
            f"PUB en :{puertos['broker_pub']} hacia {pc2_ip}"
        )
        logger.info(f"Tópicos suscritos: {TOPICOS}")

        self.reenviar_mensajes()

    def suscribir_topicos(self):
        """Registra los filtros de tópico en el socket SUB."""
        for topico in TOPICOS:
            self.sub_socket.setsockopt(zmq.SUBSCRIBE, topico.encode('utf-8'))
            logger.info(f"Suscrito al tópico: {topico}")

    def reenviar_mensajes(self):
        """
        Loop principal: recibe mensajes de los sensores
        y los reenvía hacia el servicio de analítica.
        """
        logger.info("Esperando mensajes de sensores...")
        try:
            while True:
                # Recibir mensaje multiparte [topico, datos_json]
                partes = self.sub_socket.recv_multipart()
                topico = partes[0].decode('utf-8')
                datos  = partes[1].decode('utf-8')

                logger.info(f"Recibido [{topico}] → reenviando...")

                # Reenviar hacia analítica con el mismo formato
                self.pub_socket.send_multipart([
                    topico.encode('utf-8'),
                    datos.encode('utf-8')
                ])

        except KeyboardInterrupt:
            logger.info("Broker detenido por el usuario.")
        finally:
            self._cerrar()

    def _cerrar(self):
        """Libera recursos ZMQ."""
        if self.sub_socket:
            self.sub_socket.close()
        if self.pub_socket:
            self.pub_socket.close()
        self.context.term()
        logger.info("Recursos ZMQ liberados.")


# ── Punto de entrada ──────────────────────────────────────────────────────────

if __name__ == '__main__':
    broker = BrokerZMQ()
    broker.iniciar()
