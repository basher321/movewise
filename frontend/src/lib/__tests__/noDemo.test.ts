// f01 / f03: no demo or sample data remains in the website code, the browser mock store is gone,
// and no page keeps business data in browser storage.

import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..", "..");

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return name === "__tests__" ? [] : files(path);
    return /\.(tsx?|css)$/.test(name) ? [path] : [];
  });
}

// Comments may explain the removal; the check reads the code without comments.
function code(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'])\/\/.*$/gm, "$1");
}

describe("live website code", () => {
  it("f01: the mock store, seed and storage files are gone", () => {
    for (const path of ["lib/api/seed.ts", "lib/api/storage.ts"]) {
      expect(existsSync(join(SRC, path)), path).toBe(false);
    }
    // The folder itself may remain empty (folders are not deleted by tools); it must hold no files.
    const mock = join(SRC, "lib/api/mock");
    expect(existsSync(mock) ? readdirSync(mock) : []).toEqual([]);
    for (const file of files(SRC)) {
      expect(readFileSync(file, "utf8"), relative(SRC, file)).not.toMatch(/api\/mock|api\/seed|api\/storage/);
    }
  });

  it('f03: no "demo", "mock", "sample" or "NextGen" in the code', () => {
    const found = files(SRC).filter((file) => /\b(demo|mock|sample)\b|nextgen/i.test(code(readFileSync(file, "utf8"))));
    expect(found.map((f) => relative(SRC, f).split(sep).join("/"))).toEqual([]);
  });

  it("f03: only the agent form remembers its inputs in browser storage", () => {
    const writers = files(SRC).filter((file) => /(localStorage|sessionStorage)\.setItem/.test(readFileSync(file, "utf8")));
    expect(writers.map((f) => relative(SRC, f).split(sep).join("/"))).toEqual(["lib/api/http/catalog.ts"]);
  });
});
