import { test } from "@playwright/test";

test.skip(!process.env.SCREENS, "tylko na żądanie: SCREENS=1");
test("zrzuty ekranów", async ({ page }) => {
  await page.goto("/#/mapa");
  await page.getByTestId("dataset").selectOption("demo");
  await page.waitForTimeout(2500);
  await page.screenshot({ path: "../docs/zrzuty/1_mapa.png" });
  await page.getByTestId("tab-ranking").click();
  await page.getByTestId("ranking-item").first().waitFor();
  await page.screenshot({ path: "../docs/zrzuty/2_ranking.png" });
  await page.getByTestId("ranking-item").first().click();
  await page.getByTestId("verdict").waitFor();
  await page.screenshot({ path: "../docs/zrzuty/3_karta.png" });
  await page.getByTestId("week").scrollIntoViewIfNeeded();
  await page.screenshot({ path: "../docs/zrzuty/4_7dni.png" });
  await page.getByRole("button", { name: "Kalendarz miesięczny" }).click();
  await page.getByTestId("month").waitFor();
  await page.screenshot({ path: "../docs/zrzuty/5_kalendarz.png" });
});
