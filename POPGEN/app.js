const populationRows = document.querySelector("#populationRows");
const alleleFrequencyMatrix = document.querySelector("#alleleFrequencyMatrix");
const migrationMatrix = document.querySelector("#migrationMatrix");
const populationOutput = document.querySelector("#populationOutput");
const pairwiseOutput = document.querySelector("#pairwiseOutput");
const fixationOutput = document.querySelector("#fixationOutput");
const summaryMetrics = document.querySelector("#summaryMetrics");
const fstCharts = document.querySelector("#fstCharts");
const fisCharts = document.querySelector("#fisCharts");
const neCharts = document.querySelector("#neCharts");
const alleleCharts = document.querySelector("#alleleCharts");
const statusText = document.querySelector("#statusText");
const progressBar = document.querySelector("#progressBar");

let activeRunId = 0;

const modelInputs = {
  populationCount: document.querySelector("#populationCount"),
  lociCount: document.querySelector("#lociCount"),
  generationCount: document.querySelector("#generationCount"),
  mutationRate: document.querySelector("#mutationRate"),
  permutations: document.querySelector("#permutations"),
  matingModel: document.querySelector("#matingModel"),
  inbreedingRate: document.querySelector("#inbreedingRate"),
  environmentalSynchrony: document.querySelector("#environmentalSynchrony"),
  indirectMigration: document.querySelector("#indirectMigration"),
  founderSampling: document.querySelector("#founderSampling"),
  demographicMigration: document.querySelector("#demographicMigration"),
};

const palette = ["#1f7a62", "#c87434", "#4666b0", "#9a4c8f", "#64723d", "#b23b3b"];

let populations = [
  { name: "Population A", n0: 50, r: 0.35, sd: 0.15, k: 120 },
  { name: "Population B", n0: 50, r: 0.35, sd: 0.15, k: 120 },
];

let initialAlleles = [
  [0.5, 0.5, 0.5, 0.5, 0.5],
  [0.5, 0.5, 0.5, 0.5, 0.5],
];

let migrations = [
  [0, 0],
  [0, 0],
];

const clamp = (value, min, max) => Math.min(Math.max(value, min), max);
const mean = values => values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
const format = value => Number.isFinite(value) ? value.toFixed(4) : "0.0000";
const formatNe = value => Number.isFinite(value) ? value.toFixed(1) : "0.0";

const escapeHtml = value => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

function percentile(values, p) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const index = (sorted.length - 1) * p;
  const lower = Math.floor(index);
  const upper = Math.ceil(index);
  if (lower === upper) return sorted[lower];
  return sorted[lower] + (sorted[upper] - sorted[lower]) * (index - lower);
}

function hpdInterval(values, mass = 0.95) {
  if (!values.length) return [0, 0];
  const sorted = [...values].sort((a, b) => a - b);
  const intervalSize = Math.max(1, Math.floor(sorted.length * mass));
  if (intervalSize >= sorted.length) return [sorted[0], sorted[sorted.length - 1]];

  let bestStart = 0;
  let bestWidth = Infinity;
  for (let start = 0; start + intervalSize < sorted.length; start += 1) {
    const width = sorted[start + intervalSize] - sorted[start];
    if (width < bestWidth) {
      bestWidth = width;
      bestStart = start;
    }
  }
  return [sorted[bestStart], sorted[bestStart + intervalSize]];
}

function randomNormal(meanValue, sdValue) {
  if (sdValue <= 0) return meanValue;
  const u1 = Math.max(Math.random(), Number.EPSILON);
  const u2 = Math.random();
  return meanValue + Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2) * sdValue;
}

function sampleBinomial(trials, probability) {
  const p = clamp(probability, 0, 1);
  let successes = 0;
  for (let i = 0; i < trials; i += 1) {
    if (Math.random() < p) successes += 1;
  }
  return successes;
}

function samplePoisson(lambda) {
  if (lambda <= 0) return 0;
  const limit = Math.exp(-lambda);
  let product = 1;
  let count = 0;
  do {
    count += 1;
    product *= Math.random();
  } while (product > limit);
  return count - 1;
}

function sampleMigrantCount(sourceN, migrationRate) {
  const expectedMigrants = Math.max(0, sourceN * migrationRate);
  return Math.min(sourceN, samplePoisson(expectedMigrants));
}

function getSelectionCoefficients() {
  return [...document.querySelectorAll(".selection-input")].map(input => Number(input.value) || 0);
}

function syncPopulationCount() {
  modelInputs.populationCount.value = populations.length;
}

function resizeMigrationMatrix(size) {
  const next = Array.from({ length: size }, (_, i) =>
    Array.from({ length: size }, (_, j) => {
      if (i === j) return 0;
      return migrations[i]?.[j] ?? 0;
    })
  );
  migrations = next;
}

function resizeAlleleMatrix(size) {
  initialAlleles = Array.from({ length: size }, (_value, popIndex) =>
    Array.from({ length: 5 }, (_locus, locusIndex) => initialAlleles[popIndex]?.[locusIndex] ?? 0.5)
  );
}

function setPopulationCount(count) {
  const nextCount = clamp(Math.round(count) || 2, 2, 12);
  while (populations.length < nextCount) {
    const next = populations.length + 1;
    populations.push({ name: `Population ${next}`, n0: 50, r: 0.35, sd: 0.15, k: 120 });
  }
  populations = populations.slice(0, nextCount);
  resizeMigrationMatrix(nextCount);
  resizeAlleleMatrix(nextCount);
  syncPopulationCount();
  renderPopulationRows();
  renderAlleleFrequencyMatrix();
  renderMigrationMatrix();
}

