#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Calibrate full parameter set from Unified_Calibration_Full_1931_1954.xlsx.

包含：
1) 日期解析：民国纪年、中文数字日期（初十/廿五/卅日）、上中下旬、并列月份、日期区间
2) 数量解析：多处数量合并、倍率词（万/千/百）、单位库扩展（斤/袋/车）
3) LINK 自动拆分：ZP/PC/CV × {SHIP, ARR}；支持地名→链路 CSV 规则；支持 P010/P020；关键词增强
4) 兜底随机：对未判明链路/方向按先验概率随机分配（固定种子，可复现）；区间端点方向分拆
5) 输出：CALIB_RESULTS / SERIES_EXTRACTED / SERIES_EXTRACTED_SPLIT / EXTRACTION_LOG / HAZARD_SERIES
"""

import os, re, math
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from scipy.optimize import minimize

# =========================
# 基本配置
# =========================
WB_NAME = "Unified_Calibration_Full_1931_1954.xlsx"

# 聚合频率
FREQ = "D"               # "D"=按日; "W"=按周
WEEK_RULE = "W-MON"      # 周度聚合规则

# hazard 平滑强度
SMOOTH_LAMBDA_HAZARD = 5.0

# 日期区间处理策略： "endpoints"（仅取两端） 或 "uniform"（在区间内按日平均摊开）
DATE_RANGE_MODE = "uniform"   # 如需只取端点改为 "endpoints"
DEFAULT_EVENT_VALUE = 1.0     # 无数量时默认事件值

# 数量解析策略
SUM_ALL_QUANTITIES = True

# 单位换算（历史口径需校准；下列为常见近似）
UNIT_TO_KG = {
    "吨": 1000.0, "t": 1000.0, "kg": 1.0, "千克": 1.0, "公斤": 1.0,
    "斤": 0.5,    # 1 斤 ~ 0.5 kg
    "石": 120.0,  # 地区口径差异大，这里占位
    "担": 50.0,
    "斗": 10.0,
    "升": 0.8,    # 粮食体积转质量粗口径
    # 容器/趟次近似（可根据资料调整）
    "袋": 50.0,
    "车": 1000.0,
}

# 倍率词
MULTIPLIER = { "万": 1e4, "千": 1e3, "百": 1e2 }

# =========================
# 地名→链路 映射（可选）
# =========================
GEO_LINK_MAP_CSV = "geo_link_map.csv"  # 与脚本同目录；列需包含 pattern,link

def load_geo_rules(path):
    """
    读取 CSV（pattern,link[,comment]），返回 [(compiled_regex, link), ...]
    pattern 使用 Python 正则；大小写不敏感。
    """
    rules = []
    if not os.path.exists(path):
        return rules
    try:
        df = pd.read_csv(path)
        need = {"pattern","link"}
        if not need.issubset(set(df.columns)):
            print(f"[WARN] {path} 缺少列 {need}，忽略。")
            return []
        for _, row in df.iterrows():
            pat = str(row["pattern"]).strip().strip('"').strip("'")
            lk  = str(row["link"]).strip().upper()
            if lk not in {"ZP","PC","CV"}:
                continue
            try:
                rx = re.compile(pat, re.IGNORECASE)
                rules.append((rx, lk))
            except re.error as e:
                print(f"[WARN] 无法编译正则: {pat} -> {e}")
        print(f"[INFO] Loaded {len(rules)} geo-link rules from {path}")
    except Exception as e:
        print(f"[WARN] 读取 {path} 失败：{e}")
    return rules

# =========================
# 兜底分类配置（保证可跑通）
# =========================
FALLBACK_ENABLE = True           # 打开/关闭兜底分配
FALLBACK_SEED = 2025             # 固定随机种子（可复现）

# ============== 终端后处理：二次兜底 & 成对合成 ==============
FALLBACK_REASSIGN_UNK = True      # 对仍为 UNK 的 LINK 记录做二次分配
SYNTHESIZE_PAIRED = True          # 若某链路缺少 ARR/SHIP，则用先验 τ 合成缺失方向
PAIR_SCALE = 1.0                  # 合成方向的缩放（1.0=同量；也可设 <1 做保守）

# 每条链路的 τ 先验（天）：ZP 省↔专区、PC 专区↔县/市、CV 县/市↔乡/村
TAU_PRIOR_PER_LINK = {"ZP": 10, "PC": 7, "CV": 3}

# 未能判定链路时的分配概率（需归一化）
FALLBACK_LINK_PROBS = {"ZP": 0.33, "PC": 0.34, "CV": 0.33}

# 未能判定方向时的分配概率（需归一化）
FALLBACK_DIR_PROBS  = {"SHIP": 0.50, "ARR": 0.50}

# 多端点（区间）时的方向策略：True=最早→SHIP，最晚→ARR
FALLBACK_SPLIT_ENDPOINTS = True

_rng_fb = np.random.default_rng(FALLBACK_SEED)
def _choose_by_probs(prob_map):
    keys = list(prob_map.keys())
    ps   = np.array([float(prob_map[k]) for k in keys], dtype=float)
    ps   = ps / ps.sum()
    idx = _rng_fb.choice(len(keys), p=ps)
    return keys[idx]

# =========================
# 中文数字与民国纪年支持
# =========================
CN_DIGIT = {
    "零":0,"〇":0,"○":0,"Ｏ":0,"一":1,"二":2,"两":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,
    "十":10,"廿":20,"卅":30
}
DECADE_REP = { "上旬": 5, "中旬": 15, "下旬": 25 }

def _to_halfwidth(s: str) -> str:
    return s.translate(str.maketrans("１２３４５６７８９０．／－～：",
                                     "1234567890./-~:"))

def _cn_str_to_int(s: str) -> int:
    if not s: return None
    s = s.strip().replace("初","")
    arab = "".join(ch for ch in s if ch.isdigit())
    if arab:
        try:
            v = int(arab)
            return v if v>0 else None
        except:
            pass
    total = 0
    i = 0
    if i < len(s) and s[i] in ("十","廿","卅"):
        total += CN_DIGIT.get(s[i], 0)
        i += 1
    while i < len(s):
        ch = s[i]
        if ch in CN_DIGIT:
            total += CN_DIGIT[ch]
        i += 1
    return total if total>0 else None

def _parse_minguo_year(s: str):
    m = re.search(r"民国([〇零一二两三四五六七八九十廿卅]+)年", s)
    if m:
        y = _cn_str_to_int(m.group(1))
        return 1911 + y if y else None
    m = re.search(r"民国(\d{1,3})年", s)
    if m:
        y = int(m.group(1))
        return 1911 + y if y else None
    return None

def _cn_month_to_int(tok: str):
    tok = tok.replace("月","").strip()
    v = _cn_str_to_int(tok)
    if v and 1 <= v <= 12:
        return v
    digits = "".join(ch for ch in tok if ch.isdigit())
    if digits:
        m = int(digits)
        if 1 <= m <= 12:
            return m
    return None

def _safe_date(y, m, d):
    d = max(1, min(28, d))
    try:
        return datetime(y, m, d).date()
    except Exception:
        return None

def parse_dates_from_text(text, default_year=None):
    """
    解析中文/民国日期与区间：
      - 1931年7月25日 / 1954年8月
      - 民国二十年七月廿五日 / 七月初十 / 八月下旬 / 七、八月
      - 区间：7月25日至8月5日 / 七月下旬至八月上旬
    返回：list[date]（端点模式≤2；uniform模式可能为区间内多日）
    """
    if not isinstance(text, str) or not text.strip():
        return []
    s = _to_halfwidth(text)
    s = s.replace("．",".").replace("。",".").replace("/", "-")
    s = s.replace("—","-").replace("－","-").replace("~","-").replace("至","-")
    s = s.replace("　"," ").strip()

    year = _parse_minguo_year(s) or default_year
    if not year:
        m = re.search(r"(19\d{2}|20\d{2})年", s)
        if m:
            year = int(m.group(1))

    out = []

    # 区间（两端）
    rng = re.search(r"([一二三四五六七八九十廿卅\d]{1,3})月([一二三四五六七八九十廿卅初\d]{1,3})?日?"
                    r"(?:\s*-\s*|到|-|—)"
                    r"([一二三四五六七八九十廿卅\d]{1,3})月([一二三四五六七八九十廿卅初\d]{1,3})?日?", s)
    if rng and year:
        m1 = _cn_month_to_int(rng.group(1))
        d1_tok = rng.group(2) or "15"
        d1 = _cn_str_to_int(d1_tok) or (DECADE_REP.get(d1_tok, 15) if d1_tok in DECADE_REP else 15)
        m2 = _cn_month_to_int(rng.group(3))
        d2_tok = rng.group(4) or "15"
        d2 = _cn_str_to_int(d2_tok) or (DECADE_REP.get(d2_tok, 15) if d2_tok in DECADE_REP else 15)
        dA = _safe_date(year, m1, d1) if m1 else None
        dB = _safe_date(year, m2, d2) if m2 else None
        if dA and dB:
            if DATE_RANGE_MODE == "uniform":
                if dA > dB: dA, dB = dB, dA
                cur = dA
                while cur <= dB:
                    out.append(cur)
                    cur = cur + timedelta(days=1)
            else:
                out.extend([dA, dB])

    # 具体“月-日”：阿拉伯 / 中文
    for m in re.finditer(r"(?P<m>\d{1,2})[-\.月](?P<d>\d{1,2})日?", s):
        if year:
            mm = int(m.group("m")); dd = int(m.group("d"))
            if 1<=mm<=12 and 1<=dd<=31:
                d = _safe_date(year, mm, dd)
                if d: out.append(d)
    for m in re.finditer(r"([一二三四五六七八九十廿卅]{1,3})月([一二三四五六七八九十廿卅初]{1,3})日", s):
        if year:
            mm = _cn_month_to_int(m.group(1)+"月")
            dd = _cn_str_to_int(m.group(2))
            if mm and dd and 1<=dd<=31:
                d = _safe_date(year, mm, dd)
                if d: out.append(d)

    # 年-月 / 旬
    for m in re.finditer(r"(?P<y>19\d{2}|20\d{2})年(?P<m>\d{1,2})月(?P<dec>上旬|中旬|下旬)?", s):
        y = int(m.group("y")); mm = int(m.group("m")); dec = m.group("dec")
        if 1<=mm<=12:
            day = DECADE_REP[dec] if dec else 15
            d = _safe_date(y, mm, day);  out.append(d) if d else None
    for m in re.finditer(r"民国([〇零一二两三四五六七八九十廿卅]+)年([一二三四五六七八九十廿卅]{1,3})月(上旬|中旬|下旬)?", s):
        gy = _parse_minguo_year(m.group(0))
        mm = _cn_month_to_int(m.group(2)+"月")
        dec = m.group(3)
        if gy and mm:
            day = DECADE_REP[dec] if dec else 15
            d = _safe_date(gy, mm, day); out.append(d) if d else None
    for m in re.finditer(r"([一二三四五六七八九十廿卅]{1,3})月(上旬|中旬|下旬)", s):
        if year:
            mm = _cn_month_to_int(m.group(1)+"月")
            if mm:
                d = _safe_date(year, mm, DECADE_REP[m.group(2)]); out.append(d) if d else None
    for m in re.finditer(r"([一二三四五六七八九十廿卅])、([一二三四五六七八九十廿卅])月", s):
        if year:
            mm1 = _cn_month_to_int(m.group(1)+"月"); mm2 = _cn_month_to_int(m.group(2)+"月")
            if mm1: out.append(_safe_date(year, mm1, 15))
            if mm2: out.append(_safe_date(year, mm2, 15))

    out = sorted(list({d for d in out if d}))
    return out

# =========================
# 数量抽取（增强）
# =========================
def parse_quantities_from_text(text):
    """
    抽取所有数量+单位并合并：
      - 支持“万/千/百”倍率词（如“3万斤”“2千袋”“3.5万石”）
      - 支持任意多处匹配，合并求和
    返回：value_in_kg（float）；若无数量则返回 None
    """
    if not isinstance(text, str) or not text.strip():
        return None
    s = _to_halfwidth(text)
    total_kg = 0.0
    found = False

    pat_mul = r"(?P<num>[\d,\.]+)\s*(?P<mult>万|千|百)\s*(?P<unit>吨|t|kg|千克|公斤|斤|石|担|斗|升|袋|车)"
    for m in re.finditer(pat_mul, s):
        num = float(m.group("num").replace(",",""))
        mult = MULTIPLIER.get(m.group("mult"), 1.0)
        unit = m.group("unit")
        kg = num * mult * UNIT_TO_KG.get(unit, np.nan)
        if not math.isnan(kg):
            total_kg += kg; found = True

    pat_simple = r"(?P<num>[\d,\.]+)\s*(?P<unit>吨|t|kg|千克|公斤|斤|石|担|斗|升|袋|车)"
    for m in re.finditer(pat_simple, s):
        num = float(m.group("num").replace(",",""))
        unit = m.group("unit")
        kg = num * UNIT_TO_KG.get(unit, np.nan)
        if not math.isnan(kg):
            total_kg += kg; found = True

    return float(total_kg) if found else None

# =========================
# 通用工具
# =========================
def resample_series(dates, values, freq="D", week_rule="W-MON"):
    ser = pd.Series(values, index=pd.to_datetime(dates))
    if freq == "D":
        ser = ser.resample("D").sum().fillna(0.0)
    else:
        ser = ser.resample(week_rule).sum().fillna(0.0)
    return ser

def poisson_nll(y, mu):
    mu = np.clip(mu, 1e-10, None)
    return np.sum(mu - y * np.log(mu))

# =========================
# 读取工作簿
# =========================
def load_workbook(path):
    return pd.read_excel(path, sheet_name=None)

# =========================
# 从证据构建时序（核心）
# =========================
def build_series_from_evidence(sheets, freq="D", week_rule="W-MON"):
    """
    生成：
      A) series_table：供率定使用的 ts_id->Series（按 freq 聚合）
      B) series_extracted_split：明细表（ts_id, date, value），含“发运/到达 × ZP/PC/CV”的拆分
    命名：
      LINK_ZP_SHIP, LINK_ZP_ARR, LINK_PC_SHIP, LINK_PC_ARR, LINK_CV_SHIP, LINK_CV_ARR, LINK_<LINK>_UNK
      V_DIST, STOCKS, MEDIA_REQ, BREACH, ALLOC, MISC
    """
    evi = sheets["EVIDENCE_MAP"].copy()
    for col in ["period","source_id","page_or_sheet","snippet_or_key",
                "mapped_ts_id","mapped_param_id","quote_excerpt","notes"]:
        if col not in evi.columns:
            evi[col] = ""

    # 加载地名规则
    geo_rules = load_geo_rules(GEO_LINK_MAP_CSV)

    rows_split = []
    extract_logs = []

    for idx, r in evi.iterrows():
        ts_id = str(r.get("mapped_ts_id","")).strip()
        if not ts_id:
            continue
        per   = str(r.get("period","")).strip()
        note  = str(r.get("notes",""))
        ctx   = str(r.get("quote_excerpt",""))
        sk    = str(r.get("snippet_or_key",""))

        # 年份推断
        year = None
        tmp = note + " " + ctx
        m_year = re.search(r"(19\d{2}|20\d{2})年", _to_halfwidth(tmp))
        if m_year: year = int(m_year.group(1))
        if not year and per in ["1931","1954"]:
            year = int(per)

        # 日期
        dates1 = parse_dates_from_text(ctx, default_year=year)
        dates2 = parse_dates_from_text(note, default_year=year)
        cand_dates = dates1 if dates1 else dates2
        if not cand_dates:
            extract_logs.append((idx, ts_id, "NO_DATE", "", "", note[:60], ctx[:120]))
            continue

        # 数量（kg）
        qty = parse_quantities_from_text(ctx)
        val_default = DEFAULT_EVENT_VALUE if qty is None else float(qty)

        # —— 分类命名（地名规则优先 + P010/P020 + 关键词）
        tsu = ts_id.upper()
        merged_txt = (ctx + " " + note)
        merged_low = merged_txt.lower()

        # 方向关键词 + 编码
        ship_kw = ["发运","起运","启运","发出","运出","装船","装车","开航","发往","发去","发至","起运于","出发"]
        arr_kw  = ["到达","抵达","运到","运至","送达","收到","收讫","到库","入库","验收入库","收储","接收","交付"]

        dir_from_code = None
        code_field = (str(r.get("mapped_param_id","")) + " " + str(r.get("snippet_or_key","")) + " " + tsu).upper()
        if "P010" in code_field: dir_from_code = "SHIP"
        if "P020" in code_field: dir_from_code = "ARR"

        def has_any(keys): return any(k.lower() in merged_low for k in keys)

        # 链路推断：优先地名规则；显式 ZP/PC/CV；层级启发；最后 UNK
        def decide_link(ts_id, text):
            for rx, lk in geo_rules:
                if rx.search(text):
                    return lk
            u = (ts_id or "").upper()
            if "ZP" in u: return "ZP"
            if "PC" in u: return "PC"
            if "CV" in u: return "CV"
            uu = text.upper()
            if "ZP" in uu: return "ZP"
            if "PC" in uu: return "PC"
            if "CV" in uu: return "CV"
            tl = text
            has_sheng = ("省" in tl)
            has_zhuanqu = ("专区" in tl) or ("专署" in tl) or ("地区" in tl) or ("行政督察区" in tl)
            has_xian = ("县" in tl) or ("市" in tl) or ("市辖区" in tl)
            has_xiangcun = ("乡" in tl) or ("鎭" in tl) or ("镇" in tl) or ("村" in tl) or ("公社" in tl) or ("大队" in tl) or ("生产队" in tl)
            if has_sheng and has_zhuanqu and not has_xian:
                return "ZP"
            if has_zhuanqu and has_xian and not has_xiangcun:
                return "PC"
            if has_xian and has_xiangcun:
                return "CV"
            return "UNK"

        link = decide_link(ts_id, merged_txt)

        media_kw= ["媒体","报刊","电台","广播","专电","通电","呈文","报告","批复","指示","指令","请求","请拨","请赈","致函","启事","公告"]
        stock_kw= ["库存","仓","仓库","在库","在途","存粮","存料","转仓","出入库","清查","盘点"]
        alloc_kw= ["拨付","拨款","划拨","下拨","经费","款项","募捐","募集","捐助","赈济款","赈款","拨交","拨给","拨至"]
        vdist_kw= ["发放","分发","赈济","救济","救发","配给","配售","按户发放","按人发放","按口粮","按人口","下发","发至各村"]

        # 是否运输相关
        is_linkish = ("LINK" in tsu) or ("运输" in merged_low) or ("运" in merged_low) or has_any(ship_kw+arr_kw) or (dir_from_code is not None)

        if is_linkish:
            if dir_from_code == "SHIP" or has_any(ship_kw):
                name = f"LINK_{link}_SHIP"
            elif dir_from_code == "ARR" or has_any(arr_kw):
                name = f"LINK_{link}_ARR"
            else:
                name = f"LINK_{link}_UNK"
        elif ("MEDIA" in tsu) or ("REQ" in tsu) or has_any(media_kw):
            name = "MEDIA_REQ"
        elif ("STOCK" in tsu) or has_any(stock_kw):
            name = "STOCKS"
        elif ("BREACH" in tsu) or ("溃堤" in merged_low) or ("决口" in merged_low):
            name = "BREACH"
        elif ("ALLOC" in tsu) or has_any(alloc_kw):
            name = "ALLOC"
        elif ("V_DIST" in tsu) or ("VILLAGE" in tsu) or has_any(vdist_kw):
            name = "V_DIST"
        else:
            name = "MISC"

        # —— 从 name 拆出 link/dir（便于兜底分别处理）
        cur_link = "UNK"
        cur_dir  = "UNK"
        if name.startswith("LINK_"):
            parts = name.split("_")
            if len(parts) >= 3:
                cur_link = parts[1] if parts[1] in {"ZP","PC","CV","UNK"} else "UNK"
                cur_dir  = parts[2] if parts[2] in {"SHIP","ARR","UNK"} else "UNK"

        # —— 兜底分配（分别对 link / dir）
        if FALLBACK_ENABLE and name.startswith("LINK_"):
            if cur_link == "UNK":
                cur_link = _choose_by_probs(FALLBACK_LINK_PROBS)
            if cur_dir == "UNK":
                cur_dir = _choose_by_probs(FALLBACK_DIR_PROBS)
            name = f"LINK_{cur_link}_{cur_dir}"

        # —— 写入记录（考虑区间、端点分拆；BREACH 强制端点）
        use_uniform = (DATE_RANGE_MODE == "uniform") and (len(cand_dates) >= 2) and (name != "BREACH")

        cand_dates_sorted = sorted(cand_dates)
        d_first = cand_dates_sorted[0]
        d_last  = cand_dates_sorted[-1]

        if use_uniform:
            dA, dB = d_first, d_last
            days = max(1, (dB - dA).days + 1)
            per_day = val_default / days

            if FALLBACK_ENABLE and FALLBACK_SPLIT_ENDPOINTS and name.startswith("LINK_") and days >= 2:
                parts = name.split("_")
                lk = parts[1] if len(parts)>=2 else "UNK"
                # 最早端点→SHIP
                rows_split.append({"ts_id": f"LINK_{lk}_SHIP", "date": pd.Timestamp(dA), "value": per_day})
                # 中间天：维持当前方向（name）
                cur = dA + pd.Timedelta(days=1)
                while cur < dB:
                    rows_split.append({"ts_id": name, "date": pd.Timestamp(cur), "value": per_day})
                    cur = cur + pd.Timedelta(days=1)
                # 最晚端点→ARR
                rows_split.append({"ts_id": f"LINK_{lk}_ARR", "date": pd.Timestamp(dB), "value": per_day})
                extract_logs.append((idx, ts_id, "RANGE_UNIFORM_SPLIT",
                                     f"{dA.isoformat()}~{dB.isoformat()}",
                                     "QTY" if qty is not None else "EVENT+1", note[:60], ctx[:120]))
            else:
                cur = dA
                while cur <= dB:
                    rows_split.append({"ts_id": name, "date": pd.Timestamp(cur), "value": per_day})
                    cur = cur + pd.Timedelta(days=1)
                extract_logs.append((idx, ts_id, "RANGE_UNIFORM",
                                     f"{dA.isoformat()}~{dB.isoformat()}",
                                     "QTY" if qty is not None else "EVENT+1", note[:60], ctx[:120]))
        else:
            ends = [d_first, d_last] if len(cand_dates_sorted) >= 2 else [d_first]
            if FALLBACK_ENABLE and FALLBACK_SPLIT_ENDPOINTS and name.startswith("LINK_") and len(ends) == 2:
                parts = name.split("_")
                lk = parts[1] if len(parts)>=2 else "UNK"
                rows_split.append({"ts_id": f"LINK_{lk}_SHIP", "date": pd.Timestamp(ends[0]), "value": val_default})
                rows_split.append({"ts_id": f"LINK_{lk}_ARR",  "date": pd.Timestamp(ends[1]), "value": val_default})
                extract_logs.append((idx, ts_id, "ENDPOINTS_SPLIT",
                                     ",".join([x.isoformat() for x in ends]),
                                     "QTY" if qty is not None else "EVENT+1", note[:60], ctx[:120]))
            else:
                for d in ends:
                    rows_split.append({"ts_id": name, "date": pd.Timestamp(d), "value": val_default})
                extract_logs.append((idx, ts_id, "ENDPOINTS" if len(ends)==2 else ("QTY" if qty is not None else "EVENT+1"),
                                     ",".join([x.isoformat() for x in ends]),
                                     "QTY" if qty is not None else "EVENT+1", note[:60], ctx[:120]))

    # —— 汇总前的“终端后处理”：1) 二次分配 UNK；2) 按 τ 先验合成成对方向
    if rows_split:
        # 1) 二次分配 UNK：把 LINK_UNK_UNK / LINK_UNK_* / LINK_*_UNK 都分配到 ZP/PC/CV × SHIP/ARR
        if FALLBACK_ENABLE and FALLBACK_REASSIGN_UNK:
            for i, row in enumerate(rows_split):
                ts = row["ts_id"]
                if not isinstance(ts, str):
                    continue
                if not ts.startswith("LINK_"):
                    continue
                parts = ts.split("_")
                # 规范化为 LINK_<link>_<dir>
                cur_link = parts[1] if len(parts) >= 2 else "UNK"
                cur_dir  = parts[2] if len(parts) >= 3 else "UNK"
                if cur_link == "UNK":
                    cur_link = _choose_by_probs(FALLBACK_LINK_PROBS)
                if cur_dir == "UNK":
                    cur_dir = _choose_by_probs(FALLBACK_DIR_PROBS)
                rows_split[i]["ts_id"] = f"LINK_{cur_link}_{cur_dir}"

        # 2) 若某链路只有一侧方向，则合成另一侧（按 τ 先验平移）
        if SYNTHESIZE_PAIRED:
            # 收集每条链路的日期与值
            link_dir_to_items = {}  # (link, dir) -> list[(date, value)]
            for row in rows_split:
                ts = row["ts_id"]
                if not ts.startswith("LINK_"):
                    continue
                parts = ts.split("_")
                if len(parts) < 3: 
                    continue
                lk, dr = parts[1], parts[2]
                if lk not in {"ZP","PC","CV"} or dr not in {"SHIP","ARR"}:
                    continue
                link_dir_to_items.setdefault((lk, dr), []).append((pd.Timestamp(row["date"]).normalize(), float(row["value"])))

            # 对每个链路检查是否缺少一侧
            for lk in ["ZP","PC","CV"]:
                has_ship = (lk, "SHIP") in link_dir_to_items and len(link_dir_to_items[(lk,"SHIP")])>0
                has_arr  = (lk, "ARR")  in link_dir_to_items and len(link_dir_to_items[(lk,"ARR")])>0
                if has_ship and has_arr:
                    continue  # 成对齐全

                tau = TAU_PRIOR_PER_LINK.get(lk, 5)
                if tau <= 0:
                    tau = 5

                if has_ship and not has_arr:
                    # 用 SHIP 合成 ARR：向后平移 τ 天
                    for d, v in link_dir_to_items[(lk, "SHIP")]:
                        rows_split.append({"ts_id": f"LINK_{lk}_ARR",
                                           "date": pd.Timestamp(d) + pd.Timedelta(days=tau),
                                           "value": float(v) * PAIR_SCALE})
                elif has_arr and not has_ship:
                    # 用 ARR 合成 SHIP：向前平移 τ 天（不早于最小日期减去 365，以防越界太多）
                    for d, v in link_dir_to_items[(lk, "ARR")]:
                        rows_split.append({"ts_id": f"LINK_{lk}_SHIP",
                                           "date": pd.Timestamp(d) - pd.Timedelta(days=tau),
                                           "value": float(v) * PAIR_SCALE})

    # —— 汇总
    if not rows_split:
        series_table = {}
        log_df = pd.DataFrame(extract_logs, columns=["evidence_row","ts_id","mode","date_or_range","parsed","note_head","ctx_head"])
        series_extracted_split = pd.DataFrame(columns=["ts_id","date","value"])
        return series_table, log_df, series_extracted_split

    df = pd.DataFrame(rows_split)
    agg = df.groupby(["ts_id","date"])["value"].sum().reset_index()

    # 转为率定用字典
    series_table = {}
    for ts_name, grp in agg.groupby("ts_id"):
        ser = resample_series(grp["date"].values, grp["value"].values, freq=freq, week_rule=week_rule)
        series_table[ts_name] = ser

    log_df = pd.DataFrame(extract_logs, columns=["evidence_row","ts_id","mode","date_or_range","parsed","note_head","ctx_head"])
    series_extracted_split = agg.sort_values(["ts_id","date"]).reset_index(drop=True)
    return series_table, log_df, series_extracted_split

# =========================
# 率定模块
# =========================
def estimate_hazard(series_table, smooth_lambda=5.0):
    """从 BREACH & MEDIA_REQ 构建 hazard 强度（两个观测通道）。"""
    y_breach = None
    for key in series_table:
        if "BREACH" in key.upper():
            y_breach = series_table[key]; break
    y_media = None
    for key in series_table:
        if ("MEDIA" in key.upper()) or ("REQ" in key.upper()):
            y_media = series_table[key] if y_media is None else (y_media + series_table[key])

    if y_breach is None and y_media is None:
        return None

    idx = y_breach.index if y_breach is not None else y_media.index
    y1 = y_breach.reindex(idx).fillna(0.0) if y_breach is not None else pd.Series(0.0, index=idx)
    y2 = y_media.reindex(idx).fillna(0.0) if y_media is not None else pd.Series(0.0, index=idx)

    T = len(idx)
    x0 = np.r_[np.maximum(y1.values + y2.values, 1.0)*0.2, 0.0, 0.0]
    lb = np.r_[np.zeros(T), -8.0, -8.0]
    ub = np.r_[np.ones(T)*1e5, 8.0, 8.0]

    def nll(z):
        h = np.clip(z[:T], 1e-8, None)
        a1 = math.exp(z[T+0]); a2 = math.exp(z[T+1])
        ll1 = poisson_nll(y1.values, a1*h)
        ll2 = poisson_nll(y2.values, a2*h)
        dh = np.diff(h)
        pen = smooth_lambda * np.sum(dh*dh)
        return ll1 + ll2 + pen

    res = minimize(nll, x0, method="L-BFGS-B", bounds=list(zip(lb, ub)))
    z = res.x
    h = np.clip(z[:T], 0.0, None)
    return pd.DataFrame({
        "date": idx.date, "hazard_rate_est": h,
        "alpha_breach": math.exp(z[T+0]), "alpha_media": math.exp(z[T+1]),
        "objective": res.fun, "success": res.success
    })

def estimate_tau_via_xcorr(ship_ser, arr_ser, max_lag=30):
    s = ship_ser.fillna(0.0).values
    a = arr_ser.fillna(0.0).values
    best_lag = 0; best_corr = -1e9
    for L in range(0, max_lag+1):
        s_shift = np.r_[np.zeros(L), s[:-L]] if L>0 else s
        corr = -1e9
        if np.std(s_shift)>1e-12 and np.std(a)>1e-12:
            corr = np.corrcoef(s_shift, a)[0,1]
        if corr > best_corr:
            best_corr, best_lag = corr, L
    return best_lag, best_corr

def refine_tau_mle(ship_ser, arr_ser, init_tau=5):
    """
    在互相关初值附近，用 Poisson 似然细化 tau：
      arr_t ~ Poisson( sum_k w_k * ship_{t-k} ), w 为中心在 tau 的离散高斯核
    —— 修复：
      1) k 上限裁剪到 T-1，避免空切片/负切片
      2) 极短序列或全零时回退为 xcorr lag
    """
    s = ship_ser.fillna(0.0).values.astype(float)
    a = arr_ser.fillna(0.0).values.astype(float)
    T = len(s)

    # 极短或全零直接回退
    if T < 3 or (np.allclose(s, 0) or np.allclose(a, 0)):
        return float(max(0, int(round(init_tau)))), 0.0, True

    def nll(param):
        tau = max(0.1, float(param[0]))
        width = max(1.0, tau/2.0)
        kmax = min(T-1, int(max(5, tau*3)))   # 关键修复：k 上限 ≤ T-1
        if kmax <= 0:
            mu = np.clip(np.ones(T)*1e-8, 1e-8, None)
            return poisson_nll(a, mu)
        ks = np.arange(0, kmax+1)
        w = np.exp(-0.5*((ks - tau)/width)**2)
        w /= (w.sum() + 1e-12)

        mu = np.zeros(T)
        for k, wk in enumerate(w):
            L = T - k
            if L <= 0:
                break
            mu[k:] += wk * s[:L]
        mu = np.clip(mu, 1e-8, None)
        return poisson_nll(a, mu)

    try:
        res = minimize(nll, x0=np.array([float(init_tau)]), bounds=[(0.1, 60.0)], method="L-BFGS-B")
        return float(res.x[0]), res.fun, res.success
    except Exception:
        # 再次兜底：直接返回互相关初值
        return float(max(0, int(round(init_tau)))), 0.0, False

def estimate_taus(series_table):
    out = []
    for link in ["ZP","PC","CV"]:
        ship_id = f"LINK_{link}_SHIP"
        arr_id  = f"LINK_{link}_ARR"
        if (ship_id in series_table) and (arr_id in series_table):
            s = series_table[ship_id]; a = series_table[arr_id]
            idx = s.index.union(a.index)
            s = s.reindex(idx).fillna(0.0); a = a.reindex(idx).fillna(0.0)
            lag0, corr0 = estimate_tau_via_xcorr(s, a, max_lag=30)
            tau_hat, obj, ok = refine_tau_mle(s, a, init_tau=lag0)
            out.append({"param_id": f"tau_{link}", "initial_cc_lag": lag0,
                        "tau_hat": tau_hat, "cc": corr0, "objective": obj, "success": ok})
    return pd.DataFrame(out)

def estimate_thetas_rate(series_table):
    """
    θ_Z/P/C 与 rate_dist 的稳健粗估（95%分位）
    """
    out = []
    def q95(ser): return float(np.quantile(ser.fillna(0.0).values, 0.95))
    if "V_DIST" in series_table:
        out.append({"param_id":"rate_dist", "estimate": q95(series_table["V_DIST"]), "method":"q95"})
    for lvl, link in [("Z","ZP"), ("P","PC"), ("C","CV")]:
        key = f"LINK_{link}_ARR"
        if key in series_table:
            out.append({"param_id": f"theta_{lvl}", "estimate": q95(series_table[key]), "method":"q95"})
    return pd.DataFrame(out)

def estimate_media_params(series_table):
    """
    媒体/申诉对调拨/到达的加速参数粗估：exp-kernel(media) 回归到 ALLOC（或 LINK 总量）。
    """
    media = None
    for k, ser in series_table.items():
        u = k.upper()
        if ("MEDIA" in u) or ("REQ" in u):
            media = ser if media is None else (media + ser)
    if media is None:
        return pd.DataFrame([{"param_id":"k_news","estimate":0.0,"note":"no media series"},
                             {"param_id":"mu_media","estimate":0.0,"note":"no media series"}])

    if "ALLOC" in series_table:
        resp = series_table["ALLOC"]
    else:
        resp = None
        for k, ser in series_table.items():
            if "LINK" in k.upper():
                resp = ser if resp is None else (resp + ser)
    if resp is None:
        return pd.DataFrame([{"param_id":"k_news","estimate":0.0,"note":"no response series"},
                             {"param_id":"mu_media","estimate":0.0,"note":"no response series"}])

    idx = media.index.union(resp.index)
    m = media.reindex(idx).fillna(0.0).values
    y = resp.reindex(idx).fillna(0.0).values

    def fit(mu):
        mu = max(1e-4, float(mu))
        T = len(m)
        g = np.zeros(T)
        decay = np.exp(-mu*np.arange(T))
        for t in range(T):
            k = np.arange(t+1)
            g[t] = (m[t-k] * decay[:t+1]).sum()
        X = np.vstack([np.ones(T), g]).T
        beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
        k_news = float(beta[1]); c0 = float(beta[0])
        yhat = X @ beta
        rmse = np.sqrt(np.mean((y - yhat)**2))
        return rmse, k_news, mu, c0

    grid = np.linspace(0.02, 0.5, 20)
    best = None
    for mu in grid:
        rmse, k_news, mu_v, c0 = fit(mu)
        if best is None or rmse < best[0]:
            best = (rmse, k_news, mu_v, c0)
    rmse, k_news, mu_media, c0 = best
    return pd.DataFrame([
        {"param_id":"k_news","estimate":k_news,"note":f"rmse={rmse:.4f}, intercept={c0:.2f}"},
        {"param_id":"mu_media","estimate":mu_media,"note":"gridsearch 0.02~0.5"},
    ])

# =========================
# 主流程
# =========================
def main():
    if not os.path.exists(WB_NAME):
        raise SystemExit(f"[ERROR] 找不到工作簿：{WB_NAME}（请与脚本放在同一目录）")

    sheets = load_workbook(WB_NAME)
    series_table, log_df, series_extracted_split = build_series_from_evidence(
        sheets, freq=FREQ, week_rule=WEEK_RULE
    )

    # 率定
    hazard_df = estimate_hazard(series_table, smooth_lambda=SMOOTH_LAMBDA_HAZARD)
    tau_df    = estimate_taus(series_table)
    thetas_df = estimate_thetas_rate(series_table)
    media_df  = estimate_media_params(series_table)

    # 汇总参数
    results = []
    if hazard_df is not None and not hazard_df.empty:
        results.append({"param_id":"P040(hazard_rate)", "estimate":"timeseries", "note":"see HAZARD_SERIES"})
        results.append({"param_id":"hazard_mean", "estimate": float(np.mean(hazard_df["hazard_rate_est"])), "note":"mean of hazard series"})
        results.append({"param_id":"hazard_peak", "estimate": float(np.max(hazard_df["hazard_rate_est"])), "note":"peak of hazard series"})
        results.append({"param_id":"alpha_breach", "estimate": float(hazard_df["alpha_breach"].iloc[0]), "note":"scale"})
        results.append({"param_id":"alpha_media", "estimate": float(hazard_df["alpha_media"].iloc[0]), "note":"scale"})
    if tau_df is not None and not tau_df.empty:
        for _, r in tau_df.iterrows():
            results.append({"param_id": r["param_id"], "estimate": float(r["tau_hat"]), "note": f"xcorr={r['initial_cc_lag']}, cc={r['cc']:.3f}"})
    if thetas_df is not None and not thetas_df.empty:
        for _, r in thetas_df.iterrows():
            results.append({"param_id": r["param_id"], "estimate": float(r["estimate"]), "note": r.get("method","")})
    if media_df is not None and not media_df.empty:
        for _, r in media_df.iterrows():
            results.append({"param_id": r["param_id"], "estimate": float(r["estimate"]), "note": r.get("note","")})
    calib_df = pd.DataFrame(results)

    # 导出聚合后的时序
    ser_rows = []
    for ts_id, ser in series_table.items():
        for dt, val in ser.items():
            ser_rows.append({"ts_id":ts_id, "date":dt.date(), "value":float(val)})
    series_extracted = pd.DataFrame(ser_rows)

    # 写回
    with pd.ExcelWriter(WB_NAME, engine="xlsxwriter", mode="w") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, index=False, sheet_name=name)
        calib_df.to_excel(writer, index=False, sheet_name="CALIB_RESULTS")
        series_extracted.to_excel(writer, index=False, sheet_name="SERIES_EXTRACTED")
        series_extracted_split.to_excel(writer, index=False, sheet_name="SERIES_EXTRACTED_SPLIT")
        log_df.to_excel(writer, index=False, sheet_name="EXTRACTION_LOG")
        if hazard_df is not None and not hazard_df.empty:
            hazard_df.to_excel(writer, index=False, sheet_name="HAZARD_SERIES")

    print("[OK] Calibration finished.")
    print("Written sheets: CALIB_RESULTS / SERIES_EXTRACTED / SERIES_EXTRACTED_SPLIT / EXTRACTION_LOG / HAZARD_SERIES")
    print(f"DATE_RANGE_MODE={DATE_RANGE_MODE}  (uniform=区间均匀摊开；endpoints=仅取端点)")
    print(f"FALLBACK_ENABLE={FALLBACK_ENABLE}, FALLBACK_SPLIT_ENDPOINTS={FALLBACK_SPLIT_ENDPOINTS}, SEED={FALLBACK_SEED}")

if __name__ == "__main__":
    main()
