"use client";

import { useCallback, useEffect, useState } from "react";
import ConfigPanel from "@/components/ConfigPanel";
import DownloadPopups from "@/components/DownloadPopups";
import FacebookFlow from "@/components/FacebookFlow";
import LinkAnalyzer from "@/components/LinkAnalyzer";
import PostComposer from "@/components/PostComposer";
import RestrictedVideos from "@/components/RestrictedVideos";
import UploadDialog from "@/components/UploadDialog";
import VideoDetail from "@/components/VideoDetail";
import VideoGrid from "@/components/VideoGrid";
import { VideoItem, getAuthStatus, getRecent } from "@/lib/api";

type Tab = "recent" | "restricted" | "post" | "analyze" | "upload" | "config" | "facebook";

export default function Home() {
  const [tab, setTab] = useState<Tab>("recent");
  const [days, setDays] = useState(2);
  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [channels, setChannels] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<VideoItem | null>(null);
  const [connected, setConnected] = useState(false);
  const [channelTitle, setChannelTitle] = useState("");
  const [notice, setNotice] = useState("");
  const [facebookVideo, setFacebookVideo] = useState<VideoItem | null>(null);

  const load = useCallback(async (d: number) => {
    setLoading(true);
    setError("");
    try {
      const res = await getRecent(d);
      setVideos(res.videos);
      setChannels(res.channels);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Không tải được danh sách");
      setVideos([]);
    } finally {
      setLoading(false);
    }
  }, []);

  async function refreshAuth() {
    try {
      const st = await getAuthStatus();
      setConnected(st.connected);
      setChannelTitle(st.channel_title || "");
    } catch {
      /* backend chưa chạy */
    }
  }

  useEffect(() => {
    load(days);
    refreshAuth();
    if (new URLSearchParams(window.location.search).get("connected") === "1") {
      setNotice("Đã kết nối Google thành công.");
      window.history.replaceState({}, "", "/");
      refreshAuth();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <main className="mx-auto w-full max-w-[1800px] px-3 pb-20 pt-7 sm:px-5 md:pt-9 lg:px-7">
      {/* Header — cùng ngôn ngữ thị giác SubExtractor */}
      <header className="flex flex-wrap items-end justify-between gap-4 animate-fade-in">
        <div>
          <span className="eyebrow">YouTube Data API · OAuth 2.0</span>
          <h1 className="mt-3 text-3xl font-bold tracking-tight">
            {tab === "facebook" ? "YouTube → Facebook" : tab === "restricted" ? "Video của tôi bị hạn chế" : `Video mới trong ${days} ngày qua`}
          </h1>
          <p className="mt-1.5 text-[13px] text-ink-muted">
            {connected
              ? `Đã kết nối${channelTitle ? ` · ${channelTitle}` : ""}`
              : "Chưa kết nối Google — vào tab Cấu hình để login."}{" "}
            {channels.length > 0 && `· Theo dõi ${channels.length} kênh`}
          </p>
        </div>
        <nav className="flex flex-wrap gap-2">
          {(
            [
              ["recent", "Mới nhất"],
              ["restricted", "Bị hạn chế"],
              ["facebook", "YT → Facebook"],
              ["post", "Đăng bài"],
              ["analyze", "Phân tích"],
              ["upload", "Upload"],
              ["config", "Cấu hình"],
            ] as [Tab, string][]
          ).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`tag cursor-pointer !px-4 !py-2 !text-[12px] ${tab === key ? "chip-active" : "hover:text-ink"}`}
            >
              {label}
            </button>
          ))}
        </nav>
      </header>

      {notice && (
        <div className="double-bezel mt-6">
          <div className="double-bezel-inner px-5 py-3 text-[13px] text-emerald-300">{notice}</div>
        </div>
      )}

      <section className="mt-6">
        {tab === "recent" && (
          <>
            <div className="double-bezel mb-5">
              <div className="double-bezel-inner flex flex-wrap items-center gap-3 px-5 py-4">
                <span className="text-[13px] text-ink-muted">Khoảng thời gian:</span>
                {[1, 2, 3, 7].map((d) => (
                  <button
                    key={d}
                    onClick={() => {
                      setDays(d);
                      load(d);
                    }}
                    className={`tag cursor-pointer !px-3.5 !py-1.5 ${days === d ? "chip-active" : ""}`}
                  >
                    {d} ngày
                  </button>
                ))}
                <button className="btn-island-primary btn-sm ml-auto" disabled={loading} onClick={() => load(days)}>
                  {loading ? "Đang tải…" : "Tải lại"}
                </button>
              </div>
            </div>

            {error ? (
              <div className="double-bezel">
                <div className="double-bezel-inner p-6">
                  <p className="text-[13px] text-red-300">{error}</p>
                  <button className="btn-island-secondary btn-sm mt-3" onClick={() => setTab("config")}>
                    Mở Cấu hình
                  </button>
                </div>
              </div>
            ) : loading ? (
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
                {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
                  <div key={i} className="double-bezel">
                    <div className="double-bezel-inner overflow-hidden">
                      <div className="diagonal-stripes aspect-video animate-pulse bg-white/[0.04]" />
                      <div className="space-y-2 p-4">
                        <div className="h-4 w-3/4 animate-pulse rounded bg-white/10" />
                        <div className="h-3 w-1/2 animate-pulse rounded bg-white/10" />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <>
                <p className="mb-3 text-[12px] text-ink-light">
                  Tìm thấy <b className="text-ink">{videos.length}</b> video
                </p>
                <VideoGrid videos={videos} onSelect={setSelected} />
              </>
            )}
          </>
        )}

        {tab === "post" && <PostComposer />}

        {tab === "facebook" && (
          <FacebookFlow initialVideo={facebookVideo} onOpenConfig={() => setTab("config")} />
        )}

        {tab === "restricted" && (
          <RestrictedVideos
            connected={connected}
            onSelect={setSelected}
            onOpenConfig={() => setTab("config")}
            onQueued={(msg) => { setTab("facebook"); setNotice(msg); }}
          />
        )}

        {tab === "analyze" && <LinkAnalyzer />}

        {tab === "upload" && (
          <UploadDialog onDone={(url) => setNotice(`Upload xong — xem tại ${url}`)} />
        )}

        {tab === "config" && (
          <ConfigPanel
            onSaved={() => {
              refreshAuth();
              load(days);
            }}
          />
        )}
      </section>

      {selected && (
        <VideoDetail video={selected} onClose={() => setSelected(null)} onUpdated={() => load(days)}
          onFacebook={(video) => { setFacebookVideo(video); setSelected(null); setTab("facebook"); }} />
      )}
      <DownloadPopups />
    </main>
  );
}
