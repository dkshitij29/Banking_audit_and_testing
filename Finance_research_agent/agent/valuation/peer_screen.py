"""Sector-based peer discovery."""

from agent.data.market_data import MarketDataProvider


def find_peers(ticker: str, market_data: MarketDataProvider) -> list[str]:
    """Find peers by sector + market cap filter."""
    peers = market_data.fetch_peers(ticker)
    return peers[:5]
