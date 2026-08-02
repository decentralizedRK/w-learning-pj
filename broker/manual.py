from loguru import logger

from broker.base import BaseBroker, OrderResponse


class ManualBroker(BaseBroker):
    """Signal-only broker for accounts without API access (e.g., Groww).

    Logs trade signals for manual execution. Telegram integration planned.
    """

    def __init__(self, account_name: str = "manual"):
        self.account_name = account_name

    def authenticate(self) -> bool:
        logger.info(f"Manual broker '{self.account_name}' ready (no API auth needed)")
        return True

    def get_ltp(self, symbols: list[str]) -> dict[str, float]:
        logger.warning("ManualBroker: LTP not available, use market data fetchers")
        return {}

    def get_positions(self) -> list[dict]:
        logger.warning("ManualBroker: positions must be tracked manually")
        return []

    def get_holdings(self) -> list[dict]:
        logger.warning("ManualBroker: holdings must be tracked manually")
        return []

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
    ) -> OrderResponse:
        logger.info(
            f"[SIGNAL] {self.account_name}: {transaction_type} {quantity} {symbol} "
            f"@ {order_type} {price if price else ''} | Product: {product}"
        )
        return OrderResponse(
            order_id="MANUAL",
            status="SIGNAL_SENT",
            symbol=symbol,
            quantity=quantity,
            price=price,
            message=f"Place this trade manually on {self.account_name}",
        )

    def get_margins(self) -> dict:
        return {}

    def get_orders(self) -> list[dict]:
        logger.warning("ManualBroker: orders must be tracked manually")
        return []

    def get_trades(self) -> list[dict]:
        logger.warning("ManualBroker: trades must be tracked manually")
        return []
