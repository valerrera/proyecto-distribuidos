"""
sensor_camara.py
Sensor tipo cámara de tráfico.
Genera EVENTO_LONGITUD_COLA con volumen de vehículos en espera
y velocidad promedio observada en la intersección.

Uso:
    python sensor_camara.py CAM-A1 INT_A1
    python sensor_camara.py CAM-C3 INT_C3
"""

import sys
import os
import random

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, '..'))

from pc1.sensor_base import SensorBase


class SensorCamara(SensorBase):
    """
    Simula una cámara de tráfico ubicada en una intersección.
    Mide volumen de vehículos en espera (Q) y velocidad promedio (Vp).
    """

    TOPICO = 'camara'

    def __init__(self, sensor_id: str, interseccion: str):
        super().__init__(sensor_id, interseccion, self.TOPICO)
        cfg = self.config['sensores']['camara']
        self._vol_min  = cfg['volumen_min']
        self._vol_max  = cfg['volumen_max']
        self._vel_min  = cfg['velocidad_min']
        self._vel_max  = cfg['velocidad_max']

    def calcular_cola(self, velocidad: float) -> int:
        """
        Estima la longitud de cola basándose en la velocidad:
        a menor velocidad, mayor número de vehículos detenidos.
        """
        factor = 1 - (velocidad / self._vel_max)
        return int(self._vol_max * factor * random.uniform(0.7, 1.0))

    def generar_evento(self) -> dict:
        """Genera un evento EVENTO_LONGITUD_COLA."""
        velocidad = round(random.uniform(self._vel_min, self._vel_max), 1)
        volumen   = self.calcular_cola(velocidad)

        return {
            "tipo_evento":         "EVENTO_LONGITUD_COLA",
            "sensor_id":           self.sensor_id,
            "tipo_sensor":         "camara",
            "interseccion":        self.interseccion,
            "volumen":             volumen,
            "velocidad_promedio":  velocidad,
            "timestamp":           self.timestamp_utc()
        }


# ── Punto de entrada ──────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 3:
        print("Uso: python sensor_camara.py <sensor_id> <interseccion>")
        print("Ej:  python sensor_camara.py CAM-A1 INT_A1")
        sys.exit(1)

    sensor_id    = sys.argv[1]
    interseccion = sys.argv[2]

    sensor = SensorCamara(sensor_id, interseccion)
    sensor.iniciar_loop()


if __name__ == '__main__':
    main()
