"""Diagnostic-only probe of the unofficial TradingView ETF fields."""
from tradingview_screener import Query,Column
for market in ("australia","canada","uk","germany"):
 for name,filters in (
  ("fund-type", [Column("type")=="fund"]),
  ("fund-subtype", [Column("type")=="fund", Column("subtype")=="etf"]),
  ("fund-aum", [Column("type")=="fund",Column("fund_total_assets")>=100_000_000]),
  ("etf-subtype", [Column("subtype")=="etf"]),
 ):
  try:
   q=Query().set_markets(market).select("name","description","type","subtype","fund_total_assets","Recommend.All").where(*filters).limit(3)
   total,df=q.get_scanner_data()
   print("ETF_DIAG",market,name,"COUNT",total,"SAMPLE",df.to_dict("records"),flush=True)
  except Exception as e:print("ETF_DIAG",market,name,"ERROR",str(e)[:200],flush=True)
