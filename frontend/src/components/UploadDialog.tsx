"use client";

import { useState } from "react";
import { uploadVideo } from "@/lib/api";

export default function UploadDialog({ onDone }: { onDone: (url: string) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [desc, setDesc] = useState("");
  const [privacy, setPrivacy] = useState("private");
  const [tags, setTags] = useState("");
  const [pct, setPct] = useState(0);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleUpload() {
    if (!file || !title.trim()) {
      setMsg("Chọn file và nhập tiêu đề trước.");
      return;
    }
    setBusy(true);
    setMsg("");
    try {
      const res = await uploadVideo(
        file,
        { title: title.trim(), description: desc, privacy, tags },
        setPct,
      );
      setMsg(`Upload xong: ${res.video_id}`);
      onDone(res.url);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Upload thất bại");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="double-bezel animate-fade-up">
      <div className="double-bezel-inner p-6">
        <span className="eyebrow">Upload YouTube</span>
        <h2 className="mt-3 text-xl font-semibold">Đăng video mới</h2>
        <p className="mt-1 text-[13px] text-ink-muted">Cần login Google (OAuth) với quyền youtube.upload.</p>

        <div className="mt-5 space-y-4">
          <label
            className="flex cursor-pointer items-center justify-center rounded-lg border border-dashed border-white/20 bg-black/30 px-4 py-8 text-center text-[13px] text-ink-muted hover:border-accent/60 hover:text-ink"
          >
            <input
              type="file"
              accept="video/*"
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
            />
            {file ? `Đã chọn: ${file.name} (${(file.size / 1e6).toFixed(1)} MB)` : "Kéo-thả hoặc bấm để chọn file video"}
          </label>

          <label className="block">
            <span className="mb-1.5 block text-[12px] font-medium text-ink-muted">Tiêu đề *</span>
            <input className="input-field" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Tiêu đề video" />
          </label>
          <label className="block">
            <span className="mb-1.5 block text-[12px] font-medium text-ink-muted">Mô tả</span>
            <textarea className="textarea-field !font-sans !text-[13px]" rows={5} value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Mô tả video…" />
          </label>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="block">
              <span className="mb-1.5 block text-[12px] font-medium text-ink-muted">Quyền riêng tư</span>
              <select className="input-field" value={privacy} onChange={(e) => setPrivacy(e.target.value)}>
                <option value="private">Riêng tư</option>
                <option value="unlisted">Không công khai</option>
                <option value="public">Công khai</option>
              </select>
            </label>
            <label className="block">
              <span className="mb-1.5 block text-[12px] font-medium text-ink-muted">Tags (cách nhau dấu phẩy)</span>
              <input className="input-field" value={tags} onChange={(e) => setTags(e.target.value)} placeholder="vlog, du lịch" />
            </label>
          </div>

          {busy && (
            <div className="h-2 overflow-hidden rounded-full bg-white/10">
              <div className="h-full bg-accent transition-all" style={{ width: `${pct}%` }} />
            </div>
          )}

          <button className="btn-island-primary btn-sm" disabled={busy} onClick={handleUpload}>
            {busy ? `Đang upload ${pct}%…` : "Upload lên YouTube"}
          </button>
          {msg && <p className="text-[12px] text-accent-light">{msg}</p>}
        </div>
      </div>
    </div>
  );
}
