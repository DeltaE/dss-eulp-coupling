# 7. Glossary

- **DMDU:** Decision Making Under Deep Uncertainty.
- **XLRM:** Framework elements: **X**(uncertainties), **L**(levers), **R**(relationships/models), **M**(metrics).
- **LHS:** Latin Hypercube Sampling (space-filling experimental design).
- **Sobol:** Low-discrepancy sequence for quasi-random sampling.
- **EULP:** End Use Load Profiles (NREL, OEDI).
- **SMART-DS:** Synthetic distribution feeders and scenarios.
- **Peak shaving:** Control strategy to reduce max demand via storage discharge.
- **Load growth:** The load of a planning year: factors on existing customers, new customers and named loads (`configs/growth.yaml`).
- **Network growth:** What the network gains so that it carries the grown load. Expansion is a new feeder from the substation or more substation capacity. Reinforcement is a rebuilt line, a replaced transformer or a regulator.
- **Planning limits:** The loading and voltage limits that tell a run when the network has to grow (`planning_limits` in `configs/growth.yaml`).
- **Round:** One solve of a circuit folder in network growth. Round 0 is the grown circuit as built; the planned round follows the items of `carry_forward` and `planned`, and each later round follows one applied step.
- **Head:** The first element of a path from the source bus: the line or voltage regulator Monitor m1 watches, every express line or copy of the head regulator that a new feeder starts behind, and every second circuit of such a line.
- **Express line:** The line of a new feeder, from the source bus to the open point, serving nothing on the way.
- **Open point:** The switch or line that a new feeder opens to take over the load beyond it.
- **Second circuit:** A line added beside an existing line, on the same buses, when no larger LineCode carries the load. Its name ends in `_ng<j>`.
- **Stuck line:** A three-phase medium-voltage line over its limit with no larger LineCode of its phases, level and construction in the catalogue.
- **Catalogue:** The LineCodes and transformer ratings a network growth step may use, read from SMART-DS feeder folders (`network_growth.catalog`).
- **Planning band:** The voltage band of the planning limits (`planning_limits.voltage_band`).
