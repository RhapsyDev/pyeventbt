"""
entry_calculators.py — Estrategias de entrada para la estrategia ORB Advanced.

Define cuándo entrar al mercado después de detectar una ruptura del ORB.

Métodos disponibles:
  - Entry_Breakout       : Entrada inmediata al cierre de la vela que rompe el rango.
  - Entry_RetestORB      : Espera un pullback al borde del ORB antes de entrar.
  - Entry_FVG_Retest     : Espera un retest al Fair Value Gap dejado por la ruptura.
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
    supports_retest: bool = False
    """Si True, on_breakout=False significa 'esperar retest'.
       Si False, on_breakout=False significa 'saltar senal'."""

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

    def has_retest_setup(self, session_state: "OrbSessionState") -> bool:
        """
        Indica si el estado del retest está correctamente inicializado tras
        on_breakout(). Si retorna False, la señal se descarta en vez de
        entrar en modo retest.
        """
        return True

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
    supports_retest = False

    def on_breakout(
        self,
        signal_type: SignalType,
        event: BarEvent,
        session_state: "OrbSessionState",
    ) -> bool:
        return True  # Entrada inmediata


# =============================================================================
# Entry_RetestORB — Espera pullback al borde del ORB
# =============================================================================

class Entry_RetestORB(EntryCalculator):
    """
    RETEST_ORB — Espera a que el precio rompa el ORB y luego regrese al borde
    del rango (retest) antes de entrar.

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

    name = "RETEST_ORB"
    supports_retest = True

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


# =============================================================================
# Entry_Breakout_Confirmed — Breakout + filtros Volumen / VWAP / ATR
# =============================================================================

