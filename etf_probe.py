"""Test dedicated, free TradingView ETF endpoint independently of stocks."""
import inspect
try:
 from tvscreener import ETFScreener, StockField
 print("ETF_PROBE", "class", ETFScreener,flush=True)
 es=ETFScreener()
 print("ETF_PROBE", "methods", [x for x in dir(es) if any(p in x for p in ("market","range","where","select","get","country"))],flush=True)
 print("ETF_PROBE", "methodsigs",[(k,str(inspect.signature(getattr(es,k)))) for k in ("set_markets","set_range","set_market","get") if hasattr(es,k)],flush=True)
 es.where(StockField.AUM>=100_000_000)
 es.set_range(0,10)
 df=es.get()
 print("ETF_PROBE", "rows",len(df),"columns",list(df.columns),"samples",df.head(4).to_dict("records"),flush=True)
except Exception as exc:
 print("ETF_PROBE_ERROR",type(exc).__name__,str(exc)[:1000],flush=True)
