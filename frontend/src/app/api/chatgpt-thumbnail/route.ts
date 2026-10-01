import fs from "fs";
import os from "os";
import path from "path";
import { NextRequest, NextResponse } from "next/server";
import {
  CHATGPT_URL,
  attachImage,
  closeBrowser,
  detachBrowser,
  extractGeneratedImage,
  isLoggedIn,
  openChatGptBrowser,
  submitPrompt,
} from "@/lib/chatgpt-client";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8001";

function makePrompt(title: string, part: number): string {
  return [
    "@Tạo hình ảnh",
    "Hãy tạo hình giống ảnh tham chiếu đính kèm để làm thumbnail cho video YouTube.",
    `Dùng tiêu đề tiếng Việt: \"${title}\".`,
    "Giữ font đơn giản, rõ ràng, dễ đọc; chữ phải nổi bật khi xem ở kích thước nhỏ.",
    "Chỉnh bố cục và kích thước đúng tỷ lệ thumbnail YouTube 16:9 (1280x720).",
    "Dùng tông màu hài hòa, trung tính, bớt chói.",
    `Bổ sung chữ \"Phần ${part}\" thật to, rõ, cùng font với tiêu đề ở góc trên bên phải.`,
    "Xóa toàn bộ chữ và logo gốc ở góc trên bên trái và góc trên bên phải trước khi đặt chữ mới.",
    "Giữ nguyên nhân vật chính, bối cảnh và phong cách hình ảnh; không thêm logo/watermark mới.",
    "Chỉ tạo 1 ảnh kết quả hoàn chỉnh, không giải thích bằng văn bản.",
  ].join(" ");
}

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => null);
  const videoId = String(body?.video_id || "").trim();
  const title = String(body?.title || "").trim();
  const part = Math.max(1, Number(body?.part) || 1);
  const customPrompt = String(body?.prompt || "").trim();
  if (!/^[A-Za-z0-9_-]{6,}$/.test(videoId)) {
    return NextResponse.json({ detail: "video_id không hợp lệ." }, { status: 400 });
  }
  if (!title) return NextResponse.json({ detail: "Thiếu tiêu đề tiếng Việt." }, { status: 400 });

  const tempDir = path.join(os.tmpdir(), "yt-recent-chatgpt-thumb");
  fs.mkdirSync(tempDir, { recursive: true });
  const inputPath = path.join(tempDir, `${videoId}.jpg`);
  try {
    const srcRes = await fetch(`${BACKEND_URL}/api/analyzed/${videoId}/image`);
    if (!srcRes.ok) throw new Error(`HTTP ${srcRes.status}`);
    fs.writeFileSync(inputPath, Buffer.from(await srcRes.arrayBuffer()));
  } catch {
    return NextResponse.json(
      { detail: "Không lấy được thumbnail gốc đã lưu. Hãy bấm Lưu phân tích trước." },
      { status: 400 },
    );
  }

  let handle;
  let generated = false;
  try {
    handle = await openChatGptBrowser();
    const page = await handle.browser.newPage();
    await page.goto(CHATGPT_URL, { waitUntil: "domcontentloaded", timeout: 60_000 });
    if (!(await isLoggedIn(page))) {
      await page.bringToFront();
      return NextResponse.json({
        status: "need_login",
        detail: "Chưa đăng nhập ChatGPT. Hãy đăng nhập trong Chrome vừa mở rồi thử lại.",
      });
    }

    await attachImage(page, inputPath);
    await submitPrompt(page, customPrompt || makePrompt(title, part));
    const image = await extractGeneratedImage(page);
    if (!image) {
      return NextResponse.json(
        { detail: "ChatGPT không trả về ảnh (hết quota, bị từ chối hoặc quá thời gian)." },
        { status: 502 },
      );
    }
    generated = true;
    return new NextResponse(new Uint8Array(image), {
      status: 200,
      headers: {
        "Content-Type": "image/png",
        "Cache-Control": "no-store",
      },
    });
  } catch (e) {
    return NextResponse.json(
      { detail: e instanceof Error ? e.message : "Tạo thumbnail thất bại." },
      { status: 500 },
    );
  } finally {
    if (handle) {
      if (generated) await closeBrowser(handle).catch(() => {});
      else await detachBrowser(handle).catch(() => {});
    }
  }
}
