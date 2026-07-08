from decimal import Decimal
from .base import BrokerBase


ALL_FX_SYMBOLS = (
    "AUDCAD", "AUDCHF", "AUDJPY", "AUDNZD", "AUDUSD",
    "CADCHF", "CADJPY", "CHFJPY",
    "EURAUD", "EURCAD", "EURCHF", "EURGBP", "EURJPY", "EURNZD", "EURUSD", "EURMXN",
    "GBPAUD", "GBPCAD", "GBPCHF", "GBPJPY", "GBPNZD", "GBPUSD",
    "NZDCAD", "NZDCHF", "NZDJPY", "NZDUSD",
    "USDCAD", "USDCHF", "USDJPY", "USDSEK", "USDNOK", "USDMXN",
)

PRECIOUS_METALS = ("XAUUSD", "XAGUSD", "XAUAUD", "XAUEUR", "XAGUSD", "XAGEUR")

COMMODITIES = ("XTIUSD", "XBRUSD", "XNGUSD")

CRYPTO_SYMBOLS = ("BTCUSD", "ETHUSD", "BNBUSD", "LTCUSD", "XRPUSD")

INDICES = (
    "DJ30", "NAS100", "SP500", "GER40", "FRA40", "UK100",
    "AUS200", "STOXX50E", "EUSTX50", "JP225", "HK50", "CHINA50",
    "ES35", "NI225", "WS30", "FCHI40", "SPA35", "NDX", "GDAXI",
)


class VantageBase(BrokerBase):
    @property
    def name(self) -> str:
        return "Vantage"


class RawECN(VantageBase):
    @property
    def name(self) -> str:
        return "Vantage Raw ECN"

    def commission_per_lot(self, symbol: str) -> Decimal:
        if symbol in ALL_FX_SYMBOLS:
            return Decimal('3.00')
        if symbol in PRECIOUS_METALS:
            return Decimal('3.00')
        if symbol in COMMODITIES:
            return Decimal('3.00')
        if symbol in INDICES:
            return Decimal('0')
        if symbol in CRYPTO_SYMBOLS:
            return Decimal('0')
        return Decimal('3.00')


class ProECN(VantageBase):
    @property
    def name(self) -> str:
        return "Vantage Pro ECN"

    def commission_per_lot(self, symbol: str) -> Decimal:
        if symbol in ALL_FX_SYMBOLS:
            return Decimal('1.50')
        if symbol in PRECIOUS_METALS:
            return Decimal('1.50')
        if symbol in COMMODITIES:
            return Decimal('1.50')
        if symbol in INDICES:
            return Decimal('0')
        if symbol in CRYPTO_SYMBOLS:
            return Decimal('0')
        return Decimal('1.50')


class StandardSTP(VantageBase):
    @property
    def name(self) -> str:
        return "Vantage Standard STP"

    def commission_per_lot(self, symbol: str) -> Decimal:
        return Decimal('0')
