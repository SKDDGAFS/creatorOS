export const apiUrl =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ??
  "http://127.0.0.1:8000";
export type Video = {
  id: string;
  channel_id: string;
  platform: "youtube" | "instagram" | "tiktok";
  title: string;
  status: "draft" | "scheduled" | "published" | "failed";
  published_at: string | null;
  media_path: string | null;
  created_at: string;
  transcript: string | null;
  ai_analysis: Record<string, unknown> | null;
  draft_metadata: {
    platform: Video["platform"];
    fields: Record<string, unknown>;
  } | null;
};
export type Channel = {
  id: string;
  platform: "youtube" | "instagram" | "tiktok";
  name: string;
  is_authorized: boolean;
};
export type ScheduledPost = {
  id: string;
  video_id: string;
  channel_id: string;
  platform: Channel["platform"];
  scheduled_at: string | null;
  timezone: string;
  status: "draft" | "scheduled" | "cancelled";
  metadata: Record<string, unknown>;
};
export type WatchFolderIngestResult = {
  imported: Video[];
  skipped: { filename: string; reason: string }[];
};
export type VideoMetric = {
  id: string;
  video_id: string;
  captured_at: string;
  views: number;
  likes: number;
  comments: number;
  shares: number;
  watch_time_seconds: number;
  average_view_duration_seconds: number;
  impressions: number;
  click_through_rate: string;
};
export type DashboardSnapshot = {
  videos: Video[];
  channels: Channel[];
  posts: ScheduledPost[];
  recentVideos: Video[];
  latestMetrics: Record<string, VideoMetric | null>;
};
async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { ...init, cache: "no-store" });
  if (!response.ok)
    throw new Error(
      (await response.json().catch(() => null))?.detail ?? "Request failed",
    );
  return (await response.json()) as T;
}
export async function getVideos(
  offset: number,
  signal: AbortSignal,
  limit = 20,
  refresh = 0,
): Promise<Video[]> {
  const response = await fetch(
    `${apiUrl}/api/videos?limit=${limit}&offset=${offset}&refresh=${refresh}`,
    { signal, cache: "no-store" },
  );
  if (!response.ok) throw new Error("Content unavailable");
  const data: unknown = await response.json();
  if (
    !Array.isArray(data) ||
    !data.every(
      (item) =>
        item !== null &&
        typeof item === "object" &&
        typeof item.id === "string" &&
        typeof item.channel_id === "string" &&
        typeof item.title === "string" &&
        typeof item.created_at === "string" &&
        !Number.isNaN(Date.parse(item.created_at)) &&
        ["draft", "scheduled", "published", "failed"].includes(item.status) &&
        (item.published_at === null ||
          (typeof item.published_at === "string" &&
            !Number.isNaN(Date.parse(item.published_at)))),
    )
  )
    throw new Error("Invalid content response");
  return data as Video[];
}
export async function getDashboardSnapshot(
  signal: AbortSignal,
): Promise<DashboardSnapshot> {
  const [posts, channels] = await Promise.all([
    getQueue(signal),
    json<Channel[]>(`${apiUrl}/api/channels?limit=100&offset=0`, { signal }),
  ]);
  const videos: Video[] = [];
  for (let offset = 0; ; offset += 100) {
    const page = await getVideos(offset, signal, 100);
    videos.push(...page);
    if (page.length < 100) break;
  }

  const recentVideos = [...videos]
    .sort(
      (first, second) =>
        Date.parse(second.created_at) - Date.parse(first.created_at),
    )
    .slice(0, 12);
  const metricEntries = await Promise.all(
    recentVideos.map(async (video) => {
      const metrics = await json<VideoMetric[]>(
        `${apiUrl}/api/videos/${video.id}/metrics?order=newest&limit=1&offset=0`,
        { signal },
      );
      return [video.id, metrics[0] ?? null] as const;
    }),
  );

  return {
    videos,
    channels,
    posts,
    recentVideos,
    latestMetrics: Object.fromEntries(metricEntries),
  };
}
export function setupLocal(signal?: AbortSignal) {
  return json<Channel[]>(`${apiUrl}/api/local/setup`, {
    method: "POST",
    signal,
  });
}
export function getQueue(signal?: AbortSignal) {
  return json<ScheduledPost[]>(`${apiUrl}/api/scheduled-posts`, { signal });
}
export function schedulePost(payload: Record<string, unknown>) {
  return json<ScheduledPost>(`${apiUrl}/api/scheduled-posts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
export function updatePost(id: string, payload: Record<string, unknown>) {
  return json<ScheduledPost>(`${apiUrl}/api/scheduled-posts/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
export function uploadVideo(channelId: string, file: File) {
  const form = new FormData();
  form.set("channel_id", channelId);
  form.set("file", file);
  return json<Video>(`${apiUrl}/api/videos/upload`, {
    method: "POST",
    body: form,
  });
}
export function prepareVideo(id: string) {
  return json<Video>(`${apiUrl}/api/videos/${id}/prepare`, { method: "POST" });
}
export function updateVideo(id: string, payload: Record<string, unknown>) {
  return json<Video>(`${apiUrl}/api/videos/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
export function ingestWatchFolder(channelId: string) {
  return json<WatchFolderIngestResult>(`${apiUrl}/api/videos/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ channel_id: channelId }),
  });
}
