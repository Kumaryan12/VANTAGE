import { test, expect } from "@playwright/test";

test("verified investigation uses accessible research and retains an auditable trace", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page
    .getByRole("button", { name: "AI Risk Assistant", exact: true })
    .click();
  await expect(page.getByRole("main")).toContainText(
    "AI provider not configured",
  );
  await page
    .getByRole("button", { name: "Start investigation", exact: true })
    .click();
  await expect(page.locator(".agent-answer")).toContainText(
    "No completed research experiment",
    { timeout: 20000 },
  );
  await expect(page.locator(".agent-status")).toContainText("LIMITED");
  await page
    .getByRole("button", { name: "Quantitative Research", exact: true })
    .click();
  await page.getByLabel("Maximum boosting rounds").fill("40");
  await page.getByLabel("Validation candidates").selectOption("2");
  await page.getByRole("button", { name: "Run controlled experiment" }).click();
  await expect(
    page.getByRole("heading", { name: "Model challenger leaderboard" }),
  ).toBeVisible({ timeout: 30000 });
  await page
    .getByRole("button", { name: "AI Risk Assistant", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Start investigation", exact: true })
    .click();
  await expect(page.locator(".agent-status")).toContainText("COMPLETED", {
    timeout: 20000,
  });
  await expect(page.locator(".agent-answer")).toContainText(
    "Deterministic demonstration",
  );
  await expect(
    page
      .locator(".agent-answer tr")
      .filter({ hasText: "Lowest observed average QLIKE" }),
  ).toContainText("rolling");
  await expect(page.locator(".agent-answer")).toContainText(
    "intervals include zero",
  );
  await expect(page.locator(".agent-answer")).toContainText("SYNTHETIC");
  await expect(page.locator(".agent-evidence")).toContainText(
    "compare_forecasting_models",
  );
  await expect(page.locator(".agent-activity")).toContainText(
    "Checked authoritative financial values",
  );
  const rows = page.locator(".agent-history tbody tr");
  await expect(rows).toHaveCount(2);
  await page.screenshot({
    path: "../artifacts/phase4-first-slice.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
