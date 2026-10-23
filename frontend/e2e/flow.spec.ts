import { expect, test } from "@playwright/test";

test("wybór gatunku → ranking → karta miejsca → przełączenie kalendarza (390×844)", async ({ page }) => {
  await page.goto("/#/ranking");
  // dane rzeczywiste puste w tym wdrożeniu → aplikacja proponuje dane demo i wyraźnie je oznacza
  await page.getByTestId("dataset").selectOption("demo");
  await page.getByTestId("species-top").selectOption("imleria_badia");
  await expect(page.getByTestId("demo-banner").first()).toBeVisible();

  const items = page.getByTestId("ranking-item");
  await expect(items.first()).toBeVisible();
  expect(await items.count()).toBeGreaterThan(3);
  // wskaźnik, nie "szansa" ani procent
  await expect(page.locator("body")).not.toContainText(/szansa|%\s*szans/i);

  const firstScoreOff = await items.first().getByTestId("score").innerText();
  await expect(items.first().getByTestId("breakdown")).toContainText("D");
  await expect(items.first().getByTestId("breakdown")).toContainText("brak");   // D wyłączone

  await items.first().click();
  const card = page.getByTestId("place-card");
  await expect(card.getByRole("heading", { level: 2 })).toBeVisible();
  await expect(card.getByTestId("reasons").locator("li").first()).toBeVisible();
  await expect(card.getByTestId("verdict")).toBeVisible();
  await expect(card).toContainText("Dostęp i ochrona");
  await expect(card).toContainText("w linii prostej");

  // przełączenie kalendarza
  await card.getByTestId("calendar-on").click();
  await expect(card.getByTestId("calendar-on")).toHaveAttribute("aria-pressed", "true");
  await expect(card.getByTestId("breakdown").first()).not.toContainText("brak");
  await expect(card).toContainText("Kalendarz (eksperymentalny");
  await expect(card).toContainText("tradycja");

  // stopka ze źródłami i licencjami
  await expect(page.getByTestId("footer")).toContainText("Źródła danych");

  // brak poziomego przewijania na 390 px
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  expect(firstScoreOff).toMatch(/^\d+$|—/);
});

test("mapa, kalendarz miesięczny i porównanie działają", async ({ page }) => {
  await page.goto("/#/mapa");
  await page.getByTestId("dataset").selectOption("demo");
  await page.getByTestId("species-top").selectOption("imleria_badia");   // borowik szlachetny w demo bywa poza sezonem
  await expect(page.getByTestId("map")).toBeVisible();
  await page.getByTestId("tab-ranking").click();
  const boxes = page.locator(".rank-item input[type=checkbox]");
  await expect(boxes.first()).toBeVisible();
  await boxes.nth(0).check();
  await boxes.nth(1).check();
  await page.getByTestId("tab-porownanie").click();
  await expect(page.locator(".cmp-col")).toHaveCount(2);
  await page.locator(".cmp-col").first().click();
  await page.getByRole("button", { name: "Kalendarz miesięczny" }).click();
  await expect(page.getByTestId("month").locator(".md").first()).toBeVisible();
});

test("mapa i ranking na jednym ekranie: znacznik ↔ pozycja na liście", async ({ page }) => {
  await page.goto("/#/mapa");
  await page.getByTestId("dataset").selectOption("demo");
  await page.getByTestId("species-top").selectOption("imleria_badia");   // borowik szlachetny w demo bywa poza sezonem
  const rows = page.getByTestId("map-ranking-item");
  await expect(rows.first()).toBeVisible({ timeout: 20000 });
  const pins = page.getByTestId("map-pin");
  await expect(pins.first()).toBeAttached();
  // znacznik nr 2 → podświetla 2. pozycję listy
  const pin = pins.nth(1);
  const id = await pin.getAttribute("data-id");
  await pin.dispatchEvent("click");
  await expect(page.locator(`[data-rank-id="${id}"]`)).toHaveClass(/sel/);
  // pozycja nr 1 na liście → podświetla znacznik nr 1
  await rows.first().click();
  await expect(pins.first()).toHaveClass(/sel/);
  // szczegóły → karta miejsca
  await page.getByTestId("map-ranking-open").first().click();
  await expect(page).toHaveURL(/#\/miejsce\/\d+/);
});
