export const apiUrl =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ??
  "http://127.0.0.1:8000";
export type Video = {
  id: string;
  channel_id: string;
  title: string;
  status: "draft" | "scheduled" | "published" | "failed";
  published_at: string | null;
  media_path: string | null;
};
export type Channel = { id: string; platform: "youtube" | "instagram" | "tiktok"; name: string; is_authorized: boolean };
export type ScheduledPost = { id: string; video_id: string; channel_id: string; platform: Channel["platform"]; scheduled_at: string | null; timezone: string; status: "draft" | "scheduled" | "cancelled"; metadata: Record<string, unknown> };
async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { ...init, cache: "no-store" });
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? "Request failed");
  return (await response.json()) as T;
}
export async function getVideos(
  offset: number,
  signal: AbortSignal,
): Promise<Video[]> {
  const response = await fetch(
    `${apiUrl}/api/videos?limit=20&offset=${offset}`,
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
        ["draft", "scheduled", "published", "failed"].includes(item.status) &&
        (item.published_at === null ||
          (typeof item.published_at === "string" &&
            !Number.isNaN(Date.parse(item.published_at)))),
    )
  )
    throw new Error("Invalid content response");
  return data as Video[];
}
export function setupLocal(signal?: AbortSignal) {
  return json<Channel[]>(`${apiUrl}/api/local/setup`, { method: "POST", signal });
}
export function getQueue(signal?: AbortSignal) {
  return json<ScheduledPost[]>(`${apiUrl}/api/scheduled-posts`, { signal });
}
export function schedulePost(payload: Record<string, unknown>) {
  return json<ScheduledPost>(`${apiUrl}/api/scheduled-posts`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
}
export function updatePost(id: string, payload: Record<string, unknown>) {
  return json<ScheduledPost>(`${apiUrl}/api/scheduled-posts/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
}
export function uploadVideo(channelId: string, file: File) {
  const form = new FormData();
  form.set("channel_id", channelId);
  form.set("file", file);
  return json<Video>(`${apiUrl}/api/videos/upload`, { method: "POST", body: form });
}
