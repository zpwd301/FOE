const test = require("node:test");
const assert = require("node:assert/strict");

const {
  STORAGE_KEY,
  connectThemeToggle,
  createThemeController,
  normalizeTheme,
  readStoredTheme,
  systemTheme,
} = require("../src/theme.js");

function memoryStorage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem(key) {
      return values.has(key) ? values.get(key) : null;
    },
    setItem(key, value) {
      values.set(key, value);
    },
    value(key) {
      return values.get(key);
    },
  };
}

function mediaQuery(matches = false) {
  let listener = null;
  return {
    matches,
    addEventListener(event, callback) {
      if (event === "change") listener = callback;
    },
    change(nextMatches) {
      this.matches = nextMatches;
      listener?.({ matches: nextMatches });
    },
  };
}

function themeElement() {
  return { dataset: {} };
}

function themeButton() {
  const attributes = new Map();
  let clickListener = null;
  return {
    title: "",
    setAttribute(name, value) {
      attributes.set(name, value);
    },
    getAttribute(name) {
      return attributes.get(name);
    },
    addEventListener(event, callback) {
      if (event === "click") clickListener = callback;
    },
    click() {
      clickListener?.();
    },
  };
}

test("theme values are strictly validated", () => {
  assert.equal(normalizeTheme("light"), "light");
  assert.equal(normalizeTheme("dark"), "dark");
  assert.equal(normalizeTheme("system"), null);
  assert.equal(normalizeTheme({ toString: () => "dark" }), null);
});

test("stored theme wins over the system preference", () => {
  const storage = memoryStorage({ [STORAGE_KEY]: "light" });
  const media = mediaQuery(true);
  const element = themeElement();
  const controller = createThemeController({ element, storage, mediaQuery: media });

  assert.equal(controller.start(), "light");
  assert.equal(controller.preference, "light");
  assert.equal(element.dataset.theme, "light");
});

test("system preference remains live until the user chooses a theme", () => {
  const storage = memoryStorage();
  const media = mediaQuery(false);
  const element = themeElement();
  const controller = createThemeController({ element, storage, mediaQuery: media });

  controller.start();
  assert.equal(controller.theme, "light");
  media.change(true);
  assert.equal(controller.theme, "dark");

  assert.equal(controller.toggle(), "light");
  assert.equal(storage.value(STORAGE_KEY), "light");
  media.change(false);
  media.change(true);
  assert.equal(controller.theme, "light");
});

test("invalid and unavailable storage safely fall back to the system", () => {
  const brokenStorage = {
    getItem() { throw new Error("blocked"); },
    setItem() { throw new Error("blocked"); },
  };
  const invalidStorage = memoryStorage({ [STORAGE_KEY]: "sepia" });

  assert.equal(readStoredTheme(brokenStorage), null);
  assert.equal(readStoredTheme(invalidStorage), null);
  assert.equal(systemTheme(mediaQuery(true)), "dark");

  const controller = createThemeController({
    element: themeElement(),
    storage: brokenStorage,
    mediaQuery: mediaQuery(true),
  });
  assert.equal(controller.start(), "dark");
  assert.equal(controller.toggle(), "light");
});

test("subscribers receive initial and changed themes", () => {
  const controller = createThemeController({
    element: themeElement(),
    storage: memoryStorage(),
    mediaQuery: mediaQuery(false),
  });
  const received = [];

  controller.start();
  const unsubscribe = controller.subscribe((theme, preference) => received.push([theme, preference]));
  controller.set("dark");
  unsubscribe();
  controller.set("light");

  assert.deepEqual(received, [["light", null], ["dark", "dark"]]);
});

test("theme toggle stays synchronized and changes the selected theme", () => {
  const button = themeButton();
  const icon = { textContent: "" };
  const label = { textContent: "" };
  const documentObject = {
    getElementById(id) {
      if (id === "themeToggle") return button;
      if (id === "themeToggleIcon") return icon;
      if (id === "themeToggleLabel") return label;
      return null;
    },
  };
  const controller = createThemeController({
    element: themeElement(),
    storage: memoryStorage(),
    mediaQuery: mediaQuery(false),
  });

  controller.start();
  connectThemeToggle(controller, documentObject);
  assert.equal(button.getAttribute("aria-label"), "Switch to dark mode");
  assert.equal(button.title, "Switch to dark mode");
  assert.equal(icon.textContent, "☾");
  assert.equal(label.textContent, "Dark Mode");

  button.click();
  assert.equal(controller.theme, "dark");
  assert.equal(button.getAttribute("aria-label"), "Switch to light mode");
  assert.equal(button.title, "Switch to light mode");
  assert.equal(icon.textContent, "☀");
  assert.equal(label.textContent, "Light Mode");
});
