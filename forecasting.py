"""Local linear trend forecasts with chronological validation and prediction intervals."""
import warnings
import numpy as np
import pandas as pd
from scipy.sparse import SparseEfficiencyWarning
from statsmodels.tsa.statespace.structural import UnobservedComponents

FREQUENCIES = {"day": "D", "week": "W-MON", "month": "MS"}


def regular_series(rows, grain, missing="error"):
    if grain not in FREQUENCIES or missing not in {"error", "zero"}:
        raise ValueError("Geçersiz zaman kırılımı veya eksik dönem politikası.")
    frame = pd.DataFrame(rows)
    if frame.empty or not {"period", "value"} <= set(frame):
        raise ValueError("Zaman serisi period ve value alanlarını içermeli.")
    dates = pd.to_datetime(frame["period"], errors="coerce", utc=True).dt.tz_convert(None)
    values = pd.to_numeric(frame["value"], errors="coerce")
    if dates.isna().any() or not np.isfinite(values.to_numpy(dtype=float)).all():
        raise ValueError("Seride geçersiz tarih veya sayısal değer var.")
    periods = dates.dt.to_period({"day": "D", "week": "W-SUN", "month": "M"}[grain]).dt.start_time
    if periods.duplicated().any():
        raise ValueError("Her dönemde tek toplulaştırılmış metrik olmalı.")
    series = pd.Series(values.to_numpy(dtype=float), index=pd.DatetimeIndex(periods)).sort_index()
    index = pd.date_range(series.index.min(), series.index.max(), freq=FREQUENCIES[grain])
    if len(index) > 1000:
        raise ValueError("Zaman serisi 1000 dönemden uzun olamaz.")
    series = series.reindex(index)
    gaps = int(series.isna().sum())
    if gaps and missing == "error":
        raise ValueError("Eksik dönemler var. Kapsamı düzeltin veya adet/toplam için sıfır politikasını seçin.")
    return series.fillna(0) if missing == "zero" else series


def _fit(series):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        warnings.simplefilter("ignore", category=SparseEfficiencyWarning)
        result = UnobservedComponents(series, level="local linear trend").fit(disp=False, maxiter=300)
    if not result.mle_retvals.get("converged", True):
        raise ValueError("Zaman serisi modeli yakınsamadı; kapsamı veya dönem kırılımını değiştirin.")
    return result


def forecast_series(series, horizon=6, confidence=0.95):
    if type(horizon) is not int or not 1 <= horizon <= 60 or not 0.5 < confidence < 1:
        raise ValueError("Ufuk 1–60 dönem, güven düzeyi 0.5–1 aralığında olmalı.")
    if len(series) < 16 or series.isna().any() or not np.isfinite(series).all():
        raise ValueError("Tahmin için en az 16 eksiksiz, sonlu dönem gerekli.")
    if series.index.freq is None or not series.index.is_monotonic_increasing:
        raise ValueError("Zaman serisi düzenli ve artan tarih sırasıyla gelmeli.")
    # One forecast origin: train on the past, score the untouched final periods.
    holdout = min(max(3, horizon), max(3, len(series) // 4))
    train, actual = series.iloc[:-holdout], series.iloc[-holdout:]
    if train.nunique() < 2:
        raise ValueError("Eğitim döneminde değişkenlik yok; trend modeli uygulanamaz.")
    fitted = _fit(train)
    predicted = np.asarray(fitted.get_forecast(holdout).predicted_mean, dtype=float)
    naive = np.repeat(float(train.iloc[-1]), holdout)
    errors = actual.to_numpy() - predicted
    metrics = {"mae": float(np.mean(np.abs(errors))), "rmse": float(np.sqrt(np.mean(errors ** 2))),
               "naive_mae": float(np.mean(np.abs(actual.to_numpy() - naive))),
               "holdout_periods": holdout, "train_periods": len(train)}
    final = _fit(series).get_forecast(horizon)
    bounds = np.asarray(final.conf_int(alpha=1 - confidence), dtype=float)
    mean = np.asarray(final.predicted_mean, dtype=float)
    if not np.isfinite(mean).all() or not np.isfinite(bounds).all():
        raise ValueError("Model sonlu tahmin ve aralık üretemedi.")
    future = pd.date_range(series.index[-1], periods=horizon + 1, freq=series.index.freq)[1:]
    output = pd.DataFrame({"period": future, "forecast": mean, "lower": bounds[:, 0], "upper": bounds[:, 1]})
    validation = pd.DataFrame({"period": actual.index, "actual": actual.to_numpy(),
                               "prediction": predicted, "naive": naive})
    return {"model": "Yerel doğrusal trend (durum uzayı)", "metrics": metrics,
            "confidence": confidence, "forecast": output, "validation": validation,
            "history": series, "beats_naive": metrics["mae"] < metrics["naive_mae"]}


def forecast_report(result):
    m = result["metrics"]
    comparison = "Model basit son-değer tahmininden daha düşük hata verdi." if result["beats_naive"] else (
        "Model basit son-değer tahminini geçemedi; tahmin karar vermek için zayıf olabilir.")
    return (f"**{result['model']}**\n\n"
            f"Son {m['holdout_periods']} dönem eğitim dışında sınandı. "
            f"MAE: {m['mae']:.4g}; RMSE: {m['rmse']:.4g}; basit tahmin MAE: {m['naive_mae']:.4g}. "
            f"{comparison}\n\n%{result['confidence'] * 100:.0f} tahmin aralığı model varsayımlarına dayanır; "
            "garanti değildir. Model mevsimsellik veya dış etkenler kullanmaz. Negatif tahminler "
            "adet metriklerinde modelin uygun olmayabileceğini gösterir.")
