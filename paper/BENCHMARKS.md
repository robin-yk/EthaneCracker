# Literature benchmark results

## Benchmark design

Three published conventional ethane-cracker studies were replayed with the integrated AramcoMech–Cantera–GP/process model, including the AC-201 acetylene-converter screening step. One missing reactor coordinate was inferred only when the source omitted it. Other process quantities were retained for comparison; economic context rows preserve each study’s cost definitions.

Chen et al. (2024) reports reactor temperature, dilution, outlet dry-gas composition, plant flow rates, reactor heat, compressor power, and MSP. The source contains two reactor-pressure values: ambient pressure in the process description and 4.5 bar in Table 1. Both values were propagated as a pressure envelope. Residence time was inferred from residual C2H6 only.

Shin et al. (2025) reports plant inventory and energy use without a unique reactor temperature/residence-time/pressure state in the main article. Residence time was inferred from fresh ethane demand across 800–900 °C and 1–5 bar. C3+ production, combustion energy, and on-site GHG were reserved for comparison.

Wang et al. (2026) provides reactor geometry, feed flow, inlet/outlet states, and detailed compositions. Residence time was computed from the tube volume and ideal-gas volumetric flow. The heating-history exponent was varied over the declared GP domain to test whether the reported single-pass conversion could be reached.

## Reactor and process reproduction

| Case | Quantity | Published | Model | Unit | Use |
|---|---|---:|---:|---|---|
| Chen et al. 2024 | dry C2H6 mole fraction | 0.151 | 0.151–0.151 | mol/mol | fit |
| Chen et al. 2024 | dry C2H4 mole fraction | 0.377 | 0.3719–0.3847 | mol/mol | test |
| Chen et al. 2024 | dry H2 mole fraction | 0.407 | 0.3987–0.4117 | mol/mol | test |
| Chen et al. 2024 | dry CH4 mole fraction | 0.033 | 0.03558–0.0564 | mol/mol | test |
| Chen et al. 2024 | fresh ethane | 1.108 | 1.185–1.219 | kg/kg | test |
| Chen et al. 2024 | high-temperature reactor heat | 5.249 | 7.603–7.683 | GJ/t | test |
| Chen et al. 2024 | compressor work | 370.3 | 297–306.7 | kWh/t | test |
| Chen et al. 2024 | MSP / web cost | 832 | 407.6–416.7 | USD/t | context |
| Chen et al. 2024 | TCM / web annual OPEX | 496 | 159.8–168.5 | MUSD/y | context |
| Shin et al. 2025 | fresh ethane | 1.322 | 1.318–1.322 | kg/kg | fit |
| Shin et al. 2025 | C3+ coproduct | 0.1376 | 0.1097–0.1273 | kg/kg | test |
| Shin et al. 2025 | combustion heat | 17.2 | 17.2–18.58 | GJ/t | test |
| Shin et al. 2025 | on-site GHG | 442 | 415.2–526.9 | kgCO2e/t | test |
| Shin et al. 2025 | LCOE / web cost | 746 | 363.3–397.9 | USD/t | context |
| Shin et al. 2025 | WTG GHG / web carbon | 869 | 1046–1231 | kgCO2e/t | context |
| Wang et al. 2026 | single-pass conversion | 0.685 | 0.3663 | fraction | test |
| Wang et al. 2026 | fresh ethane | 1.331 | 1.169 | kg/kg | test |
| Wang et al. 2026 | recycle ethane | 0.6006 | 2.023 | kg/kg | test |
| Wang et al. 2026 | outlet C2H4 mass fraction | 0.3995 | 0.2403 | kg/kg | test |
| Wang et al. 2026 | outlet CH4 mass fraction | 0.034 | 0.008897 | kg/kg | test |
| Wang et al. 2026 | outlet H2 mass fraction | 0.0309 | 0.01762 | kg/kg | test |
| Wang et al. 2026 | outlet C3 mass fraction | 0.0476 | 0.00362 | kg/kg | test |
| Wang et al. 2026 | outlet C4+ mass fraction | 0.0161 | 0.008082 | kg/kg | test |
| Wang et al. 2026 | CAPEX / web TOC | 357.4 | 526.8 | MUSD | context |
| Wang et al. 2026 | OPEX / web annual OPEX | 195.7 | 179.8 | MUSD/y | context |

The table uses the 640-point GP release and its 0.02–1.5 s domain. Chen residence time is reconstructed from residual ethane. Shin has 43 states within the 0.5% fresh-feed criterion. Wang uses geometry-derived residence time and the heating-ramp search. Economic context rows retain the reported study definitions.

The separate uncertainty calculation uses Chen compressor electricity and Shin total combustion energy for parameter calibration. Other outputs remain reserved for comparison. See [TEA uncertainty](UNCERTAINTY.md).

## References

- Y. Chen, M. J. Kuo, R. Lobo and M. Ierapetritou, *Green Chemistry* 26 (2024) 2903–2911. DOI: 10.1039/D3GC03858K.
- W. Shin, B. Lin, H. Lai, G. Ibrahim and G. Zang, *Green Chemistry* 27 (2025) 3655–3675. DOI: 10.1039/D4GC04538F.
- X. Wang, C. Luo, J. Hu and S. Palanki, *Frontiers in Energy Research* 14 (2026) 1726062. DOI: 10.3389/fenrg.2026.1726062.
