export type User = {
  id: number;
  username: string;
  email: string;
};

export type Stand = {
  id: number;
  name: string;
  status: "offline" | "idle" | "busy";
  online: boolean;
  last_seen_at: string | null;
};

export type Job = {
  id: string;
  status: string;
  status_display: string;
  original_filename: string;
  instruction_filename: string;
  target_agent: Stand | null;
  claimed_by: string | null;
  queue_position: number | null;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  deadline_at: string | null;
  execution_log: string;
  error_message: string;
  result_video_url: string | null;
};

export type Session = {
  id: string;
  token: string;
  agent: Stand;
  active: boolean;
  started_at: string;
  ends_at: string;
  remaining_seconds: number;
  pin_states: boolean[];
  pending_flash_name: string;
};

function getCsrf(): string {
  const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

async function ensureCsrf(): Promise<string> {
  let token = getCsrf();
  if (!token) {
    await fetch("/api/auth/csrf/", { credentials: "include" });
    token = getCsrf();
  }
  return token;
}

async function request<T>(url: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("X-CSRFToken")) {
    headers.set("X-CSRFToken", await ensureCsrf());
  }
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(url, { ...init, headers, credentials: "include" });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || `HTTP ${response.status}`);
  }
  return data as T;
}

export const api = {
  me: () => request<{ user: User | null; allow_anonymous: boolean }>("/api/auth/me/"),
  login: (username: string, password: string) =>
    request<{ user: User }>("/api/auth/login/", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  register: (username: string, password: string, email = "") =>
    request<{ user: User }>("/api/auth/register/", {
      method: "POST",
      body: JSON.stringify({ username, password, email }),
    }),
  logout: () => request<{ detail: string }>("/api/auth/logout/", { method: "POST" }),
  stands: () => request<{ stands: Stand[] }>("/api/stands/"),
  jobs: () => request<{ jobs: Job[] }>("/api/jobs/"),
  job: (id: string) => request<{ job: Job }>(`/api/jobs/${id}/`),
  createJob: (form: FormData) => request<{ job: Job }>("/api/jobs/", { method: "POST", body: form }),
  session: () => request<{ session: Session | null }>("/api/session/"),
  takeStand: (id: number, durationSeconds = 900) =>
    request<{ session: Session }>(`/api/stands/${id}/take/`, {
      method: "POST",
      body: JSON.stringify({ duration_seconds: durationSeconds }),
    }),
  releaseSession: () => request<{ session: Session }>("/api/session/release/", { method: "POST" }),
  setPin: (pin: number, state: "high" | "low") =>
    request<{ session: Session }>("/api/session/pin/", {
      method: "POST",
      body: JSON.stringify({ pin, state }),
    }),
  flashSession: (form: FormData) =>
    request<{ session: Session }>("/api/session/flash/", { method: "POST", body: form }),
};
