// 대출·반납·희망도서 입력칸. 칸 하나에 모드 셋(빌리기, 반납하기, 희망도서)이다.
// LLM을 거치지 않고 기존 REST로 바로 보낸다. 회원번호는 화면 메모리의 입력칸에만 있고,
// 칸을 닫거나 화면을 비우면 모두 지운다(공용 PC). 서버가 준 문구는 글자로만 넣는다.
import { api } from "../shared/api.js";

const MODES = {
  borrow: { group: "loan", submit: "빌리기", fields: ["accession", "member"] },
  return: { group: "loan", submit: "반납하기", fields: ["accession"] },
  request: { group: "request", submit: "신청하기", fields: ["title", "author", "isbn", "member"] },
};
const REQUIRED = {
  borrow: ["accession", "member"],
  return: ["accession"],
  request: ["title", "member"],
};
const MISSING = "빈칸을 채워 주세요.";
const INVALID = "입력한 값을 확인해 주세요.";
const GENERIC_ERROR = "잠시 뒤에 다시 시도해 주세요.";
const REQUESTED = "신청했어요. 도서관에서 확인할게요.";

// "2026-12-06" → "12월 6일"
function dayLabel(iso) {
  const match = /^\d{4}-(\d{2})-(\d{2})$/.exec(iso || "");
  return match ? `${Number(match[1])}월 ${Number(match[2])}일` : "";
}

// ui: { panel, loanButton, requestButton, tabs, tabButtons, closeButton, form, inputs, labels,
//       submit, result, setBusy(bool), onUnauthorized() }
// inputs: { accession, member, title, author, isbn } 입력 요소, labels: 같은 이름의 라벨 요소
export function createActions(ui) {
  let mode = null;
  let busy = false;

  function showResult(text, failed = false) {
    ui.result.textContent = text;
    ui.result.classList.toggle("failed", failed);
  }

  function clearInputs(names = Object.keys(ui.inputs)) {
    for (const name of names) ui.inputs[name].value = "";
  }

  function render() {
    const current = MODES[mode];
    ui.tabs.hidden = current.group !== "loan";
    for (const button of ui.tabButtons) {
      button.classList.toggle("active", button.dataset.mode === mode);
    }
    for (const name of Object.keys(ui.labels)) {
      ui.labels[name].hidden = !current.fields.includes(name);
    }
    ui.submit.textContent = current.submit;
  }

  function open(next) {
    mode = next;
    ui.panel.hidden = false;
    showResult("");
    render();
    const first = MODES[mode].fields[0];
    ui.inputs[first].focus();
  }

  // 닫을 때와 화면을 비울 때 모든 입력을 지운다(회원번호가 남지 않게)
  function close() {
    ui.panel.hidden = true;
    mode = null;
    clearInputs();
    showResult("");
  }

  function value(name) {
    return ui.inputs[name].value.trim();
  }

  async function send() {
    if (mode === "borrow") {
      const loan = await api.borrow(value("accession"), value("member"));
      clearInputs(["accession"]);
      const due = dayLabel(loan.due_on);
      return `『${loan.title}』을 빌렸어요.${due ? ` ${due}까지 반납해 주세요.` : ""}`;
    }
    if (mode === "return") {
      const loan = await api.returnBook(value("accession"));
      clearInputs(["accession"]);
      return `『${loan.title}』을 반납했어요.`;
    }
    await api.requestBook({
      memberNumber: value("member"),
      title: value("title"),
      author: value("author"),
      isbn: value("isbn"),
    });
    clearInputs();
    return REQUESTED;
  }

  function errorText(error) {
    // 404(없는 회원·등록번호)와 409(대출 중, 중복 신청, 데스크 안내)의 서버 문구를 그대로 보인다
    if ((error.kind === "not_found" || error.kind === "conflict") && error.detail) {
      return error.detail;
    }
    if (error.kind === "invalid") return INVALID;
    return GENERIC_ERROR;
  }

  async function submit() {
    if (busy || mode === null) return;
    if (REQUIRED[mode].some((name) => !value(name))) {
      showResult(MISSING, true);
      return;
    }
    busy = true;
    ui.submit.disabled = true;
    ui.setBusy(true);
    showResult("");
    try {
      showResult(await send());
      ui.inputs[MODES[mode].fields[0]].focus();
    } catch (error) {
      if (error.kind === "unauthorized") {
        close();
        ui.onUnauthorized();
      } else {
        showResult(errorText(error), true);
      }
    } finally {
      busy = false;
      ui.submit.disabled = false;
      ui.setBusy(false);
    }
  }

  ui.loanButton.addEventListener("click", () => open("borrow"));
  ui.requestButton.addEventListener("click", () => open("request"));
  ui.closeButton.addEventListener("click", close);
  for (const button of ui.tabButtons) {
    button.addEventListener("click", () => {
      mode = button.dataset.mode;
      showResult("");
      render();
    });
  }
  ui.form.addEventListener("submit", (event) => {
    event.preventDefault();
    submit();
  });

  return {
    // 자체 대출 기관만 [대출·반납]을 보인다. 서버의 409가 최종 방어선이다.
    setLoanAvailable(available) {
      ui.loanButton.hidden = !available;
      if (!available && mode !== null && MODES[mode].group === "loan") close();
    },
    openRequest: () => open("request"),
    reset: close,
  };
}
