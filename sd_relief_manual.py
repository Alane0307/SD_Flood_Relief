# sd_relief_manual.py
# 4-layer (Z→P→C→V) flood-relief model with material + information flows
# Pure-Python Euler simulator (dt=1 day) so it runs on any setup.
# Outputs: relief_results.png, four_layer_schema.png

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

OUT_DIR = Path(".")
OUT_DIR.mkdir(exist_ok=True, parents=True)

# ----------------------------
# Common model/equations
# ----------------------------
def simulate(params, t_end=90, dt=1.0):
    T = int(t_end/dt) + 1
    time = np.arange(0, T)*dt

    # Stocks (initials)
    Funds_Z   = 0.0
    Goods_Z   = 0.0
    InTr_ZP   = 0.0
    Goods_P   = 0.0
    InTr_PC   = 0.0
    Goods_C   = 0.0
    InTr_CV   = 0.0
    Goods_V   = 0.0
    Need_V    = 5000.0

    Media_M   = 0.0
    Appeal_A  = 0.0

    # Parameters
    alpha_collect = params["alpha_collect"]
    phi_admin     = params["phi_admin"]
    price_food    = params["price_food"]

    theta_Z = params["theta_Z"]
    theta_P = params["theta_P"]
    theta_C = params["theta_C"]

    tau_ZP  = params["tau_ZP"]
    tau_PC  = params["tau_PC"]
    tau_CV  = params["tau_CV"]

    rate_dist   = params["rate_dist"]
    hazard_rate = params["hazard_rate"]

    k_news   = params["k_news"]
    mu_media = params["mu_media"]
    k_req    = params["k_req"]
    mu_app   = params["mu_app"]

    # Logs
    rows = []

    for t in time:
        # --- Information flows ---
        # News pulse grows with hazard + remaining need (scaled)
        News_in     = k_news * (hazard_rate + max(0.0, Need_V/1000.0))
        Media_decay = mu_media * Media_M
        dMedia      = News_in - Media_decay
        Media_M    += dMedia*dt

        # Appeals rise with need and media; decay over time
        Appeal_in    = k_req * (Need_V/1000.0 + 0.2*Media_M)
        Appeal_decay = mu_app * Appeal_A
        dAppeal      = Appeal_in - Appeal_decay
        Appeal_A    += dAppeal*dt

        # Prioritization weight (0..1)
        prior_weight = Appeal_A / (1.0 + Appeal_A)

        cap_Z_eff = theta_Z * prior_weight
        cap_P_eff = theta_P * prior_weight
        cap_C_eff = theta_C * prior_weight

        # --- Material flows ---
        # Funds (collection depends on media; procurement drains funds; admin friction)
        dFunds = alpha_collect*Media_M - (0) - phi_admin  # Buy_Z handled below (after we compute it)
        # Buy at Z: capped by funds and a hard cap (200/day)
        Buy_Z = max(0.0, min(Funds_Z/price_food, 200.0))

        # Dispatch capped by stock and effective capacity
        Send_ZP = max(0.0, min(Goods_Z, cap_Z_eff))
        Send_PC = max(0.0, min(Goods_P, cap_P_eff))
        Send_CV = max(0.0, min(Goods_C, cap_C_eff))

        # Transport arrivals (first-order lags)
        Arrive_P = InTr_ZP / max(1e-9, tau_ZP)
        Arrive_C = InTr_PC / max(1e-9, tau_PC)
        Arrive_V = InTr_CV / max(1e-9, tau_CV)

        # Distribution at V reduces need (min of three)
        Give_V = max(0.0, min(Goods_V, min(rate_dist, Need_V)))

        # --- Integrate stocks (Euler) ---
        Funds_Z += (dFunds - Buy_Z*price_food)*dt

        Goods_Z += (Buy_Z - Send_ZP)*dt
        InTr_ZP += (Send_ZP - Arrive_P)*dt

        Goods_P += (Arrive_P - Send_PC)*dt
        InTr_PC += (Send_PC - Arrive_C)*dt

        Goods_C += (Arrive_C - Send_CV)*dt
        InTr_CV += (Send_CV - Arrive_V)*dt

        Goods_V += (Arrive_V - Give_V)*dt

        Need_V  += (hazard_rate - Give_V)*dt

        rows.append(dict(
            Time=t,
            Funds_Z=Funds_Z, Goods_Z=Goods_Z, Goods_P=Goods_P, Goods_C=Goods_C, Goods_V=Goods_V,
            InTransit_ZP=InTr_ZP, InTransit_PC=InTr_PC, InTransit_CV=InTr_CV,
            Need_V=Need_V, Give_V=Give_V,
            Send_ZP=Send_ZP, Send_PC=Send_PC, Send_CV=Send_CV,
            Arrive_P=Arrive_P, Arrive_C=Arrive_C, Arrive_V=Arrive_V,
            Media_M=Media_M, Appeal_A=Appeal_A, prior_weight=prior_weight,
            News_in=News_in
        ))

    df = pd.DataFrame(rows)
    df["cum_give"] = df["Give_V"].cumsum()
    return df

