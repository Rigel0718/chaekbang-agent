// 관리자 화면 조립. 열 때 관리자 토큰으로 역할을 확인하고, 아니면 로그인 화면으로 간다.
import { api, goLogin, requireRole } from "../shared/api.js";
import { createApprovals } from "./approvals.js";
import { createChat } from "./chat.js";
import { createImports } from "./imports.js";
import { createOverdue } from "./overdue.js";
import { createRequests } from "./requests.js";

const me = await requireRole("admin");

const $ = (id) => document.getElementById(id);
const DEFAULT_TAB = "chat";

$("org").textContent = me.library_name;
$("login-id").textContent = me.login_id;

// 쓰는 중에 401이면 토큰을 지우고 로그인 화면으로 간다
function onUnauthorized() {
  goLogin();
}

// 연체 안내는 자체 대출 기관만, 장서 가져오기는 외부 대출 기관만 쓴다. 운영 방식은 여기서 한 번 읽는다.
// 기관 정보를 못 읽으면 둘 다 숨긴 채 둔다(서버 409가 방어선).
let overdueEnabled = false;
let importsEnabled = false;
async function loadLibrary() {
  try {
    const mode = (await api.library()).loan_mode;
    if (mode === "internal") {
      overdueEnabled = true;
      $("tab-overdue").hidden = false;
      $("group-templates").hidden = false;
    } else if (mode === "external") {
      importsEnabled = true;
      $("tab-imports").hidden = false;
    }
  } catch (error) {
    if (error.kind === "unauthorized") onUnauthorized();
  }
}

async function refreshPendingCount() {
  const kinds = overdueEnabled ? ["curations", "templates", "purchases"] : ["curations", "purchases"];
  try {
    const lists = await Promise.all(kinds.map((kind) => api.approvalPending(kind)));
    const count = lists.reduce((sum, list) => sum + list.length, 0);
    const badge = $("pending-count");
    badge.textContent = String(count);
    badge.hidden = count === 0;
  } catch (error) {
    if (error.kind === "unauthorized") onUnauthorized();
  }
}

await loadLibrary();

const tabs = {
  chat: createChat({
    thread: $("chat-thread"),
    form: $("chat-form"),
    input: $("chat-input"),
    send: $("chat-send"),
    newChat: $("chat-new"),
    onDone: refreshPendingCount,
    onUnauthorized,
  }),
  approvals: createApprovals({
    root: $("panel-approvals"),
    enabledKinds: () => (overdueEnabled ? ["curations", "templates", "purchases"] : ["curations", "purchases"]),
    pendingButton: $("view-pending"),
    allButton: $("view-all"),
    onChanged: refreshPendingCount,
    onUnauthorized,
  }),
  requests: createRequests({
    list: $("list-requests"),
    more: $("more-requests"),
    onUnauthorized,
  }),
  overdue: createOverdue({
    summary: $("overdue-summary"),
    list: $("list-overdue"),
    onUnauthorized,
  }),
  imports: createImports({
    form: $("import-form"),
    file: $("import-file"),
    submit: $("import-submit"),
    columns: $("import-columns"),
    error: $("import-error"),
    summary: $("import-summary"),
    list: $("list-imports"),
    onUnauthorized,
  }),
};

let current = null;

function tabName() {
  const name = location.hash.slice(1);
  if (!(name in tabs)) return DEFAULT_TAB;
  if (name === "overdue" && !overdueEnabled) return DEFAULT_TAB;
  if (name === "imports" && !importsEnabled) return DEFAULT_TAB;
  return name;
}

function showTab() {
  const name = tabName();
  if (name === current) return;
  current = name;
  for (const button of document.querySelectorAll(".tab")) {
    button.setAttribute("aria-selected", String(button.dataset.tab === name));
  }
  for (const panel of document.querySelectorAll(".panel")) panel.hidden = panel.dataset.panel !== name;
  tabs[name].show();
}

for (const button of document.querySelectorAll(".tab")) {
  button.addEventListener("click", () => {
    location.hash = button.dataset.tab;
  });
}
window.addEventListener("hashchange", showTab);

$("logout").addEventListener("click", async () => {
  try {
    await api.logout();
  } catch {
    // 이미 끊긴 토큰이어도 이 화면의 토큰은 지운다
  }
  goLogin();
});

// 뒤로 가기 캐시에서 돌아오면 회원 값이 든 화면을 비우고 토큰을 다시 확인한다
window.addEventListener("pageshow", async (event) => {
  if (!event.persisted) return;
  document.body.hidden = true;
  await requireRole("admin");
  document.body.hidden = false;
  current = null;
  showTab();
});

showTab();
refreshPendingCount();
