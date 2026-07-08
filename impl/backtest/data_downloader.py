"""
data_downloader.py — Descarga automática de datos OHLC para backtesting
=======================================================================

Cuando una estrategia define símbolos y fechas, descarga los CSVs
automáticamente desde Dukascopy (vía dukascopy-python) si no existen.

Almacenamiento plano (sin subdirectorios):

    historical_data/
    ├── XAUUSD.csv
    ├── BTCUSD.csv
    └── SP500.csv

Cada archivo se sobreescribe con el rango solicitado. El CSVDataProvider
de PyEventBT lee directamente de ``historical_data/{symbol}.csv``.

TODOS los timestamps se almacenan en UTC.
"""

import os
import shutil
from datetime import datetime, timezone
from typing import Optional

import dukascopy_python as duka
from dukascopy_python.instruments import (
    INSTRUMENT_FX_MAJORS_EUR_USD,
    INSTRUMENT_FX_MAJORS_GBP_USD,
    INSTRUMENT_FX_MAJORS_USD_JPY,
    INSTRUMENT_FX_MAJORS_USD_CHF,
    INSTRUMENT_FX_MAJORS_USD_CAD,
    INSTRUMENT_FX_MAJORS_AUD_USD,
    INSTRUMENT_FX_MAJORS_NZD_USD,
    INSTRUMENT_FX_CROSSES_AUD_CAD,
    INSTRUMENT_FX_CROSSES_AUD_CHF,
    INSTRUMENT_FX_CROSSES_AUD_JPY,
    INSTRUMENT_FX_CROSSES_CAD_CHF,
    INSTRUMENT_FX_CROSSES_CAD_JPY,
    INSTRUMENT_FX_CROSSES_CHF_JPY,
    INSTRUMENT_FX_CROSSES_EUR_AUD,
    INSTRUMENT_FX_CROSSES_EUR_CAD,
    INSTRUMENT_FX_CROSSES_EUR_CHF,
    INSTRUMENT_FX_CROSSES_EUR_GBP,
    INSTRUMENT_FX_CROSSES_EUR_JPY,
    INSTRUMENT_FX_CROSSES_EUR_NZD,
    INSTRUMENT_FX_CROSSES_GBP_AUD,
    INSTRUMENT_FX_CROSSES_GBP_CAD,
    INSTRUMENT_FX_CROSSES_GBP_CHF,
    INSTRUMENT_FX_CROSSES_GBP_JPY,
    INSTRUMENT_FX_CROSSES_GBP_NZD,
    INSTRUMENT_FX_CROSSES_NZD_CAD,
    INSTRUMENT_FX_CROSSES_NZD_CHF,
    INSTRUMENT_FX_CROSSES_NZD_JPY,
    INSTRUMENT_FX_CROSSES_EUR_NOK,
    INSTRUMENT_FX_CROSSES_EUR_SEK,
    INSTRUMENT_FX_CROSSES_EUR_TRY,
    INSTRUMENT_FX_CROSSES_EUR_ZAR,
    INSTRUMENT_FX_CROSSES_USD_CNH,
    INSTRUMENT_FX_CROSSES_USD_HKD,
    INSTRUMENT_FX_CROSSES_USD_MXN,
    INSTRUMENT_FX_CROSSES_USD_NOK,
    INSTRUMENT_FX_CROSSES_USD_PLN,
    INSTRUMENT_FX_CROSSES_USD_SEK,
    INSTRUMENT_FX_CROSSES_USD_SGD,
    INSTRUMENT_FX_CROSSES_USD_TRY,
    INSTRUMENT_FX_CROSSES_USD_ZAR,
    INSTRUMENT_FX_CROSSES_USD_ILS,
    INSTRUMENT_FX_CROSSES_EUR_HUF,
    INSTRUMENT_FX_CROSSES_EUR_PLN,
    INSTRUMENT_FX_CROSSES_USD_CZK,
    INSTRUMENT_FX_CROSSES_USD_HUF,
    INSTRUMENT_FX_METALS_XAU_USD,
    INSTRUMENT_FX_METALS_XAG_USD,
    INSTRUMENT_CMD_METALS_XPD_CMD_USD,
    INSTRUMENT_CMD_METALS_XPT_CMD_USD,
    INSTRUMENT_CMD_ENERGY_E_LIGHT,
    INSTRUMENT_CMD_ENERGY_E_BRENT,
    INSTRUMENT_CMD_ENERGY_GAS_CMD_USD,
    INSTRUMENT_CMD_AGRICULTURAL_SUGAR_CMD_USD,
    INSTRUMENT_CMD_AGRICULTURAL_COFFEE_CMD_USX,
    INSTRUMENT_CMD_AGRICULTURAL_SOYBEAN_CMD_USX,
    INSTRUMENT_CMD_METALS_COPPER_CMD_USD,
    INSTRUMENT_IDX_AMERICA_E_SANDP_500,
    INSTRUMENT_IDX_AMERICA_E_NQ_100,
    INSTRUMENT_IDX_AMERICA_E_D_J_IND,
    INSTRUMENT_IDX_AMERICA_RUSSELL_IDX_USD,
    INSTRUMENT_IDX_AMERICA_VOL_IDX_USD,
    INSTRUMENT_IDX_EUROPE_E_DJE50XX,
    INSTRUMENT_IDX_EUROPE_E_DAAX,
    INSTRUMENT_IDX_EUROPE_E_CAAC_40,
    INSTRUMENT_IDX_EUROPE_E_FUTSEE_100,
    INSTRUMENT_IDX_EUROPE_E_SWMI,
    INSTRUMENT_IDX_ASIA_E_N225JAP,
    INSTRUMENT_IDX_ASIA_E_H_KONG,
    INSTRUMENT_IDX_ASIA_E_XJO_ASX,
    INSTRUMENT_CMD_AGRICULTURAL_SOYBEAN_CMD_USX,
    INSTRUMENT_VCCY_BTC_USD,
    INSTRUMENT_VCCY_ETH_USD,
    INSTRUMENT_VCCY_LTC_USD,
    INSTRUMENT_VCCY_XRP_USD,
    INSTRUMENT_VCCY_ADA_USD,
    INSTRUMENT_VCCY_UNI_USD,
)


