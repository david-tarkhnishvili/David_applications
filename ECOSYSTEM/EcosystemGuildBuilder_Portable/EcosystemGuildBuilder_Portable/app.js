const roles = {
  producer: {
    title: "Producers",
    subtitle: "Primary production sources converting sunlight into biomass.",
    color: "#2f8f4e",
    subfunctions: ["primary production source", "carbon aggregator", "habitat builder", "food source"]
  },
  primaryConsumer: {
    title: "1st Order Consumers",
    subtitle: "Herbivores, grazers, seed eaters, nectar feeders, detritus grazers.",
    color: "#b98619",
    subfunctions: ["pollinator", "seed disperser", "grazing pressure", "detritus shredder"]
  },
  higherConsumer: {
    title: "Higher Order Consumers",
    subtitle: "Predators, parasitoids, omnivores, and biological control species.",
    color: "#8e3d55",
    subfunctions: ["predator", "pest regulator", "trophic connector", "amphibious predator"]
  },
  decomposer: {
    title: "Decomposers & Soil Builders",
    subtitle: "Species moving nutrients through litter, dung, soil, and dead biomass.",
    color: "#596e35",
    subfunctions: ["soil builder", "nutrient recycler", "litter processor", "microhabitat engineer"]
  }
};

const traitRules = [
  { test: /rosa|crataegus|carpinus|fragaria|triticum|quercus|pinus|plant|grass|tree|shrub|herb/i, roles: ["producer"], guild: "Plants and primary production" },
  { test: /lumbricus|earthworm/i, roles: ["decomposer", "primaryConsumer"], guild: "Soil decomposer guild" },
  { test: /armadillidium|armadillium|isopod|woodlouse/i, roles: ["decomposer", "primaryConsumer"], guild: "Soil decomposer guild" },
  { test: /helix|helicella|snail|slug/i, roles: ["primaryConsumer", "decomposer"], guild: "Grazers and detritus feeders" },
  { test: /pieris|lycaena|inachis|iphiclides|butterfly|moth/i, roles: ["primaryConsumer"], guild: "Pollinator and herbivore guild", sub: ["pollinator", "nectar feeder", "larval herbivore"] },
  { test: /coccinella|ladybird|ladybug/i, roles: ["higherConsumer"], guild: "Predators and biological control", sub: ["predator", "pest regulator"] },
  { test: /carabus|beetle/i, roles: ["higherConsumer"], guild: "Predators and biological control", sub: ["ground predator"] },
  { test: /potamon|crab/i, roles: ["higherConsumer", "decomposer"], guild: "Aquatic-edge omnivores", sub: ["omnivore", "detritus processor"] },
  { test: /pelophylax|lissotriton|rana|frog|newt|amphibian/i, roles: ["higherConsumer"], guild: "Wetland predators", sub: ["insect predator", "trophic connector"] },
  { test: /callopteryx|calopteryx|dragonfly|damselfly/i, roles: ["higherConsumer"], guild: "Wetland predators", sub: ["insect predator", "aquatic larval predator"] },
  { test: /parus|passer|bird|sparrow|tit/i, roles: ["higherConsumer", "primaryConsumer"], guild: "Bird omnivore guild", sub: ["seed disperser", "insect predator", "trophic connector"] },
  { test: /pica|corvus|crow|magpie/i, roles: ["higherConsumer", "decomposer"], guild: "Bird omnivore guild", sub: ["omnivore", "scavenger", "seed disperser"] },
  { test: /egretta|heron|egret/i, roles: ["higherConsumer"], guild: "Wetland predators", sub: ["fish predator", "amphibian predator", "trophic connector"] },
  { test: /apodemus|mouse|rodent/i, roles: ["primaryConsumer"], guild: "Seed and fruit consumer guild", sub: ["seed disperser", "seed predator", "soil disturbance"] }
];

const plantNames = /rosa|crataegus|carpinus|fragaria|triticum|quercus|pinus|plant|grass|tree|shrub|herb/i;
const pollinatorNames = /pieris|lycaena|inachis|iphiclides|butterfly|moth|bee|bombus|apis/i;
const predatorNames = /carabus|coccinella|pelophylax|lissotriton|rana|callopteryx|calopteryx|dragonfly|damselfly|frog|newt|beetle|parus|pica|corvus|egretta/i;
const decomposerNames = /lumbricus|armadillidium|armadillium|earthworm|isopod|woodlouse/i;
const grazerNames = /helix|helicella|snail|slug|pieris|lycaena|inachis|iphiclides|apodemus|passer|parus/i;
const amphibianNames = /pelophylax|lissotriton|rana|frog|newt/i;
const insectPredatorNames = /callopteryx|calopteryx|carabus|coccinella|dragonfly|damselfly|beetle/i;
const smallPreyNames = /lumbricus|armadillidium|armadillium|helix|helicella|pieris|lycaena|inachis|iphiclides|apodemus|passer|snail|slug|earthworm|isopod|woodlouse/i;
const largeBirdNames = /pica|corvus|egretta|magpie|crow|egret|heron/i;
const smallBirdNames = /parus|passer|tit|sparrow/i;

let species = [];
let interactions = [];
let simulation = null;
let manualEdits = loadManualEdits();

