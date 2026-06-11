# Population Differentiation Lab

This is a static teaching web application for population ecology and genetics.

Open `index.html` in a browser to use it.

The app accepts:

- Initial population size, `N0`, for each local population
- Intrinsic growth rate, `r`, for each local population
- Environmental noise SD for each local population
- Upper population-size limit, `K`, for each local population
- Number of loci analysed
- Mutation rate
- Selection coefficients for five loci, where positive `s` lowers tracked-allele fitness as `w = 1 - s`
- Initial allele frequencies for one tracked allele at five loci in each population
- Pair-specific directional migration rates in a matrix
- Permutation number
- Isolation time in generations
- Local mating model for Fis: Hardy-Weinberg, partial inbreeding, or cumulative drift
- Inbreeding rate for the partial inbreeding model
- Environmental synchrony, from 0 independent local noise to 1 fully shared environmental noise
- Optional stepping-stone indirect migration for pair-wise Fst
- Optional founder sampling of initial allele copies
- Optional demographic migration, where migrants also change local population size

It reports:

- Fis, Fst, and Fit
- Hobs and Hexp for each local population
- Pair-wise Fst from isolation and migration assumptions
- A 95% permutation interval for Hexp
- Extinction risk for each local population
- Fis dynamics for every local population, with a grey 95% HPD band
- Pair-wise Fst dynamics for every population pair, with a grey 95% HPD band
- Allele-frequency dynamics for one allele at each of five loci in every local population, with 95% HPD bands
- Fixation outcome proportions for each pair and locus

Migration is entered as a directional matrix. Rows are source populations and columns are destination populations, so each pair can have different movement rates in each direction. Rates define the expected number of migrants as `source N * migration rate`; realized migrant counts are then sampled as integer Poisson draws.

For pair-wise Fst, the app can use a stepping-stone indirect migration approximation. When this option is enabled, indirect paths are included as products of direct rates. For example, if `m(1 -> 2) = 0.1` and `m(2 -> 3) = 0.1`, then the indirect `1 -> 3` contribution is `0.1 * 0.1 = 0.01`. This affects the Fst migration modifier. Allele movement itself is still simulated generation by generation using the direct migration matrix, so indirect gene flow emerges over time through intermediate populations.

Default migration rates are zero. This makes isolated-population behavior visible first; students can then add pair-specific migration to see how gene flow changes Fst and allele trajectories.

Model assumptions shown in the interface:

```text
Fst = 1 - (1 - 1 / 2Ne)^t
Fst = 1 / (1 + 4Nm), where Nm is based on realized integer migrant counts
Dynamic pair Fst = isolation Fst * migration-equilibrium Fst
1 - Fit = (1 - Fis) * (1 - Fst)
```

The migration expression is treated as an equilibrium modifier, not as an immediate generation-0 value. Therefore, when initial allele frequencies are equal, dynamic pair-wise Fst starts at `0`. Dynamic Fis also starts at `0` for extant populations. With no migration, the dynamic Fst follows the isolation-time curve; with migration, it grows toward a lower migration-limited value. Because migration is discrete but stochastic, very small expected migrant values can still occasionally produce one migrant. For example, `N = 100` and `m = 0.001` gives `0.1` expected migrants per generation, or about one migrant every ten generations on average.

Population-size model:

- `N0` is the initial population size used at generation 0.
- In each later generation, local Ne follows stochastic logistic dynamics:
  `N(t+1) = N(t) * exp(r * (1 - N(t) / K) + environmental noise)`.
- Environmental noise is a mixture of shared and local shocks. If environmental synchrony is `c`, then:
  `noise = SD * (sqrt(c) * shared shock + sqrt(1 - c) * local shock)`.
  Shared and local shocks are sampled from `Normal(0, 1)`.
- The updated Ne is rounded to an integer and bounded between `0` and `K`.
- If Ne falls below `2`, that local population is treated as extinct for the rest of that permutation.
- Extinct populations have allele frequency `0`, heterozygosity `0`, no migrant contribution, and flat F-statistic dynamics.
- If demographic migration is enabled, incoming migrants can rescue or recolonize a local population if the resulting population size reaches at least `2`.

The permutation model samples population size through time, then recalculates heterozygosity, pair-wise differentiation, Fis dynamics, pair-wise Fst dynamics, extinction risk, and allele-frequency dynamics for each permutation.

Fis is reported as a within-population quantity. Fst is reported only as a pair-wise or metapopulation-level quantity. For example, 2 populations produce 1 Fst trajectory, 3 populations produce 3 pair-wise Fst trajectories, and 4 populations produce 6 pair-wise Fst trajectories.

Local Fis can be modeled in three ways:

- **Hardy-Weinberg**: `Fis = 0` each generation, so `Hobs = Hexp`. Allelic diversity can still decline through drift, but low diversity alone does not create inbreeding.
- **Partial inbreeding**: `Fis(t+1) = s * (1 + Fis(t)) / 2`, where `s` is the inbreeding/selfing rate. This approaches the stable equilibrium `s / (2 - s)`.
- **Cumulative drift**: `Fis = 1 - (1 - 1 / 2Ne)^t`. This is retained as a teaching contrast for closed finite populations where identity by descent accumulates without local random-mating recovery.

Allele dynamics now use a Wright-Fisher style update. For each generation, one allele per locus is updated by selection, mutation, directional migration with realized integer migrant counts, and then binomial sampling of `2Ne` gene copies. Because the final drift step is discrete, alleles can become fixed at frequency `1` or extinct at frequency `0`. With a nonzero mutation rate, a lost or fixed allele can reappear by mutation; with mutation set to zero, fixation and extinction are absorbing states.

If founder sampling is enabled, the initial allele frequency entered by the user is treated as an expected frequency. Initial allele copies are sampled independently for each population and locus:

```text
X0 ~ Binomial(2N0, p0)
p0,realized = X0 / 2N0
```

This avoids forcing two isolated populations to begin with exactly identical allele counts when they have the same displayed starting frequency.

Selection follows the common disadvantage convention for the tracked allele: the tracked allele has relative fitness `w = 1 - s`, while the alternative allele has fitness `1`. Thus `s = 0` is neutral, `s = 0.5` means the tracked allele has half the fitness of the alternative allele, and negative `s` favors the tracked allele.

Allele plots show the permutation mean as a colored line and the 95% HPD interval as a grey band. This matters because the mean can remain intermediate even when many individual permutation runs have already reached loss or fixation.

The fixation outcome table summarizes those hidden scenarios. For every population pair and tracked locus, it reports the percentage of permutations ending with both populations fixed for the tracked allele, both fixed for the alternative allele, fixed for different alleles, still polymorphic, or extinct. This is often more informative than the mean allele-frequency line when populations are small and migration is rare.

The **Neutral drift check** preset sets two isolated populations with equal initial allele frequencies, no mutation, no migration, no selection, constant small population size, and many generations. Under this independent neutral scenario, fixed outcomes should approach approximately:

```text
same tracked fixed      = 0.25
same alternative fixed  = 0.25
different fixed         = 0.50
```

The fixation table also reports **total same fixed** and **different among fixed** to make this comparison clearer when some permutations remain polymorphic or go extinct.
