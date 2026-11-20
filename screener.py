"""Conservative, non-US stock screener pilot. This is NOT a full-market scan."""
import csv, json, time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

BASE=Path(__file__).parent
OUT=BASE/"reports"

def rsi14(close):
    c=pd.Series(close,dtype=float).reset_index(drop=True)
    delta=c.diff(); up=delta.clip(lower=0); dn=(-delta).clip(lower=0)
    out=np.full(len(c),np.nan)
    if len(c)<=14: return pd.Series(out)
    avg_u=up.iloc[1:15].mean(); avg_d=dn.iloc[1:15].mean()
    out[14]=100 if avg_d==0 else 100-100/(1+avg_u/avg_d)
    for i in range(15,len(c)):
        avg_u=(avg_u*13+up.iloc[i])/14;avg_d=(avg_d*13+dn.iloc[i])/14
        out[i]=100 if avg_d==0 else 100-100/(1+avg_u/avg_d)
    return pd.Series(out)

def supertrend(df, length=10, factor=3):
    x=df.reset_index(drop=True)
    h=x["High"].astype(float); l=x["Low"].astype(float); c=x["Close"].astype(float)
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    n=len(x); directions=np.zeros(n,dtype=int); lines=np.full(n,np.nan)
    if n<length:return pd.Series(directions),pd.Series(lines)
    atr=float(tr.iloc[:length].mean());up=lo=0.
    for i in range(length-1,n):
        if i>length-1:atr=(atr*(length-1)+float(tr.iloc[i]))/length
        mid=(h.iloc[i]+l.iloc[i])/2; raw_up=mid+factor*atr;raw_lo=mid-factor*atr
        if i==length-1:
            up=raw_up;lo=raw_lo;lines[i]=lo;directions[i]=1;continue
        next_up=raw_up if raw_up<up or c.iloc[i-1]>up else up
        next_lo=raw_lo if raw_lo>lo or c.iloc[i-1]<lo else lo
        prior_on_upper=abs(lines[i-1]-up)<1e-7*max(1,abs(up))
        directions[i]=(1 if c.iloc[i]>next_up else -1) if prior_on_upper else (-1 if c.iloc[i]<next_lo else 1)
        lines[i]=next_lo if directions[i]==1 else next_up
        up,lo=next_up,next_lo
    return pd.Series(directions),pd.Series(lines)

def evaluate_prices(df):
    df=df.dropna(subset=["Open","High","Low","Close","Volume"])
    if len(df)<175:raise ValueError("fewer than 175 complete price bars")
    c=df["Close"].astype(float).reset_index(drop=True)
    sma=float(c.tail(150).mean());rsi=float(rsi14(c).iloc[-1])
    directions,lines=supertrend(df)
    latest=df.index[-1].date().isoformat()
    return {"session":latest,"bars":len(df),"close":round(float(c.iloc[-1]),4),
        "sma150":round(sma,4),"rsi14":round(rsi,2),
        "supertrend":round(float(lines.iloc[-1]),4),
        "bullish":bool(directions.iloc[-1]==1),
        "fresh_bullish_flip":bool(directions.iloc[-2]==-1 and directions.iloc[-1]==1),
        "technical_pass":bool(directions.iloc[-2]==-1 and directions.iloc[-1]==1 and c.iloc[-1]>sma and rsi>=50)}

def load_csv(filename):
    with (BASE/"data"/filename).open(encoding="utf-8",newline="") as f:return list(csv.DictReader(f))

def run():
    OUT.mkdir(exist_ok=True)
    universe=[x for x in load_csv("universe.csv") if x["country"].strip().lower() not in ("usa","united states","united states of america")]
    successes=[];failures=[];candidates=[]
    for row in universe:
        symbol=row["symbol"]
        try:
            bars=yf.Ticker(symbol).history(period="2y",interval="1d",auto_adjust=False)
            if bars.empty:raise ValueError("empty history")
            result={"symbol":symbol,"exchange":row["exchange"],"country":row["country"],**evaluate_prices(bars)}
            successes.append(result)
            if result["technical_pass"]:candidates.append(result)
        except Exception as exc:failures.append({"symbol":symbol,"reason":str(exc)[:200]})
        time.sleep(0.25)
    report={"generated_utc":datetime.now(timezone.utc).isoformat(),
      "status":"INCOMPLETE_PILOT_NOT_FULL_MARKET",
      "universe_count":len(universe),"success_count":len(successes),"failure_count":len(failures),
      "technical_only_candidates_not_recommendations":candidates,
      "verified_purchase_recommendations":[],
      "limitations":["20-symbol pilot only; no global universe discovery",
      "No current company market cap or ETF AUM verification",
      "No USD average-dollar-volume qualification","No comprehensive SPAC detection",
      "No ticker-level Westpac/eToro Australia outright-purchase verification",
      "Latest completed session and Supertrend parity with TradingView unverified"],
      "individual_results":successes,"failures":failures}
    (OUT/"latest.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    md=["# International screener pilot",f"Generated UTC: {report['generated_utc']}",
        "**This is not a full-market scan or trading recommendation.**",
        f"Universe: {len(universe)}; evaluated: {len(successes)}; failed: {len(failures)}.",
        f"Technical-only candidates: {len(candidates)}. Broker-verified recommendations: **0**.",
        "## Technical-only candidates (not recommendations)"]
    md += [f"- {x['symbol']}: {x['session']}, RSI {x['rsi14']}, SMA150 {x['sma150']}" for x in candidates] or ["None in this limited sample."]
    md += ["## Data failures"]+[f"- {x['symbol']}: {x['reason']}" for x in failures]
    md += ["## Unverified requirements"]+[f"- {v}" for v in report["limitations"]]
    (OUT/"latest.md").write_text("\n\n".join(md)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("status","universe_count","success_count","failure_count","technical_only_candidates_not_recommendations")},indent=2))
    if not successes:raise SystemExit("No price data downloaded. Pilot unavailable; report written.")

if __name__=="__main__":run()
