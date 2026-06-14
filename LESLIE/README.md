# Leslie Population Dynamics App

This app simulates stochastic population dynamics with up to 20 yearly age classes using a Leslie-style model with:

- age-specific fecundity
- age-specific survival
- environmental stochasticity
- random catastrophic reproductive failure years
- demographic stochasticity
- density dependence through emigration above carrying capacity
- single-location and metapopulation spatial modes
- patch-specific carrying capacities
- age-specific inter-patch emigration
- single-species and two-species modes
- up to 1000 replicate simulations

Default Leslie-style schedules now open with zero-filled values so users can enter their own systems directly without clearing example numbers first.

## What This Version Does

- Tracks total population and reproductive population separately
- Defines extinction from total population reaching zero
- Supports a user-defined first reproductive age class
- Supports shared catastrophe years with species-specific reproductive failure
- Supports one-patch local dynamics and multi-patch metapopulation dynamics
- Tracks occupancy proportion and occupied patch counts in metapopulation mode
- Uses a shared effective carrying capacity in coexisting two-species mode
- Summarizes:
  - mean and SD trajectories
  - persistence probability through time
  - extinction probability
  - catastrophe and reproduction-failure probabilities
  - deterministic Leslie lambda
  - realized stochastic population growth rates
  - mean, SD, and median extinction time
  - restricted mean persistence time

## Files

- `app.py`: Streamlit web interface
- `model.py`: simulation engine
- `stochastic.py`: annual stochastic draws
- `summaries.py`: replicate summaries
- `plots.py`: Plotly visualizations
- `validators.py`: input validation
- `defaults.py`: starter parameter sets
- `io_utils.py`: config and CSV export helpers
- `launch_app.bat`: simple launcher

## Install

From the `leslie_app` folder:

```powershell
python -m pip install -r requirements.txt
```

## Run

```powershell
python -m streamlit run app.py
```

Or double-click `launch_app.bat`.

## Citation and Copyright

© David Tarkhnishvili. Please cite this program if it is used in research, teaching, reports, or derivative software.

Suggested citation:

```text
Tarkhnishvili, D. 2026. LESLIE: Leslie Population Dynamics App. Python/Streamlit application for stochastic age-structured population simulation.
```

## Notes

- The app currently uses one fecundity SD and one survival SD per species, applied across age classes.
- Fecundity and carrying capacity use lognormal annual variation because they are positive biological quantities; survival uses beta variation because it is a probability constrained to 0-1; births use Poisson draws because they are counts; and realized survival transitions use binomial draws because each individual either survives from one age class to the next or does not.
- Catastrophe timing is shared within a simulated year, but each species can be set to ignore or respond to that catastrophe.
- In `two_isolated` mode, each species gets its own carrying-capacity draw from the same `K` distribution.
- In `two_coexisting` mode, both species share one annual `K_t`.
- In metapopulation mode, patches can have their own `K` values and are linked by species-specific movement matrices.
- Age class 20 is terminal: individuals do not survive into age 21.
- Fecundity before maturity is forced to zero in the simulation engine even if nonzero values are entered in the table.
- Emigration inputs are shown in a separate table so the density-emigration field is easy to edit from top to bottom.


