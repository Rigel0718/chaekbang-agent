// 서버 호출. 기관은 토큰으로 정해지므로 library_id를 보내지 않는다.
// 브라우저 저장소에는 화면마다 토큰 키 하나만 쓴다(README 규칙).
//   키오스크(이용자 화면): localStorage  PC를 다시 켜도 이어진다
//   관리자 화면:           sessionStorage 탭을 닫으면 사라지고 키오스크 토큰을 덮어쓰지 않는다
// 화면은 처음에 useScreen으로 어느 쪽인지 정한다. 저장소 접근은 이 파일의 아래 함수들에만 있다.

const KIOSK_TOKEN_KEY = "chaekbang.kiosk.token";
const ADMIN_TOKEN_KEY = "chaekbang.admin.token";
const LOGIN_PATH = "/ui/login/";

let screen = "kiosk";

export function useScreen(name) {
  if (name !== "kiosk" && name !== "admin") throw new Error(`모르는 화면: ${name}`);
  screen = name;
}

export function getToken() {
  try {
    if (screen === "admin") return sessionStorage.getItem(ADMIN_TOKEN_KEY);
    return localStorage.getItem(KIOSK_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token) {
  try {
    if (screen === "admin") sessionStorage.setItem(ADMIN_TOKEN_KEY, token);
    else localStorage.setItem(KIOSK_TOKEN_KEY, token);
  } catch {
    // 저장이 막혀 있으면 이번 화면에서만 쓴다
  }
}

export function clearToken() {
  try {
    if (screen === "admin") sessionStorage.removeItem(ADMIN_TOKEN_KEY);
    else localStorage.removeItem(KIOSK_TOKEN_KEY);
  } catch {
    // 저장이 막혀 있으면 지울 것도 없다
  }
}

// 이 화면의 토큰을 지우고 로그인 화면으로 간다. 이동하는 동안 화면이 그려지지 않게 끝나지 않는 약속을 돌려준다.
export function goLogin() {
  clearToken();
  location.replace(LOGIN_PATH);
  return new Promise(() => {});
}

// 오류 종류: unauthorized(401) member_required(403) not_found(404) conflict(409) limit(429) invalid(422) other
// 403은 이용자 화면에서 회원 세션이 없거나 끝났다는 뜻이다(직원 토큰 오류 401과 따로 다룬다).
const KINDS = {
  401: "unauthorized",
  403: "member_required",
  404: "not_found",
  409: "conflict",
  422: "invalid",
  429: "limit",
};

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail || `요청에 실패했어요 (${status})`);
    this.status = status;
    this.kind = KINDS[status] || "other";
    // 409·429의 서버 문구는 대화에서 그대로 보인다. 입력칸(actions.js)은 404 문구도 보인다.
    // 422는 형식 오류라 보이지 않는다.
    this.detail = typeof detail === "string" ? detail : null;
  }
}

// 회원 토큰은 대출·희망도서·담은 책·회원 로그아웃 요청에만 붙인다. 호출하는 쪽이 토큰을 넘기고 이 파일은 쥐지 않는다.
const MEMBER_HEADER = "X-Member-Token";