class Entry_Breakout_Confirmed(EntryCalculator):
    """
    BREAKOUT_CONFIRMED — Entra en la ruptura solo si se cumplen filtros
    de confirmación que reducen falsos breakouts.

    Filtros (todos deben pasar):
      1. VWAP Alignment
         El precio de cierre de la vela breakout debe estar del lado correcto
         del VWAP de la sesión (long -> close > VWAP, short -> close < VWAP).
         Si no hay tickvol en los datos, usa el precio medio de la sesión
         como VWAP proxy.

      2. Tick Volume (si los datos lo soportan)
         El tickvol de la vela breakout debe superar el promedio del ORB
         multiplicado por *volume_mult*. Cuando todos los tickvol son 0
         (forex/CFDs sin volumen), este filtro se omite y se delega en ATR.

      3. ATR Expansion (fallback cuando no hay tickvol)
         El rango H-L de la vela breakout debe superar el rango promedio
         de las velas del ORB multiplicado por *atr_mult*.

    Uso en backtest:
        python main.py --entry BREAKOUT_CONFIRMED

    Referencia:
        Estudios con 6.142 días en ES/NQ muestran que aplicar filtros de
        confirmación mejora la tasa de continuacion de ~59% a ~64-71%.
        Ver: https://tradingstats.net/orb-breakout-strategy-guide/
    """

    name = "BREAKOUT_CONFIRMED"
    supports_retest = False

    def __init__(
        self,
        volume_multiplier: float = 1.5,
        atr_multiplier: float = 1.5,
        use_volume_filter: bool = True,
        use_vwap_filter: bool = True,
    ):
        """
        Args:
            volume_multiplier: Minimo tickvol de breakout / tickvol promedio ORB.
            atr_multiplier:    Minimo rango breakout / rango promedio ORB.
            use_volume_filter: Activa/desactiva el filtro de tickvol.
            use_vwap_filter:   Activa/desactiva el filtro de VWAP.
        """
        self.volume_multiplier = volume_multiplier
        self.atr_multiplier = atr_multiplier
        self.use_volume_filter = use_volume_filter
        self.use_vwap_filter = use_vwap_filter

    # ------------------------------------------------------------------
    # Calculo de VWAP de la sesion
    # ------------------------------------------------------------------
    @staticmethod
    def _calc_vwap(session_state: "OrbSessionState") -> Optional[Decimal]:
        """
        Retorna el VWAP de la sesion si hay tickvol acumulado,
        o None si no hay datos suficientes.
        """
        if session_state.orb_cumulative_tickvol > 0:
            return (
                session_state.orb_cumulative_pv
                / Decimal(str(session_state.orb_cumulative_tickvol))
            )
        return None

    # ------------------------------------------------------------------
    # Filtro 1: VWAP Alignment
    # ------------------------------------------------------------------
    def _check_vwap(
        self,
        signal_type: SignalType,
        current_close: Decimal,
        session_state: "OrbSessionState",
    ) -> bool:
        """Retorna True si el precio esta del lado correcto del VWAP."""
        if not self.use_vwap_filter:
            return True

        vwap = self._calc_vwap(session_state)
        if vwap is None:
            return True  # Sin datos suficientes, pasa

        if signal_type == SignalType.BUY:
            ok = current_close > vwap
        else:
            ok = current_close < vwap

        return ok

    # ------------------------------------------------------------------
    # Filtro 2: Tick Volume
    # ------------------------------------------------------------------
    def _check_volume(
        self,
        current_tickvol: int,
        session_state: "OrbSessionState",
    ) -> bool:
        """
        Retorna True si el tickvol del breakout supera el umbral,
        o si no hay datos de tickvol disponibles (delega en ATR).
        """
        if not self.use_volume_filter:
            return True

        avg = self._avg_tickvol(session_state)
        if avg is None:
            return True
        if avg <= 0:
            return True  # Tickvol homogeneamente 0 -> no aplica
        return current_tickvol > avg * self.volume_multiplier

    @staticmethod
    def _avg_tickvol(session_state: "OrbSessionState") -> Optional[float]:
        """Promedio de tickvol de las velas del ORB."""
        vols = session_state.orb_tickvols
        if not vols:
            return None
        return sum(vols) / len(vols)

    # ------------------------------------------------------------------
    # Filtro 3: ATR Expansion (fallback)
    # ------------------------------------------------------------------
    def _check_atr(
        self,
        breakout_range: Decimal,
        session_state: "OrbSessionState",
    ) -> bool:
        """
        Retorna True si el rango de la breakout vela supera el promedio.
        Actua como respaldo cuando tickvol no esta disponible.
        """
        avg_range = self._avg_bar_range(session_state)
        if avg_range is None or avg_range <= Decimal("0"):
            return True
        return breakout_range > avg_range * Decimal(str(self.atr_multiplier))

    @staticmethod
    def _avg_bar_range(session_state: "OrbSessionState") -> Optional[Decimal]:
        """Rango H-L promedio de las velas del ORB."""
        ranges = session_state.bar_ranges
        if not ranges:
            return None
        return sum(ranges, Decimal("0")) / Decimal(str(len(ranges)))

    # ------------------------------------------------------------------
    # Metodo principal
    # ------------------------------------------------------------------
    def on_breakout(
        self,
        signal_type: SignalType,
        event: BarEvent,
        session_state: "OrbSessionState",
    ) -> bool:
        """
        Evalua todos los filtros activos. Retorna True (entrar) solo si
        TODOS los filtros activos pasan.
        """
        divisor = Decimal(10 ** event.data.digits)
        close_price = Decimal(str(event.data.close)) / divisor

        # 1. VWAP
        if not self._check_vwap(signal_type, close_price, session_state):
            return False

        # 2. Tick volume con fallback a ATR
        vol_ok = True
        avg_vol = self._avg_tickvol(session_state)
        if avg_vol is not None and avg_vol > 0:
            # Hay datos de tickvol -> filtro real
            vol_ok = self._check_volume(event.data.tickvol, session_state)
        else:
            # Sin tickvol -> ATR expansion fallback
            br_range = session_state.breakout_bar_range
            if br_range is not None:
                vol_ok = self._check_atr(br_range, session_state)
        if not vol_ok:
            return False

        return True


# =============================================================================
# Entry_FVG_Retest — Retest del Fair Value Gap (FVG)
# =============================================================================

