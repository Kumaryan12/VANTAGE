import { test, expect } from "@playwright/test";

test("actual research forecasts, saved explanations, report and reproduction", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await page
    .getByRole("button", { name: "Quantitative Research", exact: true })
    .click();
  await page.getByLabel("Maximum boosting rounds").fill("40");
  await page.getByLabel("Validation candidates").selectOption("2");
  await page.getByRole("button", { name: "Run controlled experiment" }).click();
  await expect(
    page.getByRole("heading", { name: "Model challenger leaderboard" }),
  ).toBeVisible({ timeout: 30000 });
  await expect(page.locator(".research-leaderboard tbody tr")).toHaveCount(4);
  await expect(page.locator(".research-leaderboard")).toContainText(
    "100 common / 100 requested",
  );
  await expect(page.locator(".research-source")).toContainText(
    "SYNTHETIC RESEARCH DATA",
  );
  await expect(
    page.getByRole("heading", { name: "Volatility regime explorer" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Explain saved prediction", exact: true })
    .click();
  await expect(
    page
      .locator(".simulation-stats > div")
      .filter({ hasText: "Reconstruction residual" }),
  ).toBeVisible();
  const artifact = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download saved artifacts" }).click();
  expect((await artifact).suggestedFilename()).toMatch(/\.zip$/);
  const report = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download research report" }).click();
  expect((await report).suggestedFilename()).toMatch(/\.md$/);
  await page.getByLabel("Research evaluation start").fill("2026-09-01");
  await page.getByRole("button", { name: "Apply evaluation window" }).click();
  await expect(page.locator(".research-leaderboard")).not.toContainText(
    "100 common / 100 requested",
  );
  await page
    .getByRole("button", { name: "Reproduce experiment", exact: true })
    .click();
  await expect(
    page.getByText("Saved-input reproduction match: true", { exact: true }),
  ).toBeVisible({ timeout: 30000 });
  const checks = page.locator(".research-history input[type=checkbox]");
  await expect(checks).toHaveCount(2);
  await checks.nth(0).check();
  await checks.nth(1).check();
  await page.getByRole("button", { name: "Compare experiments (2)" }).click();
  await expect(
    page.getByRole("heading", { name: "Experiment configuration comparison" }),
  ).toBeVisible();
  await page.screenshot({
    path: "../artifacts/phase3-research-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../artifacts/phase3-research-mobile.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
