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
  assert.equal(Object.keys(manifest.assets).length, 4);
  assert.equal(assetNames.length, 4);
  assert.doesNotMatch(index, /(?:href|src)="(?:assets\/styles\.css|src\/app\.js)"/);
  assert.match(index, /href="assets\/styles\.[0-9a-f]{12}\.css"/);
  assert.match(index, /src="assets\/app\.[0-9a-f]{12}\.js"/);
  assert.match(index, /id="rage-target-level"[^>]+value="101"/);
  assert.match(index, /id="level-input"[^>]+max="301"/);
  assert.match(index, /id="rage-target-level"[^>]+max="301"/);
  assert.match(index, /id="rage-arc-p1"[^>]+max="100"[^>]+value="100"/);
  assert.match(index, /id="rage-arc-p5"[^>]+max="100"[^>]+value="90"/);
  assert.match(index, /id="rage-unlock-toggle"[^>]+aria-expanded="true"/);

  for (const outputPath of Object.values(manifest.assets)) {
    const expectedHash = outputPath.match(/\.([0-9a-f]{12})\.[^.]+$/)?.[1];
    assert.ok(expectedHash, `${outputPath} includes a content fingerprint`);
    const contents = await readFile(new URL(outputPath, DIST));
    assert.equal(contentHash(contents), expectedHash, `${outputPath} fingerprint matches its bytes`);
  }

  const app = await readFile(new URL(manifest.assets["src/app.js"], DIST), "utf8");
  assert.match(app, /from "\.\/core\.[0-9a-f]{12}\.js"/);
  assert.match(app, /fetch\("assets\/gb-analysis\.[0-9a-f]{12}\.json"\)/);
  assert.doesNotMatch(app, /(?:\.\/core\.js|data\/gb-analysis\.json)/);
});
