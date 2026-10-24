import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";
import { createHmac, randomBytes } from "node:crypto";

const host = "127.0.0.1";
const operatorToken = randomBytes(32).toString("base64url");
const viewerToken = randomBytes(32).toString("base64url");
const unlockSecret = randomBytes(32).toString("base64url");
const sessionSecret = randomBytes(32).toString("base64url");
const backendRequests = [];

function listen(server) {
  return new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, host, () => resolve(server.address().port));
  });
}

async function availablePort() {
  const server = createServer();
  const port = await listen(server);
  await new Promise((resolve) => server.close(resolve));
  return port;
}

const backend = createServer((request, response) => {
  const chunks = [];
  request.on("data", (chunk) => chunks.push(chunk));
  request.on("end", () => {
    if (request.method === "GET" && request.url?.startsWith("/v1/training/queue")) {
      const workload = new URL(request.url, "http://mock").searchParams.get("workload") ?? "pr_summary";
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(JSON.stringify({ workload, counts: { pending: 1 }, pending: 1, minimum_examples: 10, enough_examples: false }));
      return;
    }
    if (request.method === "GET" && request.url?.startsWith("/v1/training/config")) {
      const workload = new URL(request.url, "http://mock").searchParams.get("workload") ?? "pr_summary";
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(JSON.stringify({ workload, engine: "MLX-LM", base_model: "mock-qwen", fine_tune_type: "LoRA", rank: 4, trainable_layers: 4, optimizer_steps: 20, learning_rate: 0.00002, batch_size: 1, max_sequence_length: 512, cloud_required: false, estimated_resources: { duration_seconds: "20-60", peak_mlx_memory_gb: 2, trainable_parameters: 1000 } }));
      return;
    }
    if (request.method === "GET" && request.url?.startsWith("/v1/training/jobs")) {
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(JSON.stringify({ data: [{ id: 1, workload: "pr_summary", example_count: 10, status: "completed", candidate_id: "adapter-test", created_at: "2026-01-01T00:00:00Z", completed_at: "2026-01-01T00:01:00Z", metrics: { duration_seconds: 60, training_losses: [2, 1], raw_examples: ["SENSITIVE_RAW_EXAMPLE"] } }] }));
      return;
    }
    if (request.method === "GET" && request.url === "/v1/models") {
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(JSON.stringify({ data: [{ id: "adapter-test", workload: "pr_summary", kind: "adapter", status: "experimental_failed", active: 0, created_at: "2026-01-01T00:00:00Z", path: "/private/path", metrics_json: JSON.stringify({ qualification_reason: "did not pass gates", response: "SENSITIVE_RAW_EXAMPLE" }) }] }));
      return;
    }
    if (request.method !== "POST" || request.url !== "/v1/chat/completions") {
      response.writeHead(404, { "Content-Type": "application/json" });
      response.end(JSON.stringify({ detail: "not found" }));
      return;
    }
    const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    backendRequests.push({ authorization: request.headers.authorization, body });
    if (body.model === "backend-error") {
      response.writeHead(503, { "Content-Type": "application/json" });
      response.end(JSON.stringify({ detail: "mock backend unavailable" }));
      return;
    }
    response.writeHead(200, {
      "Content-Type": "application/json",
      "x-italix-trace-id": "test-trace-id",
    });
    response.end(JSON.stringify({ id: "mock-completion", choices: [], italix: { route: "local" } }));
  });
});

const backendPort = await listen(backend);
const frontendPort = await availablePort();
const origin = `http://${host}:${frontendPort}`;
const next = spawn(
  join(process.cwd(), "node_modules", ".bin", "next"),
  ["start", "--hostname", host, "--port", String(frontendPort)],
  {
    cwd: process.cwd(),
    env: {
      ...process.env,
      NODE_ENV: "production",
      ITALIX_API_URL: `http://${host}:${backendPort}`,
      ITALIX_OPERATOR_TOKEN: operatorToken,
      ITALIX_VIEWER_TOKEN: viewerToken,
      ITALIX_OPERATOR_UNLOCK_SECRET: unlockSecret,
      ITALIX_SESSION_SECRET: sessionSecret,
    },
    stdio: ["ignore", "pipe", "pipe"],
  },
);

let serverOutput = "";
next.stdout.on("data", (chunk) => { serverOutput += chunk.toString(); });
next.stderr.on("data", (chunk) => { serverOutput += chunk.toString(); });

async function waitForFrontend() {
  for (let attempt = 0; attempt < 80; attempt += 1) {
    if (next.exitCode !== null) throw new Error(`Next.js exited early: ${serverOutput}`);
    try {
      const response = await fetch(origin);
      if (response.status > 0) return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`Next.js did not start: ${serverOutput}`);
}

function jsonHeaders(extra = {}) {
  return { "Content-Type": "application/json", Origin: origin, ...extra };
}

async function scanDirectory(directory, needles) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) await scanDirectory(path, needles);
    else {
      const content = await readFile(path);
      for (const needle of needles) assert.equal(content.includes(Buffer.from(needle)), false, `secret leaked into ${path}`);
    }
  }
}