class Entry_FVG_Retest(EntryCalculator):
    """
    FVG_RETEST — Entra cuando el precio retesta un Fair Value Gap (FVG)
    dejado por la vela de breakout.

    Lógica:
      1. Tras detectar la ruptura del ORB, se calcula el FVG entre la vela
         de breakout y la vela anterior (en timeframe de breakout).
      2. Si el gap es >= fvg_min_points, se almacena la zona del FVG
         (fvg_high = borde superior, fvg_low = borde inferior).
      3. El precio debe retornar a la zona del FVG (retest).
      4. Entrada al cierre de la primera vela que toca la zona FVG.

    SL recomendado:
      - Por debajo del FVG (BUY): session_state.fvg_low - margen
      - Por encima del FVG (SELL): session_state.fvg_high + margen
      Los SL methods existentes (OPPOSITE_RANGE, MID_RANGE) también
      funcionan, pero el SL natural del FVG es justo fuera de la zona.

    Ventajas:
      - Entra en zonas de desequilibrio/ineficiencia del mercado.
      - Precio de entrada mejor que en la ruptura impulsiva.

    Desventajas:
      - No todos los breakouts dejan FVG.
      - El precio puede no retornar al FVG (movimiento direccional fuerte).
    """

    name = "FVG_RETEST"
    supports_retest = True

    def __init__(self, fvg_min_points: int = 5):
        """
        Args:
            fvg_min_points: Gap mínimo en puntos del símbolo para considerar
                           el FVG válido. Por defecto 5 (ej: 0.05 en XAUUSD).
        """
        self.fvg_min_points = fvg_min_points

    # ------------------------------------------------------------------
    # FVG detection
    # ------------------------------------------------------------------
    def on_breakout(
        self,
        signal_type: SignalType,
        event: BarEvent,
        session_state: "OrbSessionState",
    ) -> bool:
        """
        Detecta el FVG entre la vela breakout y la anterior.
        Retorna False siempre (espera retest).
        Almacena fvg_high/fvg_low en session_state si hay gap válido.
        """
        # Sin datos de barra anterior -> no se puede calcular FVG
        if session_state.last_bar_high is None or session_state.last_bar_low is None:
            return False

        divisor       = Decimal(10 ** event.data.digits)
        breakout_high = Decimal(str(event.data.high)) / divisor
        breakout_low  = Decimal(str(event.data.low))  / divisor
        prev_high     = session_state.last_bar_high
        prev_low      = session_state.last_bar_low

        if signal_type == SignalType.BUY:
            # FVG alcista: el mínimo de la breakout está por encima del máximo anterior
            if breakout_low > prev_high:
                gap_pts = int((breakout_low - prev_high) * Decimal(str(10 ** event.data.digits)))
                if gap_pts >= self.fvg_min_points:
                    session_state.fvg_high = breakout_low
                    session_state.fvg_low  = prev_high
            return False

        else:  # SELL
            # FVG bajista: el máximo de la breakout está por debajo del mínimo anterior
            if breakout_high < prev_low:
                gap_pts = int((prev_low - breakout_high) * Decimal(str(10 ** event.data.digits)))
                if gap_pts >= self.fvg_min_points:
                    session_state.fvg_high = prev_low
                    session_state.fvg_low  = breakout_high
            return False

    # ------------------------------------------------------------------
    # Retest entry
    # ------------------------------------------------------------------
    def on_bar(
        self,
        event: BarEvent,
        session_state: "OrbSessionState",
    ) -> Optional[tuple[Decimal, SignalType]]:
        """Entra cuando el precio retorna a la zona del FVG."""
        if session_state.fvg_high is None or session_state.fvg_low is None:
            return None

        divisor   = Decimal(10 ** event.data.digits)
        bar_low   = Decimal(str(event.data.low))   / divisor
        bar_high  = Decimal(str(event.data.high))  / divisor
        bar_close = Decimal(str(event.data.close)) / divisor

        if session_state.retest_direction == SignalType.BUY:
            # Precio retrocedió hasta la zona FVG (toca fvg_high desde arriba)
            if bar_low <= session_state.fvg_high:
                return (bar_close, SignalType.BUY)

        elif session_state.retest_direction == SignalType.SELL:
            # Precio retrocedió hasta la zona FVG (toca fvg_low desde abajo)
            if bar_high >= session_state.fvg_low:
                return (bar_close, SignalType.SELL)

        return None

    # ------------------------------------------------------------------
    # Setup check
    # ------------------------------------------------------------------
    def has_retest_setup(self, session_state: "OrbSessionState") -> bool:
        """Solo entra en modo retest si se detectó un FVG válido."""
        return session_state.fvg_high is not None and session_state.fvg_low is not None
