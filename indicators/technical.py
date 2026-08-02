import pandas as pd
import ta


class TechnicalIndicators:
    @staticmethod
    def add_ema(df: pd.DataFrame, period: int, column: str = "close") -> pd.DataFrame:
        indicator = ta.trend.EMAIndicator(close=df[column], window=period)
        df[f"ema_{period}"] = indicator.ema_indicator()
        return df

    @staticmethod
    def add_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        adx = ta.trend.ADXIndicator(
            high=df["high"], low=df["low"], close=df["close"], window=period
        )
        df["adx"] = adx.adx()
        df["adx_pos"] = adx.adx_pos()
        df["adx_neg"] = adx.adx_neg()
        return df

    @staticmethod
    def add_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        rsi = ta.momentum.RSIIndicator(close=df["close"], window=period)
        df["rsi"] = rsi.rsi()
        return df

    @staticmethod
    def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        atr = ta.volatility.AverageTrueRange(
            high=df["high"], low=df["low"], close=df["close"], window=period
        )
        df["atr"] = atr.average_true_range()
        return df

    @staticmethod
    def add_volume_sma(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
        df[f"volume_sma_{period}"] = df["volume"].rolling(window=period).mean()
        return df

    @staticmethod
    def add_roc(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
        df[f"roc_{period}"] = df["close"].pct_change(periods=period) * 100
        return df

    @staticmethod
    def add_volume_ratio(df: pd.DataFrame, sma_period: int = 20) -> pd.DataFrame:
        sma_col = f"volume_sma_{sma_period}"
        if sma_col not in df.columns:
            df = TechnicalIndicators.add_volume_sma(df, sma_period)
        df["volume_ratio"] = df["volume"] / df[sma_col]
        return df

    @staticmethod
    def add_all_strategy_indicators(df: pd.DataFrame) -> pd.DataFrame:
        df = TechnicalIndicators.add_ema(df, 20)
        df = TechnicalIndicators.add_ema(df, 50)
        df = TechnicalIndicators.add_adx(df, 14)
        df = TechnicalIndicators.add_rsi(df, 14)
        df = TechnicalIndicators.add_atr(df, 14)
        df = TechnicalIndicators.add_volume_sma(df, 20)
        return df
