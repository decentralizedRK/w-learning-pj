from loguru import logger

from broker.base import BaseBroker, OrderResponse
from config.settings import settings


class ZerodhaBroker(BaseBroker):
    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        access_token: str = "",
    ):
        self.api_key = api_key or settings.kite_api_key
        self.api_secret = api_secret or settings.kite_api_secret
        self.access_token = access_token or settings.kite_access_token
        self._kite = None

    def _get_kite(self):
        if self._kite is None:
            from kiteconnect import KiteConnect

            self._kite = KiteConnect(api_key=self.api_key)
            if self.access_token:
                self._kite.set_access_token(self.access_token)
        return self._kite

    def authenticate(self) -> bool:
        try:
            kite = self._get_kite()
            profile = kite.profile()
            logger.info(f"Authenticated as {profile['user_name']} ({profile['user_id']})")
            return True
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return False

    def generate_login_url(self) -> str:
        return self._get_kite().login_url()

    def generate_session(self, request_token: str) -> str:
        kite = self._get_kite()
        data = kite.generate_session(request_token, api_secret=self.api_secret)
        access_token = data["access_token"]
        kite.set_access_token(access_token)
        self.access_token = access_token
        logger.info("Session generated successfully")
        return access_token

    def get_ltp(
        self, symbols: list[str], exchange: str = "NSE"
    ) -> dict[str, float]:
        kite = self._get_kite()
        instrument_keys = [f"{exchange}:{s}" for s in symbols]
        data = kite.ltp(instrument_keys)
        return {
            key.split(":")[1]: val["last_price"]
            for key, val in data.items()
        }

    def get_positions(self) -> list[dict]:
        kite = self._get_kite()
        positions = kite.positions()
        return positions.get("net", [])

    def get_holdings(self) -> list[dict]:
        kite = self._get_kite()
        return kite.holdings()

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
        kite = self._get_kite()
        try:
            order_params = {
                "variety": kite.VARIETY_REGULAR,
                "exchange": exchange,
                "tradingsymbol": symbol,
                "transaction_type": transaction_type,
                "quantity": quantity,
                "order_type": order_type,
                "product": product,
            }
            if order_type in ("LIMIT", "SL"):
                order_params["price"] = price
            if order_type in ("SL", "SL-M"):
                order_params["trigger_price"] = trigger_price
            order_id = kite.place_order(**order_params)
            logger.info(f"Order placed: {order_id} | {transaction_type} {quantity} {symbol}")
            return OrderResponse(
                order_id=str(order_id),
                status="PLACED",
                symbol=symbol,
                quantity=quantity,
                price=price,
            )
        except Exception as e:
            logger.error(f"Order failed: {e}")
            return OrderResponse(
                order_id="",
                status="FAILED",
                symbol=symbol,
                quantity=quantity,
                price=price,
                message=str(e),
            )

    def get_margins(self) -> dict:
        kite = self._get_kite()
        return kite.margins()

    def get_orders(self) -> list[dict]:
        kite = self._get_kite()
        return kite.orders()

    def get_trades(self) -> list[dict]:
        kite = self._get_kite()
        return kite.trades()
