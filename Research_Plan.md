# System Dynamics Research Plan — 1931 & 1954 Flood Relief

*Prepared for: research on the allocation efficiency of relief in the 1931 & 1954 Changjiang floods*

---

## 0) Research purpose & evaluation metrics

**Purpose.** Explain why 1954 achieved higher relief "structure efficiency" than 1931 by modeling the collection–allocation–delivery pipeline across administrative tiers and logistics.

**Primary metrics.**

* **Structure efficiency (SE)** over a time window $[t_0, t_0+T]$: $\mathrm{SE}(T)= \frac{\text{relief delivered to households}}{\text{relief collected}}\Big|_{[t_0,t_0+T]}$.
* **Time-to-coverage**: time to deliver 25% / 50% / 80% of estimated need.
* **Response time**: median lag from flood onset (or appeal) to first arrival of material at county/village.
* **Leakage ratio**: (losses + spoilage + diversion)/collected.

**Comparative design.** Single SD model with scenario parameter sets for 1931 vs 1954; not two separate models. Scenario parameters capture governance, class structure, external stress, transport capacity, media system, and procurement frictions.

---

## 1) Model boundary & architecture

**Boundary.** Hydrology and inundation are exogenous inputs. Human behavior (evacuation) is handled via an ABM interface (Section 8). Relief modeled includes **cash**, **grain/food**, **seeds/tools (recovery kits)**, and **work-relief (以工代赈, food/cash-for-work)**.

**Tiers.** Z (central) → P (province) → C (county) → V (village/relief point). Flows move down; information & requests move up.

**Core assumptions.**

1. Budgets and in-kind donations are fungible via procurement subject to price and time-to-procure.
2. Transport capacity and approval/information delays constrain throughput.
3. Media attention and political signals modulate collection and prioritization.

---

## 2) Stocks & flows (per tier h ∈ {Z, P, C, V})

**Stocks.**

* *Pledged funds* $F^p_h$
* *Collected funds* $F^c_h$
* *Procured goods (warehouse)* $G^w_h$
* *In-transit goods* $G^{tr}_{h\to h-1}$ by mode (river/rail/road)
* *Received goods* $G^r_{h-1}$
* *Outstanding need* $N_{h-1}$ (calories/households)
* *Work-relief project backlog* $B_h$; *active projects* $A_h$
* *Labor pool available for work-relief* $L_h$
* *Media attention / appeal pressure* $M_h$

**Flows.**

* *Collection rate* $\dot F^c_h=\alpha_h \cdot M_h - \phi_h$ (bounded by administrative capacity)
* *Procurement* $\dot G^w_h= \rho_h F^c_h / P_{food}(t)$ after delay
* *Allocation decision* $u_{h\to h-1}$: dispatch from $G^w_h$ to lower tier
* *Dispatch (logistics)* $\dot G^{tr}_{h\to h-1}= u_{h\to h-1}$ subject to mode capacities $K^{mode}_h$
* *Arrival to lower tier* via transport delay
* *Ration disbursement* $\dot R_{h-1}$ to households; reduces $N_{h-1}$
* *Leakage/spoilage* at rate $\lambda_h$
* *Work-relief activation*: projects start, consume $G^w_h$ (as rations) and/or $F^c_h$ (as wages), output income/food to participants, reduce $N$, and (optionally) reduce future hazard exposure (embankments)

---

## 3) Key equations (illustrative)

* **Demand dynamics (village):** $\dot N_V= H(t) - \beta R_V - \gamma E_V$, where $H(t)$ is hazard-driven need inflow (exogenous), $R_V$ rations delivered, $E_V$ evacuees from ABM, $\beta,\gamma$ conversion factors.
* **Allocation policy (tier h):** $u_{h\to h-1}=\min\{\theta_h\,G^w_h,\ \eta_h\,K_h,\ \delta_h\,\tilde N_{h-1}\}$. Parameters $\theta_h$ (dispatch aggressiveness), $K_h$ (logistics capacity), $\eta_h$ utilization, $\tilde N_{h-1}$ prioritized need signaled upward.
* **Transport delay:** first-order material delay: $\dot G^{tr}_{h\to h-1}=u_{h\to h-1}-\frac{1}{\tau^{tr}_{mode}}G^{tr}_{h\to h-1}$, arrival flow $A_{h-1}=\frac{1}{\tau^{tr}_{mode}}G^{tr}_{h\to h-1}$.
* **Procurement delay:** $\dot Q_h = \frac{1}{\tau^{proc}_h}(\rho_h F^c_h/P_{food}-Q_h)$, then $G^w_h$ increases by $\dot Q_h$.
* **Work-relief (以工代赈) wage/food conversion:** start projects when backlog $B_h$ and funds/goods available. Output to households: $R^{work}_V = w_h A_h$ (rations or cash converted to food), with setup delay $\tau^{work}_h$.
* **Media/appeal dynamics:** $\dot M_h=\kappa_h \cdot \text{(news volume/appeals)} - \mu_h M_h$, influencing $\alpha_h$ (collection) and $\theta_h$ (dispatch priority).

---

## 4) Scenario mapping (1931 vs 1954)

Parameter families (estimate via data and priors):

* **Governance centralization & class friction:** multipliers on $\alpha_h, \theta_h$, and leakage $\lambda_h$.
* **External stress (e.g., conflict):** reduces $K_h$, increases $\tau^{tr}$, raises $\lambda_h$.
* **Transport capacity:** mode-specific $K^{river},K^{rail},K^{road}$ and delays.
* **Media system:** sensitivity of $M_h$ to news/appeals, and its effect on $\alpha_h,\theta_h$.
* **Procurement environment:** $\tau^{proc}_h$ and price $P_{food}(t)$.

---