try {
  await waitForFrontend();
  const chatUrl = `${origin}/api/operator/chat/completions`;
  const sessionUrl = `${origin}/api/operator/session`;
  const chatBody = { messages: [{ role: "user", content: "Summarize a harmless synthetic diff." }], workload: "pr_summary" };

  const initialSession = await fetch(sessionUrl);
  assert.equal(initialSession.status, 200);
  assert.deepEqual(await initialSession.json(), { authenticated: false });

  const unauthorized = await fetch(chatUrl, { method: "POST", headers: jsonHeaders(), body: JSON.stringify(chatBody) });
  assert.equal(unauthorized.status, 401);
  assert.equal(backendRequests.length, 0);

  const crossOrigin = await fetch(sessionUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json", Origin: "http://malicious.invalid" },
    body: JSON.stringify({ secret: unlockSecret }),
  });
  assert.equal(crossOrigin.status, 403);

  const invalidUnlock = await fetch(sessionUrl, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ secret: "incorrect-secret" }),
  });
  assert.equal(invalidUnlock.status, 401);

  const unlock = await fetch(sessionUrl, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ secret: unlockSecret }),
  });
  assert.equal(unlock.status, 200);
  const setCookie = unlock.headers.get("set-cookie") ?? "";
  assert.match(setCookie, /italix_operator_session=/);
  assert.match(setCookie, /HttpOnly/i);
  assert.match(setCookie, /Secure/i);
  assert.match(setCookie, /SameSite=strict/i);
  const cookie = setCookie.split(";", 1)[0];

  const valid = await fetch(chatUrl, {
    method: "POST",
    headers: jsonHeaders({ Cookie: cookie }),
    body: JSON.stringify(chatBody),
  });
  assert.equal(valid.status, 200);
  assert.equal(valid.headers.get("x-italix-trace-id"), "test-trace-id");
  assert.match(valid.headers.get("x-italix-latency-ms") ?? "", /^\d+(?:\.\d)$/);
  assert.equal(backendRequests.length, 1);
  assert.equal(backendRequests[0].authorization, `Bearer ${operatorToken}`);
  assert.equal(backendRequests[0].body.allow_cloud, false);
  assert.equal(backendRequests[0].body.capture, false);
  assert.equal(backendRequests[0].body.stream, false);

  const learning = await fetch(`${origin}/api/operator/learning`, { headers: { Cookie: cookie } });
  assert.equal(learning.status, 200);
  const learningText = await learning.text();
  assert.equal(learningText.includes("SENSITIVE_RAW_EXAMPLE"), false);
  assert.equal(learningText.includes("/private/path"), false);

  const invalidParameters = await fetch(chatUrl, {
    method: "POST",
    headers: jsonHeaders({ Cookie: cookie }),
    body: JSON.stringify({ ...chatBody, allow_cloud: "yes" }),
  });
  assert.equal(invalidParameters.status, 400);
  assert.equal(backendRequests.length, 1);

  const oversized = await fetch(chatUrl, {
    method: "POST",
    headers: jsonHeaders({ Cookie: cookie }),
    body: JSON.stringify({ messages: [{ role: "user", content: "x".repeat(70_000) }] }),
  });
  assert.equal(oversized.status, 413);
  assert.equal(backendRequests.length, 1);

  const backendError = await fetch(chatUrl, {
    method: "POST",
    headers: jsonHeaders({ Cookie: cookie }),
    body: JSON.stringify({ ...chatBody, model: "backend-error" }),
  });
  assert.equal(backendError.status, 503);

  const expiredPayload = Buffer.from(JSON.stringify({ version: 1, expires: Date.now() - 1, nonce: "expired" })).toString("base64url");
  const expiredSignature = createHmac("sha256", sessionSecret).update(expiredPayload).digest("base64url");
  const expired = await fetch(chatUrl, {
    method: "POST",
    headers: jsonHeaders({ Cookie: `italix_operator_session=${expiredPayload}.${expiredSignature}` }),
    body: JSON.stringify(chatBody),
  });
  assert.equal(expired.status, 401);

  const logout = await fetch(sessionUrl, { method: "DELETE", headers: { Origin: origin, Cookie: cookie } });
  assert.equal(logout.status, 200);
  assert.match(logout.headers.get("set-cookie") ?? "", /Max-Age=0/i);

  const bodies = [
    await unauthorized.text(),
    await invalidUnlock.text(),
    await valid.text(),
    await backendError.text(),
  ].join("\n");
  for (const secret of [operatorToken, viewerToken, unlockSecret, sessionSecret]) {
    assert.equal(bodies.includes(secret), false, "secret leaked in an HTTP response");
  }
  await scanDirectory(join(process.cwd(), ".next", "static"), [operatorToken, viewerToken, unlockSecret, sessionSecret]);

  console.log("operator security tests: 17 passed");
} finally {
  next.kill("SIGTERM");
  await new Promise((resolve) => backend.close(resolve));
}
