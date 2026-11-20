"""Broad historical international equities screen with exact cutoff; not broker-verified.
Data discovery via TradingView unofficial screener; price histories from Yahoo Finance.
Honest failures and coverage tracking. ETF AUM screen is NOT implemented.
"""
import argparse, concurrent.futures, json, math, re, time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
import yfinance as yf
from tradingview_screener import Query, Column
from screener import evaluate_prices

MARKETS=[
 "australia","canada","uk","germany","france","japan","hongkong","korea",
 "india","switzerland","netherlands","italy","spain","sweden","singapore",
 "brazil","mexico","taiwan","newzealand","norway","denmark","finland",
 "belgium","poland","portugal","austria","ireland","indonesia","malaysia",
 "thailand","philippines","vietnam","saudiarabia","turkey","israel",
 "unitedarabemirates","chile","argentina","colombia","peru","southafrica"
]
SUFFIX={"australia":".AX","canada":".TO","uk":".L","germany":".DE","france":".PA","japan":".T","hongkong":".HK","korea":".KS","india":".NS","switzerland":".SW","netherlands":".AS","italy":".MI","spain":".MC","sweden":".ST","singapore":".SI","brazil":".SA","mexico":".MX","taiwan":".TW","newzealand":".NZ","norway":".OL","denmark":".CO","finland":".HE","belgium":".BR","poland":".WA","portugal":".LS","austria":".VI","ireland":".IR","indonesia":".JK","malaysia":".KL","thailand":".BK","philippines":".PS","vietnam":".VN","saudiarabia":".SR","turkey":".IS","israel":".TA","unitedarabemirates":".AE","chile":".SN","argentina":".BA","colombia":".CL","peru":".LM","southafrica":".JO"}
PAGE=1000
MAX=20000

def ticker_map(row,market):
    ticker=str(row.get("ticker",""))
    parts=ticker.split(":")
    exch=parts[0] if len(parts)>1 else ""
    symbol=str(row.get("name") or parts[-1])
    if not symbol or market not in SUFFIX:return None
    if market=="germany":
        if exch in ("FWB","FRA"):return symbol+".F"
        if exch not in ("XETR","XETRA"):return None
    if market=="korea" and exch=="KOSDAQ":return symbol+".KQ"
    if market=="india" and exch=="BSE":return symbol+".BO"
    if market=="taiwan" and exch=="TPEX":return symbol+".TWO"
    if market=="hongkong":symbol=symbol.zfill(4)
    if market=="sweden":symbol=symbol.replace("_","-")
    if market=="india":symbol=symbol.replace("_","-")
    if market=="mexico":symbol=symbol.replace("/","-")
    if market=="canada":symbol=symbol.replace(".","-")
    return symbol+SUFFIX[market]

def fetch_market(market):
    rows=[];error=None;total=0
    for offset in range(0,MAX,PAGE):
        try:
            query=(Query().set_markets(market)
              .select("name","description","type","country","exchange","is_primary",
                "market_cap_basic","close","currency","SMA150","RSI","sector","average_volume_30d_calc")
              .set_property("price_conversion",{"to_currency":"usd"})
              .where(Column("type")=="stock",Column("is_primary")==True,
                     Column("market_cap_basic")>=1_000_000_000)
              .offset(offset).limit(offset+PAGE))
            result_count,frame=query.get_scanner_data()
            total=int(result_count)
            rows.extend(frame.to_dict("records"))
            if len(frame)<PAGE or len(rows)>=total:break
        except Exception as exc:
            error=f"At offset {offset}: {str(exc)[:200]}"
            break
        time.sleep(.2)
    return rows, {"market":market,"total_provider_filtered":total,"retrieved":len(rows),
      "error":error,"complete":error is None and len(rows)>=total}