function removePopulationAt(index) {
  populations.splice(index, 1);
  migrations = migrations
    .filter((_row, rowIndex) => rowIndex !== index)
    .map(row => row.filter((_value, columnIndex) => columnIndex !== index));
  initialAlleles = initialAlleles.filter((_row, rowIndex) => rowIndex !== index);
  syncPopulationCount();
  renderPopulationRows();
  renderAlleleFrequencyMatrix();
  renderMigrationMatrix();
}

function renderPopulationRows() {
  populationRows.innerHTML = "";

  populations.forEach((population, index) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><input aria-label="Population name" data-field="name" data-index="${index}" value="${escapeHtml(population.name)}"></td>
      <td><input aria-label="Initial population size N0" data-field="n0" data-index="${index}" type="number" min="0" step="1" value="${population.n0}"></td>
      <td><input aria-label="Intrinsic growth rate r" data-field="r" data-index="${index}" type="number" step="0.01" value="${population.r}"></td>
      <td><input aria-label="Environmental noise SD" data-field="sd" data-index="${index}" type="number" min="0" step="0.01" value="${population.sd}"></td>
      <td><input aria-label="Upper limit K" data-field="k" data-index="${index}" type="number" min="2" step="1" value="${population.k}"></td>
      <td><button class="remove-btn" type="button" data-remove="${index}" ${populations.length <= 2 ? "disabled" : ""}>x</button></td>
    `;
    populationRows.appendChild(row);
  });
}

function renderAlleleFrequencyMatrix() {
  const headerCells = Array.from({ length: 5 }, (_value, locus) => `<th>Locus ${locus + 1}</th>`).join("");
  const rows = populations.map((population, popIndex) => {
    const cells = Array.from({ length: 5 }, (_value, locus) => `
      <td>
        <input class="matrix-input" aria-label="${escapeHtml(population.name)} initial allele frequency locus ${locus + 1}"
          data-population="${popIndex}" data-locus="${locus}" type="number" min="0" max="1" step="0.01" value="${initialAlleles[popIndex][locus]}">
      </td>
    `).join("");
    return `<tr><th>${escapeHtml(population.name)}</th>${cells}</tr>`;
  }).join("");

  alleleFrequencyMatrix.innerHTML = `
    <table class="migration-table">
      <thead><tr><th>Population</th>${headerCells}</tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function renderMigrationMatrix() {
  const headerCells = populations.map(pop => `<th>${escapeHtml(pop.name)}</th>`).join("");
  const rows = populations.map((source, i) => {
    const cells = populations.map((destination, j) => {
      if (i === j) return `<td class="matrix-self">0</td>`;
      return `
        <td>
          <input class="matrix-input" aria-label="Migration from ${escapeHtml(source.name)} to ${escapeHtml(destination.name)}"
            data-source="${i}" data-destination="${j}" type="number" min="0" step="0.001" value="${migrations[i][j]}">
        </td>
      `;
    }).join("");
    return `<tr><th>${escapeHtml(source.name)} from</th>${cells}</tr>`;
  }).join("");

  migrationMatrix.innerHTML = `
    <table class="migration-table">
      <thead><tr><th>Source to destination</th>${headerCells}</tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function syncPopulationFromInput(event) {
  const input = event.target;
  const index = Number(input.dataset.index);
  const field = input.dataset.field;
  if (!field || !Number.isInteger(index)) return;

  populations[index][field] = field === "name" ? input.value : Number(input.value);
  if (field === "name") {
    renderAlleleFrequencyMatrix();
    renderMigrationMatrix();
  }
}

function syncAlleleFrequencyFromInput(event) {
  const input = event.target;
  const population = Number(input.dataset.population);
  const locus = Number(input.dataset.locus);
  if (!Number.isInteger(population) || !Number.isInteger(locus)) return;
  initialAlleles[population][locus] = clamp(Number(input.value) || 0, 0, 1);
}

function syncMigrationFromInput(event) {
  const input = event.target;
  const source = Number(input.dataset.source);
  const destination = Number(input.dataset.destination);
  if (!Number.isInteger(source) || !Number.isInteger(destination)) return;
  migrations[source][destination] = Math.max(0, Number(input.value) || 0);
}

function getModelConfig() {
  return {
    lociCount: Math.max(1, Math.round(Number(modelInputs.lociCount.value) || 1)),
    generations: Math.max(1, Math.round(Number(modelInputs.generationCount.value) || 1)),
    mutationRate: Math.max(0, Number(modelInputs.mutationRate.value) || 0),
    permutations: clamp(Math.round(Number(modelInputs.permutations.value) || 1), 1, 20000),
    matingModel: modelInputs.matingModel.value,
    inbreedingRate: clamp(Number(modelInputs.inbreedingRate.value) || 0, 0, 1),
    environmentalSynchrony: clamp(Number(modelInputs.environmentalSynchrony.value) || 0, 0, 1),
    indirectMigration: modelInputs.indirectMigration.checked,
    founderSampling: modelInputs.founderSampling.checked,
    demographicMigration: modelInputs.demographicMigration.checked,
    selection: getSelectionCoefficients(),
  };
}

function validateInputs() {
  const problems = [];

  populations.forEach((population, index) => {
    if (!population.name.trim()) problems.push(`Population ${index + 1} needs a name.`);
    if (!Number.isFinite(population.n0) || population.n0 < 0) problems.push(`${population.name || `Population ${index + 1}`} needs N0 >= 0.`);
    if (!Number.isFinite(population.r)) problems.push(`${population.name || `Population ${index + 1}`} needs a finite growth rate r.`);
    if (!Number.isFinite(population.sd) || population.sd < 0) problems.push(`${population.name || `Population ${index + 1}`} needs environmental noise SD >= 0.`);
    if (!Number.isFinite(population.k) || population.k < 2) problems.push(`${population.name || `Population ${index + 1}`} needs K >= 2.`);
    if (population.n0 > population.k) problems.push(`${population.name || `Population ${index + 1}`} needs N0 <= K.`);
  });

  initialAlleles.forEach((row, popIndex) => row.forEach((value, locus) => {
    if (!Number.isFinite(value) || value < 0 || value > 1) {
      problems.push(`${populations[popIndex].name} locus ${locus + 1} initial allele frequency must be 0-1.`);
    }
  }));

  const inbreedingRate = Number(modelInputs.inbreedingRate.value);
  if (!Number.isFinite(inbreedingRate) || inbreedingRate < 0 || inbreedingRate > 1) {
    problems.push("Inbreeding rate must be between 0 and 1.");
  }
  const environmentalSynchrony = Number(modelInputs.environmentalSynchrony.value);
  if (!Number.isFinite(environmentalSynchrony) || environmentalSynchrony < 0 || environmentalSynchrony > 1) {
    problems.push("Environmental synchrony must be between 0 and 1.");
  }

  migrations.forEach((row, i) => row.forEach((value, j) => {
    if (i !== j && (!Number.isFinite(value) || value < 0)) {
      problems.push(`Migration ${populations[i].name} to ${populations[j].name} must be >= 0.`);
    }
  }));

  return problems;
}

function heterozygosityForPopulation(ne, config, fisOverride = null) {
  if (ne < 2) return { he: 0, ho: 0, fis: 1 };
  const theta = 4 * ne * config.mutationRate;
  const neutralHexp = theta / (1 + theta);
  const selectionPressure = mean(config.selection.map(value => Math.abs(value)));
  const selectionLoss = clamp(selectionPressure, 0, 0.95);
  const lociAdjustment = 1 - Math.exp(-config.lociCount / 18);
  const he = clamp(neutralHexp * (1 - selectionLoss) * (0.7 + lociAdjustment * 0.3), 0, 0.999);
  const fis = fisOverride ?? clamp((1 / (1 + Math.sqrt(ne))) + clamp(selectionPressure * 0.25, 0, 0.5), 0, 0.95);
  const ho = clamp(he * (1 - fis), 0, 0.999);
  return { he, ho, fis };
}

function effectiveMigrationRate(source, destination, maxSteps) {
  if (source === destination) return 0;
  let total = 0;

  function walk(current, stepsRemaining, probability, visited) {
    if (stepsRemaining === 0) return;
    for (let next = 0; next < populations.length; next += 1) {
      if (next === current || visited.has(next)) continue;
      const rate = migrations[current][next] || 0;
      if (rate <= 0) continue;
      const nextProbability = probability * rate;
      if (next === destination) total += nextProbability;
      const nextVisited = new Set(visited);
      nextVisited.add(next);
      walk(next, stepsRemaining - 1, nextProbability, nextVisited);
    }
  }

  walk(source, maxSteps, 1, new Set([source]));
  return clamp(total, 0, 1);
}

function pairMigrationRate(source, destination, generations, config) {
  if (!config.indirectMigration) return migrations[source][destination] || 0;
  const maxSteps = Math.min(populations.length - 1, Math.max(1, generations + 1));
  return effectiveMigrationRate(source, destination, maxSteps);
}

function pairwiseFst(popAIndex, popBIndex, neA, neB, generations, config) {
  if (neA < 2 || neB < 2) {
    return { fstIsolation: 0, fstMigration: 0, combined: 0, nm: 0, comparable: false };
  }
  const pairNe = Math.max(1, mean([neA, neB]));
  const fstIsolation = clamp(1 - Math.pow(1 - (1 / (2 * pairNe)), generations), 0, 0.999);
  const migrantsAB = sampleMigrantCount(neA, pairMigrationRate(popAIndex, popBIndex, generations, config));
  const migrantsBA = sampleMigrantCount(neB, pairMigrationRate(popBIndex, popAIndex, generations, config));
  const nm = mean([migrantsAB, migrantsBA]);
  const fstMigration = nm > 0 ? clamp(1 / (1 + 4 * nm), 0, 0.999) : 0.999;
  const combined = clamp(fstIsolation * fstMigration, 0, 0.999);
  return { fstIsolation, fstMigration, combined, nm, comparable: true };
}

function samplePopulationSize(population, currentN, globalShock, environmentalSynchrony) {
  if (currentN < 2) return 0;
  const localShock = randomNormal(0, 1);
  const shared = Math.sqrt(environmentalSynchrony) * globalShock;
  const local = Math.sqrt(1 - environmentalSynchrony) * localShock;
  const environmentalNoise = population.sd * (shared + local);
  const growth = population.r * (1 - (currentN / population.k)) + environmentalNoise;
  return Math.round(clamp(currentN * Math.exp(growth), 0, population.k));
}

function applyDemographicMigration(nextNe, alleles, extinct) {
  const migrantMatrix = populations.map((_source, source) =>
    populations.map((_destination, destination) => {
      if (source === destination || nextNe[source] < 2) return 0;
      return sampleMigrantCount(nextNe[source], migrations[source][destination]);
    })
  );

  const cappedMatrix = migrantMatrix.map((row, source) => {
    const outgoing = row.reduce((sum, value) => sum + value, 0);
    if (outgoing <= nextNe[source]) return row;
    const scale = nextNe[source] / outgoing;
    return row.map(value => Math.floor(value * scale));
  });

  const updatedNe = nextNe.map((n, destination) => {
    const incoming = cappedMatrix.reduce((sum, row) => sum + row[destination], 0);
    const outgoing = cappedMatrix[destination].reduce((sum, value) => sum + value, 0);
    return Math.round(clamp(n - outgoing + incoming, 0, populations[destination].k));
  });

  const updatedAlleles = alleles.map((row, destination) =>
    row.map((value, locus) => {
      const incoming = cappedMatrix.reduce((sum, sourceRow) => sum + sourceRow[destination], 0);
      const outgoing = cappedMatrix[destination].reduce((sum, count) => sum + count, 0);
      const residentCount = Math.max(nextNe[destination] - outgoing, 0);
      const incomingAlleles = cappedMatrix.reduce((sum, sourceRow, source) =>
        sum + sourceRow[destination] * alleles[source][locus], 0
      );
      const total = residentCount + incoming;
      return total > 0 ? clamp(((residentCount * value) + incomingAlleles) / total, 0, 1) : 0;
    })
  );

  updatedNe.forEach((n, index) => {
    extinct[index] = n < 2;
    if (extinct[index]) {
      updatedAlleles[index] = updatedAlleles[index].map(() => 0);
    }
  });

  return { nextNe: updatedNe, alleles: updatedAlleles };
}

function updateFis(previousFis, ne, generation, config) {
  if (ne < 2) return 0;
  if (config.matingModel === "hw") return 0;
  if (config.matingModel === "partial") {
    const selfing = config.inbreedingRate;
    return clamp((selfing * (1 + previousFis)) / 2, 0, 0.999);
  }
  return clamp(1 - Math.pow(1 - (1 / (2 * ne)), generation), 0, 0.999);
}

function initializeSeries(populationCount, generations, lociCount) {
  const generationSlots = generations + 1;
  const byPopulation = Array.from({ length: populationCount }, () => ({
    fis: Array.from({ length: generationSlots }, () => []),
    ne: Array.from({ length: generationSlots }, () => []),
    alleles: Array.from({ length: Math.min(lociCount, 5) }, () =>
      Array.from({ length: generationSlots }, () => [])
    ),
  }));
  return byPopulation;
}

function initializeGenerationSeries(generations) {
  return Array.from({ length: generations + 1 }, () => []);
}

function initializeFixationCounts(lociCount) {
  return Array.from({ length: lociCount }, () => ({
    sameTracked: 0,
    sameAlternative: 0,
    differentFixed: 0,
    polymorphic: 0,
    extinct: 0,
  }));
}

function alleleState(value) {
  if (value >= 0.999) return 1;
  if (value <= 0.001) return 0;
  return null;
}

function nextFrame() {
  return new Promise(resolve => requestAnimationFrame(resolve));
}

function updateProgress(percent, message) {
  const clamped = clamp(percent, 0, 100);
  progressBar.style.width = `${clamped}%`;
  statusText.textContent = message ?? `Running model... ${clamped.toFixed(0)}%`;
}

function summarizeSeries(valuesByGeneration) {
  const intervals = valuesByGeneration.map(values => hpdInterval(values));
  return {
    mean: valuesByGeneration.map(values => mean(values)),
    low: intervals.map(interval => interval[0]),
    high: intervals.map(interval => interval[1]),
  };
}

function simulateAlleles(alleles, currentNe, extinct, config) {
  const next = alleles.map(row => [...row]);

  for (let locus = 0; locus < next[0].length; locus += 1) {
    const afterSelection = next.map((row, popIndex) => {
      if (extinct[popIndex]) return 0;
      const p = row[locus];
      const s = config.selection[locus] || 0;
      const trackedFitness = Math.max(0, 1 - s);
      const alternativeFitness = 1;
      const meanFitness = (p * trackedFitness) + ((1 - p) * alternativeFitness);
      const selected = meanFitness > 0 ? (p * trackedFitness) / meanFitness : 0;
      return clamp(selected, 0, 1);
    });

    for (let destination = 0; destination < next.length; destination += 1) {
      if (extinct[destination] || currentNe[destination] < 2) {
        next[destination][locus] = 0;
        continue;
      }

      const migrantCounts = populations.map((_, source) =>
        source === destination || extinct[source] ? 0 : sampleMigrantCount(currentNe[source], migrations[source][destination])
      );
      const rawMigrants = migrantCounts.reduce((sum, value) => sum + value, 0);
      const scale = rawMigrants > currentNe[destination] ? currentNe[destination] / rawMigrants : 1;
      const effectiveMigrants = migrantCounts.map(count => Math.floor(count * scale));
      const totalMigrants = effectiveMigrants.reduce((sum, value) => sum + value, 0);
      const residentCount = Math.max(currentNe[destination] - totalMigrants, 0);
      const immigrantAlleles = effectiveMigrants.reduce((sum, count, source) => sum + count * afterSelection[source], 0);
      const migrated = currentNe[destination] > 0
        ? ((residentCount * afterSelection[destination]) + immigrantAlleles) / currentNe[destination]
        : 0;
      const mutated = migrated * (1 - config.mutationRate) + (1 - migrated) * config.mutationRate;
      const geneCopies = Math.max(2, Math.round(2 * currentNe[destination]));
      next[destination][locus] = sampleBinomial(geneCopies, mutated) / geneCopies;
    }
  }

  return next;
}

async function runModel() {
  const runId = activeRunId + 1;
  activeRunId = runId;
  const problems = validateInputs();
  if (problems.length) {
    statusText.textContent = problems[0];
    progressBar.style.width = "0%";
    return;
  }

  const config = getModelConfig();
  updateProgress(0, "Running model... 0%");
  await nextFrame();
  if (runId !== activeRunId) return;

  const lociToTrack = Math.min(config.lociCount, 5);
  const populationStats = populations.map(population => ({
    name: population.name.trim(),
    neValues: [],
    heValues: [],
    hoValues: [],
    fisValues: [],
    extinctValues: [],
  }));
  const pairStats = [];
  const dynamics = initializeSeries(populations.length, config.generations, lociToTrack);

  for (let i = 0; i < populations.length; i += 1) {
    for (let j = i + 1; j < populations.length; j += 1) {
      pairStats.push({
        pair: `${populations[i].name.trim()} - ${populations[j].name.trim()}`,
        i,
        j,
        dynamic: initializeGenerationSeries(config.generations),
        fixation: initializeFixationCounts(lociToTrack),
        isolation: [],
        migration: [],
        combined: [],
        nm: [],
      });
    }
  }

  const progressStep = Math.max(1, Math.floor(config.permutations / 100));
  for (let permutation = 0; permutation < config.permutations; permutation += 1) {
    if (runId !== activeRunId) return;
    let currentNe = populations.map(population => Math.round(clamp(population.n0, 0, population.k)));
    const extinct = currentNe.map(ne => ne < 2);
    let fisState = populations.map(() => 0);
    let alleles = populations.map((_population, popIndex) =>
      Array.from({ length: lociToTrack }, (_value, locus) => {
        if (extinct[popIndex]) return 0;
        const initial = initialAlleles[popIndex][locus];
        if (!config.founderSampling) return initial;
        const geneCopies = Math.max(2, Math.round(2 * currentNe[popIndex]));
        return sampleBinomial(geneCopies, initial) / geneCopies;
      })
    );

    for (let generation = 0; generation <= config.generations; generation += 1) {
      const localFis = currentNe.map((ne, index) =>
        config.matingModel === "cumulative" ? updateFis(fisState[index], ne, generation, config) : fisState[index]
      );
      const pairValues = pairStats.map(pair =>
        pairwiseFst(pair.i, pair.j, currentNe[pair.i], currentNe[pair.j], generation, config)
      );

      pairStats.forEach((pair, pairIndex) => {
        if (pairValues[pairIndex].comparable) {
          pair.dynamic[generation].push(pairValues[pairIndex].combined);
        }
      });

      populations.forEach((_population, index) => {
        dynamics[index].fis[generation].push(localFis[index]);
        dynamics[index].ne[generation].push(currentNe[index]);
        alleles[index].forEach((value, locus) => {
          dynamics[index].alleles[locus][generation].push(value);
        });
      });

      if (generation < config.generations) {
        alleles = simulateAlleles(alleles, currentNe, extinct, config);
        const globalShock = randomNormal(0, 1);
        currentNe = populations.map((population, index) =>
          extinct[index] ? 0 : samplePopulationSize(population, currentNe[index], globalShock, config.environmentalSynchrony)
        );
        if (config.demographicMigration) {
          const migrated = applyDemographicMigration(currentNe, alleles, extinct);
          currentNe = migrated.nextNe;
          alleles = migrated.alleles;
        }
        currentNe.forEach((ne, index) => {
          if (ne < 2) {
            extinct[index] = true;
            currentNe[index] = 0;
            alleles[index] = alleles[index].map(() => 0);
          }
        });
        fisState = fisState.map((fis, index) => updateFis(fis, currentNe[index], generation + 1, config));
      }
    }

    currentNe.forEach((ne, index) => {
      const finalFis = mean(dynamics[index].fis[config.generations].slice(-1));
      const local = heterozygosityForPopulation(ne, config, finalFis);
      populationStats[index].neValues.push(ne);
      populationStats[index].heValues.push(local.he);
      populationStats[index].hoValues.push(local.ho);
      populationStats[index].fisValues.push(local.fis);
      populationStats[index].extinctValues.push(extinct[index] ? 1 : 0);
    });

    pairStats.forEach(pair => {
      alleles[pair.i].forEach((valueA, locus) => {
        const counts = pair.fixation[locus];
        if (extinct[pair.i] || extinct[pair.j]) {
          counts.extinct += 1;
          return;
        }

        const stateA = alleleState(valueA);
        const stateB = alleleState(alleles[pair.j][locus]);
        if (stateA === null || stateB === null) {
          counts.polymorphic += 1;
        } else if (stateA === 1 && stateB === 1) {
          counts.sameTracked += 1;
        } else if (stateA === 0 && stateB === 0) {
          counts.sameAlternative += 1;
        } else {
          counts.differentFixed += 1;
        }
      });

      const fst = pairwiseFst(pair.i, pair.j, currentNe[pair.i], currentNe[pair.j], config.generations, config);
      pair.isolation.push(fst.fstIsolation);
      pair.migration.push(fst.fstMigration);
      pair.combined.push(fst.combined);
      pair.nm.push(fst.nm);
    });

    if ((permutation + 1) % progressStep === 0 || permutation + 1 === config.permutations) {
      const percent = ((permutation + 1) / config.permutations) * 100;
      updateProgress(percent, `Running model... ${percent.toFixed(0)}%`);
      await nextFrame();
      if (runId !== activeRunId) return;
    }
  }

  updateProgress(100, "Rendering results... 100%");
  await nextFrame();
  if (runId !== activeRunId) return;
  renderOutputs(populationStats, pairStats, dynamics, config);
}

function renderOutputs(populationStats, pairStats, dynamics, config) {
  const meanFis = mean(populationStats.map(stat => mean(stat.fisValues)));
  const meanFst = pairStats.length ? mean(pairStats.map(pair => mean(pair.combined))) : 0;
  const fit = clamp(1 - ((1 - meanFis) * (1 - meanFst)), 0, 0.999);
  const meanHexp = mean(populationStats.map(stat => mean(stat.heValues)));
  const meanHobs = mean(populationStats.map(stat => mean(stat.hoValues)));

  summaryMetrics.innerHTML = [
    ["Fis", meanFis, "Mean within-population inbreeding"],
    ["Fst", meanFst, "Mean pair-wise differentiation"],
    ["Fit", fit, "Total inbreeding coefficient"],
    ["Hexp / Hobs", `${format(meanHexp)} / ${format(meanHobs)}`, `${config.permutations} permutations`],
  ].map(([label, value, note]) => `
    <div class="metric-card">
      <span>${label}</span>
      <strong>${typeof value === "number" ? format(value) : value}</strong>
      <small>${note}</small>
    </div>
  `).join("");

  populationOutput.innerHTML = populationStats.map(stat => {
    const heLow = percentile(stat.heValues, 0.025);
    const heHigh = percentile(stat.heValues, 0.975);
    return `
      <tr>
        <td>${escapeHtml(stat.name)}</td>
        <td>${formatNe(mean(stat.neValues))}</td>
        <td>${format(mean(stat.heValues))}</td>
        <td>${format(mean(stat.hoValues))}</td>
        <td>${format(mean(stat.fisValues))}</td>
        <td>${format(heLow)} - ${format(heHigh)}</td>
        <td>${(mean(stat.extinctValues) * 100).toFixed(1)}%</td>
      </tr>
    `;
  }).join("");

  pairwiseOutput.innerHTML = pairStats.length ? pairStats.map(pair => `
    <tr>
      <td>${escapeHtml(pair.pair)}</td>
      <td>${format(mean(pair.isolation))}</td>
      <td>${format(mean(pair.migration))}</td>
      <td>${format(mean(pair.combined))}</td>
      <td>${format(mean(pair.nm))}</td>
    </tr>
  `).join("") : `<tr><td class="empty-state" colspan="5">Add at least two populations.</td></tr>`;

  fixationOutput.innerHTML = pairStats.length ? pairStats.flatMap(pair =>
    pair.fixation.map((counts, locus) => {
      const total = Object.values(counts).reduce((sum, value) => sum + value, 0) || 1;
      const fixedTotal = counts.sameTracked + counts.sameAlternative + counts.differentFixed;
      const pct = value => `${((value / total) * 100).toFixed(1)}%`;
      const fixedPct = value => fixedTotal ? `${((value / fixedTotal) * 100).toFixed(1)}%` : "n/a";
      return `
        <tr>
          <td>${escapeHtml(pair.pair)}</td>
          <td>Locus ${locus + 1}</td>
          <td>${pct(counts.sameTracked)}</td>
          <td>${pct(counts.sameAlternative)}</td>
          <td>${pct(counts.sameTracked + counts.sameAlternative)}</td>
          <td>${pct(counts.differentFixed)}</td>
          <td>${fixedPct(counts.differentFixed)}</td>
          <td>${pct(counts.polymorphic)}</td>
          <td>${pct(counts.extinct)}</td>
        </tr>
      `;
    })
  ).join("") : `<tr><td class="empty-state" colspan="9">Add at least two populations.</td></tr>`;

  renderDynamicsCharts(dynamics, pairStats, config);
  statusText.textContent = `Model completed with ${config.permutations.toLocaleString()} permutations.`;
}

function createChartCard(title, subtitle, canvasClass = "") {
  const card = document.createElement("article");
  card.className = "chart-card";
  card.innerHTML = `
    <div class="chart-title">
      <h3>${escapeHtml(title)}</h3>
      <p>${escapeHtml(subtitle)}</p>
    </div>
    <canvas class="${canvasClass}" width="720" height="320"></canvas>
  `;
  return card;
}

function renderDynamicsCharts(dynamics, pairStats, config) {
  fstCharts.innerHTML = "";
  fisCharts.innerHTML = "";
  neCharts.innerHTML = "";
  alleleCharts.innerHTML = "";

  dynamics.forEach((populationDynamic, index) => {
    const name = populations[index].name.trim();
    const fCard = createChartCard(name, "Fis by generation");
    fisCharts.appendChild(fCard);
    drawLineChart(fCard.querySelector("canvas"), [
      { label: "Fis", color: palette[1], ...summarizeSeries(populationDynamic.fis) },
    ], { yMin: 0, yMax: 1, xMax: config.generations, band: true });
  });

  pairStats.forEach((pair, index) => {
    const fstCard = createChartCard(pair.pair, "Pair-wise Fst by generation");
    fstCharts.appendChild(fstCard);
    drawLineChart(fstCard.querySelector("canvas"), [
      { label: "Fst", color: palette[index % palette.length], ...summarizeSeries(pair.dynamic) },
    ], { yMin: 0, yMax: 1, xMax: config.generations, band: true });
  });

  if (!pairStats.length) {
    fstCharts.innerHTML = `<p class="empty-state">Add at least two populations.</p>`;
  }

  const neSummaries = dynamics.map(populationDynamic => summarizeSeries(populationDynamic.ne));
  const maxNe = Math.max(
    2,
    ...neSummaries.flatMap(summary => summary.high.filter(value => Number.isFinite(value))),
    ...populations.map(population => population.k || 0)
  );
  const neYMax = Math.ceil(maxNe * 1.08);
  dynamics.forEach((populationDynamic, index) => {
    const name = populations[index].name.trim();
    const neCard = createChartCard(name, "Ne by generation");
    neCharts.appendChild(neCard);
    drawLineChart(neCard.querySelector("canvas"), [
      { label: "Ne", color: palette[index % palette.length], ...neSummaries[index] },
    ], {
      yMin: 0,
      yMax: neYMax,
      xMax: config.generations,
      band: true,
      yTicks: [0, neYMax / 2, neYMax],
      yFormatter: value => Math.round(value).toString(),
    });
  });

  dynamics.forEach((populationDynamic, index) => {
    const name = populations[index].name.trim();
    const alleleCard = createChartCard(name, "Allele frequency for loci 1-5");
    alleleCharts.appendChild(alleleCard);
    drawLineChart(alleleCard.querySelector("canvas"), populationDynamic.alleles.map((series, locus) => ({
      label: `L${locus + 1}`,
      color: palette[locus % palette.length],
      ...summarizeSeries(series),
    })), { yMin: 0, yMax: 1, xMax: config.generations, band: true });
  });
}

function drawLineChart(canvas, series, options) {
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  const padding = { top: 22, right: 24, bottom: 52, left: 48 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const xMax = Math.max(options.xMax, 1);
  const yMin = options.yMin;
  const yMax = options.yMax > options.yMin ? options.yMax : options.yMin + 1;
  const yTicks = options.yTicks ?? [yMin, (yMin + yMax) / 2, yMax];
  const yFormatter = options.yFormatter ?? (value => value.toFixed(1));
  const xToPx = x => padding.left + (x / xMax) * plotWidth;
  const yToPx = y => padding.top + (1 - ((y - yMin) / (yMax - yMin))) * plotHeight;

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = "#d9e0da";
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let i = 0; i <= 4; i += 1) {
    const y = padding.top + (plotHeight / 4) * i;
    ctx.moveTo(padding.left, y);
    ctx.lineTo(width - padding.right, y);
  }
  ctx.stroke();

  ctx.fillStyle = "#64706a";
  ctx.font = "12px Segoe UI, sans-serif";
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  yTicks.forEach(tick => {
    ctx.fillText(yFormatter(tick), padding.left - 8, yToPx(tick));
  });

  const tickCount = Math.min(5, xMax);
  const tickStep = Math.max(1, Math.ceil(xMax / tickCount));
  const ticks = [];
  for (let tick = 0; tick <= xMax; tick += tickStep) ticks.push(tick);
  if (ticks[ticks.length - 1] !== xMax) ticks.push(xMax);

  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  ticks.forEach(tick => {
    const x = xToPx(tick);
    ctx.strokeStyle = "#cbd5cf";
    ctx.beginPath();
    ctx.moveTo(x, padding.top + plotHeight);
    ctx.lineTo(x, padding.top + plotHeight + 5);
    ctx.stroke();
    ctx.fillStyle = "#64706a";
    ctx.fillText(String(tick), x, padding.top + plotHeight + 9);
  });
  ctx.fillText("Generation", width / 2, height - 16);
  ctx.textAlign = "left";
  ctx.textBaseline = "alphabetic";

  series.forEach(item => {
    if (options.band) {
      ctx.beginPath();
      item.high.forEach((value, index) => {
        const x = xToPx(index);
        const y = yToPx(value);
        index === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      });
      [...item.low].reverse().forEach((value, reverseIndex) => {
        const index = item.low.length - 1 - reverseIndex;
        ctx.lineTo(xToPx(index), yToPx(value));
      });
      ctx.closePath();
      ctx.fillStyle = "rgba(120, 128, 124, 0.22)";
      ctx.fill();
    }

    ctx.beginPath();
    item.mean.forEach((value, index) => {
      const x = xToPx(index);
      const y = yToPx(value);
      index === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.strokeStyle = item.color;
    ctx.lineWidth = 2.5;
    ctx.stroke();
  });

  series.forEach((item, index) => {
    const x = padding.left + index * 72;
    const y = 16;
    ctx.fillStyle = item.color;
    ctx.fillRect(x, y - 9, 20, 4);
    ctx.fillStyle = "#25342d";
    ctx.fillText(item.label, x + 26, y - 4);
  });
}

function resetModel() {
  populations = [
    { name: "Population A", n0: 50, r: 0.35, sd: 0.15, k: 120 },
    { name: "Population B", n0: 50, r: 0.35, sd: 0.15, k: 120 },
  ];
  initialAlleles = [
    [0.5, 0.5, 0.5, 0.5, 0.5],
    [0.5, 0.5, 0.5, 0.5, 0.5],
  ];
  migrations = [
    [0, 0],
    [0, 0],
  ];
  modelInputs.lociCount.value = 10;
  modelInputs.generationCount.value = 50;
  modelInputs.mutationRate.value = 0.00001;
  modelInputs.permutations.value = 1000;
  modelInputs.matingModel.value = "hw";
  modelInputs.inbreedingRate.value = 0;
  modelInputs.environmentalSynchrony.value = 0;
  modelInputs.indirectMigration.checked = true;
  modelInputs.founderSampling.checked = true;
  modelInputs.demographicMigration.checked = true;
  document.querySelectorAll(".selection-input").forEach(input => {
    input.value = 0;
  });
  syncPopulationCount();
  renderPopulationRows();
  renderAlleleFrequencyMatrix();
  renderMigrationMatrix();
  runModel();
}

function loadExample() {
  populations = [
    { name: "Coastal", n0: 80, r: 0.28, sd: 0.12, k: 140 },
    { name: "River", n0: 22, r: 0.38, sd: 0.22, k: 70 },
    { name: "Highland", n0: 12, r: 0.45, sd: 0.28, k: 55 },
    { name: "Forest", n0: 60, r: 0.30, sd: 0.15, k: 120 },
  ];
  initialAlleles = [
    [0.5, 0.5, 0.5, 0.5, 0.5],
    [0.5, 0.5, 0.5, 0.5, 0.5],
    [0.5, 0.5, 0.5, 0.5, 0.5],
    [0.5, 0.5, 0.5, 0.5, 0.5],
  ];
  migrations = [
    [0, 0.04, 0.008, 0.025],
    [0.018, 0, 0.012, 0.02],
    [0.006, 0.01, 0, 0.014],
    [0.032, 0.028, 0.011, 0],
  ];
  modelInputs.lociCount.value = 18;
  modelInputs.generationCount.value = 80;
  modelInputs.mutationRate.value = 0.00002;
  modelInputs.permutations.value = 1500;
  modelInputs.matingModel.value = "partial";
  modelInputs.inbreedingRate.value = 0.05;
  modelInputs.environmentalSynchrony.value = 0.2;
  modelInputs.indirectMigration.checked = true;
  modelInputs.founderSampling.checked = true;
  modelInputs.demographicMigration.checked = true;
  document.querySelectorAll(".selection-input").forEach((input, index) => {
    input.value = [0, 0.015, 0, 0.01, 0.02][index];
  });
  syncPopulationCount();
  renderPopulationRows();
  renderAlleleFrequencyMatrix();
  renderMigrationMatrix();
  runModel();
}

function loadNeutralCheck() {
  populations = [
    { name: "Population A", n0: 12, r: 0, sd: 0, k: 12 },
    { name: "Population B", n0: 12, r: 0, sd: 0, k: 12 },
  ];
  initialAlleles = [
    [0.5, 0.5, 0.5, 0.5, 0.5],
    [0.5, 0.5, 0.5, 0.5, 0.5],
  ];
  migrations = [
    [0, 0],
    [0, 0],
  ];
  modelInputs.lociCount.value = 5;
  modelInputs.generationCount.value = 200;
  modelInputs.mutationRate.value = 0;
  modelInputs.permutations.value = 3000;
  modelInputs.matingModel.value = "hw";
  modelInputs.inbreedingRate.value = 0;
  modelInputs.environmentalSynchrony.value = 0;
  modelInputs.indirectMigration.checked = false;
  modelInputs.founderSampling.checked = true;
  modelInputs.demographicMigration.checked = false;
  document.querySelectorAll(".selection-input").forEach(input => {
    input.value = 0;
  });
  syncPopulationCount();
  renderPopulationRows();
  renderAlleleFrequencyMatrix();
  renderMigrationMatrix();
  runModel();
}

populationRows.addEventListener("input", syncPopulationFromInput);
populationRows.addEventListener("click", event => {
  const index = Number(event.target.dataset.remove);
  if (!Number.isInteger(index) || populations.length <= 2) return;
  removePopulationAt(index);
  runModel();
});

migrationMatrix.addEventListener("input", syncMigrationFromInput);
alleleFrequencyMatrix.addEventListener("input", syncAlleleFrequencyFromInput);

modelInputs.populationCount.addEventListener("change", () => {
  setPopulationCount(Number(modelInputs.populationCount.value));
  runModel();
});

document.querySelector("#addPopulation").addEventListener("click", () => {
  setPopulationCount(populations.length + 1);
});

document.querySelector("#runModel").addEventListener("click", runModel);
document.querySelector("#resetModel").addEventListener("click", resetModel);
document.querySelector("#loadExample").addEventListener("click", loadExample);
document.querySelector("#loadNeutralCheck").addEventListener("click", loadNeutralCheck);

syncPopulationCount();
renderPopulationRows();
renderAlleleFrequencyMatrix();
renderMigrationMatrix();
runModel();
