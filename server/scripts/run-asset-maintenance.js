#!/usr/bin/env node
import { runMaintenance } from '../src/asset-builder/maintenance/assetMaintenance.js';

/**
 * External-scheduler entrypoint (cron, a Routine, a CI job, ...) for the
 * Academic Asset Builder's maintenance sweep. Never invoked by the Express
 * app or during a student session — see maintenance/assetMaintenance.js.
 *
 * Usage: node scripts/run-asset-maintenance.js
 */
async function main() {
  console.log('Running asset library maintenance sweep...');
  const report = await runMaintenance();

  console.log(`\nChecked ${report.checked} asset(s).`);
  console.log(`Broken/missing: ${report.broken.length}`);
  console.log(`Replaced: ${report.replaced.length}`);
  if (report.stillBroken.length) {
    console.warn(`Still broken (needs manual attention): ${report.stillBroken.length}`);
    console.warn(report.stillBroken.join(', '));
  }
}

main().catch((err) => {
  console.error('Maintenance run failed:', err);
  process.exit(1);
});
