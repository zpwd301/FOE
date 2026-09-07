import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile, readdir } from "node:fs/promises";
import test from "node:test";

const DIST = new URL("../dist/", import.meta.url);

function contentHash(contents) {
  return createHash("sha256").update(contents).digest("hex").slice(0, 12);
}

test("static build fingerprints every cacheable resource and rewrites dependencies", async () => {
  const [index, manifestSource, assetNames] = await Promise.all([
    readFile(new URL("index.html", DIST), "utf8"),
    readFile(new URL("asset-manifest.json", DIST), "utf8"),
    readdir(new URL("assets/", DIST)),
  ]);
  const manifest = JSON.parse(manifestSource);

  assert.equal(manifest.algorithm, "sha256");
  assert.equal(manifest.hashLength, 12);
  assert.match(manifest.version, /^1\.0\.\d+$/);
  assert.equal(Object.keys(manifest.assets).length, 5);
  assert.equal(assetNames.length, 5);
  assert.doesNotMatch(index, /(?:href|src)="(?:assets\/styles\.css|src\/app\.js)"/);
  assert.match(index, /href="assets\/styles\.[0-9a-f]{12}\.css"/);
  assert.match(index, /src="assets\/app\.[0-9a-f]{12}\.js"/);
  assert.match(index, /id="rage-target-level"[^>]+value="101"/);
  assert.match(index, /id="level-input"[^>]+max="301"/);
  assert.match(index, /id="rage-target-level"[^>]+max="301"/);
  assert.match(index, /Dashboard v1\.0\.\d+/);
  assert.doesNotMatch(index, /FoE Helper 4\.8\.1\.0 · exact FP \+ medal data/);
  assert.match(index, /id="rage-arc-p1"[^>]+max="180"[^>]+value="180"/);
  assert.match(index, /id="rage-arc-p5"[^>]+max="180"[^>]+value="80"/);
  assert.match(index, /id="rage-unlock-toggle"[^>]+aria-expanded="true"/);
  assert.match(index, /id="rage-unlock-toggle-label">Hide unlocking costs</);
  assert.doesNotMatch(index, /(?:metric-grid|metric-level|metric-cumulative|metric-coverage)/);
  assert.doesNotMatch(index, /class="method-note"/);
  assert.match(index, /id="building-benefit"/);
  assert.match(index, /data-reward-view="base"[^>]+aria-pressed="true"/);
  assert.match(index, /data-reward-view="boosted"[^>]+aria-pressed="false"/);
  assert.match(index, /id="owner-priming-cost"/);
  assert.match(index, /id="selected-total-fp-cost"/);
  assert.match(index, /id="selected-level-benefits"/);
  assert.match(index, /id="rage-benefit-toggle"[^>]+aria-expanded="true"/);
  assert.match(index, /id="rage-benefit-toggle-label">Hide GB benefits</);
  assert.ok(
    index.indexOf('id="curve-preview"') < index.indexOf('class="analysis-grid"'),
    "Curve preview replaces the former summary-card position",
  );
  assert.ok(
    index.indexOf('class="panel reward-panel"') < index.indexOf('class="analysis-side"'),
    "Contributor rewards span the row above the supporting panels",
  );
  assert.ok(
    index.indexOf('class="panel goods-panel"') < index.indexOf('id="unlock-costs"'),
    "Foundation goods appear to the left of unlock costs",
  );

  for (const outputPath of Object.values(manifest.assets)) {
    const expectedHash = outputPath.match(/\.([0-9a-f]{12})\.[^.]+$/)?.[1];
    assert.ok(expectedHash, `${outputPath} includes a content fingerprint`);
    const contents = await readFile(new URL(outputPath, DIST));
    assert.equal(contentHash(contents), expectedHash, `${outputPath} fingerprint matches its bytes`);
  }

  const app = await readFile(new URL(manifest.assets["src/app.js"], DIST), "utf8");
  assert.match(app, /from "\.\/core\.[0-9a-f]{12}\.js"/);
  assert.match(app, /fetch\("assets\/gb-analysis\.[0-9a-f]{12}\.json"\)/);
  assert.match(app, /fetch\("assets\/gb-benefits-source\.[0-9a-f]{12}\.json"\)/);
  assert.doesNotMatch(
    app,
    /(?:\.\/core\.js|data\/gb-analysis\.json|data\/gb-benefits-source\.json)/,
  );
});
