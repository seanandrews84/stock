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
coverage_by_type={}
for kind in ("stock","etf"):
    mapped_kind=sum(r.get("instrument_coverage",{}).get(kind,{}).get("mapped",0) for r in reports)
    valid_kind=sum(r.get("instrument_coverage",{}).get(kind,{}).get("valid",0) for r in reports)
    coverage_by_type[kind]={"mapped":mapped_kind,"analysed":valid_kind,
                            "coverage_pct":round(100*valid_kind/mapped_kind,1) if mapped_kind else None}
summary["coverage_by_type"]=coverage_by_type
summary["etf_markets_capped"]=[d["market"] for d in discovery if d.get("kind")=="etf" and d.get("error")=="CAPPED_ETF_DISCOVERY"]
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
 "# International screener — "+str(summary["asof_perth"]),
 "## Technical candidates for manual chart review",
 "Passed fresh Supertrend (10,3), TradingView daily Strong Buy, RSI >=50, SMA150 and USD$1m average daily traded value.",
 "**Broker availability is NOT confirmed for these candidates. This is a technical watchlist, not a list of verified purchase opportunities.**",
 header,divider,
]
if liquid:
    lines.extend(compact_row(x,"excluded") for x in sorted(liquid,key=lambda z:z["tv_ticker"]))
else:
    lines.append("| — | No liquidity-qualified technical candidates | — | — | — | — | — | — | — | — |")
lines += [
 "## Fully verified outright-purchase opportunities",
 f"**{len(verified)}** securities confirmed through exact Westpac/eToro Australia evidence.",
]
if verified:
    lines.extend([header,divider])
    lines.extend(compact_row(x,"verified") for x in sorted(verified,key=lambda z:z["tv_ticker"]))
lines += [
 "## Excluded technical signals",
 "Passed the technical filters, but failed or could not verify USD trading liquidity.",
 header,divider,
]
nonliquid=[x for x in technical if not x.get("liquidity_pass")]
if nonliquid:
    lines.extend(compact_row(x,"excluded") for x in sorted(nonliquid,key=lambda z:z["tv_ticker"]))
else:
    lines.append("| — | None | — | — | — | — | — | — | — | — |")
lines += [
 "## Scan integrity",
 f"- **Stock price coverage:** {coverage_by_type['stock']['analysed']}/{coverage_by_type['stock']['mapped']} ({coverage_by_type['stock']['coverage_pct']}%).",
 f"- **ETF price coverage:** {coverage_by_type['etf']['analysed']}/{coverage_by_type['etf']['mapped']} ({coverage_by_type['etf']['coverage_pct']}%).",
 f"- **Combined candidate coverage:** {valid}/{mapped} ({coverage}%).",
 f"- **Market/instrument discovery:** {summary['queries_complete']}/{len(discovery)} complete. ETF AUM cap of 80 per market reached in {len(summary['etf_markets_capped'])} markets.",
 f"- **Exchange calendar uncertainties:** {len(calerr)} markets.",
 f"- **Signals:** {len(technical)} technical, {len(liquid)} above USD$1m turnover, {len(verified)} broker-verified.",
 f"- **Coverage warning:** {'YES — incomplete' if summary['coverage_warning'] else 'NO for this provider-filtered universe'}",
 "- History failures include new listings with insufficient 150-day data and unmatched Yahoo/exchange symbols, not just network errors.",
 "- Broker approvals must be supported by exact listing and underlying-asset order evidence, not merely a quote page.",
 "- TradingView ratings, AUM and market caps are live data, not archived as-of 6:00 am; exchange-local session closes are enforced for daily-price calculations.",
 "- ETF discovery is AUM-ranked and capped in some markets: this is NOT an exhaustive global ETF scan."
]
(ROOT/"latest.md").write_text("\n\n".join(lines)+"\n",encoding="utf-8")
print("CONSOLIDATED_RESULT",json.dumps({k:v for k,v in summary.items() if k not in ("technical_signals","liquidity_pass_signals","verified_opportunities","calendar_errors")},default=str),flush=True)
