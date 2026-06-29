"""
PyEventBT - ORB Simple Strategy
"""

from pyeventbt import (
    Strategy, BarEvent, SignalEvent, Modules, StrategyTimeframes,
    PassthroughRiskConfig, Mt5PlatformConfig
)
from pyeventbt.sizing_engine.core.configurations.sizing_engine_configurations import RiskPctSizingConfig
from pyeventbt.events.events import OrderType, SignalType
from pyeventbt.strategy.core.account_currencies import AccountCurrencies
from datetime import datetime, time
from decimal import Decimal
import logging

logger = logging.getLogger("pyeventbt")

# =============================================================================
# STRATEGY CONFIGURATION
# =============================================================================
strategy_id = "ORB_SIMPLE_01"
strategy = Strategy(logging_level=logging.INFO)

# Configurar timeframe principal (M15 es ideal para ORB de 30 mins)
signal_timeframe = StrategyTimeframes.FIFTEEN_MIN
strategy_timeframes = [signal_timeframe]

# Categorías de Símbolos a operar
SYMBOLS = {
    "FOREX": ["EURUSD"],
    "METALS": ["XAUUSD"],
    "CRYPTO": ["BTCUSD"],
    "INDICES": ["US30", "NAS100"]
}
# Por ahora empezamos con XAUUSD
symbols_to_trade = SYMBOLS["FOREX"]

# Riesgo y Capital
starting_capital = 2000
risk_per_trade_pct = 2.0  # Arriesgar 2% de la cuenta por trade
rr_ratio = Decimal('1.0') # Ratio Riesgo/Beneficio 1:1 para Take Profit

# Horarios de Sesiones (Ajustar a la hora del servidor del Broker, ej. Vantage es UTC+3 en verano)
# El flag "enabled" activa o desactiva la sesión para el backtest/live.
SESSIONS = {
    "ASIA":   {"start": time(1, 0),  "duration_minutes": 30, "enabled": False},
    "LONDON": {"start": time(10, 0), "duration_minutes": 30, "enabled": False},
    "NY":     {"start": time(15, 30), "duration_minutes": 30, "enabled": False},
    # Sesión falsa para pruebas en vivo inmediatas (Ajusta la hora a tu hora actual en MT5)
    "TEST":   {"start": time(18, 0),  "duration_minutes": 15, "enabled": True} 
}
SESSION_END_HOUR = time(23, 0) # Hora forzada de cierre de sesión

# =============================================================================
# STATE TRACKING (MODULE LEVEL)
# =============================================================================
orb_high: dict[str, Decimal] = {s: Decimal('-1') for s in symbols_to_trade}
orb_low: dict[str, Decimal] = {s: Decimal('999999') for s in symbols_to_trade}
orb_defined: dict[str, bool] = {s: False for s in symbols_to_trade}
trade_taken_today: dict[str, bool] = {s: False for s in symbols_to_trade}
current_trading_date: dict[str, datetime | None] = {s: None for s in symbols_to_trade}
active_session_name: dict[str, str | None] = {s: None for s in symbols_to_trade}


def is_time_in_window(current_time: time, start_time: time, duration_minutes: int) -> bool:
    """Check if current time is within the ORB formation window."""
    curr_mins = current_time.hour * 60 + current_time.minute
    start_mins = start_time.hour * 60 + start_time.minute
    end_mins = start_mins + duration_minutes
    return start_mins <= curr_mins < end_mins

def get_active_session(current_time: time) -> str | None:
    """Return the name of the session if we are in its ORB formation window."""
    for session_name, config in SESSIONS.items():
        if config["enabled"]:
            if is_time_in_window(current_time, config["start"], config["duration_minutes"]):
                return session_name
    return None

def is_after_session_formation(current_time: time, session_name: str) -> bool:
    """Check if the ORB window has finished but the day hasn't ended."""
    if session_name not in SESSIONS: return False
    config = SESSIONS[session_name]
    start_mins = config["start"].hour * 60 + config["start"].minute
    end_mins = start_mins + config["duration_minutes"]
    curr_mins = current_time.hour * 60 + current_time.minute
    end_of_day_mins = SESSION_END_HOUR.hour * 60 + SESSION_END_HOUR.minute
    return end_mins <= curr_mins < end_of_day_mins

