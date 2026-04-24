#!/usr/bin/env node
/**
 * TaxLens Wave Delivery Orchestrator
 *
 * Executes the 9-step wave delivery pattern using Claude Agent SDK.
 * Reads wave config from YAML, runs steps sequentially (respecting depends_on),
 * tracks progress, and supports resume-from-failure.
 *
 * Usage:
 *   npx ts-node orchestrator.ts --config waves/wave-37-form8889.yaml
 *   npx ts-node orchestrator.ts --config waves/wave-37-form8889.yaml --from tests
 *   npx ts-node orchestrator.ts --config waves/wave-37-form8889.yaml --step deploy
 *   npx ts-node orchestrator.ts --config waves/wave-37-form8889.yaml --dry-run
 *   npx ts-node orchestrator.ts --list
 */

import { readFileSync, writeFileSync, existsSync, readdirSync } from "fs";
import { join, resolve } from "path";
import * as yaml from "js-yaml";

// ── Types ──────────────────────────────────────────────────────────────────

interface WaveStep {
  name: string;
  id: string;
  agent: string;
  depends_on: string[];
  task: string;
  files?: string[];
  acceptance?: string[];
}

interface AgentConfig {
  display_name: string;
  model: string;
  permission_mode: string;
  system_prompt: string;
  max_turns: number;
}

interface WaveConfig {
  name: string;
  description: string;
  version_bump: string;
  feature: {
    wave_number: number;
    name: string;
    forms: string[];
    income_type: string | null;
    deduction_type: string | null;
    credit_type: string | null;
    schedule: string | null;
  };
  paths: {
    repo: string;
    engine: string;
    config: string;
    routes: string;
    mcp: string;
    main: string;
    tests: string;
  };
  deploy: {
    image: string;
    node: string;
    ssh_key: string;
    namespace: string;
    deployment: string;
    health_url: string;
  };
  steps: WaveStep[];
  agents: Record<string, AgentConfig>;
}

interface StepResult {
  step_id: string;
  step_name: string;
  status: "completed" | "failed" | "skipped";
  duration_ms: number;
  output: string;
  error?: string;
}

interface WaveProgress {
  wave: string;
  version: string;
  started_at: string;
  updated_at: string;
  completed_steps: string[];
  failed_step?: string;
  results: StepResult[];
}

// ── YAML Loader ────────────────────────────────────────────────────────────

function loadWaveConfig(configPath: string): WaveConfig {
  const raw = readFileSync(configPath, "utf-8");
  const config = yaml.load(raw) as WaveConfig;

  // Load agent definitions from template if not in wave config
  if (!config.agents) {
    const templatePath = join(__dirname, "templates", "wave-template.yaml");
    if (existsSync(templatePath)) {
      const template = yaml.load(readFileSync(templatePath, "utf-8")) as WaveConfig;
      config.agents = template.agents;
    }
  }

  return config;
}

// ── Progress Tracking ──────────────────────────────────────────────────────

function progressFilePath(config: WaveConfig): string {
  return join(__dirname, ".progress", `wave-${config.feature.wave_number}.json`);
}

function loadProgress(config: WaveConfig): WaveProgress | null {
  const path = progressFilePath(config);
  if (!existsSync(path)) return null;
  return JSON.parse(readFileSync(path, "utf-8"));
}

function saveProgress(config: WaveConfig, progress: WaveProgress): void {
  const dir = join(__dirname, ".progress");
  if (!existsSync(dir)) {
    const { mkdirSync } = require("fs");
    mkdirSync(dir, { recursive: true });
  }
  progress.updated_at = new Date().toISOString();
  writeFileSync(progressFilePath(config), JSON.stringify(progress, null, 2));
}

// ── Topological Sort ───────────────────────────────────────────────────────

function topoSort(steps: WaveStep[]): WaveStep[] {
  const byId = new Map(steps.map((s) => [s.id, s]));
  const visited = new Set<string>();
  const sorted: WaveStep[] = [];

  function visit(id: string) {
    if (visited.has(id)) return;
    visited.add(id);
    const step = byId.get(id);
    if (!step) throw new Error(`Unknown step dependency: ${id}`);
    for (const dep of step.depends_on) {
      visit(dep);
    }
    sorted.push(step);
  }

  for (const step of steps) visit(step.id);
  return sorted;
}

// ── Step Executor ──────────────────────────────────────────────────────────

