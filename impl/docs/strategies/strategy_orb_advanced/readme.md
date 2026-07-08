# ORB Advanced Strategy

## Ejemplos Rápidos de Uso

**1. Modo Backtest (Única configuración vía CLI):**
```bash
python impl/strategies/orb_advanced/main.py --mode BACKTEST --start-date 2026-06-01 --end-date 2026-07-01 --entry BREAKOUT --sl OPPOSITE_RANGE --tp FIXED_1R
```

**2. Modo Backtest Masivo (Múltiples combinaciones):**
Edita las fechas y lista de escenarios dentro de `impl/backtest/run_backtest.py` y luego ejecuta:
```bash
python impl/backtest/run_backtest.py
```

**3. Modo Live (MetaTrader 5):**
Requiere que tengas las credenciales en el archivo `.env` en la raíz del proyecto.
```bash
python impl/strategies/orb_advanced/main.py --mode LIVE
```

---

El package `orb_advanced` implementa la estrategia de Opening Range Breakout (ORB) con soporte para múltiples métodos de entrada, stop loss y take profit.

## Arquitectura Modular

La estrategia ha sido refactorizada para seguir principios SOLID y aislar dependencias:

*   **`main.py`**: Entry point principal. Usa `argparse` para inyectar configuración desde la línea de comandos, lo que simplifica los backtests masivos.
*   **`config.py`**: Almacena toda la configuración base, constantes (como timeframes y horarios), y carga credenciales de entorno (`.env`).
*   **`state_manager.py`**: Encapsula todo el estado mutable (`pending_signals`, `trade_results`, `trail_state`, etc.) en una clase `ORBStateManager`, eliminando las variables globales e impurezas del módulo.
*   **`strategy.py`**: `ORBAdvancedStrategy` ejecuta el ciclo principal de eventos, gestiona aperturas/cierres de día, genera `SignalEvents` y evalúa el `Trailing Stop` barra a barra.
*   **`hooks.py`**: Define closures para reaccionar a `FillEvent` (gestión de P&L, logging de cierres) y fin de backtest (impresión de tablas de resultados).

### Calculadores (Patrón Strategy)

La lógica de trading se ha delegado en clases específicas, permitiendo extender la estrategia fácilmente:

*   **`entry_calculators.py`**: `Entry_Breakout` (entrada inmediata) vs `Entry_Retest` (espera un pullback).
*   **`sl_calculators.py`**: `SL_OppositeRange` (extremo opuesto) vs `SL_MidRange` (punto medio).
*   **`tp_calculators.py`**: `TP_Fixed` (RR 1:1, 1:1.5) vs `TP_Trailing` (trailing dinámico basado en ATR).

## Trailing Stop (Chandelier Exit)

La estrategia implementa un trailing stop dinámico como alternativa al Take Profit fijo. Dado que MT5 no soporta órdenes de trailing stop del lado del broker de forma segura frente a desconexiones, el trailing se evalúa *barra a barra* dentro de `process_bar_event`.

El algoritmo sigue 3 fases:
1.  **Stop Inicial**: Definido por el calculador de SL (ej. Extremo opuesto).
2.  **Breakeven**: Al alcanzar +0.5R, el SL se mueve al punto de entrada.
3.  **Trailing**: Al alcanzar +1.0R, el SL comienza a perseguir el precio a una distancia de **1.5 × ATR**. Funciona en modo "ratchet" (solo avanza a favor de la posición, nunca retrocede).

## Ejecución

(Ver sección "Ejemplos Rápidos de Uso" al inicio de este documento).
