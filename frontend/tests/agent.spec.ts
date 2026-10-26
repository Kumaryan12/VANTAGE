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

test("document citations, hypothetical shock and executed golden evaluation remain usable on mobile", async ({
  page,
}) => {
  test.setTimeout(60000);
  const { execFileSync } = await import("node:child_process");
  const pdf = execFileSync(
    process.env.VANTAGE_PYTHON || "../backend/.venv/bin/python",
    [
      "-c",
      "import sys; from app.agent.fixtures import pdf_bytes, LIQUIDITY, DEBT; sys.stdout.buffer.write(pdf_bytes([LIQUIDITY, DEBT]))",
    ],
  );
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page
    .getByRole("button", { name: "AI Risk Assistant", exact: true })
    .click();
  await page
    .getByLabel("Financial PDF", { exact: true })
    .setInputFiles({
      name: "synthetic-risk.pdf",
      mimeType: "application/pdf",
      buffer: pdf,
    });
  await page
    .getByLabel("Document source", { exact: true })
    .fill("Permitted synthetic company disclosure");
  await page
    .getByLabel("Document company", { exact: true })
    .fill("SYNTHETIC_CO");
  await page.getByLabel("Document reporting period").fill("FY2026");
  await page.getByLabel("Document processing permission").check();
  await page.getByRole("button", { name: "Upload and index PDF" }).click();
  const document = page
    .locator(".document-library tbody tr")
    .filter({ hasText: "synthetic-risk.pdf" });
  await expect(document).toContainText("ready", { timeout: 20000 });
  await page.getByLabel("Use document synthetic-risk.pdf").check();
  await page
    .getByLabel("Financial document search", { exact: true })
    .fill("liquidity refinancing");
  await page.getByRole("button", { name: "Search document evidence" }).click();
  await expect(
    page.locator(".document-library blockquote").first(),
  ).toContainText("Cash reserves");
  await page.getByRole("button", { name: "Document research example" }).click();
  await page
    .getByRole("button", { name: "Start investigation", exact: true })
    .click();
  await expect(page.locator(".agent-status")).toContainText("COMPLETED", {
    timeout: 20000,
  });
  await expect(page.locator(".agent-citations")).toContainText("page 1");
  await expect(page.locator(".agent-answer")).toContainText(
    "citations: passed",
  );
  await page
    .getByRole("button", { name: "Inspect cited passage" })
    .first()
    .click();
  await expect(page.locator(".agent-citations pre").first()).toContainText(
    "Liquidity",
  );
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download source PDF" }).first().click();
  expect((await download).suggestedFilename()).toBe("synthetic-risk.pdf");
  await page.getByRole("button", { name: "Sector shock example" }).click();
  await page
    .getByRole("button", { name: "Start investigation", exact: true })
    .click();
  await expect(
    page
      .locator(".agent-answer tbody tr")
      .filter({ hasText: "Hypothetical scenario P&L" }),
  ).toContainText("85,718.24", { timeout: 20000 });
  await expect(page.locator(".agent-answer")).toContainText("not a forecast");
  await page.getByRole("button", { name: "Run golden evaluation" }).click();
  await expect(page.locator(".agent-evaluation")).toContainText(
    "acceptance passed",
    { timeout: 40000 },
  );
  await expect(page.locator(".agent-evaluation-cases details")).toHaveCount(60);
  await page.screenshot({
    path: "../artifacts/phase4-terminal-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../artifacts/phase4-terminal-mobile.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Delete document synthetic-risk.pdf" })
    .click();
  await expect(page.locator(".document-library")).toContainText(
    "No uploaded financial documents",
  );
  expect(errors).toEqual([]);
});