## 5) Data design & coding (so calibration isn’t “guessy”)

**Event database (news & archives).**

* **Entities:** event\_id, date (ISO), location (admin code), type (flood onset, appeal issued, donation pledged, dispatch, arrival, distribution, work-relief start), quantities (cash, grain tons, rations, workers), source, confidence (A/B/C), notes/verbatim.
* **Derived durations:** onset→appeal, appeal→dispatch, dispatch→arrival, arrival→distribution.
* **Counts/volume by week:** media volume $V_t$ for attention index.

**Administrative aggregates.** Collected funds, procured grain, deliveries by tier and week; wage scales and project counts for work-relief; transport logs if available.

**Socioeconomic baselines.** Population, households affected, caloric needs; price series for grain; transport network distances.

---

## 6) Calibration & inference

* **Approach:** Bayesian calibration of $\Theta=\{\alpha,\theta,\tau,\lambda,\rho,\dots\}$ using event durations and aggregate flows.
* **Observation models:**

  * Durations \~ Lognormal/Weibull linked to $\tau^{proc},\tau^{tr},$ and approval delays.
  * Media counts → latent attention $M$ via Negative Binomial state-space.
  * Delivered amounts observed with measurement error.
* **Techniques:** MCMC (NUTS), particle filtering for delay states; Morris/Sobol sensitivity for policy levers; identifiability checks (profile likelihoods).

---

## 7) Linking news to parameters

* Build weekly **attention index**: $M_t = f(V_t)$ after debiasing (publisher fixed-effects, duplication removal).
* Use **dynamic regression**: collection rate parameter $\alpha_t = \alpha_0 + \alpha_M M_t$; dispatch aggressiveness $\theta_t = \theta_0 + \theta_M M_t$.
* **Event triggers:** when reports say “convoy dispatched/arrived,” pin those time-stamps to constrain $\tau^{tr}$ and effective capacity $K$ (via back-calculated tonnage/day).

---

## 8) SD ↔ ABM coupling (evacuation sensitivity)

* SD outputs per-village **relief arrival profile** (kg/person/week) and **arrival times**; feed to ABM, which returns **evacuation share** $E_V(t)$.
* Feedback: higher evacuation lowers local need $N_V$ and labor $L_V$ (affecting work-relief throughput).
* Coupling cadence: weekly; exchange variables {$R_V$, $E_V$}.

---

## 9) Modeling specific relief types

* **Cash relief:** inflow to $F^c$; conversion to goods via $\rho/P_{food}$ with $\tau^{proc}$. Can also be **wages** in work-relief.
* **Material relief (food):** direct donation or procured; subject to storage/leakage and transport bottlenecks; delivered as rations $\text{kg/person/day}$.
* **Seeds/tools:** modeled in a recovery submodule with a planting window; benefits realized as reduced future need.
* **Work-relief (以工代赈):** projects as tasks consuming rations/cash and producing immediate transfers to participants (and possibly protective works). Includes setup and supervision delays.

---

## 10) Response-time measurement protocol

1. Define canonical timestamps: **onset**, **appeal issued**, **dispatch**, **arrival at county**, **arrival at village**, **first distribution**.
2. Extract from sources; record uncertainty (± days) and whether the report references past events (e.g., “arrived yesterday”).
3. Compute durations with uncertainty; apply right-censoring when only lower/upper bounds exist.
4. Fit distributions (Weibull/Lognormal) by year and tier; compare medians and IQRs; use posteriors as priors for $\tau$ parameters.
5. Validate against any logistics/railway records when available.

---

## 11) Scenario experiments

* **Base 1931 vs base 1954** (estimated parameters).
* **Swap tests:** 1931 governance with 1954 transport, and vice versa.
* **Policy levers:** pre-positioned stocks; earlier appeals; more cash vs in-kind; scale of work-relief; prioritization rules (need vs population vs proximity).
* **Stress tests:** transport disruptions; price spikes; doubled media coverage.

---

## 12) Deliverables & timeline (suggested)

* **D1. Data coding protocol** (event schema + codebook) — Week 1–2.
* **D2. SD model v0 (structure + unit tests)** — Week 2–3.
* **D3. Event database v1 (pilot counties)** — Week 3–4.
* **D4. Calibration v1 + sensitivity** — Week 5–6.
* **D5. SD–ABM coupling demo** — Week 7.
* **D6. Paper figures & policy scenarios** — Week 8–9.

---

## 13) Parameter table (initial priors; to be refined)

| Symbol          | Meaning                                | 1931 prior | 1954 prior |
| --------------- | -------------------------------------- | ---------- | ---------- |
| $\alpha_h$      | Collection responsiveness to attention | lower      | higher     |
| $\theta_h$      | Dispatch aggressiveness                | lower      | higher     |
| $\lambda_h$     | Leakage/spoilage                       | higher     | lower      |
| $K_h$           | Logistics capacity                     | lower      | higher     |
| $\tau^{proc}_h$ | Procurement delay                      | longer     | shorter    |
| $\tau^{tr}$     | Transport delay                        | longer     | shorter    |
| $\rho$          | Cash→food conversion efficiency        | lower      | higher     |

---

## 14) Validation & reporting

* **Face validation** with domain experts; **extreme-conditions tests**; **posterior predictive checks**.
* Visuals: stock–flow diagram, response-time distributions, cumulative delivery curves, SE(T) by scenario, and tornado charts for sensitivity.

---

## 15) Risks & mitigations

* **Data gaps/bias:** use uncertainty coding, partial pooling across counties, and triangulation across sources.
* **Identifiability issues:** limit parameter proliferation; fix or inform some priors from external literature/archives; perform structural tests early.
* **Coupling complexity:** keep SD–ABM interface minimal (two-way low-dimensional signals).

---

*End of plan*
