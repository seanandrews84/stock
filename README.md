# International Stock Screener

Automated international (non-US listings) Supertrend screening project.

**Status:** In development. No full-universe or broker-availability verification has yet been completed.

Target strategy: latest completed daily bar switches Supertrend (ATR 10, multiplier 3) from bearish to bullish; RSI(14) ≥50; close > SMA(150); exclude SPACs and US listings; company market cap ≥ USD 1 billion or ETF AUM ≥ USD 100 million; average daily traded value ≥ USD 1 million. Report only securities verified purchasable outright on Westpac Share Trading or eToro Australia, not CFDs.

The system must report the number of securities actually processed and distinguish incomplete coverage from zero matches.
