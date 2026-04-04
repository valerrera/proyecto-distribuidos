-- ============================================================
-- Schema: Gestión Inteligente de Tráfico Urbano
-- Usado por BD principal (PC3) y réplica (PC2)
-- ============================================================

-- Tabla de eventos de sensores (todos los tipos)
CREATE TABLE IF NOT EXISTS eventos_sensores (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sensor_id       TEXT    NOT NULL,
    tipo_sensor     TEXT    NOT NULL CHECK(tipo_sensor IN ('camara','espira_inductiva','gps')),
    interseccion    TEXT    NOT NULL,
    timestamp       TEXT    NOT NULL,

    -- Campos cámara
    volumen         INTEGER,
    velocidad_promedio REAL,

    -- Campos espira
    vehiculos_contados INTEGER,
    intervalo_segundos INTEGER,
    timestamp_inicio   TEXT,
    timestamp_fin      TEXT,

    -- Campos GPS
    nivel_congestion   TEXT CHECK(nivel_congestion IN ('ALTA','NORMAL','BAJA', NULL))
);

-- Tabla de estado actual de semáforos
CREATE TABLE IF NOT EXISTS estado_semaforos (
    interseccion    TEXT    PRIMARY KEY,
    estado          TEXT    NOT NULL CHECK(estado IN ('VERDE','ROJO')),
    razon           TEXT,   -- 'normal', 'congestion', 'priorizacion', 'manual'
    timestamp       TEXT    NOT NULL
);

-- Tabla de decisiones de analítica (historial de acciones)
CREATE TABLE IF NOT EXISTS decisiones_analitica (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    interseccion    TEXT    NOT NULL,
    condicion       TEXT    NOT NULL CHECK(condicion IN ('NORMAL','CONGESTION','PRIORIZACION')),
    accion          TEXT    NOT NULL,
    timestamp       TEXT    NOT NULL,
    origen          TEXT    DEFAULT 'automatico' -- 'automatico' o 'manual'
);

-- Tabla de log de fallas y eventos del sistema
CREATE TABLE IF NOT EXISTS log_sistema (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo_evento     TEXT    NOT NULL, -- 'FALLA_PC3', 'RECONEXION', 'INICIO', etc.
    descripcion     TEXT,
    timestamp       TEXT    NOT NULL
);

-- Índices para consultas históricas eficientes
CREATE INDEX IF NOT EXISTS idx_eventos_timestamp    ON eventos_sensores(timestamp);
CREATE INDEX IF NOT EXISTS idx_eventos_interseccion ON eventos_sensores(interseccion);
CREATE INDEX IF NOT EXISTS idx_decisiones_timestamp ON decisiones_analitica(timestamp);
CREATE INDEX IF NOT EXISTS idx_decisiones_cond      ON decisiones_analitica(condicion);
