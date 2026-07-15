const os = require("os");
const path = require("path");
const { chromium } = require("playwright");

const BASE_URL = process.env.GUARDIAN_BASE_URL || "http://127.0.0.1:8765";

async function waitForDetail(page, expected) {
  try {
    await page.locator("#eventDetail").getByText(expected, { exact: false }).waitFor({ timeout: 12000 });
  } catch (error) {
    const detail = await page.locator("#eventDetail").textContent().catch(() => "<missing>");
    const toast = await page.locator("#toast").textContent().catch(() => "<missing>");
    const eventId = await page.evaluate(() => sessionStorage.getItem("guardian_debug_event_id"));
    throw new Error(`${error.message}\nDebug detail=${detail}; toast=${toast}; event_id=${eventId}`);
  }
}

async function run() {
  const executablePath = process.env.PLAYWRIGHT_BROWSER_PATH || "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
  const browser = await chromium.launch({ headless: true, executablePath });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const browserErrors = [];
  const httpErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error" && !message.text().includes("Failed to load resource")) browserErrors.push(message.text());
  });
  page.on("pageerror", (error) => browserErrors.push(error.message));
  page.on("response", async (response) => {
    if (response.status() >= 400) {
      httpErrors.push(`${response.status()} ${response.url()} ${await response.text()}`);
    }
  });

  await page.goto(BASE_URL, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "重置调试数据" }).click();
  await page.locator("#timerSeconds").fill("30");
  await page.getByRole("button", { name: "睡眠带：离床" }).click();
  await waitForDetail(page, "等待老人确认");
  if ((await page.locator("#timerSeconds").inputValue()) !== "30") throw new Error("timer seconds input did not preserve 30");
  await page.waitForFunction(() => document.querySelector("#timerClock strong")?.textContent?.includes("s"), null, { timeout: 5000 });

  await page.locator("#nightTurnText").fill("我去趟卫生间，不用担心");
  const conversationResponsePromise = page.waitForResponse((response) => response.url().includes("/api/v1/guardian/conversations/night-turn"));
  const conversationRequestPromise = page.waitForRequest((request) => request.url().includes("/api/v1/guardian/conversations/night-turn"));
  await page.locator('[data-action="night-turn"]').click();
  const conversationResponse = await conversationResponsePromise;
  const conversationRequest = await conversationRequestPromise;
  if (!conversationResponse.ok()) {
    const activeEventId = await page.locator(".event-card.active").getAttribute("data-event-id");
    throw new Error(`conversation request failed: ${conversationResponse.status()} ${await conversationResponse.text()} request=${conversationRequest.postData()} active=${activeEventId}`);
  }
  await waitForDetail(page, "观察返床");
  const conversationCard = page.locator(".conversation-turn").last();
  try {
    await conversationCard.waitFor({ timeout: 8000 });
  } catch (error) {
    const requestBody = JSON.parse(conversationRequest.postData());
    const dashboardResponse = await page.request.get(`${BASE_URL}/api/v1/dashboard?elder_id=E001&selected_event_id=${requestBody.event_id}`);
    throw new Error(`conversation card missing; dashboard=${await dashboardResponse.text()}`);
  }
  const conversationCardText = await conversationCard.textContent();
  if (!conversationCardText.includes("bathroom")) throw new Error(`unexpected conversation card: ${conversationCardText}`);
  await page.getByRole("button", { name: "睡眠带：已返床" }).click();
  await waitForDetail(page, "已关闭");

  const desktopScreenshot = path.join(os.tmpdir(), "guardian-debug-console-desktop.png");
  await page.screenshot({ path: desktopScreenshot, fullPage: true });

  await page.getByRole("button", { name: "重置调试数据" }).click();
  await page.locator("#timerSeconds").fill("1");
  await page.getByRole("button", { name: "睡眠带：离床" }).click();
  await waitForDetail(page, "等待老人确认");
  await waitForDetail(page, "等待子女确认");

  const timeoutEvent = await page.locator("#eventDetail").textContent();

  await page.getByRole("button", { name: "重置调试数据" }).click();
  await page.getByRole("button", { name: "雷达：疑似跌倒" }).click();
  await waitForDetail(page, "已紧急升级");
  await page.locator("#voiceAlert p").getByText("检测到您存在安全问题，我已联系您的子女", { exact: false }).waitFor();
  await page.getByRole("button", { name: "睡眠带：已返床" }).click();
  await waitForDetail(page, "已紧急升级");
  await page.locator("#voiceAlert small").getByText("每 2 秒重复", { exact: false }).waitFor();
  const voiceAlertScreenshot = path.join(os.tmpdir(), "guardian-debug-console-voice-alert.png");
  await page.screenshot({ path: voiceAlertScreenshot, fullPage: true });

  const mobilePage = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await mobilePage.goto(BASE_URL, { waitUntil: "networkidle" });
  const mobileScreenshot = path.join(os.tmpdir(), "guardian-debug-console-mobile.png");
  await mobilePage.screenshot({ path: mobileScreenshot, fullPage: true });

  if (browserErrors.length || httpErrors.length) {
    throw new Error(`Browser errors: ${[...browserErrors, ...httpErrors].join(" | ")}`);
  }

  console.log(
    JSON.stringify(
      {
        normal_flow: "LEAVE_BED -> bathroom -> MONITORING_RETURN -> RETURN_TO_BED -> CLOSED",
        timeout_flow: timeoutEvent.includes("等待子女确认") ? "WAITING_FAMILY_CONFIRM" : "unexpected",
        fall_return_voice_alert: "ESCALATED + start_repeating every 2 seconds",
        voice_alert_screenshot: voiceAlertScreenshot,
        conversation_turns: await page.locator(".conversation-turn").count(),
        desktop_screenshot: desktopScreenshot,
        mobile_screenshot: mobileScreenshot,
        browser_errors: browserErrors,
        http_errors: httpErrors,
      },
      null,
      2
    )
  );

  await browser.close();
}

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
