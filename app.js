(function () {
  let specimens = mergeCustomSpecimens();
  let regions = buildRegions();
  let occurrences = buildOccurrences();
  const ranks = ["phylum", "class", "order", "family", "genus"];
  const beginnerRanks = ["phylum", "class", "order", "family"];
  const teacherGalleryKey = "taxonomy2026";
  const rankLabels = {
    phylum: "Phylum",
    class: "Class",
    order: "Order",
    family: "Family",
    genus: "Genus",
    species: "Species"
  };

  const treeRankOrder = ["phylum", "class", "order", "family", "genus", "species"];
  const phylumGroups = {
    Arthropoda: "Protostomia",
    Mollusca: "Protostomia",
    Annelida: "Protostomia",
    Nematoda: "Protostomia",
    Chordata: "Deuterostomia",
    Echinodermata: "Deuterostomia",
    Hemichordata: "Deuterostomia",
    Cnidaria: "Radiata",
    Ctenophora: "Radiata",
    Porifera: "Porifera",
    Tracheophyta: "Plants",
    Bryophyta: "Plants",
    Ascomycota: "Fungi",
    Basidiomycota: "Fungi"
  };

  let quizSpecimen = null;
  let quizQueue = [];
  let answered = new Set();
  let quizPool = [];
  let quizResults = [];
  let identificationResults = [];
  let identifyPool = [];
  let identifyIndex = 0;
  let selectedIdentification = "";
  let geographyChecks = [];
  let treeClusterIndex = 0;
  let selectedBranches = [];
  let treeFailed = false;
  let activeBranches = [];
  let completedClusters = [];
  let galleryNamesUnlocked = false;
  let candidateRequestId = 0;
  const candidateCache = {};

  const el = (id) => document.getElementById(id);

  function customSpecimens() {
    try {
      return JSON.parse(localStorage.getItem("taxonomyTrainerCustomSpecimens") || "[]");
    } catch {
      return [];
    }
  }

  function mergeCustomSpecimens() {
    const base = window.TAXONOMY_SPECIMENS || [];
    const custom = customSpecimens();
    const byId = new Map(base.map((item) => [item.id, item]));
    custom.forEach((item) => byId.set(item.id, item));
    return [...byId.values()];
  }

  function buildOccurrences() {
    const result = { ...(window.TAXONOMY_OCCURRENCES || {}) };
    (window.TAXONOMY_SPECIMENS || []).concat(customSpecimens()).forEach((specimen) => {
      const listedRegions = specimen.regions || [];
      [specimen.taxonomy?.species, ...(specimen.candidates || [])].filter(Boolean).forEach((name) => {
        result[name] = unique([...(result[name] || []), ...listedRegions]);
      });
    });
    return result;
  }

  function buildRegions() {
    return unique([
      ...(window.TAXONOMY_REGIONS || []),
      ...(window.TAXONOMY_SPECIMENS || []).concat(customSpecimens()).flatMap((specimen) => [
        ...(specimen.regions || []),
        specimen.pictureRegion,
        specimen.studentRegion
      ].filter(Boolean))
    ]);
  }

  function shuffle(items) {
    return [...items].sort(() => Math.random() - 0.5);
  }

  function unique(values) {
    return [...new Set(values)];
  }

  function normalizeName(value) {
    return (value || "").trim().replace(/\s+/g, " ");
  }

  function activeSpecimenIds() {
    try {
      const localIds = JSON.parse(localStorage.getItem("taxonomyTrainerActiveSpecimens") || "[]");
      if (localIds.length) return localIds;
    } catch {
      return [];
    }
    return Array.isArray(window.TAXONOMY_ACTIVE_SET) ? window.TAXONOMY_ACTIVE_SET : [];
  }

  function localActiveSpecimenIds() {
    try {
      return JSON.parse(localStorage.getItem("taxonomyTrainerActiveSpecimens") || "[]");
    } catch {
      return [];
    }
  }

  function setActiveSpecimenIds(ids) {
    localStorage.setItem("taxonomyTrainerActiveSpecimens", JSON.stringify(unique(ids)));
  }

  function taskSpecimens() {
    const ids = activeSpecimenIds();
    if (!ids.length) return specimens;
    const active = specimens.filter((specimen) => ids.includes(specimen.id));
    return active.length ? active : specimens;
  }

  function choicesFor(rank, specimen) {
    const correct = specimen.taxonomy[rank];
    const extras = window.TAXONOMY_DISTRACTORS?.[rank] || [];
    const sameRankPool = unique([...taskSpecimens().map((item) => item.taxonomy[rank]).filter(Boolean), ...extras]);
    const mixedRankPool = unique(ranks
      .filter((otherRank) => otherRank !== rank)
      .map((otherRank) => specimen.taxonomy[otherRank])
      .filter(Boolean));
    const distractors = unique([
      ...shuffle(mixedRankPool.filter((value) => value !== correct)).slice(0, 2),
      ...shuffle(sameRankPool.filter((value) => value !== correct)).slice(0, 4)
    ]).slice(0, 4);
    return shuffle([correct, ...distractors]);
  }

  function switchView(viewId) {
    document.querySelectorAll(".view").forEach((view) => view.classList.toggle("active", view.id === viewId));
    document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.view === viewId));
  }

  function startQuizSession() {
    quizPool = shuffle(taskSpecimens());
    quizResults = [];
    startNextQuizSpecimen();
  }

  function activeQuizRanks() {
    return el("student-level")?.value === "beginner" ? beginnerRanks : ranks;
  }

  function startNextQuizSpecimen() {
    if (!quizPool.length) {
      renderQuizEnd();
      return;
    }

    quizSpecimen = quizPool.shift();
    quizQueue = shuffle(activeQuizRanks());
    answered = new Set();
    el("quiz-image").src = quizSpecimen.image;
    el("quiz-image").alt = quizSpecimen.commonName;
    el("quiz-common").textContent = "Specimen image";
    el("quiz-feedback").textContent = "";
    el("quiz-feedback").className = "feedback";
    renderQuizSummary();
    renderRankStair();
    askNextRank();
  }

  function renderQuizEnd() {
    const failed = quizResults.filter((result) => !result.passed);
    el("quiz-title").textContent = "Quiz finished";
    el("quiz-question").textContent = `Misidentified pictures: ${failed.length} of ${quizResults.length}.`;
    el("quiz-options").innerHTML = `<button class="primary" id="restart-quiz">Restart quiz</button>`;
    el("quiz-progress").textContent = "done";
    el("quiz-feedback").className = failed.length ? "feedback bad" : "feedback good";
    el("quiz-feedback").textContent = failed.length
      ? "Some pictures were allocated incorrectly."
      : "All pictures were allocated correctly.";
    el("rank-stair").innerHTML = "";
    el("restart-quiz").addEventListener("click", startQuizSession);
    renderQuizSummary();
  }

  function askNextRank() {
    if (!quizQueue.length) {
      quizResults.push({ id: quizSpecimen.id, commonName: quizSpecimen.commonName, passed: true });
      el("quiz-title").textContent = "Taxonomic stair complete";
      el("quiz-question").textContent = "This picture passed. Moving to the next organism.";
      el("quiz-options").innerHTML = "";
      const quizRanks = activeQuizRanks();
      el("quiz-progress").textContent = `${quizRanks.length} / ${quizRanks.length}`;
      el("quiz-feedback").className = "feedback good";
      el("quiz-feedback").textContent = "Accepted full taxonomic stair for this picture.";
      renderQuizSummary();
      setTimeout(startNextQuizSpecimen, 1100);
      return;
    }

    const rank = quizQueue[0];
    el("quiz-title").textContent = `Which ${rankLabels[rank].toLowerCase()}?`;
    el("quiz-question").textContent = "One mistake fails this picture and the quiz moves to the next organism.";
    el("quiz-progress").textContent = `${answered.size} / ${activeQuizRanks().length}`;
    el("quiz-options").innerHTML = "";
    choicesFor(rank, quizSpecimen).forEach((choice) => {
      const button = document.createElement("button");
      button.className = "option";
      button.textContent = choice;
      button.addEventListener("click", () => answerRank(rank, choice, button));
      el("quiz-options").appendChild(button);
    });
  }

  function answerRank(rank, choice, button) {
    const correct = quizSpecimen.taxonomy[rank];
    const buttons = [...document.querySelectorAll(".option")];
    buttons.forEach((option) => {
      option.disabled = true;
      if (option.textContent === correct) option.classList.add("correct");
    });

    if (choice === correct) {
      answered.add(rank);
      quizQueue.shift();
      button.classList.add("correct");
      el("quiz-feedback").className = "feedback good";
      el("quiz-feedback").textContent = "Correct.";
      renderRankStair();
      setTimeout(askNextRank, 500);
      return;
    }

    button.classList.add("incorrect");
    quizResults.push({
      id: quizSpecimen.id,
      commonName: quizSpecimen.commonName,
      passed: false,
      failedRank: rank,
      expected: correct,
      selected: choice
    });
    el("quiz-feedback").className = "feedback bad";
    el("quiz-feedback").textContent = `Fail for this picture. Correct ${rankLabels[rank].toLowerCase()}: ${correct}. Moving to next organism.`;
    renderQuizSummary();
    setTimeout(startNextQuizSpecimen, 1500);
  }

  function renderQuizSummary() {
    const failed = quizResults.filter((result) => !result.passed).length;
    const passed = quizResults.filter((result) => result.passed).length;
    const remaining = quizPool.length + (quizSpecimen && quizQueue.length ? 1 : 0);
    el("quiz-summary").innerHTML = `
      <span class="stat-card good"><strong>${passed}</strong><small>Correct</small></span>
      <span class="stat-card bad"><strong>${failed}</strong><small>Incorrect</small></span>
      <span class="stat-card"><strong>${remaining}</strong><small>Remaining</small></span>
    `;
  }

  function renderRankStair() {
    el("rank-stair").innerHTML = activeQuizRanks().map((rank) => {
      const done = answered.has(rank);
      const value = done ? quizSpecimen.taxonomy[rank] : "hidden";
      return `<div class="rank-chip ${done ? "done" : ""}"><strong>${rankLabels[rank]}</strong>${value}</div>`;
    }).join("");
  }

  function renderIdentify() {
    const select = el("identify-specimen");
    select.innerHTML = taskSpecimens().map((item, index) => `<option value="${item.id}">Picture ${index + 1}</option>`).join("");
    el("region-filter").innerHTML = regions.map((region) => `<option value="${region}">${region}</option>`).join("");
    identifyPool = shuffle(taskSpecimens());
    identifyIndex = 0;
    select.addEventListener("change", () => {
      const index = identifyPool.findIndex((item) => item.id === select.value);
      identifyIndex = index >= 0 ? index : identifyIndex;
      updateIdentifyLinks();
    });
    el("validate-identification").addEventListener("click", validateIdentification);
    el("save-identification").addEventListener("click", saveIdentification);
    el("student-identification").addEventListener("input", () => {
      selectedIdentification = el("student-identification").value;
      el("identification-feedback").textContent = "";
    });
    showIdentifySpecimen();
    renderIdentificationSummary();
  }

  function selectedIdentifySpecimen() {
    return identifyPool[identifyIndex] || taskSpecimens().find((item) => item.id === el("identify-specimen").value) || taskSpecimens()[0];
  }

  function showIdentifySpecimen() {
    const specimen = selectedIdentifySpecimen();
    el("identify-specimen").value = specimen.id;
    el("identify-image").src = specimen.image;
    el("identify-image").alt = specimen.commonName;
    el("identify-common").textContent = "Specimen image";
    el("identify-position").textContent = `Picture ${Math.min(identifyIndex + 1, identifyPool.length)} of ${identifyPool.length}`;
    geographyChecks = [];
    renderGeographyChecks();
    updateIdentifyLinks();
  }

  function advanceIdentifySpecimen() {
    identifyIndex += 1;
    if (identifyIndex >= identifyPool.length) {
      identifyPool = shuffle(taskSpecimens());
      identifyIndex = 0;
    }
    showIdentifySpecimen();
  }

  function updateIdentifyLinks() {
    const specimen = selectedIdentifySpecimen();
    const query = encodeURIComponent(`${specimen.commonName} ${specimen.taxonomy.genus} ${specimen.taxonomy.family}`);
    el("google-search").href = `https://www.google.com/search?tbm=isch&q=${query}`;
    el("wiki-search").href = `https://en.wikipedia.org/wiki/${encodeURIComponent(specimen.taxonomy.genus)}`;
    el("candidate-list").innerHTML = "";
    renderCandidateButtons(localCandidateNames(specimen), "Closest gallery species");
    selectedIdentification = "";
    el("student-identification").value = "";
    el("identification-feedback").textContent = "";
  }

  function renderCandidateButtons(names, label) {
    el("candidate-list").innerHTML = names.length
      ? `<p class="mini-copy">${label}</p>`
      : "<p class=\"mini-copy\">No candidates available yet.</p>";
    names.forEach((name) => {
      const button = document.createElement("button");
      button.className = "candidate-item";
      button.innerHTML = `<i>${name}</i>`;
      button.addEventListener("click", () => {
        selectedIdentification = name;
        el("student-identification").value = name;
        el("identification-feedback").textContent = "";
      });
      el("candidate-list").appendChild(button);
    });
  }

  function localCandidateNames(specimen) {
    const pool = taskSpecimens().filter((item) => item.taxonomy?.species);
    const correct = specimen.taxonomy.species;
    const closest = pool
      .filter((item) => item.id !== specimen.id)
      .sort((a, b) => specimenDistanceScore(specimen, b) - specimenDistanceScore(specimen, a))
      .map((item) => item.taxonomy.species);
    return shuffle(unique([correct, ...closest]).slice(0, Math.min(10, pool.length)));
  }

  function specimenDistanceScore(left, right) {
    const weights = {
      phylum: 1,
      class: 2,
      order: 3,
      family: 5,
      genus: 8
    };
    return Object.entries(weights).reduce((score, [rank, weight]) => {
      return score + (left.taxonomy[rank] && left.taxonomy[rank] === right.taxonomy[rank] ? weight : 0);
    }, 0);
  }

  function validateIdentification() {
    const name = normalizeName(el("student-identification").value);
    const region = el("region-filter").value;
    if (geographyChecks.length >= 3) {
      const feedback = el("identification-feedback");
      feedback.className = "feedback bad";
      feedback.textContent = "Three geography checks are already used for this picture. Submit the final answer.";
      return lastGeographyCheck()?.valid || false;
    }
    const result = checkGeography(name, region);
    if (name) {
      geographyChecks.push(result);
      renderGeographyChecks();
    }
    return result.valid;
  }

  function checkGeography(name, region) {
    const knownRegions = occurrenceRegionsFor(name);
    const feedback = el("identification-feedback");
    const specimen = selectedIdentifySpecimen();

    if (!name) {
      feedback.className = "feedback bad";
      feedback.textContent = "Enter or select a species name first.";
      return { name, region, valid: false, message: feedback.textContent };
    }

    if (specimen.taxonomy.species.toLowerCase() === name.toLowerCase() && regionMatches(specimenRegions(specimen, knownRegions), region)) {
      feedback.className = "feedback good";
      feedback.textContent = `${name} is accepted for ${region} from this exercise record.`;
      return { name, region, valid: true, message: feedback.textContent };
    }

    if (!knownRegions) {
      const genusMatch = name.match(/^([A-Z][a-z-]+)\s+sp\.$/);
      if (genusMatch && genusIsPossibleInRegion(genusMatch[1], region)) {
        feedback.className = "feedback good";
        feedback.textContent = `${name} is plausible at genus level in ${region}.`;
        return { name, region, valid: true, message: feedback.textContent };
      }
      feedback.className = "feedback bad";
      feedback.textContent = `No local occurrence record for ${name}. Treat as unvalidated until you add a source-backed record.`;
      return { name, region, valid: false, message: feedback.textContent };
    }

    if (regionMatches(knownRegions, region)) {
      feedback.className = "feedback good";
      feedback.textContent = `${name} is marked as possible in ${region}.`;
      return { name, region, valid: true, message: feedback.textContent };
    }

    feedback.className = "feedback bad";
    feedback.textContent = `${name} is not marked as possible in ${region}. Listed regions: ${knownRegions.join(", ")}.`;
    return { name, region, valid: false, message: feedback.textContent };
  }

  function specimenRegions(specimen, knownRegions) {
    return unique([
      ...(specimen.regions || []),
      specimen.pictureRegion,
      specimen.studentRegion,
      ...(knownRegions || [])
    ].filter(Boolean));
  }

  function renderGeographyChecks() {
    const remaining = Math.max(0, 3 - geographyChecks.length);
    el("geography-check-log").innerHTML = `
      <strong>Geography checks</strong>
      <span>${remaining} remaining</span>
      ${geographyChecks.map((check, index) => `
        <div class="check-item ${check.valid ? "good" : "bad"}">
          ${index + 1}. <i>${check.name}</i> in ${check.region}: ${check.valid ? "possible" : "not confirmed"}
        </div>
      `).join("")}
    `;
  }

  function lastGeographyCheck() {
    return geographyChecks[geographyChecks.length - 1] || null;
  }

  function genusIsPossibleInRegion(genus, region) {
    return Object.entries(occurrences)
      .filter(([speciesName]) => speciesName.toLowerCase().startsWith(`${genus.toLowerCase()} `))
      .some(([, listedRegions]) => regionMatches(listedRegions, region));
  }

  function occurrenceRegionsFor(name) {
    const direct = occurrences[name];
    if (direct) return direct;
    const lower = name.toLowerCase();
    const key = Object.keys(occurrences).find((candidate) => candidate.toLowerCase() === lower);
    return key ? occurrences[key] : null;
  }

  function regionMatches(listedRegions, region) {
    const wanted = normalizeName(region).toLowerCase();
    return (listedRegions || []).some((listedRegion) => {
      const value = normalizeName(listedRegion).toLowerCase();
      return value === wanted || value.includes(wanted) || wanted.includes(value);
    });
  }

  function saveIdentification() {
    const specimen = selectedIdentifySpecimen();
    const name = normalizeName(el("student-identification").value) || "unrecorded";
    const region = el("region-filter").value || "region not specified";
    const directCheck = checkGeography(name, region);
    const matchingSavedCheck = geographyChecks.find((check) => check.name.toLowerCase() === name.toLowerCase() && check.region === region);
    const regionValid = (matchingSavedCheck || directCheck).valid;
    const verdict = document.querySelector("input[name='identification-verdict']:checked")?.value || "correct";
    const evaluation = evaluateIdentification(specimen, name, region, regionValid, verdict);
    identificationResults.push({
      specimenId: specimen.id,
      commonName: specimen.commonName,
      expected: specimen.taxonomy.species,
      selected: name,
      region,
      regionValid,
      verdict,
      correct: evaluation.score === 1,
      score: evaluation.score,
      outcome: evaluation.outcome
    });
    renderIdentificationSummary();
    const item = document.createElement("div");
    item.className = "note-item";
    item.innerHTML = `<strong>Picture result</strong><br><i>${name}</i><br>${region}<br>Final selection: ${verdict}<br>Outcome: ${evaluation.outcome}<br>Score: ${evaluation.score}<br>${regionValid ? "Region validation: pass" : "Region validation: fail or unvalidated"}`;
    el("identification-log").prepend(item);
    el("identification-feedback").className = evaluation.score ? "feedback good" : "feedback bad";
    el("identification-feedback").textContent = `Submitted: ${evaluation.outcome}. Moving to the next picture.`;
    setTimeout(advanceIdentifySpecimen, 800);
  }

  function evaluateIdentification(specimen, name, region, regionValid, verdict) {
    const normalized = name.toLowerCase();
    const exactSpecies = specimen.taxonomy.species.toLowerCase();
    const genusSp = `${specimen.taxonomy.genus.toLowerCase()} sp.`;
    const genusLevel = normalized === genusSp;

    if (verdict === "correct") {
      if (normalized === exactSpecies && regionValid) return { score: 1, outcome: "correct species" };
      if (genusLevel && regionValid) return { score: 0.5, outcome: "genus-level half credit" };
      return { score: 0, outcome: "incorrect" };
    }

    if (verdict === "incorrect") {
      return normalized !== exactSpecies || !regionValid
        ? { score: 1, outcome: "correctly rejected" }
        : { score: 0, outcome: "incorrect rejection" };
    }

    if (verdict === "unsure") {
      return normalized === genusSp && genusIsPossibleInRegion(specimen.taxonomy.genus, region)
        ? { score: 0.5, outcome: "genus-level half credit" }
        : { score: 0, outcome: "incorrect" };
    }

    return { score: 0, outcome: "incorrect" };
  }

  function renderIdentificationSummary() {
    const correct = identificationResults.filter((result) => result.score === 1).length;
    const half = identificationResults.filter((result) => result.score === 0.5).length;
    const incorrect = identificationResults.filter((result) => !result.score).length;
    const total = identificationResults.length;
    const points = identificationResults.reduce((sum, result) => sum + (result.score || 0), 0);
    const percent = total ? Math.round((points / total) * 100) : 0;
    el("identification-summary").innerHTML = `
      <span class="stat-card good"><strong>${correct}</strong><small>Correct</small></span>
      <span class="stat-card"><strong>${half}</strong><small>Half credit</small></span>
      <span class="stat-card bad"><strong>${incorrect}</strong><small>Incorrect</small></span>
      <span class="stat-card"><strong>${percent}%</strong><small>Species score</small></span>
    `;
  }

  function renderTreeGallery() {
    el("reset-tree").addEventListener("click", resetTreeTask);
    resetTreeTask();
  }

  function resetTreeTask() {
    treeClusterIndex = 1;
    selectedBranches = [];
    treeFailed = false;
    completedClusters = [];
    activeBranches = taskSpecimens().map((specimen, index) => ({
      id: branchLetter(index),
      label: branchLetter(index),
      specimenIds: [specimen.id],
      children: []
    }));
    renderTreeTask();
  }

  function branchLetter(index) {
    const letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
    if (index < letters.length) return letters[index];
    return `T${index + 1}`;
  }

  function renderTreeTask() {
    const complete = activeBranches.length === 1 && !treeFailed;
    el("tree-step").innerHTML = treeFailed
      ? "<strong>Task status: fail.</strong> Reset the tree and try again."
      : complete
        ? "<strong>Task status: success.</strong> The tree was built correctly."
        : "<strong>Cluster two active branches.</strong> Start with the closest tip branches, then cluster the closest higher-order branches until one final branch remains.";

    renderActiveBranches();
    renderTreeBoard();
    renderTreeFeedback();
  }

  function renderActiveBranches() {
    const complete = activeBranches.length === 1 && !treeFailed;
    el("tree-gallery").innerHTML = activeBranches.map((branch) => `
      <button class="tree-pick ${selectedBranches.includes(branch.id) ? "selected" : ""}" data-id="${branch.id}" ${treeFailed || complete ? "disabled" : ""}>
        ${renderBranchTile(branch)}
      </button>
    `).join("");

    document.querySelectorAll(".tree-pick").forEach((button) => {
      button.addEventListener("click", () => toggleBranchSelection(button.dataset.id));
    });
  }

  function renderBranchTile(branch) {
    const images = branch.specimenIds.map((id) => {
      const specimen = specimens.find((item) => item.id === id);
      return `<img src="${specimen.image}" alt="">`;
    }).join("");
    return `
      <div class="branch-label">Branch ${branch.label}</div>
      <div class="branch-images">${images}</div>
    `;
  }

  function toggleBranchSelection(id) {
    if (treeFailed || activeBranches.length === 1) return;
    if (selectedBranches.includes(id)) {
      selectedBranches = selectedBranches.filter((branchId) => branchId !== id);
    } else if (selectedBranches.length < 2) {
      selectedBranches.push(id);
    }
    renderTreeTask();
  }

  function clusterSelectedBranches() {
    if (treeFailed || activeBranches.length === 1 || selectedBranches.length !== 2) return;
    if (!isBestTreePair(selectedBranches)) {
      treeFailed = true;
      renderTreeTask();
      return;
    }

    const selected = activeBranches.filter((branch) => selectedBranches.includes(branch.id));
    const newLabel = `${String.fromCharCode(64 + treeClusterIndex)}${treeClusterIndex}`;
    const newBranch = {
      id: newLabel,
      label: newLabel,
      specimenIds: selected.flatMap((branch) => branch.specimenIds),
      children: selected
    };
    activeBranches = activeBranches.filter((branch) => !selectedBranches.includes(branch.id));
    activeBranches.push(newBranch);
    completedClusters.push(`Branch ${newLabel}`);
    treeClusterIndex += 1;
    selectedBranches = [];
    renderTreeTask();
  }

  function isBestTreePair(branchIds) {
    const selectedScore = branchScoreByIds(branchIds[0], branchIds[1]);
    const allScores = [];
    for (let i = 0; i < activeBranches.length; i += 1) {
      for (let j = i + 1; j < activeBranches.length; j += 1) {
        allScores.push(branchScore(activeBranches[i], activeBranches[j]));
      }
    }
    return selectedScore === Math.max(...allScores);
  }

  function branchScoreByIds(a, b) {
    return branchScore(
      activeBranches.find((branch) => branch.id === a),
      activeBranches.find((branch) => branch.id === b)
    );
  }

  function branchScore(a, b) {
    const scores = [];
    a.specimenIds.forEach((leftId) => {
      b.specimenIds.forEach((rightId) => {
        scores.push(specimenSimilarity(leftId, rightId));
      });
    });
    return scores.reduce((sum, score) => sum + score, 0) / scores.length;
  }

  function specimenSimilarity(a, b) {
    const left = specimens.find((item) => item.id === a);
    const right = specimens.find((item) => item.id === b);
    let score = 0;
    if (phylumGroup(left) && phylumGroup(left) === phylumGroup(right)) score += 2;
    return treeRankOrder.reduce((total, rank) => total + (left.taxonomy[rank] === right.taxonomy[rank] ? 2 : 0), score);
  }

  function phylumGroup(specimen) {
    return phylumGroups[specimen.taxonomy.phylum] || specimen.taxonomy.phylum || "";
  }

  function renderTreeBoard() {
    const complete = activeBranches.length === 1 && !treeFailed;
    el("tree-targets").innerHTML = treeFailed || complete ? "" : `
      <button id="cluster-branches" class="primary" ${selectedBranches.length === 2 ? "" : "disabled"}>Cluster selected branches</button>
    `;
    const clusterButton = el("cluster-branches");
    if (clusterButton) clusterButton.addEventListener("click", clusterSelectedBranches);

    el("tree-board").innerHTML = `
      <div class="tree-row" style="--depth:0"><div><strong>Completed clusters</strong><br>${completedClusters.length ? completedClusters.join(" -> ") : "none yet"}</div></div>
      <div class="tree-row" style="--depth:1"><div><strong>Selected branches</strong><br>${selectedBranches.length ? selectedBranches.map((id) => `Branch ${id}`).join(" + ") : "none"}</div></div>
      <div class="tree-row" style="--depth:2"><div><strong>Task status</strong><br>${treeFailed ? "fail" : complete ? "success" : "in progress"}</div></div>
      ${complete ? renderCorrectCladogram(activeBranches[0]) : ""}
    `;
  }

  function renderTreeFeedback() {
    if (treeFailed) {
      el("tree-feedback").className = "feedback bad";
      el("tree-feedback").textContent = "Tree task: fail. The selected branches are not the closest valid cluster at this stage.";
    } else if (activeBranches.length === 1) {
      el("tree-feedback").className = "feedback good";
      el("tree-feedback").textContent = "Pass: the branch-clustering order is correct.";
    } else {
      el("tree-feedback").className = "feedback";
      el("tree-feedback").textContent = "";
    }
  }

  function imgFor(id) {
    return specimens.find((item) => item.id === id).image;
  }

  function renderTipImage(id) {
    return `<span class="clado-tip"><img src="${imgFor(id)}" alt=""></span>`;
  }

  function renderCorrectCladogram(rootBranch) {
    const layout = layoutSvgCladogram(orderCladeForDisplay(rootBranch));
    return `
      <div class="phylo-tree">
        <strong>Built cladogram</strong>
        <div class="cladogram-canvas" style="--cladogram-width:${layout.width}px; --cladogram-height:${layout.height}px">
          ${layout.tips.map((tip) => `<span class="clado-tip" style="left:${tip.x}px"><img src="${imgFor(tip.id)}" alt=""></span>`).join("")}
          <svg class="cladogram-lines" viewBox="0 0 ${layout.width} ${layout.height}" aria-hidden="true">
            ${layout.paths.join("")}
          </svg>
        </div>
      </div>
    `;
  }

  function layoutSvgCladogram(rootBranch) {
    const tips = [];
    const paths = [];
    const xStep = 108;
    const xStart = 58;
    const yTip = 96;
    const yStep = 54;
    let nextTip = 0;
    let maxDepth = 0;

    function collectDepth(branch, depth) {
      maxDepth = Math.max(maxDepth, depth);
      (branch.children || []).forEach((child) => collectDepth(child, depth + 1));
    }

    function nodeY(depth) {
      return yTip + (maxDepth - depth + 1) * yStep;
    }

    function visit(branch, depth) {
      if (!branch.children || branch.children.length === 0) {
        const x = xStart + nextTip * xStep;
        nextTip += 1;
        tips.push({ id: branch.specimenIds[0], x });
        return { x, y: yTip };
      }

      const childNodes = branch.children.map((child) => visit(child, depth + 1));
      const minX = Math.min(...childNodes.map((node) => node.x));
      const maxX = Math.max(...childNodes.map((node) => node.x));
      const y = nodeY(depth);
      childNodes.forEach((node) => {
        paths.push(`<path d="M${node.x} ${node.y} V${y}" />`);
      });
      paths.push(`<path d="M${minX} ${y} H${maxX}" />`);
      return { x: (minX + maxX) / 2, y };
    }

    collectDepth(rootBranch, 0);
    visit(rootBranch, 0);
    return {
      tips,
      paths,
      width: Math.max(760, tips.length * xStep + 20),
      height: Math.max(290, yTip + (maxDepth + 1) * yStep + 42)
    };
  }

  function orderCladeForDisplay(branch) {
    if (!branch.children || branch.children.length === 0) return branch;
    const orderedChildren = branch.children.map(orderCladeForDisplay).sort((a, b) => cladeSortKey(a).localeCompare(cladeSortKey(b)));
    return { ...branch, children: orderedChildren };
  }

  function cladeSortKey(branch) {
    const first = specimens.find((item) => item.id === branch.specimenIds[0]);
    const groupOrder = {
      Porifera: "0",
      Radiata: "1",
      Protostomia: "2",
      Deuterostomia: "3",
      Plants: "4",
      Fungi: "5"
    };
    const group = phylumGroup(first);
    return `${groupOrder[group] || "9"}-${first.taxonomy.phylum || ""}-${first.taxonomy.class || ""}-${first.taxonomy.order || ""}-${first.taxonomy.family || ""}`;
  }

  function renderFullGallery() {
    const registeredImages = new Set(specimens.map((item) => item.image));
    const manifestImages = window.TAXONOMY_GALLERY_IMAGES || specimens.map((item) => item.image);
    const hideNames = !galleryNamesUnlocked || (el("hide-gallery-names")?.checked ?? true);
    const activeIds = activeSpecimenIds();
    const teacherDisabled = galleryNamesUnlocked ? "" : "disabled";
    const registeredCards = specimens.map((item) => `
      <article class="gallery-card">
        <div class="thumb"><img src="${item.image}" alt="${item.commonName}"></div>
        <div>
          <label class="activate-card">
            <input type="checkbox" class="activate-specimen" data-id="${item.id}" ${activeIds.includes(item.id) ? "checked" : ""} ${teacherDisabled}>
            Active in tasks
          </label>
          ${hideNames
            ? "<strong>Registered exercise image</strong><br><span class=\"answer-hidden\">Names hidden</span><br>"
            : `<strong>${item.commonName}</strong><br><i>${item.taxonomy.species}</i><br>${item.taxonomy.phylum} &gt; ${item.taxonomy.class} &gt; ${item.taxonomy.order}<br>`}
          <a href="${item.sourceUrl}" target="_blank" rel="noreferrer">${item.sourceName}</a>, ${item.license}
          <br><button class="secondary edit-registered-image" data-image="${item.image}" type="button" ${teacherDisabled}>Edit regions</button>
        </div>
      </article>
    `);
    const extraCards = manifestImages
      .filter((image) => !registeredImages.has(image))
      .map((image, index) => `
        <article class="gallery-card unregistered-card">
          <div class="thumb"><img src="${image}" alt="Unregistered gallery image ${index + 1}"></div>
          <div>
            <strong>Gallery image ${index + 1}</strong><br>
            Not registered for quiz/species/tree yet.<br>
            <button class="secondary register-image" data-image="${image}" ${teacherDisabled}>Register this image</button>
          </div>
        </article>
      `);
    el("full-gallery").innerHTML = [...registeredCards, ...extraCards].join("");
    document.querySelectorAll(".activate-specimen").forEach((checkbox) => {
      checkbox.addEventListener("change", () => {
        const ids = activeSpecimenIds();
        const nextIds = checkbox.checked
          ? unique([...ids, checkbox.dataset.id])
          : ids.filter((id) => id !== checkbox.dataset.id);
        setActiveSpecimenIds(nextIds);
        refreshTaskPools();
        renderActiveSetCount();
      });
    });
    document.querySelectorAll(".register-image").forEach((button) => {
      button.addEventListener("click", () => {
        openRegistryEditor(button.dataset.image);
      });
    });
    document.querySelectorAll(".edit-registered-image").forEach((button) => {
      button.addEventListener("click", () => openRegistryEditor(button.dataset.image));
    });
    renderActiveSetCount();
    updateTeacherEditingControls();
  }

  function openRegistryEditor(image) {
    if (!galleryNamesUnlocked) {
      el("registry-lookup-status").textContent = "Teacher key required before editing registrations or regions.";
      el("teacher-key").focus();
      return;
    }
    el("registry-image").value = image;
    loadRegistryForm(image);
    el("registry-lookup-status").textContent = "Edit regions or locality fields, then save to update this exercise image.";
    el("registry-form").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function initRegistryForm() {
    const manifestImages = window.TAXONOMY_GALLERY_IMAGES || specimens.map((item) => item.image);
    el("registry-image").innerHTML = manifestImages.map((image) => `<option value="${image}">${image.replace("GALLERY/", "")}</option>`).join("");
    el("registry-image").addEventListener("change", () => loadRegistryForm(el("registry-image").value));
    el("registry-proposed-name").addEventListener("input", updateRegistryGoogleLink);
    el("registry-taxonomy-lookup").addEventListener("click", lookupRegistryTaxonomy);
    el("registry-form").addEventListener("submit", saveRegistryForm);
    el("clear-custom-registry").addEventListener("click", () => {
      localStorage.removeItem("taxonomyTrainerCustomSpecimens");
      refreshFunctionalData();
    });
    el("hide-gallery-names").addEventListener("change", renderFullGallery);
    el("unlock-gallery-names").addEventListener("click", unlockGalleryNames);
    el("activate-random-ten").addEventListener("click", activateRandomTen);
    el("activate-all").addEventListener("click", activateAllRegistered);
    el("clear-active-set").addEventListener("click", clearActiveSet);
    el("export-active-set").addEventListener("click", exportActiveSet);
    el("copy-active-set").addEventListener("click", copyActiveSetExport);
    el("download-active-set").addEventListener("click", downloadActiveSetExport);
    el("teacher-key").addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        unlockGalleryNames();
      }
    });
    loadRegistryForm(el("registry-image").value);
    updateTeacherEditingControls();
  }

  function renderActiveSetCount() {
    const ids = activeSpecimenIds();
    const localIds = localActiveSpecimenIds();
    const publishedIds = Array.isArray(window.TAXONOMY_ACTIVE_SET) ? window.TAXONOMY_ACTIVE_SET : [];
    const activeCount = ids.length ? specimens.filter((specimen) => ids.includes(specimen.id)).length : specimens.length;
    const mode = ids.length ? "selected active images" : "all registered images active";
    const source = localIds.length ? "local teacher selection" : publishedIds.length ? "published GitHub set" : "no fixed set";
    el("active-set-count").textContent = `${activeCount} of ${specimens.length}: ${mode}; source: ${source}.`;
  }

  function activateRandomTen() {
    if (!galleryNamesUnlocked) return;
    setActiveSpecimenIds(shuffle(specimens).slice(0, Math.min(10, specimens.length)).map((specimen) => specimen.id));
    refreshTaskPools();
    renderFullGallery();
  }

  function activateAllRegistered() {
    if (!galleryNamesUnlocked) return;
    setActiveSpecimenIds(specimens.map((specimen) => specimen.id));
    refreshTaskPools();
    renderFullGallery();
  }

  function clearActiveSet() {
    if (!galleryNamesUnlocked) return;
    localStorage.removeItem("taxonomyTrainerActiveSpecimens");
    refreshTaskPools();
    renderFullGallery();
  }

  function activeSetExportText() {
    const ids = activeSpecimenIds();
    return `window.TAXONOMY_ACTIVE_SET = ${JSON.stringify(ids, null, 2)};\n`;
  }

  function exportActiveSet() {
    if (!galleryNamesUnlocked) return;
    const text = activeSetExportText();
    el("active-set-export").value = text;
    el("active-set-export-status").textContent = "Upload this text as data/active_set.js on GitHub so students receive this task set.";
    return text;
  }

  async function copyActiveSetExport() {
    if (!galleryNamesUnlocked) return;
    const text = el("active-set-export").value || exportActiveSet();
    try {
      await navigator.clipboard.writeText(text);
      el("active-set-export-status").textContent = "Copied. Paste it into GitHub file data/active_set.js.";
    } catch {
      el("active-set-export").focus();
      el("active-set-export").select();
      el("active-set-export-status").textContent = "Select the text and copy it manually.";
    }
  }

  function downloadActiveSetExport() {
    if (!galleryNamesUnlocked) return;
    const text = el("active-set-export").value || exportActiveSet();
    const blob = new Blob([text], { type: "text/javascript" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "active_set.js";
    link.click();
    URL.revokeObjectURL(link.href);
    el("active-set-export-status").textContent = "Downloaded active_set.js. Upload it into the GitHub data folder.";
  }

  function refreshTaskPools() {
    startQuizSession();
    identifyPool = shuffle(taskSpecimens());
    identifyIndex = 0;
    const select = el("identify-specimen");
    select.innerHTML = taskSpecimens().map((item, index) => `<option value="${item.id}">Picture ${index + 1}</option>`).join("");
    showIdentifySpecimen();
    resetTreeTask();
  }

  function unlockGalleryNames() {
    const key = el("teacher-key").value.trim();
    const status = el("teacher-key-status");
    if (key !== teacherGalleryKey) {
      galleryNamesUnlocked = false;
      el("hide-gallery-names").checked = true;
      el("hide-gallery-names").disabled = true;
      status.textContent = "Names remain hidden.";
      updateTeacherEditingControls();
      renderFullGallery();
      return;
    }

    galleryNamesUnlocked = true;
    el("hide-gallery-names").disabled = false;
    el("hide-gallery-names").checked = false;
    status.textContent = "Teacher mode: names, registration, regions, and active-set editing are unlocked.";
    updateTeacherEditingControls();
    renderFullGallery();
  }

  function updateTeacherEditingControls() {
    const registryControls = [...el("registry-form").querySelectorAll("input, select, button")];
    registryControls.forEach((control) => {
      control.disabled = !galleryNamesUnlocked;
    });
    ["activate-random-ten", "activate-all", "clear-active-set", "export-active-set", "copy-active-set", "download-active-set"].forEach((id) => {
      el(id).disabled = !galleryNamesUnlocked;
    });
    document.querySelectorAll(".register-image, .edit-registered-image, .activate-specimen").forEach((control) => {
      control.disabled = !galleryNamesUnlocked;
    });
    if (!galleryNamesUnlocked) {
      el("registry-lookup-status").textContent = "Teacher key required before editing registrations, regions, or candidate species.";
    }
  }

  function loadRegistryForm(image) {
    const specimen = specimens.find((item) => item.image === image);
    const taxonomy = specimen?.taxonomy || {};
    el("registry-preview-image").src = image;
    el("registry-preview-image").alt = "Selected gallery image";
    el("registry-proposed-name").value = taxonomy.species || "";
    el("registry-phylum").value = taxonomy.phylum || "";
    el("registry-class").value = taxonomy.class || "";
    el("registry-order").value = taxonomy.order || "";
    el("registry-family").value = taxonomy.family || "";
    el("registry-genus").value = taxonomy.genus || "";
    el("registry-species").value = taxonomy.species || "";
    el("registry-candidates").value = specimen?.candidates?.join(", ") || "";
    el("registry-regions").value = specimen?.regions?.join(", ") || "";
    el("registry-picture-region").value = specimen?.pictureRegion || "";
    el("registry-student-region").value = specimen?.studentRegion || "";
    el("registry-lookup-status").textContent = "";
    updateRegistryGoogleLink();
  }

  function updateRegistryGoogleLink() {
    const name = normalizeName(el("registry-proposed-name").value);
    const query = encodeURIComponent(name || el("registry-image").value.replace("GALLERY/", "").replace(/\.[^.]+$/, ""));
    el("registry-google-search").href = `https://www.google.com/search?tbm=isch&q=${query}`;
  }

  async function lookupRegistryTaxonomy() {
    const name = normalizeName(el("registry-proposed-name").value);
    const status = el("registry-lookup-status");
    if (!name || /\ssp\.$/i.test(name)) {
      status.textContent = "Enter a species name, not only Genus sp., for automatic upper-taxon lookup.";
      return;
    }

    status.textContent = "Looking up taxonomy in GBIF...";
    try {
      const response = await fetch(`https://api.gbif.org/v1/species/match?verbose=true&name=${encodeURIComponent(name)}`);
      if (!response.ok) throw new Error(`GBIF request failed: ${response.status}`);
      const data = await response.json();
      if (!data.usageKey && !data.genus) {
        status.textContent = "No confident GBIF match. Please correct fields manually.";
        return;
      }
      const taxonomy = normalizeLookupTaxonomy(data, name);
      el("registry-phylum").value = taxonomy.phylum;
      el("registry-class").value = taxonomy.class;
      el("registry-order").value = taxonomy.order;
      el("registry-family").value = taxonomy.family;
      el("registry-genus").value = taxonomy.genus;
      el("registry-species").value = taxonomy.species;
      if (!el("registry-candidates").value.trim()) {
        el("registry-candidates").value = unique([taxonomy.species, `${taxonomy.genus} sp.`].filter(Boolean)).join(", ");
      }
      status.textContent = taxonomy.exactSpecies
        ? `Taxonomy filled from GBIF (${data.matchType || "match"}). Check and correct if needed.`
        : "GBIF matched a higher taxon. Your proposed species name was kept; upper taxa were filled for checking.";
    } catch (error) {
      status.textContent = "Could not reach GBIF. You can still fill or correct fields manually.";
    }
  }

  function normalizeLookupTaxonomy(data, fallbackName) {
    const exactSpecies = data.matchType === "EXACT" && data.rank === "SPECIES";
    const cleanFallback = cleanScientificName(fallbackName);
    const cleanGbifName = cleanScientificName(data.scientificName || "");
    const taxonomy = {
      phylum: data.phylum || "",
      class: data.class || "",
      order: data.order || "",
      family: data.family || "",
      genus: data.genus || cleanFallback.split(" ")[0] || "",
      species: exactSpecies ? cleanGbifName : cleanFallback,
      exactSpecies
    };
    const orderToClass = {
      Squamata: "Reptilia",
      Testudines: "Reptilia",
      Crocodylia: "Reptilia",
      Rhynchocephalia: "Reptilia",
      Anura: "Amphibia",
      Caudata: "Amphibia",
      Gymnophiona: "Amphibia",
      Carnivora: "Mammalia",
      Rodentia: "Mammalia",
      Primates: "Mammalia",
      Chiroptera: "Mammalia",
      Artiodactyla: "Mammalia",
      Passeriformes: "Aves",
      Accipitriformes: "Aves",
      Coleoptera: "Insecta",
      Lepidoptera: "Insecta",
      Diptera: "Insecta",
      Hymenoptera: "Insecta",
      Stylommatophora: "Gastropoda",
      Fagales: "Magnoliopsida"
    };

    if (!taxonomy.order && orderToClass[taxonomy.class]) {
      taxonomy.order = taxonomy.class;
      taxonomy.class = orderToClass[taxonomy.order];
    }

    return taxonomy;
  }

  function cleanScientificName(name) {
    const parts = normalizeName(name).split(" ");
    if (parts.length < 2) return normalizeName(name);
    return `${parts[0]} ${parts[1]}`;
  }

  function saveRegistryForm(event) {
    event.preventDefault();
    if (!galleryNamesUnlocked) {
      el("registry-lookup-status").textContent = "Teacher key required before saving registration edits.";
      el("teacher-key").focus();
      return;
    }
    const image = el("registry-image").value;
    const existing = specimens.find((item) => item.image === image);
    const species = normalizeName(el("registry-species").value || el("registry-proposed-name").value);
    const id = image.replace(/^GALLERY\//, "").replace(/\.[^.]+$/, "").toLowerCase().replace(/[^a-z0-9]+/g, "-");
    const candidates = splitList(el("registry-candidates").value);
    const pictureRegion = normalizeName(el("registry-picture-region").value);
    const studentRegion = normalizeName(el("registry-student-region").value);
    const regionsList = unique([...splitList(el("registry-regions").value), pictureRegion, studentRegion].filter(Boolean));
    const record = {
      id,
      commonName: existing?.commonName || "Custom specimen",
      image,
      sourceName: existing?.sourceName || "Local gallery",
      sourceUrl: existing?.sourceUrl || image,
      license: existing?.license || "Classroom image",
      pictureRegion,
      studentRegion,
      taxonomy: {
        phylum: normalizeName(el("registry-phylum").value),
        class: normalizeName(el("registry-class").value),
        order: normalizeName(el("registry-order").value),
        family: normalizeName(el("registry-family").value),
        genus: normalizeName(el("registry-genus").value),
        species
      },
      candidates: unique([species, ...candidates].filter(Boolean)),
      regions: regionsList
    };
    const custom = customSpecimens().filter((item) => item.id !== id);
    custom.push(record);
    localStorage.setItem("taxonomyTrainerCustomSpecimens", JSON.stringify(custom));
    refreshFunctionalData();
  }

  function splitList(value) {
    return value.split(",").map((item) => normalizeName(item)).filter(Boolean);
  }

  function refreshFunctionalData() {
    window.location.reload();
  }

  function buildResultsReport() {
    const student = normalizeName(el("student-name").value) || "Unnamed student";
    const now = new Date();
    const quizCorrect = quizResults.filter((result) => result.passed).length;
    const quizIncorrect = quizResults.filter((result) => !result.passed).length;
    const speciesCorrect = identificationResults.filter((result) => result.score === 1).length;
    const speciesHalf = identificationResults.filter((result) => result.score === 0.5).length;
    const speciesIncorrect = identificationResults.filter((result) => !result.score).length;
    const speciesPoints = identificationResults.reduce((sum, result) => sum + (result.score || 0), 0);
    const treeStatus = treeFailed
      ? "fail"
      : activeBranches.length === 1
        ? "success"
        : "in progress";
    const level = el("student-level").value === "beginner" ? "Beginner (genus not asked)" : "Standard (genus included)";
    const lines = [
      "Taxonomy Trainer results",
      `Student: ${student}`,
      `Date: ${now.toLocaleString()}`,
      "",
      `Quiz level: ${level}`,
      `Quiz correct pictures: ${quizCorrect}`,
      `Quiz incorrect pictures: ${quizIncorrect}`,
      `Quiz total finished pictures: ${quizResults.length}`,
      "",
      `Species Check correct: ${speciesCorrect}`,
      `Species Check half credit: ${speciesHalf}`,
      `Species Check incorrect: ${speciesIncorrect}`,
      `Species Check total submitted: ${identificationResults.length}`,
      `Species Check points: ${speciesPoints} of ${identificationResults.length}`,
      "",
      `Tree task status: ${treeStatus}`,
      `Tree clusters completed: ${completedClusters.length}`,
      "",
      "Quiz details:"
    ];

    if (quizResults.length) {
      quizResults.forEach((result, index) => {
        const state = result.passed ? "correct" : "incorrect";
        const detail = result.failedRank
          ? `; failed rank ${rankLabels[result.failedRank]}: selected ${result.selected}, expected ${result.expected}`
          : result.skipped
            ? "; skipped"
            : "";
        lines.push(`${index + 1}. ${result.commonName || result.id}: ${state}${detail}`);
      });
    } else {
      lines.push("No quiz pictures completed yet.");
    }

    lines.push("", "Species Check details:");
    if (identificationResults.length) {
      identificationResults.forEach((result, index) => {
        lines.push(`${index + 1}. ${result.commonName || result.specimenId}: ${result.outcome || (result.correct ? "correct" : "incorrect")}; score ${result.score || 0}; selected ${result.selected}; expected ${result.expected}; region ${result.region}; verdict ${result.verdict}`);
      });
    } else {
      lines.push("No species identifications submitted yet.");
    }

    return lines.join("\n");
  }

  function generateResultsReport() {
    const report = buildResultsReport();
    el("results-output").value = report;
    el("results-feedback").className = "feedback good";
    el("results-feedback").textContent = "Report generated.";
    return report;
  }

  async function copyResultsReport() {
    const report = el("results-output").value || generateResultsReport();
    try {
      await navigator.clipboard.writeText(report);
      el("results-feedback").className = "feedback good";
      el("results-feedback").textContent = "Report copied. It can be pasted into email.";
    } catch {
      el("results-output").focus();
      el("results-output").select();
      el("results-feedback").className = "feedback";
      el("results-feedback").textContent = "Select the report text and copy it manually.";
    }
  }

  function downloadResultsReport() {
    const report = el("results-output").value || generateResultsReport();
    const filename = `taxonomy-trainer-results-${new Date().toISOString().slice(0, 10)}.txt`;
    const blob = new Blob([report], { type: "text/plain" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
    URL.revokeObjectURL(link.href);
    el("results-feedback").className = "feedback good";
    el("results-feedback").textContent = "Text report downloaded.";
  }

  document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => switchView(tab.dataset.view)));
  el("student-level").addEventListener("change", startQuizSession);
  el("next-specimen").addEventListener("click", () => {
    if (quizSpecimen && quizQueue.length) {
      quizResults.push({ id: quizSpecimen.id, commonName: quizSpecimen.commonName, passed: false, skipped: true });
    }
    startNextQuizSpecimen();
  });
  el("generate-results").addEventListener("click", generateResultsReport);
  el("copy-results").addEventListener("click", copyResultsReport);
  el("download-results").addEventListener("click", downloadResultsReport);
  renderIdentify();
  renderTreeGallery();
  renderFullGallery();
  initRegistryForm();
  startQuizSession();
})();
