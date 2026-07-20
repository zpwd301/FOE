(function initializeBuildingRankingTheme(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (!root) return;

  root.FOE_BUILDING_RANKING_THEME_API = api;
  if (!root.document?.documentElement) return;

  let storage = null;
  let mediaQuery = null;
  try {
    storage = root.localStorage;
  } catch (_error) {
    storage = null;
  }
  try {
    mediaQuery = root.matchMedia("(prefers-color-scheme: dark)");
  } catch (_error) {
    mediaQuery = null;
  }

  root.FOE_BUILDING_RANKING_THEME = api.createThemeController({
    element: root.document.documentElement,
    storage,
    mediaQuery,
  });
  root.FOE_BUILDING_RANKING_THEME.start();
  const connectToggle = () => api.connectThemeToggle(
    root.FOE_BUILDING_RANKING_THEME,
    root.document
  );
  if (root.document.readyState === "loading") {
    root.document.addEventListener("DOMContentLoaded", connectToggle, { once: true });
  } else {
    connectToggle();
  }
})(typeof window !== "undefined" ? window : globalThis, function themeFactory() {
  "use strict";

  const STORAGE_KEY = "foe-building-rankings.theme.v1";
  const LIGHT_THEME = "light";
  const DARK_THEME = "dark";

  function normalizeTheme(value) {
    return value === LIGHT_THEME || value === DARK_THEME ? value : null;
  }

  function readStoredTheme(storage, key = STORAGE_KEY) {
    if (!storage) return null;
    try {
      return normalizeTheme(storage.getItem(key));
    } catch (_error) {
      return null;
    }
  }

  function systemTheme(mediaQuery) {
    return mediaQuery?.matches ? DARK_THEME : LIGHT_THEME;
  }

  function createThemeController(options = {}) {
    const element = options.element || null;
    const storage = options.storage || null;
    const mediaQuery = options.mediaQuery || null;
    const key = options.key || STORAGE_KEY;
    const subscribers = new Set();
    let preference = readStoredTheme(storage, key);
    let theme = preference || systemTheme(mediaQuery);
    let listening = false;

    function notify() {
      subscribers.forEach((subscriber) => subscriber(theme, preference));
    }

    function apply(nextTheme) {
      theme = normalizeTheme(nextTheme) || systemTheme(mediaQuery);
      if (element) {
        element.dataset.theme = theme;
      }
      notify();
      return theme;
    }

    function save(nextTheme) {
      if (!storage) return;
      try {
        storage.setItem(key, nextTheme);
      } catch (_error) {
        // The visual theme still works when storage is unavailable.
      }
    }

    function handleSystemChange() {
      if (!preference) apply(systemTheme(mediaQuery));
    }

    return {
      get theme() {
        return theme;
      },

      get preference() {
        return preference;
      },

      start() {
        apply(preference || systemTheme(mediaQuery));
        if (!listening && mediaQuery) {
          if (typeof mediaQuery.addEventListener === "function") {
            mediaQuery.addEventListener("change", handleSystemChange);
            listening = true;
          } else if (typeof mediaQuery.addListener === "function") {
            mediaQuery.addListener(handleSystemChange);
            listening = true;
          }
        }
        return theme;
      },

      set(nextTheme) {
        const normalized = normalizeTheme(nextTheme);
        if (!normalized) return theme;
        preference = normalized;
        save(normalized);
        return apply(normalized);
      },

      toggle() {
        return this.set(theme === DARK_THEME ? LIGHT_THEME : DARK_THEME);
      },

      subscribe(subscriber) {
        if (typeof subscriber !== "function") return () => {};
        subscribers.add(subscriber);
        subscriber(theme, preference);
        return () => subscribers.delete(subscriber);
      },
    };
  }

  function connectThemeToggle(controller, documentObject) {
    const button = documentObject?.getElementById("themeToggle");
    const icon = documentObject?.getElementById("themeToggleIcon");
    const label = documentObject?.getElementById("themeToggleLabel");
    if (!controller || !button) return () => {};

    const unsubscribe = controller.subscribe((theme) => {
      const darkMode = theme === DARK_THEME;
      const targetTheme = darkMode ? LIGHT_THEME : DARK_THEME;
      button.setAttribute("aria-label", `Switch to ${targetTheme} mode`);
      button.title = `Switch to ${targetTheme} mode`;
      if (icon) icon.textContent = darkMode ? "☀" : "☾";
      if (label) label.textContent = darkMode ? "Light Mode" : "Dark Mode";
    });
    button.addEventListener("click", () => controller.toggle());
    return unsubscribe;
  }

  return {
    STORAGE_KEY,
    LIGHT_THEME,
    DARK_THEME,
    normalizeTheme,
    readStoredTheme,
    systemTheme,
    createThemeController,
    connectThemeToggle,
  };
});
