"""Static seed data — no imports, no logic."""

SEED_LEVERAGED_ETFS: list[dict] = [
    {"ticker": "TSLL", "underlying": "TSLA", "leverage_factor":  2.0, "name": "Direxion Daily TSLA Bull 2X"},
    {"ticker": "TSLS", "underlying": "TSLA", "leverage_factor": -1.0, "name": "Direxion Daily TSLA Bear 1X"},
    {"ticker": "NVDL", "underlying": "NVDA", "leverage_factor":  2.0, "name": "GraniteShares 2x Long NVDA"},
    {"ticker": "NVDS", "underlying": "NVDA", "leverage_factor": -1.5, "name": "AXS 1.5X NVDA Bear Daily ETF"},
    {"ticker": "SOXL", "underlying": "SOXX", "leverage_factor":  3.0, "name": "Direxion Daily Semiconductors Bull 3X"},
    {"ticker": "SOXS", "underlying": "SOXX", "leverage_factor": -3.0, "name": "Direxion Daily Semiconductors Bear 3X"},
    {"ticker": "TQQQ", "underlying": "QQQ",  "leverage_factor":  3.0, "name": "ProShares UltraPro QQQ"},
    {"ticker": "SQQQ", "underlying": "QQQ",  "leverage_factor": -3.0, "name": "ProShares UltraPro Short QQQ"},
    {"ticker": "UPRO", "underlying": "SPY",  "leverage_factor":  3.0, "name": "ProShares UltraPro S&P500"},
    {"ticker": "SPXL", "underlying": "SPY",  "leverage_factor":  3.0, "name": "Direxion Daily S&P 500 Bull 3X"},
    {"ticker": "SPXS", "underlying": "SPY",  "leverage_factor": -3.0, "name": "Direxion Daily S&P 500 Bear 3X"},
    {"ticker": "LABU", "underlying": "IBB",  "leverage_factor":  3.0, "name": "Direxion Daily S&P Biotech Bull 3X"},
    {"ticker": "FAS",  "underlying": "XLF",  "leverage_factor":  3.0, "name": "Direxion Daily Financial Bull 3X"},
    {"ticker": "TNA",  "underlying": "IWM",  "leverage_factor":  3.0, "name": "Direxion Daily Small Cap Bull 3X"},
    {"ticker": "FNGU", "underlying": "FANG+", "leverage_factor": 3.0, "name": "MicroSectors FANG+ Index 3X Leveraged ETN"},
    {"ticker": "MSTU", "underlying": "MSTR", "leverage_factor":  2.0, "name": "T-Rex 2X Long MSTR Daily Target ETF"},
    {"ticker": "MSTZ", "underlying": "MSTR", "leverage_factor": -2.0, "name": "T-Rex 2X Inverse MSTR Daily Target ETF"},
]
