"use client";

import { useEffect, useMemo, useState } from "react";
import {
  POST_VARS,
  VideoItem,
  copyImage,
  copyText,
  formatDate,
  getConfig,
  getRecent,
  lowThumbnailUrl,
  renderPost,
  safeFileName,
  saveConfig,
  thumbnailUrl,
} from "@/lib/api";
import { DownloadIcon } from "@/components/icons";

/**
 * Tab Đăng bài (YouTube Community):
 * - List video theo số ngày, tích chọn nhiều clip
 * - Template động {title} {url} {video_id} {channel} {date}, lưu vào config
 * - Preview từng bài: nội dung đã render + ảnh thumbnail
 * - Copy / tải thumbnail / mở YouTube Studio để đăng
 *
 * Lưu ý: YouTube Data API KHÔNG hỗ trợ tạo community post nên bước đăng cuối
 * là bán tự động (copy 1-click + mở Studio), không phải full-auto ngầm.
 */
export default function PostComposer() {
  const [days, setDays] = useState(2);
  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [template, setTemplate] = useState("");
  const [savedTemplate, setSavedTemplate] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [copiedId, setCopiedId] = useState("");
  const [copiedThumbId, setCopiedThumbId] = useState("");

  async function load(d: number) {
    setLoading(true);
    setError("");
    try {
      const [res, cfg] = await Promise.all([getRecent(d), getConfig()]);
      setVideos(res.videos);
      setChecked(new Set(res.videos.map((v) => v.video_id)));
      if (!template) {
        setTemplate(cfg.post_template);
        setSavedTemplate(cfg.post_template);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Không tải được danh sách");
      setVideos([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load(2);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selected = useMemo(
    () => videos.filter((v) => checked.has(v.video_id)),
    [videos, checked],
  );

  function toggle(id: string) {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function insertVar(v: string) {
    setTemplate((t) => t + (t.endsWith(" ") || t === "" ? "" : " ") + v + " ");
  }

  async function handleSaveTemplate() {
    try {
      await saveConfig({ post_template: template });
      setSavedTemplate(template);
      setMsg("Đã lưu template.");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Lưu template thất bại");
    }
  }

  async function handleCopy(text: string, id: string) {
    await copyText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(""), 1500);
  }

  async function handleCopyThumb(v: VideoItem) {
    try {
      await copyImage(thumbnailUrl(v.video_id));
      setCopiedThumbId(v.video_id);
      setTimeout(() => setCopiedThumbId(""), 1500);
    } catch {
      setMsg("Copy ảnh thất bại — trình duyệt chặn clipboard.");
    }
  }

  async function handleCopyAll() {
    await copyText(selected.map((v) => renderPost(template, v)).join("\n\n─────\n\n"));
    setMsg(`Đã copy ${selected.length} bài vào clipboard.`);
  }

  async function handleDownloadThumbs() {
    setMsg("Đang tải thumbnails…");
    for (const v of selected) {
      const a = document.createElement("a");
      a.href = thumbnailUrl(v.video_id);
      a.download = `${safeFileName(v.title)}.jpg`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      await new Promise((r) => setTimeout(r, 600));
    }
    setMsg(`Đã tải ${selected.length} ảnh thumbnail.`);
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[380px_1fr]">
      {/* ── Cột trái: list video + tích chọn ── */}
      <div className="double-bezel animate-fade-up">
        <div className="double-bezel-inner flex max-h-[720px] flex-col p-5">
          <div className="flex items-center justify-between">
            <span className="eyebrow">Chọn clip · {selected.length}/{videos.length}</span>
            <div className="flex gap-1.5">
              {[1, 2, 3, 7].map((d) => (
                <button
                  key={d}
                  onClick={() => {
                    setDays(d);
                    load(d);
                  }}
                  className={`tag cursor-pointer ${days === d ? "chip-active" : ""}`}
                >
                  {d}d
                </button>
              ))}
            </div>
          </div>

          <div className="mt-3 flex gap-2">
            <button className="tag cursor-pointer" onClick={() => setChecked(new Set(videos.map((v) => v.video_id)))}>
              Chọn hết
            </button>
            <button className="tag cursor-pointer" onClick={() => setChecked(new Set())}>
              Bỏ hết
            </button>
            <button className="tag cursor-pointer ml-auto" onClick={() => load(days)}>
              {loading ? "…" : "↻ Tải lại"}
            </button>
          </div>

          <div className="scrollbar-thin mt-3 flex-1 space-y-2 overflow-y-auto pr-1">
            {error && <p className="text-[12px] text-red-300">{error}</p>}
            {loading && <p className="text-[12px] text-ink-muted">Đang tải…</p>}
            {!loading &&
              videos.map((v) => (
                <label
                  key={v.video_id}
                  className={`flex cursor-pointer gap-3 rounded-lg p-2 ring-1 transition-colors ${
                    checked.has(v.video_id)
                      ? "bg-accent-muted ring-accent/40"
                      : "bg-white/[0.03] ring-white/10 hover:bg-white/[0.06]"
                  }`}
                >
                  <input
                    type="checkbox"
                    className="mt-1 h-4 w-4 shrink-0 accent-[#4d93ff]"
                    checked={checked.has(v.video_id)}
                    onChange={() => toggle(v.video_id)}
                  />
                  {v.thumbnail ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={lowThumbnailUrl(v.video_id)} alt="" className="h-11 w-20 shrink-0 rounded object-cover" loading="lazy" />
                  ) : (
                    <div className="h-11 w-20 shrink-0 rounded bg-white/10" />
                  )}
                  <div className="min-w-0">
                    <p className="line-clamp-2 text-[12px] font-medium leading-snug">{v.title}</p>
                    <p className="mt-0.5 text-[11px] text-ink-light">
                      {v.channel_title} · {formatDate(v.published_at)}
                    </p>
                  </div>
                </label>
              ))}
            {!loading && videos.length === 0 && !error && (
              <p className="text-[12px] text-ink-muted">Không có video nào trong {days} ngày qua.</p>
            )}
          </div>
        </div>
      </div>

      {/* ── Cột phải: template + preview ── */}
      <div className="space-y-5">
        <div className="double-bezel animate-fade-up" style={{ animationDelay: "60ms" }}>
          <div className="double-bezel-inner p-5">
            <span className="eyebrow">Template đăng bài</span>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {POST_VARS.map((v) => (
                <button key={v} onClick={() => insertVar(v)} className="tag cursor-pointer font-mono hover:text-accent-light">
                  {v}
                </button>
              ))}
            </div>
            <textarea
              className="textarea-field mt-3 !font-sans !text-[13px] !leading-relaxed"
              rows={7}
              value={template}
              onChange={(e) => setTemplate(e.target.value)}
              placeholder="Bài đăng mới hôm nay: {title} …"
            />
            <div className="mt-3 flex items-center gap-3">
              <button className="btn-island-secondary btn-sm" onClick={handleSaveTemplate}>
                Lưu template
              </button>
              {template !== savedTemplate && (
                <span className="text-[11px] text-warn">● chưa lưu</span>
              )}
            </div>
          </div>
        </div>

        <div className="double-bezel animate-fade-up" style={{ animationDelay: "120ms" }}>
          <div className="double-bezel-inner p-5">
            <div className="flex flex-wrap items-center gap-3">
              <span className="eyebrow">Preview · {selected.length} bài</span>
              <div className="ml-auto flex flex-wrap gap-2">
                <button className="btn-island-secondary btn-sm" disabled={selected.length === 0} onClick={handleCopyAll}>
                  Copy tất cả
                </button>
                <button className="btn-island-secondary btn-sm" disabled={selected.length === 0} onClick={handleDownloadThumbs} title="Tải thumbnails" aria-label="Tải thumbnails">
                  <DownloadIcon />
                </button>
                <a
                  className="btn-island-primary btn-sm"
                  href="https://studio.youtube.com"
                  target="_blank"
                  rel="noreferrer"
                >
                  Mở YouTube Studio ↗
                </a>
              </div>
            </div>
            {msg && <p className="mt-2 text-[12px] text-accent-light">{msg}</p>}

            <div className="mt-4 space-y-4">
              {selected.map((v) => {
                const text = renderPost(template, v);
                return (
                  <div key={v.video_id} className="rounded-lg bg-black/30 p-4 ring-1 ring-white/10">
                    <div className="flex items-start gap-3">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={lowThumbnailUrl(v.video_id)}
                        alt=""
                        className="h-20 w-36 shrink-0 rounded-md object-cover ring-1 ring-white/10"
                        loading="lazy"
                      />
                      <div className="min-w-0 flex-1">
                        <p className="whitespace-pre-wrap text-[13px] leading-relaxed">{text}</p>
                        <p className="mt-1.5 text-[11px] text-ink-light">{text.length} ký tự · ảnh: thumbnail video</p>
                      </div>
                    </div>
                    <div className="mt-3 flex gap-2">
                      <button className="btn-island-secondary btn-xs" onClick={() => handleCopy(text, v.video_id)}>
                        {copiedId === v.video_id ? "✓ Đã copy" : "Copy bài này"}
                      </button>
                      <button className="btn-island-secondary btn-xs" onClick={() => handleCopyThumb(v)}>
                        {copiedThumbId === v.video_id ? "✓ Đã copy ảnh" : "Copy thumbnail"}
                      </button>
                      <a className="btn-island-secondary btn-xs" href={thumbnailUrl(v.video_id)} download={`${safeFileName(v.title)}.jpg`} title="Tải ảnh" aria-label="Tải ảnh">
                        <DownloadIcon className="h-3 w-3 shrink-0" />
                      </a>
                      <a className="btn-island-secondary btn-xs" href={v.url} target="_blank" rel="noreferrer">
                        Mở video ↗
                      </a>
                    </div>
                  </div>
                );
              })}
              {selected.length === 0 && (
                <p className="text-[13px] text-ink-muted">Tích chọn ít nhất 1 clip ở cột trái để xem preview.</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
