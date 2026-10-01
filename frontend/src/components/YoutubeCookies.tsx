"use client";

import { useEffect, useRef, useState } from "react";
import {
  deleteYoutubeCookies,
  getYoutubeCookiesStatus,
  uploadYoutubeCookies,
} from "@/lib/api";

/** Upload/lưu file cookies.txt để vượt bot-check YouTube khi tải video bị chặn. */
export default function YoutubeCookies({ compact = false }: { compact?: boolean }) {
  const [hasCookies, setHasCookies] = useState(false);
  const [size, setSize] = useState(0);
  const [mtime, setMtime] = useState(0);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  async function refresh() {
    try {
      const status = await getYoutubeCookiesStatus();
      setHasCookies(status.has_cookies);
      setSize(status.size);
      setMtime(status.mtime);
    } catch {
      /* backend chưa chạy — giữ trạng thái cũ */
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function handleFile(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setMsg("");
    try {
      await uploadYoutubeCookies(file);
      await refresh();
      setMsg("Đã lưu cookies.txt — các lượt tải sau sẽ ưu tiên dùng file này.");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Upload cookie thất bại.");
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function handleDelete() {
    setBusy(true);
    setMsg("");
    try {
      await deleteYoutubeCookies();
      await refresh();
      setMsg("Đã xóa cookies.txt.");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Xóa cookie thất bại.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={`rounded-lg bg-white/[0.03] p-3 ring-1 ring-white/10 ${compact ? "" : "mt-3"}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className={`tag ${hasCookies ? "!text-emerald-300 !border-emerald-400/30" : ""}`}>
          {hasCookies ? `● Đã có cookies.txt (${(size / 1024).toFixed(1)} KB)` : "○ Chưa có cookies.txt"}
        </span>
        <label className="btn-island-secondary btn-xs cursor-pointer">
          {busy ? "Đang xử lý…" : hasCookies ? "Upload lại" : "Upload cookies.txt"}
          <input
            ref={inputRef}
            type="file"
            accept=".txt,text/plain"
            className="hidden"
            disabled={busy}
            onChange={(e) => void handleFile(e.target.files?.[0])}
          />
        </label>
        {hasCookies && (
          <button className="btn-island-secondary btn-xs" disabled={busy} onClick={() => void handleDelete()}>
            Xóa
          </button>
        )}
      </div>
      {hasCookies && mtime > 0 && (
        <p className="mt-1.5 text-[11px] text-ink-light">
          Cập nhật: {new Date(mtime * 1000).toLocaleString("vi-VN")}
        </p>
      )}
      <details className="mt-2 text-[11px] leading-relaxed text-ink-muted">
        <summary className="cursor-pointer text-accent-light">Cách lấy cookies.txt (khuyên dùng khi gặp lỗi bot-check)</summary>
        <ol className="mt-1.5 list-decimal space-y-1 pl-4">
          <li>Mở trình duyệt đã đăng nhập YouTube (nên dùng Chrome profile chính).</li>
          <li>Cài extension &quot;Get cookies.txt LOCALLY&quot; → mở youtube.com → Export → tick youtube.com.</li>
          <li>Upload file vừa xuất ở đây. Backend ưu tiên dùng file này thay vì đọc cookie trình duyệt.</li>
          <li>Nếu vẫn báo bot-check: đăng nhập lại YouTube, xuất file mới rồi upload lại.</li>
        </ol>
      </details>
      {msg && <p className="mt-2 text-[11px] text-ink-muted" role="status">{msg}</p>}
    </div>
  );
}
