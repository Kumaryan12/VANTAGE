import { test, expect } from "@playwright/test";

test("advanced models, custom parameters, private history, comparison and exact replay", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(
    page.getByText("Not actual account performance", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Risk Analytics", exact: true })
    .click();
  await page.getByLabel("Advanced confidence percent").fill("97.5");
  await page.getByLabel("Simulation count").fill("2000");
  await page.getByLabel("Random seed", { exact: true }).fill("2026");
  await page.getByLabel("Covariance policy").selectOption("0.1");
  const firstResponse = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/v1/risk/analysis") &&
      r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Calculate and save" }).click();
  const first = await (await firstResponse).json();
  expect(first.parameters.confidence).toBe(0.975);
  expect(first.parameters.seed).toBe(2026);
  await expect(
    page.getByRole("heading", {
      name: "Correlated Monte Carlo P&L distribution",
    }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("region", { name: "VaR and Expected Shortfall comparison" })
      .locator("article"),
  ).toHaveCount(3);
  await expect(
    page.getByRole("heading", { name: "Security volatility contributions" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Risk concentration & reconciliation" }),
  ).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export comparison" }).click();
  expect((await downloadPromise).suggestedFilename()).toMatch(
    /^vantage-phase2-.*\.json$/,
  );
  await page.getByLabel("Random seed", { exact: true }).fill("2027");
  const secondResponse = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/v1/risk/analysis") &&
      r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Calculate and save" }).click();
  await secondResponse;
  await page.getByRole("button", { name: "Risk Runs", exact: true }).click();
  const checks = page.getByRole("checkbox");
  await expect(checks).toHaveCount(2);
  await checks.nth(0).check();
  await checks.nth(1).check();
  await page
    .getByRole("button", { name: "Compare selected (2)", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Saved run comparison" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Open run", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("heading", { name: /Archived snapshot/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Replay saved inputs" }).click();
  await expect(page.getByRole("status")).toContainText(
    "Reproducibility verified",
  );
  await expect(page.getByRole("status")).toContainText(
    "numerical results match: true",
  );
  expect(errors).toEqual([]);
});

test("stress mappings, unavailable historical events and synthetic replay", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByText("Not actual account performance", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Stress Testing", exact: true })
    .click();
  await page.getByLabel("Technology sector shock percent").fill("-20");
  const responsePromise = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/v1/risk/stress-test") &&
      r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Run stress scenario" }).click();
  const result = await (await responsePromise).json();
  expect(result.kind).toBe("stress");
  expect(
    result.assets.find((a: { sector: string }) => a.sector === "Technology")
      .shock_return,
  ).toBe(-0.2);
  await expect(
    page.getByRole("heading", { name: "Affected holdings & shock mapping" }),
  ).toBeVisible();
  await page.getByLabel("Scenario type").selectOption("historical");
  await expect(
    page
      .getByLabel("Named replay window")
      .locator('option[value="pandemic_2020"]'),
  ).toHaveAttribute("disabled", "");
  await page.getByLabel("Named replay window").selectOption("synthetic_2026");
  await page.getByRole("button", { name: "Run stress scenario" }).click();
  await expect(
    page.getByRole("heading", { name: "Buy-and-hold scenario path" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Scenario comparison", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "SYNTHETIC REPLAY: this is not an actual historical market event.",
      { exact: true },
    ),
  ).toBeVisible();
  await page.getByRole("button", { name: "Risk Runs", exact: true }).click();
  await page
    .getByRole("button", { name: "Open run", exact: true })
    .first()
    .click();
  await page.getByRole("button", { name: "Replay saved inputs" }).click();
  await expect(page.getByRole("status")).toContainText(
    "Reproducibility verified",
  );
});

test("advanced analysis stays within a mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(
    page.getByText("Not actual account performance", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page
    .getByRole("button", { name: "Risk Analytics", exact: true })
    .click();
  await page.getByLabel("Simulation count").fill("2000");
  await page.getByRole("button", { name: "Calculate and save" }).click();
  await expect(
    page.getByRole("heading", {
      name: "Correlated Monte Carlo P&L distribution",
    }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