const els = {
  file: document.querySelector("#csvFile"),
  loadSample: document.querySelector("#loadSample"),
  enrich: document.querySelector("#enrichBtn"),
  statusDot: document.querySelector("#statusDot"),
  statusText: document.querySelector("#statusText"),
  progressWrap: document.querySelector("#progressWrap"),
  progressBar: document.querySelector("#progressBar"),
  progressText: document.querySelector("#progressText"),
  roleGrid: document.querySelector("#roleGrid"),
  moduleGrid: document.querySelector("#moduleGrid"),
  network: document.querySelector("#networkCanvas"),
  matrix: document.querySelector("#matrixTable"),
  simpleMatrix: document.querySelector("#simpleMatrixTable"),
  sources: document.querySelector("#sourceList"),
  editSpecies: document.querySelector("#editSpeciesSelect"),
  editRoleChecks: document.querySelector("#editRoleChecks"),
  editSubfunctions: document.querySelector("#editSubfunctions"),
  editGuild: document.querySelector("#editGuild"),
  editModule: document.querySelector("#editModule"),
  saveSpeciesEdit: document.querySelector("#saveSpeciesEdit"),
  resetSpeciesEdit: document.querySelector("#resetSpeciesEdit"),
  editPairA: document.querySelector("#editPairA"),
  editPairB: document.querySelector("#editPairB"),
  editEffectAB: document.querySelector("#editEffectAB"),
  editEffectBA: document.querySelector("#editEffectBA"),
  editStrength: document.querySelector("#editStrength"),
  editPairNote: document.querySelector("#editPairNote"),
  savePairEdit: document.querySelector("#savePairEdit"),
  resetPairEdit: document.querySelector("#resetPairEdit"),
  clearManualEdits: document.querySelector("#clearManualEdits"),
  manualEditList: document.querySelector("#manualEditList"),
  showWeak: document.querySelector("#showWeak"),
  showNeutral: document.querySelector("#showNeutral"),
  charge: document.querySelector("#chargeSlider"),
  size: document.querySelector("#sizeSlider")
};

document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab, .view").forEach(item => item.classList.remove("active"));
    tab.classList.add("active");
    document.querySelector(`#${tab.dataset.view}`).classList.add("active");
    if (tab.dataset.view === "network") renderNetwork();
  });
});

els.file.addEventListener("change", async event => {
  const file = event.target.files[0];
  if (!file) return;
  loadCsv(await file.text(), file.name);
});

els.loadSample.addEventListener("click", async () => {
  setStatus("busy", "Loading local species.csv...");
  try {
    const response = await fetch("species.csv", { cache: "no-store" });
    if (!response.ok) throw new Error("Could not fetch species.csv");
    loadCsv(await response.text(), "species.csv");
  } catch (error) {
    setStatus("", "Open this folder through the local web server, or use Upload CSV.");
  }
});

els.enrich.addEventListener("click", enrichFromInternet);
els.showWeak.addEventListener("change", renderNetwork);
els.showNeutral.addEventListener("change", renderNetwork);
els.charge.addEventListener("input", renderNetwork);
els.size.addEventListener("input", renderNetwork);
els.editSpecies.addEventListener("change", syncSpeciesEditor);
els.editPairA.addEventListener("change", syncPairEditor);
els.editPairB.addEventListener("change", syncPairEditor);
els.saveSpeciesEdit.addEventListener("click", saveSpeciesCorrection);
els.resetSpeciesEdit.addEventListener("click", resetSpeciesCorrection);
els.savePairEdit.addEventListener("click", savePairCorrection);
els.resetPairEdit.addEventListener("click", resetPairCorrection);
els.clearManualEdits.addEventListener("click", clearManualCorrections);

function parseCsv(text) {
  const lines = text.replace(/^\uFEFF/, "").split(/\r?\n/).filter(Boolean);
  const headers = splitCsvLine(lines.shift()).map(h => h.trim().toLowerCase());
  const speciesIndex = headers.findIndex(h => ["species", "taxon", "name", "scientific_name"].includes(h));
  if (speciesIndex < 0) throw new Error("CSV needs a species column.");
  return lines.map(line => splitCsvLine(line)[speciesIndex]?.trim()).filter(Boolean);
}

function splitCsvLine(line) {
  const cells = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < line.length; i += 1) {
    const char = line[i];
    if (char === '"' && line[i + 1] === '"') {
      cell += '"';
      i += 1;
    } else if (char === '"') {
      quoted = !quoted;
    } else if (char === "," && !quoted) {
      cells.push(cell);
      cell = "";
    } else {
      cell += char;
    }
  }
  cells.push(cell);
  return cells;
}

function loadCsv(text, sourceName) {
  try {
    species = parseCsv(text).map((name, index) => applySpeciesOverride(classifySpecies(name, index)));
    interactions = buildInteractions(species);
    renderAll();
    setProgress(0, 0, false);
    setStatus("good", `Loaded ${species.length} species from ${sourceName}. Classification uses ecological rules; press Consult internet to add evidence notes.`);
  } catch (error) {
    setStatus("", error.message);
  }
}

function classifySpecies(name, index) {
  const matched = traitRules.filter(rule => rule.test.test(name));
  const roleKeys = [...new Set(matched.flatMap(rule => rule.roles))];
  const subfunctions = [...new Set(matched.flatMap(rule => rule.sub || roleKeys.flatMap(role => roles[role].subfunctions.slice(0, 2))))];
  const guild = matched[0]?.guild || "Unresolved ecological role";
  return {
    id: `s${index}`,
    name,
    roles: roleKeys.length ? roleKeys : ["primaryConsumer"],
    subfunctions: subfunctions.length ? subfunctions : ["field observation needed"],
    guild,
    module: inferModule(name, guild),
    source: null,
    summary: "Internet evidence has not been loaded yet."
  };
}