async function request(path, { method = "GET", body, signal, extraHeaders } = {}) {
  const headers = { ...extraHeaders };
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

const APPROVAL_BASES = {
  curations: "/curations",
  templates: "/overdue-notice-templates",
  purchases: "/purchase-requests",
};

export const api = {
  suggest: (q, signal) => query("/catalog/suggest", q, signal),
  search: (q, signal) => query("/catalog/search", q, signal),
  topic: (q, signal) => query("/catalog/topic", q, signal),
  similar: (id, signal) => request(`/catalog/books/${id}/similar`, { signal }).then((r) => r.json()),
  guide: (signal) => request("/library/guide", { signal }).then((r) => r.json()),
  // SSE 응답 그대로 돌려준다. 읽는 쪽은 sse.js다.
  openMessages: (body, signal) => request("/librarian/messages", { method: "POST", body, signal }),
  endSession: (id) => request(`/librarian/sessions/${id}`, { method: "DELETE" }),
  // 회원 로그인(휴대폰 번호)과 대출·반납·희망도서 입력칸(actions.js). 번호는 로그인 요청의 본문에만 들어가고,
  // 대출·희망도서는 회원 토큰 헤더로 회원을 정한다(대화 요청에는 회원 값이 없다).
  memberLogin: (phone) =>
    request("/auth/member-login", { method: "POST", body: { phone } }).then((r) => r.json()),
  memberLogout: (memberToken) =>
    request("/auth/member-logout", { method: "POST", extraHeaders: { [MEMBER_HEADER]: memberToken } }),
  borrow: (accessionNumber, memberToken) =>
    request("/loans", {
      method: "POST",
      body: { accession_number: accessionNumber },
      extraHeaders: { [MEMBER_HEADER]: memberToken },
    }).then((r) => r.json()),
  // 담은 책: 서버에 회원별로 3시간 보관한다. 담기·빼기·비우기는 본문 없이 204다.
  basket: (memberToken) =>
    request("/basket", { extraHeaders: { [MEMBER_HEADER]: memberToken } }).then((r) => r.json()),
  addBasket: (id, memberToken) =>
    request(`/basket/${id}`, { method: "PUT", extraHeaders: { [MEMBER_HEADER]: memberToken } }),
  removeBasket: (id, memberToken) =>
    request(`/basket/${id}`, { method: "DELETE", extraHeaders: { [MEMBER_HEADER]: memberToken } }),
  clearBasket: (memberToken) =>
    request("/basket", { method: "DELETE", extraHeaders: { [MEMBER_HEADER]: memberToken } }),
  returnBook: (accessionNumber) =>
    request("/loans/return", { method: "POST", body: { accession_number: accessionNumber } }).then(
      (r) => r.json(),
    ),
  requestBook: ({ title, author, isbn }, memberToken) =>
    request("/book-requests", {
      method: "POST",
      body: { title, author, isbn },
      extraHeaders: { [MEMBER_HEADER]: memberToken },
    }).then((r) => r.json()),
  // 로그인 화면과 역할 확인
  login: (loginId, password) =>
    request("/auth/login", { method: "POST", body: { login_id: loginId, password } }).then((r) =>
      r.json(),
    ),
  me: () => request("/auth/me").then((r) => r.json()),
  logout: () => request("/auth/logout", { method: "POST" }),
  // 관리자 화면. 기관 정보는 운영 방식을 읽는 데 쓴다.
  library: () => request("/library").then((r) => r.json()),
  adminOpenMessages: (body, signal) => request("/admin-agent/messages", { method: "POST", body, signal }),
  adminEndSession: (id) => request(`/admin-agent/sessions/${id}`, { method: "DELETE" }),
  // 승인 목록: kind는 curations | templates | purchases. 한 종류의 경로는 APPROVAL_BASES 한 곳에 있다.
  approvalPending: (kind) =>
    request(`${APPROVAL_BASES[kind]}?status=pending_approval`).then((r) => r.json()),
  approvalAll: (kind) => request(`${APPROVAL_BASES[kind]}`).then((r) => r.json()),
  approvalGet: (kind, id) => request(`${APPROVAL_BASES[kind]}/${id}`).then((r) => r.json()),
  approve: (kind, id) => request(`${APPROVAL_BASES[kind]}/${id}/approve`, { method: "POST" }).then((r) => r.json()),
  reject: (kind, id, reason) =>
    request(`${APPROVAL_BASES[kind]}/${id}/reject`, { method: "POST", body: { reason } }).then((r) =>
      r.json(),
    ),
  unpublish: (id) => request(`${APPROVAL_BASES.curations}/${id}/unpublish`, { method: "POST" }).then((r) => r.json()),
  // 희망도서와 오늘의 연체
  bookRequests: (offset, limit) =>
    request(`/book-requests?status=requested&limit=${limit}&offset=${offset}`).then((r) => r.json()),
  closeBookRequest: (id) =>
    request(`/book-requests/${id}`, { method: "PATCH", body: { status: "closed" } }).then((r) => r.json()),
  overdueToday: () => request("/overdue-notices/today").then((r) => r.json()),
};

// 열 때 이 화면의 토큰으로 역할을 확인한다. 토큰이 없거나 401이거나 역할이 다르면 이 화면의 토큰만 지우고
// 로그인 화면으로 보낸다(끝나지 않는 약속). 다른 오류는 그대로 던진다.
export async function requireRole(role) {
  useScreen(role);
  if (!getToken()) return goLogin();
  let me;
  try {
    me = await api.me();
  } catch (error) {
    if (error.kind === "unauthorized") return goLogin();
    throw error;
  }
  if (me.role !== role) return goLogin();
  return me;
}
