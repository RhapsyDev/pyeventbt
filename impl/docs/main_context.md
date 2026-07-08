# main_context — Memoria de Contexto Centralizado

> **Instrucción de Activación para la IA:**
> Cuando el usuario inicie el chat con la frase **"Lee el contexto y prepárate"**, deberás:
> 1. Leer este archivo en su totalidad para comprender los objetivos del proyecto y la arquitectura de PyEventBT.
> 2. Situarte en el punto de desarrollo sin reexplicar conceptos básicos del framework.
> 3. Responder confirmando que has asimilado la información y quedar a la espera de que el usuario te indique qué archivo de estrategia específico debes leer o qué tarea implementar.


---

## Tabla de Contenidos

1. [Introducción y Core del Framework](#1-introducción-y-core-del-framework)
2. [Arquitectura de Módulos de PyEventBT](#2-arquitectura-de-módulos-de-pyeventbt)
3. [Ejemplos de Referencia en el Repositorio](#3-ejemplos-de-referencia-en-el-repositorio)
4. [Entorno de Trabajo Actual (Stack Local)](#4-entorno-de-trabajo-actual-stack-local)
5. [Estrategias del Proyecto](#5-estrategias-del-proyecto)
6. [Instrucciones de Comportamiento para la IA](#6-instrucciones-de-comportamiento-para-la-ia)

---

## 1. Introducción y Core del Framework

### ¿Qué es PyEventBT?

**PyEventBT** (`v0.0.13`) es una librería Python de código abierto (Apache 2.0) diseñada para el **backtesting orientado a eventos** (*Event-Driven*) de estrategias de trading algorítmico y su **ejecución en vivo** a través de MetaTrader 5.

- **Autores:** Marti Castany, Alain Porto
- **PyPI:** `pip install pyeventbt`
- **Repositorio original:** [github.com/marticastany/pyeventbt](https://github.com/marticastany/pyeventbt)
- **Documentación oficial:** [pyeventbt.com](https://pyeventbt.com)

### Event-Driven vs. Vectorial: La diferencia fundamental

| Característica | Framework Vectorial | PyEventBT (Event-Driven) |
|---|---|---|
| **Paradigma** | Opera sobre arrays completos de datos históricos | Procesa los datos bar-a-bar, como ocurriría en vivo |
| **Look-Ahead Bias** | Alto riesgo si no se maneja con cuidado | **Eliminado por diseño**: la estrategia solo ve los datos disponibles en ese instante |
| **Realismo** | Bajo (opera en batch) | **Alto**: simula condiciones reales de mercado secuencialmente |
| **Transición Backtest→Live** | Requiere reescritura del código | **Código unificado**: la misma función se ejecuta en backtest y en live |
| **Latencia de señal** | Inexistente (procesa todo a la vez) | Controlada: las señales se generan para la siguiente barra |

### Flujo de eventos (pipeline)

```
BarEvent (OHLCV) → SignalEvent → [Sizing Engine] → [Risk Engine] → OrderEvent → ExecutionEngine → FillEvent → Portfolio
```

Cada evento es procesado **secuencialmente**, garantizando que la estrategia nunca accede a datos futuros.

### Documentación de Referencia Obligatoria

| Sección | URL |
|---|---|
| Instalación | https://pyeventbt.com/getting-started/installation/ |
| Guía Rápida | https://pyeventbt.com/getting-started/quickstart-guide/ |
| Arquitectura | https://pyeventbt.com/getting-started/how-it-works/ |
| Changelog | https://pyeventbt.com/changelog/ |

---

## 2. Arquitectura de Módulos de PyEventBT

El repositorio tiene la siguiente organización clave, aislando completamente el framework de la implementación:

*   **`pyeventbt/`**: Core framework (eventos, portfolio, data, ejecución). No se modifica.
*   **`impl/`**: Todo el código personalizado, estrategias y scripts de testing.
    *   **`brokers/`**: Lógicas de comisiones (Vantage), reutilizables.
    *   **`strategies/`**: Contiene implementaciones de estrategias como packages modulares.
        *   **`orb_advanced/`**: Estrategia principal refactorizada con `main.py` (entry point CLI).
    *   **`backtest/`**: Entorno de testing centralizado.
        *   **`run_backtest.py`**: Único script para correr múltiples combinaciones a la vez y generar un reporte unificado.
        *   **`data_downloader.py`**: Script para descarga de datos.
        *   **`historical_data/`**: Datasets en formato CSV/Parquet.
        *   **`results/`**: Tablas resumen (.txt) generadas tras las simulaciones.
    *   **`docs/`**: Documentación específica de tus implementaciones.

### 2.1 Strategy (Orquestador Principal)

El objeto `Strategy` es el punto de entrada de todo el sistema. Registra la función de señal mediante el decorador `@strategy.custom_signal_engine(...)`, configura los motores de sizing y riesgo, y lanza el backtest o el trading en vivo.

```python
strategy = Strategy(logging_level=logging.INFO)

@strategy.custom_signal_engine(strategy_id=strategy_id, strategy_timeframes=strategy_timeframes)
def my_strategy(event: BarEvent, modules: Modules):
    ...

strategy.configure_predefined_sizing_engine(MinSizingConfig())
strategy.configure_predefined_risk_engine(PassthroughRiskConfig())
strategy.backtest(...)  # o strategy.run_live(...)
```

### 2.2 Data Provider — Conector de Datos

**Rol:** Actúa como la única fuente de verdad para los datos de mercado dentro de la función de estrategia. En backtest utiliza datos históricos (CSV o descarga automática); en live se conecta al feed de MT5 en tiempo real.

**Acceso:** `modules.DATA_PROVIDER`

**Documentación:** https://pyeventbt.com/modules/data-provider/

**Métodos clave:**

```python
# Obtener las últimas N barras de un símbolo y timeframe
bars = modules.DATA_PROVIDER.get_latest_bars(symbol, timeframe, n_bars)
# Retorna: polars.DataFrame con columnas: open, high, low, close, volume

# Obtener el último tick (precio bid/ask en tiempo real)
tick = modules.DATA_PROVIDER.get_latest_tick(symbol)
# Retorna: dict con keys 'bid' y 'ask'
```

> **Restricción crítica:** Dentro de la función de señal, **solo** se debe acceder a los datos a través de `modules.DATA_PROVIDER`. Nunca usar variables globales de datos para preservar el correcto aislamiento temporal del backtester.

---

### 2.3 Execution Engine — Enrutador de Órdenes

**Rol:** Recibe los `OrderEvent` generados por el pipeline y los enruta: en backtest los simula internamente; en live los envía directamente a MetaTrader 5 vía la API oficial de MT5.

**Acceso:** `modules.EXECUTION_ENGINE`

**Documentación:** https://pyeventbt.com/modules/execution-engine/

**Métodos clave:**

```python
# Cerrar todas las posiciones cortas abiertas de la estrategia en un símbolo
modules.EXECUTION_ENGINE.close_strategy_short_positions_by_symbol(symbol)

# Cerrar todas las posiciones largas abiertas de la estrategia en un símbolo
modules.EXECUTION_ENGINE.close_strategy_long_positions_by_symbol(symbol)
```

> **Nota arquitectónica:** Las órdenes no se envían directamente desde la estrategia. La estrategia emite `SignalEvent`, que fluye por el Sizing Engine → Risk Engine → `OrderEvent` → Execution Engine. El acceso directo de cierre de posiciones es la única excepción explícita a este flujo.

---

### 2.4 Portfolio & Risk Manager — Control de Balance y Posiciones

**Rol:** Mantiene el estado completo de la cuenta en tiempo real durante el backtest y en live: balance, equity, posiciones abiertas por símbolo y estrategia, P&L flotante y realizado, y margen utilizado.

**Acceso:** `modules.PORTFOLIO`

**Documentación:** https://pyeventbt.com/modules/portfolio/

**Métodos clave:**

```python
# Consultar número de posiciones abiertas de esta estrategia para un símbolo
positions = modules.PORTFOLIO.get_number_of_strategy_open_positions_by_symbol(symbol)
# Retorna: dict con keys 'LONG' y 'SHORT' (int)
```

---

### 2.5 Signal Engine & Sizing Engine

**Signal Engine:** Es la propia función decorada con `@strategy.custom_signal_engine`. Recibe `BarEvent` y debe retornar una lista de `SignalEvent` (o `None`/lista vacía si no hay señal).

**Sizing Engine:** Calcula el tamaño (volumen/lotaje) de cada orden. Se configura con clases predefinidas:
- `MinSizingConfig()` — Mínimo lote permitido por el símbolo
- Configuraciones custom para sizing por riesgo (% del capital, ATR, etc.)

---

### 2.6 Referencia de Eventos (Event Registry)

El flujo interno de eventos sigue este orden estricto:

| Evento | Generado por | Consumido por | Contenido |
|---|---|---|---|
| `BarEvent` | Data Provider | Strategy (Signal Engine) | symbol, datetime, timeframe, OHLCV |
| `SignalEvent` | Signal Engine (estrategia) | Sizing Engine → Risk Engine | symbol, strategy_id, signal_type, order_type, price, sl, tp |
| `OrderEvent` | Risk Engine (tras validación) | Execution Engine | Orden validada con tamaño calculado |
| `FillEvent` | Execution Engine | Portfolio | Confirmación de ejecución con precio real |

**Documentación de referencia:**
- Core Architecture: https://pyeventbt.com/reference/core-architecture/
- Events: https://pyeventbt.com/reference/events/

---

### 2.7 Contexto de Ejecución

```python
# Distinguir si estamos en backtest o en live dentro de la función de señal
if modules.TRADING_CONTEXT == "BACKTEST":
    time_generated = event.datetime + signal_timeframe.to_timedelta()
else:
    time_generated = datetime.now()
```

---

## 3. Ejemplos de Referencia en el Repositorio

Los siguientes archivos en la **raíz del fork local** actúan como plantillas de diseño canónico para nuestra estrategia ORB. Se deben consultar antes de escribir cualquier código nuevo.

### 3.1 MA Crossover — Plantilla base de estrategia

**Archivo local:** `c:\trading\bots\pyeventbt\example_ma_crossover.py`
**Documentación:** https://pyeventbt.com/strategy-examples/ma-crossover/

**Patrón de código demostrado:**
- Estructura completa de `@strategy.custom_signal_engine`
- Uso de `modules.DATA_PROVIDER.get_latest_bars()` y `get_latest_tick()`
- Uso de `modules.PORTFOLIO.get_number_of_strategy_open_positions_by_symbol()`
- Cierre de posiciones opuestas antes de abrir nuevas
- Construcción correcta de `SignalEvent` con todos sus parámetros
- Switch backtest/live para `time_generated`
- Configuración de backtest con `strategy.backtest(...)`
- Configuración comentada de live trading con `Mt5PlatformConfig`

```python
# Imports canónicos de PyEventBT (extraídos del ejemplo)
from pyeventbt import (
    Strategy, BarEvent, SignalEvent, Modules,
    StrategyTimeframes, PassthroughRiskConfig, MinSizingConfig
)
from pyeventbt.events.events import OrderType, SignalType
from pyeventbt.strategy.core.account_currencies import AccountCurrencies
from pyeventbt.indicators import SMA
```

---

### 3.2 Bollinger Bands Breakout — Plantilla de estrategia de ruptura

**Archivo local:** `c:\trading\bots\pyeventbt\example_bbands_breakout.py`
**Documentación:** https://pyeventbt.com/strategy-examples/bollinger-bands-breakout/

**Patrón de código demostrado:**
- Lógica de breakout (ruptura de niveles) → **Referencia directa para la lógica ORB**
- Uso del indicador `BollingerBands` del módulo `pyeventbt.indicators`
- Gestión de señales de entrada y salida basadas en niveles dinámicos calculados por barra
- Uso de `OrderType.MARKET` para entrada inmediata

---

### 3.3 Quantdle Integration — Fuente de datos alternativa

**Archivo local:** `c:\trading\bots\pyeventbt\example_quantdle_ma_crossover.py`
**Documentación:** https://pyeventbt.com/strategy-examples/quantdle-data-integration/

**Patrón de código demostrado:**
- Integración con proveedor de datos externo (Quantdle) para backtest con datos de alta calidad
- Configuración de `DataProviderConfig` personalizado

---

## 4. Entorno de Trabajo Actual (Stack Local)

### 4.1 Metadata del Proyecto

| Parámetro | Valor |
|---|---|
| **Nombre del paquete** | `pyeventbt` |
| **Versión actual** | `0.0.13` |
| **Licencia** | Apache 2.0 |
| **Ruta del workspace** | `c:\trading\bots\pyeventbt\` |

### 4.2 Intérprete y Dependencias

- **Entorno virtual activo:** `(venv)` — ubicado en `c:\trading\bots\pyeventbt\venv\`
- **Python requerido:** `^3.12` (restricción de Numba: `>=3.10, <3.14`)
- **Gestor de paquetes:** Poetry / pip

**Dependencias principales:**

```toml
python       = "^3.12"
polars       = "^1.35.0"    # DataFrames de alto rendimiento (retornados por DATA_PROVIDER)
numpy        = "^2.0.0"     # Cálculo numérico para indicadores
pandas       = "^2.2.3"     # Compatibilidad general
numba        = "^0.62.1"    # JIT compilation (restricción de versión Python)
pydantic     = "^2.12.3"    # Validación de modelos de eventos
matplotlib   = "^3.7.0"     # Gráficas de backtest
scipy        = "^1.10.0"    # Análisis estadístico
scikit-learn = "^1.3.0"     # ML (disponible para features avanzadas)
```

> **Nota sobre polars:** `modules.DATA_PROVIDER.get_latest_bars()` retorna un `polars.DataFrame`.
> Usar la API de Polars para manipulación de datos (`.select()`, `.to_numpy()`, `.height`, etc.).



### 4.4 IDE y Herramientas

| Herramienta | Detalle |
|---|---|
| **IDE** | Antigravity IDE (entorno unificado con terminal y agente integrado) |
| **Agente** | Claude Sonnet (Thinking) |
| **Terminal** | PowerShell (Windows) |

### 4.5 Conector Live — MetaTrader 5

- **Estado:** Conectado y validado
- **Plataforma:** MetaTrader 5 (instalado localmente)
- **Cuenta:** Demo — Servidor `VantageMarkets-Demo`
- **Bróker:** Vantage Markets

**Plantilla de configuración live:**

```python
from pyeventbt import Mt5PlatformConfig

mt5_config = Mt5PlatformConfig(
    path="C:\\Program Files\\MetaTrader 5\\terminal64.exe",
    login=TU_LOGIN,
    password="TU_PASSWORD",
    server="VantageMarkets-Demo",
    timeout=60000,
    portable=False
)

strategy.run_live(
    mt5_configuration=mt5_config,
    strategy_id=strategy_id,
    initial_capital=100000,
    symbols_to_trade=symbols_to_trade,
    heartbeat=0.1
)
```

---

## 5. Estrategias del Proyecto

Las estrategias desarrolladas o en proceso de desarrollo se encuentran documentadas de manera individual en sus respectivas carpetas dentro de `docs/strategies/`.

### 5.1 Listado de Estrategias

1.  **Backtest de combinación única**: `python impl/strategies/orb_advanced/main.py --mode BACKTEST --start-date 2026-06-01 --end-date 2026-07-01 --entry BREAKOUT --sl OPPOSITE_RANGE --tp FIXED_1R`
2.  **Backtest de campaña completa**: Edita y ejecuta `python impl/backtest/run_backtest.py`
3.  **Análisis de resultados**: Los logs y estadísticas se guardan en `impl/backtest/results/`.
4.  **Live Trading**: `python impl/strategies/orb_advanced/main.py --mode LIVE`
- Todas las estrategias están ubicadas en la carpeta `impl/strategies/`. Debes consultar el `readme.md` de cada estrategia para entender su funcionamiento en `impl/docs/strategies/<strategy_name>`.

---

## 6. Instrucciones de Comportamiento para la IA

### Regla 1 — Activación por Frase Clave

Cuando el usuario escriba **"Lee el contexto y prepárate"**, deberás asimilar este documento de contexto y responder con un breve resumen de los objetivos del proyecto y la fase actual. Quedarás a la espera de que el usuario te indique qué archivo de estrategia específico leer o qué tarea abordar.


### Regla 2 — Diseño de Código Orientado a Eventos

**OBLIGATORIO:** Todo código propuesto para las estrategias debe:

1. **Respetar el patrón del decorador** `@strategy.custom_signal_engine(...)`.
2. **Acceder a datos SOLO** a través de `modules.DATA_PROVIDER` (nunca variables globales de datos).
3. **Retornar siempre** una lista de `SignalEvent` o `None` / lista vacía.
4. **Gestionar el tiempo** distinguiendo entre backtest y live:

```python
if modules.TRADING_CONTEXT == "BACKTEST":
    time_generated = event.datetime + signal_timeframe.to_timedelta()
else:
    time_generated = datetime.now()
```

5. **No introducir look-ahead bias**: solo procesar el bar actual y barras pasadas.
6. **Mantener el estado interno** usando variables de módulo (Python module scope) o clases, nunca dentro del objeto `event`.

### Regla 3 — Estándares de Calidad

- Toda propuesta de código debe incluir **docstrings** explicando la lógica algorítmica.
- Los parámetros de la estrategia se definen como **constantes de módulo** al inicio del archivo.
- Preferir `polars` sobre `pandas` para manipulación de DataFrames de barras.
- Usar `Decimal` para precios y niveles de SL/TP.

### Regla 4 — Separación Backtest/Live

El código debe ser **agnóstico** al modo de ejecución. La única diferencia permitida es el bloque `if modules.TRADING_CONTEXT`:

```python
# CORRECTO — el mismo código funciona en backtest y live
@strategy.custom_signal_engine(strategy_id=strategy_id, strategy_timeframes=timeframes)
def orb_strategy(event: BarEvent, modules: Modules):
    if modules.TRADING_CONTEXT == "BACKTEST":
        time_generated = event.datetime + signal_timeframe.to_timedelta()
    else:
        time_generated = datetime.now()
    ...
```

### Regla 5 — Nunca Reexplicar Fundamentos

Asumiendo que este contexto ha sido leído, NO es necesario explicar en sesiones subsiguientes:
- Qué es un BarEvent, SignalEvent, etc.
- Por qué se usa event-driven vs. vectorial
- Cómo instalar el entorno o configurar MT5

En sesiones posteriores, ir directo a la implementación.

---

## Historial de Sesiones

| Fecha | Fase | Tarea realizada |
|---|---|---|
| 2026-06-29 | Fase 0 | Setup completo: entorno virtual, dependencias, conexión MT5 Demo (VantageMarkets-Demo) validada. Creación de este archivo de contexto centralizado. |

---

*Documento generado el 2026-06-29 · Versión PyEventBT: 0.0.13*