function inferModule(name, guild) {
  if (plantNames.test(name) || pollinatorNames.test(name)) return "Plant-pollinator-herbivore module";
  if (decomposerNames.test(name) || /helix|helicella/i.test(name)) return "Soil-litter nutrient module";
  if (/pelophylax|lissotriton|callopteryx|calopteryx|potamon/i.test(name)) return "Wetland food-web module";
  if (predatorNames.test(name)) return "Predator-control module";
  return guild;
}

function buildInteractions(items) {
  const links = [];
  for (let i = 0; i < items.length; i += 1) {
    for (let j = i + 1; j < items.length; j += 1) {
      const a = items[i];
      const b = items[j];
      const relation = applyPairOverride(a, b, inferRelation(a, b));
      links.push({ source: a.id, target: b.id, a: a.name, b: b.name, ...relation });
    }
  }
  return links;
}

function inferRelation(a, b) {
  const an = a.name;
  const bn = b.name;
  if (plantNames.test(an) && pollinatorNames.test(bn)) return link("++", "strong", "pollination and nectar/host-plant dependence");
  if (pollinatorNames.test(an) && plantNames.test(bn)) return link("++", "strong", "pollination and nectar/host-plant dependence");
  if (plantNames.test(an) && grazerNames.test(bn)) return link("+-", "strong", "herbivory: consumer benefits, plant loses tissue", true);
  if (grazerNames.test(an) && plantNames.test(bn)) return link("+-", "strong", "herbivory: consumer benefits, plant loses tissue");
  if (predatorNames.test(an) && grazerNames.test(bn)) return link("+-", "strong", "predation: predator benefits, prey is harmed");
  if (grazerNames.test(an) && predatorNames.test(bn)) return link("+-", "strong", "predation: predator benefits, prey is harmed", true);
  if (amphibianNames.test(an) && insectPredatorNames.test(bn)) return link("+-", "weak", "possible predator-prey link: amphibians may eat adult or larval insects");
  if (insectPredatorNames.test(an) && amphibianNames.test(bn)) return link("+-", "weak", "possible predator-prey link: amphibians may eat adult or larval insects", true);
  if (predatorNames.test(an) && smallPreyNames.test(bn)) return link("+-", "weak", "possible predator-prey dependency; confirm from local diet evidence");
  if (smallPreyNames.test(an) && predatorNames.test(bn)) return link("+-", "weak", "possible predator-prey dependency; confirm from local diet evidence", true);
  if (predatorNames.test(an) && pollinatorNames.test(bn)) return link("+-", "weak", "possible predation on insects");
  if (pollinatorNames.test(an) && predatorNames.test(bn)) return link("+-", "weak", "possible predation on insects", true);
  if (decomposerNames.test(an) && plantNames.test(bn)) return link("0+", "weak", "nutrient cycling can support plant growth");
  if (plantNames.test(an) && decomposerNames.test(bn)) return link("0+", "weak", "litter and roots feed decomposer pathway");
  if (decomposerNames.test(an) && grazerNames.test(bn)) return link("0+", "weak", "soil and litter processing may indirectly improve food-plant quality for grazers");
  if (grazerNames.test(an) && decomposerNames.test(bn)) return link("0+", "weak", "soil and litter processing may indirectly improve food-plant quality for grazers", true);
  if (largeBirdNames.test(an) && smallBirdNames.test(bn)) return link("0-", "weak", "possible disturbance or avoidance pressure without clear benefit to the larger species");
  if (smallBirdNames.test(an) && largeBirdNames.test(bn)) return link("0-", "weak", "possible disturbance or avoidance pressure without clear benefit to the larger species", true);
  if (largeBirdNames.test(an) && grazerNames.test(bn)) return link("0-", "weak", "possible disturbance, displacement, or avoidance pressure; field evidence needed");
  if (grazerNames.test(an) && largeBirdNames.test(bn)) return link("0-", "weak", "possible disturbance, displacement, or avoidance pressure; field evidence needed", true);
  if (a.roles.some(role => b.roles.includes(role))) return link("--", "weak", "possible competition within a similar functional niche");
  if (a.module === b.module) return link("00", "weak", "shared habitat; direct interaction not established");
  return link("00", "weak", "no direct relation inferred; field evidence needed");
}

function link(type, strength, note, reverse = false) {
  const effect = {
    "++": ["positive", "positive"],
    "+-": ["positive", "negative"],
    "0+": ["neutral", "positive"],
    "0-": ["neutral", "negative"],
    "--": ["negative", "negative"],
    "00": ["neutral", "neutral"]
  }[type];
  return reverse
    ? { type, strength, note, sourceEffect: effect[1], targetEffect: effect[0] }
    : { type, strength, note, sourceEffect: effect[0], targetEffect: effect[1] };
}

function applySpeciesOverride(item) {
  const override = manualEdits.species[speciesKey(item.name)];
  return override ? { ...item, ...override } : item;
}

function applyPairOverride(a, b, inferred) {
  const override = manualEdits.pairs[pairNameKey(a.name, b.name)];
  if (!override) return inferred;
  const sourceIsA = speciesKey(a.name) === speciesKey(override.a);
  const sourceEffect = sourceIsA ? override.aEffect : override.bEffect;
  const targetEffect = sourceIsA ? override.bEffect : override.aEffect;
  return {
    type: relationTypeFromEffects(sourceEffect, targetEffect),
    strength: override.strength,
    note: `${override.note} (manual correction)`,
    sourceEffect,
    targetEffect
  };
}