def scan_one(item,cutoff):
    symbol,meta=item
    try:
        hist=yf.Ticker(symbol).history(period="2y",interval="1d",auto_adjust=False,timeout=20)
        if hist.empty:raise ValueError("empty daily history")
        # A strict historical replay: use bars dated BEFORE 20 Nov 2026
        # for a 6am Perth scan on 20 Nov. Future-scheduled runs use
        # latest completed day based on local market and trade completion;
        # date-only cutoff is conservative if market hours uncertain.
        last_date=(cutoff.astimezone(ZoneInfo("Australia/Perth"))-timedelta(days=1)).date()
        hist=hist[hist.index.date<=last_date]
        if hist.empty:raise ValueError("no completed session by cutoff")
        data=evaluate_prices(hist)
        if data["session"]!=str(last_date):
            raise ValueError(f"stale session {data['session']} expected {last_date}")
        out={"status":"ok","symbol":symbol,**meta,**data}
        return out
    except Exception as exc:
        return {"status":"error","symbol":symbol,"tv_ticker":meta.get("ticker"),"reason":str(exc)[:180]}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--asof-perth",default=None)
    parser.add_argument("--shard-number",type=int,default=0)
    parser.add_argument("--shards",type=int,default=1)
    args=parser.parse_args()
    cutoff=(datetime.fromisoformat(args.asof_perth) if args.asof_perth else datetime.now(ZoneInfo("Australia/Perth")))
    if cutoff.tzinfo is None:raise ValueError("--asof-perth must include timezone offset")
    # Scheduled 06:00 Perth: all included non-US markets typically have their
    # previous local date's closing session available. A later manual run
    # simulates the latest 06:00 Perth by rounding back.
    cutoff=cutoff.astimezone(ZoneInfo("Australia/Perth"))
    cutoff=cutoff.replace(hour=6,minute=0,second=0,microsecond=0)
    root=Path("reports");root.mkdir(exist_ok=True)
    allrows={};markets=[]
    if args.shards<1 or args.shard_number<0 or args.shard_number>=args.shards:raise ValueError("invalid shard configuration")
    selected_markets=[m for i,m in enumerate(MARKETS) if i%args.shards==args.shard_number]
    for market in selected_markets:
        rows,stat=fetch_market(market)
        markets.append(stat)
        for row in rows:
            if str(row.get("country","")).strip().lower()=="united states":continue
            if row.get("is_primary") is not True:continue
            key=ticker_map(row,market)
            if not key:continue
            # Retain TV's USD-converted cap; this is a current-screen estimate,
            # not a historical 06:00 cap.
            row["market"]=market
            if key not in allrows:allrows[key]=row
        print("MARKET",market,stat,"ADDED_TOTAL",len(allrows),flush=True)
    data=[];errors=[]
    print("PRICE_HISTORY_START",len(allrows),flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(scan_one,x,cutoff) for x in allrows.items()]
        for ix,fut in enumerate(concurrent.futures.as_completed(futures),1):
            result=fut.result()
            if result["status"]=="ok":
                data.append(result)
            else:errors.append(result)
            if ix%500==0:print("HISTORY_PROGRESS",ix,len(allrows),"ok",len(data),"errors",len(errors),flush=True)
    technical=[x for x in data if x["technical_pass"]]
    # Conservative liquidity: quote currency from TradingView. No reliable
    # local/USD FX snapshot stored, so the USD 1m condition is NOT validated.
    technical.sort(key=lambda x:x.get("rsi14",0),reverse=True)
    out={
      "shard_number":args.shard_number,"shards_total":args.shards,
      "asof_perth":cutoff.isoformat(),
      "generated_utc":datetime.now(timezone.utc).isoformat(),
      "screen_type":"BROAD_HISTORICAL_EQUITY_ATTEMPT_NOT_FULL_COVERAGE",
      "markets":markets,
      "markets_success":sum(x["complete"] for x in markets),
      "market_errors":sum(not x["complete"] for x in markets),
      "universe_after_current_usd_market_cap_and_primary_listing_prequal":len(allrows),
      "histories_complete":len(data),
      "histories_unavailable_or_stale":len(errors),
      "technical_matches":technical,
      "broker_verified_investment_opportunities":[],
      "limitations":[
         "Today's market-cap prefilter is not historical as-of 06:00; 2026-11-20 06:00 replay is approximated.",
         "No exhaustive exchange/ETF universe; ETF AUM not screened.",
         "ETF/SPAC classification beyond is_primary/type not definitively checked.",
         "30-day USD traded value and exact broker purchase accessibility are NOT verified.",
         "TradingView/Yahoo ticker mapping sometimes mismatches and may cause failures.",
         "TradingView 10,3 Supertrend calculation parity remains unvalidated.",
         "Data source is unofficial and availability can change."],
      "history_errors":errors}
    (root/f"full_equity_attempt_shard{args.shard_number}.json").write_text(json.dumps(out,indent=2,default=str))
    md=["# Broad international equities screen",f"As of Perth: {cutoff.isoformat()}",
       "**NOT COMPLETE; technical-only signals, NOT broker-verified investment recommendations.**",
       f"Markets successfully retrieved: {out['markets_success']}/{len(markets)}",
       f"Unique primary-listing equities prequalified: {len(allrows)}",
       f"Valid completed historical analyses: {len(data)}, unavailable/stale: {len(errors)}",
       f"Fresh bullish technical matches: {len(technical)}",
       "## Technical-only review candidates"]
    md += [f"- {x.get('ticker','')} ({x['symbol']}) | {x.get('description','')} | {x['market']} | {x['session']} | close {x['close']} {x.get('currency','')} | RSI {x['rsi14']} | +{round(100*(x['close']/x['sma150']-1),2)}% over SMA150 | current market cap (USD estimate) {x.get('market_cap_basic')} | **broker unverified**" for x in technical] or ["None with validated complete histories."]
    md += ["## Market errors"]+[f"- {m['market']}: {m['error']}" for m in markets if not m["complete"]]
    md += ["## Important limitations"]+out["limitations"]
    (root/f"full_equity_attempt_shard{args.shard_number}.md").write_text("\n\n".join(md))
    print("FULL_RESULT",json.dumps({"shard":args.shard_number,"asof":out["asof_perth"],"markets_success":out["markets_success"],"market_errors":out["market_errors"],"universe":len(allrows),"analysed":len(data),"failed_or_stale":len(errors),"matches":technical[:60],"total_matches":len(technical)},default=str),flush=True)
    if not data:raise SystemExit("No valid price histories")
if __name__=="__main__":main()
