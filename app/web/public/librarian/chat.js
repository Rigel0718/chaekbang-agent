// 대화 한 턴의 흐름: 찾은 책 카드(found) → 진행 문구(status) → 답과 추천 카드(answer) → done.
// 검색 카드 줄은 서버 세션에 남지 않는다. 사서의 문맥에 넣으려면 카드의 [이 책 물어보기]를 쓴다.
import { api } from "../shared/api.js";
import { createCard } from "../shared/card.js";
import { readEvents } from "../shared/sse.js";

const GENERIC_ERROR = "잠시 뒤에 다시 시도해 주세요.";
const WAITING = "사서가 살펴보는 중…";
const BOOK_REQUEST_NOTE = "찾는 책이 없다면 희망도서를 신청해 주세요.";
const BOOK_REQUEST_BUTTON = "희망도서 신청";

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
        block.append(element("p", "results-note", "찾는 책이 없어요. 사서에게 물어보세요."));
      } else {
        block.append(cards(books, "summary").strip);
      }
    } catch (error) {
      failed(error, block);
    }
    return true;
  }

  function reset() {
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
    reset,
    get busy() {
      return busy;
    },
  };
}
