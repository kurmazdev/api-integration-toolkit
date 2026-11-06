import { test, expect } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  const history = await (await request.get("/api/runs")).json();
  if (history[0]?.status === "running")
    await request.post(`/api/runs/${history[0].id}/stop`, {
      headers: { "X-Toolkit-Request": "1" },
    });
  const reset = await request.post("/api/reset", {
    headers: { "X-Toolkit-Request": "1" },
  });
  expect(reset.ok()).toBeTruthy();
});

test("preview → sync → inspect → export → replay", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Integration workspace" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Run sync", exact: true }),
  ).toBeDisabled();
  await page.screenshot({
    path: "../docs/screenshots/workspace.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Test & preview" }).click();
  await expect(page.getByRole("status")).toContainText("Connection verified");
  await expect(page.getByRole("cell", { name: "ORD-0001" })).toBeVisible();
  await page.getByRole("button", { name: "Run sync", exact: true }).click();
  await expect(page.getByLabel("Run details")).toContainText("completed");
  await expect(page.getByRole("tab", { name: "Synced records" })).toContainText(
    "23",
  );
  await page.screenshot({
    path: "../docs/screenshots/synchronized.png",
    fullPage: true,
  });
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "CSV", exact: true }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("orders.csv");
  const replayResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/runs") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Replay all" }).click();
  const replay = await (await replayResponse).json();
  await expect(page.getByLabel("Run details")).toContainText(
    replay.id.slice(0, 8),
  );
  await expect(page.getByLabel("Run details")).toContainText("completed");
  await expect(page.getByRole("tab", { name: "Synced records" })).toContainText(
    "23",
  );
  await page.getByRole("button", { name: "Run history" }).click();
  await expect(page.locator(".history-table tbody tr")).toHaveCount(2);
});

test("broken cursor shows actionable diagnosis and resumes without duplicates", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Test & preview" }).click();
  await expect(page.getByRole("status")).toContainText("Connection verified");
  await page
    .getByLabel("Demo scenario", { exact: true })
    .selectOption("pagination");
  await page.getByRole("button", { name: "Run sync", exact: true }).click();
  await expect(page.getByLabel("Run details")).toContainText("failed");
  await expect(page.getByRole("log")).toContainText(
    "repeated its current cursor",
  );
  await expect(page.getByRole("tab", { name: "Synced records" })).toContainText(
    "5",
  );
  await page.screenshot({
    path: "../docs/screenshots/pagination-failure.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Fix demo & resume" }).click();
  await expect(page.getByLabel("Run details")).toContainText("completed");
  await expect(page.getByRole("tab", { name: "Synced records" })).toContainText(
    "23",
  );
});

test("stop slow run and resume at a committed checkpoint", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Test & preview" }).click();
  await expect(page.getByRole("status")).toContainText("Connection verified");
  await page.getByLabel("Demo scenario", { exact: true }).selectOption("slow");
  await page.getByRole("button", { name: "Run sync", exact: true }).click();
  await expect(page.getByRole("log")).toContainText("Page 1:");
  await page.getByRole("button", { name: "Stop run" }).click();
  await expect(page.getByLabel("Run details")).toContainText("cancelled");
  await page.getByRole("button", { name: "Fix demo & resume" }).click();
  await expect(page.getByLabel("Run details")).toContainText("completed");
  await expect(page.getByRole("tab", { name: "Synced records" })).toContainText(
    "23",
  );
});

test("mobile navigation and reset confirmation", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Connection", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "../docs/screenshots/mobile.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Debugging guide" }).click();
  await expect(
    page.getByRole("heading", { name: "Reproduce a broken integration" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Integration", exact: true }).click();
  await page
    .getByRole("button", { name: "Reset workspace", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "Keep workspace" }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
});
