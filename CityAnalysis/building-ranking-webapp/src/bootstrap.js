(function bootstrapDashboard(script) {
  const dataVersion = script?.dataset.dataVersion || "1";
  const appVersion = script?.dataset.appVersion || "1";
  const loadStatus = document.getElementById("loadStatus");

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const element = document.createElement("script");
      element.src = src;
      element.onload = resolve;
      element.onerror = () => reject(new Error(`Could not load ${src}`));
      document.body.appendChild(element);
    });
  }

  async function loadCompressedData() {
    if (!("DecompressionStream" in window)) {
      throw new Error("This browser does not support streamed gzip decompression.");
    }
    const response = await fetch(`data/ranking-data.json.gz?v=${encodeURIComponent(dataVersion)}`, {
      cache: "force-cache",
      credentials: "omit",
    });
    if (!response.ok || !response.body) {
      throw new Error(`Compressed ranking data returned ${response.status}.`);
    }
    const contentEncoding = response.headers.get("content-encoding");
    const jsonResponse = contentEncoding
      ? response
      : new Response(response.body.pipeThrough(new DecompressionStream("gzip")));
    window.FOE_BUILDING_RANKING_DATA = await jsonResponse.json();
  }

  async function start() {
    try {
      await loadCompressedData();
    } catch (compressedError) {
      console.warn("Compressed data unavailable; loading the compatibility dataset.", compressedError);
      await loadScript(`data/ranking-data.js?v=${encodeURIComponent(dataVersion)}`);
    }

    if (!window.FOE_BUILDING_RANKING_DATA) {
      throw new Error("Ranking data did not initialize.");
    }
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