# =============================================================================
# Mapeo símbolo -> instrumento Dukascopy
# =============================================================================

SYMBOL_MAP = {
    "EURUSD":  INSTRUMENT_FX_MAJORS_EUR_USD,
    "GBPUSD":  INSTRUMENT_FX_MAJORS_GBP_USD,
    "USDJPY":  INSTRUMENT_FX_MAJORS_USD_JPY,
    "USDCHF":  INSTRUMENT_FX_MAJORS_USD_CHF,
    "USDCAD":  INSTRUMENT_FX_MAJORS_USD_CAD,
    "AUDUSD":  INSTRUMENT_FX_MAJORS_AUD_USD,
    "NZDUSD":  INSTRUMENT_FX_MAJORS_NZD_USD,
    "AUDCAD":  INSTRUMENT_FX_CROSSES_AUD_CAD,
    "AUDCHF":  INSTRUMENT_FX_CROSSES_AUD_CHF,
    "AUDJPY":  INSTRUMENT_FX_CROSSES_AUD_JPY,
    "CADCHF":  INSTRUMENT_FX_CROSSES_CAD_CHF,
    "CADJPY":  INSTRUMENT_FX_CROSSES_CAD_JPY,
    "CHFJPY":  INSTRUMENT_FX_CROSSES_CHF_JPY,
    "EURAUD":  INSTRUMENT_FX_CROSSES_EUR_AUD,
    "EURCAD":  INSTRUMENT_FX_CROSSES_EUR_CAD,
    "EURCHF":  INSTRUMENT_FX_CROSSES_EUR_CHF,
    "EURGBP":  INSTRUMENT_FX_CROSSES_EUR_GBP,
    "EURJPY":  INSTRUMENT_FX_CROSSES_EUR_JPY,
    "EURNZD":  INSTRUMENT_FX_CROSSES_EUR_NZD,
    "EURHUF":  INSTRUMENT_FX_CROSSES_EUR_HUF,
    "EURPLN":  INSTRUMENT_FX_CROSSES_EUR_PLN,
    "EURNOK":  INSTRUMENT_FX_CROSSES_EUR_NOK,
    "EURSEK":  INSTRUMENT_FX_CROSSES_EUR_SEK,
    "EURTRY":  INSTRUMENT_FX_CROSSES_EUR_TRY,
    "EURZAR":  INSTRUMENT_FX_CROSSES_EUR_ZAR,
    "GBPAUD":  INSTRUMENT_FX_CROSSES_GBP_AUD,
    "GBPCAD":  INSTRUMENT_FX_CROSSES_GBP_CAD,
    "GBPCHF":  INSTRUMENT_FX_CROSSES_GBP_CHF,
    "GBPJPY":  INSTRUMENT_FX_CROSSES_GBP_JPY,
    "GBPNZD":  INSTRUMENT_FX_CROSSES_GBP_NZD,
    "NZDCAD":  INSTRUMENT_FX_CROSSES_NZD_CAD,
    "NZDCHF":  INSTRUMENT_FX_CROSSES_NZD_CHF,
    "NZDJPY":  INSTRUMENT_FX_CROSSES_NZD_JPY,
    "USDCNH":  INSTRUMENT_FX_CROSSES_USD_CNH,
    "USDHKD":  INSTRUMENT_FX_CROSSES_USD_HKD,
    "USDMXN":  INSTRUMENT_FX_CROSSES_USD_MXN,
    "USDNOK":  INSTRUMENT_FX_CROSSES_USD_NOK,
    "USDPLN":  INSTRUMENT_FX_CROSSES_USD_PLN,
    "USDSEK":  INSTRUMENT_FX_CROSSES_USD_SEK,
    "USDSGD":  INSTRUMENT_FX_CROSSES_USD_SGD,
    "USDTRY":  INSTRUMENT_FX_CROSSES_USD_TRY,
    "USDZAR":  INSTRUMENT_FX_CROSSES_USD_ZAR,
    "USDILS":  INSTRUMENT_FX_CROSSES_USD_ILS,
    "USDCZK":  INSTRUMENT_FX_CROSSES_USD_CZK,
    "USDHUF":  INSTRUMENT_FX_CROSSES_USD_HUF,
    "XAUUSD":  INSTRUMENT_FX_METALS_XAU_USD,
    "XAGUSD":  INSTRUMENT_FX_METALS_XAG_USD,
    "XPDUSD":  INSTRUMENT_CMD_METALS_XPD_CMD_USD,
    "XPTUSD":  INSTRUMENT_CMD_METALS_XPT_CMD_USD,
    "USOIL":   INSTRUMENT_CMD_ENERGY_E_LIGHT,
    "XTIUSD":  INSTRUMENT_CMD_ENERGY_E_LIGHT,
    "UKOIL":   INSTRUMENT_CMD_ENERGY_E_BRENT,
    "XBRUSD":  INSTRUMENT_CMD_ENERGY_E_BRENT,
    "NATGAS":  INSTRUMENT_CMD_ENERGY_GAS_CMD_USD,
    "SUGAR":   INSTRUMENT_CMD_AGRICULTURAL_SUGAR_CMD_USD,
    "COFFEE":  INSTRUMENT_CMD_AGRICULTURAL_COFFEE_CMD_USX,
    "SOYBEAN": INSTRUMENT_CMD_AGRICULTURAL_SOYBEAN_CMD_USX,
    "COPPER":  INSTRUMENT_CMD_METALS_COPPER_CMD_USD,
    "SP500":   INSTRUMENT_IDX_AMERICA_E_SANDP_500,
    "NAS100":  INSTRUMENT_IDX_AMERICA_E_NQ_100,
    "US100":   INSTRUMENT_IDX_AMERICA_E_NQ_100,
    "US30":    INSTRUMENT_IDX_AMERICA_E_D_J_IND,
    "RUSSELL": INSTRUMENT_IDX_AMERICA_RUSSELL_IDX_USD,
    "VIX":     INSTRUMENT_IDX_AMERICA_VOL_IDX_USD,
    "EU50":    INSTRUMENT_IDX_EUROPE_E_DJE50XX,
    "DAX40":   INSTRUMENT_IDX_EUROPE_E_DAAX,
    "FRA40":   INSTRUMENT_IDX_EUROPE_E_CAAC_40,
    "UK100":   INSTRUMENT_IDX_EUROPE_E_FUTSEE_100,
    "SWI20":   INSTRUMENT_IDX_EUROPE_E_SWMI,
    "JP225":   INSTRUMENT_IDX_ASIA_E_N225JAP,
    "HK50":    INSTRUMENT_IDX_ASIA_E_H_KONG,
    "AUS200":  INSTRUMENT_IDX_ASIA_E_XJO_ASX,
    "BTCUSD":  INSTRUMENT_VCCY_BTC_USD,
    "ETHUSD":  INSTRUMENT_VCCY_ETH_USD,
    "LTCUSD":  INSTRUMENT_VCCY_LTC_USD,
    "XRPUSD":  INSTRUMENT_VCCY_XRP_USD,
    "ADAUSD":  INSTRUMENT_VCCY_ADA_USD,
    "UNIUSD":  INSTRUMENT_VCCY_UNI_USD,
}


