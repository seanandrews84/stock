import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
from pipeline import eligible_brokers, valid_usd_turnover, previous_completed_session, get_bars
from full_scan import is_tv_strong_buy

def test_strong_buy_strict():
    assert is_tv_strong_buy(0.6)
    assert not is_tv_strong_buy(0.5)
    assert not is_tv_strong_buy(float("nan"))
    assert not is_tv_strong_buy(None)

def test_no_verified_brokers_fail_closed():
    assert eligible_brokers("UNKNOWN.EX",datetime(2026,11,24,tzinfo=ZoneInfo("Australia/Perth")))==[]

def test_liquidity_missing_fx_fails_closed(monkeypatch):
    import pipeline
    monkeypatch.setattr(pipeline,"get_usd_rate",lambda currency:None)
    df=pd.DataFrame({"Close":[100.]*30,"Volume":[15000.]*30})
    assert valid_usd_turnover(df,"XYZ") is None

def test_liquidity_threshold_with_usd():
    df=pd.DataFrame({"Close":[100.]*30,"Volume":[12000.]*30})
    assert valid_usd_turnover(df,"USD")==1200000.

def test_calendar_weekend_uses_previous_session():
    # 06:00 Perth Saturday 21 Nov: ASX Friday session complete.
    cutoff=datetime(2026,11,21,6,0,tzinfo=ZoneInfo("Australia/Perth"))
    date,error=previous_completed_session("australia",cutoff)
    assert error is None
    assert date=="2026-11-20"

def test_unsupported_calendar_fails_closed():
    date,error=previous_completed_session("nonexistent-market",datetime(2026,11,24,tzinfo=ZoneInfo("Australia/Perth")))
    assert date is None and error

def test_stale_data_never_passes(monkeypatch):
    import pipeline
    class Ticker:
        def history(self,**kwargs):
            return pd.DataFrame({"Close":[10.],"Volume":[100.]},index=pd.to_datetime(["2026-11-20"]))
    monkeypatch.setattr(pipeline.yf,"Ticker",lambda sym:Ticker())
    monkeypatch.setattr(pipeline.time,"sleep",lambda duration:None)
    result,error=get_bars("TEST.X","2026-11-23")
    assert result is None and "stale-session" in error

def test_provider_market_aliases():
    from pipeline import PROVIDER_MARKETS
    assert PROVIDER_MARKETS["southafrica"]=="rsa"
    assert PROVIDER_MARKETS["saudiarabia"]=="ksa"
    assert PROVIDER_MARKETS["unitedarabemirates"]=="uae"

def test_calendar_registry_graceful_fallback():
    import pipeline
    # Registry-derived calendars don't silently invent sessions.
    assert "newzealand" in pipeline.CALENDAR_ALIASES
    assert "mexico" in pipeline.CALENDAR_ALIASES

def test_broker_requires_specific_proof(tmp_path,monkeypatch):
    import pipeline
    (tmp_path/"data").mkdir()
    (tmp_path/"data"/"broker_verified.csv").write_text(
        "symbol,broker,verified_date,evidence_url,outright_buy_confirmed\n"
        "ABC.X,etoro,2026-11-24,https://www.etoro.com/markets/abc.x,no\n")
    monkeypatch.setattr(pipeline,"ROOT",tmp_path)
    now=datetime(2026,11,24,tzinfo=ZoneInfo("Australia/Perth"))
    assert pipeline.eligible_brokers("ABC.X",now)==[]
