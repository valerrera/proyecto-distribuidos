# Gestión Inteligente de Tráfico Urbano
**Pontificia Universidad Javeriana — Sistemas Distribuidos 2026-10**

## Requisitos

- Python 3.11+
- pyzmq

```bash
pip install -r requirements.txt
```

## Configuración de IPs

Editar `config/config.json` y ajustar las IPs reales de las VMs:

```json
"pc1_ip": "192.168.1.10",
"pc2_ip": "192.168.1.20",
"pc3_ip": "192.168.1.30"
```

## Inicializar bases de datos

**En PC3:**
```bash
python db/init_db.py --solo-principal
```

**En PC2:**
```bash
python db/init_db.py --solo-replica
```

## Orden de arranque

### PC3 (primero)
```bash
python pc3/base_datos.py
python pc3/monitoreo.py
```

### PC2 (segundo)
```bash
python pc2/bd_replica.py
python pc2/semaforos.py
python pc2/analitica.py
```

### PC1 (último)
```bash
python pc1/broker.py

# En terminales separadas, un proceso por sensor:
python pc1/sensor_camara.py CAM-A1 INT_A1
python pc1/sensor_espira.py ESP-A1 INT_A1
python pc1/sensor_gps.py    GPS-A1 INT_A1

# Repetir para las intersecciones deseadas
```

## Estructura de la ciudad

Cuadrícula 4×5 — filas A–D, columnas 1–5.

```
     1      2      3      4      5
A  INT_A1 INT_A2 INT_A3 INT_A4 INT_A5
B  INT_B1 INT_B2 INT_B3 INT_B4 INT_B5
C  INT_C1 INT_C2 INT_C3 INT_C4 INT_C5
D  INT_D1 INT_D2 INT_D3 INT_D4 INT_D5
```

## Simular falla de PC3

Detener los procesos en PC3. El sistema detecta la falla
automáticamente vía health check y redirige la persistencia
a la BD réplica en PC2 sin intervención manual.

## Puertos ZMQ

| Puerto | Uso |
|--------|-----|
| 5554   | Broker SUB (sensores → broker) |
| 5555   | Broker PUB (broker → analítica) |
| 5556   | Analítica → Semáforos PUSH/PULL |
| 5557   | Analítica → BD principal PUSH/PULL |
| 5558   | Analítica → BD réplica PUSH/PULL |
| 5560   | Monitoreo REQ/REP (usuario) |
| 5561   | Analítica REP (indicaciones directas) |
| 5562   | Health check PC3 |
