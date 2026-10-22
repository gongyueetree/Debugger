export async function bridge(path: "status" | "prepare", body?: unknown) {
  const url = new URL(process.env.CH347_BRIDGE_URL || "http://127.0.0.1:8765");
  if (!["127.0.0.1", "localhost"].includes(url.hostname) || url.protocol !== "http:" || url.username || url.password) throw new Error("Only loopback bridge is allowed");
  const token = process.env.CH347_BRIDGE_TOKEN;
  if (!token) throw new Error("Set CH347_BRIDGE_TOKEN in the eve process environment");
  const response = await fetch(new URL(`/api/${path}`, url), {
    method: body ? "POST" : "GET",
    redirect: "error",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(10000),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Bridge request failed");
  return data;
}
