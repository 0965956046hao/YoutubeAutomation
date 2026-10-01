"use client";

import { useState } from "react";
import {
  VideoItem,
  copyImage,
  formatDate,
  formatViews,
  postComment,
  thumbnailUrl,
  updateVideo,
} from "@/lib/api";
import { startVideoDownload } from "@/lib/downloads";
import { DownloadIcon } from "@/components/icons";

export default function VideoDetail({
  video,
  onClose,
  onUpdated,
  onFacebook,
}: {
  video: VideoItem;
  onClose: () => void;
  onUpdated: () => void;
  onFacebook: (video: VideoItem) => void;
}) {
  const [tab, setTab] = useState<"info" | "edit" | "post">("info");
  const [title, setTitle] = useState(video.title);
  const [desc, setDesc] = useState(video.description);
  const [comment, setComment] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSave() {
    setBusy(true);
    setMsg("");
    try {
      await updateVideo(video.video_id, { title, description: desc });
      setMsg("Đã cập nhật tiêu đề / mô tả.");
      onUpdated();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Cập nhật thất bại");
    } finally {
      setBusy(false);
    }
  }

  async function handleComment() {
    setBusy(true);
    setMsg("");
    try {
      const res = await postComment(video.video_id, comment);
      setMsg(res.note || "Đã đăng bình luận.");
      setComment("");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Đăng thất bại");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-stretch justify-end bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div
        className="glass-panel flex h-full w-full max-w-xl flex-col overflow-hidden animate-scale-in"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 border-b border-white/10 p-5">
          <div>
            <span className="eyebrow">Chi tiết video</span>
            <h3 className="mt-2 line-clamp-2 text-[16px] font-semibold leading-snug">{video.title}</h3>
            <p className="mt-1 text-[12px] text-ink-muted">
              {video.channel_title} · {formatDate(video.published_at)} · {formatViews(video.view_count)} lượt xem
            </p>
          </div>
          <button className="icon-btn" onClick={onClose} title="Đóng">✕</button>
        </div>

        <div className="flex gap-2 border-b border-white/10 px-5 py-3">
          {(
            [
              ["info", "Mô tả"],
              ["edit", "Sửa"],
              ["post", "Đăng"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`tag cursor-pointer !py-1.5 !px-4 ${tab === key ? "chip-active" : ""}`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto p-5 scrollbar-thin">
          {tab === "info" && (
            <>
              {video.thumbnail && (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={thumbnailUrl(video.video_id)}
                  alt={video.title}
                  className="aspect-video w-full rounded-lg object-cover ring-1 ring-white/10"
                />
              )}
              <p className="mt-4 whitespace-pre-wrap text-[13px] leading-relaxed text-ink-muted">
                {video.description || "(Video không có mô tả)"}
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                <button className="btn-island-primary btn-sm" onClick={() => onFacebook(video)}>
                  Cắt 30 phút → Facebook
                </button>
                <button
                  className="btn-island-secondary btn-sm"
                  onClick={() => {
                    copyImage(thumbnailUrl(video.video_id))
                      .then(() => setMsg("Đã copy thumbnail — dán (Ctrl+V) vào Studio."))
                      .catch(() => setMsg("Copy ảnh thất bại — trình duyệt chặn clipboard."));
                  }}
                >
                  Copy thumbnail
                </button>
                <button
                  className="btn-island-secondary btn-sm"
                  title="Tải mp4 về máy"
                  aria-label="Tải mp4"
                  onClick={() => {
                    startVideoDownload(video.video_id)
                      .then(() => setMsg("Đã tạo tác vụ tải — theo dõi ở popup góc phải dưới."))
                      .catch((e) => setMsg(e instanceof Error ? e.message : "Tạo tác vụ thất bại"));
                  }}
                >
                  <DownloadIcon />
                </button>
                <a className="btn-island-secondary btn-sm" href={video.url} target="_blank" rel="noreferrer">
                  ↗ Mở YouTube
                </a>
              </div>
            </>
          )}

          {tab === "edit" && (
            <div className="space-y-3">
              <label className="block">
                <span className="mb-1.5 block text-[12px] font-medium text-ink-muted">Tiêu đề</span>
                <input className="input-field" value={title} onChange={(e) => setTitle(e.target.value)} />
              </label>
              <label className="block">
                <span className="mb-1.5 block text-[12px] font-medium text-ink-muted">Mô tả</span>
                <textarea className="textarea-field !font-sans !text-[13px]" rows={12} value={desc} onChange={(e) => setDesc(e.target.value)} />
              </label>
              <button className="btn-island-primary btn-sm" disabled={busy} onClick={handleSave}>
                {busy ? "Đang lưu…" : "Lưu thay đổi (cần OAuth)"}
              </button>
            </div>
          )}

          {tab === "post" && (
            <div className="space-y-3">
              <p className="rounded-lg bg-white/[0.05] p-3 text-[12px] leading-relaxed text-ink-muted ring-1 ring-white/10">
                YouTube Data API không hỗ trợ tạo bài đăng Cộng đồng. Tab này đăng
                <b> bình luận top-level </b> vào video — phù hợp để ghim thông báo / link.
              </p>
              <textarea
                className="textarea-field !font-sans !text-[13px]"
                rows={5}
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="Nội dung bình luận…"
              />
              <button className="btn-island-primary btn-sm" disabled={busy || !comment.trim()} onClick={handleComment}>
                {busy ? "Đang đăng…" : "Đăng bình luận (cần OAuth)"}
              </button>
            </div>
          )}

          {msg && <p className="mt-4 text-[12px] text-accent-light">{msg}</p>}
        </div>
      </div>
    </div>
  );
}
