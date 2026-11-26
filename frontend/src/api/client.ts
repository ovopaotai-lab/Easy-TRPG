export async function apiFetch<T = any>(url: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers || {});
  if (!(init?.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const resp = await fetch(url, {
    credentials: "same-origin",
    ...init,
    headers,
  });
  if (!resp.ok) {
    let msg = `HTTP ${resp.status}`;
    try {
      const data = await resp.json();
      msg = data.detail || data.message || data.error || msg;
    } catch {
      const txt = await resp.text().catch(() => "");
      if (txt) msg = txt.slice(0, 200);
    }
    throw new Error(msg);
  }
  const ctype = (resp.headers.get("content-type") || "").toLowerCase();
  if (ctype.includes("application/json")) {
    return (await resp.json()) as T;
  }
  return (await resp.text()) as unknown as T;
}

export async function streamSSE(
  url: string,
  body: any,
  onEvent: (ev: Record<string, any>) => void,
  signal?: AbortSignal
): Promise<void> {
  const resp = await fetch(url, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!resp.ok) {
    let msg = `HTTP ${resp.status}`;
    try {
      const d = await resp.json();
      msg = d.detail || d.message || msg;
    } catch {}
    throw new Error(msg);
  }
  const reader = resp.body?.getReader();
  if (!reader) return;
  const decoder = new TextDecoder("utf-8");
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop() ?? "";
    for (const rawLine of lines) {
      const ln = rawLine.trim();
      if (!ln.startsWith("data:")) continue;
      const payload = ln.slice(5).trim();
      if (!payload) continue;
      try {
        onEvent(JSON.parse(payload));
      } catch {}
    }
  }
  buf += decoder.decode();
  const tail = buf.trim();
  if (tail.startsWith("data:")) {
    const payload = tail.slice(5).trim();
    if (payload) {
      try {
        onEvent(JSON.parse(payload));
      } catch {}
    }
  }
}

export async function streamNDJSON(
  url: string,
  body: any,
  onEvent: (ev: Record<string, any>) => void,
  signal?: AbortSignal
): Promise<void> {
  const resp = await fetch(url, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const reader = resp.body?.getReader();
  if (!reader) return;
  const decoder = new TextDecoder("utf-8");
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop() ?? "";
    for (const raw of lines) {
      const ln = raw.trim();
      if (!ln) continue;
      try {
        onEvent(JSON.parse(ln));
      } catch {}
    }
  }
}
