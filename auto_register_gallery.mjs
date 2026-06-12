import fs from "node:fs/promises";
import path from "node:path";

const root = process.argv[2] || process.cwd();
const galleryDir = path.join(root, "GALLERY");
const dataDir = path.join(root, "data");
const manifestPath = path.join(dataDir, "gallery_manifest.js");
const specimensPath = path.join(dataDir, "specimens.js");
const imageExtensions = new Set([".jpg", ".jpeg", ".png", ".gif", ".webp"]);

const baseDistractors = {
  phylum: ["Tracheophyta", "Cnidaria", "Echinodermata", "Annelida"],
  class: ["Reptilia", "Magnoliopsida", "Octocorallia", "Aves"],
  order: ["Squamata", "Fagales", "Malacalcyonacea", "Carnivora", "Stylommatophora"],
  family: ["Lacertidae", "Fagaceae", "Melithaeidae", "Helicidae", "Cerambycidae"],
  genus: ["Lacerta", "Darevskia", "Fagus", "Melithaea", "Quercus"]
};

const manualCorrections = {
  "Angius colchica": "Anguis colchica",
  "corracias garrulus": "Coracias garrulus",
  "Cychorium intybus": "Cichorium intybus",
  "Zygaena fillipendulae": "Zygaena filipendulae"
};

const manualTaxonomyByGenus = {
  Lumbricus: {
    phylum: "Annelida",
    class: "Clitellata",
    order: "Haplotaxida",
    family: "Lumbricidae"
  }
};

function isImage(file) {
  return imageExtensions.has(path.extname(file).toLowerCase());
}

