"""
state_manager.py — Gestor centralizado del estado mutable en tiempo de ejecución.

Encapsula todas las variables globales que en la versión anterior vivían dispersas
a nivel de módulo. Esto permite:
  - Código testeable (se puede crear un state limpio por test)
  - Eliminación de side-effects implícitos entre hooks y la estrategia
  - Un único punto de acceso/reset del estado de la sesión
"""

from decimal import Decimal
from typing import Dict, List, Optional, Set
from pyeventbt.events.events import SignalType


class ORBStateManager:
    """
    Centraliza todo el estado mutable de la estrategia ORB Advanced.

    Una instancia de esta clase se crea en main.py y se pasa por referencia
    a la estrategia (ORBAdvancedStrategy) y a los hooks (_on_fill, _on_end).

    Atributos
    ---------
    pending_signals : list[dict]
        Señales enviadas al framework pero cuyo FillEvent IN aún no se recibió.
        Cada dict contiene: symbol, entry, sl, tp, signal_type, session.

    position_map : dict[int, dict]
        Mapa de position_id → datos de la posición abierta.
        Se llena al recibir FillEvent IN y se consulta en FillEvent OUT.

    trade_results : list[dict]
        Historial de operaciones cerradas con P&L, motivo (TP/SL/EOD), etc.

    skipped : dict[str, dict[str, int]]
        Contador de señales descartadas por motivo (wide_sl, holiday).

    cancelled : dict[str, dict[str, int]]
        Contador de sesiones canceladas por motivo (timeout, expired).

    days_tested : int
        Número de días procesados (para el reporte final).

    trail_state : dict[str, dict]
        Estado del trailing stop por símbolo. Creado por TP_Trailing.init_trail_state().

    closed_tickets : set[int]
        Tickets de posiciones que ya recibieron FillEvent OUT (evita duplicados).

    summarized_sessions : set[str]
        Sesiones que ya mostraron el resumen de cierre (evita imprimir doble).

    session_positions : dict[str, set[int]]
        Mapa de nombre_sesión → conjunto de position_ids abiertos en esa sesión.

    current_session_for_signal : dict[str, str]
        Símbolo → nombre de la sesión que generó la última señal activa.

    current_session : str
        Nombre de la sesión que se está procesando en el bar actual.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        """Reinicia todo el estado. Útil para backtests consecutivos."""
        self.pending_signals:              List[dict]         = []
        self.position_map:                 Dict[int, dict]    = {}
        self.trade_results:                List[dict]         = []
        self.skipped:  Dict[str, Dict[str, int]]             = {"wide_sl": {}, "holiday": {}}
        self.cancelled: Dict[str, Dict[str, int]]            = {"timeout": {}, "expired": {}}
        self.days_tested:                  int                = 0
        self.trail_state:                  Dict[str, dict]    = {}
        self.closed_tickets:               Set[int]           = set()
        self.detected_closes:              Set[int]           = set()
        self.summarized_sessions:          Set[str]           = set()
        self.session_positions:            Dict[str, Set[int]] = {}
        self.current_session_for_signal:   Dict[str, str]     = {}
        self.current_session:              str                = "---"
        self.session_risk_pool:            Dict[str, dict]    = {}
