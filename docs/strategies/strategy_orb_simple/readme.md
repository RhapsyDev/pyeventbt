# Estrategia: Opening Range Breakout (ORB) Simple

Este documento contiene la especificación, lógica y plan de desarrollo para la estrategia institucional **ORB Simple** en PyEventBT.

---

## 1. Concepto

El **Opening Range Breakout (ORB)** se basa en la premisa de que el rango de precios establecido en los primeros minutos de la jornada (generalmente 15, 30 o 60 minutos tras la apertura del mercado) define niveles clave de soporte y resistencia que guiarán la tendencia intradiaria si son superados con suficiente fuerza.

---

## 2. Lógica Algorítmica (Diseño de Alto Nivel)

```
DEFINICIÓN DEL RANGO (Opening Range)
  - Monitorizar las primeras X barras (ej. 30 minutos) desde el inicio de la sesión según la configuración de `SESSIONS`.
  - ORB_HIGH = Valor máximo (High) registrado en ese periodo.
  - ORB_LOW  = Valor mínimo (Low) registrado en ese periodo.

DETECCIÓN DE RUPTURA (Breakout)
  - Señal BUY: Entrada a mercado cuando el precio de cierre de la barra actual rompe por encima del ORB_HIGH.
  - Señal SELL: Entrada a mercado cuando el precio de cierre de la barra actual rompe por debajo del ORB_LOW.

GESTIÓN DE RIESGO
  - Stop Loss (SL): Posicionado al otro lado del rango.
    * Para compras (BUY): SL en el nivel ORB_LOW.
    * Para ventas (SELL): SL en el nivel ORB_HIGH.
  - Take Profit (TP): Ratio de Riesgo/Beneficio de 1:1, calculado respecto a la distancia de la entrada al SL.
  - Dimensionamiento de posición (Sizing): Riesgo estricto de 2% de la cuenta usando `RiskPctSizingConfig`.

GESTIÓN DE LA POSICIÓN
  - Permitir un máximo de una operación por día y por símbolo.
  - Cierre forzado intradiario antes del cierre oficial de la sesión (ej. a las 23:00 de la plataforma) para evitar swaps o gaps de mercado.
```

---

## 3. Parámetros de Configuración

| Parámetro | Tipo | Descripción | Valor Inicial Recomendado |
|---|---|---|---|
| `SESSIONS` | `dict` | Diccionario configurando los inicios y duración de las sesiones (Asia, London, NY). | Múltiples sesiones |
| `SIGNAL_TIMEFRAME` | `StrategyTimeframes` | Timeframe de las velas de control para rupturas y cálculo del rango. | `M15` |
| `SYMBOLS` | `list` | Instrumentos a operar. Preparado para Forex, Índices, Cryptos. | `['XAUUSD']` |
| `RISK_PER_TRADE_PCT` | `float` | Riesgo por operación en base al balance de la cuenta (%). | `2.0` |
| `RR_RATIO` | `float` | Ratio de Riesgo:Recompensa para definir el Take Profit. | `1.0` |
| `SESSION_END_HOUR` | `time` | Hora de cierre forzado de posiciones activas (Broker time). | `23:00` |

---

## 4. Fases de Desarrollo de la Estrategia

- [x] **Fase 0 — Setup del Entorno:** Validar intérprete, dependencias y conector MT5.
- [x] **Fase 1 — Diseño Detallado:** Lógica de sesiones y cálculo de rangos definido en un diccionario.
- [x] **Fase 2 — Implementación:** Archivo de estrategia `strategy_orb_simple.py` implementado en la carpeta `custom_strategies`.
- [ ] **Fase 3 — Backtesting y Validación:** Ejecución histórica desde Junio 1 a Junio 29 2026.
- [ ] **Fase 4 — Live Paper Trading:** Despliegue en cuenta demo Vantage Markets.

---

## 5. Instrucciones de Ejecución

El código fuente de la estrategia se encuentra en: `custom_strategies/strategy_orb_simple.py`. Se ha ubicado en esta carpeta separada para evitar conflictos con actualizaciones futuras de la base del framework.

Para iniciar el backtest, simplemente ejecutar:
```bash
python custom_strategies/strategy_orb_simple.py
```

Para probar en modo "Demo Live", abre el archivo, cambia `MODE = "LIVE"`, e introduce una hora cercana en la configuración `"TEST"` de la variable `SESSIONS`.