function toTitleName(name) {
  const titled = name
    .replace(/[-_]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .split(" ")
    .map((part, index) => index === 0
      ? part.charAt(0).toUpperCase() + part.slice(1).toLowerCase()
      : part.toLowerCase())
    .join(" ");
  return titled.replace(/\ssp$/i, " sp.");
}

function nameFromFile(file) {
  const raw = path.basename(file, path.extname(file));
  if (!/[A-Za-z]+[_ -][A-Za-z]+/.test(raw)) return null;
  const candidate = toTitleName(raw);
  return manualCorrections[candidate] || candidate;
}

function idFromName(name) {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

function cleanScientificName(name, fallback) {
  const parts = (name || fallback || "").replace(/\s+/g, " ").trim().split(" ");
  if (parts.length >= 3 && parts[2].toLowerCase() === "sp.") return `${parts[0]} sp.`;
  if (parts.length >= 3 && /^[a-z]/.test(parts[2])) return `${parts[0]} ${parts[1]} ${parts[2]}`;
  if (parts.length >= 2) return `${parts[0]} ${parts[1]}`;
  return fallback || name || "";
}

async function gbifMatch(name) {
  const genusSp = /\ssp\.?$/i.test(name);
  const lookupName = genusSp ? name.replace(/\ssp\.?$/i, "") : name;
  const url = `https://api.gbif.org/v1/species/match?verbose=true&name=${encodeURIComponent(lookupName)}`;
  const response = await fetch(url);
  if (!response.ok) throw new Error(`GBIF ${response.status}`);
  const data = await response.json();
  const fallbackGenus = lookupName.split(" ")[0] || "";
  return {
    phylum: data.phylum || "",
    class: data.class || "",
    order: data.order || "",
    family: data.family || "",
    genus: data.genus || fallbackGenus,
    species: genusSp ? `${fallbackGenus} sp.` : cleanScientificName(data.scientificName || data.canonicalName, name),
    matchType: data.matchType || "",
    rank: data.rank || ""
  };
}

function fixCommonRankProblems(taxonomy) {
  const orderToClass = {
    Squamata: "Reptilia",
    Testudines: "Reptilia",
    Crocodylia: "Reptilia",
    Rhynchocephalia: "Reptilia",
    Anura: "Amphibia",
    Caudata: "Amphibia",
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
    Salmoniformes: "Actinopterygii",
    Stylommatophora: "Gastropoda",
    Fagales: "Magnoliopsida"
  };

  if (!taxonomy.order && orderToClass[taxonomy.class]) {
    taxonomy.order = taxonomy.class;
    taxonomy.class = orderToClass[taxonomy.order];
  }
  if ((!taxonomy.class || taxonomy.class === "Unknown") && orderToClass[taxonomy.order]) {
    taxonomy.class = orderToClass[taxonomy.order];
  }
  const manualGenusTaxonomy = manualTaxonomyByGenus[taxonomy.genus];
  if (manualGenusTaxonomy) {
    for (const [rank, value] of Object.entries(manualGenusTaxonomy)) {
      if (!taxonomy[rank] || taxonomy[rank] === "Unknown") taxonomy[rank] = value;
    }
  }
  return taxonomy;
}

function unique(values) {
  return [...new Set(values.filter(Boolean))];
}

async function main() {
  await fs.mkdir(dataDir, { recursive: true });
  const files = (await fs.readdir(galleryDir)).filter(isImage).sort((a, b) => a.localeCompare(b));
  const images = files.map((file) => `GALLERY/${file}`);
  const specimens = [];
  const occurrences = {};
  const lookupFailures = [];

  for (const file of files) {
    const scientificName = nameFromFile(file);
    if (!scientificName) continue;
    let taxonomy;
    try {
      taxonomy = fixCommonRankProblems(await gbifMatch(scientificName));
    } catch (error) {
      const parts = scientificName.split(" ");
      taxonomy = {
        phylum: "",
        class: "",
        order: "",
        family: "",
        genus: parts[0] || "",
        species: scientificName
      };
      lookupFailures.push(scientificName);
    }

    const species = taxonomy.species || scientificName;
    const candidates = unique([species, `${taxonomy.genus} sp.`]);
    const record = {
      id: idFromName(species || scientificName),
      commonName: species,
      image: `GALLERY/${file}`,
      sourceName: "Local gallery",
      sourceUrl: `GALLERY/${file}`,
      license: "Classroom image",
      pictureRegion: "Georgia",
      studentRegion: "Georgia",
      taxonomy: {
        phylum: taxonomy.phylum || "Unknown",
        class: taxonomy.class || "Unknown",
        order: taxonomy.order || "Unknown",
        family: taxonomy.family || "Unknown",
        genus: taxonomy.genus || scientificName.split(" ")[0],
        species
      },
      candidates,
      regions: ["Georgia"]
    };
    specimens.push(record);
    candidates.forEach((candidate) => {
      occurrences[candidate] = ["Georgia"];
    });
  }

  const distractors = { ...baseDistractors };
  for (const rank of ["phylum", "class", "order", "family", "genus"]) {
    distractors[rank] = unique([
      ...(distractors[rank] || []),
      ...specimens.map((specimen) => specimen.taxonomy[rank]).filter((value) => value && value !== "Unknown")
    ]).sort((a, b) => a.localeCompare(b));
  }

  const specimensJs = [
    `window.TAXONOMY_SPECIMENS = ${JSON.stringify(specimens, null, 2)};`,
    "",
    `window.TAXONOMY_DISTRACTORS = ${JSON.stringify(distractors, null, 2)};`,
    "",
    `window.TAXONOMY_REGIONS = ${JSON.stringify(["Georgia", "Caucasus", "Europe", "Western Asia", "North America", "Introduced"], null, 2)};`,
    "",
    `window.TAXONOMY_OCCURRENCES = ${JSON.stringify(occurrences, null, 2)};`,
    ""
  ].join("\n");

  const manifestJs = `window.TAXONOMY_GALLERY_IMAGES = ${JSON.stringify(images, null, 2)};\n`;

  await fs.writeFile(specimensPath, specimensJs, "utf8");
  await fs.writeFile(manifestPath, manifestJs, "utf8");
  console.log(`Registered ${specimens.length} species-like image(s).`);
  console.log(`Manifest includes ${images.length} image(s).`);
  if (lookupFailures.length) {
    console.log(`GBIF lookup fallback used for: ${lookupFailures.join(", ")}`);
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