function relationFromEffects(aEffect, bEffect, strength, note) {
  return {
    type: relationTypeFromEffects(aEffect, bEffect),
    strength,
    note,
    sourceEffect: aEffect,
    targetEffect: bEffect
  };
}

function relationTypeFromEffects(aEffect, bEffect) {
  return `${signForEffect(aEffect)}${signForEffect(bEffect)}`;
}

function renderAll() {
  renderRoles();
  renderModules();
  renderNetwork();
  renderMatrix();
  renderSources();
  renderEditControls();
}

function renderRoles() {
  els.roleGrid.innerHTML = Object.entries(roles).map(([key, role]) => {
    const members = species.filter(item => item.roles.includes(key));
    return `
      <article class="role-card">
        <header style="background:${role.color}">
          <h2>${role.title}</h2>
          <p>${members.length} species · ${role.subtitle}</p>
        </header>
        <div class="species-list">
          ${members.map(speciesPill).join("") || "<p class='empty'>No species assigned yet.</p>"}
        </div>
      </article>`;
  }).join("");
}

function renderModules() {
  const grouped = groupBy(species, item => item.module);
  els.moduleGrid.innerHTML = Object.entries(grouped).map(([name, members]) => `
    <article class="module-card">
      <header style="background:#246a73">
        <h2>${name}</h2>
        <p>${members.length} species in a highly connected learning block</p>
      </header>
      <div class="species-list">${members.map(speciesPill).join("")}</div>
    </article>
  `).join("");
}

function speciesPill(item) {
  return `<article class="species-pill">
    <span class="species-icon ${speciesIconType(item)}" aria-hidden="true">${speciesIconSvg(item)}</span>
    <span>
      <strong><em>${escapeHtml(item.name)}</em></strong>
      <small>${item.subfunctions.join(" · ")}</small>
    </span>
  </article>`;
}

function renderNetwork() {
  if (!species.length) {
    els.network.innerHTML = "<p class='empty-state'>Upload a CSV or load species.csv to draw the interaction web.</p>";
    return;
  }
  if (simulation) simulation.stop();
  const requestedSize = Number(els.size.value);
  const width = Math.max(els.network.clientWidth || 900, requestedSize);
  const height = Math.round(requestedSize * 0.7);
  els.network.style.setProperty("--network-width", `${width}px`);
  els.network.style.setProperty("--network-height", `${height}px`);
  const nodes = species.map(item => ({ ...item }));
  const showWeak = els.showWeak.checked;
  const showNeutral = els.showNeutral.checked;
  const links = interactions
    .filter(link => (showWeak || link.strength === "strong") && (showNeutral || link.type !== "00"))
    .map(link => ({ ...link }));

  els.network.innerHTML = "";
  const svg = d3.select(els.network).append("svg").attr("viewBox", [0, 0, width, height]);
  svg.append("defs").selectAll("marker")
    .data(["positive", "negative", "neutral"])
    .enter()
    .append("marker")
    .attr("id", d => `arrow-${d}`)
    .attr("viewBox", "0 -5 10 10")
    .attr("refX", 21)
    .attr("refY", 0)
    .attr("markerWidth", 4.8)
    .attr("markerHeight", 4.8)
    .attr("orient", "auto")
    .append("path")
    .attr("d", "M0,-5L10,0L0,5")
    .attr("fill", d => effectColor(d));

  const linkGroup = svg.append("g").attr("class", "links");
  const forward = linkGroup.selectAll("path.forward").data(links).enter().append("path")
    .attr("fill", "none")
    .attr("stroke", d => effectColor(d.targetEffect))
    .attr("stroke-width", d => d.strength === "strong" ? 3.2 : 1.25)
    .attr("stroke-opacity", d => d.type === "00" ? 0.25 : 0.72)
    .attr("marker-end", d => `url(#arrow-${d.targetEffect})`);

  const backward = linkGroup.selectAll("path.backward").data(links).enter().append("path")
    .attr("fill", "none")
    .attr("stroke", d => effectColor(d.sourceEffect))
    .attr("stroke-width", d => d.strength === "strong" ? 3.2 : 1.25)
    .attr("stroke-opacity", d => d.type === "00" ? 0.25 : 0.72)
    .attr("marker-end", d => `url(#arrow-${d.sourceEffect})`);

  const node = svg.append("g").selectAll("g").data(nodes).enter().append("g").attr("class", "node");
  node.append("circle")
    .attr("r", d => d.roles.includes("producer") ? 16 : d.roles.includes("higherConsumer") ? 14 : 12)
    .attr("fill", d => roles[d.roles[0]]?.color || "#7c8791")
    .attr("stroke", "white")
    .attr("stroke-width", 2.4);
  node.append("text").attr("x", 20).attr("y", 4).text(d => d.name);
  node.append("title").text(d => `${d.name}\n${d.subfunctions.join(", ")}`);

  simulation = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(links).id(d => d.id).distance(d => d.strength === "strong" ? 110 : 165).strength(d => d.strength === "strong" ? 0.35 : 0.08))
    .force("charge", d3.forceManyBody().strength(Number(els.charge.value)))
    .force("center", d3.forceCenter(width / 2, height / 2))
    .force("collision", d3.forceCollide(44))
    .on("tick", () => {
      forward.attr("d", d => curvePath(d.source, d.target, 15));
      backward.attr("d", d => curvePath(d.target, d.source, -15));
      node.attr("transform", d => `translate(${d.x},${d.y})`);
    });

  node.call(d3.drag()
    .on("start", event => {
      if (!event.active) simulation.alphaTarget(0.3).restart();
      event.subject.fx = event.subject.x;
      event.subject.fy = event.subject.y;
    })
    .on("drag", event => {
      event.subject.fx = event.x;
      event.subject.fy = event.y;
    })
    .on("end", event => {
      if (!event.active) simulation.alphaTarget(0);
      event.subject.fx = null;
      event.subject.fy = null;
    }));
}

