"""
tp_calculators.py — Calculadores de Take Profit para la estrategia ORB Advanced.

Patrón Strategy (GoF): todas las implementaciones heredan de TakeProfitCalculator.

Métodos disponibles:
  - TP_Fixed    : TP fijo a un R:R configurable (cubre 1:1 y 1:1.5).
  - TP_Trailing : Sin TP fijo; trailing stop que persigue el precio con ATR.

Para añadir un nuevo método, heredar de TakeProfitCalculator e implementar
calculate_tp() y, opcionalmente, init_trail_state() + check_and_update_trail().
"""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional
from pyeventbt.events.events import SignalType


class TakeProfitCalculator(ABC):
    """Interfaz base para todos los calculadores de Take Profit."""

    name: str = "Base"
    is_trailing: bool = False  # Indica si el TP es trailing (para el motor de estrategia)

    @abstractmethod
    def calculate_tp(
        self,
        entry_price: Decimal,
        stop_loss_price: Decimal,
        rr_ratio: float,
        signal_type: SignalType,
    ) -> Decimal:
        """
        Calcula el precio de Take Profit.

        Parámetros
        ----------
        entry_price     : Precio de entrada.
        stop_loss_price : Precio del Stop Loss calculado.
        rr_ratio        : Ratio Riesgo:Recompensa (p.ej. 1.0 para 1:1, 1.5 para 1:1.5).
        signal_type     : BUY o SELL.

        Retorna
        -------
        Decimal : Precio del Take Profit. Decimal('0.0') si no hay TP fijo.
        """


# =============================================================================
# TP_Fixed — Take Profit fijo a un R:R configurable
# =============================================================================

class TP_Fixed(TakeProfitCalculator):
    """
    Take Profit fijo calculado como múltiplo del riesgo (distancia entrada→SL).

      TP = entrada + (|entrada - SL|) × rr_ratio  (BUY)
      TP = entrada - (|entrada - SL|) × rr_ratio  (SELL)

    Uso:
      TP_Fixed(rr=1.0)   → TP a 1:1 (misma distancia que el SL)
      TP_Fixed(rr=1.5)   → TP a 1:1.5
    """

    is_trailing = False

    def __init__(self, rr: float = 1.0):
        self.rr = Decimal(str(rr))
        self.name = f"FIXED_{str(rr).replace('.', '_')}R"

    def calculate_tp(
        self,
        entry_price: Decimal,
        stop_loss_price: Decimal,
        rr_ratio: float,  # ignorado — usamos self.rr fijo
        signal_type: SignalType,
    ) -> Decimal:
        risk = abs(entry_price - stop_loss_price)
        reward = risk * self.rr
        if signal_type == SignalType.BUY:
            return entry_price + reward
        elif signal_type == SignalType.SELL:
            return entry_price - reward
        return Decimal("0.0")


# =============================================================================
# TP_Trailing — Trailing Stop sin TP fijo
# =============================================================================

