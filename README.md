# Kronos Paper Trader

Bot de paper trading con señales de IA (Kronos-small) sobre BTC, ETH y SOL.
Capital simulado: **5 000 €**. Infraestructura: **100% gratuita**.

---

## Arquitectura

```
Binance API (datos OHLCV)
       ↓
GitHub Actions (cron cada hora, gratis)
       ↓
Kronos-small (modelo IA de señales)
       ↓
Gestor de riesgo (stop-loss, sizing, max 3 posiciones)
       ↓
Supabase (base de datos, gratis)  ←→  Dashboard Vercel (gratis)
```

---

## Parámetros del bot

| Parámetro | Valor | Descripción |
|---|---|---|
| Capital inicial | 5 000 € | Simulado |
| Pares | BTC/USDT, ETH/USDT, SOL/USDT | Binance |
| Timeframe | 1h | Velas horarias |
| Max posiciones | 3 | Simultáneas |
| Tamaño posición | ~33% del portfolio | Equal weight |
| Threshold entrada | +1.5% | Retorno esperado mínimo |
| Stop-loss | -2% | Por posición |
| Comisión simulada | 0.1% | Por lado |
| Pausa drawdown | -10% | Desde el máximo histórico |

---

## Setup paso a paso

### Paso 1 — Crea el repositorio en GitHub

1. Ve a **github.com/new** y crea un repositorio **público** (necesario para Actions gratuito ilimitado)
2. Nómbralo `kronos-paper-trader`
3. Sube todos los ficheros de este proyecto:
   ```bash
   git init
   git add .
   git commit -m "init"
   git branch -M main
   git remote add origin https://github.com/TU_USUARIO/kronos-paper-trader.git
   git push -u origin main
   ```

---

### Paso 2 — Crea el proyecto en Supabase

1. Ve a **supabase.com** → "New project"
2. Dale un nombre (ej: `kronos-trader`) y una contraseña segura
3. Una vez creado, ve a **SQL Editor** → "New query"
4. Pega el contenido de `schema.sql` y pulsa **Run**
5. Verás que se crean las tablas `portfolio`, `trades` y `signals`

**Copia estas dos claves** (las necesitarás en el paso 3 y 4):
- Ve a **Settings → API**
- `Project URL` → para el bot y el dashboard
- `service_role` (secret key) → **solo para el bot** (nunca la pongas en el dashboard)
- `anon` (public key) → para el dashboard

---

### Paso 3 — Añade los secrets a GitHub Actions

1. En tu repo de GitHub: **Settings → Secrets and variables → Actions → New repository secret**
2. Añade dos secrets:

| Name | Value |
|---|---|
| `SUPABASE_URL` | Tu Project URL de Supabase |
| `SUPABASE_KEY` | Tu **service_role** key de Supabase |

---

### Paso 4 — Primera ejecución manual

1. En GitHub, ve a tu repo → **Actions → Kronos Paper Trader**
2. Pulsa **"Run workflow"** → **"Run workflow"**
3. Observa los logs en tiempo real (tarda ~5-8 min en la primera ejecución por la descarga del modelo)
4. Si ves `━━━ Fin total=5000.xx€ ROI=+0.00% ━━━` → todo funciona

A partir de ahí, se ejecutará automáticamente cada hora.

---

### Paso 5 — Despliega el dashboard en Vercel

1. Ve a **vercel.com** → "Add New Project" → "Import Git Repository"
2. Selecciona `kronos-paper-trader`
3. En **"Root Directory"** escribe: `dashboard`
4. Deja el resto por defecto → **Deploy**
5. Abre la URL que te da Vercel
6. En el modal de configuración, introduce:
   - Tu `Project URL` de Supabase
   - Tu **anon** key de Supabase (la pública, NO la service_role)
7. Pulsa "Guardar" → verás el dashboard con los datos en tiempo real

---

## ¿Cómo interpretar los resultados?

Tras un mes de funcionamiento, las métricas clave son:

- **ROI > 0%**: el sistema hubiera ganado dinero
- **Win rate > 50%**: más de la mitad de las operaciones fueron ganadoras
- **Max drawdown < 10%**: el sistema se mantuvo bajo control de riesgo
- **Sharpe ratio > 1**: buen retorno ajustado al riesgo (lo puedes calcular con los datos de Supabase)

Si el ROI es positivo y estable durante el mes, entonces tiene sentido plantearse pasar al trading real con capital pequeño (100-500€) y escalar gradualmente.

---

## Ajustar parámetros

Todo se controla desde las primeras líneas de `bot.py`. Puedes hacer fork del proyecto y experimentar:

- Subir `ENTRY_THRESH` → el bot opera menos pero con más confianza
- Bajar `STOP_LOSS` → recorta pérdidas más rápido
- Cambiar `PAIRS` → añadir BNB/USDT, AVAX/USDT, etc.
- Aumentar `SAMPLE_COUNT` → señales más estables (pero más lentas)

---

## Ficheros del proyecto

```
kronos-paper-trader/
├── bot.py                          ← lógica principal del bot
├── requirements.txt                ← dependencias Python
├── .github/
│   └── workflows/
│       └── trading_bot.yml         ← cron de GitHub Actions
├── schema.sql                      ← tablas de Supabase
├── dashboard/
│   └── index.html                  ← interfaz web (Vercel)
└── README.md                       ← este fichero
```

---

## Preguntas frecuentes

**¿Gasta dinero real?**
No. Es 100% paper trading. No se conecta a ningún broker ni wallet. Simula las operaciones con lógica interna y precios reales de Binance.

**¿Puedo añadir más pares?**
Sí. Edita `PAIRS` en `bot.py`. Ten en cuenta que cada par tarda ~1-2 minutos más en el run.

**¿Qué pasa si el workflow falla?**
GitHub lo reintentará en la siguiente hora. El estado del portfolio en Supabase no se corrompe porque cada run solo añade filas nuevas (nunca modifica las antiguas, salvo al cerrar trades).

**¿Puedo usarlo con Bybit, Kraken u otro exchange?**
Sí. Cambia `ccxt.binance` por `ccxt.bybit` o `ccxt.kraken` en `bot.py`. El resto del código no cambia.
