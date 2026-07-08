"""
config.py — Configuración global de la estrategia ORB Advanced.

Todas las constantes y parámetros de la estrategia viven aquí.
main.py lee este módulo y puede sobreescribir sus valores vía argparse
antes de instanciar la estrategia.
"""

import os
import sys
from datetime import datetime, time
from enum import Enum
from zoneinfo import ZoneInfo

# Carga credenciales desde .env si python-dotenv está disponible
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
    load_dotenv(_env_path)
except ImportError:
    pass

# =============================================================================
# Zona horaria
# =============================================================================
BROKER_TZ = ZoneInfo("Etc/GMT-3")   # Vantage UTC+3 en verano
LOCAL_TZ  = ZoneInfo("Europe/Madrid")  # CEST = UTC+2 en verano

# =============================================================================
# Modo de ejecución (BACKTEST | LIVE)
# =============================================================================
MODE = "BACKTEST"
# MODE = "LIVE"

# =============================================================================
# Rango de descarga de datos históricos
# =============================================================================
DATA_FROM = datetime(year=2026, month=6, day=1, tzinfo=None)
DATA_TO   = datetime(year=2027, month=8, day=1, tzinfo=None)

# Rango de simulación de backtest (subconjunto de datos descargados)
BT_FROM = datetime(year=2026, month=6, day=1, tzinfo=None)
BT_TO   = datetime(year=2026, month=7, day=1, tzinfo=None)

# =============================================================================
# Credenciales MT5 — cargadas desde .env / variables de entorno
# =============================================================================
MT5_PATH     = "C:\\Program Files\\MetaTrader 5\\terminal64.exe"
MT5_LOGIN    = int(os.environ.get("MT5_LOGIN", "0") or "0")
MT5_PASSWORD = os.environ.get("MT5_PASSWORD", "")
MT5_SERVER   = os.environ.get("MT5_SERVER", "VantageMarkets-Demo")
MT5_TIMEOUT  = 60000

# =============================================================================
# Capital inicial
# =============================================================================
STARTING_CAPITAL = 1000

# =============================================================================
# Identificador de estrategia
# =============================================================================
STRATEGY_ID = "999001"

# =============================================================================
# Instrumentos a operar
# =============================================================================
SYMBOL_CATEGORIES = {
    "metals":      ["XAUUSD"],
    "indices":     ["SP500", "NAS100"],
    "commodities": ["XTIUSD"],
    "crypto":      ["BTCUSD", "ETHUSD"],
}
SYMBOLS: list[str] = [s for cat in SYMBOL_CATEGORIES.values() for s in cat]

# Mapeo de sufijos MT5 para cuentas swap-free (live únicamente)
MT5_SYMBOL_MAP: dict[str, str] = {"XAUUSD": "XAUUSD+", "XTIUSD": "USOUSD"}

# Símbolos que usa la estrategia internamente (sin sufijos)
STRATEGY_SYMBOLS: list[str] = SYMBOLS  # sobreescrito en main.py tras saber el MODE

# =============================================================================
# Gestión de riesgo y capital
# =============================================================================
RISK_PCT        = 2.0                        # Riesgo total en % de la cuenta
RR_RATIO        = 1.0                        # R:R fijo (para TP_FIXED_1R / TP_FIXED_1_5R)

# =============================================================================
# Sesiones de trading
# =============================================================================
from datetime import date

SESSION_END_HOUR = time(23, 0)   # Cierre forzado EOD (hora broker)

# Festivos importados desde el módulo de festivos de custom_strategies
# (se mantiene en su ubicación original para no romper la importación)
try:
    from impl.strategies.orb_advanced.market_holidays import SESSION_HOLIDAYS
except ImportError:
    SESSION_HOLIDAYS = {"NY": [], "LONDON": [], "ASIA": []}

SESSIONS: dict = {
    "LONDON": {
        "start_time": time(10, 0),
        "max_wait_minutes": 60,
        "enabled": False,
        "end_time": None,
        "holidays": SESSION_HOLIDAYS.get("LONDON", []),
    },
    "NY": {
        "start_time": time(16, 30),
        "max_wait_minutes": 60,
        "enabled": True,
        "end_time": None,
        "holidays": SESSION_HOLIDAYS.get("NY", []),
    },
    "ASIA": {
        "start_time": time(1, 0),
        "max_wait_minutes": 60,
        "enabled": True,
        "end_time": None,
        "holidays": SESSION_HOLIDAYS.get("ASIA", []),
    },
    "TEST": {
        "start_time": time(9, 30),
        "max_wait_minutes": 30,
        "enabled": False,
        "end_time": None,
        "holidays": [],
    },
}

# =============================================================================
# Timeframes
# =============================================================================
from pyeventbt import StrategyTimeframes

ORB_BASE_TIMEFRAME  = StrategyTimeframes.FIVE_MIN   # Timeframe de formación del rango
BREAKOUT_TIMEFRAME  = StrategyTimeframes.ONE_MIN    # Timeframe de detección de ruptura

# =============================================================================
# Métodos de entrada, SL y TP
# =============================================================================

class EntryMethod(str, Enum):
    BREAKOUT = "BREAKOUT"   # Entrada inmediata al romper el ORB
    RETEST   = "RETEST"     # Espera pullback al borde del ORB


class SLMethod(str, Enum):
    OPPOSITE_RANGE = "OPPOSITE_RANGE"  # SL en extremo opuesto del ORB
    MID_RANGE      = "MID_RANGE"       # SL al 50% del rango ORB


class TPMethod(str, Enum):
    FIXED_1R   = "FIXED_1R"    # TP fijo a 1:1 R:R
    FIXED_1_5R = "FIXED_1_5R"  # TP fijo a 1:1.5 R:R
    TRAILING   = "TRAILING"    # Trailing stop sin TP fijo


# Valores por defecto (sobreescribibles vía argparse en main.py)
ENTRY_METHOD: EntryMethod = EntryMethod.BREAKOUT
SL_METHOD:    SLMethod    = SLMethod.OPPOSITE_RANGE
TP_METHOD:    TPMethod    = TPMethod.FIXED_1R

# =============================================================================
# Parámetros del Trailing Stop
# =============================================================================
TRAILING_ATR_MULTIPLIER = 1.5  # Distancia SL = 1.5 × ATR (estándar Chandelier Exit)
TRAILING_BE_R           = 0.5  # Mueve SL a breakeven cuando precio alcanza +0.5R
TRAILING_ACTIVATE_R     = 1.0  # Activa trailing cuando precio alcanza +1R

# =============================================================================
# Logging
# =============================================================================
VERBOSE_MODE = False

# =============================================================================
# Broker
# =============================================================================
from impl.brokers import RawECN
BROKER = RawECN()
