"use client";

import {
  DownloadTask,
  removeDownloadTask,
  taskFileUrl,
  useDownloadTasks,
} from "@/lib/downloads";
import { DownloadIcon } from "@/components/icons";

function statusColor(t: DownloadTask): string {
  if (t.status === "done") return "text-emerald-300";
  if (t.status === "error") return "text-red-300";
  if (t.status === "cancelled") return "text-ink-light";
  return "text-accent-light";
}

function Card({ task }: { task: DownloadTask }) {
  const active = task.status === "queued" || task.status === "downloading";
  return (
    <div className="double-bezel animate-scale-in">
      <div className="double-bezel-inner p-3.5">
        <div className="flex items-start gap-2">
          <div className="min-w-0 flex-1">
            <p className="line-clamp-1 text-[13px] font-semibold" title={task.title}>
              {task.title}
            </p>
            <p className={`mt-0.5 text-[11px] ${statusColor(task)}`}>
              {task.status === "error" ? task.error || "Tải thất bại." : task.message}
            </p>
          </div>
          <button
            className="icon-btn !h-6 !w-6 shrink-0 !text-[11px]"
            title="Xóa khỏi danh sách"
            onClick={() => removeDownloadTask(task.task_id)}
          >
            ✕
          </button>
        </div>

        {active && (
          <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-white/10">
            <div
              className="h-full rounded-full bg-accent transition-all duration-500"
              style={{ width: `${Math.max(2, task.progress)}%` }}
            />
          </div>
        )}

        <div className="mt-2.5 flex items-center gap-2">
          {task.status === "done" && (
            <a
              className="btn-island-primary btn-xs"
              href={taskFileUrl(task.task_id)}
              download={task.filename || true}
            >
              <DownloadIcon className="h-3 w-3 shrink-0" /> Lưu về máy
            </a>
          )}
          {active && (
            <button
              className="btn-island-danger btn-xs"
              onClick={() => removeDownloadTask(task.task_id)}
            >
              Hủy
            </button>
          )}
          {task.status === "done" && task.size > 0 && (
            <span className="tag">{(task.size / 1e6).toFixed(1)} MB</span>
          )}
          {active && <span className="tag ml-auto">{task.progress.toFixed(0)}%</span>}
        </div>
      </div>
    </div>
  );
}

/** Popup theo dõi tiến trình tải — góc phải dưới, mỗi task 1 card nhỏ. */
export default function DownloadPopups() {
  const tasks = useDownloadTasks();
  if (tasks.length === 0) return null;
  const visible = tasks.slice(0, 3);
  return (
    <div className="fixed bottom-5 right-5 z-50 flex w-[320px] flex-col gap-3">
      <p className="inline-flex items-center justify-end gap-1 text-[11px] text-ink-light">
        <DownloadIcon className="h-3 w-3 shrink-0" /> {tasks.length} tác vụ tải
      </p>
      {visible.map((t) => (
        <Card key={t.task_id} task={t} />
      ))}
      {tasks.length > visible.length && (
        <p className="text-right text-[11px] text-ink-light">
          +{tasks.length - visible.length} tác vụ khác
        </p>
      )}
    </div>
  );
}