function curvePath(source, target, bend) {
  const dx = target.x - source.x;
  const dy = target.y - source.y;
  const dr = Math.sqrt(dx * dx + dy * dy) * 1.55;
  return `M${source.x},${source.y}A${dr + bend},${dr + bend} 0 0,1 ${target.x},${target.y}`;
}

function renderMatrix() {
  if (!species.length) {
    els.simpleMatrix.innerHTML = "<tr><td class='empty-state'>Upload a CSV or load species.csv to build the matrix.</td></tr>";
    els.matrix.innerHTML = "<tr><td class='empty-state'>Detailed pair evidence will appear here.</td></tr>";
    return;
  }
  const byPair = new Map();
  interactions.forEach(link => {
    byPair.set(pairKey(link.source, link.target), link);
  });
  const simpleHead = `<tr><th>Species</th>${species.map(s => `<th>${speciesNameLabel(s)}</th>`).join("")}</tr>`;
  const simpleRows = species.map(row => {
    const cells = species.map(col => {
      if (row.id === col.id) return "<td class='self-cell'>self</td>";
      const link = byPair.get(pairKey(row.id, col.id));
      if (!link) return "<td></td>";
      const pair = effectPairForRow(row.id, link);
      return `<td><span class="big-symbol ${symbolClass(pair)}">${formatPair(pair)}</span></td>`;
    }).join("");
    return `<tr><td>${speciesNameLabel(row)}</td>${cells}</tr>`;
  }).join("");
  els.simpleMatrix.innerHTML = simpleHead + simpleRows;

  const head = `<tr><th>Species</th>${species.map(s => `<th>${speciesNameLabel(s)}</th>`).join("")}</tr>`;
  const rows = species.map(row => {
    const cells = species.map(col => {
      if (row.id === col.id) return "<td>self</td>";
      const link = byPair.get(pairKey(row.id, col.id));
      if (!link) return "<td></td>";
      const pair = effectPairForRow(row.id, link);
      return `<td><strong class="big-symbol ${symbolClass(pair)}">${formatPair(pair)}</strong><br><small>${link.strength}<br>${escapeHtml(link.note)}</small></td>`;
    }).join("");
    return `<tr><td>${speciesNameLabel(row)}</td>${cells}</tr>`;
  }).join("");
  els.matrix.innerHTML = head + rows;
}

function pairKey(a, b) {
  return [a, b].sort((left, right) => Number(left.slice(1)) - Number(right.slice(1))).join("|");
}

function effectPairForRow(rowId, link) {
  const sourceSign = signForEffect(link.sourceEffect);
  const targetSign = signForEffect(link.targetEffect);
  return rowId === link.source ? `${sourceSign}${targetSign}` : `${targetSign}${sourceSign}`;
}

function signForEffect(effect) {
  return { positive: "+", negative: "-", neutral: "0" }[effect] || "0";
}

function formatPair(pair) {
  return pair.split("").map(char => `<span class="${char === "0" ? "zero-char" : ""}">${char}</span>`).join("");
}

function symbolClass(pair) {
  if (pair.includes("+") && pair.includes("-")) return "mixed-symbol";
  if (pair.includes("+")) return "positive-symbol";
  if (pair.includes("-")) return "negative-symbol";
  return "neutral-symbol";
}

function renderSources() {
  if (!species.length) {
    els.sources.innerHTML = "<article class='source-card'><h3>No species loaded</h3><p>Upload a CSV or load species.csv, then press Consult internet. Progress will appear in the status bar above.</p></article>";
    return;
  }
  els.sources.innerHTML = species.map(item => `
    <article class="source-card">
      <h3>${speciesNameLabel(item)}</h3>
      <p>${escapeHtml(item.summary)}</p>
      ${item.source ? `<a href="${item.source}" target="_blank" rel="noreferrer">Open source</a>` : ""}
    </article>
  `).join("");
}

function renderEditControls() {
  const speciesOptions = species.map(item => `<option value="${item.id}">${escapeHtml(item.name)}</option>`).join("");
  els.editSpecies.innerHTML = speciesOptions;
  els.editPairA.innerHTML = speciesOptions;
  els.editPairB.innerHTML = speciesOptions;
  if (species.length > 1 && els.editPairA.value === els.editPairB.value) {
    els.editPairB.selectedIndex = 1;
  }
  syncSpeciesEditor();
  syncPairEditor();
  renderManualEditList();
}

function syncSpeciesEditor() {
  const item = species.find(entry => entry.id === els.editSpecies.value);
  const disabled = !item;
  [els.editSubfunctions, els.editGuild, els.editModule, els.saveSpeciesEdit, els.resetSpeciesEdit].forEach(control => {
    control.disabled = disabled;
  });
  els.editRoleChecks.querySelectorAll("input").forEach(input => {
    input.disabled = disabled;
    input.checked = item ? item.roles.includes(input.value) : false;
  });
  els.editSubfunctions.value = item ? item.subfunctions.join(", ") : "";
  els.editGuild.value = item?.guild || "";
  els.editModule.value = item?.module || "";
}

