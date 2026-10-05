import axios from "axios";

const api = axios.create({ baseURL: "/api", timeout: 60000 });

api.interceptors.response.use(
  (res) => res,
  (error) => {
    const msg =
      error.response?.data?.detail || error.message || "Có lỗi xảy ra";
    return Promise.reject(new Error(msg));
  },
);

export interface AppConfig {
  youtube_client_id: string;
  has_client_secret: boolean;
  has_api_key: boolean;
  oauth_redirect_uri: string;
  track_channel_ids: string[];
  days_window: number;
  has_gemini_key: boolean;
  post_template: string;
  connected: boolean;
  channel_title: string;
  facebook_page_id: string;
  has_facebook_token: boolean;
  facebook_api_version: string;
}

export interface VideoItem {
  video_id: string;
  channel_id: string;
  channel_title: string;
  title: string;
  description: string;
  published_at: string;
  thumbnail: string;
  duration: string;
  view_count: number;
  like_count: number;
  url: string;
  tags?: string[];
}

export interface OwnedVideoItem extends VideoItem {
  privacy_status: string;
  upload_status: string;
  failure_reason: string;
  rejection_reason: string;
  region_blocked: string[];
  region_allowed: string[];
  age_restricted: boolean;
  restricted: boolean;
}

export async function getConfig(): Promise<AppConfig> {
  const res = await api.get<AppConfig>("/config");
  return res.data;
}

export async function saveConfig(body: {
  youtube_client_id?: string;
  youtube_client_secret?: string;
  youtube_api_key?: string;
  oauth_redirect_uri?: string;
  track_channel_ids?: string[];
  days_window?: number;
  gemini_api_key?: string;
  post_template?: string;
  facebook_page_id?: string;
  facebook_page_token?: string;
  facebook_api_version?: string;
}): Promise<void> {
  await api.post("/config", body);
}

export async function getAuthUrl(): Promise<string> {
  const res = await api.get<{ url: string }>("/youtube/auth/url");
  return res.data.url;
}

export type CookieBrowser = "" | "chrome" | "firefox" | "safari" | "edge" | "brave";

export interface YoutubeCookiesStatus {
  has_cookies: boolean;
  size: number;
  mtime: number;
}

export async function getYoutubeCookiesStatus(): Promise<YoutubeCookiesStatus> {
  return (await api.get<YoutubeCookiesStatus>("/youtube/cookies/status")).data;
}

export async function uploadYoutubeCookies(file: File): Promise<void> {
  const form = new FormData();
  form.append("file", file);
  await api.post("/youtube/cookies", form, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 30000,
  });
}

export async function deleteYoutubeCookies(): Promise<void> {
  await api.delete("/youtube/cookies");
}

export const COVER_PROMPT_DEFAULT =
  "Làm rõ nét hình ảnh, giữ lại thông tin Phần ở góc trên phải, chỉnh tỉ lệ hình thành 1088 × 1446";

export interface FacebookFlowInput {
  video_id: string;
  title: string;
  description: string;
  tags: string[];
  target_minutes: number;
  search_window: number;
  silence_db: number;
  silence_duration: number;
  cookies_from_browser: CookieBrowser;
  full_video?: boolean;
  comment_blocked?: boolean;
  add_intro_outro?: boolean;
  intro_seconds?: number;
  outro_seconds?: number;
  cover_prompt?: string;
}

export interface FacebookFlowTask {
  task_id: string;
  video_id: string;
  title: string;
  page_id: string;
  page_name: string;
  status: "queued" | "checking" | "downloading" | "analyzing" | "cutting" | "uploading" | "processing" | "publishing" | "done" | "error" | "cancelling" | "cancelled";
  progress: number;
  download_progress?: number;
  message: string;
  error: string;
  created_at: number;
  description?: string;
  facebook_video_id: string;
  facebook_url: string;
  clip_ready: boolean;
  thumbnail_ready?: boolean;
  thumbnail_set?: boolean;
  cover_ready?: boolean;
  intro_outro?: {
    intro_seconds: number;
    outro_seconds: number;
    duration: number;
    cover_ai: boolean;
  } | null;
  comment_posted?: boolean;
  comment_error?: string;
  can_resume: boolean;
  queue_position?: number;
  delete_requested?: boolean;
  cut: { seconds: number; source_duration: number; reason: string } | null;
}

export async function checkFacebookPage(): Promise<{ id: string; name: string }> {
  return (await api.post("/facebook/check")).data;
}

export async function createFacebookFlow(body: FacebookFlowInput): Promise<FacebookFlowTask> {
  return (await api.post("/facebook/flows", body)).data;
}

