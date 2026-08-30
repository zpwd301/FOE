(function bootstrapDashboard(script) {
  const dataVersion = script?.dataset.dataVersion || "1";
  const appVersion = script?.dataset.appVersion || "1";
  const loadStatus = document.getElementById("loadStatus");
  const ageLoads = new Map();

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

  async function fetchCompressedJson(src) {
    if (!("DecompressionStream" in window)) {
      throw new Error("This browser does not support streamed gzip decompression.");
    }
    const response = await fetch(src, { cache: "force-cache" });
    if (!response.ok || !response.body) {
      throw new Error(`${src} returned ${response.status}.`);
    }
    const contentEncoding = response.headers.get("content-encoding");
    const jsonResponse = contentEncoding
      ? response
      : new Response(response.body.pipeThrough(new DecompressionStream("gzip")));
    return jsonResponse.json();
  }

  async function loadJsonAsset(compressedPath, fallbackPath, label) {
    const version = encodeURIComponent(dataVersion);
    try {
      return await fetchCompressedJson(`${compressedPath}?v=${version}`);
    } catch (compressedError) {
      console.warn(`Compressed ${label} unavailable; loading the JSON fallback.`, compressedError);
      return fetchJson(`${fallbackPath}?v=${version}`);
    }
  }

  async function loadCoreData() {
    const data = await loadJsonAsset(
      "data/ranking-core.json.gz",
      "data/ranking-core.json",
      "ranking core"
    );
    if (!data || typeof data !== "object" || !Array.isArray(data.ages)) {
      throw new Error("Ranking core data did not initialize.");
    }
    data.recordsByAge = {};
    window.FOE_BUILDING_RANKING_DATA = data;
  }

  async function loadAgeData(age) {
    const data = window.FOE_BUILDING_RANKING_DATA;
    if (!data?.ages?.some((item) => item.key === age)) throw new Error(`Unknown city age: ${age}`);
    if (Array.isArray(data.recordsByAge?.[age])) return data.recordsByAge[age];
    if (ageLoads.has(age)) return ageLoads.get(age);

    const load = (async () => {
      const encodedAge = encodeURIComponent(age);
      const payload = await loadJsonAsset(
        `data/ages/${encodedAge}.json.gz`,
        `data/ages/${encodedAge}.json`,
        `${age} ranking data`
      );
      if (payload?.age !== age || !Array.isArray(payload.records)) {
        throw new Error(`Ranking data for ${age} is invalid.`);
      }
      data.recordsByAge[age] = payload.records;
      return payload.records;
    })();
    ageLoads.set(age, load);
    try {
      return await load;
    } finally {
      ageLoads.delete(age);
    }
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
      loadCoreData(),
    ]);
    window.FOE_LOAD_BUILDING_RANKING_AGE = loadAgeData;
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
