#!/usr/bin/env node
/**
 * Wave Workflow Manager
 *
 * Manage wave progress, create new waves from templates, and inspect state.
 *
 * Commands:
 *   manage.ts status <wave-number>         Show wave progress
 *   manage.ts reset <wave-number> [step]   Reset progress (all or from step)
 *   manage.ts new <wave-number> <name>     Create new wave config from template
 *   manage.ts validate <config.yaml>       Validate wave config (check deps, agents)
 *   manage.ts history                      Show all wave execution history
 */

import { readFileSync, writeFileSync, existsSync, readdirSync, mkdirSync, unlinkSync } from "fs";
import { join, resolve } from "path";
import * as yaml from "js-yaml";

const WORKFLOWS_DIR = __dirname;
const WAVES_DIR = join(WORKFLOWS_DIR, "waves");
const PROGRESS_DIR = join(WORKFLOWS_DIR, ".progress");
const TEMPLATE_PATH = join(WORKFLOWS_DIR, "templates", "wave-template.yaml");

// ── Status ─────────────────────────────────────────────────────────────────

function showStatus(waveNumber: number) {
  const progressPath = join(PROGRESS_DIR, `wave-${waveNumber}.json`);
  if (!existsSync(progressPath)) {
    console.log(`No progress found for Wave ${waveNumber}.`);

    // Check if config exists
    const configs = readdirSync(WAVES_DIR).filter((f) =>
      f.includes(`wave-${waveNumber}`)
    );
    if (configs.length) {
      console.log(`Config available: ${configs.join(", ")}`);
      console.log(`Run: npx ts-node orchestrator.ts --config waves/${configs[0]}`);
    }
    return;
  }

  const progress = JSON.parse(readFileSync(progressPath, "utf-8"));
  console.log(`\nWave: ${progress.wave}`);
  console.log(`Version: ${progress.version}`);
  console.log(`Started: ${progress.started_at}`);
  console.log(`Updated: ${progress.updated_at}`);
  console.log(`Completed: ${progress.completed_steps.length} steps`);
  if (progress.failed_step) {
    console.log(`Failed at: ${progress.failed_step}`);
  }

  console.log(`\nStep Results:`);
  for (const result of progress.results) {
    const icon = result.status === "completed" ? "+" : result.status === "skipped" ? "~" : "X";
    const time = `${(result.duration_ms / 1000).toFixed(1)}s`;
    console.log(`  [${icon}] ${result.step_name} (${time})${result.error ? ` — ${result.error}` : ""}`);
  }
}

// ── Reset ──────────────────────────────────────────────────────────────────

function resetProgress(waveNumber: number, fromStep?: string) {
  const progressPath = join(PROGRESS_DIR, `wave-${waveNumber}.json`);
  if (!existsSync(progressPath)) {
    console.log(`No progress to reset for Wave ${waveNumber}.`);
    return;
  }

  if (!fromStep) {
    unlinkSync(progressPath);
    console.log(`Reset all progress for Wave ${waveNumber}.`);
    return;
  }

  const progress = JSON.parse(readFileSync(progressPath, "utf-8"));
  const idx = progress.completed_steps.indexOf(fromStep);
  if (idx === -1) {
    console.log(`Step "${fromStep}" not in completed steps. No change.`);
    return;
  }

  const removed = progress.completed_steps.splice(idx);
  progress.results = progress.results.filter(
    (r: any) => !removed.includes(r.step_id)
  );
  delete progress.failed_step;
  progress.updated_at = new Date().toISOString();
  writeFileSync(progressPath, JSON.stringify(progress, null, 2));
  console.log(`Reset Wave ${waveNumber} from step "${fromStep}". Removed: ${removed.join(", ")}`);
}

// ── New Wave ───────────────────────────────────────────────────────────────

function createWave(waveNumber: number, featureName: string) {
  if (!existsSync(TEMPLATE_PATH)) {
    console.error(`Template not found at ${TEMPLATE_PATH}`);
    process.exit(1);
  }

  const slug = featureName
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  const outputPath = join(WAVES_DIR, `wave-${waveNumber}-${slug}.yaml`);

  if (existsSync(outputPath)) {
    console.error(`Config already exists: ${outputPath}`);
    process.exit(1);
  }

  let template = readFileSync(TEMPLATE_PATH, "utf-8");

  // Replace placeholders
  template = template.replace(/\{N\}/g, String(waveNumber));
  template = template.replace(/\{Feature Name\}/g, featureName);

  // Update wave number in YAML
  const config = yaml.load(template) as any;
  config.name = `Wave ${waveNumber}: ${featureName}`;
  config.feature.wave_number = waveNumber;
  config.feature.name = featureName;

  if (!existsSync(WAVES_DIR)) mkdirSync(WAVES_DIR, { recursive: true });
  writeFileSync(outputPath, yaml.dump(config, { lineWidth: 120, noRefs: true }));
  console.log(`Created: ${outputPath}`);
  console.log(`Edit the config, then run: npx ts-node orchestrator.ts --config waves/wave-${waveNumber}-${slug}.yaml`);
}

