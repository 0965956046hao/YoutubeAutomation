"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  AppConfig, CookieBrowser, COVER_PROMPT_DEFAULT, FacebookFlowTask, VideoItem,
  analyzeLink, cancelFacebookFlow, coverUrl, createFacebookFlow, createFacebookFlows, deleteFacebookFlow, formatDate, generateChatGptThumbnail, getConfig, getRecent, getSavedVideo, getVideoDetail,
  listFacebookFlows, lowThumbnailUrl, resumeFacebookFlow, retryFacebookFlow, saveAnalyzedVideo, saveGeneratedThumbnail, setFacebookFlowThumbnail, thumbnailUrl,
} from "@/lib/api";
import YoutubeCookies from "@/components/YoutubeCookies";

const STATUS: Record<FacebookFlowTask["status"], string> = {
  queued: "Đang chờ", checking: "Kiểm tra Page", downloading: "Tải YouTube",
  analyzing: "Tìm khoảng lặng", cutting: "Cắt video", uploading: "Upload Facebook",
  processing: "Facebook xử lý", publishing: "Đang đăng", done: "Đã đăng", error: "Có lỗi",
  cancelling: "Đang hủy…", cancelled: "Đã hủy",
};

function isActive(task: FacebookFlowTask) {
  return !["done", "error", "cancelled"].includes(task.status);
}

