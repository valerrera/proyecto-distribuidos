"""
config/loader.py
Utilidad para cargar config.json desde cualquier módulo del proyecto.
"""

import json
import os

_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'config.json'
)


def cargar_config() -> dict:
    """Carga y retorna el diccionario de configuración global."""
    with open(_CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)
