"""
patches.py — Monkey-patches al framework pyeventbt.

Expone funciones explícitas que main.py llama en orden correcto,
evitando side effects implícitos al importar el módulo.
"""

from decimal import Decimal
from time import sleep


def apply_symbol_info_patch():
    """
    Inyecta información de símbolo faltante en el simulador MT5 para backtest.
    Permite operar con índices y crypto que el simulador no conoce por defecto.
    """
    from pyeventbt.broker.mt5_broker.shared.shared_data import SharedData
    from pyeventbt.broker.mt5_broker.core.entities.symbol_info import SymbolInfo
    from pyeventbt.broker.mt5_broker.connectors.mt5_simulator_connector import SymbolConnector

    _orig_symbol_info = SymbolConnector.symbol_info

    @staticmethod
    def _patched_symbol_info(symbol: str):
        info = _orig_symbol_info(symbol)
        if info is not None:
            return info
        # Fallback: usa SP500 como plantilla para símbolos desconocidos
        fallback = SharedData.symbol_info.get("SP500")
        if fallback is None:
            fallback = next(iter(SharedData.symbol_info.values()), None)
        if fallback is not None:
            d = fallback.model_dump()
            d.update(
                name=symbol, description=symbol, path=symbol,
                digits=2, currency_margin="USD", currency_profit="USD",
                currency_base="USD", trade_contract_size=Decimal("100"),
                point=Decimal("0.01"), trade_tick_size=Decimal("0.01"),
                trade_tick_value=Decimal("1"), trade_tick_value_profit=Decimal("1"),
                trade_tick_value_loss=Decimal("1"),
            )
            return SymbolInfo(**d)
        return None

    SymbolConnector.symbol_info = _patched_symbol_info


def apply_commission_patch(broker):
    """
    Reemplaza el cálculo de comisiones del simulador por el del broker configurado.
    Permite simular spreads y comisiones reales de Vantage RawECN.
    """
    from pyeventbt.execution_engine.connectors.mt5_simulator_execution_engine_connector import (
        Mt5SimulatorExecutionEngineConnector,
    )

    def _patched_commission(self, symbol: str, volume: Decimal, trade_price: Decimal) -> Decimal:
        return broker.commission_per_lot(symbol) * volume

    Mt5SimulatorExecutionEngineConnector._compute_commission_in_account_ccy = _patched_commission


def apply_live_patches(state):
    """
    Patches necesarios únicamente en modo LIVE:
      1. ORDER_FILLING_IOC — Vantage RawECN requiere IOC en lugar de FOK.
      2. Detección de cierres por SL/TP en MT5 (genera OUT FillEvent cuando
         MT5 cierra una posición automáticamente sin pasar por el framework).

    Parámetros
    ----------
    state : ORBStateManager
        Referencia al state manager; el patch accede a position_map y closed_tickets.
    """
    import MetaTrader5 as mt5

    # --- Patch 1: ORDER_FILLING_IOC ---
    _mt5_order_send_orig = mt5.order_send

    def _mt5_order_send_patched(request):
        request["type_filling"] = mt5.ORDER_FILLING_IOC
        return _mt5_order_send_orig(request)

    mt5.order_send = _mt5_order_send_patched

    # --- Patch 2: detección de cierres MT5 (SL/TP hit fuera del framework) ---
    from pyeventbt.execution_engine.connectors.mt5_live_execution_engine_connector import (
        Mt5LiveExecutionEngineConnector,
    )

    _original_update_check = (
        Mt5LiveExecutionEngineConnector._update_values_and_check_executions_and_fills
    )

    def _patched_update_check(self, bar_event):
        _original_update_check(self, bar_event)
        if not state.position_map:
            return
        try:
            open_positions = mt5.positions_get()
        except Exception:
            return
        if open_positions is None:
            return
        open_tickets = set(p.identifier for p in open_positions)
        for ticket in list(state.position_map.keys()):
            if ticket in open_tickets or ticket in state.detected_closes:
                continue
            deals = mt5.history_deals_get(position=ticket)
            if not deals:
                for _ in range(20):
                    sleep(0.05)
                    deals = mt5.history_deals_get(position=ticket)
                    if deals:
                        break
            if deals:
                for deal in deals:
                    if deal.entry == 1:  # OUT
                        state.detected_closes.add(ticket)
                        self._generate_and_put_fill_event(
                            trade_deal=deal, events_queue=self.events_queue
                        )
                        break

    Mt5LiveExecutionEngineConnector._update_values_and_check_executions_and_fills = (
        _patched_update_check
    )
