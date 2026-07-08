"""
session_state.py — Estado de la estrategia ORB por símbolo y sesión.

OrbSessionState es un contenedor de datos mutable que representa el ciclo
de vida de una sesión de trading para un instrumento específico.
Se instancia de nuevo cada día al detectar el cambio de fecha.
"""

from decimal import Decimal
from datetime import datetime
from typing import Optional
from pyeventbt.events.events import SignalType


class OrbSessionState:
    """
    Estado de una sesión ORB para un símbolo concreto.

    Ciclo de vida:
      1. Inicio del día → OrbSessionState() (todo a None/False)
      2. Llegada de la primera vela dentro de la ventana de sesión
         → orb_accumulating = True
      3. Acumulación de velas hasta completar el rango ORB
         → orb_formed = True
      4. Espera de ruptura (breakout o retest)
         → breakout_attempted = True al producirse (o timeout)
    """

    def __init__(self):
        # --- Rango ORB ---
        self.orb_high: Optional[Decimal] = None
        self.orb_low:  Optional[Decimal] = None

        # --- Tiempo de sesión ---
        self.session_start_time:  Optional[datetime] = None
        self.orb_window_start:    Optional[datetime] = None
        self.last_day_processed:  Optional[datetime] = None

        # --- Máquina de estados ---
        self.orb_formed:          bool = False  # Rango completamente formado
        self.orb_accumulating:    bool = False  # Acumulando velas para el rango
        self.breakout_attempted:  bool = False  # Ruptura detectada o timeout

        # --- Modo retest ---
        self.retest_mode:         bool = False
        self.retest_direction:    Optional[SignalType] = None
        self.retest_boundary:     Optional[Decimal] = None
        self.breakout_occurred:   bool = False
        self.breakout_high:       Optional[Decimal] = None
        self.breakout_low:        Optional[Decimal] = None

        # --- Logging flags (evitan spam en el log) ---
        self.session_open_logged:   bool = False
        self.waiting_logged:        bool = False
        self.market_closed_logged:  bool = False

        # --- Datos de volatilidad (para ATR del trailing) ---
        self.bar_ranges: list[Decimal] = []  # Rangos H-L de las velas 1m del ORB
