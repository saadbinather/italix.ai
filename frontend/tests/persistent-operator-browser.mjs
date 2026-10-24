import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { chromium } from "playwright-core";

const origin = "http://127.0.0.1:3000";
const executablePath = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const unlockSecret = process.env.ITALIX_OPERATOR_UNLOCK_SECRET ?? "";
const sessionSecret = process.env.ITALIX_SESSION_SECRET ?? "";
assert.ok(unlockSecret.length >= 32 && sessionSecret.length >= 32, "persistent operator secrets are required");

const browser = await chromium.launch({ executablePath, headless: true });
try {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, reducedMotion: "reduce" });
  const page = await context.newPage();
  await page.goto(`${origin}/gateway`, { waitUntil: "networkidle" });

  const beforeUnlock = await context.request.post(`${origin}/api/operator/chat/completions`, {
    headers: { Origin: origin, "Content-Type": "application/json" },
    data: { messages: [{ role: "user", content: "synthetic unauthorized request" }] },
  });
  assert.equal(beforeUnlock.status(), 401);

  await page.getByPlaceholder("Operator unlock secret").fill(unlockSecret);
  await page.getByRole("button", { name: "Unlock playground" }).click();
  await page.getByText("Operator session unlocked").waitFor();
  const cookie = (await context.cookies()).find((item) => item.name === "italix_operator_session");
  assert.ok(cookie);
  assert.equal(cookie.httpOnly, true);
  assert.equal(cookie.secure, true);
  assert.equal(cookie.sameSite, "Strict");

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

  await page.getByRole("button", { name: "Lock session" }).click();
  await page.getByRole("button", { name: "Unlock playground" }).waitFor();
  assert.equal((await context.cookies()).some((item) => item.name === "italix_operator_session"), false);

  const expiredPayload = Buffer.from(JSON.stringify({ version: 1, expires: Date.now() - 1, nonce: "expired-browser-check" })).toString("base64url");
  const expiredSignature = createHmac("sha256", sessionSecret).update(expiredPayload).digest("base64url");
  await context.addCookies([{
    name: "italix_operator_session",
    value: `${expiredPayload}.${expiredSignature}`,
    url: origin,
    httpOnly: true,
    secure: true,
    sameSite: "Strict",
  }]);
  const expired = await context.request.post(`${origin}/api/operator/chat/completions`, {
    headers: { Origin: origin, "Content-Type": "application/json" },
    data: { messages: [{ role: "user", content: "synthetic expired-session request" }] },
  });
  assert.equal(expired.status(), 401);

  console.log(JSON.stringify(evidence, null, 2));
} finally {
  await browser.close();
}
