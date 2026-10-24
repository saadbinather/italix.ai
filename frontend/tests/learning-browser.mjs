import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { join } from "node:path";
import { chromium } from "playwright-core";

const origin = "http://127.0.0.1:3000";
const unlockSecret = process.env.ITALIX_OPERATOR_UNLOCK_SECRET ?? "";
assert.ok(unlockSecret.length >= 32, "persistent operator unlock secret is required");

const browser = await chromium.launch({
  executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: true,
});
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, reducedMotion: "reduce" });
  const page = await context.newPage();
  await page.goto(`${origin}/learning`, { waitUntil: "networkidle" });
  await page.getByPlaceholder("Operator unlock secret").fill(unlockSecret);
  await page.getByRole("button", { name: "Unlock playground" }).click();
  await page.getByText("No LoRA adapter is production-qualified").waitFor({ timeout: 15_000 });

  const apiResponse = await context.request.get(`${origin}/api/operator/learning`);
  assert.equal(apiResponse.status(), 200);
  const apiText = await apiResponse.text();
  assert.ok(apiText.length < 50_000, "sanitized learning response is unexpectedly large");
  for (const forbidden of ["prompt_json", "response_text", "training_losses", "validation_losses", "adapter_path", "log_path", "metrics_json", "examples"]) {
    assert.equal(apiText.includes(`\"${forbidden}\"`), false, `sensitive field ${forbidden} reached the browser`);
  }
  const data = JSON.parse(apiText);
  assert.equal(Array.isArray(data.queues), true);
  assert.equal(Array.isArray(data.jobs), true);
  assert.equal(Array.isArray(data.models), true);
  assert.equal(data.summary.qualified_adapters, 0);

  await mkdir(join(process.cwd(), "artifacts", "screenshots"), { recursive: true });
  await page.screenshot({ path: join(process.cwd(), "artifacts", "screenshots", "learning-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 500, height: 1000 });
  await page.screenshot({ path: join(process.cwd(), "artifacts", "screenshots", "learning-mobile.png"), fullPage: true });

  console.log(JSON.stringify({
    pending_examples: data.summary.pending_examples,
    completed_jobs: data.summary.completed_jobs,
    experimental_adapters: data.summary.experimental_adapters,
    qualified_adapters: data.summary.qualified_adapters,
    response_bytes: apiText.length,
  }));
} finally {
  await browser.close();
}
