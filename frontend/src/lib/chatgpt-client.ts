import fs from "fs";
import os from "os";
import path from "path";
import puppeteer, { type Browser, type ElementHandle, type Page } from "puppeteer-core";

export const CHATGPT_URL = process.env.CHATGPT_URL || "https://chatgpt.com/";
const CHATGPT_PORT = Number(process.env.CHATGPT_PORT || "9233");
const PROFILE_DIR = process.env.CHATGPT_PROFILE_DIR || path.join(os.homedir(), ".yt-recent-videos", "chatgpt-profile");
const GENERATE_TIMEOUT_MS = Number(process.env.CHATGPT_GENERATE_TIMEOUT || "300000");

function chromePath(): string {
  const candidates = [
    process.env.CHROME_PATH,
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
  ].filter(Boolean) as string[];
  const found = candidates.find((p) => fs.existsSync(p));
  if (!found) throw new Error("Không tìm thấy Google Chrome. Có thể đặt CHROME_PATH.");
  return found;
}

export interface BrowserHandle {
  browser: Browser;
  persistent: boolean;
}

/** Reuse Chrome đang chạy hoặc mở profile riêng, visible để user login ChatGPT Plus. */
export async function openChatGptBrowser(): Promise<BrowserHandle> {
  try {
    const browser = await puppeteer.connect({
      browserURL: `http://127.0.0.1:${CHATGPT_PORT}`,
      defaultViewport: null,
    });
    return { browser, persistent: true };
  } catch {
    fs.mkdirSync(PROFILE_DIR, { recursive: true });
    const browser = await puppeteer.launch({
      executablePath: chromePath(),
      headless: false,
      userDataDir: PROFILE_DIR,
      args: [
        "--disable-blink-features=AutomationControlled",
        `--remote-debugging-port=${CHATGPT_PORT}`,
      ],
      defaultViewport: null,
    });
    return { browser, persistent: false };
  }
}

/** Chỉ detach để Chrome profile tiếp tục sống và giữ login. */
export async function detachBrowser(handle: BrowserHandle): Promise<void> {
  await handle.browser.disconnect();
}

/** Đóng Chrome automation sau khi đã lấy xong kết quả tạo ảnh. */
export async function closeBrowser(handle: BrowserHandle): Promise<void> {
  await handle.browser.close();
}

const COMPOSER_SELECTORS = [
  "#prompt-textarea",
  'div[contenteditable="true"][data-placeholder]',
  'div.ProseMirror[contenteditable="true"]',
  '[contenteditable="true"][role="textbox"]',
];

async function findComposer(page: Page): Promise<ElementHandle<HTMLElement> | null> {
  for (const selector of COMPOSER_SELECTORS) {
    const element = await page.$(selector).catch(() => null);
    if (element) return element as ElementHandle<HTMLElement>;
  }
  return null;
}

export async function isLoggedIn(page: Page): Promise<boolean> {
  const deadline = Date.now() + 35_000;
  while (Date.now() < deadline) {
    if (await findComposer(page)) return true;
    // Profile menu chỉ xuất hiện ở phiên đã đăng nhập; dùng làm fallback khi
    // composer mới của ChatGPT chưa mount xong hoặc đã đổi selector.
    const hasProfile = await page.$('button[aria-label="Open profile menu"]').catch(() => null);
    if (hasProfile) return true;
    const hasLogin = await page.evaluate(() =>
      Array.from(document.querySelectorAll("a,button")).some((n) =>
        /log\s*in|sign\s*in/i.test((n.textContent || "").trim()),
      ),
    ).catch(() => false);
    if (hasLogin) return false;
    await new Promise((r) => setTimeout(r, 1000));
  }
  return false;
}

export async function attachImage(page: Page, imagePath: string): Promise<void> {
  const initialAttachmentCount = await page.$$eval(
    'button[aria-label^="Remove "]',
    (buttons) => buttons.length,
  );
  const deadline = Date.now() + 30_000;
  let input: ElementHandle<HTMLInputElement> | null = null;
  while (Date.now() < deadline && !input) {
    // Các input vẫn tồn tại nhưng bị disabled cho tới khi mở menu đính kèm.
    input = (await page.$(
      'input[type="file"][aria-label="Attach photos"]:not([disabled]), input[type="file"][aria-label="Attach photos or videos"]:not([disabled]), input[type="file"][accept*="image"]:not([disabled])',
    ).catch(() => null)) as ElementHandle<HTMLInputElement> | null;
    if (!input) {
      const addButton = await page.$('button[aria-label="Add files and more"]');
      if (addButton) {
        const enabled = await addButton.evaluate(
          (el) => !(el as HTMLButtonElement).disabled && el.getAttribute("aria-disabled") !== "true",
        ).catch(() => false);
        if (enabled) await addButton.click().catch(() => {});
      }
      await new Promise((r) => setTimeout(r, 500));
    }
  }
  if (!input) throw new Error("Không tìm thấy input đính kèm ảnh của ChatGPT.");
  await input.uploadFile(imagePath);
  const attached = await page.waitForFunction(
    (previousCount) =>
      document.querySelectorAll('button[aria-label^="Remove "]').length > previousCount,
    { timeout: 30_000, polling: 300 },
    initialAttachmentCount,
  ).then(() => true).catch(() => false);
  if (!attached) {
    throw new Error("ChatGPT không hiển thị preview của ảnh gốc; prompt chưa được gửi.");
  }
}

