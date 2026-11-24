# International Stock Screener

Free automated screening of non-US exchange-listed companies and ETFs, with a conservative research-only output when eligibility is unverified.

## Schedule

GitHub Actions: 22:00 UTC Monday–Friday, corresponding to **06:00 AWST Tuesday–Saturday**. GitHub-hosted scheduled jobs may start late. The latest completed local exchange session is validated against supported exchange calendars.

## Daily prerequisites

- TradingView **Daily Technical Rating Strong Buy** (composite `Recommend.All > 0.50`).
- **Fresh Supertrend 10,3** bearish → bullish switch on the latest completed local session, using Yahoo Finance historical prices.
- RSI(14) >= 50 and daily close above SMA(150).
- Primary non-US-listed shares with TradingView USD-converted market capitalisation >= US$1 billion.
- Exchange-traded funds from TradingView's **dedicated ETF Screener** with AUM >= US$100 million.
- Thirty-session average daily USD turnover >= US$1 million (daily price×volume converted using free FX data).
- An exact evidence-backed Westpac or eToro Australia listing verified as an **outright purchase**, not a CFD.

## Output

The workflow runs eight shards and merges their artifacts into one `international-morning-report` artifact and GitHub Actions step summary. The concise report shows:

1. **Technical candidates for manual chart review:** pass technical filters and USD turnover, but broker status may be unverified.
2. **Verified purchase opportunities:** pass all prerequisites including exact broker confirmation.
3. **Excluded technical signals:** failed or unverified liquidity.
4. **Coverage diagnostics:** market discovery, stock vs ETF mapping/price coverage, missing sessions, capped ETF markets, and broker status.

### Known limitations (read before making decisions)

- Broker verification is **fail-closed**. `data/broker_verified.csv` currently has **no verified rows**, so zero final purchase opportunities are intentional. Public quote pages do not prove Australian-account underlying-share/ETF outright availability.
- ETF discovery uses the TradingView ETF endpoint, with **top 80 AUM-ranked ETFs per market** as a free resource limit. Markets at the cap are flagged incomplete; this is **not an exhaustive ETF scan**.
- Market-discovery snapshots (market cap/AUM/Strong Buy) are current at job execution. Previous 06:00 historical snapshots are not archived.
- Some Yahoo Finance ticker mappings do not match TradingView, some instruments have less than 175 complete price bars, and some symbols have stale data. These are excluded and counted as coverage gaps.
- Not all exchange calendars are available through the calendar library. Unsupported markets cannot be claimed scanned successfully.
- Independent TradingView chart parity for the locally computed Supertrend 10,3 has not been comprehensively audited.
- Scheduled results are stored on GitHub Actions. Delivery *into a ChatGPT conversation* is separate and not configured by this repository.

## Tools

`pipeline.py`: market discovery, ETF filtering, exchange-local session checks, historical price analysis, FX and broker evidence gates.

`consolidate.py`: merges eight machine-readable reports into one concise report with coverage warnings.

`test_pipeline.py`, `test_screener.py`: automated regression tests.

**Not investment advice:** always inspect TradingView charts and confirm broker order type, spread, liquidity and fees before trading.
