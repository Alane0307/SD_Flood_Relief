#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# --- 兼容：wb 可为路径或 dict(sheet_name->DataFrame)
def _read_sheet(wb, sheet_name):
    if isinstance(wb, dict):
        if sheet_name not in wb:
            raise KeyError(f"sheet '{sheet_name}' not in workbook dict")
        return wb[sheet_name].copy()
    return pd.read_excel(wb, sheet_name=sheet_name)

def _ensure_outdir(outdir):
    os.makedirs(outdir, exist_ok=True)

def _daily(series_df, sid):
    g = series_df[series_df["ts_id"] == sid].copy()
    if g.empty:
        return pd.Series(dtype=float)
    g["date"] = pd.to_datetime(g["date"]).dt.normalize()
    return g.groupby("date")["value"].sum().sort_index()

def _year_slice(s: pd.Series, year: int):
    if s.empty: return s
    idx = s.index
    return s[(idx.year == year)]

# ------------------------- 图 1：Hazard 轨迹 -------------------------
def plot_hazard_trajectory(wb, outdir, year=None):
    _ensure_outdir(outdir)
    # 优先 HAZARD_SERIES；没有就用 BREACH_SPREAD/ BREACH 构造
    try:
        hz = _read_sheet(wb, "HAZARD_SERIES")
        need = {"date","hazard_rate_est"}
        if not need.issubset(hz.columns):
            raise KeyError("HAZARD_SERIES missing columns")
        hz = hz.copy()
        hz["date"] = pd.to_datetime(hz["date"]).dt.normalize()
        ser = pd.Series(hz["hazard_rate_est"].values, index=hz["date"])
    except Exception:
        sed = _read_sheet(wb, "SERIES_EXTRACTED_SPLIT")
        need = {"ts_id","date","value"}
        if not need.issubset(sed.columns):
            print("[WARN] SERIES_EXTRACTED_SPLIT 缺列，跳过 hazard_trajectory")
            return
        ser = _daily(sed, "BREACH_SPREAD")
        if ser.empty:
            ser = _daily(sed, "BREACH")
        if ser.empty:
            print("[WARN] 无 BREACH/BREACH_SPREAD 可用于 hazard_trajectory")
            return

    if year is not None:
        ser = _year_slice(ser, year)
        if ser.empty:
            print(f"[WARN] hazard series empty for year={year}")
            return

    plt.figure(figsize=(10,4.5))
    plt.plot(ser.index, ser.values, label="hazard")
    ttl = "Estimated Hazard Trajectory" + (f" ({year})" if year is not None else "")
    plt.title(ttl); plt.xlabel("Date"); plt.ylabel("Hazard")
    plt.legend(); plt.tight_layout()
    f = "hazard_trajectory" + (f"_{year}" if year is not None else "") + ".png"
    fpath = os.path.join(outdir, f)
    plt.savefig(fpath, dpi=160); plt.close()
    print(f"[OK] saved: {fpath}")

# ------------------------- 图 2：Ship-Arrive 配对 -------------------------
def plot_ship_arrive_pair(wb, outdir, series_sheet="SERIES_EXTRACTED_SPLIT", link="ZP", max_lag=30, year=None):
    _ensure_outdir(outdir)
    try:
        df = _read_sheet(wb, series_sheet)
    except Exception as e:
        print(f"[WARN] 无法读取 {series_sheet}: {e}")
        return
    need = {"ts_id","date","value"}
    if not need.issubset(df.columns):
        print(f"[WARN] {series_sheet} 缺列 {need - set(df.columns)}")
        return

    sid = f"LINK_{link}_SHIP"
    aid = f"LINK_{link}_ARR"
    g = df[df["ts_id"].isin([sid, aid])].copy()
    if g.empty:
        print(f"[WARN] No ship/arr series found for link={link}")
        return

    g["date"] = pd.to_datetime(g["date"]).dt.normalize()
    ship = g[g["ts_id"]==sid].groupby("date")["value"].sum().sort_index()
    arr  = g[g["ts_id"]==aid].groupby("date")["value"].sum().sort_index()

    if year is not None:
        ship = _year_slice(ship, year)
        arr  = _year_slice(arr, year)

    if ship.empty or arr.empty:
        print(f"[WARN] No ship/arr for link={link}" + (f" in {year}" if year else ""))
        return

    idx = ship.index.union(arr.index)
    s = ship.reindex(idx).fillna(0.0)
    a = arr.reindex(idx).fillna(0.0)

    def xcorr_best_lag(sv, av, max_lag=30):
        best_lag, best_cc = 0, -1e9
        max_lag = min(max_lag, max(0, len(sv)-1))
        for L in range(0, max_lag+1):
            s_shift = np.r_[np.zeros(L), sv[:-L]] if L>0 else sv
            if np.std(s_shift) < 1e-12 or np.std(av) < 1e-12:
                cc = -1e-9
            else:
                cc = np.corrcoef(s_shift, av)[0,1]
            if cc > best_cc:
                best_cc, best_lag = cc, L
        return best_lag, best_cc

    lag, cc = xcorr_best_lag(s.values, a.values, max_lag=max_lag)
    lag = int(max(0, min(lag, max(0, len(s)-1))))
    s_shift = s.shift(lag, fill_value=0.0)

    plt.figure(figsize=(9,4.5))
    plt.plot(s.index, s, label=sid)
    plt.plot(a.index, a, label=aid)
    plt.plot(s_shift.index, s_shift, linestyle="--", label=f"{sid} (shift {lag}d)")
    ttl = f"Ship vs Arrive ({link})" + (f" - {year}" if year is not None else "")
    plt.title(f"{ttl}  | best_lag={lag}, cc~{cc:.3f}")
    plt.xlabel("Date"); plt.ylabel("Value"); plt.legend(); plt.tight_layout()
    f = f"ship_arrive_{link}" + (f"_{year}" if year is not None else "") + ".png"
    fpath = os.path.join(outdir, f)
    plt.savefig(fpath, dpi=160); plt.close()
    print(f"[OK] saved: {fpath}")

