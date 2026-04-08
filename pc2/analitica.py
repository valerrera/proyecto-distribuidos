"""
analitica.py
Servicio de Analítica — PC2.

Responsabilidades:
  1. Suscribirse a los eventos de sensores vía broker ZMQ (PUB/SUB)
  2. Evaluar reglas de tráfico para determinar la condición de cada intersección
  3. Enviar comandos de control al servicio de semáforos (PUSH/PULL)
  4. Persistir eventos en BD principal (PC3) y réplica (PC2) vía PUSH/PULL
  5. Atender indicaciones directas del servicio de monitoreo (REQ/REP)
  6. Detectar falla en PC3 y redirigir persistencia a réplica (health check)

Uso:
    python analitica.py
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
    format='%(asctime)s [Analítica] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('ServicioAnalitica')


class ServicioAnalitica:
    """
    Servicio central de procesamiento y toma de decisiones.
    """

    CONDICION_NORMAL      = 'NORMAL'
    CONDICION_CONGESTION  = 'CONGESTION'
    CONDICION_PRIORIDAD   = 'PRIORIZACION'

    def __init__(self):
        self.config  = cargar_config()
        self.reglas  = self.config['reglas']
        self.red     = self.config['red']
        self.context = zmq.Context()

        # Estado de conectividad hacia BD principal
        self._pc3_disponible    = True
        self._lock_pc3          = threading.Lock()

        # Buffer de último evento por intersección (para evaluar reglas cruzadas)
        self._ultimo_evento: dict[str, dict] = {}
        self._lock_eventos = threading.Lock()

        # Sockets (se inicializan en iniciar())
        self.sub_socket      = None  # Recibe eventos del broker
        self.push_semaforos  = None  # Envía comandos a semáforos
        self.push_bd         = None  # Envía a BD principal (PC3)
        self.push_replica    = None  # Envía a BD réplica (PC2)
        self.rep_socket      = None  # Responde indicaciones del monitoreo

    # ── Inicialización ────────────────────────────────────────────────────────

    def iniciar(self):
        """Configura sockets e inicia todos los hilos del servicio."""
        p   = self.red['puertos']
        pc1 = self.red['pc1_ip']
        pc2 = self.red['pc2_ip']
        pc3 = self.red['pc3_ip']

        # SUB — recibe eventos del broker en PC1
        self.sub_socket = self.context.socket(zmq.SUB)
        self.sub_socket.connect(f"tcp://{pc1}:{p['broker_pub']}")
        for topico in ['camara', 'espira', 'gps']:
            self.sub_socket.setsockopt(zmq.SUBSCRIBE, topico.encode())

        # PUSH — envía comandos al servicio de semáforos (mismo PC2)
        # Semáforos hace bind; analítica se conecta a él.
        self.push_semaforos = self.context.socket(zmq.PUSH)
        self.push_semaforos.connect(f"tcp://{pc2}:{p['analitica_push_semaforos']}")

        # PUSH — envía eventos a BD principal (PC3)
        self.push_bd = self.context.socket(zmq.PUSH)
        self.push_bd.connect(f"tcp://{pc3}:{p['bd_principal_pull']}")
        self.push_bd.setsockopt(zmq.SNDTIMEO, 2000)  # timeout 2s para detectar falla

        # PUSH — envía eventos a BD réplica (PC2 local)
        self.push_replica = self.context.socket(zmq.PUSH)
        self.push_replica.connect(f"tcp://{pc2}:{p['analitica_push_replica']}")

        # REP — atiende indicaciones directas del monitoreo
        self.rep_socket = self.context.socket(zmq.REP)
        self.rep_socket.bind(f"tcp://*:{p['analitica_rep']}")

        logger.info("Servicio de analítica iniciado.")
        logger.info(f"Suscrito al broker en {pc1}:{p['broker_pub']}")

        # Lanzar hilos paralelos
        hilo_monitoreo   = threading.Thread(target=self._atender_monitoreo, daemon=True)
        hilo_health      = threading.Thread(target=self._health_check_pc3,  daemon=True)

        hilo_monitoreo.start()
        hilo_health.start()

        # Hilo principal: procesar eventos de sensores
        self._procesar_eventos()

    # ── Procesamiento de eventos ──────────────────────────────────────────────

    def _procesar_eventos(self):
        """Loop principal: recibe y procesa eventos de sensores."""
        logger.info("Esperando eventos de sensores...")
        try:
            while True:
                partes = self.sub_socket.recv_multipart()
                topico = partes[0].decode('utf-8')
                datos  = json.loads(partes[1].decode('utf-8'))

                logger.info(f"Evento recibido [{topico}] — {datos.get('interseccion')}")

                # Actualizar buffer de última lectura por intersección
                interseccion = datos.get('interseccion', 'DESCONOCIDA')
                with self._lock_eventos:
                    if interseccion not in self._ultimo_evento:
                        self._ultimo_evento[interseccion] = {}
                    self._ultimo_evento[interseccion][topico] = datos

                # Persistir en BD
                self._guardar_en_bd(datos)

                # Evaluar reglas con todos los datos disponibles
                condicion = self._evaluar_reglas(interseccion)
                self._tomar_decision(interseccion, condicion, datos)

        except KeyboardInterrupt:
            logger.info("Servicio detenido.")
        finally:
            self._cerrar()

    # ── Evaluación de reglas ──────────────────────────────────────────────────

    def _evaluar_reglas(self, interseccion: str) -> str:
        """
        Evalúa las reglas de tráfico con los últimos datos disponibles
        para la intersección indicada.

        Reglas:
          NORMAL     → Q < 5  AND Vp > 35 AND V < 20
          CONGESTIÓN → Q >= 5 OR  Vp <= 35 OR  V >= 20

        Returns:
            'NORMAL', 'CONGESTION'
        """
        with self._lock_eventos:
            lecturas = self._ultimo_evento.get(interseccion, {})

        r_normal     = self.reglas['normal']
        r_congestion = self.reglas['congestion']

        # Extraer valores disponibles (None si aún no hay lectura)
        camara = lecturas.get('camara', {})
        espira = lecturas.get('espira', {})
        gps    = lecturas.get('gps', {})

        Q  = camara.get('volumen')
        Vp = camara.get('velocidad_promedio') or gps.get('velocidad_promedio')
        V  = espira.get('vehiculos_contados')

        # Si no hay suficientes datos aún, asumir normal
        if Q is None or Vp is None or V is None:
            return self.CONDICION_NORMAL

        # Evaluar condición de congestión
        congestion = (
            Q  >= r_congestion['Q_min']  or
            Vp <= r_congestion['Vp_max'] or
            V  >= r_congestion['V_min']
        )

        if congestion:
            condicion = self.CONDICION_CONGESTION
        else:
            condicion = self.CONDICION_NORMAL

        logger.info(
            f"[{interseccion}] Q={Q} Vp={Vp} V={V} → {condicion}"
        )
        return condicion

    # ── Toma de decisiones ────────────────────────────────────────────────────

    def _tomar_decision(self, interseccion: str, condicion: str, evento: dict):
        """
        Determina la acción a tomar sobre el semáforo según la condición
        detectada y envía el comando correspondiente.
        """
        sem_cfg = self.config['semaforos']

        if condicion == self.CONDICION_NORMAL:
            accion  = 'CICLO_NORMAL'
            tiempo  = sem_cfg['tiempo_verde_normal_seg']
            logger.info(f"[{interseccion}] Tráfico NORMAL — ciclo estándar {tiempo}s")

        elif condicion == self.CONDICION_CONGESTION:
            accion  = 'EXTENDER_VERDE'
            tiempo  = sem_cfg['tiempo_verde_congestion_seg']
            logger.warning(
                f"[{interseccion}] CONGESTIÓN detectada — "
                f"extendiendo verde a {tiempo}s"
            )

        else:
            return  # PRIORIZACION se maneja desde monitoreo

        comando = {
            "interseccion": interseccion,
            "accion":       accion,
            "tiempo_seg":   tiempo,
            "condicion":    condicion,
            "origen":       "automatico",
            "timestamp":    self._ts()
        }
        self._enviar_comando_semaforo(comando)
        self._registrar_decision(interseccion, condicion, accion)

    def _enviar_comando_semaforo(self, comando: dict):
        """Envía un comando de control al servicio de semáforos."""
        self.push_semaforos.send_json(comando)
        logger.info(f"Comando enviado → semáforos: {comando['accion']} en {comando['interseccion']}")

    # ── Persistencia ──────────────────────────────────────────────────────────

    def _guardar_en_bd(self, evento: dict):
        """
        Envía el evento a la BD principal (PC3) y a la réplica (PC2).
        Si PC3 no está disponible, omite el envío principal
        y solo persiste en la réplica.
        """
        mensaje = json.dumps(evento)

        # Siempre guardar en réplica
        self.push_replica.send_string(mensaje)

        # Guardar en BD principal solo si PC3 está disponible
        with self._lock_pc3:
            pc3_ok = self._pc3_disponible

        if pc3_ok:
            try:
                self.push_bd.send_string(mensaje, zmq.NOBLOCK)
            except zmq.Again:
                logger.error("BD principal (PC3) no responde — usando solo réplica.")
                with self._lock_pc3:
                    self._pc3_disponible = False

    def _registrar_decision(self, interseccion: str, condicion: str, accion: str):
        """Envía el registro de decisión a la BD."""
        registro = {
            "tipo":          "decision",
            "interseccion":  interseccion,
            "condicion":     condicion,
            "accion":        accion,
            "origen":        "automatico",
            "timestamp":     self._ts()
        }
        self._guardar_en_bd(registro)

    # ── Health check PC3 ──────────────────────────────────────────────────────

    def _health_check_pc3(self):
        """
        Hilo que verifica periódicamente si PC3 sigue disponible.
        Crea un socket REQ nuevo en cada ping para evitar que el socket
        quede en estado corrupto tras un timeout (limitación de ZMQ REQ).
        """
        p         = self.red['puertos']
        pc3       = self.red['pc3_ip']
        timeout   = self.config['base_datos']['health_check_timeout_seg'] * 1000
        intervalo = self.config['base_datos']['health_check_intervalo_seg']

        logger.info(f"Health check PC3 iniciado (cada {intervalo}s)")

        while True:
            time.sleep(intervalo)
            socket_ping = self.context.socket(zmq.REQ)
            socket_ping.setsockopt(zmq.RCVTIMEO, timeout)
            socket_ping.setsockopt(zmq.SNDTIMEO, timeout)
            socket_ping.setsockopt(zmq.LINGER, 0)
            socket_ping.connect(f"tcp://{pc3}:{p['health_check']}")
            try:
                socket_ping.send_string('PING')
                respuesta = socket_ping.recv_string()
                if respuesta == 'PONG':
                    with self._lock_pc3:
                        if not self._pc3_disponible:
                            logger.info("PC3 recuperado — reanudando escritura en BD principal.")
                        self._pc3_disponible = True
            except zmq.Again:
                with self._lock_pc3:
                    if self._pc3_disponible:
                        logger.error(
                            "PC3 NO RESPONDE — "
                            "redirigiendo persistencia a BD réplica en PC2."
                        )
                    self._pc3_disponible = False
            except Exception as e:
                logger.error(f"Error en health check: {e}")
            finally:
                socket_ping.close()

    # ── Indicaciones directas del monitoreo ──────────────────────────────────

    def _atender_monitoreo(self):
        """
        Hilo que atiende solicitudes directas del servicio de monitoreo
        (ej. forzar ola verde para paso de ambulancia).
        Patrón REQ/REP.
        """
        logger.info("Esperando indicaciones del servicio de monitoreo...")
        while True:
            try:
                solicitud = self.rep_socket.recv_json()
                logger.info(f"Indicación recibida de monitoreo: {solicitud}")

                accion = solicitud.get('accion')
                respuesta = self._ejecutar_indicacion(solicitud)

                self.rep_socket.send_json(respuesta)

            except Exception as e:
                logger.error(f"Error atendiendo indicación: {e}")
                try:
                    self.rep_socket.send_json({"estado": "ERROR", "detalle": str(e)})
                except Exception:
                    pass

    def _ejecutar_indicacion(self, solicitud: dict) -> dict:
        """
        Procesa una indicación directa del operador.
        Soporta:
          - OLA_VERDE: priorizar toda una vía (fila o columna)
          - FORZAR_VERDE: forzar verde en una intersección específica
          - FORZAR_ROJO: forzar rojo en una intersección específica
        """
        accion       = solicitud.get('accion')
        interseccion = solicitud.get('interseccion')
        via          = solicitud.get('via')
        sem_cfg      = self.config['semaforos']

        if accion == 'OLA_VERDE':
            # Priorizar toda una vía (ambulancia)
            intersecciones = self._obtener_via(via)
            for inter in intersecciones:
                cmd = {
                    "interseccion": inter,
                    "accion":       "FORZAR_VERDE",
                    "tiempo_seg":   sem_cfg['tiempo_verde_priorizacion_seg'],
                    "condicion":    self.CONDICION_PRIORIDAD,
                    "origen":       "manual",
                    "timestamp":    self._ts()
                }
                self._enviar_comando_semaforo(cmd)
                self._registrar_decision(inter, self.CONDICION_PRIORIDAD, 'FORZAR_VERDE')

            logger.warning(f"OLA VERDE activada en vía: {via}")
            return {"estado": "OK", "via": via, "intersecciones": intersecciones}

        elif accion in ('FORZAR_VERDE', 'FORZAR_ROJO'):
            estado  = 'VERDE' if accion == 'FORZAR_VERDE' else 'ROJO'
            tiempo  = sem_cfg['tiempo_verde_priorizacion_seg']
            cmd = {
                "interseccion": interseccion,
                "accion":       accion,
                "tiempo_seg":   tiempo,
                "condicion":    self.CONDICION_PRIORIDAD,
                "origen":       "manual",
                "timestamp":    self._ts()
            }
            self._enviar_comando_semaforo(cmd)
            self._registrar_decision(interseccion, self.CONDICION_PRIORIDAD, accion)
            return {"estado": "OK", "interseccion": interseccion, "nuevo_estado": estado}

        else:
            logger.warning(f"Acción desconocida: {accion}")
            return {"estado": "ERROR", "detalle": f"Acción no reconocida: {accion}"}

    def _obtener_via(self, via: str) -> list:
        """
        Retorna todas las intersecciones de una vía.
        via puede ser una fila ('A','B','C','D')
        o una columna ('1','2','3','4','5').
        """
        ciudad  = self.config['ciudad']
        filas   = ciudad['filas']
        columnas = [str(c) for c in ciudad['columnas']]

        if via in filas:
            return [f"INT_{via}{c}" for c in columnas]
        elif via in columnas:
            return [f"INT_{f}{via}" for f in filas]
        else:
            logger.warning(f"Vía no reconocida: {via}")
            return []

    # ── Utilidades ────────────────────────────────────────────────────────────

    def _ts(self) -> str:
        return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    def _cerrar(self):
        sockets = [
            self.sub_socket, self.push_semaforos,
            self.push_bd, self.push_replica, self.rep_socket
        ]
        for s in sockets:
            if s:
                s.close()
        self.context.term()
        logger.info("Recursos liberados.")


# ── Punto de entrada ──────────────────────────────────────────────────────────

if __name__ == '__main__':
    servicio = ServicioAnalitica()
    servicio.iniciar()
