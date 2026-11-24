"""International equities/ETF screener with fail-closed eligibility.

Free/unofficial TradingView and Yahoo endpoints are not a completeness guarantee.
Only exact broker-approved listings can appear in 'verified_opportunities'.
"""
import argparse
import concurrent.futures
import csv
import json
import math
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from zoneinfo import ZoneInfo

import pandas as pd
import pandas_market_calendars as mcal
import yfinance as yf
from tradingview_screener import Column, Query
from full_scan import MARKETS, ticker_map, is_tv_strong_buy
from screener import evaluate_prices

ROOT = Path(__file__).resolve().parent
PROVIDER_MARKETS={"saudiarabia":"ksa","southafrica":"rsa","unitedarabemirates":"uae"}
# Calendar candidates are checked against the library registry at runtime.
CALENDAR_ALIASES={
 "mexico":["XMEX"],"newzealand":["XNZE"],"italy":["XMIL"],
 "indonesia":["XIDX"],"spain":["XMAD"],"denmark":["XCSE"],
 "finland":["XHEL"],"thailand":["XBKK"],"singapore":["XSES"],
 "philippines":["XPHS"],"poland":["XWAR"],"israel":["TASE","XTAE"],
 "turkey":["XIST"],"southafrica":["XJSE"],
 "portugal":["XLIS"],"ireland":["XDUB"],"vietnam":["XHCM"],
 "chile":["XSGO"],"colombia":["XBOG"],"peru":["XLIM"],
 "argentina":["XBUE"],"saudiarabia":["XSAU"],"unitedarabemirates":["XDFM"]
}
CALENDARS = {
 "australia":"ASX","canada":"TSX","uk":"LSE","germany":"XETR",
 "france":"EUREX","japan":"JPX","hongkong":"HKEX","india":"NSE",
 "switzerland":"SIX","netherlands":"EUREX","italy":"MIL",
 "spain":"BME","sweden":"SSE","singapore":"SGX",
 "brazil":"BMF","newzealand":"NZX","norway":"OSE","denmark":"CSE",
 "finland":"HEL","belgium":"EUREX","poland":"WSE",
 "austria":"XWBO","korea":"XKRX","taiwan":"XTAI",
 "mexico":"BMV","thailand":"SET","indonesia":"IDX",
 "malaysia":"XKLS","philippines":"PSE","southafrica":"JSE",
}
# Reject US-origin secondary local listings by checking is_primary and
# exchange/provider country; original company domicile alone is not enough.
MAX_ROWS_PER_MARKET = 15000
PAGE_SIZE = 1000
MIN_USD_VOLUME = 1_000_000
BROKER_MAX_AGE_DAYS = 90
RETRIES = 3
FX_CACHE = {}
FX_LOCK = Lock()

def previous_completed_session(market, cutoff):
    """Return an expected close DATE; None means unverified calendar."""
    candidates=[CALENDARS[market]] if market in CALENDARS else []
    candidates+=CALENDAR_ALIASES.get(market,[])
    registered=set(mcal.get_calendar_names())
    name=next((c for c in candidates if c in registered),None)
    if not name:
        return None, "no verified exchange calendar in installed registry"
    try:
        cal = mcal.get_calendar(name)
        schedule = cal.schedule(start_date=(cutoff-timedelta(days=15)).date(),
                                end_date=cutoff.date())
        if schedule.empty:
            return None, "calendar returned no sessions"
        close_times = schedule["market_close"]
        elapsed = close_times[close_times <= pd.Timestamp(cutoff.astimezone(timezone.utc) - timedelta(minutes=30))]
        if elapsed.empty:
            return None, "no completed close before cutoff"
        return elapsed.index[-1].date().isoformat(), None
    except Exception as exc:
        return None, "calendar unavailable: " + str(exc)[:120]

def eligible_brokers(ticker, asof):
    path = ROOT / "data" / "broker_verified.csv"
    if not path.exists():
        return []
    approved=[]
    with path.open(newline="",encoding="utf-8") as fp:
        for record in csv.DictReader(fp):
            if record.get("symbol","").strip().upper()!=ticker.upper():
                continue
            if record.get("outright_buy_confirmed","").strip().lower() not in ("yes","true","1"):
                continue
            if not record.get("evidence_url","").strip().startswith("https://"):
                continue
            if record.get("broker","").strip().lower() not in ("westpac","etoro"):
                continue
            try:
                checked=datetime.fromisoformat(record["verified_date"]).date()
                if (asof.date()-checked).days not in range(0,BROKER_MAX_AGE_DAYS+1):
                    continue
            except (KeyError,ValueError):
                continue
            approved.append(record["broker"].strip())
    return sorted(set(approved))

