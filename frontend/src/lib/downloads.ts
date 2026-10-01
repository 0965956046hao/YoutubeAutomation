"use client";

import { useSyncExternalStore } from "react";

export interface DownloadTask {
  task_id: string;
  video_id: string;
  title: string;
  quality: string;
  status: "queued" | "downloading" | "done" | "error" | "cancelled";
  progress: number;
  message: string;
  filename: string;
  error: string;
  size: number;
}

let tasks: DownloadTask[] = [];
const listeners = new Set<() => void>();
let timer: ReturnType<typeof setInterval> | null = null;

function emit() {
  listeners.forEach((l) => l());
}

function subscribe(fn: () => void) {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

async function refresh() {
  try {
    const res = await fetch("/api/download-tasks");
    if (res.ok) {
      const data = await res.json();
      tasks = data.tasks ?? [];
      emit();
    }
  } catch {
    /* backend chưa chạy — giữ list cũ */
  }
  const active = tasks.some((t) => t.status === "queued" || t.status === "downloading");
  if (!active && timer) {
    clearInterval(timer);
    timer = null;
  }
}

function ensurePolling() {
  refresh();
  if (!timer) timer = setInterval(refresh, 2000);
}

export async function startVideoDownload(
  videoId: string,
  quality = "best",
  cookiesFromBrowser = "",
): Promise<void> {
  const params = new URLSearchParams({ quality });
  if (cookiesFromBrowser) params.set("cookies_from_browser", cookiesFromBrowser);
  const res = await fetch(`/api/videos/${videoId}/download-tasks?${params}`, {
    method: "POST",
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || "Không tạo được tác vụ tải");
  }
  ensurePolling();
}

export async function removeDownloadTask(taskId: string): Promise<void> {
  await fetch(`/api/download-tasks/${taskId}`, { method: "DELETE" }).catch(() => {});
  refresh();
}

export function taskFileUrl(taskId: string): string {
  return `/api/download-tasks/${taskId}/file`;
}

export function useDownloadTasks(): DownloadTask[] {
  return useSyncExternalStore(subscribe, () => tasks, () => tasks);
}
