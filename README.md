# Ethane Cracking TEA

A browser model for the cost and carbon intensity of fired and Joule-heated ethane cracking. AramcoMech 3.0 reaction chemistry is solved in Cantera and evaluated in the browser through a Gaussian-process surrogate.

[Simulator](https://robin-yk.github.io/TEA-EthaneCracking/) · [Literature comparison](https://robin-yk.github.io/TEA-EthaneCracking/benchmarks/) · [TEA uncertainty](https://robin-yk.github.io/TEA-EthaneCracking/uncertainty/)

## Model

Reactor temperature, residence time, steam dilution, pressure and heating history determine species yields and reaction duty. These outputs set fresh ethane demand, recycle, compression, acetylene hydrogenation, refrigeration, C2 separation, heating duty, cost and carbon intensity.

The process model includes:

- fired and Joule heating, with tail-gas use and purchased energy;
- four-stage compression to 32 bar;
- AC-201 acetylene hydrogenation, with 90% selectivity to ethylene and a 5 ppm product target;
- cold-box ethylene recovery of 99.5% and a C2 splitter shortcut;
- TLE heat recovery, utility costs and coproduct revenue;
- capacity-scaled capital, operating costs and cradle-to-gate carbon intensity.

The simulator provides sensitivity plots, paired heating-route comparisons, saved cases, and SVG/PNG export. An empirical reactor correlation is retained in the engine for regression checks.

## Reactor domain

| Input | Range |
|---|---:|
| Outlet temperature | 750–1000 °C |
| Residence time | 0.02–1.5 s |
| Steam / hydrocarbon | 0–0.70 kg/kg |
| Pressure | 1–5 bar |
| Heating-ramp exponent | 0.45–4 |
| Inlet temperature | 650 °C |

The prescribed temperature history is $T(f)=T_{in}+(T_{out}-T_{in})f^n$, with $f=t/\tau$. The stored GP uses 640 training points, 128 independent Cantera holdout points and 20 reactor segments.

| Holdout quantity | R² | RMSE / observed range |
|---|---:|---:|
| C2H6 conversion | 0.9997 | 0.0059 |
| C2H4 selectivity | 0.9993 | 0.0039 |
| C2H4 yield | 0.9994 | 0.0085 |
| CH4 yield | 0.9996 | 0.0026 |
| H2 yield | 0.9995 | 0.0076 |
| C2H2 yield | 0.9956 | 0.0124 |
| C3 lump | 0.9971 | 0.0162 |
| C4+ lump | 0.9962 | 0.0098 |
| Enthalpy rise | 0.9993 | 0.0077 |

These statistics compare the GP with Cantera calculations. Training and holdout points use separate sampling seeds. Release checks cover reactor-segment convergence, elemental and mass closure, artifact hashes and browser calculations.

## Product and energy accounting

Species yields are expressed per kg ethane entering the coil. With reactor ethylene yield $Y_E$, ethylene formed in AC-201 $\Delta Y_E$, and recovery $R=0.995$, coil feed per kg recovered ethylene is

$$m_{coil}=\frac{1}{R(Y_E+\Delta Y_E)}.$$

Fresh ethane is $(X-\Delta Y_{ethane})m_{coil}$, where $X$ is ethane conversion and $\Delta Y_{ethane}$ is ethane formed in AC-201 per kg coil feed. The remaining ethane is recycled.

Unrecovered ethylene joins the tail gas. Fired heaters consume tail gas before purchased natural gas; Joule heaters supply reactor heat electrically. Only sold surplus gas earns revenue. The acetylene product limit assumes all residual acetylene reaches the recovered product.

Compression, refrigeration, separation and equipment costs use the equations and assumptions in [Methods](paper/METHODS.md). Capital is reported as an AACE Class 5 estimate.

## Literature and uncertainty

[Three literature cases](paper/BENCHMARKS.md) compare composition, feed demand, utility use and emissions. Chen compressor electricity and Shin combustion energy are used to estimate a compression multiplier and effective fired efficiency.

The [uncertainty calculation](uncertainty/README.md) propagates those estimates and specified heat-recovery and capital ranges into costs and break-even electricity prices. Results show the 2.5th, 50th and 97.5th percentiles for assumed model–literature discrepancies of 5%, 10% and 20%.

The planned experimental kinetics comparison is Cassady et al., *Fuel* 268 (2020), 117409 ([DOI](https://doi.org/10.1016/j.fuel.2020.117409)); that comparison is pending.

## Run locally

```sh
python -m http.server 8000
```

Open `http://localhost:8000/`. The repository contains the trained surrogate and saved analysis results.

To rebuild the reactor model, install [the Python dependencies](multiscale/requirements.txt) and follow the commands in [the GP workflow](.github/workflows/cantera-gp.yml). See [multiscale/README.md](multiscale/README.md) for the mechanism files, sampling design and validation steps.

## Files

| Path | Contents |
|---|---|
| `index.html` | Simulator interface |
| `engine.html` | Process calculations and public API |
| `multiscale/` | Cantera calculations, GP and holdout results |
| `benchmarks/` | Literature inputs and model comparisons |
| `uncertainty/` | Parameter calibration and cost uncertainty |
| `paper/` | Methods and numerical tables |
| `qa/` | Browser regression checks |
| `docs/archive/` | Earlier interface and model audit records |

Process reference: Mittal, Kwak, Zheng, Ierapetritou and Vlachos, *Chemical Engineering Journal* 523 (2025), 168251 ([DOI](https://doi.org/10.1016/j.cej.2025.168251)).