def get_usd_rate(currency):
    currency=(currency or "").upper().strip()
    if currency=="USD":return 1.
    if not re.fullmatch("[A-Z]{3}",currency):return None
    with FX_LOCK:
        if currency in FX_CACHE:return FX_CACHE[currency]
        # Serialize FX calls to avoid multiplying rate limits.
        rate=None
        for symbol,invert in ((currency+"USD=X",False),("USD"+currency+"=X",True)):
            try:
                data=yf.Ticker(symbol).history(period="5d",interval="1d",timeout=10)
                if not data.empty:
                    x=float(data["Close"].iloc[-1])
                    if math.isfinite(x) and x>0:
                        rate=1/x if invert else x
                        break
            except Exception:
                pass
        FX_CACHE[currency]=rate
        return rate

def valid_usd_turnover(hist,currency):
    """Mean price*volume over 30 sessions, spot FX; return None if unknown."""
    subset=hist.dropna(subset=["Close","Volume"]).tail(30)
    if len(subset)<30:return None
    rate=get_usd_rate(currency)
    if rate is None:return None
    val=float((subset["Close"]*subset["Volume"]).mean())*rate
    return round(val,2) if math.isfinite(val) else None

def get_bars(symbol, expected_date):
    errors=[]
    for attempt in range(RETRIES):
        try:
            df=yf.Ticker(symbol).history(period="2y",interval="1d",auto_adjust=False,timeout=18)
            if df.empty:
                errors.append("empty-history")
            else:
                df=df[df.index.date <= datetime.fromisoformat(expected_date).date()]
                if df.empty:
                    errors.append("no-data-before-cutoff")
                else:
                    seen=df.index[-1].date().isoformat()
                    if seen == expected_date:
                        return df, None
                    errors.append("stale-session:"+seen+" expected:"+expected_date)
        except Exception as exc:
            errors.append(type(exc).__name__+":"+str(exc)[:80])
        if attempt+1<RETRIES:time.sleep((attempt+1)*1.5)
    return None, ";".join(errors)

def scan_ticker(item, expected_date, asof):
    ticker,meta=item
    df,error=get_bars(ticker,expected_date)
    if error:
        return {"status":"missing","symbol":ticker,"market":meta["market"],"reason":error}
    try:
        t=evaluate_prices(df)
        daily_rate=meta.get("Recommend.All")
        # Strong Buy is sourced from a LIVE snapshot, not a historical rating.
        if not is_tv_strong_buy(daily_rate):return {"status":"invalid-rating","symbol":ticker}
        currency=meta.get("currency","")
        turnover=valid_usd_turnover(df,currency) if t["technical_pass"] else None
        brokers=eligible_brokers(str(meta.get("ticker","")),asof)
        # Alias based on Yahoo's symbol is also allowed, but must match
        # one exact explicit broker-approved listing, never a fuzzy match.
        brokers=sorted(set(brokers+eligible_brokers(ticker,asof)))
        is_liquid=turnover is not None and turnover>=MIN_USD_VOLUME
        result={
            "status":"ok","symbol":ticker,"tv_ticker":meta.get("ticker"),
            "company":meta.get("description"),"market":meta["market"],
            "sector":meta.get("sector"),"instrument_type":meta.get("_kind"),
            "currency":currency,"market_cap_usd_estimate":meta.get("market_cap_basic"),
            "etf_aum_usd_estimate":meta.get("fund_total_assets"),
            "tradingview_daily_rating":round(float(daily_rate),4),
            "avg_daily_usd_traded":turnover,"liquidity_pass":is_liquid,
            "broker_verified":brokers,**t,
            "verified_opportunity":bool(t["technical_pass"] and is_liquid and brokers),
        }
        return result
    except Exception as exc:
        return {"status":"missing","symbol":ticker,"market":meta["market"],
                "reason":"calculation:"+str(exc)[:150]}

def query_market(market,kind):
    """Discover primary securities, fail rather than silently drop pages."""
    rows=[];error=None;total=0
    for offset in range(0,MAX_ROWS_PER_MARKET,PAGE_SIZE):
        try:
            fields=["name","description","type","country","exchange","is_primary",
                    "close","currency","Recommend.All","sector","average_volume_30d_calc","subtype"]
            query=(Query().set_markets(PROVIDER_MARKETS.get(market,market)).set_property("price_conversion",{"to_currency":"usd"}))
            if kind=="stock":
                fields.append("market_cap_basic")
                query=query.where(Column("type")=="stock",Column("is_primary")==True,
                                  Column("market_cap_basic")>=1_000_000_000,
                                  Column("Recommend.All")>0.5)
            else:
                fields.append("fund_total_assets")
                query=query.where(Column("type")=="fund",Column("subtype")=="etf",Column("is_primary")==True,
                                  Column("fund_total_assets")>=100_000_000,
                                  Column("Recommend.All")>0.5)
            query=query.select(*fields).offset(offset).limit(offset+PAGE_SIZE)
            count,frame=query.get_scanner_data()
            total=int(count)
            rows.extend(frame.to_dict("records"))
            if len(frame)<PAGE_SIZE or len(rows)>=total:break
            time.sleep(.15)
        except Exception as exc:
            error=f"page {offset}: {str(exc)[:180]}"
            break
    if len(rows)<total and error is None:error="pagination truncated"
    return rows,{"market":market,"kind":kind,"total":total,"retrieved":len(rows),"error":error,
                 "complete":error is None and len(rows)>=total}

