"""Expanded international TECHNICAL test, not a full-market or broker-verified scan."""
import json, time, concurrent.futures
from pathlib import Path
from datetime import datetime,timezone
import yfinance as yf
from tradingview_screener import Query, Column
from screener import evaluate_prices

MARKETS=["australia","canada","uk","germany","france","japan","hongkong","korea","india","switzerland","netherlands","italy","spain","sweden","singapore","brazil","mexico","taiwan","newzealand"]
SUFFIX={"australia":".AX","canada":".TO","uk":".L","germany":".DE","france":".PA","japan":".T","hongkong":".HK","korea":".KS","india":".NS","switzerland":".SW","netherlands":".AS","italy":".MI","spain":".MC","sweden":".ST","singapore":".SI","brazil":".SA","mexico":".MX","taiwan":".TW","newzealand":".NZ"}
MAX_PER_MARKET=60
def yahoo_symbol(row,market):
    raw=str(row.get("ticker","")).split(":")
    exchange=raw[0] if len(raw)>1 else ""
    name=str(row.get("name",raw[-1]))
    if not name: return None
    if market=="india" and exchange=="BSE":return name+".BO"
    if market=="korea" and exchange=="KOSDAQ":return name+".KQ"
    if market=="taiwan" and exchange=="TPEX":return name+".TWO"
    if market=="germany":
        if exchange in ("FWB","FRA"):return name+".F"
        if exchange not in ("XETR","XETRA"):return None
    if market=="hongkong":name=name.zfill(4)
    return name+SUFFIX[market]
def scan_one(item):
    symbol,market,tv=item
    try:
        h=yf.Ticker(symbol).history(period="2y",interval="1d",auto_adjust=False,timeout=12)
        if h.empty: raise ValueError("empty daily history")
        result=evaluate_prices(h)
        return {"status":"ok","symbol":symbol,"tv_ticker":tv,"market":market,**result}
    except Exception as exc:
        return {"status":"failed","symbol":symbol,"market":market,"error":str(exc)[:140]}
def main():
    Path("reports").mkdir(exist_ok=True)
    markets=[];failed_markets=[];selected={}
    for market in MARKETS:
        try:
            q=(Query().set_markets(market).select("name","close","volume","market_cap_basic","RSI","exchange","currency").where(Column("market_cap_basic")>=1_000_000_000,Column("RSI")>=50).limit(MAX_PER_MARKET))
            total,df=q.get_scanner_data()
            markets.append({"market":market,"preliminary_total":int(total),"sampled":len(df)})
            for row in df.to_dict("records"):
                y=yahoo_symbol(row,market)
                if y and y not in selected:selected[y]=(y,market,str(row.get("ticker","")))
            print("DISCOVERY",market,total,len(df),flush=True)
        except Exception as e:
            failed_markets.append({"market":market,"reason":str(e)[:180]})
    print("START_PRICES",len(selected),flush=True)
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures=[executor.submit(scan_one,row) for row in selected.values()]
        for i,f in enumerate(concurrent.futures.as_completed(futures),1):
            results.append(f.result())
            if i%100==0: print("PROGRESS",i,"/",len(selected),flush=True)
    good=[r for r in results if r["status"]=="ok"]
    matched=[r for r in good if r["technical_pass"]]
    failed=[r for r in results if r["status"]!="ok"]
    report={"generated_utc":datetime.now(timezone.utc).isoformat(),
      "status":"PARTIAL_TECHNICAL_SAMPLE_NOT_FULL_MARKET",
      "markets":markets,"market_failures":failed_markets,
      "unique_candidates_attempted":len(selected),"price_histories_successful":len(good),
      "price_histories_failed":len(failed),
      "technical_matches":matched,
      "broker_verified_matches":[],
      "limitations":["Top 60 RSI>=50 and provider-native market-cap filtered symbols per market; not an exhaustive universe.",
      "Market capitalisation may be in local currencies rather than USD equivalent.",
      "Company versus ETF/SPAC classification not validated.",
      "TradingView API via unofficial library is not guaranteed to stay available.",
      "Cross-market market cap/volume comparisons, ETF AUM and FX conversion are not validated.",
      "No Westpac/eToro outright purchase verification; matches are technical research only.",
      "Intraday/incomplete daily bars have not been excluded for markets currently open.",
      "Supertrend differences from TradingView's chart initialization have not been backtested."],
      "download_failures":failed}
    Path("reports/expanded_technical_test.json").write_text(json.dumps(report,indent=2,default=str))
    lines=["# Expanded international technical test","**NOT a full-market screen. NOT broker-verified recommendations.**",
      f"Markets queried: {len(markets)}, market errors: {len(failed_markets)}",
      f"History attempts: {len(selected)}, successful: {len(good)}, failed: {len(failed)}, technical matches: {len(matched)}",
      "## Technical candidates (unverified)"]
    lines += [f"- {x['tv_ticker']} / {x['symbol']}: session {x['session']}; close {x['close']}; SMA150 {x['sma150']}; RSI {x['rsi14']}" for x in matched] or ["None in this sampled set."]
    lines += ["## Limitations"]+report["limitations"]
    Path("reports/expanded_technical_test.md").write_text("\n\n".join(lines)+"\n")
    print("RESULT",json.dumps({"attempted":len(selected),"successful":len(good),"failed":len(failed),"technical_matches":matched,"broker_verified":0,"markets":len(markets)}),flush=True)
if __name__=="__main__":main()
