import { test } from "@playwright/test";

test.skip(!process.env.SCREENS, "tylko na żądanie: SCREENS=1");
test("zrzuty — dane rzeczywiste", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("query", JSON.stringify({ species: "imleria_badia", lat: 50.17, lon: 21.96, radius_km: 15, calendar: false, dataset: "real" })));
  await page.goto("/#/ranking");
  await page.getByTestId("ranking-item").first().waitFor();
  await page.screenshot({ path: "../docs/zrzuty/real_1_ranking.png" });
  await page.getByTestId("ranking-item").first().click();
  await page.getByTestId("verdict").waitFor();
  await page.screenshot({ path: "../docs/zrzuty/real_2_karta.png", fullPage: true });
  await page.goto("/#/mapa");
  await page.waitForResponse((r) => r.url().includes("/api/mapa"), { timeout: 30000 });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: "../docs/zrzuty/real_3_mapa.png" });
});
