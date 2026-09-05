(function bootstrapDashboard(script) {
  const dataVersion = script?.dataset.dataVersion || "1";
  const appVersion = script?.dataset.appVersion || "1";
  const loadStatus = document.getElementById("loadStatus");
  const ageLoads = new Map();
  const cityAgeLoads = new Map();

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const element = document.createElement("script");
      element.src = src;
      element.onload = resolve;
      element.onerror = () => reject(new Error(`Could not load ${src}`));
      document.body.appendChild(element);
    });
  }

  async function fetchJson(src) {
    const response = await fetch(src, { cache: "force-cache" });
    if (!response.ok) throw new Error(`${src} returned ${response.status}.`);
    return response.json();
  }

  function supportsDecompression(format) {
    if (!("DecompressionStream" in window)) return false;
    try {
      new DecompressionStream(format);
      return true;
    } catch (_error) {
      return false;
    }
  }

  async function fetchCompressedJson(src, format) {
    const response = await fetch(src, { cache: "force-cache" });
    if (!response.ok || !response.body) {
      throw new Error(`${src} returned ${response.status}.`);
    }
    const contentEncoding = response.headers.get("content-encoding");
    if (contentEncoding) return response.json();
    if (!supportsDecompression(format)) {
      throw new Error(`This browser cannot decompress raw ${format} responses.`);
    }
    const jsonResponse = new Response(response.body.pipeThrough(new DecompressionStream(format)));
    return jsonResponse.json();
  }

  async function loadJsonAsset(brotliPath, gzipPath, fallbackPath, label) {
    const version = encodeURIComponent(dataVersion);
    for (const candidate of [
      { path: brotliPath, format: "brotli", name: "Brotli" },
      { path: gzipPath, format: "gzip", name: "gzip" },
    ]) {
      try {
        return await fetchCompressedJson(`${candidate.path}?v=${version}`, candidate.format);
      } catch (compressedError) {
        console.warn(`${candidate.name} ${label} unavailable; trying the next fallback.`, compressedError);
      }
    }
    return fetchJson(`${fallbackPath}?v=${version}`);
  }

  async function loadCoreData() {
    const data = await loadJsonAsset(
      "data/ranking-core.json.br",
      "data/ranking-core.json.gz",
      "data/ranking-core.json",
      "ranking core"
    );
    if (!data || typeof data !== "object" || !Array.isArray(data.ages)) {
      throw new Error("Ranking core data did not initialize.");
    }
    data.recordsByAge = {};
    data.cityRecordsByAge = {};
    window.FOE_BUILDING_RANKING_DATA = data;
  }

  async function loadAgeAsset(age, { directory, recordKey, loads, label }) {
    const data = window.FOE_BUILDING_RANKING_DATA;
    if (!data?.ages?.some((item) => item.key === age)) throw new Error(`Unknown city age: ${age}`);
    if (Array.isArray(data[recordKey]?.[age])) return data[recordKey][age];
    if (loads.has(age)) return loads.get(age);

    const load = (async () => {
      const encodedAge = encodeURIComponent(age);
      const payload = await loadJsonAsset(
        `data/${directory}/${encodedAge}.json.br`,
        `data/${directory}/${encodedAge}.json.gz`,
        `data/${directory}/${encodedAge}.json`,
        `${age} ${label}`
      );
      if (payload?.age !== age || !Array.isArray(payload.records)) {
        throw new Error(`${label} for ${age} is invalid.`);
      }
      data[recordKey][age] = payload.records;
      return payload.records;
    })();
    loads.set(age, load);
    try {
      return await load;
    } finally {
      loads.delete(age);
    }
  }

  function loadAgeData(age) {
    return loadAgeAsset(age, {
      directory: "ages",
      recordKey: "recordsByAge",
      loads: ageLoads,
      label: "ranking data",
    });
  }

  function loadCityAgeData(age) {
    return loadAgeAsset(age, {
      directory: "city-ages",
      recordKey: "cityRecordsByAge",
      loads: cityAgeLoads,
      label: "all-level city data",
    });
  }

  function browserStorage() {
    try {
      return window.localStorage;
    } catch (_error) {
      return null;
    }
  }

  function initialAge() {
    const data = window.FOE_BUILDING_RANKING_DATA;
    const allowedAges = new Set(data.ages.map((age) => age.key));
    const urlAge = new URLSearchParams(window.location.search).get("age");
    if (allowedAges.has(urlAge)) return urlAge;
    const stored = window.FOE_BUILDING_RANKING_PREFERENCES
      ?.createPreferenceStore(browserStorage())
      .read();
    if (allowedAges.has(stored?.age)) return stored.age;
    return data.metadata.defaultAge;
  }

  async function start() {
    await Promise.all([
      loadScript(`src/preferences.js?v=${encodeURIComponent(appVersion)}`),
      loadScript(`src/strengths.js?v=${encodeURIComponent(appVersion)}`),
      loadScript(`src/unit-production.js?v=${encodeURIComponent(appVersion)}`),
      loadScript(`src/production-search.js?v=${encodeURIComponent(appVersion)}`),
      loadScript(`src/city-map.js?v=${encodeURIComponent(appVersion)}`),
      loadScript(`src/ranking.js?v=${encodeURIComponent(appVersion)}`),
      loadCoreData(),
    ]);
    window.FOE_LOAD_BUILDING_RANKING_AGE = loadAgeData;
    window.FOE_LOAD_BUILDING_RANKING_CITY_AGE = loadCityAgeData;
    await loadAgeData(initialAge());
    await loadScript(`src/app.js?v=${encodeURIComponent(appVersion)}`);
    document.body.classList.remove("is-loading");
    if (loadStatus) loadStatus.hidden = true;
  }

  start().catch((error) => {
    console.error(error);
    document.body.classList.remove("is-loading");
    if (loadStatus) {
      loadStatus.classList.add("load-error");
      loadStatus.textContent = "The ranking data could not be loaded. Refresh the page to try again.";
    }
  });
})(document.currentScript);
