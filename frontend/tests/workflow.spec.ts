import { test, expect } from "@playwright/test";

test("credential-free demo, validated risk, controls and export", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Your portfolio, in perspective." }),
  ).toBeVisible();
  await expect(page.getByText("Analytics API connected")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Portfolio holdings" }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "NORTHSTAR Northstar Consumer" }),
  ).toBeVisible();
  await expect(
    page.getByText("Not actual account performance", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Confidence level").selectOption("0.99");
  await expect(
    page.getByText("Historical VaR · 99%", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Estimation window").selectOption("126");
  await expect(
    page.getByText("126 daily returns · 252 days / year"),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Risk Analytics", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Return correlation" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Scenario drawdown" }),
  ).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export risk run" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^vantage-risk-.*\.json$/);
  await page.getByRole("button", { name: "Portfolio", exact: true }).click();
  await page.getByLabel("Search holdings").fill("Northstar");
  await expect(page.locator("tbody tr")).toHaveCount(1);
  expect(errors).toEqual([]);
});

test("real account failures and imports are visible without synthetic fallback", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByText("Not actual account performance", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Portfolio mode").selectOption("kite");
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "Connect an authorized Zerodha account first.",
  );
  await expect(
    page.getByRole("heading", { name: "Portfolio holdings" }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Data Sources", exact: true }).click();
  await page.getByRole("button", { name: "Fetch observations" }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "FRED" }),
  ).toContainText("FRED_API_KEY");
  await page.getByLabel("History file").setInputFiles({
    name: "permitted-test.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "date,instrument,close,currency\n2026-01-01,NSE:TEST,100,INR\n2026-01-02,NSE:TEST,101,INR\n",
    ),
  });
  await page
    .getByLabel("Source and permission description")
    .fill("Synthetic browser-test data only");
  await page
    .getByLabel("Corporate-action adjustment")
    .selectOption("split_dividend_adjusted");
  await page.getByRole("button", { name: "Validate and import" }).click();
  await expect(page.getByRole("status")).toContainText(
    "Imported 2 validated observations",
  );
  await page.getByLabel("Portfolio mode").selectOption("demo");
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  await expect(
    page.getByText("Not actual account performance", { exact: true }),
  ).toBeVisible();
});

test("mobile navigation and tables remain usable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(
    page.getByText("Not actual account performance", { exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page
    .getByRole("button", { name: "Risk Analytics", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Return correlation" }),
  ).toBeVisible();
});
