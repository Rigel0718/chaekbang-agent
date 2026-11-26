// 이용자 화면 조립. 열 때 키오스크 토큰으로 역할을 확인하고, 아니면 로그인 화면으로 간다(README).
import { api, goLogin, requireRole, GENERIC_ERROR } from "../shared/api.js";
import { createActions } from "./actions.js";
import { createBasket } from "./basket.js";
import { createChat } from "./chat.js";
import { createMember } from "./member.js";
import { CAP_MS, CAP_WARN_MS, IDLE_MS, IDLE_WARN_MS, createIdleTimer } from "./idle.js";
import { MAX_QUERY, createSuggest } from "./suggest.js";

const SESSION_ENDED_NOTICE = "대화가 끝나서 새로 시작해요.";
const BASKET_FULL = "담은 책은 10권까지예요.";

// 키오스크 계정이 아니면 로그인 화면으로 가고, 이 아래는 실행되지 않는다
await requireRole("kiosk");

const $ = (id) => document.getElementById(id);
const input = $("input");
const send = $("send");
const notice = $("notice");
const due = $("due");

function showNotice(text) {
  notice.textContent = text;
  notice.hidden = false;
}

function hideNotice() {
  notice.hidden = true;
}

// 쓰는 중에 401이면 토큰을 지우고 로그인 화면으로 간다
function onUnauthorized() {
  goLogin();
}

function renderDue(guide) {
  due.replaceChildren();
  due.classList.remove("closed");
  due.hidden = true;
  if (!guide.registered) return;
  const today = guide.today;
  if (today.status === "closed") {
    due.classList.add("closed");
    due.textContent = "오늘은 쉬는 날이에요";
    if (today.closed_reason) {
      const reason = document.createElement("small");
      reason.textContent = today.closed_reason;
      due.append(reason);
    }
    due.hidden = false;
  } else if (today.due_if_borrowed) {
    due.textContent = `오늘 빌리면 ${today.due_if_borrowed.label}까지 반납`;
    if (guide.due_is_estimate) {
      const estimate = document.createElement("small");
      estimate.textContent = "외부 대출 프로그램이 정하는 날짜라 예상이에요";
      due.append(estimate);
    }
    due.hidden = false;
  }
}

async function loadGuide() {
  try {
    const guide = await api.guide();
    renderDue(guide);
    // 자체 대출 기관만 [대출·반납]을 보인다. 안내를 못 읽으면 숨긴다.
    actions.setLoanAvailable(guide.loan_mode === "internal");
  } catch (error) {
    due.hidden = true;
    actions.setLoanAvailable(false);
    if (error.kind === "unauthorized") onUnauthorized();
  }
}

// 담은 책 요청이 실패했을 때: 401은 키오스크 로그인 화면, 403은 회원 로그아웃과 로그인 칸, 그 밖은 짧은 문구
function basketError(error) {
  if (error.kind === "unauthorized") return onUnauthorized();
  if (error.kind === "member_required") {
    memberLost();
    actions.openLogin();
    return undefined;
  }
  showNotice(error.kind === "conflict" ? BASKET_FULL : GENERIC_ERROR);
  return undefined;
}

const basket = createBasket({
  list: $("basket-list"),
  empty: $("basket-empty"),
  count: $("basket-count"),
  panel: $("basket"),
  toggle: $("basket-toggle"),
  clearAll: $("basket-clear"),
  token: () => member.token,
  onError: basketError,
});

// 회원 로그인. 위 띠에는 이름·번호 없이 "로그인 중"만 보인다. 담은 책과 카드의 [담기]는 로그인한 동안에만 보인다.
function renderMember(loggedIn) {
  document.querySelector(".app").classList.toggle("logged-in", loggedIn);
  $("open-login").hidden = loggedIn;
  $("member-status").hidden = !loggedIn;
  $("member-logout").hidden = !loggedIn;
  $("basket-toggle").hidden = !loggedIn;
  $("basket").hidden = !loggedIn;
}

const member = createMember({
  onChange(loggedIn) {
    renderMember(loggedIn);
    if (loggedIn) {
      hideNotice();
      idle.memberLoggedIn(); // 이용 상한은 로그인한 순간부터 센다
      basket.load(); // 서버에 보관한 담은 책을 불러온다
    }
  },
});

// 개발·확인용: ?idle_seconds=N, ?cap_seconds=N으로 두 시계를 짧게 줄인다(알림은 15초·30초 앞, 최소 1초).
function seconds(name) {
  const value = Number(new URLSearchParams(location.search).get(name));
  return value > 0 ? value : null;
}
const idleSeconds = seconds("idle_seconds");
const capSeconds = seconds("cap_seconds");

const warning = $("clear-warning");
const warningText = $("clear-warning-text");
const warningKeep = $("clear-warning-keep");
let warningTick = null;

// 알림 띠: 남은 초를 1초마다 글자로 바꾼다. 무입력 알림에만 [계속 쓰기]가 있다.
function showWarning(info) {
  clearInterval(warningTick);
  if (!info) {
    warning.hidden = true;
    return;
  }
  warningKeep.hidden = info.kind !== "idle";
  const render = () => {
    const left = Math.max(0, Math.ceil((info.deadline - Date.now()) / 1000));
    if (info.kind === "cap") warningText.textContent = `${left}초 뒤 이용 시간이 끝나 로그아웃해요.`;
    else warningText.textContent = info.member ? `${left}초 뒤 로그아웃해요.` : `${left}초 뒤 화면을 비워요.`;
  };
  render();
  warning.hidden = false;
  warningTick = setInterval(render, 1000);
}

