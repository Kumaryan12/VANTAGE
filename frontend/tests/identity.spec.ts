import { test, expect } from "@playwright/test";

test("durable account, explicit legacy claim, private saved runs and cross-user denial", async ({
  page,
  browser,
}) => {
  const email = `browser-${Date.now()}@example.com`;
  const password = "Synthetic private browser passphrase 83!";
  await page.goto("/");
  await expect(
    page.getByRole("region", { name: "Portfolio metrics" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Account & Security", exact: true })
    .click();
  await page.getByLabel("Account email", { exact: true }).fill(email);
  await page.getByLabel("Account password", { exact: true }).fill(password);
  await page
    .getByRole("button", { name: "Register research account", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Registration processed",
  );
  await page.getByLabel("Account password", { exact: true }).fill(password);
  await page
    .getByRole("button", { name: "Sign in to account", exact: true })
    .click();
  await expect(
    page.getByText("Authenticated workspace", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Account & Security", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Sign out of account", exact: true }),
  ).toBeVisible();
  await Promise.all([
    page.waitForEvent("load"),
    page
      .getByRole("button", {
        name: "Claim this live legacy workspace",
        exact: true,
      })
      .click(),
  ]);
  await page
    .getByRole("button", { name: "Portfolio Optimization", exact: true })
    .click();
  const optimizationResponse = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/v1/optimization/run") &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Run portfolio optimization", exact: true })
    .click();
  const optimization = (await (await optimizationResponse).json()).id as string;
  await expect(page.locator(".optimization-job")).toContainText(
    "COMPLETED · optimal",
    { timeout: 20000 },
  );
  await expect(page.locator(".model-governance")).toContainText(
    "different explicitly assigned durable research reviewer",
  );
  await page
    .getByRole("button", { name: "Risk Analytics", exact: true })
    .click();
  const riskResponse = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/v1/risk/analysis") &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Calculate and save", exact: true })
    .click();
  const risk = (await (await riskResponse).json()).run_id as string;
  await page
    .getByRole("button", { name: "Account & Security", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Sign out of account", exact: true })
    .click();
  await expect(
    page.getByText("Temporary local guest", { exact: true }),
  ).toBeVisible();
  expect(
    (
      await page.request.get(`/api/v1/optimization/runs/${optimization}`)
    ).status(),
  ).toBe(404);
  await page
    .getByRole("button", { name: "Account & Security", exact: true })
    .click();
  await page.getByLabel("Account email", { exact: true }).fill(email);
  await page.getByLabel("Account password", { exact: true }).fill(password);
  await page
    .getByRole("button", { name: "Sign in to account", exact: true })
    .click();
  await expect(
    page.getByText("Authenticated workspace", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Portfolio Optimization", exact: true })
    .click();
  await page
    .locator(".optimization-history")
    .getByRole("button", { name: "Open optimization", exact: true })
    .first()
    .click();
  await expect(page.locator(".optimization-job")).toContainText(optimization);
  expect((await page.request.get(`/api/v1/risk/runs/${risk}`)).status()).toBe(
    200,
  );
  const cookies = await page.context().cookies();
  expect(cookies.find((c) => c.name === "vantage_auth")?.httpOnly).toBe(true);
  expect(await page.evaluate(() => Object.keys(localStorage))).toEqual([]);
  const isolated = await browser.newContext();
  const stranger = await isolated.newPage();
  await stranger.goto("/");
  const different = `stranger-${Date.now()}@example.com`;
  await stranger.request.post("/api/auth/register", {
    data: { email: different, password },
  });
  await stranger.request.post("/api/auth/login", {
    data: { email: different, password },
  });
  expect(
    (
      await stranger.request.get(`/api/v1/optimization/runs/${optimization}`)
    ).status(),
  ).toBe(404);
  expect(
    (await stranger.request.get(`/api/v1/risk/runs/${risk}`)).status(),
  ).toBe(404);
  await isolated.close();
});