function syncPairEditor() {
  const a = species.find(entry => entry.id === els.editPairA.value);
  const b = species.find(entry => entry.id === els.editPairB.value);
  const disabled = !a || !b || a.id === b.id;
  [els.editEffectAB, els.editEffectBA, els.editStrength, els.editPairNote, els.savePairEdit, els.resetPairEdit].forEach(control => {
    control.disabled = disabled;
  });
  if (disabled) {
    els.editPairNote.value = "";
    return;
  }
  const link = interactions.find(entry => pairKey(entry.source, entry.target) === pairKey(a.id, b.id));
  const sourceIsA = link?.source === a.id;
  els.editEffectAB.value = sourceIsA ? link.sourceEffect : link.targetEffect;
  els.editEffectBA.value = sourceIsA ? link.targetEffect : link.sourceEffect;
  els.editStrength.value = link?.strength || "weak";
  els.editPairNote.value = link?.note || "";
}

function saveSpeciesCorrection() {
  const item = species.find(entry => entry.id === els.editSpecies.value);
  if (!item) return;
  const rolesSelected = [...els.editRoleChecks.querySelectorAll("input:checked")].map(input => input.value);
  const correction = {
    roles: rolesSelected.length ? rolesSelected : item.roles,
    subfunctions: splitList(els.editSubfunctions.value),
    guild: els.editGuild.value.trim() || item.guild,
    module: els.editModule.value.trim() || item.module
  };
  manualEdits.species[speciesKey(item.name)] = correction;
  Object.assign(item, correction);
  interactions = buildInteractions(species);
  saveManualEdits();
  renderAll();
  setStatus("good", `Saved manual correction for ${item.name}.`);
}

function resetSpeciesCorrection() {
  const item = species.find(entry => entry.id === els.editSpecies.value);
  if (!item) return;
  delete manualEdits.species[speciesKey(item.name)];
  const restored = applySpeciesOverride(classifySpecies(item.name, Number(item.id.slice(1))));
  Object.assign(item, restored);
  interactions = buildInteractions(species);
  saveManualEdits();
  renderAll();
  setStatus("good", `Reset manual species correction for ${item.name}.`);
}

function savePairCorrection() {
  const a = species.find(entry => entry.id === els.editPairA.value);
  const b = species.find(entry => entry.id === els.editPairB.value);
  if (!a || !b || a.id === b.id) return;
  const override = relationFromEffects(els.editEffectAB.value, els.editEffectBA.value, els.editStrength.value, els.editPairNote.value.trim() || "manual correction");
  manualEdits.pairs[pairNameKey(a.name, b.name)] = {
    a: a.name,
    b: b.name,
    aEffect: els.editEffectAB.value,
    bEffect: els.editEffectBA.value,
    strength: els.editStrength.value,
    note: override.note
  };
  interactions = buildInteractions(species);
  saveManualEdits();
  renderAll();
  setStatus("good", `Saved manual interaction correction for ${a.name} and ${b.name}.`);
}

function resetPairCorrection() {
  const a = species.find(entry => entry.id === els.editPairA.value);
  const b = species.find(entry => entry.id === els.editPairB.value);
  if (!a || !b || a.id === b.id) return;
  delete manualEdits.pairs[pairNameKey(a.name, b.name)];
  interactions = buildInteractions(species);
  saveManualEdits();
  renderAll();
  setStatus("good", `Reset manual pair correction for ${a.name} and ${b.name}.`);
}

function clearManualCorrections() {
  manualEdits = { species: {}, pairs: {} };
  saveManualEdits();
  species = species.map((item, index) => classifySpecies(item.name, index));
  interactions = buildInteractions(species);
  renderAll();
  setStatus("good", "Cleared all manual corrections.");
}

function renderManualEditList() {
  const speciesCorrections = Object.entries(manualEdits.species);
  const pairCorrections = Object.entries(manualEdits.pairs);
  if (!speciesCorrections.length && !pairCorrections.length) {
    els.manualEditList.innerHTML = "<p class='empty-state'>No manual corrections saved yet.</p>";
    return;
  }
  const speciesItems = speciesCorrections.map(([key, edit]) => `<li><strong>${escapeHtml(key)}</strong>: ${edit.roles.map(role => roles[role]?.title || role).join(", ")}; ${escapeHtml(edit.subfunctions.join(", "))}</li>`).join("");
  const pairItems = pairCorrections.map(([, edit]) => `<li><strong>${escapeHtml(edit.a)}</strong> / <strong>${escapeHtml(edit.b)}</strong>: ${signForEffect(edit.aEffect)}${signForEffect(edit.bEffect)}, ${escapeHtml(edit.strength)}; ${escapeHtml(edit.note)}</li>`).join("");
  els.manualEditList.innerHTML = `
    ${speciesItems ? `<h3>Species</h3><ul>${speciesItems}</ul>` : ""}
    ${pairItems ? `<h3>Pairs</h3><ul>${pairItems}</ul>` : ""}
  `;
}

function speciesNameLabel(item) {
  return `<span class="species-label"><span class="species-icon ${speciesIconType(item)}" aria-hidden="true">${speciesIconSvg(item)}</span><em>${escapeHtml(item.name)}</em></span>`;
}

function speciesIconType(item) {
  const name = item.name.toLowerCase();
  if (/pelophylax|lissotriton|rana|frog|newt/.test(name)) return "icon-frog";
  if (/pieris|lycaena|inachis|iphiclides|butterfly|moth/.test(name)) return "icon-butterfly";
  if (/lumbricus|earthworm/.test(name)) return "icon-worm";
  if (/helix|helicella|snail|slug/.test(name)) return "icon-snail";
  if (/carabus|coccinella|callopteryx|calopteryx|beetle|dragonfly|damselfly/.test(name)) return "icon-insect";
  if (/potamon|crab/.test(name)) return "icon-crab";
  if (/parus|pica|corvus|passer|egretta|bird|sparrow|tit|crow|magpie|egret|heron/.test(name)) return "icon-bird";
  if (/apodemus|mouse|rodent/.test(name)) return "icon-mouse";
  if (item.roles.includes("producer") || plantNames.test(item.name)) return "icon-plant";
  if (item.roles.includes("decomposer")) return "icon-soil";
  return "icon-generic";
}

