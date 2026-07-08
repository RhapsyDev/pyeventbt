"""
entry_calculators.py — Estrategias de entrada para la estrategia ORB Advanced.

Define cuándo entrar al mercado después de detectar una ruptura del ORB.

Métodos disponibles:
  - Entry_Breakout : Entrada inmediata al cierre de la vela que rompe el rango.
  - Entry_Retest   : Espera un pullback al borde del ORB antes de entrar.
"""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional, TYPE_CHECKING
from pyeventbt import BarEvent
from pyeventbt.events.events import SignalType

if TYPE_CHECKING:
    from impl.strategies.orb_advanced.session_state import OrbSessionState


class EntryCalculator(ABC):
    """Interfaz base para las estrategias de entrada."""

    name: str = "Base"

    @abstractmethod
    def on_breakout(
        self,
        signal_type: SignalType,
        event: BarEvent,
        session_state: "OrbSessionState",
    ) -> bool:
        """
        Llamado cuando se detecta una ruptura del ORB.

        Retorna True para entrar inmediatamente, False para esperar confirmación.
        """

    def on_bar(
        self,
        event: BarEvent,
        session_state: "OrbSessionState",
    ) -> Optional[tuple[Decimal, SignalType]]:
        """
        Llamado en cada vela mientras el modo retest está activo.

        Retorna (precio_entrada, dirección) si se confirma el retest, o None.
        """
        return None


# =============================================================================
# Entry_Breakout — Entrada inmediata al romper el ORB
# =============================================================================

class Entry_Breakout(EntryCalculator):
    """
    Entra al mercado en la misma vela que confirma la ruptura del ORB.

    Ventajas:
      - Captura el movimiento completo desde la ruptura.
      - Sin riesgo de perder la señal por esperar el retest.

    Desventajas:
      - Puede generar entradas en falsos breakouts (bull/bear traps).
      - El spread en el momento de la ruptura suele ser más amplio.
    """

    name = "BREAKOUT"

    def on_breakout(
        self,
        signal_type: SignalType,
        event: BarEvent,
        session_state: "OrbSessionState",
    ) -> bool:
        return True  # Entrada inmediata


# =============================================================================
# Entry_Retest — Espera pullback al borde del ORB
# =============================================================================

class Entry_Retest(EntryCalculator):
    """
    Espera a que el precio rompa el ORB y luego regrese al borde del rango
    (retest) antes de entrar.

    Condiciones de entrada:
      - BUY:  El precio toca el ORB High (bar_low ≤ ORB_high × tolerancia)
               y la vela cierra por encima del ORB High.
      - SELL: El precio toca el ORB Low (bar_high ≥ ORB_low / tolerancia)
               y la vela cierra por debajo del ORB Low.

    Ventajas:
      - Mejor precio de entrada (menor slippage vs. momento de ruptura).
      - Filtra algunos falsos breakouts.

    Desventajas:
      - En movimientos impulsivos, el retest no ocurre y se pierde la señal.
      - Aumenta la tasa de sesiones canceladas por timeout.
    """

    name = "RETEST"

    def on_breakout(
        self,
        signal_type: SignalType,
        event: BarEvent,
        session_state: "OrbSessionState",
    ) -> bool:
        return False  # No entrar: esperar retest

    def on_bar(
        self,
        event: BarEvent,
        session_state: "OrbSessionState",
    ) -> Optional[tuple[Decimal, SignalType]]:
        divisor    = Decimal(10 ** event.data.digits)
        bar_low    = Decimal(str(event.data.low))   / divisor
        bar_high   = Decimal(str(event.data.high))  / divisor
        bar_close  = Decimal(str(event.data.close)) / divisor

        tolerance = Decimal("1.0005")  # 0.05% de margen para el toque del nivel

        if session_state.retest_direction == SignalType.BUY:
            boundary = session_state.retest_boundary
            # Precio toca el ORB High (con tolerancia) y cierra por encima
            if bar_low <= boundary * tolerance and bar_close > boundary:
                return (bar_close, SignalType.BUY)

        elif session_state.retest_direction == SignalType.SELL:
            boundary = session_state.retest_boundary
            # Precio toca el ORB Low (con tolerancia) y cierra por debajo
            if bar_high >= boundary / tolerance and bar_close < boundary:
                return (bar_close, SignalType.SELL)

        return None
