# Estimation of Structural Efficiency in the 1931 and 1954 Yangtze River Floods

This repository contains the data, scripts, and presentation materials for the study:  
**"Estimation of the Structure Efficiency that Caused Different Flood Damages in 1931 and 1954"**.

The project combines historical archival records, hydrological simulations, and a System Dynamics (SD) model to explain why the 1954 flood, despite being more hydrologically extreme, resulted in relatively smaller economic losses compared to 1931.

---

## 📂 Repository Structure

```
.
├── Estimation of the structure efficiency that caused different.pptx   # Presentation slides
├── AAEH2025_ab.docx                                                    # Conference abstract / manuscript
├── build_demo_and_plots.py                                             # Script for demo plots & calibration
├── sd_relief_manual.py                                                 # Main SD model implementation
├── geo_link_map.csv                                                    # Link mapping file (transport network)
├── Unified_Calibration_Full_1931_1954.xlsx                             # Parameter calibration sheet
├── relief_efficiency_summary.csv                                       # Output: relief efficiency metrics
├── structure_efficiency_summary.csv                                    # Output: structural efficiency metrics
└── README.md                                                           # Project documentation
```

---

## 🔍 Research Context

- **Flood years studied**: 1931 and 1954, two of the largest Yangtze River floods in the 20th century.  
- **Puzzle**: The 1954 flood covered **1.5× the inundation area of 1931**, but its **relative economic loss was smaller**.  
- **Hypothesis**: The difference was caused by improvements in the **structural efficiency** of the disaster relief system.  

---

## 🧩 System Dynamics Model

The SD model represents a hierarchical relief system with two coupled flows:

1. **Material flows**: Central (Z) → Province (P) → County (C) → Village (V).  
2. **Information flows**: Village needs → Media reporting → Appeals → Central response.  

Key output metrics:

- **Relief Efficiency (RE)**
```
RE = (Σ Relief delivered) / (Hazard inflow)
```

- **Structural Efficiency (SE)**
```
SE(T) = (Σ Relief delivered to households) / (Σ Relief collected) over [t0, t0+T]
```

---

## ⚙️ How to Run

### Requirements
- Python 3.9+
- pandas, numpy, matplotlib

### 1. Clone the repository
```bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Run simulations

- **Relief efficiency**
```bash
python -c "import sd_relief_manual as sdm; df = sdm.simulate(sdm.SC1954); print(df.head())"
```

- **Generate calibration plots**
```bash
python build_demo_and_plots.py
```

- **Compute structure efficiency**
```bash
python analysis_compute_SE.py   # optional wrapper if provided
```

---

## 📊 Key Results

- **1931 flood**: Structural Efficiency (SE) ≈ **0.64**  
- **1954 flood**: Structural Efficiency (SE) ≈ **0.78**  

→ The 1954 relief system was nearly **20% more efficient**, helping reduce relative economic damages despite stronger hydrological forcing.

---

## 📑 Presentation & Manuscript

- The **PowerPoint slides** summarize the research logic and results for a ~15 min talk.  
- The **Word document** contains the abstract and extended description for AAEH 2025.  

---

## 📜 License

This project is released under the MIT License.  
Please cite the work if you use it in research.

---

## 🙏 Acknowledgments

Archival sources include *Archival Documents of the 1931 Flood in Hubei* and *Archival Documents on Flood Control and Relief, 1954*.  
Modeling framework inspired by standard System Dynamics approaches in disaster logistics.
