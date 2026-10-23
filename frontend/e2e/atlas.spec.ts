import { expect, test } from "@playwright/test";

const SPECIES = ["boletus_edulis", "imleria_badia", "cantharellus_cibarius", "tylopilus_felleus", "rubroboletus_satanas", "hygrophoropsis_aurantiaca"];
const PAIRS = ["borowik_goryczak", "borowik_szatanski", "podgrzybek_goryczak", "kurka_lisowka"];

test("atlas działa offline dla gatunków MVP i ich sobowtórów (390×844)", async ({ page, context }) => {
  await page.goto("/#/atlas");
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload();                                   // strona pod kontrolą service workera
  await expect(page.getByTestId("atlas-notice")).toContainText("100% pewnością");
  await expect(page.getByTestId("atlas-draft")).toBeVisible();
  await page.getByTestId("atlas-offline").click();
  await expect(page.getByTestId("atlas-offline-status")).toContainText("Zapisano", { timeout: 20_000 });

  await context.setOffline(true);
  for (const s of SPECIES) {
    await page.goto(`/#/atlas/gatunek/${s}`);
    await expect(page.getByRole("heading", { level: 2 })).toBeVisible();
    await expect(page.getByTestId("atlas-notice")).toBeVisible();
    // brakujące ujęcia oznaczone jako brak, nie zastąpione zdjęciem innego gatunku
    await expect.poll(async () => (await page.getByTestId("photo-missing").count()) + (await page.locator(".ph-img img").count())).toBe(5);
  }
  for (const p of PAIRS) {
    await page.goto(`/#/atlas/para/${p}`);
    await expect(page.getByTestId("pair-table")).toBeVisible();
    await expect(page.getByTestId("single-feature-warning")).toContainText("Pojedyncza cecha");
  }
  await page.goto("/#/atlas/bezpieczenstwo");
  await expect(page.locator("a.call-112")).toBeVisible();
  await expect(page.getByTestId("myths")).toContainText("srebrnej łyżeczki");
  await context.setOffline(false);

  // atlas nie oferuje rozpoznawania ani oceny okazu
  await expect(page.locator("input[type=file]")).toHaveCount(0);
  await expect(page.locator("body")).not.toContainText(/rozpoznaj gatunek|czy (ten|mój) grzyb jest jadalny/i);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test("katalog: przeglądanie, karta gatunku, pomoc w oznaczaniu bez rozpoznawania zdjęcia", async ({ page }) => {
  await page.goto("/#/atlas");
  await page.getByTestId("atlas-katalog").click();
  const cards = page.getByTestId("katalog-gatunek");
  await expect(cards.first()).toBeVisible({ timeout: 20000 });
  await page.getByTestId("katalog-szukaj").fill("borowik");
  await expect(cards.first()).toContainText(/orowik/i);
  await cards.first().click();
  await expect(page.getByTestId("katalog-karta")).toBeVisible();
  await expect(page.getByTestId("katalog-uwaga")).toBeVisible();
  await page.goto("/#/atlas/oznacz");
  await expect(page.getByTestId("klucz-ostrzezenie")).toBeVisible();
  await page.getByTestId("klucz-hymenium-blaszki").click();
  await page.getByTestId("klucz-trzon-pochwa").click();
  await expect(page.getByTestId("klucz-wynik").first()).toBeVisible();
  await expect(page.getByTestId("klucz-wyniki")).toContainText(/uchomor/);
  await page.getByTestId("klucz-wynik").first().click();
  await expect(page.getByTestId("klucz-porownanie")).toBeVisible();
});
