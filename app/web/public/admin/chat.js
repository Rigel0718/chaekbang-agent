// 운영 대화: 답 문장과 그 아래 표·[초안 보기]를 글자로 보인다. 사건은 session, status, result, answer,
// done이다. result는 모아 두었다가 answer가 온 뒤에만 그리고, answer가 없으면 버린다.
import { api, GENERIC_ERROR } from "../shared/api.js";
import { button, el } from "../shared/dom.js";
import { readEvents } from "../shared/sse.js";

const WAITING = "살펴보는 중…";
const UNSUPPORTED_NOTE = "지금은 못 하는 분석이에요.";
const SESSION_ENDED = "대화가 끝나 새 대화로 시작해요. 보낸 문장은 입력칸에 되돌려 놨어요.";
// 초안 결과의 종류 → 승인 목록의 묶음
const DRAFT_KINDS = { curation: "curations", template: "templates", purchase: "purchases" };

function isNumberColumn(rows, index) {
  return rows.some((row) => typeof row[index] === "number") && rows.every((row) => row[index] === null || typeof row[index] === "number");
}

// 막대 길이는 그 열의 가장 큰 값을 100%로 맞춘다
function barCell(value, max) {
  const bar = el("span", { className: "bar" });
  bar.style.width = `${(value / max) * 100}%`;
  const track = el("span", { className: "bar-track", children: [bar] });
  return el("td", { className: "num", children: [el("div", { className: "bar-cell", children: [track, el("span", { text: String(value) })] })] });
}

function tableBlock(result) {
  const { columns, rows } = result;
  const numeric = columns.map((_, i) => isNumberColumn(rows, i));
  const barAt = result.bar_column;
  const max = barAt === null ? 0 : Math.max(0, ...rows.map((row) => row[barAt] ?? 0));
  const head = el("tr", { children: columns.map((name, i) => el("th", { className: numeric[i] ? "num" : "", text: name })) });
  const body = rows.map((row) =>
    el("tr", {
      children: row.map((value, i) => {
        if (i === barAt && max > 0 && typeof value === "number") return barCell(value, max);
        return el("td", { className: numeric[i] ? "num" : "", text: value === null ? "-" : String(value) });
      }),
    }),
  );
  const table = el("table", { children: [el("thead", { children: [head] }), el("tbody", { children: body })] });
  const block = el("div", { className: "result", children: [el("p", { className: "result-title", text: result.title })] });
  if (result.caption) block.append(el("p", { className: "result-caption", text: result.caption }));
  block.append(el("div", { className: "result-table", children: [table] }));
  if (result.truncated) block.append(el("p", { className: "result-more", text: `전체 ${result.total}건 중 ${rows.length}건` }));
  return block;
}

// ui: { thread, form, input, send, newChat, onDone(), onOpenDraft(kind, id), onUnauthorized() }
export function createChat(ui) {
  let sessionId = null;
  let busy = false;
  let controller = null;

  function add(node) {
    ui.thread.append(node);
    node.scrollIntoView({ block: "nearest" });
  }

  // 표는 받은 순서대로, 그다음 [초안 보기]. 모르는 kind는 건너뛴다
  function showResults(reply, results) {
    for (const result of results) {
      if (result.kind === "table") reply.append(tableBlock(result));
    }
    const drafts = results.filter((result) => result.kind === "draft" && result.draft in DRAFT_KINDS);
    if (drafts.length === 0) return;
    const buttons = drafts.map((result) => button("초안 보기", () => ui.onOpenDraft(DRAFT_KINDS[result.draft], result.id)));
    reply.append(el("div", { className: "draft-actions", children: buttons }));
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
    const results = [];
    try {
      const response = await api.adminOpenMessages(
        sessionId ? { session_id: sessionId, message: text } : { message: text },
        controller.signal,
      );
      for await (const event of readEvents(response)) {
        if (event.name === "session") sessionId = event.data.session_id;
        else if (event.name === "status") status.textContent = event.data.text;
        else if (event.name === "result") results.push(event.data);
        else if (event.name === "answer") {
          answered = true;
          status.remove();
          reply.append(el("div", { className: "bubble bubble-admin", text: event.data.message }));
          if (event.data.unsupported) reply.append(el("p", { className: "reply-note", text: UNSUPPORTED_NOTE }));
          showResults(reply, results);
          reply.scrollIntoView({ block: "nearest" });
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