export async function createFacebookFlows(items: FacebookFlowInput[]): Promise<{
  tasks: FacebookFlowTask[];
  skipped: { video_id: string; reason: string }[];
  count: number;
}> {
  return (await api.post("/facebook/flows/batch", { items })).data;
}

export async function listFacebookFlows(): Promise<FacebookFlowTask[]> {
  return (await api.get<{ tasks: FacebookFlowTask[] }>("/facebook/flows")).data.tasks;
}

export async function resumeFacebookFlow(taskId: string): Promise<FacebookFlowTask> {
  return (await api.post(`/facebook/flows/${taskId}/resume`)).data;
}

export async function cancelFacebookFlow(taskId: string): Promise<FacebookFlowTask> {
  return (await api.post(`/facebook/flows/${taskId}/cancel`)).data;
}

export async function setFacebookFlowThumbnail(taskId: string): Promise<FacebookFlowTask> {
  return (await api.post(`/facebook/flows/${taskId}/thumbnail`)).data;
}

export async function deleteFacebookFlow(taskId: string): Promise<void> {
  await api.delete(`/facebook/flows/${taskId}`);
}

export async function getAuthStatus(): Promise<{ connected: boolean; channel_title: string }> {
  const res = await api.get("/youtube/auth/status");
  return res.data;
}

export async function disconnectAuth(): Promise<void> {
  await api.post("/youtube/auth/disconnect");
}

export async function getRecent(days = 2): Promise<{ videos: VideoItem[]; count: number; channels: string[] }> {
  const res = await api.get("/videos/recent", { params: { days } });
  return res.data;
}

export async function getOwnedVideos(limit = 200): Promise<{
  videos: OwnedVideoItem[];
  count: number;
  restricted_count: number;
}> {
  const res = await api.get("/videos-mine", { params: { limit } });
  return res.data;
}

export async function getVideoDetail(videoId: string): Promise<VideoItem> {
  const res = await api.get(`/videos/${videoId}`);
  return res.data;
}

export async function updateVideo(
  videoId: string,
  body: { title?: string; description?: string; privacy?: string },
): Promise<void> {
  await api.put(`/videos/${videoId}`, body);
}

export function downloadUrl(videoId: string, quality = "best"): string {
  return `/api/videos/${videoId}/download?quality=${quality}`;
}

export async function uploadVideo(
  file: File,
  meta: { title: string; description: string; privacy: string; tags: string },
  onProgress?: (pct: number) => void,
): Promise<{ video_id: string; url: string }> {
  const form = new FormData();
  form.append("file", file);
  form.append("title", meta.title);
  form.append("description", meta.description);
  form.append("privacy", meta.privacy);
  form.append("tags", meta.tags);
  const res = await api.post("/videos/upload", form, {
    timeout: 120 * 60 * 1000,
    onUploadProgress: (e) => {
      if (onProgress && e.total) onProgress(Math.round((e.loaded * 100) / e.total));
    },
  });
  return res.data;
}

export async function postComment(videoId: string, text: string): Promise<{ note?: string }> {
  const res = await api.post(`/videos/${videoId}/comment`, { text });
  return res.data;
}

export function thumbnailUrl(videoId: string): string {
  return `/api/videos/${videoId}/thumbnail`;
}

/** Ảnh nhẹ 320x180 chỉ dành cho list/card; chi tiết và copy dùng thumbnailUrl(). */
export function lowThumbnailUrl(videoId: string): string {
  return `https://i.ytimg.com/vi/${videoId}/mqdefault.jpg`;
}

