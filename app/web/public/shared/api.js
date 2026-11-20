// 서버 호출. 기관은 토큰으로 정해지므로 library_id를 보내지 않는다.
// 브라우저 저장소에는 토큰 키 하나만 쓴다(README 규칙).

const TOKEN_KEY = "chaekbang.token";

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token) {
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // 저장이 막혀 있으면 이번 화면에서만 쓴다
  }
}

export function clearToken() {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    // 저장이 막혀 있으면 지울 것도 없다
  }
}

// 오류 종류: unauthorized(401) not_found(404) conflict(409) limit(429) invalid(422) other
const KINDS = { 401: "unauthorized", 404: "not_found", 409: "conflict", 422: "invalid", 429: "limit" };

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail || `요청에 실패했어요 (${status})`);
    this.status = status;
    this.kind = KINDS[status] || "other";
    // 409·429의 서버 문구는 그대로 이용자에게 보인다. 422는 형식 오류라 보이지 않는다.
    this.detail = typeof detail === "string" ? detail : null;
  }
}

async function request(path, { method = "GET", body, signal } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(path, {
    method,
    headers,
    signal,
    cache: "no-store",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    let detail = null;
    try {
      detail = (await response.json()).detail;
    } catch {
      // 본문이 JSON이 아니면 상태 코드만 쓴다
    }
    throw new ApiError(response.status, detail);
  }
  return response;
}

function query(path, q, signal) {
  return request(`${path}?q=${encodeURIComponent(q)}`, { signal }).then((r) => r.json());
}

export const api = {
  suggest: (q, signal) => query("/catalog/suggest", q, signal),
  search: (q, signal) => query("/catalog/search", q, signal),
  similar: (id, signal) => request(`/catalog/books/${id}/similar`, { signal }).then((r) => r.json()),
  guide: (signal) => request("/library/guide", { signal }).then((r) => r.json()),
  // SSE 응답 그대로 돌려준다. 읽는 쪽은 sse.js다.
  openMessages: (body, signal) => request("/librarian/messages", { method: "POST", body, signal }),
  endSession: (id) => request(`/librarian/sessions/${id}`, { method: "DELETE" }),
};