class TP_Trailing(TakeProfitCalculator):
    """
    Trailing stop adaptativo sin Take Profit fijo.

    Diseño basado en el estándar del Chandelier Exit (Van Tharp / Elder):

      Fase 1 — Breakeven (+0.5R):
        Cuando el precio alcanza +0.5R desde la entrada, el SL se mueve
        a breakeven (precio de entrada). Esto protege el capital ante
        reversiones tempranas.

      Fase 2 — Trailing activo (+1R):
        Cuando el precio alcanza +1R, el trailing se activa:
          - BUY:  trail_level = close_actual - (ATR × multiplier)
          - SELL: trail_level = close_actual + (ATR × multiplier)
        El trail_level solo se mueve en la dirección favorable (ratchet).

      Fase 3 — Cierre:
        La posición cierra cuando el precio toca el trail_level (vía
        cierre manual en process_bar_event, no por orden broker).

    ¿Por qué 1.5× ATR?
    ------------------
    El ATR de las velas de 1m del ORB representa la volatilidad típica
    de la sesión. Con 1.5× el SL tiene margen para respirar sin ser
    golpeado por el ruido intrabarra habitual. Menos (1×) provoca stops
    prematuros en XAUUSD y crypto; más (2×) renuncia demasiada ganancia.

    Parámetros
    ----------
    atr_multiplier : float
        Factor × ATR para la distancia del trailing SL. Default: 1.5.
    be_r : float
        R al que se activa el breakeven. Default: 0.5 (= +0.5R).
    activate_r : float
        R al que se activa el trailing propiamente dicho. Default: 1.0.
    """

    is_trailing = True

    def __init__(
        self,
        atr_multiplier: float = 1.5,
        be_r: float = 0.5,
        activate_r: float = 1.0,
    ):
        self.atr_multiplier = Decimal(str(atr_multiplier))
        self.be_r = Decimal(str(be_r))
        self.activate_r = Decimal(str(activate_r))
        self.name = f"TRAILING_{atr_multiplier}xATR"

    def calculate_tp(
        self,
        entry_price: Decimal,
        stop_loss_price: Decimal,
        rr_ratio: float,
        signal_type: SignalType,
    ) -> Decimal:
        """Sin TP fijo — retorna 0.0 para que el framework no coloque orden TP."""
        return Decimal("0.0")

    def init_trail_state(
        self,
        entry: Decimal,
        initial_sl: Decimal,
        atr: Decimal,
        direction: SignalType,
    ) -> dict:
        """
        Inicializa el estado del trailing para una posición nueva.

        Retorna un dict con todo el estado necesario para check_and_update_trail().
        Guardado por símbolo en ORBStateManager.trail_state.
        """
        return {
            "entry": entry,
            "initial_sl": initial_sl,
            "atr": atr,
            "direction": direction,
            "be_activated": False,       # ¿Breakeven activado?
            "trail_activated": False,    # ¿Trailing activo (≥ +1R)?
            "trail_level": initial_sl,   # Nivel actual del SL trailing
            "active": True,              # False cuando la posición ya cerró
        }

    def check_and_update_trail(
        self,
        trail_state: dict,
        bar_high: Decimal,
        bar_low: Decimal,
        bar_close: Decimal,
    ) -> Optional[str]:
        """
        Evalúa el estado del trailing stop en cada barra y actualiza trail_level.

        Retorna
        -------
        "CLOSE" si el trailing SL fue golpeado y hay que cerrar la posición.
        None    en caso contrario.

        Modifica trail_state in-place.
        """
        if not trail_state.get("active"):
            return None

        entry      = trail_state["entry"]
        initial_sl = trail_state["initial_sl"]
        atr        = trail_state["atr"]
        direction  = trail_state["direction"]
        risk = abs(entry - initial_sl)

        if risk == Decimal("0"):
            return None

        if direction == SignalType.BUY:
            # --- Comprobar si el trailing SL fue tocado ---
            if trail_state["trail_activated"] and bar_low <= trail_state["trail_level"]:
                trail_state["active"] = False
                return "CLOSE"

            # --- Fase 1: Breakeven en +be_r × R ---
            be_target = entry + risk * self.be_r
            if not trail_state["be_activated"] and bar_high >= be_target:
                trail_state["trail_level"] = max(trail_state["trail_level"], entry)
                trail_state["be_activated"] = True

            # --- Fase 2: Trailing en +activate_r × R ---
            activate_target = entry + risk * self.activate_r
            if not trail_state["trail_activated"] and bar_high >= activate_target:
                new_level = bar_close - atr * self.atr_multiplier
                if new_level > initial_sl:
                    trail_state["trail_level"] = max(trail_state["trail_level"], new_level)
                    trail_state["trail_activated"] = True
            elif trail_state["trail_activated"]:
                # Ratchet: solo mover el SL hacia arriba
                new_level = bar_close - atr * self.atr_multiplier
                if new_level > trail_state["trail_level"]:
                    trail_state["trail_level"] = new_level

        else:  # SELL
            # --- Comprobar si el trailing SL fue tocado ---
            if trail_state["trail_activated"] and bar_high >= trail_state["trail_level"]:
                trail_state["active"] = False
                return "CLOSE"

            # --- Fase 1: Breakeven en +be_r × R ---
            be_target = entry - risk * self.be_r
            if not trail_state["be_activated"] and bar_low <= be_target:
                trail_state["trail_level"] = min(trail_state["trail_level"], entry)
                trail_state["be_activated"] = True

            # --- Fase 2: Trailing en +activate_r × R ---
            activate_target = entry - risk * self.activate_r
            if not trail_state["trail_activated"] and bar_low <= activate_target:
                new_level = bar_close + atr * self.atr_multiplier
                if new_level < initial_sl:
                    trail_state["trail_level"] = min(trail_state["trail_level"], new_level)
                    trail_state["trail_activated"] = True
            elif trail_state["trail_activated"]:
                # Ratchet: solo mover el SL hacia abajo
                new_level = bar_close + atr * self.atr_multiplier
                if new_level < trail_state["trail_level"]:
                    trail_state["trail_level"] = new_level

        return None