export function safeFileName(name: string, maxLen = 100): string {
  const cleaned = (name || "")
    .replace(/[\\/:*?"<>|\u0000-\u001f]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^[.]+|[.]+$/g, "");
  return (cleaned || "video").slice(0, maxLen);
}

export const POST_VARS = ["{title}", "{url}", "{video_id}", "{channel}", "{date}"] as const;

export function renderPost(template: string, v: VideoItem): string {
  return template
    .split("{title}").join(v.title)
    .split("{url}").join(v.url || `https://youtu.be/${v.video_id}`)
    .split("{video_id}").join(v.video_id)
    .split("{channel}").join(v.channel_title)
    .split("{date}").join(formatDate(v.published_at));
}

export async function copyImage(url: string): Promise<void> {
  if (!navigator.clipboard?.write || typeof ClipboardItem === "undefined") {
    throw new Error("Trình duyệt không hỗ trợ copy ảnh vào clipboard");
  }
  // Gọi Clipboard API ngay trong cú click để không mất user activation trong
  // lúc fetch và chuyển JPEG sang PNG.
  const pngPromise = (async () => {
    const res = await fetch(url);
    if (!res.ok) throw new Error("Không tải được ảnh");
    const blob = await res.blob();
    const bitmap = await createImageBitmap(blob);
    const canvas = document.createElement("canvas");
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Không thể chuyển đổi thumbnail");
    context.drawImage(bitmap, 0, 0);
    bitmap.close();
    return new Promise<Blob>((resolve, reject) => {
      canvas.toBlob(
        (png) => png ? resolve(png) : reject(new Error("Không thể chuyển thumbnail sang PNG")),
        "image/png",
      );
    });
  })();
  await navigator.clipboard.write([new ClipboardItem({ "image/png": pngPromise })]);
}

export async function copyText(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
}

export interface AnalyzeResult {
  video_id: string;
  channel_id: string;
  channel_title: string;
  title: string;
  description: string;
  published_at: string;
  thumbnail: string;
  duration: string;
  view_count: number;
  like_count: number;
  url: string;
  tags: string[];
  hashtags: string[];
  warning: string;
}

export interface TitleAiResult {
  translation: string;
  options: string[];
  raw: string;
  model: string;
}

export async function analyzeLink(url: string): Promise<AnalyzeResult> {
  const res = await api.post<AnalyzeResult>("/analyze", { url });
  return res.data;
}

export async function suggestTitles(title: string): Promise<TitleAiResult> {
  const res = await api.post<TitleAiResult>("/analyze/title-ai", { title });
  return res.data;
}

export interface SavedVideoSummary {
  video_id: string;
  title: string;
  channel_title: string;
  thumbnail: string;
  thumbnail_local: string;
  has_ai: boolean;
  has_generated_thumbnail: boolean;
  has_cover?: boolean;
  saved_at: number;
}

export interface SavedVideoDetail {
  info: AnalyzeResult;
  ai: TitleAiResult | null;
  saved_at: number;
  thumbnail_local: string;
  generated_thumbnail: string;
  cover?: string;
}

export async function listSavedVideos(): Promise<SavedVideoSummary[]> {
  const res = await api.get<{ videos: SavedVideoSummary[] }>("/analyzed");
  return res.data.videos;
}

export async function saveAnalyzedVideo(
  info: AnalyzeResult,
  ai: TitleAiResult | null,
): Promise<{ status: string; video_id: string; thumbnail_saved: boolean }> {
  const res = await api.post("/analyzed", { info, ai });
  return res.data;
}

export async function getSavedVideo(videoId: string): Promise<SavedVideoDetail> {
  const res = await api.get<SavedVideoDetail>(`/analyzed/${videoId}`);
  return res.data;
}

export async function deleteSavedVideo(videoId: string): Promise<void> {
  await api.delete(`/analyzed/${videoId}`);
}

export async function openChatGptLogin(): Promise<string> {
  const res = await api.post<{ detail: string }>("/chatgpt/login");
  return res.data.detail;
}

export async function generateChatGptThumbnail(body: {
  video_id: string;
  title: string;
  part: number;
  prompt?: string;
}): Promise<{ status: "done"; image: Blob } | { status: "need_login"; detail: string }> {
  const res = await fetch("/api/chatgpt-thumbnail", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const contentType = res.headers.get("content-type") || "";
  if (res.ok && contentType.startsWith("image/")) {
    return { status: "done", image: await res.blob() };
  }
  const data = await res.json().catch(() => ({ detail: "Tạo thumbnail thất bại." }));
  if (!res.ok) throw new Error(data.detail || "Tạo thumbnail thất bại.");
  return { status: "need_login", detail: data.detail || "Hãy đăng nhập ChatGPT rồi thử lại." };
}

export async function saveGeneratedThumbnail(
  videoId: string,
  image: Blob,
  slot?: "cover",
): Promise<{ status: string; url: string }> {
  const form = new FormData();
  form.append("file", image, slot === "cover" ? "cover.png" : "thumbnail.png");
  const res = await api.post(`/analyzed/${videoId}/generated-thumbnail${slot === "cover" ? "?slot=cover" : ""}`, form);
  return res.data;
}

export function coverUrl(videoId: string): string {
  return `/api/analyzed/${videoId}/cover`;
}

export function generatedThumbnailUrl(videoId: string): string {
  return `/api/analyzed/${videoId}/generated-thumbnail`;
}

export function formatViews(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return `${n}`;
}

export function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString("vi-VN", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function parseDuration(iso: string): string {
  const m = /PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/.exec(iso || "");
  if (!m) return "";
  const h = parseInt(m[1] || "0", 10);
  const min = parseInt(m[2] || "0", 10);
  const s = parseInt(m[3] || "0", 10);
  const mm = h > 0 ? String(min).padStart(2, "0") : String(min);
  const ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}
