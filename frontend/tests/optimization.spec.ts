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

test("decision laboratory solves trade-offs, labeled sensitivity and identical stresses", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
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
    page.locator(".optimization-risk-comparison tbody tr"),
  ).toHaveCount(10);
  await page
    .getByRole("button", {
      name: "Compare identical stress scenario",
      exact: true,
    })
    .click();
  await expect(page.locator(".optimization-stress tbody tr")).toHaveCount(6, {
    timeout: 15000,
  });
  await expect(page.locator(".optimization-stress")).toContainText(
    "Current scenario P&L",
  );
  await page.getByLabel("Optimization stress kind").selectOption("historical");
  await page.getByLabel("Optimization scenario start").fill("2026-01-05");
  await page.getByLabel("Optimization scenario end").fill("2026-03-31");
  const response = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/v1/optimization/counterfactual") &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", {
      name: "Compare identical stress scenario",
      exact: true,
    })
    .click();
  expect((await response).status()).toBe(200);
  await page
    .getByRole("button", { name: "Calculate risk–turnover curve", exact: true })
    .click();
  await expect(page.locator(".optimization-job")).toContainText(
    "COMPLETED · mixed",
    { timeout: 20000 },
  );
  await expect(page.locator(".optimization-study tbody tr")).toHaveCount(5);
  await expect(
    page.locator(".optimization-study tbody tr").first(),
  ).toContainText("infeasible");
  await page
    .getByRole("button", { name: "Inspect point 4", exact: true })
    .click();
  await expect(page.locator(".optimization-allocation tbody tr")).toHaveCount(
    6,
  );
  await page.getByLabel("Optimization sensitivity variations").fill(
    JSON.stringify([
      { kind: "window", value: 126 },
      { kind: "shrinkage", value: 0.1 },
      { kind: "max_weight", value: 0.25 },
      { kind: "sector_max", sector: "Technology", value: 0.15 },
      { kind: "turnover", value: 0.1 },
      { kind: "cost_penalty", value: 5 },
    ]),
  );
  await page
    .getByRole("button", { name: "Run sensitivity study", exact: true })
    .click();
  await expect(page.locator(".optimization-job")).toContainText("COMPLETED", {
    timeout: 20000,
  });
  await expect(page.locator(".optimization-study tbody tr")).toHaveCount(7);
  await page
    .getByRole("button", { name: "Inspect point 2", exact: true })
    .click();
  await expect(page.getByText(/126 daily returns/)).toBeVisible();
  await page.screenshot({
    path: "../artifacts/phase5/decision-laboratory.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("human governance evidence gates and pinned optimization investigation", async ({
  page,
}) => {
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
  await expect(page.locator(".governance-status")).toContainText("candidate");
  const originalModel = await page
    .getByLabel("Governance model", { exact: true })
    .inputValue();
  await page
    .getByLabel("Governance rationale")
    .fill(
      "Automated browser fixture exercising the explicit methodological research review contract; no real-market approval.",
    );
  await page.getByLabel("Governance human research acknowledgement").check();
  await page
    .getByRole("button", { name: "Record human review decision", exact: true })
    .click();
  await expect(page.locator(".governance-status")).toContainText(
    "under_review",
  );
  await page.getByLabel("Governance decision").selectOption("validated");
  for (const area of [
    "out_of_sample",
    "var_coverage",
    "uncertainty",
    "data_quality",
    "leakage",
    "regime_stability",
    "complexity",
    "reproducibility_operations",
  ]) {
    await page
      .getByLabel(`Governance assessment ${area}`, { exact: true })
      .fill(
        "Synthetic browser contract fixture: evidence is methodological only; future investment validity is unassessed.",
      );
  }
  await page
    .getByLabel("Governance rationale")
    .fill(
      "Automated test of the evidence gate; not a financial approval or real human model review.",
    );
  await page.getByLabel("Governance human research acknowledgement").check();
  await page
    .getByRole("button", { name: "Record human review decision", exact: true })
    .click();
  await expect(page.locator(".model-governance")).toContainText(
    "Validation requires complete numerical/source checks",
  );
  await page
    .getByRole("button", { name: "Reproduce optimization", exact: true })
    .click();
  await expect(page.locator(".optimization-job")).toContainText(
    "Saved-input optimization reproduction match: true",
    { timeout: 20000 },
  );
  await page
    .getByLabel("Governance model", { exact: true })
    .selectOption(originalModel);
  await page.getByLabel("Governance decision").selectOption("validated");
  await page
    .getByRole("button", { name: "Record human review decision", exact: true })
    .click();
  await expect(page.locator(".governance-status")).toContainText(
    "Review status: validated",
  );
  await page
    .getByLabel("Governance decision")
    .selectOption("approved_research");
  await page
    .getByLabel("Governance rationale")
    .fill(
      "Automated fixture approval of methodological test use only, with synthetic and in-sample limitations preserved.",
    );
  await page.getByLabel("Governance human research acknowledgement").check();
  await page
    .getByRole("button", { name: "Record human review decision", exact: true })
    .click();
  await expect(page.locator(".governance-status")).toContainText(
    "approved_research",
  );
  await expect(page.locator(".model-governance tbody tr")).toHaveCount(4);
  await page
    .getByRole("button", { name: "AI Risk Assistant", exact: true })
    .click();
  await page
    .getByLabel("Investigation optimization")
    .selectOption({ index: 1 });
  await page
    .getByLabel("Investigation question", { exact: true })
    .fill(
      "Explain the saved optimization tradeoffs and actual risk comparison.",
    );
  await page
    .getByRole("button", { name: "Start investigation", exact: true })
    .click();
  await expect(page.locator(".agent-status")).toContainText("COMPLETED", {
    timeout: 20000,
  });
  await expect(page.locator(".agent-answer")).toContainText(
    "Portfolio optimization investigation",
  );
});
