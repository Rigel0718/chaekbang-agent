// 휴관일 탭: 오늘부터 1년의 임시 휴관일 목록, 더하기, 지우기. 변수 이름 closure는 ClosureRead에만 쓴다.
import { api } from "../shared/api.js";
import { button, el } from "../shared/dom.js";

const DAYS = 365;
const GENERIC_ERROR = "잠시 뒤에 다시 시도해 주세요.";
const INVALID_INPUT = "입력한 값을 확인해 주세요.";
const DELETE_CONFIRM = "이 휴관일을 지울까요?";
const COLUMNS = ["날짜", "사유", ""];

// 브라우저의 오늘을 YYYY-MM-DD로. 관리자 PC가 기관에 있다고 본다(design 결정 4).
function isoDate(date) {
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function message(error) {
  if (error.detail) return error.detail;
  return error.kind === "invalid" ? INVALID_INPUT : GENERIC_ERROR;
}

// ui: { form, date, reason, submit, error, table, onUnauthorized() }
export function createClosures(ui) {
  let view = 0;

  function fail(error) {
    if (error.kind === "unauthorized") return ui.onUnauthorized();
    ui.error.textContent = message(error);
  }

  function closureRow(closure) {
    const remove = button("삭제", () => removeClosure(closure), "btn danger");
    return el("tr", {
      children: [
        el("td", { text: closure.closed_on }),
        el("td", { text: closure.reason || "" }),
        el("td", { children: [remove] }),
      ],
    });
  }

  async function load() {
    view += 1;
    const mine = view;
    const today = new Date();
    const from = isoDate(today);
    const to = isoDate(new Date(today.getFullYear(), today.getMonth(), today.getDate() + DAYS));
    try {
      const list = await api.closures(from, to);
      if (mine !== view) return;
      if (!list.length) {
        ui.table.replaceChildren(el("p", { className: "empty-note", text: "등록한 휴관일이 없어요." }));
        return;
      }
      const head = el("thead", { children: [el("tr", { children: COLUMNS.map((name) => el("th", { text: name })) })] });
      ui.table.replaceChildren(
        el("table", { className: "grid", children: [head, el("tbody", { children: list.map(closureRow) })] }),
      );
    } catch (error) {
      if (mine === view) fail(error);
    }
  }

  async function removeClosure(closure) {
    if (!confirm(DELETE_CONFIRM)) return;
    ui.error.textContent = "";
    try {
      await api.deleteClosure(closure.id);
      await load();
    } catch (error) {
      fail(error);
    }
  }

  async function add() {
    if (!ui.date.value) return;
    ui.error.textContent = "";
    ui.submit.disabled = true;
    try {
      const payload = { closed_on: ui.date.value };
      const reason = ui.reason.value.trim();
      if (reason) payload.reason = reason;
      await api.addClosure(payload);
      ui.form.reset();
      await load();
    } catch (error) {
      fail(error);
    } finally {
      ui.submit.disabled = false;
    }
  }

  ui.form.addEventListener("submit", (event) => {
    event.preventDefault();
    add();
  });

  return {
    show() {
      ui.form.reset();
      ui.error.textContent = "";
      ui.table.replaceChildren();
      load();
    },
  };
}
