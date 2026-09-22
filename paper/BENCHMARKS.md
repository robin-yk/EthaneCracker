# Literature benchmark results

## Benchmark design

Three published conventional ethane-cracker studies were replayed with the integrated AramcoMech–Cantera–GP/process model, including the AC-201 acetylene-converter screening step. One missing reactor coordinate was inferred only when the source omitted it. All remaining process quantities were retained as tests.

Chen et al. (2024) reports reactor temperature, dilution, outlet dry-gas composition, plant flow rates, reactor heat, compressor power, and MSP. The source contains two reactor-pressure values: ambient pressure in the process description and 4.5 bar in Table 1. Both values were propagated as a pressure envelope. Residence time was inferred from residual C2H6 only.

Shin et al. (2025) reports plant inventory and energy use without a unique reactor temperature/residence-time/pressure state in the main article. Residence time was inferred from fresh ethane demand across 800–900 °C and 1–5 bar. C3+ production, combustion energy, and on-site GHG remained independent tests.

Wang et al. (2026) provides reactor geometry, feed flow, inlet/outlet states, and detailed compositions. Residence time was computed from the tube volume and ideal-gas volumetric flow. The heating-history exponent was varied over the declared GP domain to test whether the reported single-pass conversion could be reached.

## Reactor and process reproduction

| case | fitted quantity | independent quantity | published | model |
|---|---|---|---:|---:|
| Chen 2024 | C2H6 dry fraction | C2H4 dry fraction | 0.377 | 0.371–0.384 |
| Chen 2024 | C2H6 dry fraction | H2 dry fraction | 0.407 | 0.396–0.412 |
| Chen 2024 | C2H6 dry fraction | CH4 dry fraction | 0.033 | 0.035–0.060 |
| Chen 2024 | C2H6 dry fraction | fresh ethane, kg/kg | 1.108 | 1.248–1.272 |
| Chen 2024 | C2H6 dry fraction | high-T heat, GJ/t | 5.25 | 7.79–7.83 |
| Chen 2024 | C2H6 dry fraction | compressor, kWh/t | 370 | 299–309 |
| Shin 2025 | fresh ethane | C3+, kg/kg | 0.1376 | 0.1145–0.1303 |
| Shin 2025 | fresh ethane | combustion heat, GJ/t | 17.2 | 17.50–18.43 |
| Shin 2025 | fresh ethane | on-site GHG, kg/t | 442 | 442–507 |
| Wang 2026 | geometry; ramp domain | conversion | 0.685 | 0.390 |
| Wang 2026 | geometry; ramp domain | fresh ethane, kg/kg | 1.331 | 1.177 |
| Wang 2026 | geometry; ramp domain | OPEX, MUSD/y | 195.65 | 171.61 |

Chen reproduces the dominant dry-gas species after the residence-time constraint. The remaining fresh-feed and heat gaps locate the discrepancy in overall selectivity and energy accounting.

Shin provides the cleanest process-level check. Its published 17.2 GJ/t combustion energy lies 1.7% below the nearest model state, and the published 442 kgCO2e/t on-site GHG lies at the lower edge of the 442–507 kg/t envelope. C3+ production remains 5–17% lower.

Wang gives a kinetic-model discrimination case. Published geometry fixes a residence time near 0.29 s. AramcoMech reaches 39.0% conversion at the fastest heating history in the current domain; the paper reports 68.5%. The benchmark therefore identifies reaction kinetics and thermal history as the first quantities to reconcile before downstream TEA values are compared.

## Current manuscript use

The literature benchmark supports three distinct validation levels:

1. **species distribution** — Chen;
2. **plant energy and direct emissions** — Shin;
3. **kinetic-model discrimination** — Wang.

The economic values remain visible in the benchmark tables. Cost harmonization requires each study's capital definition, utility boundary, coproduct treatment, and financing basis to be mapped onto one common basis before a direct MSP/LCOE error is assigned.

## References

- Y. Chen, M. J. Kuo, R. Lobo and M. Ierapetritou, *Green Chemistry* 26 (2024) 2903–2911. DOI: 10.1039/D3GC03858K.
- W. Shin, B. Lin, H. Lai, G. Ibrahim and G. Zang, *Green Chemistry* 27 (2025) 3655–3675. DOI: 10.1039/D4GC04538F.
- X. Wang, C. Luo, J. Hu and S. Palanki, *Frontiers in Energy Research* 14 (2026) 1726062. DOI: 10.3389/fenrg.2026.1726062.
