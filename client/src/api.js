// client/src/api.js
// One fetch wrapper for every view. Always surfaces the server's own error
// message (the backend returns {"error": ...} bodies with proper status
// codes) -- no request in this client is allowed to fail silently.

export async function fetchJson(url, options) {
  let res;
  try {
    res = await fetch(url, options);
  } catch {
    throw new Error('Network error -- could not reach the server.');
  }

  let data = null;
  try {
    data = await res.json();
  } catch {
    // Non-JSON body (e.g. proxy error page); fall through to status check.
  }

  if (!res.ok) {
    throw new Error(data?.error || `Request failed (HTTP ${res.status}).`);
  }
  // Some endpoints signal failure with an error field even on 200.
  if (data && data.error) {
    throw new Error(data.error);
  }
  return data ?? {};
}

export function postJson(url, body, extra = {}) {
  return fetchJson(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    ...extra,
  });
}
