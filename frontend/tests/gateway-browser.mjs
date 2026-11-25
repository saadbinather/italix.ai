import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { mkdir } from "node:fs/promises";
import { createServer } from "node:http";
import { join } from "node:path";
import { chromium } from "playwright-core";

const host = "127.0.0.1";
const executablePath = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const operatorToken = process.env.ITALIX_OPERATOR_TOKEN ?? "";
assert.ok(operatorToken.length >= 32, "ITALIX_OPERATOR_TOKEN is required for the live browser test");

function listen(server) {
  return new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, host, () => resolve(server.address().port));
  });
}

const portServer = createServer();
const frontendPort = await listen(portServer);
await new Promise((resolve) => portServer.close(resolve));
const origin = `http://${host}:${frontendPort}`;
const unlockSecret = randomBytes(32).toString("base64url");
const sessionSecret = randomBytes(32).toString("base64url");

const apiUrl = process.env.ITALIX_API_URL ?? "http://127.0.0.1:8000";
const health = await fetch(`${apiUrl}/health`);
assert.equal(health.ok, true, "FastAPI must be running for live browser verification");

const next = spawn(
  join(process.cwd(), "node_modules", ".bin", "next"),
  ["start", "--hostname", host, "--port", String(frontendPort)],
  {
    cwd: process.cwd(),
    env: {
      ...process.env,
      NODE_ENV: "production",
      ITALIX_API_URL: apiUrl,
      ITALIX_OPERATOR_TOKEN: operatorToken,
      ITALIX_OPERATOR_UNLOCK_SECRET: unlockSecret,
      ITALIX_SESSION_SECRET: sessionSecret,
    },
    stdio: ["ignore", "pipe", "pipe"],
  },
);
let output = "";
next.stdout.on("data", (chunk) => { output += chunk.toString(); });
next.stderr.on("data", (chunk) => { output += chunk.toString(); });

async function waitForServer() {
  for (let attempt = 0; attempt < 80; attempt += 1) {
    if (next.exitCode !== null) throw new Error(`Next.js exited early: ${output}`);
    try {
      const response = await fetch(`${origin}/gateway`);
      if (response.ok) return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`Next.js did not start: ${output}`);
}

let browser;
try {
  await waitForServer();
  browser = await chromium.launch({ executablePath, headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, reducedMotion: "reduce" });
  const page = await context.newPage();
  await page.goto(`${origin}/gateway`, { waitUntil: "networkidle" });

  await page.getByPlaceholder("Operator unlock secret").fill(unlockSecret);
  await page.getByRole("button", { name: "Unlock playground" }).click();
  await page.getByText("Operator session unlocked").waitFor();
  const sessionCookie = (await context.cookies()).find((cookie) => cookie.name === "italix_operator_session");
  assert.ok(sessionCookie, "operator session cookie was not created");
  assert.equal(sessionCookie.httpOnly, true);
  assert.equal(sessionCookie.secure, true);
  assert.equal(sessionCookie.sameSite, "Strict");

  await page.getByRole("button", { name: "Load safe sample" }).click();
  await page.getByRole("button", { name: /^Generate/ }).click();
  await page.getByTestId("response-output").waitFor({ timeout: 30_000 });

  const evidence = {
    response: (await page.getByTestId("response-output").innerText()).trim(),
    model: (await page.getByTestId("response-model").innerText()).trim(),
    route: (await page.getByTestId("response-route").innerText()).trim(),
    latency: (await page.getByTestId("response-latency").innerText()).trim(),
    trace_id: (await page.getByTestId("response-trace").innerText()).trim(),
  };
  assert.equal(evidence.model, "pr-summary-deterministic-v1");
  assert.equal(evidence.route, "deterministic");
  assert.match(evidence.latency, /^\d+(?:\.\d)? ms$/);
  assert.ok(evidence.trace_id.length > 10);
  assert.match(evidence.response, /REQUEST_TIMEOUT_SECONDS/);

  const screenshotDirectory = process.env.ITALIX_GATEWAY_SCREENSHOTS ?? join(process.cwd(), "artifacts", "screenshots");
  await mkdir(screenshotDirectory, { recursive: true });
  await page.screenshot({ path: join(screenshotDirectory, "gateway-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 500, height: 1000 });
  await page.screenshot({ path: join(screenshotDirectory, "gateway-mobile.png"), fullPage: true });

  await page.getByLabel("Prompt or Git diff").fill(
    "diff --git a/logo.png b/logo.png\nnew file mode 100644\nBinary files /dev/null and b/logo.png differ",
  );
  await page.getByRole("button", { name: /^Generate/ }).click();
  await page.getByText("Abstained", { exact: true }).waitFor({ timeout: 30_000 });
  const abstentionOutput = (await page.getByTestId("response-output").innerText()).trim();

  await page.getByLabel("Workload").selectOption("hybrid_triage");
  await page.getByRole("button", { name: /^Generate/ }).click();
  const hybrid = page.getByTestId("hybrid-result");
  await hybrid.getByText(/Human review required/).waitFor();
  const patchPath = "api/rate_limit/rules.py";
  await page.getByLabel("Prompt or Git diff").fill(
    `diff --git a/${patchPath} b/${patchPath}\n--- a/${patchPath}\n+++ b/${patchPath}\n@@ -1 +1 @@\n-LIMIT = 10\n+LIMIT = 5`,
  );
  await page.getByLabel("Select evidence with the local model").check();
  await page.getByRole("button", { name: /^Generate/ }).click();
  await hybrid.getByText(/deterministic_policy.*policy_validated/).waitFor({ timeout: 30_000 });
  assert.match(await hybrid.innerText(), /"risk": "medium"/);
  assert.match(await hybrid.innerText(), /Local model invocation attempted · Yes/);
  assert.match(await hybrid.innerText(), /Prompt tokens · \d+ · Output tokens · \d+/);
  assert.match(await hybrid.innerText(), /Code excerpts/);

  await page.getByRole("button", { name: "Lock session" }).click();
  await page.getByRole("button", { name: "Unlock playground" }).waitFor();
  const cookieAfterLogout = (await context.cookies()).find((cookie) => cookie.name === "italix_operator_session");
  assert.equal(cookieAfterLogout, undefined);

  console.log(JSON.stringify({ deterministic: evidence, binary_abstention: abstentionOutput }, null, 2));
} finally {
  if (browser) await browser.close();
  next.kill("SIGTERM");
}
