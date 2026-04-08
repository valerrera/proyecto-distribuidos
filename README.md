# Gestión Inteligente de Tráfico Urbano
**Pontificia Universidad Javeriana — Sistemas Distribuidos 2026-10**

## IPs de las máquinas

| Máquina | IP            |
|---------|---------------|
| PC1     | 10.43.99.136  |
| PC2     | 10.43.99.139  |
| PC3     | 10.43.97.251  |

Si las IPs cambian, editar `config/config.json`.

---

## Paso 0 — Instalar dependencias (en las 3 máquinas)

```bash
pip3 install pyzmq
```

---

## Paso 1 — Inicializar las bases de datos (hacer UNA SOLA VEZ)

**En PC3** — crea la BD principal:
```bash
python3 db/init_db.py --solo-principal
```

**En PC2** — crea la BD réplica:
```bash
python3 db/init_db.py --solo-replica
```

---

## Paso 2 — Arrancar PC3

Abrir **1 terminal** en PC3 y ejecutar:

```bash
python3 pc3/base_datos.py
```

Dejar esa terminal corriendo. Debe mostrar:
`BD principal lista. Esperando eventos...`

---

## Paso 3 — Arrancar PC2

Abrir **3 terminales** en PC2, una por proceso:

**Terminal 1:**
```bash
python3 pc2/bd_replica.py
```
Debe mostrar: `Réplica lista. Esperando eventos...`

**Terminal 2:**
```bash
python3 pc2/semaforos.py
```
Debe mostrar: `Esperando comandos en puerto :5556`

**Terminal 3:**
```bash
python3 pc2/analitica.py
```
Debe mostrar: `Servicio de analítica iniciado.`

---

## Paso 4 — Arrancar PC1

Abrir **4 terminales** en PC1 (o más si se usan más sensores):

**Terminal 1 — Broker:**
```bash
python3 pc1/broker.py
```
Debe mostrar: `Broker iniciado | SUB en :5554 | PUB en :5555`

**Terminal 2 — Sensor cámara:**
```bash
python3 pc1/sensor_camara.py CAM-A1 INT_A1
```

**Terminal 3 — Sensor espira:**
```bash
python3 pc1/sensor_espira.py ESP-A1 INT_A1
```

**Terminal 4 — Sensor GPS:**
```bash
python3 pc1/sensor_gps.py GPS-A1 INT_A1
```

> Se pueden lanzar sensores en más intersecciones repitiendo los comandos con IDs distintos, por ejemplo:
> ```bash
> python3 pc1/sensor_camara.py CAM-B3 INT_B3
> python3 pc1/sensor_espira.py ESP-B3 INT_B3
> python3 pc1/sensor_gps.py    GPS-B3 INT_B3
> ```

---

## Estructura de la ciudad

Cuadrícula 4×5 — filas A–D, columnas 1–5.

```
     1      2      3      4      5
A  INT_A1 INT_A2 INT_A3 INT_A4 INT_A5
B  INT_B1 INT_B2 INT_B3 INT_B4 INT_B5
C  INT_C1 INT_C2 INT_C3 INT_C4 INT_C5
D  INT_D1 INT_D2 INT_D3 INT_D4 INT_D5
```

Cada intersección tiene un semáforo y 3 sensores (cámara, espira, GPS).

---

## Consultar las bases de datos desde terminal

### En PC3 — BD principal (`db/trafico_principal.db`)

```bash
# Últimos 10 eventos de sensores recibidos
sqlite3 db/trafico_principal.db "SELECT * FROM eventos_sensores ORDER BY id DESC LIMIT 10;"

# Estado actual de todos los semáforos
sqlite3 db/trafico_principal.db "SELECT * FROM estado_semaforos;"

# Últimas decisiones de analítica (NORMAL / CONGESTION / PRIORIZACION)
sqlite3 db/trafico_principal.db "SELECT * FROM decisiones_analitica ORDER BY id DESC LIMIT 10;"

# Total de eventos almacenados
sqlite3 db/trafico_principal.db "SELECT COUNT(*) FROM eventos_sensores;"
```

### En PC2 — BD réplica (`db/trafico_replica.db`)

```bash
# Mismas consultas pero apuntando a la réplica:
sqlite3 db/trafico_replica.db "SELECT * FROM eventos_sensores ORDER BY id DESC LIMIT 10;"
sqlite3 db/trafico_replica.db "SELECT * FROM estado_semaforos;"
sqlite3 db/trafico_replica.db "SELECT * FROM decisiones_analitica ORDER BY id DESC LIMIT 10;"
sqlite3 db/trafico_replica.db "SELECT COUNT(*) FROM eventos_sensores;"
```

---

## Simular falla de PC3

Detener el proceso `base_datos.py` en PC3 (Ctrl+C).  
La analítica detecta la falla automáticamente mediante health check
y redirige toda la persistencia a la BD réplica en PC2.
El sistema sigue funcionando sin intervención manual.

---

## Puertos ZMQ

| Puerto | Uso |
|--------|-----|
| 5554   | Broker SUB — sensores publican aquí |
| 5555   | Broker PUB — analítica se suscribe aquí |
| 5556   | Semáforos PULL — analítica envía comandos aquí |
| 5557   | BD principal PULL — analítica envía eventos aquí |
| 5558   | BD réplica PULL — analítica envía eventos aquí |
| 5561   | Analítica REP — reservado para monitoreo (2ª entrega) |
| 5562   | Health check PC3 |