async function executeStep(
  step: WaveStep,
  config: WaveConfig,
  dryRun: boolean
): Promise<StepResult> {
  const start = Date.now();
  const agent = config.agents?.[step.agent];

  const prompt = buildPrompt(step, config);

  console.log(`\n${"=".repeat(60)}`);
  console.log(`Step: ${step.name} (${step.id})`);
  console.log(`Agent: ${agent?.display_name || step.agent}`);
  console.log(`Files: ${step.files?.join(", ") || "none"}`);
  console.log(`${"=".repeat(60)}`);

  if (dryRun) {
    console.log(`[DRY RUN] Would execute:\n${prompt.slice(0, 500)}...`);
    return {
      step_id: step.id,
      step_name: step.name,
      status: "skipped",
      duration_ms: Date.now() - start,
      output: "[dry run]",
    };
  }

  try {
    // Try claude-agent-sdk query()
    let query: any;
    try {
      const sdk = await import("@anthropic-ai/claude-code");
      query = sdk.query;
    } catch {
      // SDK not available, fall back to CLI
    }

    let output = "";

    if (query) {
      const messages = await query({
        prompt,
        options: {
          maxTurns: agent?.max_turns || 30,
          model: agent?.model || "claude-opus-4-6",
          permissionMode: (agent?.permission_mode as any) || "acceptEdits",
          cwd: config.paths.repo,
          systemPrompt: agent?.system_prompt || "",
        },
      });

      for (const msg of messages) {
        if (msg.type === "text") output += msg.text + "\n";
      }
    } else {
      // CLI fallback
      const { execSync } = await import("child_process");
      const model = agent?.model || "claude-opus-4-6";
      const escapedPrompt = prompt.replace(/'/g, "'\\''");
      output = execSync(
        `claude --model ${model} --cwd "${config.paths.repo}" -p '${escapedPrompt}'`,
        {
          encoding: "utf-8",
          timeout: 600_000, // 10 min per step
          maxBuffer: 10 * 1024 * 1024,
        }
      );
    }

    console.log(`\nCompleted: ${step.name} (${Date.now() - start}ms)`);

    return {
      step_id: step.id,
      step_name: step.name,
      status: "completed",
      duration_ms: Date.now() - start,
      output: output.slice(-2000), // Keep last 2000 chars
    };
  } catch (err: any) {
    console.error(`\nFailed: ${step.name} — ${err.message}`);
    return {
      step_id: step.id,
      step_name: step.name,
      status: "failed",
      duration_ms: Date.now() - start,
      output: "",
      error: err.message,
    };
  }
}

// ── Prompt Builder ─────────────────────────────────────────────────────────

function buildPrompt(step: WaveStep, config: WaveConfig): string {
  const f = config.feature;
  let prompt = `# Wave ${f.wave_number}: ${f.name} — Step: ${step.name}\n\n`;
  prompt += `## Context\n`;
  prompt += `You are executing step "${step.name}" of the TaxLens wave delivery pattern.\n`;
  prompt += `Feature: ${f.name}\n`;
  prompt += `Version target: ${config.version_bump}\n`;
  if (f.forms.length) prompt += `Forms: ${f.forms.join(", ")}\n`;
  if (f.schedule) prompt += `Schedule: ${f.schedule}\n`;
  prompt += `\n## Task\n${step.task}\n`;

  if (step.files?.length) {
    prompt += `\n## Files to modify\n`;
    for (const file of step.files) {
      prompt += `- ${join(config.paths.repo, file)}\n`;
    }
    prompt += `\nRead each file before modifying it.\n`;
  }

  if (step.acceptance?.length) {
    prompt += `\n## Acceptance Criteria\n`;
    for (const criterion of step.acceptance) {
      prompt += `- [ ] ${criterion}\n`;
    }
  }

  prompt += `\n## Important\n`;
  prompt += `- Do NOT skip to other steps. Only complete this step.\n`;
  prompt += `- Follow existing code patterns in the TaxLens codebase.\n`;
  prompt += `- For phaseouts, use preliminary AGI to avoid circular dependency.\n`;
  prompt += `- For risk scoring, use additive points (not multiplicative).\n`;

  return prompt;
}

// ── Main Orchestrator ──────────────────────────────────────────────────────

async function run() {
  const args = process.argv.slice(2);

  // --list: show available wave configs
  if (args.includes("--list")) {
    const wavesDir = join(__dirname, "waves");
    if (!existsSync(wavesDir)) {
      console.log("No wave configs found. Create one in workflows/waves/");
      return;
    }
    const files = readdirSync(wavesDir).filter((f) => f.endsWith(".yaml"));
    console.log("Available wave configs:");
    for (const file of files) {
      const cfg = yaml.load(readFileSync(join(wavesDir, file), "utf-8")) as any;
      console.log(`  ${file} — ${cfg.name || "untitled"}`);
    }
    return;
  }

  // Parse args
  const configIdx = args.indexOf("--config");
  if (configIdx === -1 || !args[configIdx + 1]) {
    console.error("Usage: orchestrator.ts --config <wave-config.yaml> [--from <step-id>] [--step <step-id>] [--dry-run]");
    process.exit(1);
  }

  const configPath = resolve(args[configIdx + 1]);
  const dryRun = args.includes("--dry-run");
  const fromIdx = args.indexOf("--from");
  const fromStep = fromIdx !== -1 ? args[fromIdx + 1] : null;
  const stepIdx = args.indexOf("--step");
  const onlyStep = stepIdx !== -1 ? args[stepIdx + 1] : null;

  // Load config
  const config = loadWaveConfig(configPath);
  console.log(`\nWave: ${config.name}`);
  console.log(`Description: ${config.description}`);
  console.log(`Version: ${config.version_bump}`);
  console.log(`Steps: ${config.steps.length}`);
  if (dryRun) console.log(`Mode: DRY RUN`);

  // Topological sort
  const sortedSteps = topoSort(config.steps);

  // Filter steps based on --from or --step
  let stepsToRun = sortedSteps;
  if (onlyStep) {
    stepsToRun = sortedSteps.filter((s) => s.id === onlyStep);
    if (stepsToRun.length === 0) {
      console.error(`Step "${onlyStep}" not found. Available: ${sortedSteps.map((s) => s.id).join(", ")}`);
      process.exit(1);
    }
  } else if (fromStep) {
    const idx = sortedSteps.findIndex((s) => s.id === fromStep);
    if (idx === -1) {
      console.error(`Step "${fromStep}" not found. Available: ${sortedSteps.map((s) => s.id).join(", ")}`);
      process.exit(1);
    }
    stepsToRun = sortedSteps.slice(idx);
  }

  // Load or create progress
  let progress = loadProgress(config) || {
    wave: config.name,
    version: config.version_bump,
    started_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    completed_steps: [],
    results: [],
  };

  console.log(`\nExecution plan (${stepsToRun.length} steps):`);
  for (const step of stepsToRun) {
    const done = progress.completed_steps.includes(step.id);
    const marker = done ? "[done]" : "[pending]";
    console.log(`  ${marker} ${step.id}: ${step.name} (agent: ${step.agent})`);
  }

  // Execute steps
  for (const step of stepsToRun) {
    // Skip already-completed steps (unless --step forces re-run)
    if (!onlyStep && progress.completed_steps.includes(step.id)) {
      console.log(`\nSkipping ${step.name} (already completed)`);
      continue;
    }

    // Verify dependencies completed
    for (const dep of step.depends_on) {
      if (!progress.completed_steps.includes(dep)) {
        console.error(`\nCannot run ${step.name}: dependency "${dep}" not completed`);
        console.error(`Run with --from ${dep} to start from the missing dependency`);
        process.exit(1);
      }
    }

    const result = await executeStep(step, config, dryRun);
    progress.results.push(result);

    if (result.status === "completed" || result.status === "skipped") {
      progress.completed_steps.push(step.id);
      delete progress.failed_step;
    } else {
      progress.failed_step = step.id;
      saveProgress(config, progress);
      console.error(`\nWave halted at step: ${step.name}`);
      console.error(`Resume with: --from ${step.id}`);
      process.exit(1);
    }

    saveProgress(config, progress);
  }

  // Summary
  console.log(`\n${"=".repeat(60)}`);
  console.log(`Wave ${config.feature.wave_number} complete!`);
  console.log(`Steps: ${progress.completed_steps.length}/${config.steps.length}`);
  const totalMs = progress.results.reduce((sum, r) => sum + r.duration_ms, 0);
  console.log(`Total time: ${(totalMs / 1000).toFixed(1)}s`);
  console.log(`${"=".repeat(60)}`);
}

run().catch((err) => {
  console.error("Orchestrator error:", err);
  process.exit(1);
});
