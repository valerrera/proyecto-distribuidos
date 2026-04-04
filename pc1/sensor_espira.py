"""
sensor_espira.py
Sensor tipo espira inductiva.
Genera EVENTO_CONTEO_VEHICULAR contando vehículos que pasan
sobre la espira en un intervalo de tiempo configurable.

Uso:
    python sensor_espira.py ESP-B2 INT_B2
"""

import sys
import os
import random

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, '..'))

from pc1.sensor_base import SensorBase
from datetime import datetime, timezone, timedelta


class SensorEspira(SensorBase):
    """
    Simula una espira inductiva embebida en el pavimento.
    Mide el volumen de vehículos V (veh/min) que cruzan la intersección.
    """

    TOPICO = 'espira'

    def __init__(self, sensor_id: str, interseccion: str):
        super().__init__(sensor_id, interseccion, self.TOPICO)
        cfg = self.config['sensores']['espira']
        self._veh_min       = cfg['vehiculos_min']
        self._veh_max       = cfg['vehiculos_max']
        self._intervalo_cnt = cfg['intervalo_conteo_seg']

    def contar_vehiculos(self) -> int:
        """
        Simula el conteo de vehículos en el intervalo de medición.
        En condiciones normales el valor oscila entre min y max.
        """
        return random.randint(self._veh_min, self._veh_max)

    def generar_evento(self) -> dict:
        """Genera un evento EVENTO_CONTEO_VEHICULAR."""
        ahora      = datetime.now(timezone.utc)
        ts_inicio  = (ahora - timedelta(seconds=self._intervalo_cnt)).strftime('%Y-%m-%dT%H:%M:%SZ')
        ts_fin     = ahora.strftime('%Y-%m-%dT%H:%M:%SZ')
        vehiculos  = self.contar_vehiculos()

        return {
            "tipo_evento":          "EVENTO_CONTEO_VEHICULAR",
            "sensor_id":            self.sensor_id,
            "tipo_sensor":          "espira_inductiva",
            "interseccion":         self.interseccion,
            "vehiculos_contados":   vehiculos,
            "intervalo_segundos":   self._intervalo_cnt,
            "timestamp_inicio":     ts_inicio,
            "timestamp_fin":        ts_fin
        }


# ── Punto de entrada ──────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 3:
        print("Uso: python sensor_espira.py <sensor_id> <interseccion>")
        print("Ej:  python sensor_espira.py ESP-B2 INT_B2")
        sys.exit(1)

    sensor_id    = sys.argv[1]
    interseccion = sys.argv[2]

    sensor = SensorEspira(sensor_id, interseccion)
    sensor.iniciar_loop()


if __name__ == '__main__':
    main()
