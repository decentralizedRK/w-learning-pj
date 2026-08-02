from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Quote:
    symbol: str
    ltp: float
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass
class OrderResponse:
    order_id: str
    status: str
    symbol: str
    quantity: int
    price: float
    message: str = ""


class BaseBroker(ABC):
    @abstractmethod
    def authenticate(self) -> bool: ...

    @abstractmethod
    def get_ltp(self, symbols: list[str]) -> dict[str, float]: ...

    @abstractmethod
    def get_positions(self) -> list[dict]: ...

    @abstractmethod
    def get_holdings(self) -> list[dict]: ...

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        exchange: str,
        transaction_type: str,
        quantity: int,
        order_type: str = "MARKET",
        price: float = 0,
        trigger_price: float = 0,
        product: str = "NRML",
    ) -> OrderResponse: ...

    @abstractmethod
    def get_margins(self) -> dict: ...

    @abstractmethod
    def get_orders(self) -> list[dict]: ...

    @abstractmethod
    def get_trades(self) -> list[dict]: ...
