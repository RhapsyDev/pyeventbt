from abc import ABC, abstractmethod
from decimal import Decimal


class BrokerBase(ABC):
    @abstractmethod
    def commission_per_lot(self, symbol: str) -> Decimal:
        """Commission per standard lot, per side, in account currency."""
        ...

    def round_turn_per_lot(self, symbol: str) -> Decimal:
        return self.commission_per_lot(symbol) * 2

    def calc_commission(self, symbol: str, volume: Decimal, trade_price: Decimal = None) -> Decimal:
        """Total commission for a round trip for the given volume (in lots).
        Override for percentage-based commission (e.g. crypto)."""
        return self.round_turn_per_lot(symbol) * volume

    @property
    @abstractmethod
    def name(self) -> str:
        ...