# ------------------------- 图 3：Top 覆盖 -------------------------
def plot_coverage_top(wb, outdir, series_sheet="SERIES_EXTRACTED_SPLIT", topn=12, year=None):
    _ensure_outdir(outdir)
    try:
        df = _read_sheet(wb, series_sheet)
    except Exception as e:
        print(f"[WARN] 无法读取 {series_sheet}: {e}")
        return

    need = {"ts_id","date","value"}
    if not need.issubset(df.columns):
        print(f"[WARN] {series_sheet} 缺列 {need - set(df.columns)}")
        return

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    if year is not None:
        df = df[df["date"].dt.year == year]

    if df.empty:
        print(f"[WARN] no data for coverage_top" + (f" in {year}" if year else ""))
        return

    s = df.groupby("ts_id")["value"].sum().sort_values(ascending=False)
    if s.empty:
        return

    if "BREACH_SPREAD" in s.index and "BREACH" in s.index:
        s.loc["BREACH_SPREAD"] += s.loc["BREACH"]
        s = s.drop(index="BREACH")

    s_top = s.head(topn)
    plt.figure(figsize=(10,5))
    s_top.plot(kind="bar")
    ttl = f"Top-{topn} Evidence Coverage"
    plt.title(ttl + (f" ({year})" if year is not None else ""))
    plt.ylabel("Sum of values"); plt.tight_layout()
    f = "coverage_top" + (f"_{year}" if year is not None else "") + ".png"
    fpath = os.path.join(outdir, f)
    plt.savefig(fpath, dpi=160); plt.close()
    print(f"[OK] saved: {fpath}")

# ------------------------- 主流程 -------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wb", required=True, help="工作簿路径")
    ap.add_argument("--outdir", default="figs", help="输出目录")
    ap.add_argument("--series-sheet", default="SERIES_EXTRACTED_SPLIT", help="明细表名")
    ap.add_argument("--years", default="", help="逗号分隔的年份列表，如 1931,1954；留空则只画合并图")
    args = ap.parse_args()

    try:
        wb = pd.read_excel(args.wb, sheet_name=None)
    except Exception:
        wb = args.wb

    # 合并图
    plot_hazard_trajectory(wb, args.outdir, year=None)
    for link in ["ZP","PC","CV"]:
        plot_ship_arrive_pair(wb, args.outdir, series_sheet=args.series_sheet, link=link, year=None)
    plot_coverage_top(wb, args.outdir, series_sheet=args.series_sheet, year=None)

    # 分年图
    years = []
    if args.years.strip():
        for tok in args.years.split(","):
            tok = tok.strip()
            if tok.isdigit():
                years.append(int(tok))
    for y in years:
        plot_hazard_trajectory(wb, args.outdir, year=y)
        for link in ["ZP","PC","CV"]:
            plot_ship_arrive_pair(wb, args.outdir, series_sheet=args.series_sheet, link=link, year=y)
        plot_coverage_top(wb, args.outdir, series_sheet=args.series_sheet, year=y)

if __name__ == "__main__":
    main()
