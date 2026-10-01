"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import {
  AnalyzeResult,
  SavedVideoSummary,
  TitleAiResult,
  analyzeLink,
  copyImage,
  copyText,
  deleteSavedVideo,
  formatDate,
  formatViews,
  generateChatGptThumbnail,
  generatedThumbnailUrl,
  getSavedVideo,
  listSavedVideos,
  lowThumbnailUrl,
  openChatGptLogin,
  parseDuration,
  saveAnalyzedVideo,
  saveGeneratedThumbnail,
  suggestTitles,
  thumbnailUrl,
} from "@/lib/api";
import { DownloadIcon } from "@/components/icons";

/** Tab Phân tích link: paste link YT bất kỳ → full info + Gemini gợi ý tiêu đề. */
export default function LinkAnalyzer() {
  const [url, setUrl] = useState("");
  const [info, setInfo] = useState<AnalyzeResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [ai, setAi] = useState<TitleAiResult | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState("");
  const [copied, setCopied] = useState("");
  const [thumbMsg, setThumbMsg] = useState("");
  const [partNum, setPartNum] = useState(1);
  const [titleSuffix, setTitleSuffix] = useState("Tiêu Dao Vietsub");
  const [saved, setSaved] = useState<SavedVideoSummary[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const [savedThumb, setSavedThumb] = useState("");
  const [thumbState, setThumbState] = useState<"live" | "local" | "gone">("live");
  const [thumbTitle, setThumbTitle] = useState("");
  const [gptPrompt, setGptPrompt] = useState("");
  const [gptBusy, setGptBusy] = useState(false);
  const [gptSaving, setGptSaving] = useState(false);
  const [gptMsg, setGptMsg] = useState("");
  const [generatedUrl, setGeneratedUrl] = useState("");
  const [generatedPreviewUrl, setGeneratedPreviewUrl] = useState("");
  const [generatedPreviewBlob, setGeneratedPreviewBlob] = useState<Blob | null>(null);
  const [generatedExpanded, setGeneratedExpanded] = useState("");
  const [detailView, setDetailView] = useState<"info" | "titles" | "thumbnail">("info");

  async function loadSaved() {
    try {
      setSaved(await listSavedVideos());
    } catch {
      /* backend chưa chạy */
    }
  }

  useEffect(() => {
    loadSaved();
  }, []);

  useEffect(() => {
    if (!expanded && !generatedExpanded) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setExpanded(false);
        setGeneratedExpanded("");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [expanded, generatedExpanded]);

  useEffect(() => {
    return () => {
      if (generatedPreviewUrl) URL.revokeObjectURL(generatedPreviewUrl);
    };
  }, [generatedPreviewUrl]);

  function flash(id: string) {
    setCopied(id);
    setTimeout(() => setCopied(""), 1500);
  }

  function composeTitle(t: string): string {
    return `Full Phần ${partNum} | ${t} | ${titleSuffix}`;
  }

  function buildGptPrompt(title = thumbTitle, part = partNum): string {
    return `@Tạo hình ảnh Hãy tạo hình giống ảnh tham chiếu đính kèm để làm thumbnail cho video YouTube. Dùng tiêu đề tiếng Việt: "${title}". Giữ font đơn giản, rõ ràng, dễ đọc, chữ nổi bật khi xem nhỏ. Chỉnh kích thước đúng thumbnail YouTube 16:9 (1280x720), dùng tông màu hài hòa trung tính, bớt chói. Bổ sung chữ "Phần ${part}" thật to, rõ, cùng font với tiêu đề ở góc trên bên phải. Xóa toàn bộ chữ và logo gốc ở góc trên bên trái và góc trên bên phải trước khi đặt chữ mới. Giữ nguyên nhân vật chính, bối cảnh và phong cách; không thêm logo hoặc watermark mới. Chỉ tạo 1 ảnh hoàn chỉnh, không giải thích.`;
  }

  function applyThumbnailTitle(title: string) {
    setThumbTitle(title);
    setGptPrompt(title ? buildGptPrompt(title) : "");
  }

  async function handleAnalyze() {
    if (!url.trim()) return;
    setLoading(true);
    setError("");
    setInfo(null);
    setAi(null);
    setAiError("");
    setSavedThumb("");
    setThumbState("live");
    setSaveMsg("");
    setThumbTitle("");
    setGptPrompt("");
    setGptMsg("");
    setGeneratedUrl("");
    setGeneratedPreviewUrl("");
    setGeneratedPreviewBlob(null);
    setDetailView("info");
    try {
      setInfo(await analyzeLink(url.trim()));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Phân tích thất bại");
    } finally {
      setLoading(false);
    }
  }

  async function handleAi() {
    if (!info?.title) return;
    setAiLoading(true);
    setAiError("");
    try {
      const result = await suggestTitles(info.title);
      setAi(result);
      setThumbTitle("");
      setGptPrompt("");
    } catch (e) {
      setAiError(e instanceof Error ? e.message : "Gọi Gemini thất bại");
    } finally {
      setAiLoading(false);
    }
  }

  async function handleSave() {
    if (!info) return;
    try {
      const res = await saveAnalyzedVideo(info, ai);
      setSaveMsg(res.thumbnail_saved ? "Đã lưu phân tích + thumbnail." : "Đã lưu phân tích (không tải được thumbnail).");
      loadSaved();
    } catch (e) {
      setSaveMsg(e instanceof Error ? e.message : "Lưu thất bại");
    }
  }

  async function handleOpenSaved(videoId: string) {
    setError("");
    try {
      const data = await getSavedVideo(videoId);
      setInfo(data.info);
      setAi(data.ai);
      setAiError("");
      setSaveMsg("");
      setSavedThumb(data.thumbnail_local || "");
      setThumbState("live");
      setThumbTitle("");
      setGptPrompt("");
      setGeneratedUrl(data.generated_thumbnail || "");
      setGeneratedPreviewUrl("");
      setGeneratedPreviewBlob(null);
      setDetailView("info");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Mở thất bại");
    }
  }

  async function handleDeleteSaved(videoId: string) {
    try {
      await deleteSavedVideo(videoId);
      loadSaved();
      if (info?.video_id === videoId) setSaveMsg("");
    } catch (e) {
      setSaveMsg(e instanceof Error ? e.message : "Xóa thất bại");
    }
  }

  async function handleChatGptLogin() {
    try {
      setGptMsg(await openChatGptLogin());
    } catch (e) {
      setGptMsg(e instanceof Error ? e.message : "Không mở được ChatGPT.");
    }
  }

  async function handleGenerateThumbnail() {
    if (!info || !thumbTitle.trim()) return;
    setGptBusy(true);
    setGptMsg("Đang lưu ảnh gốc và chờ ChatGPT tạo ảnh (có thể mất 2–5 phút)…");
    try {
      await saveAnalyzedVideo(info, ai);
      const prompt = gptPrompt.trim() || buildGptPrompt();
      const result = await generateChatGptThumbnail({
        video_id: info.video_id,
        title: thumbTitle.trim(),
        part: partNum,
        prompt,
      });
      if (result.status === "need_login") {
        setGptMsg(result.detail);
        return;
      }
      setGeneratedPreviewBlob(result.image);
      setGeneratedPreviewUrl(URL.createObjectURL(result.image));
      setGptMsg("Đã tạo ảnh xem trước. Bấm Lưu ảnh nếu muốn giữ lại.");
    } catch (e) {
      setGptMsg(e instanceof Error ? e.message : "Tạo thumbnail thất bại.");
    } finally {
      setGptBusy(false);
    }
  }

  async function handleSaveGeneratedThumbnail() {
    if (!info || !generatedPreviewBlob) return;
    setGptSaving(true);
    setGptMsg("Đang lưu thumbnail…");
    try {
      await saveGeneratedThumbnail(info.video_id, generatedPreviewBlob);
      setGeneratedUrl(`${generatedThumbnailUrl(info.video_id)}?v=${Date.now()}`);
      setGeneratedPreviewUrl("");
      setGeneratedPreviewBlob(null);
      setGptMsg("Đã lưu thumbnail mới bên dưới ảnh gốc.");
      loadSaved();
    } catch (e) {
      setGptMsg(e instanceof Error ? e.message : "Lưu thumbnail thất bại.");
    } finally {
      setGptSaving(false);
    }
  }

  function handleDiscardGeneratedThumbnail() {
    setGeneratedPreviewUrl("");
    setGeneratedPreviewBlob(null);
    setGeneratedExpanded("");
    setGptMsg("Đã bỏ ảnh xem trước, ảnh không được lưu.");
  }

  const thumbnailTitleOptions = info
    ? [
        { label: "Tiêu đề gốc", value: info.title },
        ...(ai?.translation ? [{ label: "Bản dịch raw", value: ai.translation }] : []),
        ...(ai?.options || []).map((value, index) => ({ label: `Gợi ý ${index + 1}`, value })),
      ].filter(
        (option, index, options) => option.value && options.findIndex((item) => item.value === option.value) === index,
      )
    : [];

  return (
    <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-[minmax(20rem,25%)_minmax(0,1fr)]">
      {/* ── Ô paste link ── */}
      <div className="double-bezel animate-fade-up xl:col-span-2">
        <div className="double-bezel-inner p-5">
          <span className="eyebrow">Phân tích link YouTube</span>
          <div className="mt-3 flex flex-col gap-2 sm:flex-row">
            <input
              className="input-field font-mono !text-[12px]"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleAnalyze()}
              placeholder="Dán link video: youtube.com/watch?v=… / youtu.be/… / shorts/…"
            />
            <button
              className="btn-island-primary btn-sm shrink-0"
              disabled={loading || !url.trim()}
              onClick={handleAnalyze}
            >
              {loading ? "Đang lấy…" : "Phân tích"}
            </button>
          </div>
          {error && <p className="mt-2 text-[12px] text-red-300">{error}</p>}
        </div>
      </div>

      {/* ── Video đã lưu ── */}
      {saved.length > 0 && (
        <div className="double-bezel xl:sticky xl:top-4 xl:col-start-1 xl:row-start-2 animate-fade-up">
          <aside className="double-bezel-inner flex max-h-[22rem] flex-col p-3 xl:max-h-[calc(100dvh-7.5rem)] xl:min-h-[34rem]">
            <div className="flex items-center justify-between px-1 pt-1">
              <span className="eyebrow">Đã lưu · {saved.length}</span>
              <span className="text-[10px] text-ink-light">Chọn để mở</span>
            </div>
            <div className="scrollbar-thin mt-3 flex-1 space-y-1.5 overflow-y-auto pr-1">
              {saved.map((s) => (
                <div
                  key={s.video_id}
                  className={`flex cursor-pointer items-center gap-2.5 rounded-lg p-2 ring-1 transition-colors ${
                    info?.video_id === s.video_id
                      ? "bg-accent-muted ring-accent/40"
                      : "bg-white/[0.03] ring-white/10 hover:bg-white/[0.06]"
                  }`}
                  onClick={() => handleOpenSaved(s.video_id)}
                >
                  {s.thumbnail_local || s.thumbnail ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={lowThumbnailUrl(s.video_id)} alt="" className="h-11 w-[4.5rem] shrink-0 rounded object-cover" loading="lazy" />
                  ) : (
                    <div className="h-11 w-[4.5rem] shrink-0 rounded bg-white/10" />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="line-clamp-2 text-[12px] font-medium leading-[1.35]" title={s.title}>{s.title || s.video_id}</p>
                    <p className="mt-0.5 truncate text-[11px] text-ink-light">
                      {s.channel_title}
                      {s.saved_at > 0 && ` · ${new Date(s.saved_at * 1000).toLocaleString("vi-VN", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}`}
                    </p>
                  </div>
                  {s.has_ai && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-accent" title="Đã có tiêu đề AI" />}
                  {s.has_generated_thumbnail && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" title="Đã có ảnh GPT" />}
                  <button
                    className="tag shrink-0 cursor-pointer !text-[10px] hover:text-red-300"
                    title="Xóa khỏi danh sách lưu"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteSaved(s.video_id);
                    }}
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          </aside>
        </div>
      )}

      {info && (
        <div className={`grid min-w-0 gap-4 xl:col-start-2 xl:row-start-2 ${saved.length === 0 ? "xl:col-span-2 xl:col-start-1" : ""} lg:grid-cols-[minmax(18rem,0.62fr)_minmax(0,1.38fr)]`}>
          {/* ── Cột trái: thumbnail + meta ── */}
          <div className="double-bezel self-start animate-fade-up lg:sticky lg:top-4">
            <div className="double-bezel-inner overflow-hidden">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              {thumbState === "gone" ? (
                <div className="flex aspect-video w-full flex-col items-center justify-center gap-1 bg-black/40 text-ink-light">
                  <span className="text-[13px]">Thumbnail không còn khả dụng</span>
                  <span className="text-[11px]">Link gốc đã chết và chưa kịp lưu ảnh</span>
                </div>
              ) : (
                <img
                  src={thumbState === "local" && savedThumb ? savedThumb : thumbnailUrl(info.video_id)}
                  alt=""
                  title="Bấm để phóng to"
                  onClick={() => setExpanded(true)}
                  onError={() => setThumbState((s) => (s === "live" ? "local" : "gone"))}
                  className="aspect-video w-full cursor-zoom-in bg-black/40 object-cover"
                />
              )}
              {expanded &&
                createPortal(
                  <div
                    className="fixed inset-0 z-[60] flex items-center justify-center bg-black/80 p-6 backdrop-blur-sm"
                    onClick={() => setExpanded(false)}
                  >
                    <button
                      className="icon-btn absolute right-5 top-5"
                      title="Đóng (Esc)"
                      onClick={() => setExpanded(false)}
                    >
                      ✕
                    </button>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={thumbState === "local" && savedThumb ? savedThumb : thumbnailUrl(info.video_id)}
                      alt=""
                      title="Bấm để thu nhỏ"
                      onClick={() => setExpanded(false)}
                      className="max-h-full max-w-5xl cursor-zoom-out rounded-lg object-contain ring-1 ring-white/20 animate-scale-in"
                    />
                  </div>,
                  document.body,
                )}
              {generatedUrl && (
                <div className="border-t border-white/10 p-3.5">
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <span className="text-[11px] font-semibold uppercase tracking-wider text-emerald-300">
                      Thumbnail ChatGPT đã lưu
                    </span>
                    <div className="flex gap-1.5">
                      <button
                        className="tag cursor-pointer hover:text-accent-light"
                        onClick={() => copyImage(generatedUrl).then(() => setGptMsg("Đã copy thumbnail ChatGPT."))}
                      >
                        Copy
                      </button>
                      <a
                        className="tag cursor-pointer hover:text-accent-light"
                        href={generatedUrl}
                        download={`${info.video_id}-chatgpt-thumbnail.png`}
                        title="Tải ảnh"
                        aria-label="Tải thumbnail ChatGPT"
                      >
                        <DownloadIcon className="h-3 w-3" />
                      </a>
                    </div>
                  </div>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={generatedUrl}
                    alt="Thumbnail ChatGPT đã lưu"
                    className="aspect-video w-full cursor-zoom-in rounded-md bg-black/40 object-cover ring-1 ring-white/10"
                    onClick={() => setGeneratedExpanded(generatedUrl)}
                  />
                </div>
              )}
              {generatedExpanded && createPortal(
                <div
                  className="fixed inset-0 z-[70] flex items-center justify-center bg-black/85 p-6 backdrop-blur-sm"
                  onClick={() => setGeneratedExpanded("")}
                >
                  <button className="icon-btn absolute right-5 top-5" onClick={() => setGeneratedExpanded("")}>✕</button>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={generatedExpanded}
                    alt="Thumbnail ChatGPT"
                    className="max-h-full max-w-6xl cursor-zoom-out rounded-lg object-contain ring-1 ring-white/20 animate-scale-in"
                  />
                </div>,
                document.body,
              )}
              <div className="space-y-2 p-3.5">
                <div className="flex flex-wrap gap-1.5">
                  {info.published_at && <span className="tag">{formatDate(info.published_at)}</span>}
                  {info.duration && <span className="tag">{parseDuration(info.duration)}</span>}
                  {info.view_count > 0 && <span className="tag">{formatViews(info.view_count)} xem</span>}
                </div>
                <div className="flex flex-wrap gap-2 pt-1">
                  <button className="btn-island-primary btn-xs" onClick={handleSave}>
                    Lưu phân tích
                  </button>
                  <button
                    className="btn-island-secondary btn-xs"
                    onClick={() => {
                      copyImage(thumbnailUrl(info.video_id))
                        .then(() => setThumbMsg("Đã copy thumbnail — Ctrl+V để dán."))
                        .catch(() => setThumbMsg("Copy ảnh thất bại."));
                    }}
                  >
                    Copy thumbnail
                  </button>
                  <a
                    className="btn-island-secondary btn-xs"
                    href={thumbnailUrl(info.video_id)}
                    download
                    title="Tải ảnh"
                    aria-label="Tải ảnh"
                  >
                    <DownloadIcon className="h-3 w-3 shrink-0" />
                  </a>
                  <a className="btn-island-secondary btn-xs" href={info.url} target="_blank" rel="noreferrer">
                    Mở video ↗
                  </a>
                </div>
                {thumbMsg && <p className="text-[11px] text-accent-light">{thumbMsg}</p>}
                {saveMsg && <p className="text-[11px] text-emerald-300">{saveMsg}</p>}
              </div>
            </div>
          </div>

          {/* ── Cột phải: thông tin / AI / thumbnail ── */}
          <section className="min-w-0 space-y-3">
            <nav className="double-bezel animate-fade-up" aria-label="Chế độ xem phân tích">
              <div className="double-bezel-inner flex flex-wrap items-center gap-1.5 p-2">
                {([
                  ["info", "Thông tin video"],
                  ["titles", ai ? "Tiêu đề AI · xong" : "Tiêu đề AI"],
                  [
                    "thumbnail",
                    generatedPreviewUrl ? "Thumbnail · chờ lưu" : generatedUrl ? "Thumbnail · xong" : "Thumbnail GPT",
                  ],
                ] as const).map(([key, label]) => (
                  <button
                    key={key}
                    className={`tag cursor-pointer !px-3.5 !py-2 !text-[12px] ${detailView === key ? "chip-active" : "hover:text-ink"}`}
                    onClick={() => setDetailView(key)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </nav>
            {info.warning && (
              <div className="double-bezel">
                <div className="double-bezel-inner px-4 py-3 text-[12px] text-warn">⚠ {info.warning}</div>
              </div>
            )}

            {detailView === "info" && (
            <div className="double-bezel animate-fade-up" style={{ animationDelay: "60ms" }}>
              <div className="double-bezel-inner space-y-3 p-4">
                <div>
                  <div className="mb-1 flex items-center gap-2">
                    <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-light">Tiêu đề gốc</span>
                    <button
                      className="tag cursor-pointer hover:text-accent-light"
                      onClick={() => {
                        copyText(info.title);
                        flash("title");
                      }}
                    >
                      {copied === "title" ? "✓" : "Copy"}
                    </button>
                  </div>
                  <p className="text-[15px] font-semibold leading-snug">{info.title || "(không lấy được)"}</p>
                  {info.channel_title && (
                    <p className="mt-1 text-[12px] text-ink-muted">{info.channel_title}</p>
                  )}
                </div>

                {info.description && (
                  <div>
                    <div className="mb-1 flex items-center gap-2">
                      <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-light">Mô tả</span>
                      <button
                        className="tag cursor-pointer hover:text-accent-light"
                        onClick={() => {
                          copyText(info.description);
                          flash("desc");
                        }}
                      >
                        {copied === "desc" ? "✓" : "Copy"}
                      </button>
                    </div>
                    <p className="scrollbar-thin max-h-32 overflow-y-auto whitespace-pre-wrap pr-1 text-[13px] leading-relaxed text-ink-muted">
                      {info.description}
                    </p>
                  </div>
                )}

                {info.tags.length > 0 && (
                  <div>
                    <div className="mb-1.5 flex items-center gap-2">
                      <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-light">
                        Thẻ ({info.tags.length})
                      </span>
                      <button
                        className="tag cursor-pointer hover:text-accent-light"
                        onClick={() => {
                          copyText(info.tags.join(", "));
                          flash("tags");
                        }}
                      >
                        {copied === "tags" ? "✓" : "Copy hết"}
                      </button>
                    </div>
                    <div className="scrollbar-thin flex max-h-24 flex-wrap gap-1.5 overflow-y-auto pr-1">
                      {info.tags.map((t) => (
                        <button
                          key={t}
                          className="tag cursor-pointer hover:text-accent-light"
                          title="Bấm để copy thẻ này"
                          onClick={() => {
                            copyText(t);
                            flash(`tag:${t}`);
                          }}
                        >
                          {copied === `tag:${t}` ? `✓ ${t}` : t}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {info.hashtags.length > 0 && (
                  <div>
                    <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-ink-light">Hashtag</span>
                    <div className="flex flex-wrap gap-1.5">
                      {info.hashtags.map((h) => (
                        <span key={h} className="tag !text-accent-light !border-accent/30">
                          {h}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
            )}

            {/* ── Gemini gợi ý tiêu đề ── */}
            {detailView === "titles" && (
            <div className="double-bezel animate-fade-up" style={{ animationDelay: "120ms" }}>
              <div className="double-bezel-inner p-5">
                <div className="flex flex-wrap items-center gap-3">
                  <span className="eyebrow">Gemini · dịch + gợi ý tiêu đề{ai?.model ? ` · ${ai.model}` : ""}</span>
                  <button
                    className="btn-island-primary btn-sm ml-auto"
                    disabled={aiLoading || !info.title}
                    onClick={handleAi}
                  >
                    {aiLoading ? "Gemini đang viết…" : ai ? "Viết lại" : "Dịch + gợi ý (~70 ký tự)"}
                  </button>
                </div>
                {aiError && <p className="mt-2 text-[12px] text-red-300">{aiError}</p>}

                {ai && (
                  <div className="mt-4 space-y-3">
                    <div className="flex flex-col gap-2 rounded-lg bg-white/[0.04] p-3.5 ring-1 ring-white/10 sm:flex-row sm:items-end">
                      <label className="block">
                        <span className="mb-1 block text-[11px] font-medium text-ink-muted">Số phần</span>
                        <input
                          className="input-field !w-24"
                          type="number"
                          min={1}
                          value={partNum}
                          onChange={(e) => {
                            const next = Math.max(1, Number(e.target.value) || 1);
                            setPartNum(next);
                            setGptPrompt(thumbTitle ? buildGptPrompt(thumbTitle, next) : "");
                          }}
                        />
                      </label>
                      <label className="block flex-1">
                        <span className="mb-1 block text-[11px] font-medium text-ink-muted">Hậu tố (sau dấu |)</span>
                        <input
                          className="input-field"
                          value={titleSuffix}
                          onChange={(e) => setTitleSuffix(e.target.value)}
                          placeholder="Tiêu Dao Vietsub"
                        />
                      </label>
                    </div>
                    <div className="rounded-lg bg-black/30 p-3.5 ring-1 ring-white/10">
                      <div className="mb-1 flex items-center gap-2">
                        <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-light">Bản dịch raw</span>
                        <button
                          className="tag cursor-pointer hover:text-accent-light"
                          onClick={() => {
                            copyText(ai.translation);
                            flash("raw");
                          }}
                        >
                          {copied === "raw" ? "✓" : "Copy"}
                        </button>
                      </div>
                      <p className="text-[13px] leading-relaxed">{ai.translation}</p>
                    </div>
                    {ai.options.map((opt, i) => {
                      const full = composeTitle(opt);
                      return (
                        <div key={i} className="rounded-lg bg-accent-muted p-3.5 ring-1 ring-accent/25">
                          <div className="flex items-start gap-2">
                            <span className="tag shrink-0">{i + 1} · {opt.length} ký tự</span>
                            <p className="min-w-0 flex-1 text-[13px] leading-relaxed text-ink-muted">{opt}</p>
                            <button
                              className="tag shrink-0 cursor-pointer hover:text-accent-light"
                              onClick={() => {
                                applyThumbnailTitle(opt);
                                setGptMsg("Đã chọn tiêu đề này cho thumbnail.");
                              }}
                            >
                              Dùng cho ảnh
                            </button>
                            <button
                              className="tag shrink-0 cursor-pointer hover:text-accent-light"
                              onClick={() => {
                                copyText(opt);
                                flash(`opt:${i}`);
                              }}
                            >
                              {copied === `opt:${i}` ? "✓" : "Copy"}
                            </button>
                          </div>
                          <div className="mt-2.5 flex items-start gap-2 rounded-md bg-black/30 p-2.5 ring-1 ring-white/10">
                            <p className="min-w-0 flex-1 text-[13px] font-semibold leading-relaxed">{full}</p>
                            <button
                              className="tag shrink-0 cursor-pointer hover:text-accent-light"
                              title="Copy chuỗi hoàn chỉnh"
                              onClick={() => {
                                copyText(full);
                                flash(`full:${i}`);
                              }}
                            >
                              {copied === `full:${i}` ? "✓ Đã copy" : `Copy full · ${full.length} ký tự`}
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
                {!ai && !aiError && (
                  <p className="mt-3 text-[12px] text-ink-light">
                    Gemini sẽ dịch tiêu đề sang tiếng Việt và gợi ý 3–4 tiêu đề hấp dẫn khoảng 70 ký tự. Cần lưu Gemini API key ở tab Cấu hình trước.
                  </p>
                )}
              </div>
            </div>
            )}

            {/* ── ChatGPT Plus browser thumbnail ── */}
            {detailView === "thumbnail" && (
            <div className="double-bezel animate-fade-up" style={{ animationDelay: "180ms" }}>
              <div className="double-bezel-inner p-5">
                <div className="flex flex-wrap items-center gap-3">
                  <span className="eyebrow">ChatGPT Plus · tạo lại thumbnail</span>
                  <button className="btn-island-secondary btn-sm ml-auto" onClick={handleChatGptLogin}>
                    Mở / đăng nhập ChatGPT
                  </button>
                </div>
                <p className="mt-2 text-[12px] leading-relaxed text-ink-muted">
                  Dùng trực tiếp giao diện chatgpt.com bằng Chrome profile riêng. Không cần OpenAI API key; cần tài khoản ChatGPT đã đăng nhập.
                </p>

                <div className="mt-4 grid gap-3 sm:grid-cols-[110px_1fr]">
                  <label className="block">
                    <span className="mb-1 block text-[11px] font-medium text-ink-muted">Số phần</span>
                    <input
                      className="input-field"
                      type="number"
                      min={1}
                      value={partNum}
                          onChange={(e) => {
                            const next = Math.max(1, Number(e.target.value) || 1);
                            setPartNum(next);
                            setGptPrompt(thumbTitle ? buildGptPrompt(thumbTitle, next) : "");
                          }}
                    />
                  </label>
                  <label className="block">
                    <span className="mb-1 block text-[11px] font-medium text-ink-muted">Chọn tiêu đề dùng trên ảnh</span>
                    <select
                      className="input-field mb-2"
                      value={thumbnailTitleOptions.some((option) => option.value === thumbTitle) ? thumbTitle : ""}
                      onChange={(e) => applyThumbnailTitle(e.target.value)}
                    >
                      <option value="">Chọn một tiêu đề…</option>
                      {thumbnailTitleOptions.map((option) => (
                        <option key={`${option.label}:${option.value}`} value={option.value}>
                          {option.label} · {option.value}
                        </option>
                      ))}
                    </select>
                    <span className="mb-1 block text-[11px] font-medium text-ink-muted">Tiêu đề đã chọn / tùy chỉnh</span>
                    <input
                      className="input-field"
                      value={thumbTitle}
                      onChange={(e) => applyThumbnailTitle(e.target.value)}
                      placeholder="Mặc định để trống…"
                    />
                  </label>
                </div>

                <label className="mt-3 block">
                  <span className="mb-1 block text-[11px] font-medium text-ink-muted">Prompt gửi ChatGPT (được phép chỉnh sửa)</span>
                  <textarea
                    className="textarea-field !font-sans !text-[12px] !leading-relaxed"
                    rows={7}
                    value={gptPrompt}
                    onChange={(e) => setGptPrompt(e.target.value)}
                    placeholder={buildGptPrompt()}
                  />
                </label>

                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <button
                    className="btn-island-primary btn-sm"
                    disabled={gptBusy || !thumbTitle.trim()}
                    onClick={handleGenerateThumbnail}
                  >
                    {gptBusy ? "ChatGPT đang tạo ảnh…" : `Tạo thumbnail · Phần ${partNum}`}
                  </button>
                  <button
                    className="btn-island-secondary btn-sm"
                    disabled={gptBusy || !thumbTitle.trim()}
                    onClick={() => setGptPrompt(buildGptPrompt())}
                  >
                    Khôi phục prompt mẫu
                  </button>
                </div>
                {gptMsg && <p className="mt-2 text-[12px] text-accent-light">{gptMsg}</p>}

                {generatedPreviewUrl && (
                  <div className="mt-4 rounded-lg bg-black/30 p-3 ring-1 ring-amber-300/30">
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <span className="text-[11px] font-semibold uppercase tracking-wider text-amber-200">
                        Ảnh xem trước · chưa lưu
                      </span>
                      <span className="text-[10px] text-ink-light">Thoát trang sẽ mất ảnh này</span>
                    </div>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={generatedPreviewUrl}
                      alt="Thumbnail ChatGPT chưa lưu"
                      className="aspect-video w-full cursor-zoom-in rounded-md object-cover"
                      onClick={() => setGeneratedExpanded(generatedPreviewUrl)}
                    />
                    <div className="mt-3 flex flex-wrap gap-2">
                      <button
                        className="btn-island-primary btn-sm"
                        disabled={gptSaving}
                        onClick={handleSaveGeneratedThumbnail}
                      >
                        {gptSaving ? "Đang lưu…" : "Lưu ảnh này"}
                      </button>
                      <button
                        className="btn-island-secondary btn-sm"
                        disabled={gptSaving}
                        onClick={handleDiscardGeneratedThumbnail}
                      >
                        Thoát, không lưu
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
