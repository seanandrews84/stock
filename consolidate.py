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
lines=["# International Screener — "+str(summary["asof_perth"]),
       "**Verified opportunities: "+str(len(verified))+"**",
       "## Ticker / company / confirmed filters"]
for x in sorted(verified,key=lambda z:z["tv_ticker"]):
    above=round(100*(x["close"]/x["sma150"]-1),2)
    lines.append(f"- **{x['tv_ticker']} — {x.get('company')}** ({x['market']}); {x['session']}; close {x['close']} {x['currency']}; Supertrend flip ✓; TradingView Strong Buy {x['tradingview_daily_rating']} ✓; RSI {x['rsi14']} ✓; SMA150 +{above}% ✓; turnover USD {x['avg_daily_usd_traded']:,.0f} ✓; outright broker {','.join(x['broker_verified'])} ✓")
if not verified:lines.append("**None passed every verified requirement.**")
lines.append("## Excluded technical signals (not purchase opportunities)")
for x in sorted(technical,key=lambda z:z["tv_ticker"]):
    reasons=[]
    if not x.get("liquidity_pass"):reasons.append("USD volume below threshold or unverified")
    if not x.get("broker_verified"):reasons.append("exact broker outright availability unverified")
    lines.append(f"- {x['tv_ticker']} — {x.get('company')} ({x['market']}), RSI {x['rsi14']}; excluded: {', '.join(reasons)}")
if not technical:lines.append("None found.")
lines.extend(["## Coverage",
              f"- Market/instrument queries: {summary['queries_complete']}/{len(discovery)} complete",
              f"- Daily price histories: {valid}/{mapped} ({coverage}%)",
              f"- Failed/stale histories: {failed}; unsupported calendars: {len(calerr)}",
              f"- Technical-only signals: {len(technical)}; volume-qualified: {len(liquid)}",
              f"- **Coverage warning: {'YES' if summary['coverage_warning'] else 'NO'}**",
              "- Important: TradingView ratings and size estimates are live snapshots, not historically archived as-of values.",
              "- ETF coverage depends on fund data exposed by provider; unavailable ETFs are not assumed scanned."])
(ROOT/"latest.md").write_text("\n\n".join(lines)+"\n")
print("CONSOLIDATED_RESULT",json.dumps({k:v for k,v in summary.items() if k not in ("technical_signals","liquidity_pass_signals","verified_opportunities","calendar_errors")},default=str),flush=True)
