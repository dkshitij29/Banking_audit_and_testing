"""Peer multiples comparison (EV/EBITDA, P/E, P/B)."""

from agent.models.valuation import CompsData, PeerMetric
from agent.data.market_data import MarketDataProvider
from agent.data.yfinance_adapter import YFinanceAdapter
from typing import Optional


def compute_comps(
    ticker: str,
    peers: list[str],
    market_data: MarketDataProvider,
) -> CompsData:
    """Run peer comparison using EV/EBITDA, P/E, P/B multiples."""
    adapter = YFinanceAdapter()

    target_data = market_data.fetch_price(ticker)
    if not target_data:
        return CompsData(ticker=ticker, peers=[])

    peers_data: list[PeerMetric] = []

    for peer_ticker in peers:
        peer_info = market_data.fetch_price(peer_ticker)
        if not peer_info:
            continue

        peer_metric = PeerMetric(
            ticker=peer_ticker,
            market_cap=peer_info.get("market_cap"),
            enterprise_value=peer_info.get("enterprise_value"),
            share_price=peer_info.get("current_price"),
            pe_ratio=peer_info.get("trailing_pe"),
        )

        peer_financials = market_data.fetch_financials(peer_ticker)
        if peer_financials["income_statement"]:
            stmt = peer_financials["income_statement"][0]
            if stmt.ebitda and peer_metric.enterprise_value:
                peer_metric.ev_ebitda = peer_metric.enterprise_value / stmt.ebitda
            if stmt.eps_diluted:
                peer_metric.eps = stmt.eps_diluted
            peer_metric.ebitda = stmt.ebitda

        if peer_metric.ev_ebitda or peer_metric.pe_ratio:
            peers_data.append(peer_metric)

    ev_ebitdas = [p.ev_ebitda for p in peers_data if p.ev_ebitda]
    pe_ratios = [p.pe_ratio for p in peers_data if p.pe_ratio]
    pb_ratios = [p.pb_ratio for p in peers_data if p.pb_ratio]

    median_ev_ebitda = sorted(ev_ebitdas)[len(ev_ebitdas) // 2] if ev_ebitdas else None
    median_pe = sorted(pe_ratios)[len(pe_ratios) // 2] if pe_ratios else None
    median_pb = sorted(pb_ratios)[len(pb_ratios) // 2] if pb_ratios else None

    target_financials = market_data.fetch_financials(ticker)
    target_is = target_financials["income_statement"][0] if target_financials["income_statement"] else None

    implied_price_ev = _implied_price_from_ev_ebitda(target_data, target_is, median_ev_ebitda)
    implied_price_pe = _implied_price_from_pe(target_data, target_is, median_pe)
    implied_price_pb = None

    implied_prices = [p for p in [implied_price_ev, implied_price_pe, implied_price_pb] if p is not None]
    implied_median = sorted(implied_prices)[len(implied_prices) // 2] if implied_prices else None

    return CompsData(
        ticker=ticker,
        peers=peers_data,
        median_ev_ebitda=median_ev_ebitda,
        median_pe=median_pe,
        median_pb=median_pb,
        implied_price_ev_ebitda=implied_price_ev,
        implied_price_pe=implied_price_pe,
        implied_price_pb=implied_price_pb,
        implied_median_price=implied_median,
    )


def _implied_price_from_ev_ebitda(price_data: dict, is_stmt: Optional[any], median_multiple: Optional[float]) -> Optional[float]:
    if not median_multiple or not is_stmt or not is_stmt.ebitda:
        return None
    implied_ev = is_stmt.ebitda * median_multiple
    shares = price_data.get("shares_outstanding")
    if not shares:
        return None
    return implied_ev / shares


def _implied_price_from_pe(price_data: dict, is_stmt: Optional[any], median_pe: Optional[float]) -> Optional[float]:
    if not median_pe or not is_stmt:
        return None
    if is_stmt.eps_diluted:
        return is_stmt.eps_diluted * median_pe
    elif is_stmt.eps:
        return is_stmt.eps * median_pe
    return None


def render_comps_table(comps: CompsData) -> str:
    """Render comps table as formatted text."""
    lines = ["PEER", "EV/EBITDA", "P/E", "Price"]
    lines.append("-" * 50)

    for p in comps.peers:
        ev_eb = f"{p.ev_ebitda:.1f}x" if p.ev_ebitda else "N/A"
        pe = f"{p.pe_ratio:.1f}x" if p.pe_ratio else "N/A"
        price = f"${p.share_price:.2f}" if p.share_price else "N/A"
        lines.append(f"{p.ticker:<8} {ev_eb:<12} {pe:<10} {price}")

    lines.append("-" * 50)
    ev_eb = f"{comps.median_ev_ebitda:.1f}x" if comps.median_ev_ebitda else "N/A"
    pe = f"{comps.median_pe:.1f}x" if comps.median_pe else "N/A"
    price = f"${comps.implied_median_price:.2f}" if comps.implied_median_price else "N/A"
    lines.append(f"{'Median':<8} {ev_eb:<12} {pe:<10} {price}")

    return "\n".join(lines)