def run(args):
    asof=datetime.fromisoformat(args.asof_perth) if args.asof_perth else datetime.now(ZoneInfo("Australia/Perth"))
    if asof.tzinfo is None:raise ValueError("as-of must be timezone aware")
    asof=asof.astimezone(ZoneInfo("Australia/Perth")).replace(hour=6,minute=0,second=0,microsecond=0)
    markets=[m for i,m in enumerate(MARKETS) if i%args.shards==args.shard_number]
    selected={};discovery=[];calendar_errors=[]
    for market in markets:
        session,cal_error=previous_completed_session(market,asof)
        if cal_error:
            calendar_errors.append({"market":market,"reason":cal_error})
        for kind in ("stock","etf"):
            rows,state=query_market(market,kind)
            discovery.append(state)
            if cal_error:continue
            for row in rows:
                if row.get("is_primary") is not True:continue
                if kind=="etf" and str(row.get("subtype","")).lower()!="etf":continue
                if str(row.get("country","")).strip().lower() in ("united states","usa"):continue
                if not is_tv_strong_buy(row.get("Recommend.All")):continue
                symbol=ticker_map(row,market)
                if not symbol:continue
                row["_kind"]=kind;row["market"]=market;row["_session_expected"]=session
                # Stocks/ETFs are different instruments; retain first unique exact listing.
                selected.setdefault(symbol,row)
        print("DISCOVERED",market,len(selected),flush=True)
    results=[];missing=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        tasks={pool.submit(scan_ticker,(symbol,meta),meta["_session_expected"],asof):symbol
               for symbol,meta in selected.items()}
        for future in concurrent.futures.as_completed(tasks):
            value=future.result()
            if value["status"]=="ok":results.append(value)
            else:missing.append(value)
    technical=[x for x in results if x["technical_pass"]]
    liquidity_qualified=[x for x in technical if x["liquidity_pass"]]
    opportunities=[x for x in liquidity_qualified if x["verified_opportunity"]]
    report={
        "asof_perth":asof.isoformat(),"shard":args.shard_number,"shards":args.shards,
        "discovery":discovery,"calendar_errors":calendar_errors,
        "prequalified_mapped_count":len(selected),"price_histories_valid":len(results),
        "price_histories_failed":len(missing),"technical_signals":technical,
        "liquidity_pass_signals":liquidity_qualified,
        "verified_opportunities":opportunities,"failures":missing,
        "limitations":[
         "TradingView Strong Buy rating and market cap/AUM are current, not point-in-time historical.",
         "TradingView fund classification and fund_total_assets may not cover all exchange-traded ETFs; incomplete endpoints logged.",
         "No candidates without a valid FX rate, adequate dollar volume or exact broker verification are called opportunities.",
         "Yahoo history attempts are retried, but independently sourced fallback OHLCV is unavailable; stale candles never count as current.",
         "Calendar mappings are verified only where exchange calendar implementation is available.",
         "Source markets outside the configured list remain uncovered."
        ]}
    out=ROOT/"reports";out.mkdir(exist_ok=True)
    (out/f"screen_shard_{args.shard_number}.json").write_text(json.dumps(report,indent=2,default=str))
    print("SHARD_RESULT",json.dumps({
      "shard":args.shard_number,"markets":len(markets),
      "discovery_complete":sum(x["complete"] for x in discovery),
      "discovery_attempts":len(discovery),"calendars_missing":len(calendar_errors),
      "mapped":len(selected),"analysed":len(results),"failed":len(missing),
      "technical":len(technical),"liquid":len(liquidity_qualified),
      "broker_verified":len(opportunities)},default=str),flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--shards",type=int,default=8)
    p.add_argument("--shard-number",type=int,required=True)
    p.add_argument("--asof-perth")
    a=p.parse_args()
    if a.shards<1 or not 0<=a.shard_number<a.shards:raise ValueError("invalid shards")
    run(a)
if __name__=="__main__":main()