def _normalize_symbol(symbol: str) -> str:
    """Elimina sufijos de broker (+, ., m) para buscar en el mapa."""
    for suffix in ["+", ".", "m", ".crp"]:
        if symbol.endswith(suffix):
            return symbol[:-len(suffix)]
    return symbol


def get_dukascopy_instrument(symbol: str):
    """Busca el instrumento de Dukascopy para el símbolo dado."""
    clean = _normalize_symbol(symbol)
    instr = SYMBOL_MAP.get(clean)
    if instr is not None:
        return instr
    for key, val in SYMBOL_MAP.items():
        if clean.startswith(key) or key.startswith(clean):
            return val
    raise ValueError(
        f"No hay mapping Dukascopy para '{symbol}' (limpio: '{clean}'). "
        f"Símbolos disponibles: {list(SYMBOL_MAP.keys())}"
    )


# =============================================================================
# Determinación de decimales según el precio
# =============================================================================

def _price_format(sample_price: float) -> str:
    if sample_price >= 1000:   return "{:.2f}"
    elif sample_price >= 100:  return "{:.3f}"
    elif sample_price >= 10:   return "{:.4f}"
    elif sample_price >= 1:    return "{:.5f}"
    else:                      return "{:.5f}"


# =============================================================================
# Descarga desde Dukascopy
# =============================================================================

