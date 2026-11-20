// 이용자 화면 조립. 로그인 화면은 없다. 개발용 토큰은 주소의 #token=으로 한 번 넣는다(README).
import { api, clearToken, getToken, setToken } from "../shared/api.js";
import { createBasket } from "./basket.js";
import { createChat } from "./chat.js";
import { IDLE_MS, createIdleTimer } from "./idle.js";
import { createSuggest } from "./suggest.js";

const TOKEN_NOTICE =
  "토큰이 없거나 만료됐어요. 개발 중이라면 Swagger에서 키오스크 계정으로 로그인한 뒤, 주소 끝에 #token=토큰 을 붙여 열어 주세요.";
const SESSION_ENDED_NOTICE = "대화가 끝나서 새로 시작해요.";

const $ = (id) => document.getElementById(id);
const input = $("input");
const send = $("send");
const notice = $("notice");
const due = $("due");

function takeTokenFromHash() {
  const match = location.hash.match(/^#token=(.+)$/);
  if (!match) return;
  setToken(decodeURIComponent(match[1]));
  // 토큰이 주소창과 기록에 남지 않게 지운다
  history.replaceState(null, "", location.pathname + location.search);
}

function showNotice(text) {
  notice.textContent = text;
  notice.hidden = false;
}

function hideNotice() {
  notice.hidden = true;
}

function onUnauthorized() {
  clearToken();
  showNotice(TOKEN_NOTICE);
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
    renderDue(await api.guide());
  } catch (error) {
    due.hidden = true;
    if (error.kind === "unauthorized") onUnauthorized();
  }
}

const basket = createBasket({
  list: $("basket-list"),
  empty: $("basket-empty"),
  count: $("basket-count"),
  panel: $("basket"),
  toggle: $("basket-toggle"),
});

const idleSeconds = Number(new URLSearchParams(location.search).get("idle_seconds"));
const idle = createIdleTimer({
  ms: idleSeconds > 0 ? idleSeconds * 1000 : IDLE_MS,
  onIdle: () => resetAll(),
});

const chat = createChat({
  thread: $("thread"),
  emptyState: $("empty"),
  basket,
  setBusy(busy) {
    send.disabled = busy;
    if (busy) idle.pause();
    else idle.resume();
  },
  onUnauthorized,
  onSessionLost() {
    resetAll();
    showNotice(SESSION_ENDED_NOTICE);
  },
});

const suggest = createSuggest({
  input,
  panel: $("suggest"),
  onPick: (hit) => (chat.busy ? false : chat.sendSelected(hit.library_book_id, hit.title)),
  onSearchAll: (query) => chat.showSearch(query),
  onSubmit: submit,
  onUnauthorized,
});

function submit() {
  const text = input.value.trim();
  if (!text || chat.busy) return;
  suggest.close();
  input.value = "";
  chat.sendText(text);
}

// 새 대화, 무입력 4분 30초, 세션 404가 모두 이 함수로 화면을 비운다
function resetAll() {
  chat.reset();
  basket.clear();
  suggest.close();
  input.value = "";
  hideNotice();
  loadGuide();
  idle.touch();
}

$("composer").addEventListener("submit", (event) => {
  event.preventDefault();
  submit();
});
$("new-chat").addEventListener("click", resetAll);

takeTokenFromHash();
if (getToken()) loadGuide();
else onUnauthorized();
