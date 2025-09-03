# System Dynamics Research Plan — 1931 & 1954 Flood Relief

*Prepared for: research on the allocation efficiency of relief in the 1931 & 1954 Changjiang floods*

---

## 0) Research purpose & evaluation metrics

**Purpose.** Explain why 1954 achieved higher relief "structure efficiency" than 1931 by modeling the collection–allocation–delivery pipeline across administrative tiers and logistics.

**Primary metrics.**

* **Structure efficiency (SE):**

$$
\mathrm{SE}(T)= \frac{\text{relief delivered to households}}{\text{relief collected}}\Big|_{[t_0,t_0+T]}
$$

* **Time-to-coverage:** time to deliver 25% / 50% / 80% of estimated need.  
* **Response time:** median lag from flood onset (or appeal) to first arrival.  
* **Leakage ratio:**

$$
\text{Leakage} = \frac{\text{losses + spoilage + diversion}}{\text{collected}}
$$

**Comparative design.** Single SD model with scenario parameter sets for 1931 vs 1954. Parameters: governance, class structure, external stress, transport capacity, media system, procurement frictions.

---

## 1) Model boundary & architecture

**Boundary.** Hydrology and inundation are exogenous inputs. Evacuation handled via ABM coupling. Relief modeled includes:  
- **Cash**  
- **Grain/food**  
- **Seeds/tools (recovery kits)**  
- **Work-relief (以工代赈)**  

**Tiers.**  
$$
Z \ (\text{central}) \;\to\; P \ (\text{province}) \;\to\; C \ (\text{county}) \;\to\; V \ (\text{village})
$$

**Core assumptions.**

1. Budgets and in-kind donations fungible via procurement (price + delay).  
2. Transport & approval delays constrain throughput.  
3. Media/political signals modulate collection and prioritization.

---

## 2) Stocks & flows (per tier $h$)

**Stocks.**

- Pledged funds $F^p_h$  
- Collected funds $F^c_h$  
- Warehouse goods $G^w_h$  
- In-transit goods $G^{tr}_{h\to h-1}$ (river/rail/road)  
- Received goods $G^r_{h-1}$  
- Outstanding need $N_{h-1}$  
- Work-relief backlog $B_h$, active projects $A_h$  
- Labor pool $L_h$  
- Media/appeal attention $M_h$  

**Flows.**

- Collection:

$$
\dot F^c_h=\alpha_h M_h - \phi_h
$$

- Procurement:

$$
\dot G^w_h = \frac{\rho_h F^c_h}{P_{food}(t)}
$$

- Allocation: $u_{h\to h-1}$  
- Dispatch (logistics):

$$
\dot G^{tr}_{h\to h-1}= u_{h\to h-1}, \quad \text{subject to mode capacities } K^{mode}_h
$$

- Transport delay → arrival  
- Ration disbursement $\dot R_{h-1}$  
- Leakage/spoilage $\lambda_h$  
- Work-relief activation: $R^{work}_V = w_h A_h$

---

## 3) Key equations (illustrative)

**Demand dynamics (village):**

$$
\dot N_V = H(t) - \beta R_V - \gamma E_V
$$

**Allocation policy (tier $h$):**

$$
u_{h\to h-1} = \min \{\theta_h G^w_h, \ \eta_h K_h, \ \delta_h \tilde N_{h-1}\}
$$

**Transport delay (first-order):**

$$
\dot G^{tr}_{h\to h-1} = u_{h\to h-1} - \frac{1}{\tau^{tr}_{mode}} G^{tr}_{h\to h-1}, \quad
A_{h-1} = \frac{1}{\tau^{tr}_{mode}} G^{tr}_{h\to h-1}
$$

**Procurement delay:**

$$
\dot Q_h = \frac{1}{\tau^{proc}_h}\left(\frac{\rho_h F^c_h}{P_{food}} - Q_h\right), \quad
\dot G^w_h = \dot Q_h
$$

**Work-relief transfer:**

$$
R^{work}_V = w_h A_h
$$

**Media/appeal dynamics:**

$$
\dot M_h = \kappa_h \cdot (\text{news volume}) - \mu_h M_h
$$

---

## 4) Scenario mapping (1931 vs 1954)

* Governance centralization & class friction → $\alpha_h,\theta_h$ multipliers; leakage $\lambda_h$  
* External stress (e.g. conflict) → lower $K_h$, higher $\tau^{tr}$, higher $\lambda_h$  
* Transport capacity → $K^{river}, K^{rail}, K^{road}$ and delays  
* Media system → responsiveness of $M_h$ to news; effects on $\alpha_h,\theta_h$  
* Procurement environment → $\tau^{proc}_h$, $P_{food}(t)$  