def _download_dukascopy(
    symbol: str,
    start_date: datetime,
    end_date: datetime,
    output_path: str,
) -> None:
    """Descarga OHLC M1 desde Dukascopy y guarda en output_path."""
    clean = _normalize_symbol(symbol)
    instrument = get_dukascopy_instrument(symbol)

    if start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=timezone.utc)
    if end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=timezone.utc)

    print(f"[DATA] Descargando {clean} M1 desde {start_date.date()} hasta {end_date.date()} (vía Dukascopy)...")

    try:
        df = duka.fetch(
            instrument=instrument,
            interval=duka.INTERVAL_MIN_1,
            offer_side=duka.OFFER_SIDE_BID,
            start=start_date,
            end=end_date,
            debug=False,
        )
    except Exception as e:
        raise RuntimeError(f"Error descargando {symbol}: {e}") from e

    if df is None or df.empty:
        raise RuntimeError(f"No se obtuvieron datos para {symbol}")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    sample = float(df.iloc[0].get("open", 0))
    fmt = _price_format(sample)

    lines = 0
    with open(output_path, "w", encoding="utf-8") as f:
        for idx, row in df.iterrows():
            ts = row.get("timestamp", idx)
            if isinstance(ts, datetime):
                pass
            elif hasattr(idx, "to_pydatetime"):
                ts = idx.to_pydatetime()
            else:
                ts = idx

            if ts.tzinfo is not None:
                ts = ts.astimezone(timezone.utc)

            date_str = ts.strftime("%Y.%m.%d")
            time_str = ts.strftime("%H:%M:%S")
            o = fmt.format(float(row.get("open", 0)))
            h = fmt.format(float(row.get("high", 0)))
            l = fmt.format(float(row.get("low", 0)))
            c = fmt.format(float(row.get("close", 0)))
            vol = int(float(row.get("volume", 0)))
            f.write(f"{date_str},{time_str},{o},{h},{l},{c},{vol},{vol},0\n")
            lines += 1

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"[DATA] OK: {output_path} ({lines:,} filas, {size_mb:.1f} MB) - UTC")