function clock(seconds: number) {
  const rounded = Math.round(seconds);
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, "0")}`;
}

function FlowProgress({ task }: { task: FacebookFlowTask }) {
  const downloading = task.status === "downloading";
  const progress = Math.max(0, Math.min(100, downloading ? task.download_progress ?? 0 : task.progress));
  const label = downloading ? "Tải từ YouTube" : "Tiến độ toàn bộ flow";
  return (
    <div className="mt-3">
      <div className="mb-2 flex items-center justify-between gap-2 text-[11px] text-ink-muted">
        <span>{label}</span>
        <span className="tag tabular-nums !text-accent-light">{progress.toFixed(downloading ? 1 : 0)}%</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-white/10" role="progressbar"
        aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}>
        <div className="h-full rounded-full bg-accent transition-all duration-500" style={{ width: `${progress}%` }} />
      </div>
      {downloading && <p className="mt-1.5 text-[11px] text-ink-light">Tiến độ luồng đang tải; video và âm thanh có thể tải riêng trước khi ghép.</p>}
    </div>
  );
}

function captionPreview(title: string, description: string, tags: string[], videoId: string) {
  let body = description.trim();
  while (body && body.split("\n", 1)[0].trim() === title.trim()) {
    const newline = body.indexOf("\n");
    body = newline < 0 ? "" : body.slice(newline + 1).trim();
  }
  const header = `${title.trim()}\n\nXem full tại : https://www.youtube.com/watch?v=${videoId}`.trim();
  const caption = [header, body].filter(Boolean).join("\n\n");
  const seen = new Set((caption.match(/#[\p{L}\p{N}_]+/gu) || []).map((tag) => tag.toLowerCase()));
  const hashtags: string[] = [];
  for (const tag of tags) {
    const cleaned = tag.normalize("NFC").replace(/[^\p{L}\p{N}_]/gu, "");
    if (!cleaned) continue;
    const hashtag = `#${cleaned}`;
    if (!seen.has(hashtag.toLowerCase())) {
      seen.add(hashtag.toLowerCase());
      hashtags.push(hashtag);
    }
  }
  return [caption, hashtags.join(" ")].filter(Boolean).join("\n\n");
}

export default function FacebookFlow({
  initialVideo, onOpenConfig,
}: {
  initialVideo: VideoItem | null;
  onOpenConfig: () => void;
}) {
  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [days, setDays] = useState(2);
  const [reload, setReload] = useState(0);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState("");
  const [selectedVideoId, setSelectedVideoId] = useState("");
  const [source, setSource] = useState<VideoItem | null>(null);
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [minutes, setMinutes] = useState(30);
  const [windowSeconds, setWindowSeconds] = useState(60);
  const [noiseDb, setNoiseDb] = useState(-35);
  const [silenceDuration, setSilenceDuration] = useState(0.5);
  const [browser, setBrowser] = useState<CookieBrowser>("");
  const [addIntroOutro, setAddIntroOutro] = useState(true);
  const [introSeconds, setIntroSeconds] = useState(0.1);
  const [outroSeconds, setOutroSeconds] = useState(10);
  const [coverPrompt, setCoverPrompt] = useState(COVER_PROMPT_DEFAULT);
  const [coverReady, setCoverReady] = useState<boolean | null>(null);
  const [gptBusy, setGptBusy] = useState(false);
  const [gptMsg, setGptMsg] = useState("");
  const [coverBuster, setCoverBuster] = useState(0);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [tasks, setTasks] = useState<FacebookFlowTask[]>([]);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [starting, setStarting] = useState(false);
  const [queueBusy, setQueueBusy] = useState(false);
  const [pendingTask, setPendingTask] = useState("");
  const [error, setError] = useState("");
  const [pollError, setPollError] = useState("");
  const [notice, setNotice] = useState("");
  const requestId = useRef(0);

  async function selectVideo(input: string, isLink = false) {
    const current = ++requestId.current;
    setSelectedVideoId(isLink ? "" : input);
    setLoading(true);
    setSource(null);
    setError("");
    setNotice("");
    setGptMsg("");
    setCoverReady(null);
    try {
      const info = isLink ? await analyzeLink(input) : await getVideoDetail(input);
      if (current !== requestId.current) return;
      setSelectedVideoId(info.video_id);
      setSource(info);
      setTitle(info.title.slice(0, 255));
      setDescription(info.description);
      setTags((info.tags || []).join(", "));
      setUrl(info.url);
      if ("warning" in info && info.warning) setNotice(String(info.warning));
      getSavedVideo(info.video_id).then(
        (saved) => { if (current === requestId.current) setCoverReady(Boolean(saved.cover)); },
        () => { if (current === requestId.current) setCoverReady(false); },
      );
    } catch (e) {
      if (current === requestId.current) {
        setSelectedVideoId("");
        setError(e instanceof Error ? e.message : "Không lấy được thông tin video.");
      }
    } finally {
      if (current === requestId.current) setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    setListLoading(true);
    setListError("");
    getRecent(days).then((result) => {
      if (active) setVideos(result.videos);
    }).catch((e) => {
      if (active) {
        setVideos([]);
        setListError(e instanceof Error ? e.message : "Không tải được danh sách video.");
      }
    }).finally(() => { if (active) setListLoading(false); });
    return () => { active = false; };
  }, [days, reload]);

  useEffect(() => {
    if (initialVideo) void selectVideo(initialVideo.video_id);
    return () => { requestId.current += 1; };
  }, [initialVideo]);

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    getConfig().then((value) => { if (!stopped) setConfig(value); })
      .catch((e) => { if (!stopped) setError(e.message); });
    async function poll() {
      try {
        const result = await listFacebookFlows();
        if (!stopped) { setTasks(result); setPollError(""); }
      } catch (e) {
        if (!stopped) setPollError(e instanceof Error ? e.message : "Mất kết nối tiến độ.");
      } finally {
        if (!stopped) timer = setTimeout(poll, 3000);
      }
    }
    void poll();
    return () => { stopped = true; clearTimeout(timer); };
  }, []);

  const configured = Boolean(config?.facebook_page_id && config.has_facebook_token);
  const tagList = tags.split(/[,\n]+/).map((tag) => tag.trim()).filter(Boolean);
  const activeTasks = useMemo(() => tasks.filter((t) => t.status !== "done"), [tasks]);
  const uploadedTasks = useMemo(() => tasks.filter((t) => t.status === "done"), [tasks]);

  function toggleCheck(id: string) {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleGenerateCover() {
    if (!source || gptBusy) return;
    setGptBusy(true);
    setGptMsg("Đang lưu ảnh gốc và chờ ChatGPT tạo cover 1088×1446 (có thể mất 2–5 phút)…");
    try {
      await saveAnalyzedVideo(
        { ...source, tags: source.tags || [], hashtags: [], warning: "" },
        null,
        "facebook-flow",
      );
      const result = await generateChatGptThumbnail({
        video_id: source.video_id,
        title: (title || source.title).trim(),
        part: 1,
        prompt: coverPrompt.trim() || COVER_PROMPT_DEFAULT,
      });
      if (result.status === "need_login") {
        setGptMsg(result.detail);
        return;
      }
      await saveGeneratedThumbnail(source.video_id, result.image, "cover");
      setCoverReady(true);
      setCoverBuster(Date.now());
      setGptMsg("Đã lưu ảnh bìa ChatGPT. Flow sẽ tự dùng ảnh này ở intro; nếu chưa kịp gen, flow dùng thumbnail gốc upscale.");
    } catch (e) {
      setGptMsg(e instanceof Error ? e.message : "Tạo cover thất bại.");
    } finally {
      setGptBusy(false);
    }
  }

  async function queueSelected() {
    const selected = videos.filter((v) => checked.has(v.video_id));
    if (selected.length === 0) return;
    setQueueBusy(true);
    setError("");
    try {
      const result = await createFacebookFlows(selected.map((v) => ({
        video_id: v.video_id,
        title: v.title.slice(0, 255) || v.video_id,
        description: v.description || "",
        tags: v.tags || [],
        target_minutes: minutes, search_window: windowSeconds, silence_db: noiseDb,
        silence_duration: silenceDuration, cookies_from_browser: browser,
        add_intro_outro: addIntroOutro, intro_seconds: introSeconds,
        outro_seconds: outroSeconds, cover_prompt: coverPrompt.trim() || COVER_PROMPT_DEFAULT,
      })));
      setTasks(await listFacebookFlows());
      const skipped = result.skipped.map((s) => `${s.video_id}: ${s.reason}`).join("\n");
      setNotice(`Đã thêm ${result.count} video vào hàng đợi — xử lý tuần tự, tự động cắt và đăng từng video.` +
        (skipped ? `\nBỏ qua:\n${skipped}` : ""));
      setChecked(new Set());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Không thêm được hàng đợi.");
    } finally {
      setQueueBusy(false);
    }
  }
  const activeForSource = tasks.some((task) => task.video_id === source?.video_id &&
    task.page_id === config?.facebook_page_id && isActive(task));

  async function start() {
    if (!source) return;
    setStarting(true);
    setError("");
    try {
      const task = await createFacebookFlow({
        video_id: source.video_id, title, description,
        tags: tagList,
        target_minutes: minutes, search_window: windowSeconds, silence_db: noiseDb,
        silence_duration: silenceDuration, cookies_from_browser: browser,
        add_intro_outro: addIntroOutro, intro_seconds: introSeconds,
        outro_seconds: outroSeconds, cover_prompt: coverPrompt.trim() || COVER_PROMPT_DEFAULT,
      });
      setTasks((previous) => [task, ...previous.filter((item) => item.task_id !== task.task_id)]);
      setNotice("Flow đã chạy nền. Bạn có thể chuyển tab; tiến độ và kết quả lưu tại đây." +
        (addIntroOutro && coverReady !== true
          ? " Chưa có cover AI — vẫn kịp bấm “Gen cover bằng ChatGPT” ngay bây giờ, nếu xong trước bước ghép thì flow sẽ dùng ảnh AI."
          : ""));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Không tạo được flow.");
    } finally {
      setStarting(false);
    }
  }

  async function taskAction(taskId: string, action: "resume" | "retry" | "delete" | "thumbnail" | "cancel") {
    setPendingTask(taskId);
    setError("");
    setNotice("");
    try {
      if (action === "resume") await resumeFacebookFlow(taskId);
      else if (action === "retry") {
        await retryFacebookFlow(taskId);
        setNotice("Đã cho flow chạy lại từ đầu (tải/cắt/ghép/upload lại toàn bộ).");
      }
      else if (action === "cancel") await cancelFacebookFlow(taskId);
      else if (action === "thumbnail") {
        await setFacebookFlowThumbnail(taskId);
        setNotice("Đã đặt thumbnail YouTube làm ảnh bìa video Facebook.");
      } else await deleteFacebookFlow(taskId);
      setTasks(await listFacebookFlows());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Thao tác thất bại.");
    } finally {
      setPendingTask("");
    }
  }

  return (
    <div className="grid items-start gap-5 lg:grid-cols-[380px_minmax(0,1fr)] animate-fade-up">
      <aside className="double-bezel min-w-0 lg:sticky lg:top-5" aria-label="Danh sách video YouTube">
        <div className="double-bezel-inner flex max-h-[520px] flex-col p-5 lg:max-h-[720px]">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="eyebrow">Chọn video · {checked.size}/{videos.length}</span>
            <div className="flex gap-1.5">
              {[1, 2, 3, 7].map((d) => (
                <button key={d} onClick={() => setDays(d)} aria-pressed={days === d}
                  className={`tag cursor-pointer ${days === d ? "chip-active" : ""}`}>
                  {d}d
                </button>
              ))}
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <button className="tag cursor-pointer" onClick={() => setChecked(new Set(videos.map((v) => v.video_id)))}>
              Chọn hết
            </button>
            <button className="tag cursor-pointer" onClick={() => setChecked(new Set())}>
              Bỏ hết
            </button>
            <button className="tag ml-auto cursor-pointer" disabled={listLoading} onClick={() => setReload((value) => value + 1)}>
              {listLoading ? "Đang tải…" : "↻ Tải lại"}
            </button>
          </div>
          <button className="btn-island-primary btn-sm mt-3 w-full"
            disabled={checked.size === 0 || queueBusy || starting || !configured}
            onClick={() => void queueSelected()}>
            {queueBusy ? "Đang thêm…" : `Thêm ${checked.size} video vào hàng đợi`}
          </button>
          <p className="mt-2 text-[11px] text-ink-light">Tích chọn nhiều video → xử lý tuần tự, tự cắt và đăng. Bấm vào video để xem/sửa nội dung trước khi đăng lẻ.</p>
          <div className="scrollbar-thin mt-3 min-h-0 flex-1 space-y-2 overflow-y-auto p-1" aria-busy={listLoading}>
            {listError && <p className="text-[12px] text-red-300" role="alert">{listError}</p>}
            {listLoading && <p className="text-[12px] text-ink-muted">Đang tải danh sách…</p>}
            {!listLoading && videos.map((video) => (
              <div key={video.video_id}
                className={`flex gap-3 rounded-lg p-2 ring-1 transition-colors ${
                  selectedVideoId === video.video_id
                    ? "bg-accent-muted ring-accent/40"
                    : "bg-white/[0.03] ring-white/10 hover:bg-white/[0.06]"
                }`}>
                <input type="checkbox" aria-label={`Chọn ${video.title}`}
                  className="mt-1 h-4 w-4 shrink-0 accent-[#4d93ff]"
                  checked={checked.has(video.video_id)}
                  onChange={() => toggleCheck(video.video_id)} />
                <button type="button" disabled={starting} onClick={() => void selectVideo(video.video_id)}
                  className="flex min-w-0 flex-1 gap-3 text-left">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={lowThumbnailUrl(video.video_id)} alt="" className="h-11 w-20 shrink-0 rounded object-cover" loading="lazy" />
                  <div className="min-w-0">
                    <p className="line-clamp-2 text-[12px] font-medium leading-snug">{video.title}</p>
                    <p className="mt-0.5 text-[11px] text-ink-light">{video.channel_title} · {formatDate(video.published_at)}</p>
                  </div>
                </button>
              </div>
            ))}
            {!listLoading && !listError && videos.length === 0 && (
              <p className="text-[12px] text-ink-muted">Không có video nào trong {days} ngày qua.</p>
            )}
          </div>
        </div>
      </aside>

      <div className="min-w-0 space-y-5">
      <div className="double-bezel">
        <div className="double-bezel-inner p-5 sm:p-6">
          <span className="eyebrow">YouTube → khoảng lặng → Facebook Page</span>
          <h2 className="mt-2 text-xl font-semibold">Cắt phần đầu và đăng Facebook</h2>
          <p className="mt-2 max-w-4xl text-[13px] leading-relaxed text-ink-muted">
            Tải video → tìm khoảng lặng gần {minutes} phút → cắt MP4 → chuẩn hoá cover 1088×1446 → chèn cover vào đầu video (giữ tỉ lệ, căn giữa) → thêm outro template YouTube ở cuối → đăng cùng mô tả và hashtag.
            Video ngắn hơn mốc cắt được giữ toàn bộ. Tìm khoảng lặng giúp giảm cắt ngang câu, không đảm bảo hiểu ngữ nghĩa lời nói.
          </p>
          <p className="mt-2 text-[12px] text-ink-light">
            Video dài dùng API video của Page. Hiển thị dạng Reel phụ thuộc hỗ trợ hợp nhất video/Reels của Meta trên Page.
          </p>
          {config && !configured && (
            <div className="mt-4 flex flex-wrap items-center gap-3 rounded-lg bg-white/5 p-3">
              <p className="text-[13px] text-amber-200">Cần cấu hình Facebook Page ID và Page access token.</p>
              <button className="btn-island-secondary btn-sm" onClick={onOpenConfig}>Mở Cấu hình</button>
            </div>
          )}

          <div className="mt-5">
            <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); void selectVideo(url, true); }}>
              <label className="block min-w-0 flex-1">
                <span className="mb-1.5 block text-[12px] text-ink-muted">Hoặc dán link YouTube</span>
                <input className="input-field" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://www.youtube.com/watch?v=…" />
              </label>
              <button className="btn-island-secondary btn-sm" disabled={!url.trim() || loading || starting}>
                {loading ? "Đang lấy…" : "Lấy thông tin"}
              </button>
            </form>
          </div>

          {loading && <p className="mt-4 text-[13px] text-ink-muted" role="status">Đang lấy thông tin video…</p>}
          {!source && !loading && !error && <p className="mt-4 text-[13px] text-ink-muted">Chọn video trong danh sách hoặc dán link YouTube để bắt đầu.</p>}

          {source && (
            <form className="mt-5 space-y-4 border-t border-white/10 pt-5" onSubmit={(e) => { e.preventDefault(); void start(); }}>
              <div className="grid gap-5 xl:grid-cols-[200px_minmax(0,1fr)]">
                <div>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={thumbnailUrl(source.video_id)} alt={`Thumbnail ${source.title}`} className="aspect-video w-full rounded-lg object-cover" />
                  <p className="mt-2 text-[11px] text-ink-light">Dùng thumbnail gốc làm ảnh bìa Facebook.</p>
                  <a href={source.url} target="_blank" rel="noreferrer" className="mt-2 inline-block text-[12px] text-accent-light">Xem nguồn YouTube ↗</a>
                </div>
                <div className="space-y-3">
                  <label className="block">
                    <span className="mb-1.5 block text-[12px] text-ink-muted">Tiêu đề Facebook</span>
                    <input className="input-field" required maxLength={255} value={title} onChange={(e) => setTitle(e.target.value)} />
                  </label>
                  <label className="block">
                    <span className="mb-1.5 block text-[12px] text-ink-muted">Mô tả gốc / nội dung bổ sung</span>
                    <textarea className="textarea-field !font-sans !text-[13px]" rows={6} maxLength={20000} value={description} onChange={(e) => setDescription(e.target.value)} />
                  </label>
                  <label className="block">
                    <span className="mb-1.5 block text-[12px] text-ink-muted">Thẻ YouTube → hashtag Facebook (phân cách bằng dấu phẩy)</span>
                    <textarea className="textarea-field !font-sans !text-[13px]" rows={2} value={tags} onChange={(e) => setTags(e.target.value)} />
                  </label>
                </div>
              </div>
              <label className="block rounded-lg bg-white/[0.03] p-4 ring-1 ring-accent/30">
                <span className="mb-2 block text-[12px] font-semibold text-accent-light">Nội dung sẽ đăng Facebook</span>
                <textarea className="textarea-field !font-sans !text-[13px]" rows={8} readOnly
                  value={captionPreview(title, description, tagList, source.video_id)} />
                <span className="mt-2 block text-[11px] text-ink-light">
                  Dòng “Xem full tại” tự thêm dưới tiêu đề, cách một dòng trống. Bản xem trước cập nhật theo nội dung bạn chỉnh ở trên.
                </span>
              </label>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-5">
                <label className="block">
                  <span className="mb-1.5 block text-[12px] text-ink-muted">Lấy phần đầu (phút)</span>
                  <input className="input-field" type="number" required min={1} max={180} step={0.5} value={minutes} onChange={(e) => setMinutes(Number(e.target.value))} />
                </label>
                <label className="block">
                  <span className="mb-1.5 block text-[12px] text-ink-muted">Tìm quanh mốc ± (giây)</span>
                  <input className="input-field" type="number" required min={5} max={300} value={windowSeconds} onChange={(e) => setWindowSeconds(Number(e.target.value))} />
                </label>
                <label className="block">
                  <span className="mb-1.5 block text-[12px] text-ink-muted">Ngưỡng khoảng lặng (dB)</span>
                  <input className="input-field" type="number" required min={-60} max={-15} value={noiseDb} onChange={(e) => setNoiseDb(Number(e.target.value))} />
                </label>
                <label className="block">
                  <span className="mb-1.5 block text-[12px] text-ink-muted">Khoảng lặng tối thiểu (giây)</span>
                  <input className="input-field" type="number" required min={0.2} max={3} step={0.1} value={silenceDuration} onChange={(e) => setSilenceDuration(Number(e.target.value))} />
                </label>
                <label className="block">
                  <span className="mb-1.5 block text-[12px] text-ink-muted">Cookie YouTube</span>
                  <select className="input-field" value={browser} onChange={(e) => setBrowser(e.target.value as CookieBrowser)}>
                    <option value="">Không dùng</option>
                    <option value="chrome">Chrome</option><option value="firefox">Firefox</option>
                    <option value="safari">Safari</option><option value="edge">Edge</option><option value="brave">Brave</option>
                  </select>
                </label>
              </div>
              <YoutubeCookies />
              <div className="rounded-lg bg-white/[0.03] p-4 ring-1 ring-white/10">
                <label className="flex cursor-pointer items-center gap-2 text-[13px] font-semibold">
                  <input type="checkbox" className="h-4 w-4 accent-[#4d93ff]"
                    checked={addIntroOutro} onChange={(e) => setAddIntroOutro(e.target.checked)} />
                  Chèn cover vào đầu + outro YouTube ở cuối video
                </label>
                {addIntroOutro && (
                  <div className="mt-3 space-y-3">
                    <div className="grid gap-3 sm:grid-cols-2">
                      <label className="block">
                        <span className="mb-1.5 block text-[12px] text-ink-muted">Cover hiện ở đầu (giây, số lẻ được)</span>
                        <input className="input-field" type="number" min={0.1} max={10} step={0.1}
                          value={introSeconds} onChange={(e) => setIntroSeconds(Number(e.target.value))} />
                      </label>
                      <label className="block">
                        <span className="mb-1.5 block text-[12px] text-ink-muted">Outro template YT ở cuối (giây, số lẻ được)</span>
                        <input className="input-field" type="number" min={2} max={15} step={0.1}
                          value={outroSeconds} onChange={(e) => setOutroSeconds(Number(e.target.value))} />
                      </label>
                    </div>
                    <label className="block">
                      <span className="mb-1.5 block text-[12px] text-ink-muted">Prompt gen cover từ thumbnail (ChatGPT)</span>
                      <textarea className="textarea-field !font-sans !text-[13px]" rows={2}
                        value={coverPrompt} onChange={(e) => setCoverPrompt(e.target.value)} />
                    </label>
                    <div className="flex flex-wrap items-center gap-2">
                      <button type="button" className="btn-island-secondary btn-sm"
                        disabled={gptBusy || !source} onClick={() => void handleGenerateCover()}>
                        {gptBusy ? "ChatGPT đang tạo cover…" : "Gen cover bằng ChatGPT (1088×1446)"}
                      </button>
                      {coverReady === true && <span className="tag !text-emerald-300">Đã có ảnh bìa AI</span>}
                      {coverReady === false && <span className="tag">Chưa có ảnh bìa AI</span>}
                    </div>
                    {coverReady === true && source && (
                      /* eslint-disable-next-line @next/next/no-img-element */
                      <img src={`${coverUrl(source.video_id)}?v=${coverBuster}`} alt="Ảnh bìa ChatGPT 1088×1446"
                        className="w-40 rounded-lg object-cover ring-1 ring-white/20" loading="lazy" />
                    )}
                    {gptMsg && <p className="text-[12px] text-accent-light" role="status">{gptMsg}</p>}
                    <p className="text-[11px] text-ink-light">
                      Cover giữ tỉ lệ gốc và căn giữa video. Outro tự render tên kênh + thumbnail + tên video YouTube (không dán link) để người xem tìm tới bản gốc.
                      Nếu chưa kịp gen cover khi flow chạy, hệ thống tự upscale thumbnail gốc để không kẹt hàng đợi.
                    </p>
                  </div>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <button className="btn-island-primary btn-sm" disabled={starting || loading || !configured || activeForSource}>
                  {starting ? "Đang tạo flow…" : activeForSource ? "Video này đang có flow chạy" : "Tải → Cắt → Đăng Facebook"}
                </button>
                {configured && <span className="text-[12px] text-ink-light">Page đích: {config?.facebook_page_id}</span>}
              </div>
              {addIntroOutro && coverReady !== true && (
                <p className="mt-2 text-[12px] text-amber-200" role="status">
                  Worker không tự mở ChatGPT — muốn intro dùng ảnh AI thì bấm “Gen cover bằng ChatGPT (1088×1446)” ở trên trước khi flow chạy tới bước ghép.
                  Bỏ qua bước này thì flow dùng thumbnail gốc upscale.
                </p>
              )}
            </form>
          )}
          {notice && <p className="mt-4 text-[12px] text-accent-light" role="status">{notice}</p>}
          {error && <p className="mt-4 whitespace-pre-wrap text-[12px] text-red-300" role="alert">{error}</p>}
        </div>
      </div>

      <div className="flex items-center justify-between gap-3">
        <h3 className="text-[15px] font-semibold">Hàng đợi · {activeTasks.length}</h3>
        <span className="text-[11px] text-ink-light">Xử lý tuần tự từng video · tự cập nhật 3 giây</span>
      </div>
      {pollError && <p className="text-[12px] text-red-300" role="alert">Không cập nhật được tiến độ: {pollError}</p>}
      {tasks.length === 0 && !pollError && <p className="glass-panel rounded-xl p-6 text-[13px] text-ink-muted">Tích chọn video trong danh sách để thêm vào hàng đợi.</p>}
      {activeTasks.map((task) => (
        <article key={task.task_id} className="double-bezel">
          <div className="double-bezel-inner p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <h4 className="text-[14px] font-semibold">{task.title}</h4>
                <p className="mt-1 text-[11px] text-ink-light">
                  {task.queue_position ? `#${task.queue_position} trong hàng đợi · ` : ""}{task.page_name || task.page_id} · {new Date(task.created_at * 1000).toLocaleString("vi-VN")}
                </p>
              </div>
              <span className={`tag ${task.status === "error" ? "!text-red-300" : "!text-accent-light"}`}>{STATUS[task.status]}</span>
            </div>
            <FlowProgress task={task} />
            <p className="mt-2 text-[12px] text-ink-muted">{task.message}</p>
            {task.cut && <p className="mt-2 text-[12px] text-ink-muted">Điểm cắt: <b className="text-ink">{clock(task.cut.seconds)}</b> / {clock(task.cut.source_duration)} · {task.cut.reason}</p>}
            {task.intro_outro && (
              <p className="mt-1 text-[12px] text-ink-muted">
                Intro cover {task.intro_outro.intro_seconds} giây + outro YT {task.intro_outro.outro_seconds} giây · cover: {task.intro_outro.cover_ai ? "ảnh bìa ChatGPT" : "thumbnail gốc upscale"}.
              </p>
            )}
            {task.error && <p className="mt-2 whitespace-pre-wrap break-words text-[12px] text-red-300">{task.error}</p>}
            {task.comment_posted && <p className="mt-2 text-[12px] text-emerald-300">Đã đăng comment link Facebook lên video YouTube — vào Studio ghim tay.</p>}
            {task.comment_error && <p className="mt-2 whitespace-pre-wrap break-words text-[12px] text-red-300">{task.comment_error} Đăng tay trong Studio.</p>}
            <div className="mt-3 flex flex-wrap gap-2">
              {task.facebook_url && <a className="btn-island-secondary btn-xs" href={task.facebook_url} target="_blank" rel="noreferrer">Kiểm tra video Facebook ↗</a>}
              {task.status === "error" && !task.thumbnail_set && task.thumbnail_ready && task.facebook_video_id && <button className="btn-island-secondary btn-xs" disabled={Boolean(pendingTask)} onClick={() => taskAction(task.task_id, "thumbnail")} title="Đặt thumbnail YouTube làm ảnh bìa video Facebook">Đặt ảnh bìa YT</button>}
              {task.can_resume && <button className="btn-island-primary btn-xs" disabled={Boolean(pendingTask)} onClick={() => taskAction(task.task_id, "resume")}>Tiếp tục video đã upload</button>}
              {task.status === "error" && !task.can_resume && <button className="btn-island-primary btn-xs" disabled={Boolean(pendingTask)} onClick={() => taskAction(task.task_id, "retry")} title="Tải/cắt/ghép/upload lại toàn bộ từ đầu">Chạy lại từ đầu</button>}
              {task.clip_ready && <a className="btn-island-secondary btn-xs" href={`/api/facebook/flows/${task.task_id}/clip`} download>Tải video đã cắt</a>}
              {task.cover_ready && <a className="btn-island-secondary btn-xs" href={`/api/facebook/flows/${task.task_id}/cover`} download>Tải cover 1088×1446</a>}
              {isActive(task) && <button className="btn-island-danger btn-xs" disabled={Boolean(pendingTask) || task.status === "cancelling"}
                onClick={() => taskAction(task.task_id, "cancel")}>{task.status === "cancelling" ? "Đang hủy…" : "Hủy"}</button>}
              <button className="btn-island-secondary btn-xs" disabled={Boolean(pendingTask) || task.delete_requested}
                onClick={() => taskAction(task.task_id, "delete")} title="Dừng tác vụ, xóa file và lịch sử trên máy">
                {task.delete_requested ? "Đang hủy & xóa…" : isActive(task) ? "Hủy & xóa" : "Xóa file & lịch sử local"}
              </button>
            </div>
            {task.clip_ready && (
              <details className="mt-3 text-[12px] text-ink-muted">
                <summary className="cursor-pointer">Xem video đã cắt &amp; nội dung đăng</summary>
                <video className="mt-3 max-h-80 w-full rounded-lg bg-black" controls preload="none" poster={`/api/facebook/flows/${task.task_id}/thumbnail`} src={`/api/facebook/flows/${task.task_id}/clip`} />
                <p className="mt-3 whitespace-pre-wrap">{task.description}</p>
              </details>
            )}
          </div>
        </article>
      ))}

      <div className="flex items-center justify-between gap-3 pt-2">
        <h3 className="text-[15px] font-semibold">Đã upload · {uploadedTasks.length}</h3>
        <span className="text-[11px] text-ink-light">Lưu lại sau khi mở app · xem lại và tải clip</span>
      </div>
      {uploadedTasks.length === 0 && <p className="glass-panel rounded-xl p-6 text-[13px] text-ink-muted">Chưa có video nào đăng xong. Video đăng thành công sẽ nằm ở đây để xem lại và tải bản đã cắt.</p>}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 2xl:grid-cols-4">
        {uploadedTasks.map((task) => (
          <article key={task.task_id} className="double-bezel">
            <div className="double-bezel-inner h-full overflow-hidden">
              <div className="relative aspect-video bg-black/40">
                {task.thumbnail_ready ? (
                  /* eslint-disable-next-line @next/next/no-img-element */
                  <img src={`/api/facebook/flows/${task.task_id}/thumbnail`} alt={task.title}
                    className="h-full w-full object-cover" loading="lazy" />
                ) : (
                  <div className="flex h-full w-full items-center justify-center text-[11px] text-ink-light">Không còn ảnh</div>
                )}
                {task.cut && (
                  <span className="absolute bottom-1.5 right-1.5 rounded bg-black/80 px-1.5 py-0.5 text-[10px]">
                    {clock(task.cut.seconds)}
                  </span>
                )}
              </div>
              <div className="p-2.5 pb-1.5">
                <p className="line-clamp-1 text-[12px] font-semibold leading-snug" title={task.title}>{task.title}</p>
                <p className="mt-0.5 text-[10px] text-ink-light">
                  {new Date(task.created_at * 1000).toLocaleDateString("vi-VN")}
                </p>
              </div>
              <div className="flex gap-1.5 px-2.5 pb-2.5">
                {task.facebook_url && <a className="btn-island-primary btn-xs flex-1 !px-2" href={task.facebook_url} target="_blank" rel="noreferrer">Xem bài ↗</a>}
                {task.clip_ready && <a className="btn-island-secondary btn-xs flex-1 !px-2" href={`/api/facebook/flows/${task.task_id}/clip`} download>Tải clip</a>}
                {!task.thumbnail_set && task.thumbnail_ready && <button className="btn-island-secondary btn-xs flex-1 !px-2" disabled={Boolean(pendingTask)} onClick={() => taskAction(task.task_id, "thumbnail")} title="Đặt thumbnail YouTube làm ảnh bìa video Facebook">Đặt ảnh bìa</button>}
                <button className="btn-island-secondary btn-xs !px-2" disabled={Boolean(pendingTask)} onClick={() => taskAction(task.task_id, "delete")} title="Xóa file & lịch sử local">✕</button>
              </div>
              {task.clip_ready && (
                <details className="mx-2.5 mb-2.5 text-[11px] text-ink-muted">
                  <summary className="cursor-pointer">Xem lại</summary>
                  <video className="mt-2 max-h-48 w-full rounded-lg bg-black" controls preload="none" poster={`/api/facebook/flows/${task.task_id}/thumbnail`} src={`/api/facebook/flows/${task.task_id}/clip`} />
                  <p className="mt-2 whitespace-pre-wrap">{task.description}</p>
                </details>
              )}
            </div>
          </article>
        ))}
      </div>
      </div>
    </div>
  );
}
