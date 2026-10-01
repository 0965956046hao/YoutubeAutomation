"use client";

import { VideoItem, formatDate, formatViews, lowThumbnailUrl, parseDuration } from "@/lib/api";
import { startVideoDownload } from "@/lib/downloads";
import { DownloadIcon } from "@/components/icons";

export default function VideoGrid({
  videos,
  onSelect,
}: {
  videos: VideoItem[];
  onSelect: (v: VideoItem) => void;
}) {
  if (videos.length === 0) {
    return (
      <div className="double-bezel">
        <div className="double-bezel-inner p-10 text-center">
          <p className="text-[14px] text-ink-muted">
            Không có video nào trong khoảng thời gian này. Thêm kênh ở tab Cấu hình rồi bấm Tải lại.
          </p>
        </div>
      </div>
    );
  }
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
      {videos.map((v, i) => (
        <button
          key={v.video_id}
          onClick={() => onSelect(v)}
          className="double-bezel text-left animate-fade-up"
          style={{ animationDelay: `${Math.min(i, 8) * 60}ms` }}
        >
          <div className="double-bezel-inner overflow-hidden">
            <div className="relative aspect-video bg-black/40">
              {v.thumbnail ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={lowThumbnailUrl(v.video_id)} alt={v.title} className="h-full w-full object-cover" loading="lazy" />
              ) : (
                <div className="flex h-full items-center justify-center text-ink-light">No thumbnail</div>
              )}
              {v.duration && (
                <span className="absolute bottom-2 right-2 rounded bg-black/80 px-1.5 py-0.5 text-[11px] font-medium">
                  {parseDuration(v.duration)}
                </span>
              )}
            </div>
            <div className="p-4">
              <p className="line-clamp-2 text-[14px] font-semibold leading-snug">{v.title}</p>
              <p className="mt-1.5 truncate text-[12px] text-ink-muted">{v.channel_title}</p>
              <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                <span className="tag">{formatDate(v.published_at)}</span>
                <span className="tag">{formatViews(v.view_count)} lượt xem</span>
                <button
                  className="tag inline-flex cursor-pointer items-center gap-1 hover:text-accent-light"
                  onClick={(e) => {
                    e.stopPropagation();
                    startVideoDownload(v.video_id).catch((err) => console.error(err));
                  }}
                  title="Tải mp4 về máy — theo dõi tiến độ ở popup góc phải dưới"
                  aria-label="Tải"
                >
                  <DownloadIcon className="h-3 w-3 shrink-0" />
                </button>
                <a
                  className="tag hover:text-accent-light"
                  href={v.url}
                  target="_blank"
                  rel="noreferrer"
                  onClick={(e) => e.stopPropagation()}
                >
                  ↗ YouTube
                </a>
              </div>
            </div>
          </div>
        </button>
      ))}
    </div>
  );
}
