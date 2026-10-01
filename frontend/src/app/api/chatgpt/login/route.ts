import { NextResponse } from "next/server";
import { CHATGPT_URL, detachBrowser, openChatGptBrowser } from "@/lib/chatgpt-client";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST() {
  let handle;
  try {
    handle = await openChatGptBrowser();
    const pages = await handle.browser.pages();
    const page = pages.find((p) => p.url().includes("chatgpt.com")) || (await handle.browser.newPage());
    await page.goto(CHATGPT_URL, { waitUntil: "domcontentloaded", timeout: 60_000 });
    await page.bringToFront();
    return NextResponse.json({ status: "opened", detail: "Đăng nhập ChatGPT trong cửa sổ Chrome vừa mở." });
  } catch (e) {
    return NextResponse.json(
      { detail: e instanceof Error ? e.message : "Không mở được ChatGPT." },
      { status: 500 },
    );
  } finally {
    if (handle) await detachBrowser(handle).catch(() => {});
  }
}
