"""Merge all GitHub shard artifacts into one US-style morning report."""
import json
from pathlib import Path
ROOT=Path("reports")
ROOT.mkdir(exist_ok=True)
paths=list(Path("shard_downloads").rglob("screen_shard_*.json"))
reports=sorted([json.loads(p.read_text()) for p in paths],key=lambda x:x.get("shard",-1))
found={r.get("shard") for r in reports}
seen=set()
def distinct(field):
    out=[]
    for rep in reports:
        for item in rep.get(field,[]):
            key=(item["tv_ticker"],item["session"])
            if key not in seen:
                seen.add(key);out.append(item)
    return out
# Avoid suppressing an item merely because it occurs in a different report section.
technical=distinct("technical_signals")
seen.clear()
liquid=distinct("liquidity_pass_signals")
seen.clear()
verified=distinct("verified_opportunities")
discovery=[x for r in reports for x in r.get("discovery",[])]
calerr=[x for r in reports for x in r.get("calendar_errors",[])]
mapped=sum(r.get("prequalified_mapped_count",0) for r in reports)
valid=sum(r.get("price_histories_valid",0) for r in reports)
failed=sum(r.get("price_histories_failed",0) for r in reports)
coverage=round(valid*100/mapped,1) if mapped else 0
summary={"asof_perth":reports[0].get("asof_perth") if reports else None,
         "shards_completed":len(found),"shards_expected":8,
         "market_instrument_queries":len(discovery),
         "queries_complete":sum(x.get("complete",False) for x in discovery),
         "queries_failed":sum(not x.get("complete",False) for x in discovery),
         "calendar_errors":calerr,"prequalified":mapped,"histories_valid":valid,
         "histories_failed":failed,"history_coverage_pct":coverage,
         "technical_signals":technical,"liquidity_pass_signals":liquid,
         "verified_opportunities":verified}
summary["coverage_warning"]=bool(len(found)!=8 or coverage<95 or summary["queries_failed"] or calerr)
(ROOT/"latest.json").write_text(json.dumps(summary,indent=2,default=str))
# Format matches the US screener: ticker, company, and the confirmed checks.
# Do not promote technical matches to investment opportunities without broker proof.
def fmt(value,decimals=2):
    if value is None:return "Not verified"
    try:return ("{:,.%df}"%decimals).format(float(value))
    except (ValueError,TypeError):return "Not verified"

def compact_row(x,category):
    close=fmt(x.get("close"))
    currency=x.get("currency") or "?"
    rsi=fmt(x.get("rsi14"))
    sma=x.get("sma150")
    pct=fmt(100*(x["close"]/sma-1))+"%" if sma and x.get("close") is not None else "Not verified"
    tv=fmt(x.get("tradingview_daily_rating"),3)
    turnover=fmt(x.get("avg_daily_usd_traded"),0)
    brokers=", ".join(x.get("broker_verified") or []) or "Not verified"
    scope=x.get("market") or "?"
    base=f"| **{x.get('tv_ticker') or x.get('symbol')}** | {x.get('company') or 'Unknown'} | {scope} | ✓ | Strong Buy ({tv}) | {rsi} | +{pct} | {turnover} | {brokers} |"
    if category=="verified":return base+" Eligible |"
    reasons=[]
    if not x.get("liquidity_pass"):reasons.append("USD liquidity not passed")
    if not x.get("broker_verified"):reasons.append("Broker unverified")
    return base+" Excluded: "+"; ".join(reasons)+" |"

header="| Ticker | Company | Market | Supertrend flip | TradingView | RSI 14 | Above SMA150 | 30d USD traded/day | Broker | Status |"
divider="|---|---|---|---|---|---:|---:|---:|---|---|"
lines=[
 "# International stock screener — "+str(summary["asof_perth"]),
 "**Verified opportunities: "+str(len(verified))+"**",
 "## Qualified tickers for chart review",
 header,divider,
]
if verified:
    lines.extend(compact_row(x,"verified") for x in sorted(verified,key=lambda z:z["tv_ticker"]))
else:
    lines.append("| — | No fully verified opportunities | — | — | — | — | — | — | — | — |")
lines.extend([
 "## Technical signals excluded from purchase shortlist",
 "These pass Supertrend (10,3), TradingView daily Strong Buy, RSI >=50, and close > SMA150; their other requirements remain unverified or failed.",
 header,divider,
])
if technical:
    lines.extend(compact_row(x,"excluded") for x in sorted(technical,key=lambda z:z["tv_ticker"]))
else:
    lines.append("| — | No technical signals | — | — | — | — | — | — | — | — |")
lines.extend([
 "## Scan checks",
 f"- **Data integrity:** {valid}/{mapped} historical price sets analysed ({coverage}%), {failed} failed.",
 f"- **Market discovery:** {summary['queries_complete']}/{len(discovery)} market/instrument queries complete.",
 f"- **Exchange calendars:** {len(calerr)} unsupported/error cases.",
 f"- **Technical signals:** {len(technical)}; liquidity-qualified: {len(liquid)}; broker-verified: {len(verified)}.",
 f"- **Coverage warning:** {'YES — incomplete' if summary['coverage_warning'] else 'NO for the provider-returned universe'}",
 "- **No market-wide coverage claim:** data coverage percentage is only for mapped prequalified candidates; missing endpoints and unsupported calendar markets are excluded.",
 "- The available broker approval list is empty unless separately populated with verified, exact outright-purchase evidence. Unverified signals are not investment opportunities.",
 "- TradingView Strong Buy scores, market capitalisation and ETF AUM are live screener data, not historical point-in-time values. ETF discovery remains provider-dependent.",
])
(ROOT/"latest.md").write_text("\n\n".join(lines)+"\n",encoding="utf-8")
print("CONSOLIDATED_RESULT",json.dumps({k:v for k,v in summary.items() if k not in ("technical_signals","liquidity_pass_signals","verified_opportunities","calendar_errors")},default=str),flush=True)