function speciesIconSvg(item) {
  const type = speciesIconType(item);
  const icons = {
    "icon-frog": `<svg viewBox="0 0 64 64" role="img"><path d="M12 35c0-12 9-22 20-22s20 10 20 22c0 10-8 17-20 17s-20-7-20-17Z"/><circle cx="22" cy="21" r="8"/><circle cx="42" cy="21" r="8"/><circle cx="22" cy="21" r="3" fill="white"/><circle cx="42" cy="21" r="3" fill="white"/><path d="M23 38c5 4 13 4 18 0" fill="none" stroke="white" stroke-width="4" stroke-linecap="round"/></svg>`,
    "icon-butterfly": `<svg viewBox="0 0 64 64" role="img"><path d="M31 31C18 7 3 14 8 31c4 13 16 13 23 4v17h2V35c7 9 19 9 23-4 5-17-10-24-23 0V14h-2v17Z"/></svg>`,
    "icon-worm": `<svg viewBox="0 0 64 64" role="img"><path d="M8 42c8-18 17 10 28-6 7-10 10-20 20-11" fill="none" stroke="currentColor" stroke-width="10" stroke-linecap="round"/><circle cx="55" cy="25" r="2" fill="white"/></svg>`,
    "icon-snail": `<svg viewBox="0 0 64 64" role="img"><path d="M7 45h43c6 0 8-4 8-8 0-6-5-10-10-10h-4"/><circle cx="27" cy="34" r="15" fill="none" stroke="currentColor" stroke-width="8"/><circle cx="27" cy="34" r="5"/><path d="M48 27l5-11M53 27l8-8" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round"/></svg>`,
    "icon-insect": `<svg viewBox="0 0 64 64" role="img"><ellipse cx="32" cy="34" rx="11" ry="18"/><circle cx="32" cy="16" r="8"/><path d="M21 26 9 18M43 26l12-8M21 36H7M43 36h14M22 46 10 56M42 46l12 10" fill="none" stroke="currentColor" stroke-width="5" stroke-linecap="round"/></svg>`,
    "icon-crab": `<svg viewBox="0 0 64 64" role="img"><ellipse cx="32" cy="38" rx="16" ry="11"/><circle cx="24" cy="29" r="3" fill="white"/><circle cx="40" cy="29" r="3" fill="white"/><path d="M17 37 6 29M47 37l11-8M20 45 9 52M44 45l11 7M18 28 8 17M46 28l10-11" fill="none" stroke="currentColor" stroke-width="5" stroke-linecap="round"/><circle cx="7" cy="16" r="5"/><circle cx="57" cy="16" r="5"/></svg>`,
    "icon-bird": `<svg viewBox="0 0 64 64" role="img"><path d="M9 39c16 3 20-18 40-18-3 13-13 25-30 25H9Z"/><path d="M45 23l14-5-11 10Z"/><circle cx="43" cy="22" r="2" fill="white"/><path d="M27 45v9M34 44v10" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round"/></svg>`,
    "icon-mouse": `<svg viewBox="0 0 64 64" role="img"><ellipse cx="34" cy="37" rx="19" ry="13"/><circle cx="19" cy="28" r="8"/><circle cx="44" cy="27" r="5"/><circle cx="48" cy="33" r="2" fill="white"/><path d="M15 39C4 38 2 48 10 53" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round"/></svg>`,
    "icon-plant": `<svg viewBox="0 0 64 64" role="img"><path d="M32 55V20" fill="none" stroke="currentColor" stroke-width="6" stroke-linecap="round"/><path d="M32 30C17 30 12 18 15 9c12 0 18 8 17 21ZM32 39c15 0 20-12 17-21-12 0-18 8-17 21Z"/></svg>`,
    "icon-soil": `<svg viewBox="0 0 64 64" role="img"><path d="M10 44c8-7 14-7 22 0s14 7 22 0v10H10Z"/><circle cx="18" cy="31" r="5"/><circle cx="32" cy="24" r="4"/><circle cx="46" cy="32" r="5"/></svg>`,
    "icon-generic": `<svg viewBox="0 0 64 64" role="img"><circle cx="32" cy="32" r="20"/><path d="M20 33h24M32 21v24" stroke="white" stroke-width="5" stroke-linecap="round"/></svg>`
  };
  return icons[type] || icons["icon-generic"];
}

