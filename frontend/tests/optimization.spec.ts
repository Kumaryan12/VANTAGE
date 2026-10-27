import { test, expect } from "@playwright/test";

test("saved minimum-variance allocation, constraints, infeasibility and exact saved-input replay", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await page
    .getByRole("button", { name: "Portfolio Optimization", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Run portfolio optimization", exact: true })
    .click();
  await expect(page.locator(".optimization-job")).toContainText(
    "COMPLETED · optimal",
    { timeout: 20000 },
  );
  await expect(
    page.getByRole("heading", { name: "Current versus proposed allocation" }),
  ).toBeVisible();
  await expect(page.locator(".optimization-overview")).toContainText(
    "not assumed zero",
  );
  await expect(page.locator(".optimization-allocation tbody tr")).toHaveCount(
    6,
  );
  const download = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Export optimization", exact: true })
    .click();
  expect((await download).suggestedFilename()).toMatch(
    /^vantage-optimization-.*\.json$/,
  );
  await page
    .getByRole("button", { name: "Reproduce optimization", exact: true })
    .click();
  await expect(page.locator(".optimization-job")).toContainText(
    "Saved-input optimization reproduction match: true",
    { timeout: 20000 },
  );
  await page.getByLabel("Optimization turnover percent").fill("0");
  await page
    .getByRole("button", { name: "Run portfolio optimization", exact: true })
    .click();
  await expect(page.locator(".optimization-job")).toContainText(
    "COMPLETED · infeasible",
    { timeout: 20000 },
  );
  await expect(page.locator(".optimization-overview")).toContainText(
    "Unavailable",
  );
  await expect(page.locator(".optimization-overview")).toContainText(
    "turnover",
  );
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
});
