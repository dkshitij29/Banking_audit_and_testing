"""Phase 0: India market foundation tests."""

import pytest
from unittest.mock import patch, MagicMock


class TestMarketConfig:
    def test_us_defaults(self):
        from agent.config.markets import get_market_config
        cfg = get_market_config("US", 0.043, 0.0423)
        assert cfg.code == "US"
        assert cfg.currency == "USD"
        assert cfg.default_tax_rate == 0.21
        assert cfg.beta_index == "^GSPC"

    def test_in_defaults(self):
        from agent.config.markets import get_market_config
        cfg = get_market_config("IN", 0.073, 0.06)
        assert cfg.code == "IN"
        assert cfg.currency == "INR"
        assert cfg.default_tax_rate == 0.2517
        assert cfg.beta_index == "^NSEI"
        assert cfg.risk_free_rate == 0.073

    def test_in_case_insensitive(self):
        from agent.config.markets import get_market_config
        cfg = get_market_config("in", 0.073, 0.06)
        assert cfg.code == "IN"

    def test_is_india_config_ready_all_set(self):
        from agent.config.markets import is_india_config_ready
        result = is_india_config_ready(0.073, 0.06)
        assert result["ready"] is True
        assert result["missing"] == []

    def test_is_india_config_ready_missing_both(self):
        from agent.config.markets import is_india_config_ready
        result = is_india_config_ready(None, None)
        assert result["ready"] is False
        assert "IN_RISK_FREE_RATE" in result["missing"]
        assert "IN_EQUITY_RISK_PREMIUM" in result["missing"]

    def test_is_india_config_ready_partial(self):
        from agent.config.markets import is_india_config_ready
        result = is_india_config_ready(0.073, None)
        assert result["ready"] is False
        assert result["missing"] == ["IN_EQUITY_RISK_PREMIUM"]


class TestIndianSymbolResolver:
    @pytest.fixture(autouse=True)
    def load_resolver(self):
        from agent.data.in_symbols import IndianSymbolResolver
        self.resolver = IndianSymbolResolver()
        assert self.resolver.is_loaded(), "NSE data not loaded"

    def test_exact_nse_symbol(self):
        result = self.resolver.resolve("RELIANCE")
        assert result.ticker == "RELIANCE.NS"
        assert result.exchange == "NSE"

    def test_already_suffixed_ns(self):
        result = self.resolver.resolve("TCS.NS")
        assert result.ticker == "TCS.NS"

    def test_bse_code(self):
        result = self.resolver.resolve("500325")
        assert result.ticker == "RELIANCE.BO"
        assert result.exchange == "BSE"

    def test_fuzzy_name_match(self):
        from agent.data.in_symbols import AmbiguousSymbol
        result = self.resolver.resolve("Reliance Industries")
        # Could be Ambiguous (NSE+BSE share the same name) or a single winner
        if isinstance(result, AmbiguousSymbol):
            tickers = {c.ticker for c in result.candidates}
            assert "RELIANCE.NS" in tickers or "RELIANCE.BO" in tickers
        else:
            assert result.ticker in ("RELIANCE.NS", "RELIANCE.BO")

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown symbol"):
            self.resolver.resolve("ZZZZNONEXISTENT")

    def test_already_suffixed_bo(self):
        result = self.resolver.resolve("RELIANCE.BO")
        assert result.ticker == "RELIANCE.BO"


class TestIndiaStaticUniverse:
    @pytest.fixture(autouse=True)
    def load_universe(self):
        from agent.data.in_universe import IndiaStaticUniverse
        self.universe = IndiaStaticUniverse()
        assert self.universe.is_loaded(), "Universe data not loaded"

    def test_find_peers_by_sector(self):
        peers = self.universe.find_peers("RELIANCE.NS", sector="Energy")
        assert len(peers) >= 1
        assert all(p.symbol != "RELIANCE.NS" for p in peers)

    def test_find_peers_excludes_self(self):
        peers = self.universe.find_peers("TCS.NS", sector="Technology")
        assert all(p.symbol != "TCS.NS" for p in peers)

    def test_find_peers_limit(self):
        peers = self.universe.find_peers("TCS.NS", sector="Technology", n=3)
        assert len(peers) <= 3

    def test_get_entry(self):
        entry = self.universe.get_entry("RELIANCE.NS")
        assert entry is not None
        assert entry.name == "Reliance Industries"

    def test_get_all_sectors(self):
        sectors = self.universe.get_all_sectors()
        assert "Technology" in sectors
        assert "Financials" in sectors

    def test_empty_path(self, tmp_path):
        from agent.data.in_universe import IndiaStaticUniverse
        u = IndiaStaticUniverse(path=tmp_path / "nonexistent.csv")
        assert u.is_loaded() is False
        assert u.size == 0


class TestMarketDataProvider:
    @pytest.fixture(autouse=True)
    def setup_provider(self):
        from agent.config import Settings
        self.settings = Settings()

    def test_normalize_in_ticker(self):
        from agent.data.market_data import MarketDataProvider
        provider = MarketDataProvider(self.settings, market="IN")
        ticker = provider.normalize_ticker("RELIANCE")
        assert ticker.endswith(".NS") or ticker.endswith(".BO")

    def test_normalize_us_ticker(self):
        from agent.data.market_data import MarketDataProvider
        provider = MarketDataProvider(self.settings, market="US")
        ticker = provider.normalize_ticker("AAPL")
        assert ticker == "AAPL"

    def test_ambiguous_or_empty_symbol(self):
        from agent.data.market_data import MarketDataProvider, DataQualityError
        provider = MarketDataProvider(self.settings, market="IN")
        # Empty string should raise ValueError from resolver
        with pytest.raises(ValueError, match="Unknown symbol"):
            provider._in_resolver.resolve("")

    def test_default_market_is_us(self):
        from agent.data.market_data import MarketDataProvider
        provider = MarketDataProvider(self.settings)
        assert provider.market == "US"


class TestSettings:
    def test_india_fields_default(self):
        from agent.config import Settings
        # Create with no env vars to check defaults
        import os
        original = {k: os.environ.pop(k, None) for k in [
            "IN_RISK_FREE_RATE", "IN_EQUITY_RISK_PREMIUM",
        ]}
        try:
            s = Settings(_env_file=None)
            assert s.in_risk_free_rate is None
            assert s.in_equity_risk_premium is None
            assert s.in_default_tax_rate == 0.2517
            assert s.max_upload_files == 40
        finally:
            for k, v in original.items():
                if v is not None:
                    os.environ[k] = v
