// 운영 대화: 답 문장만 글자로 보인다(표·차트는 24b). 사건은 session, status, answer, done이다.
import { api } from "../shared/api.js";
import { el } from "../shared/dom.js";
import { readEvents } from "../shared/sse.js";

const GENERIC_ERROR = "잠시 뒤에 다시 시도해 주세요.";
const WAITING = "운영 에이전트가 살펴보는 중…";
const UNSUPPORTED_NOTE = "지금은 못 하는 분석이에요(기록해 둡니다).";
const SESSION_ENDED = "대화가 끝나 새 대화로 시작해요. 보낸 문장은 입력칸에 되돌려 놨어요.";

// ui: { thread, form, input, send, newChat, onDone(), onUnauthorized() }
export function createChat(ui) {
  let sessionId = null;
  let busy = false;
  let controller = null;

  function add(node) {
    ui.thread.append(node);
    node.scrollIntoView({ block: "nearest" });
  }

  function setBusy(value) {
    busy = value;
    ui.input.disabled = value;
    ui.send.disabled = value;
  }

  async function send(text) {
    if (busy) return;
    setBusy(true);
    add(el("div", { className: "bubble bubble-user", text }));
    const reply = el("div", { className: "reply" });
    const status = el("p", { className: "reply-status", text: WAITING });
    reply.append(status);
    add(reply);
    controller = new AbortController();
    let answered = false;
    let finished = false;
    try {
      const response = await api.adminOpenMessages(
        sessionId ? { session_id: sessionId, message: text } : { message: text },
        controller.signal,
      );
      for await (const event of readEvents(response)) {
        if (event.name === "session") sessionId = event.data.session_id;
        else if (event.name === "status") status.textContent = event.data.text;
        else if (event.name === "answer") {
          answered = true;
          status.remove();
          reply.append(el("div", { className: "bubble bubble-admin", text: event.data.message }));
          if (event.data.unsupported) reply.append(el("p", { className: "reply-note", text: UNSUPPORTED_NOTE }));
        } else if (event.name === "done") finished = true;
      }
      status.remove();
      if (!answered || !finished) reply.append(el("p", { className: "reply-error", text: GENERIC_ERROR }));
    } catch (error) {
      status.remove();
      if (error.name === "AbortError") return;
      if (error.kind === "unauthorized") return ui.onUnauthorized();
      if (error.kind === "not_found") {
        // 세션이 끝났다: 세션을 버리고 보낸 문장을 입력칸에 되돌린다
        sessionId = null;
        ui.input.value = text;
        reply.append(el("p", { className: "reply-error", text: SESSION_ENDED }));
        return;
      }
      const shown = (error.kind === "conflict" || error.kind === "limit") && error.detail;
      reply.append(el("p", { className: "reply-error", text: shown || GENERIC_ERROR }));
    } finally {
      controller = null;
      setBusy(false);
      // 초안이 생겼을 수 있으니 승인 대기 수를 다시 센다
      ui.onDone();
    }
  }

  function reset() {
    if (controller) controller.abort();
    if (sessionId) api.adminEndSession(sessionId).catch(() => {});
    sessionId = null;
    ui.thread.replaceChildren();
    ui.input.value = "";
  }

  ui.form.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = ui.input.value.trim();
    if (!text || busy) return;
    ui.input.value = "";
    send(text);
  });
  ui.newChat.addEventListener("click", reset);

  return { reset, show() {} };
}
