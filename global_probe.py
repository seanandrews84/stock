"""Probe global TradingView stock discovery on hosted GitHub runner.

Uses a community-maintained library and an undocumented endpoint; coverage and
terms are not guaranteed. No recommendation or broker-availability claims.
"""
import json
from pathlib import Path
from datetime import datetime, timezone
from tradingview_screener import Query, Column
MARKETS=["australia","canada","uk","germany","france","japan","hongkong","korea","india","switzerland","netherlands","italy","spain","sweden","singapore","brazil","mexico","taiwan","southafrica","newzealand"]
out={"timestamp":datetime.now(timezone.utc).isoformat(),"markets_attempted":MARKETS,"markets_ok":[],"markets_failed":[],"count_total_market_cap_rsi_filtered":0,"candidates":[]}
for market in MARKETS:
    try:
        q=(Query().set_markets(market).select("name","close","volume","market_cap_basic","RSI","exchange","currency").where(Column("market_cap_basic")>=1_000_000_000,Column("RSI")>=50).limit(200))
        total,frame=q.get_scanner_data()
        d=frame.to_dict("records")
        out["markets_ok"].append({"market":market,"total_filtered":int(total),"returned":len(d)})
        out["count_total_market_cap_rsi_filtered"]+=int(total)
        out["candidates"] += [{"market":market,**{k:(None if str(v)=="nan" else v) for k,v in row.items()}} for row in d]
        print(market,"OK",total,len(d),flush=True)
    except Exception as ex:
        out["markets_failed"].append({"market":market,"error":str(ex)[:400]})
        print(market,"FAIL",str(ex)[:200],flush=True)
Path("reports").mkdir(exist_ok=True)
Path("reports/global_discovery_probe.json").write_text(json.dumps(out,default=str,indent=2))
print("SUMMARY",json.dumps({k:out[k] for k in ("markets_ok","markets_failed","count_total_market_cap_rsi_filtered")},default=str))
if not out["markets_ok"]:raise SystemExit("No TradingView international market could be retrieved")