---

## 5) Data design & coding

**Event database.**  
Entities: event\_id, date, location, type (onset, appeal, dispatch, arrival, distribution, work-relief start), quantities, source, confidence, notes.  

Durations: onset→appeal, appeal→dispatch, dispatch→arrival, arrival→distribution.  

Weekly media volume $V_t$ → attention index.

**Aggregates.** Collected funds, procured grain, deliveries, wages/projects, transport logs.  

**Baselines.** Population, needs, prices, transport distances.  

---

## 6) Calibration & inference

**Parameters:**

$$
\Theta = \{\alpha,\theta,\tau,\lambda,\rho,\dots\}
$$

**Observation models.**  
- Durations $\sim$ Lognormal/Weibull (map to $\tau^{proc},\tau^{tr}$).  
- Media counts $\to$ latent $M_t$ (Negative Binomial state-space).  
- Delivered amounts with error.  

**Techniques.** MCMC (NUTS), particle filters, Morris/Sobol sensitivity, identifiability checks.  

---

## 7) Linking news to parameters

* Weekly attention index $M_t = f(V_t)$  
* Dynamic regression:  

$$
\alpha_t = \alpha_0 + \alpha_M M_t, \quad
\theta_t = \theta_0 + \theta_M M_t
$$

* Event triggers (dispatch/arrival) → constrain $\tau^{tr}$ and effective $K_h$

---

## 8) SD ↔ ABM coupling

* SD → ABM: relief arrival profile $R_V(t)$  
* ABM → SD: evacuee share $E_V(t)$  
* Feedback: evac lowers $N_V$ and labor $L_V$  
* Exchange weekly: $\{R_V, E_V\}$  

---

## 9) Relief types modeled

* **Cash relief:** inflow $F^c$; convert via $\rho/P_{food}$ with $\tau^{proc}$  
* **Material relief:** grain/food; subject to spoilage/leakage; rations (kg/person/day)  
* **Seeds/tools:** recovery submodule; planting window  
* **Work-relief (以工代赈):** consume goods/cash, produce transfers, possible protective works  

---

## 10) Response-time protocol

1. Time-stamps: onset, appeal, dispatch, arrival (county/village), distribution  
2. Record uncertainty ±days; retroactive flags  
3. Compute durations, apply censoring  
4. Fit distributions (Weibull/Lognormal) by year/tier  
5. Use posteriors as priors for $\tau$; validate against transport records  

---

## 11) Scenario experiments

- Base 1931 vs 1954 (estimated parameters)  
- Swap tests: governance vs transport cross-years  
- Policy levers: pre-positioned stocks; earlier appeals; cash vs in-kind; scale of work-relief  
- Stress tests: transport disruption, price spikes, doubled media coverage  

---

## 12) Deliverables & timeline

* D1. Data coding protocol — Week 1–2  
* D2. SD model v0 — Week 2–3  
* D3. Event DB v1 — Week 3–4  
* D4. Calibration v1 — Week 5–6  
* D5. SD–ABM demo — Week 7  
* D6. Paper figures — Week 8–9  

---

## 13) Parameter table (initial priors)

| Symbol          | Meaning                                | 1931 prior | 1954 prior |
| --------------- | -------------------------------------- | ---------- | ---------- |
| $\alpha_h$      | Collection responsiveness              | lower      | higher     |
| $\theta_h$      | Dispatch aggressiveness                | lower      | higher     |
| $\lambda_h$     | Leakage/spoilage                       | higher     | lower      |
| $K_h$           | Logistics capacity                     | lower      | higher     |
| $\tau^{proc}_h$ | Procurement delay                      | longer     | shorter    |
| $\tau^{tr}$     | Transport delay                        | longer     | shorter    |
| $\rho$          | Cash→food efficiency                   | lower      | higher     |

---

## 14) Validation & reporting

* Face validation with experts  
* Extreme-conditions tests  
* Posterior predictive checks  
* Figures: stock–flow diagrams, response-time distributions, SE(T), sensitivity tornado charts  

---

## 15) Risks & mitigations

* Data gaps/bias → uncertainty coding, partial pooling  
* Identifiability issues → informative priors, structural tests  
* Coupling complexity → keep SD–ABM interface minimal  

---

*End of plan*
