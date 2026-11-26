// 대화 한 턴의 흐름: 찾은 책 카드(found) → 진행 문구(status) → 답과 추천 카드(answer) → done.
// 검색 카드 줄은 서버 세션에 남지 않는다. 사서의 문맥에 넣으려면 카드의 [이 책 물어보기]를 쓴다.
import { api, GENERIC_ERROR } from "../shared/api.js";
import { createCard } from "../shared/card.js";
import { readEvents } from "../shared/sse.js";

const WAITING = "살펴보는 중…";
const BOOK_REQUEST_NOTE = "찾는 책이 없다면 희망도서를 신청해 주세요.";
const BOOK_REQUEST_BUTTON = "희망도서 신청";
const ASK_BUTTON = "AI 사서에게 묻기";
const TOP_TITLE = "이 책을 찾으시나요?";
const LOWER_WAITING = "관련된 책을 찾는 중…";
// 두 단계 결과의 위 단에 보이는 책 수(찾기 결과의 앞쪽). 나머지는 자동완성의 "모두 찾기"로 본다.
export const TWO_STEP_TOP_COUNT = 2;

// "'질의'와/과 관련된 책": 마지막 글자가 받침 있는 한글이면 `과`, 아니면 `와`
function relatedTitle(query) {
  const code = query.charCodeAt(query.length - 1);
  const batchim = code >= 0xac00 && code <= 0xd7a3 && (code - 0xac00) % 28 !== 0;
  return `'${query}'${batchim ? "과" : "와"} 관련된 책`;
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// ui: { thread, emptyState, basket, setBusy(bool), onUnauthorized(), onRequestBook(), onSessionLost() }
export function createChat(ui) {
  let sessionId = null;
  let busy = false;
  let controller = null;
  // 두 단계 검색: 서명·저자 찾기 요청 중이면 searching, 아래 단의 주제 검색 요청은 pending에 둔다
  let searching = false;
  let searchController = null;
  const pending = new Set();

  const cardOptions = {
    loadSimilar: (id) => api.similar(id),
    onAsk: (book) => sendSelected(book.library_book_id, book.title),
    basket: ui.basket,
  };

  function add(node) {
    ui.emptyState.hidden = true;
    ui.thread.append(node);
    node.scrollIntoView({ block: "nearest" });
  }

  function cards(books, kind) {
    const strip = element("div", "cards");
    const nodes = books.map((book) => createCard(book, kind, cardOptions));
    strip.append(...nodes);
    return { strip, nodes };
  }

  function showFound(reply, status, books) {
    if (books.length === 0) return;
    const { strip, nodes } = cards(books, "summary");
    reply.insertBefore(strip, status);
    // 찾은 책이 한 권이면 비슷한 책을 저절로 펼친다
    if (nodes.length === 1) nodes[0].expand();
    strip.scrollIntoView({ block: "nearest" });
  }

  function showAnswer(reply, status, answer) {
    status.remove();
    reply.append(element("div", "bubble bubble-librarian", answer.message));
    if (answer.recommendations.length > 0) {
      reply.append(cards(answer.recommendations, "recommend").strip);
    }
    if (answer.suggest_book_request) {
      reply.append(element("p", "reply-note", BOOK_REQUEST_NOTE));
      const button = element("button", "btn", BOOK_REQUEST_BUTTON);
      button.type = "button";
      button.addEventListener("click", () => ui.onRequestBook());
      reply.append(button);
    }
    reply.scrollIntoView({ block: "nearest" });
  }

  function failed(error, target) {
    if (error.name === "AbortError") return;
    if (error.kind === "unauthorized") return ui.onUnauthorized();
    if (error.kind === "not_found") return ui.onSessionLost();
    // 409(답하는 중, 턴 한도)와 429(일일 상한)는 서버 문구를 그대로 보인다
    const shown = (error.kind === "conflict" || error.kind === "limit") && error.detail;
    target.append(element("p", "reply-error", shown || GENERIC_ERROR));
  }

  async function runTurn(body, userText) {
    if (busy) return false;
    busy = true;
    ui.setBusy(true);
    add(element("div", "bubble bubble-user", userText));
    const reply = element("div", "reply");
    const status = element("p", "reply-status", WAITING);
    reply.append(status);
    add(reply);
    controller = new AbortController();
    let finished = false;
    let answered = false;
    try {
      const response = await api.openMessages(
        sessionId ? { ...body, session_id: sessionId } : body,
        controller.signal,
      );
      for await (const event of readEvents(response)) {
        if (event.name === "session") sessionId = event.data.session_id;
        else if (event.name === "found") showFound(reply, status, event.data.books);
        else if (event.name === "status") status.textContent = event.data.text;
        else if (event.name === "answer") {
          answered = true;
          showAnswer(reply, status, event.data);
        } else if (event.name === "done") finished = true;
      }
      status.remove();
      const needsAnswer = body.message !== undefined;
      if (!finished || (needsAnswer && !answered)) reply.append(element("p", "reply-error", GENERIC_ERROR));
    } catch (error) {
      status.remove();
      failed(error, reply);
    } finally {
      busy = false;
      controller = null;
      ui.setBusy(false);
    }
    return true;
  }

  function sendText(text) {
    return runTurn({ message: text }, text);
  }

  // 자동완성이나 카드에서 고른 책: LLM 없이 그 책의 카드만 나온다
  function sendSelected(id, title) {
    return runTurn({ selected_library_book_id: id }, `『${title}』`);
  }

  async function showSearch(query) {
    const block = element("section", "results");
    block.append(element("p", "results-title", `'${query}' 검색 결과`));
    add(block);
    try {
      const books = await api.search(query);
      if (books.length === 0) {
        block.append(element("p", "results-note", "찾은 책이 없어요."));
      } else {
        block.append(cards(books, "summary").strip);
      }
    } catch (error) {
      failed(error, block);
    }
    return true;
  }

  // 아래 단: 주제 검색 결과에서 위 단의 책을 뺀다. 비거나 실패하면 아래 단을 제목째 지운다.
  async function fillLower(lower, query, shown, signal) {
    let books;
    try {
      books = await api.topic(query, signal);
    } catch (error) {
      if (error.name === "AbortError") return;
      if (error.kind === "unauthorized") return ui.onUnauthorized();
      lower.remove();
      return;
    }
    const rest = books.filter((book) => !shown.has(book.library_book_id));
    if (rest.length === 0) {
      lower.remove();
      return;
    }
    lower.replaceChildren(element("p", "results-title", relatedTitle(query)), cards(rest, "summary").strip);
  }

  // 두 단계 결과: 위 단은 바로, 아래 단은 주제 검색이 오면 채운다. 서버 세션은 건드리지 않는다.
  function showTwoStep(query, found) {
    const top = found.slice(0, TWO_STEP_TOP_COUNT);
    const block = element("section", "results two-step");
    const lower = element("div", "two-step-lower");
    lower.append(element("p", "results-note", LOWER_WAITING));
    const ask = element("button", "btn two-step-ask", ASK_BUTTON);
    ask.type = "button";
    ask.addEventListener("click", () => {
      if (busy || ask.disabled) return;
      ask.disabled = true;
      sendText(query);
    });
    block.append(element("p", "results-title", TOP_TITLE), cards(top, "summary").strip, lower, ask);
    add(block);
    const mine = new AbortController();
    pending.add(mine);
    fillLower(lower, query, new Set(top.map((book) => book.library_book_id)), mine.signal).finally(() =>
      pending.delete(mine),
    );
  }

  // Enter: 서명·저자 찾기를 먼저 부른다. 1권 이상이면 두 단계 결과, 0권이거나 실패하면(401은 로그인 화면) 대화로 보낸다.
  async function submitText(text) {
    if (searching) return;
    searching = true;
    const mine = new AbortController();
    searchController = mine;
    let found = null;
    try {
      found = await api.search(text, mine.signal);
    } catch (error) {
      if (error.name === "AbortError") return;
      if (error.kind === "unauthorized") return ui.onUnauthorized();
    } finally {
      if (searchController === mine) {
        searchController = null;
        searching = false;
      }
    }
    if (mine.signal.aborted) return;
    if (!found || found.length === 0) return sendText(text);
    showTwoStep(text, found);
  }

  function reset() {
    if (searchController) searchController.abort();
    searchController = null;
    searching = false;
    for (const request of pending) request.abort();
    pending.clear();
    if (controller) controller.abort();
    if (sessionId) api.endSession(sessionId).catch(() => {});
    sessionId = null;
    ui.thread.replaceChildren();
    ui.emptyState.hidden = false;
  }

  return {
    sendText,
    sendSelected,
    showSearch,
    submitText,
    reset,
    get busy() {
      return busy;
    },
    get searching() {
      return searching;
    },
  };
}