const idle = createIdleTimer({
  idleMs: idleSeconds ? idleSeconds * 1000 : IDLE_MS,
  idleWarnMs: idleSeconds ? Math.max(1000, (idleSeconds - 15) * 1000) : IDLE_WARN_MS,
  capMs: capSeconds ? capSeconds * 1000 : CAP_MS,
  capWarnMs: capSeconds ? Math.max(1000, (capSeconds - 30) * 1000) : CAP_WARN_MS,
  onWarn: showWarning,
  // 로그인하지 않았으면 화면을 비우고 시작 화면을 보인다(답을 받는 중이면 요청을 끊는다).
  // 로그인 중이면 회원만 로그아웃한다(받는 중인 답은 끊지 않는다). 키오스크 토큰은 어느 쪽도 건드리지 않는다.
  onClear: ({ member: loggedIn }) => (loggedIn ? memberLogout() : resetAll({ toStart: true })),
});

const actions = createActions({
  panel: $("desk"),
  loanButton: $("open-loan"),
  requestButton: $("open-request"),
  tabs: $("desk-tabs"),
  tabButtons: document.querySelectorAll(".desk-tab"),
  closeButton: $("desk-close"),
  form: $("desk-form"),
  inputs: {
    phone: $("in-phone"),
    accession: $("in-accession"),
    title: $("in-title"),
    author: $("in-author"),
    isbn: $("in-isbn"),
  },
  labels: {
    phone: $("label-phone"),
    accession: $("label-accession"),
    title: $("label-title"),
    author: $("label-author"),
    isbn: $("label-isbn"),
  },
  submit: $("desk-submit"),
  result: $("desk-result"),
  member,
  setBusy(busy) {
    if (busy) idle.pause();
    else idle.resume();
  },
  onUnauthorized,
  onMemberLost: memberLost,
});

const chat = createChat({
  thread: $("thread"),
  emptyState: $("empty"),
  basket, // 카드의 [담기]는 로그인한 동안에만 보인다(CSS), 담기는 서버가 성공한 뒤 반영한다
  setBusy(busy) {
    send.disabled = busy;
    if (busy) idle.pause();
    else idle.resume();
  },
  onUnauthorized,
  onRequestBook: () => actions.openRequest(),
  onSessionLost() {
    resetChat();
    showNotice(SESSION_ENDED_NOTICE);
  },
});

const suggest = createSuggest({
  input,
  panel: $("suggest"),
  onPick: (hit) =>
    chat.busy || chat.searching ? false : chat.sendSelected(hit.library_book_id, hit.title),
  onSearchAll: (query) => (chat.searching ? false : chat.showSearch(query)),
  onSubmit: submit,
  onUnauthorized,
});

function submit() {
  const text = input.value.trim();
  if (!text || chat.busy || chat.searching) return;
  suggest.close();
  input.value = "";
  // 질의 상한을 넘는 글은 질문이라 찾기 없이 사서에게 보낸다. 아니면 서명·저자 찾기를 먼저 한다.
  if (text.length > MAX_QUERY) chat.sendText(text);
  else chat.submitText(text);
}

const start = $("start-screen");

function showStart() {
  start.hidden = false;
  start.focus();
}

// 시작 화면을 누르는 것도 입력이라 이용 상한 시계가 그때 시작한다
start.addEventListener("click", () => {
  start.hidden = true;
  input.focus();
});

// 화면을 비우는 길은 셋이다. 어느 쪽도 키오스크 토큰은 건드리지 않는다.
//   resetAll   로그인하지 않았을 때 무입력 1분, 회원 로그아웃: 전부 비우고(toStart) 시작 화면
//   resetChat  [새 대화], 서버 대화 세션 끝(404): 대화·자동완성·알림·입력만. 로그인과 담은 책은 남긴다
//   memberLogout  [로그아웃], 로그인 중 무입력 1분, 이용 상한 3분: 회원 로그아웃 뒤 resetAll로 바로 시작 화면. 대화·화면의 담은 책·입력칸도 비운다
//                 (서버에 보관한 담은 책은 지우지 않는다. 다시 로그인하면 나온다)
function resetAll({ toStart = false } = {}) {
  chat.reset();
  basket.clear();
  actions.reset();
  suggest.close();
  input.value = "";
  hideNotice();
  loadGuide();
  idle.reset();
  if (toStart) showStart();
}

function resetChat() {
  chat.reset();
  suggest.close();
  input.value = "";
  hideNotice();
  loadGuide();
  // 로그인하지 않았으면 지금처럼 시계도 처음으로. 로그인 중이면 이용 상한을 건드리지 않는다.
  if (!member.loggedIn) idle.reset();
}

function memberLogout() {
  idle.memberLoggedOut();
  const done = member.logout(); // 화면은 바로 로그아웃하고 서버 세션은 뒤에서 끊는다
  // 대화·담은 책·입력칸을 비우고 바로 시작 화면으로 간다(다음 사람이 앞사람의 화면을 보지 않게).
  // 문구도, 익명 무입력 시계를 한 번 더 세는 일도 없다. 받는 중인 답은 끊긴다.
  resetAll({ toStart: true });
  return done;
}

// 요청 중에 서버가 회원 세션이 끝났다고 답했다(403). 화면만 로그아웃하고, 로그인 칸은 actions가 연다.
function memberLost() {
  idle.memberLoggedOut();
  basket.clear();
  resetChat();
  member.logout({ remote: false });
}

$("composer").addEventListener("submit", (event) => {
  event.preventDefault();
  submit();
});
$("new-chat").addEventListener("click", () => resetChat());
$("open-login").addEventListener("click", () => actions.openLogin());
$("member-logout").addEventListener("click", () => memberLogout());

loadGuide();
start.focus();
