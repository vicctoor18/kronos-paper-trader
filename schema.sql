-- ═══════════════════════════════════════════════════════════
--  Kronos Paper Trader — Schema Supabase
--  Ejecuta este SQL en: Supabase → SQL Editor → Run
-- ═══════════════════════════════════════════════════════════

-- ── Historial del portfolio (una fila por hora) ─────────────
CREATE TABLE IF NOT EXISTS portfolio (
    id                    BIGSERIAL PRIMARY KEY,
    cash                  DECIMAL(12,4)  NOT NULL,
    total_value           DECIMAL(12,4)  NOT NULL,
    peak_value            DECIMAL(12,4)  NOT NULL,
    open_positions_count  INTEGER        DEFAULT 0,
    paused                BOOLEAN        DEFAULT FALSE,
    created_at            TIMESTAMPTZ    DEFAULT NOW()
);

-- ── Operaciones (paper trades) ──────────────────────────────
CREATE TABLE IF NOT EXISTS trades (
    id               BIGSERIAL PRIMARY KEY,
    symbol           VARCHAR(20)    NOT NULL,
    entry_price      DECIMAL(20,8)  NOT NULL,
    qty              DECIMAL(20,8)  NOT NULL,
    cost             DECIMAL(12,4)  NOT NULL,
    status           VARCHAR(10)    DEFAULT 'open',   -- open | closed
    entry_time       TIMESTAMPTZ    NOT NULL,
    exit_price       DECIMAL(20,8),
    exit_time        TIMESTAMPTZ,
    pnl              DECIMAL(12,4),
    close_reason     VARCHAR(30),                      -- stop_loss | signal_exit
    expected_return  DECIMAL(10,6),
    created_at       TIMESTAMPTZ    DEFAULT NOW()
);

-- ── Señales de Kronos (una por par por hora) ─────────────────
CREATE TABLE IF NOT EXISTS signals (
    id                    BIGSERIAL PRIMARY KEY,
    symbol                VARCHAR(20)    NOT NULL,
    current_price         DECIMAL(20,8)  NOT NULL,
    predicted_price_24h   DECIMAL(20,8)  NOT NULL,
    expected_return       DECIMAL(10,6)  NOT NULL,
    created_at            TIMESTAMPTZ    DEFAULT NOW()
);

-- ── Índices para las queries del dashboard ───────────────────
CREATE INDEX IF NOT EXISTS idx_portfolio_ts  ON portfolio(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_sym    ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_signals_ts    ON signals(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_sym   ON signals(symbol, created_at DESC);

-- ── Row Level Security ───────────────────────────────────────
--  El bot usa la SERVICE KEY (bypassa RLS automáticamente).
--  El dashboard usa la ANON KEY, que solo puede leer.

ALTER TABLE portfolio ENABLE ROW LEVEL SECURITY;
ALTER TABLE trades    ENABLE ROW LEVEL SECURITY;
ALTER TABLE signals   ENABLE ROW LEVEL SECURITY;

-- Lectura pública (para el dashboard con anon key)
CREATE POLICY "anon_read_portfolio" ON portfolio FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_trades"    ON trades    FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_signals"   ON signals   FOR SELECT TO anon USING (true);