async function enrichFromInternet() {
  if (!species.length) {
    setStatus("", "Load a species list first.");
    return;
  }
  setStatus("busy", "Consulting Wikipedia summaries for ecological evidence...");
  setProgress(0, species.length, true);
  els.enrich.disabled = true;
  for (let i = 0; i < species.length; i += 1) {
    const item = species[i];
    setStatus("busy", `Consulting internet evidence ${i + 1}/${species.length}: ${item.name}`);
    setProgress(i, species.length, true, `Loading ${i + 1} / ${species.length}`);
    const evidence = await wikipediaSummary(item.name);
    if (evidence) {
      item.summary = evidence.extract;
      item.source = evidence.url;
      improveClassificationFromText(item, evidence.extract);
    } else {
      item.summary = "No direct Wikipedia summary was found. Keep this species in the field-observation queue.";
      item.source = `https://www.google.com/search?q=${encodeURIComponent(item.name + " ecology trophic role")}`;
    }
    renderRoles();
    renderModules();
    renderSources();
    setProgress(i + 1, species.length, true, `${i + 1} / ${species.length} notes loaded`);
    await delay(180);
  }
  interactions = buildInteractions(species);
  renderNetwork();
  renderMatrix();
  setStatus("good", "Internet consultation complete. Review uncertain species and correct roles if field evidence suggests a better pattern.");
  setProgress(species.length, species.length, true, `${species.length} / ${species.length} notes checked`);
  els.enrich.disabled = false;
}

async function wikipediaSummary(name) {
  const lookup = normalizeLookupName(name);
  const title = encodeURIComponent(toTitleCase(lookup));
  const endpoint = `https://en.wikipedia.org/w/api.php?action=query&prop=extracts%7Cinfo&exintro=1&explaintext=1&redirects=1&format=json&origin=*&inprop=url&titles=${title}`;
  try {
    const response = await fetch(endpoint);
    if (!response.ok) return wikipediaSearchSummary(lookup);
    const data = await response.json();
    const page = firstWikiPage(data);
    if (!page?.extract || page.missing !== undefined) return wikipediaSearchSummary(lookup);
    return { extract: page.extract, url: page.fullurl || `https://en.wikipedia.org/wiki/${title}` };
  } catch {
    return wikipediaSearchSummary(lookup);
  }
}

async function wikipediaSearchSummary(name) {
  const query = encodeURIComponent(name.replace(/\bsp\.\b/i, "").trim());
  const searchUrl = `https://en.wikipedia.org/w/api.php?action=opensearch&search=${query}&limit=1&namespace=0&format=json&origin=*`;
  try {
    const response = await fetch(searchUrl);
    if (!response.ok) return null;
    const data = await response.json();
    const title = data?.[1]?.[0];
    if (!title) return null;
    const summary = await fetch(`https://en.wikipedia.org/w/api.php?action=query&prop=extracts%7Cinfo&exintro=1&explaintext=1&redirects=1&format=json&origin=*&inprop=url&titles=${encodeURIComponent(title)}`);
    if (!summary.ok) return null;
    const page = firstWikiPage(await summary.json());
    if (!page?.extract || page.missing !== undefined) return null;
    return { extract: page.extract, url: page.fullurl || data?.[3]?.[0] };
  } catch {
    return null;
  }
}

function firstWikiPage(data) {
  const pages = data?.query?.pages;
  if (!pages) return null;
  return Object.values(pages)[0] || null;
}

function normalizeLookupName(name) {
  return name
    .replace(/Callopterix/i, "Calopteryx")
    .replace(/coccinella semptempunctata/i, "Coccinella septempunctata")
    .replace(/Armadillium/i, "Armadillidium")
    .replace(/triticum vulgare/i, "Triticum aestivum");
}

function improveClassificationFromText(item, text) {
  const lower = text.toLowerCase();
  const addRoles = [];
  const addSubs = [];
  if (/plant|tree|shrub|rose|wheat|flower|fruit/.test(lower)) addRoles.push("producer");
  if (/pollinat|nectar|butterfly|flower/.test(lower)) addSubs.push("pollinator");
  if (/decompos|detrit|soil|litter|earthworm|isopod/.test(lower)) addRoles.push("decomposer");
  if (/predator|preys|carnivor|insectivor|larvae feed on insects/.test(lower)) addRoles.push("higherConsumer");
  if (/herbivor|feeds on plants|graz/.test(lower)) addRoles.push("primaryConsumer");
  item.roles = [...new Set([...item.roles, ...addRoles])];
  item.subfunctions = [...new Set([...item.subfunctions, ...addSubs])];
  Object.assign(item, applySpeciesOverride(item));
}

function groupBy(items, getter) {
  return items.reduce((groups, item) => {
    const key = getter(item);
    groups[key] ||= [];
    groups[key].push(item);
    return groups;
  }, {});
}

function effectColor(effect) {
  return { positive: "#239b56", negative: "#c84635", neutral: "#7c8791" }[effect] || "#7c8791";
}

function toTitleCase(value) {
  return value.split(/\s+/).map(part => part ? part[0].toUpperCase() + part.slice(1).toLowerCase() : part).join(" ");
}

function splitList(value) {
  return value.split(",").map(item => item.trim()).filter(Boolean);
}

function speciesKey(name) {
  return name.trim().toLowerCase();
}

function pairNameKey(a, b) {
  return [speciesKey(a), speciesKey(b)].sort().join(" | ");
}

function loadManualEdits() {
  try {
    const stored = JSON.parse(localStorage.getItem("ecosystemManualEdits") || "{}");
    return { species: stored.species || {}, pairs: stored.pairs || {} };
  } catch {
    return { species: {}, pairs: {} };
  }
}

function saveManualEdits() {
  localStorage.setItem("ecosystemManualEdits", JSON.stringify(manualEdits));
}

function setStatus(kind, text) {
  els.statusDot.className = kind;
  els.statusText.textContent = text;
}

function setProgress(done, total, visible, label = null) {
  els.progressWrap.hidden = !visible;
  const percent = total ? Math.round((done / total) * 100) : 0;
  els.progressBar.style.width = `${percent}%`;
  els.progressText.textContent = label || `${done} / ${total}`;
}

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, char => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;"
  }[char]));
}

renderAll();
