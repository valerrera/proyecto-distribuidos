"""
sensor_gps.py
Sensor tipo GPS (vehículos conectados).
Genera EVENTO_DENSIDAD_DE_TRAFICO con velocidad promedio
y nivel de congestión calculado según umbrales del sistema.

Uso:
    python sensor_gps.py GPS-D5 INT_D5
"""

import sys
import os
import random

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, '..'))

from pc1.sensor_base import SensorBase


class SensorGPS(SensorBase):
    """
    Simula señales GPS de vehículos circulando en la intersección.
    Calcula el nivel de congestión a partir de la velocidad promedio:
        ALTA   → Vp < 10 km/h
        NORMAL → 10 ≤ Vp ≤ 39 km/h
        BAJA   → Vp > 39 km/h  (tráfico fluido)
    """

    TOPICO = 'gps'

    # Umbrales de congestión según el enunciado
    VEL_CONGESTION_ALTA   = 10   # km/h — por debajo: ALTA congestión
    VEL_CONGESTION_NORMAL = 39   # km/h — por encima: congestión BAJA (fluido)

    def __init__(self, sensor_id: str, interseccion: str):
        super().__init__(sensor_id, interseccion, self.TOPICO)
        cfg = self.config['sensores']['gps']
        self._vel_min = cfg['velocidad_min']
        self._vel_max = cfg['velocidad_max']

    def calcular_nivel(self, velocidad: float) -> str:
        """
        Determina el nivel de congestión según la velocidad promedio.

        Args:
            velocidad: Velocidad promedio en km/h.
        Returns:
            'ALTA', 'NORMAL' o 'BAJA'
        """
        if velocidad < self.VEL_CONGESTION_ALTA:
            return 'ALTA'
        elif velocidad <= self.VEL_CONGESTION_NORMAL:
            return 'NORMAL'
        else:
            return 'BAJA'

    def generar_evento(self) -> dict:
        """Genera un evento EVENTO_DENSIDAD_DE_TRAFICO."""
        velocidad = round(random.uniform(self._vel_min, self._vel_max), 1)
        nivel     = self.calcular_nivel(velocidad)

        return {
            "tipo_evento":         "EVENTO_DENSIDAD_DE_TRAFICO",
            "sensor_id":           self.sensor_id,
            "tipo_sensor":         "gps",
            "interseccion":        self.interseccion,
            "nivel_congestion":    nivel,
            "velocidad_promedio":  velocidad,
            "timestamp":           self.timestamp_utc()
        }


# ── Punto de entrada ──────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 3:
        print("Uso: python sensor_gps.py <sensor_id> <interseccion>")
        print("Ej:  python sensor_gps.py GPS-D5 INT_D5")
        sys.exit(1)

    sensor_id    = sys.argv[1]
    interseccion = sys.argv[2]

    sensor = SensorGPS(sensor_id, interseccion)
    sensor.iniciar_loop()


if __name__ == '__main__':
    main()
