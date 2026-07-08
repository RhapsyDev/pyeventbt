"""
sl_calculators.py — Calculadores de Stop Loss para la estrategia ORB Advanced.

Patrón Strategy (GoF): todas las implementaciones heredan de StopLossCalculator.
Para añadir un nuevo método de SL, crear una clase que herede de StopLossCalculator
e implementar calculate_sl().
"""

from abc import ABC, abstractmethod
from decimal import Decimal
from pyeventbt.events.events import SignalType


class StopLossCalculator(ABC):
    """Interfaz base para todos los calculadores de Stop Loss."""

    name: str = "Base"

    @abstractmethod
    def calculate_sl(
        self,
        entry_price: Decimal,
        orb_high: Decimal,
        orb_low: Decimal,
        signal_type: SignalType,
        **kwargs,
    ) -> Decimal:
        """
        Calcula el precio de Stop Loss.

        Parámetros
        ----------
        entry_price  : Precio de entrada estimado en el momento del breakout.
        orb_high     : Máximo del rango ORB.
        orb_low      : Mínimo del rango ORB.
        signal_type  : BUY o SELL.
        **kwargs     : Parámetros opcionales (volatility, bar_low, bar_high, ...).

        Retorna
        -------
        Decimal : Precio del Stop Loss.
        """


# =============================================================================
# SL_OppositeRange — SL en el extremo opuesto del rango ORB
# =============================================================================

class SL_OppositeRange(StopLossCalculator):
    """
    Coloca el Stop Loss en el extremo opuesto del rango ORB:
      - BUY:  SL = ORB Low  (el precio no debería volver a caer dentro del rango)
      - SELL: SL = ORB High (el precio no debería volver a subir dentro del rango)

    Es el método más conservador: maximiza la probabilidad de que el SL no sea
    tocado por ruido dentro del rango, pero implica una distancia SL mayor
    y por lo tanto un R más amplio.
    """

    name = "OPPOSITE_RANGE"

    def calculate_sl(
        self,
        entry_price: Decimal,
        orb_high: Decimal,
        orb_low: Decimal,
        signal_type: SignalType,
        **kwargs,
    ) -> Decimal:
        if signal_type == SignalType.BUY:
            return orb_low
        elif signal_type == SignalType.SELL:
            return orb_high
        return Decimal("0.0")


# =============================================================================
# SL_MidRange — SL al 50% del rango ORB
# =============================================================================

class SL_MidRange(StopLossCalculator):
    """
    Coloca el Stop Loss en el punto medio del rango ORB.

    Lógica: si el precio ha roto el ORB con fuerza, no debería volver ni siquiera
    al 50% del rango. Un SL más ajustado implica:
      - Menor pérdida si la señal es falsa.
      - Mayor número de stops prematuros en mercados ruidosos.
    """

    name = "MID_RANGE"

    def calculate_sl(
        self,
        entry_price: Decimal,
        orb_high: Decimal,
        orb_low: Decimal,
        signal_type: SignalType,
        **kwargs,
    ) -> Decimal:
        return (orb_high + orb_low) / Decimal("2")