# =============================================================================
# SIGNAL ENGINE
# =============================================================================
@strategy.custom_signal_engine(strategy_id=strategy_id, strategy_timeframes=strategy_timeframes)
def orb_simple_strategy(event: BarEvent, modules: Modules):
    """
    Opening Range Breakout (ORB) Strategy.
    1. Define el rango de apertura (ORB_HIGH, ORB_LOW) durante la ventana especificada.
    2. Espera ruptura del rango con vela cerrada por encima o por debajo.
    3. Calcula TP/SL basado en Riesgo/Recompensa 1:1.
    4. El sizing se maneja automáticamente por el RiskPctSizingConfig (2%).
    """
    if event.timeframe != signal_timeframe:
        return
        
    symbol = event.symbol
    signal_events = []
    
    current_time = event.datetime.time()
    current_date = event.datetime.date()
    
    # 1. Reset diario de variables de estado
    if current_trading_date[symbol] != current_date:
        current_trading_date[symbol] = current_date
        trade_taken_today[symbol] = False
        orb_defined[symbol] = False
        orb_high[symbol] = Decimal('-1')
        orb_low[symbol] = Decimal('999999')
        active_session_name[symbol] = None
        
    # 2. Cierre forzado de fin de sesión (para no dejar abiertas overnight)
    if current_time >= SESSION_END_HOUR:
        open_positions = modules.PORTFOLIO.get_number_of_strategy_open_positions_by_symbol(symbol)
        if open_positions['TOTAL'] > 0:
            logger.info(f"{event.datetime} - Cierre fin de dia para {symbol}")
            modules.EXECUTION_ENGINE.close_all_strategy_positions_by_symbol(symbol)
        return
        
    # 3. Comprobar si estamos formando un nuevo rango ORB
    current_session = get_active_session(current_time)
    if current_session:
        active_session_name[symbol] = current_session
        orb_defined[symbol] = False # Todavía se está formando
        
        bar_high = Decimal(str(event.data.high_f))
        bar_low = Decimal(str(event.data.low_f))
        
        # Acumular máximos y mínimos de las velas en esta ventana
        if bar_high > orb_high[symbol]:
            orb_high[symbol] = bar_high
        if bar_low < orb_low[symbol]:
            orb_low[symbol] = bar_low
            
        return # No operar mientras se forma el rango
        
    # 4. Finalizó la ventana de formación de rango
    if active_session_name[symbol] and not orb_defined[symbol]:
        if is_after_session_formation(current_time, active_session_name[symbol]):
            orb_defined[symbol] = True
            logger.info(f"{event.datetime} - {symbol} Rango {active_session_name[symbol]} DEFINIDO | ALTO: {orb_high[symbol]} | BAJO: {orb_low[symbol]}")
            
    # 5. Lógica de Ruptura (Breakout)
    if orb_defined[symbol] and not trade_taken_today[symbol]:
        open_positions = modules.PORTFOLIO.get_number_of_strategy_open_positions_by_symbol(symbol)
        
        # Solo abrir si no hay otra operación de esta estrategia activa
        if open_positions['TOTAL'] == 0:
            bar_close = Decimal(str(event.data.close_f))
            
            signal_type = None
            order_price = Decimal('0')
            sl = Decimal('0')
            tp = Decimal('0')
            
            # Ruptura Alcista
            if bar_close > orb_high[symbol]:
                signal_type = SignalType.BUY
                order_price = bar_close 
                sl = orb_low[symbol] # SL conservador al otro lado del rango
                distance = order_price - sl
                tp = order_price + (distance * rr_ratio) # TP 1:1
                
            # Ruptura Bajista
            elif bar_close < orb_low[symbol]:
                signal_type = SignalType.SELL
                order_price = bar_close
                sl = orb_high[symbol]
                distance = sl - order_price
                tp = order_price - (distance * rr_ratio)
                
            if signal_type:
                trade_taken_today[symbol] = True # Limitar a 1 trade por dia
                
                # Ajuste de tiempo de generacion para evitar lookahead bias
                if modules.TRADING_CONTEXT == "BACKTEST":
                    time_generated = event.datetime + signal_timeframe.to_timedelta()
                else:
                    time_generated = datetime.now()
                    
                    # En modo LIVE, usar el último tick real para mayor precision
                    last_tick = modules.DATA_PROVIDER.get_latest_tick(symbol)
                    order_price = Decimal(str(last_tick['ask'] if signal_type == SignalType.BUY else last_tick['bid']))
                
                signal_events.append(SignalEvent(
                    symbol=symbol,
                    time_generated=time_generated,
                    strategy_id=strategy_id,
                    signal_type=signal_type,
                    order_type=OrderType.MARKET,
                    order_price=order_price,
                    sl=sl,
                    tp=tp
                ))
                logger.info(f"{event.datetime} - SEÑAL CREADA: {signal_type} {symbol} Precio: {order_price} SL: {sl} TP: {tp}")
                
    return signal_events

# =============================================================================
# ENGINES CONFIGURATION
# =============================================================================
# Sizing por porcentaje de riesgo (El framework calcula lotaje ideal para arriesgar 2%)
strategy.configure_predefined_sizing_engine(RiskPctSizingConfig(risk_pct=risk_per_trade_pct))
strategy.configure_predefined_risk_engine(PassthroughRiskConfig())

# =============================================================================
# EXECUTION MODE
# =============================================================================
# Cambiar a "LIVE" para operar en cuenta Demo
MODE = "BACKTEST" 

if __name__ == "__main__":
    if MODE == "BACKTEST":
        logger.info("Iniciando Backtest...")
        from_date = datetime(year=2026, month=6, day=1)
        to_date = datetime(year=2026, month=6, day=29)
        
        backtest = strategy.backtest(
            strategy_id=strategy_id,
            initial_capital=starting_capital,
            symbols_to_trade=symbols_to_trade,
            csv_dir=None, # Descarga los datos automáticamente si no los tienes cacheados
            backtest_name=strategy_id,
            start_date=from_date,
            end_date=to_date,
            export_backtest_parquet=False,
            account_currency=AccountCurrencies.USD
        )
        
        logger.info("Backtest finalizado.")
        backtest.plot()
        
    elif MODE == "LIVE":
        logger.info("Iniciando Live Trading en MT5 Demo...")
        mt5_config = Mt5PlatformConfig(
            path="C:\\Program Files\\MetaTrader 5\\terminal64.exe",
            login=25684767,
            password="t^5S&Ekq",
            server="VantageMarkets-Demo",
            timeout=60000,
            portable=False
        )
        strategy.run_live(
            mt5_configuration=mt5_config,
            strategy_id=strategy_id,
            initial_capital=starting_capital,
            symbols_to_trade=symbols_to_trade,
            heartbeat=0.1
        )