export async function submitPrompt(page: Page, prompt: string): Promise<void> {
  const deadline = Date.now() + 30_000;
  let composer = await findComposer(page);
  while (!composer && Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 500));
    composer = await findComposer(page);
  }
  if (!composer) throw new Error("Không tìm thấy ô chat ChatGPT.");
  await composer.click();
  await page.keyboard.down(process.platform === "darwin" ? "Meta" : "Control");
  await page.keyboard.press("a");
  await page.keyboard.up(process.platform === "darwin" ? "Meta" : "Control");
  await page.keyboard.press("Backspace");
  const oneLine = prompt.replace(/\s*\n+\s*/g, " ").trim();
  await page.keyboard.type(oneLine, { delay: 3 });

  // ChatGPT hiện tại không submit bằng Enter ổn định trên contenteditable.
  // Chờ attachment upload xong và click nút Send khi nút được enable.
  const sendSelectors = [
    'button[data-testid="send-button"]',
    'button[aria-label="Send prompt"]',
    'button[aria-label="Send message"]',
    'button[aria-label="Send"]',
  ];
  const sendDeadline = Date.now() + 60_000;
  let sent = false;
  while (Date.now() < sendDeadline && !sent) {
    for (const selector of sendSelectors) {
      const button = await page.$(selector).catch(() => null);
      if (!button) continue;
      const enabled = await button.evaluate((el) =>
        !(el as HTMLButtonElement).disabled && el.getAttribute("aria-disabled") !== "true",
      ).catch(() => false);
      if (!enabled) continue;
      await button.click();
      sent = true;
      break;
    }
    if (!sent) {
      // Fallback khi aria-label đổi nhưng vẫn có button chứa chữ Send.
      sent = await page.evaluate(() => {
        const button = Array.from(document.querySelectorAll<HTMLButtonElement>("button"))
          .find((el) => {
            const label = `${el.getAttribute("aria-label") || ""} ${el.getAttribute("data-testid") || ""} ${el.title || ""}`;
            return /send/i.test(label) && !el.disabled && el.getAttribute("aria-disabled") !== "true";
          });
        if (!button) return false;
        button.click();
        return true;
      }).catch(() => false);
    }
    if (!sent) await new Promise((r) => setTimeout(r, 500));
  }
  if (!sent) {
    throw new Error("Không tìm thấy nút Gửi của ChatGPT sau khi đã nhập prompt.");
  }

  // Xác nhận submit: composer phải rỗng hoặc nút Stop xuất hiện.
  const submitted = await page.waitForFunction(
    () => {
      const composer = document.querySelector<HTMLElement>(
        '#prompt-textarea, div.ProseMirror[contenteditable="true"], [contenteditable="true"][role="textbox"]',
      );
      const stopped = document.querySelector(
        'button[data-testid="stop-button"], button[aria-label*="Stop"]',
      );
      return Boolean(stopped) || !composer || !(composer.textContent || "").trim();
    },
    { timeout: 15_000, polling: 300 },
  ).then(() => true).catch(() => false);
  if (!submitted) {
    throw new Error("Đã click Gửi nhưng ChatGPT chưa nhận prompt. Hãy thử lại.");
  }
}

export async function extractGeneratedImage(page: Page): Promise<Buffer | null> {
  const handle = await page.waitForFunction(
    () => {
      const images = Array.from(document.querySelectorAll<HTMLImageElement>("img[alt]"));
      const img = images.reverse().find((el) => {
        const alt = (el.getAttribute("alt") || "").toLowerCase();
        const src = el.getAttribute("src") || "";
        return alt.startsWith("generated image") && el.complete && el.naturalWidth > 300 && Boolean(src);
      });
      return img?.src || null;
    },
    { timeout: GENERATE_TIMEOUT_MS, polling: 2000 },
  );
  const url = (await handle.jsonValue()) as string;
  if (!url) return null;
  const base64 = await page.evaluate(async (src) => {
    const res = await fetch(src);
    if (!res.ok) return "";
    const bytes = new Uint8Array(await res.arrayBuffer());
    let binary = "";
    const chunk = 0x8000;
    for (let i = 0; i < bytes.length; i += chunk) {
      binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
    }
    return btoa(binary);
  }, url);
  return base64 ? Buffer.from(base64, "base64") : null;
}