// ── Validate ───────────────────────────────────────────────────────────────

function validateConfig(configPath: string) {
  const raw = readFileSync(resolve(configPath), "utf-8");
  const config = yaml.load(raw) as any;
  const errors: string[] = [];

  // Check required fields
  if (!config.name) errors.push("Missing: name");
  if (!config.version_bump) errors.push("Missing: version_bump");
  if (!config.feature?.wave_number) errors.push("Missing: feature.wave_number");
  if (!config.steps?.length) errors.push("Missing: steps (empty or missing)");

  // Check step dependencies exist
  const stepIds = new Set(config.steps.map((s: any) => s.id));
  for (const step of config.steps || []) {
    if (!step.id) errors.push(`Step "${step.name}" missing id`);
    if (!step.agent) errors.push(`Step "${step.id}" missing agent`);
    for (const dep of step.depends_on || []) {
      if (!stepIds.has(dep)) {
        errors.push(`Step "${step.id}" depends on unknown step "${dep}"`);
      }
    }
  }

  // Check for circular dependencies
  try {
    const visited = new Set<string>();
    const visiting = new Set<string>();
    const byId = new Map(config.steps.map((s: any) => [s.id, s]));

    function checkCycle(id: string) {
      if (visiting.has(id)) throw new Error(`Circular dependency at: ${id}`);
      if (visited.has(id)) return;
      visiting.add(id);
      const step = byId.get(id);
      for (const dep of step?.depends_on || []) checkCycle(dep);
      visiting.delete(id);
      visited.add(id);
    }
    for (const step of config.steps) checkCycle(step.id);
  } catch (err: any) {
    errors.push(err.message);
  }

  // Check agents referenced by steps exist
  if (config.agents) {
    for (const step of config.steps || []) {
      if (step.agent && !config.agents[step.agent]) {
        errors.push(`Step "${step.id}" references unknown agent "${step.agent}"`);
      }
    }
  }

  if (errors.length) {
    console.error("Validation FAILED:");
    for (const err of errors) console.error(`  - ${err}`);
    process.exit(1);
  } else {
    console.log(`Valid: ${config.name} (${config.steps.length} steps, version ${config.version_bump})`);
  }
}

// ── History ────────────────────────────────────────────────────────────────

function showHistory() {
  if (!existsSync(PROGRESS_DIR)) {
    console.log("No execution history.");
    return;
  }

  const files = readdirSync(PROGRESS_DIR).filter((f) => f.endsWith(".json"));
  if (!files.length) {
    console.log("No execution history.");
    return;
  }

  console.log("Wave Execution History:\n");
  for (const file of files.sort()) {
    const progress = JSON.parse(readFileSync(join(PROGRESS_DIR, file), "utf-8"));
    const totalMs = progress.results.reduce((s: number, r: any) => s + r.duration_ms, 0);
    const status = progress.failed_step ? `FAILED at ${progress.failed_step}` : "COMPLETE";
    console.log(
      `  ${progress.wave} — ${status} — ${progress.completed_steps.length} steps — ${(totalMs / 1000).toFixed(1)}s — ${progress.updated_at}`
    );
  }
}

// ── CLI ────────────────────────────────────────────────────────────────────

const [, , command, ...rest] = process.argv;

switch (command) {
  case "status":
    showStatus(parseInt(rest[0], 10));
    break;
  case "reset":
    resetProgress(parseInt(rest[0], 10), rest[1]);
    break;
  case "new":
    createWave(parseInt(rest[0], 10), rest.slice(1).join(" "));
    break;
  case "validate":
    validateConfig(rest[0]);
    break;
  case "history":
    showHistory();
    break;
  default:
    console.log(`Usage:
  manage.ts status <wave-number>
  manage.ts reset <wave-number> [from-step]
  manage.ts new <wave-number> <feature-name>
  manage.ts validate <config.yaml>
  manage.ts history`);
}