# =============================================================================
# Función principal
# =============================================================================

def ensure_backtest_data(
    symbol: str,
    start_date: datetime,
    end_date: datetime,
    csv_dir: str = "historical_data",
    force: bool = False,
) -> str:
    """
    Asegura que existan datos OHLC M1 para el símbolo y rango solicitados.

    Descarga y guarda directamente como ``{csv_dir}/{symbol}.csv``.
    Si ya existe y ``force=False``, lo omite.

    Parameters
    ----------
    symbol : str
        Símbolo (ej. "XAUUSD", "BTCUSD"). Sufijos de broker se normalizan.
    start_date : datetime
        Inicio de la descarga (timezone-naive → UTC).
    end_date : datetime
        Fin de la descarga (timezone-naive → UTC).
    csv_dir : str
        Directorio donde guardar el CSV (default "historical_data").
    force : bool
        Si True, descarga de nuevo aunque ya exista.

    Returns
    -------
    str
        Ruta absoluta al CSV.
    """
    if start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=timezone.utc)
    if end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=timezone.utc)

    clean = _normalize_symbol(symbol)
    csv_path = os.path.join(csv_dir, f"{clean}.csv")

    if os.path.exists(csv_path) and not force:
        print(f"[DATA] Ya existe: {csv_path}")
        return os.path.abspath(csv_path)

    _download_dukascopy(symbol, start_date, end_date, csv_path)
    return os.path.abspath(csv_path)


def ensure_backtest_data_for_symbols(
    symbols: list[str],
    start_date: datetime,
    end_date: datetime,
    csv_dir: str = "historical_data",
    force: bool = False,
) -> list[str]:
    """
    Ejecuta ensure_backtest_data para una lista de símbolos.

    Parameters
    ----------
    symbols : list[str]
        Lista de símbolos.
    start_date : datetime
        Inicio de descarga para todos.
    end_date : datetime
        Fin de descarga para todos.
    csv_dir : str
        Directorio de salida.
    force : bool
        Si True, fuerza redescarga.

    Returns
    -------
    list[str]
        Rutas absolutas a los CSVs.
    """
    results = []
    for sym in symbols:
        path = ensure_backtest_data(sym, start_date, end_date, csv_dir, force)
        results.append(path)
    return results


# =============================================================================
# Ejemplo de uso
# =============================================================================

if __name__ == "__main__":
    SYMBOLS = ["XAUUSD", "SP500"]
    FROM = datetime(2026, 6, 1)
    TO = datetime(2026, 6, 30)

    paths = ensure_backtest_data_for_symbols(SYMBOLS, FROM, TO)
    for p in paths:
        print(f"  Listo: {p}")