# ----------------------------
# Scenarios
# ----------------------------
BASE = dict(
    alpha_collect=0.04, phi_admin=0.5, price_food=1.0,
    theta_Z=100.0, theta_P=120.0, theta_C=150.0,
    tau_ZP=2.0, tau_PC=2.0, tau_CV=1.0,
    rate_dist=80.0, hazard_rate=60.0,
    k_news=0.5, mu_media=0.15, k_req=0.6, mu_app=0.10
)

SC1931 = BASE | dict(
    theta_Z=60.0, theta_P=130.0, theta_C=150.0,
    tau_ZP=12.0, tau_PC=7.0, tau_CV=2.0,
    alpha_collect=0.05, rate_dist=90.0,
    mu_media=0.20, k_news=0.40
)

SC1954 = BASE | dict(
    theta_Z=60.0, theta_P=130.0, theta_C=150.0,
    tau_ZP=6.0, tau_PC=4.0, tau_CV=1.0,
    alpha_collect=0.05, rate_dist=90.0,
    mu_media=0.12, k_news=0.60
)

df31 = simulate(SC1931)
df54 = simulate(SC1954)
df31["scenario"] = "1931"
df54["scenario"] = "1954"
df = pd.concat([df31, df54], ignore_index=True)

# ----------------------------
# Plots
# ----------------------------
fig, axs = plt.subplots(2, 2, figsize=(12,8), dpi=120)
for name, g in df.groupby("scenario"):
    axs[0,0].plot(g["Time"], g["cum_give"], label=name)
    axs[0,1].plot(g["Time"], g["Need_V"], label=name)
    axs[1,0].plot(g["Time"], g["Send_CV"], label=f"{name} dispatch")
    axs[1,0].plot(g["Time"], g["Arrive_V"], linestyle="--", label=f"{name} arrival")
    axs[1,1].plot(g["Time"], g["Media_M"], label=f"{name} media")
    axs[1,1].plot(g["Time"], g["Appeal_A"], linestyle="--", label=f"{name} appeals")

axs[0,0].set_title("Cumulative distribution to village (coverage proxy)")
axs[0,1].set_title("Remaining need at village (Need_V)")
axs[1,0].set_title("Dispatch vs Arrival at village")
axs[1,1].set_title("Information signals: Media & Appeals")
for a in axs.flat:
    a.grid(True); a.set_xlabel("Days")
axs[0,0].legend(); axs[0,1].legend(); axs[1,0].legend(); axs[1,1].legend()
plt.tight_layout()
plt.savefig(OUT_DIR/"relief_results.png", bbox_inches="tight")
plt.show()

# ----------------------------
# Simple 4-layer schema (for discussion)
# ----------------------------
def draw_four_layer_schema(outdir: Path = OUT_DIR):
    import matplotlib.patches as patches
    fig, ax = plt.subplots(figsize=(12,5), dpi=120)
    ax.axis("off")
    boxes = {"Z (Central)": (0.5, 3.0), "P (Province)": (3.5, 3.0),
             "C (County)": (6.5, 3.0), "V (Village)": (9.5, 3.0)}
    for t,(x,y) in boxes.items():
        ax.add_patch(patches.Rectangle((x,y), 2.5, 1.5, fill=False, lw=2))
        ax.text(x+1.25, y+0.75, t, ha="center", va="center", fontsize=12, weight="bold")
    def arr(x1,y1,x2,y2,ls="-"):
        ax.annotate("", (x2,y2), (x1,y1), arrowprops=dict(arrowstyle="->", lw=2, linestyle=ls))
    # Goods (solid)
    arr(3.0, 3.75, 3.5, 3.75); arr(6.0, 3.75, 6.5, 3.75); arr(9.0, 3.75, 9.5, 3.75)
    ax.text(1.75, 4.8, "Goods: Buy → Dispatch → Transport → Arrival → Distribution", fontsize=11)
    # Information (dashed, upstream)
    arr(10.75, 4.5, 1.75, 4.5, ls="--")
    ax.text(6.25, 4.9, "Appeals & Media attention influence collection/dispatch", ha="center", fontsize=10)
    fig.savefig(outdir/"four_layer_schema.png", bbox_inches="tight")
    plt.close(fig)

draw_four_layer_schema()
print("Saved figures:\n - relief_results.png\n - four_layer_schema.png")
