import pandas as pd
from screener import rsi14, supertrend, evaluate_prices

def test_rsi_rising():
    values=list(range(100,300))
    assert rsi14(values).iloc[-1]==100

def test_sma_and_dates():
    n=200
    df=pd.DataFrame({"Open":[100+i*.2 for i in range(n)],
        "High":[101+i*.2 for i in range(n)],
        "Low":[99+i*.2 for i in range(n)],
        "Close":[100+i*.2 for i in range(n)],
        "Volume":[1000]*n},index=pd.date_range("2025-01-01",periods=n,freq="B"))
    a=evaluate_prices(df)
    assert a["bars"]==n
    assert a["rsi14"]==100
    assert a["close"]>a["sma150"]
    assert isinstance(a["fresh_bullish_flip"],bool)

def test_supertrend_length():
    df=pd.DataFrame({"Open":[10]*20,"High":[11]*20,"Low":[9]*20,"Close":[10]*20,"Volume":[1000]*20})
    directions,values=supertrend(df)
    assert len(directions)==20
    assert pd.isna(values.iloc[0])

def test_tradingview_strong_buy_threshold():
    from full_scan import is_tv_strong_buy
    assert is_tv_strong_buy(0.50001)
    assert is_tv_strong_buy(0.75)
    assert is_tv_strong_buy(1.0)
    for score in (0.5,0.49,0.0,-0.5,None,float("nan"),1.01,""):
        assert not is_tv_strong_buy(score)
