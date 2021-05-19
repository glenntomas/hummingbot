#!/usr/bin/env python

import logging
import pandas as pd

from typing import (
    Dict,
)

from hummingbot.core.clock import Clock
from hummingbot.core.utils.async_utils import safe_ensure_future
from hummingbot.connector.exchange_base import ExchangeBase
from hummingbot.logger import HummingbotLogger
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple
from hummingbot.strategy.strategy_py_base import StrategyPyBase

gob_logger = None


class GetOrderBookStrategy(StrategyPyBase):
    """
    Simple strategy. This strategy waits for connector to be ready. Displays the live order book as per running
    the `orderbook --live` command.
    Note: Strategy is intended to be a developer guide.
    """

    @classmethod
    def logger(cls) -> HummingbotLogger:
        global gob_logger
        if gob_logger is None:
            gob_logger = logging.getLogger(__name__)
        return gob_logger

    def __init__(self,
                 exchange: ExchangeBase,
                 market_info: Dict[str, MarketTradingPairTuple],
                 trading_pair: str,
                 lines: int,
                 ):

        super().__init__()
        self._exchange = exchange
        self._market_info = market_info
        self._trading_pair = trading_pair
        self._lines = lines

        self.add_markets([self._exchange])

        self._ready = False
        self._get_order_book_task = None

    def notify_hb_app(self, msg: str):
        """
        Method called to display message on the Output Panel(upper left)
        """
        from hummingbot.client.hummingbot_application import HummingbotApplication
        HummingbotApplication.main_application()._notify(msg)

    async def format_status(self) -> str:
        """
        Method called by the `status` command. Generates the status report for this strategy.
        Outputs the best bid and ask prices for the specified trading
        """
        if not self._ready:
            return "Exchange connector(s) are not ready."
        lines = []

        for market_info in self._market_infos.values():
            lines.extend(["", "  Assets:"] + ["    " + str(self._asset) + "    " +
                                              str(market_info.market.get_balance(self._asset))])

        return "\n".join(lines)

    def get_order_book(self):
        order_book = self._exchange.order_books[self._trading_pair]

        bids = order_book.snapshot[0][['price', 'amount']].head(self._lines)
        bids.rename(columns={'price': 'bid_price', 'amount': 'bid_volume'}, inplace=True)
        asks = order_book.snapshot[1][['price', 'amount']].head(self._lines)
        asks.rename(columns={'price': 'ask_price', 'amount': 'ask_volume'}, inplace=True)
        joined_df = pd.concat([bids, asks], axis=1)
        text_lines = ["    " + line for line in joined_df.to_string(index=False).split("\n")]
        header = f"  market: {self._exchange.name} {self._trading_pair}\n"

        return header + "\n".join(text_lines)

    async def show_order_book(self):
        from hummingbot.client.hummingbot_application import HummingbotApplication
        main_app = HummingbotApplication.main_application()

        if self._trading_pair not in self._exchange.order_books:
            self.logger().error(f"Invalid market {self._trading_pair} on {self._exchange.name} connector.")
            raise ValueError(f"Invalid market {self._trading_pair} on {self._exchange.name} connector.")

        await main_app.stop_live_update()
        main_app.app.live_updates = True
        while main_app.app.live_updates:
            await main_app.cls_display_delay(self.get_order_book() + "\n\n Press escape key to stop update.", 0.5)

        self.notify_hb_app("Stopped live orderbook display update.")

    def stop(self, clock: Clock):
        """
        Performs the necessary stop process. This function is called after the StrategyBase.c_stop() is called.
        """
        if self._get_order_book_task is not None:
            self._get_order_book_task.cancel()
            self._get_order_book_task = None

    def tick(self, timestamp: float):
        """
        Clock tick entry point, it runs every second (on normal tick settings)
        : param timestamp: current tick timestamp
        """
        if self._ready:
            return

        if not self._ready and not self._exchange.ready:
            # Message output using self.logger() will be displayed on Log panel(right) and saved on the strategy's log file.
            self.logger().warning(f"{self._exchange.name} is not ready. Please wait...")
        else:
            # Message output using self.notify_hb_app(...) will be displayed on the Output panel(upper left) and not saved on the strategy's log file.
            self.notify_hb_app(f"{self._exchange.name.upper()} Connector is ready!")
            try:
                if self._get_order_book_task is None:
                    self._get_order_book_task = safe_ensure_future(self.show_order_book())
                    self._ready = True
            except Exception:
                self.logger().error("Error starting live order book. ",
                                    exc_info=True)
                self._ready = False

        return
