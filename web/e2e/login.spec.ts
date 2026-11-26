import { expect, test } from "@playwright/test";

test("sem sessão, o painel redireciona para o login por magic link", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByRole("heading", { name: /Monitor de passagens/ })).toBeVisible();
  await expect(page.getByLabel("E-mail")).toBeVisible();
  await expect(page.getByRole("button", { name: /Receber link/ })).toBeVisible();
});

test("webhook do Telegram recusa chamadas sem o segredo", async ({ request }) => {
  const r = await request.post("/api/telegram", { data: { message: { text: "/status" } } });
  expect(r.status()).toBe(401);
});
