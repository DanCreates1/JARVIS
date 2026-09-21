import { readFile } from "node:fs/promises";

const allowedLicenses = new Set([
  "(BSD-3-Clause OR GPL-2.0)",
  "(MIT OR Apache-2.0)",
  "(MIT OR CC0-1.0)",
  "0BSD",
  "Apache-2.0",
  "BSD-2-Clause",
  "BSD-3-Clause",
  "BlueOak-1.0.0",
  "CC-BY-4.0",
  "ISC",
  "MIT",
  "MIT AND Apache-2.0",
  "MPL-2.0",
  "Python-2.0",
  "Unlicense",
]);

const reviewedOverrides = new Map([
  // exit@0.1.2 omits package metadata but ships node_modules/exit/LICENSE-MIT.
  ["node_modules/exit", "MIT"],
]);

const lock = JSON.parse(await readFile(new URL("../package-lock.json", import.meta.url), "utf8"));
const violations = [];
let checkedPackages = 0;

for (const [packagePath, metadata] of Object.entries(lock.packages ?? {})) {
  if (!packagePath || metadata.link) {
    continue;
  }

  checkedPackages += 1;
  const license = reviewedOverrides.get(packagePath) ?? metadata.license;
  if (typeof license !== "string" || !allowedLicenses.has(license)) {
    violations.push(`${packagePath}: ${license ?? "missing license"}`);
  }
}

if (violations.length > 0) {
  console.error("Dependency license policy failed:");
  for (const violation of violations) {
    console.error(`- ${violation}`);
  }
  process.exitCode = 1;
} else {
  console.log(
    `Dependency license policy passed: ${checkedPackages} packages, ` +
      `${allowedLicenses.size} reviewed license expressions.`,
  );
}
