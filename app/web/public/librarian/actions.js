// 회원 로그인·대출·반납·희망도서 입력칸. 칸 하나에 모드 넷(로그인, 빌리기, 반납하기, 희망도서)이다.
// LLM을 거치지 않고 기존 REST로 바로 보낸다. 휴대폰 번호는 화면 메모리의 입력칸에만 있고, 로그인에 성공하거나
// 칸을 닫거나 화면을 비우면 지운다(공용 PC). 서버가 준 문구는 글자로만 넣는다.
// 빌리기와 희망도서는 회원 로그인이 필요하다: 로그인 전이면 로그인 모드로 열고, 성공하면 이어서 한다.
// (담기는 로그인 전에는 버튼이 없어 이어서 할 일이 없다.)
import { api } from "../shared/api.js";
import { attachPhoneInput } from "../shared/phone.js";

const MODES = {
  login: { group: "login", submit: "로그인", fields: ["phone"] },
  borrow: { group: "loan", submit: "빌리기", fields: ["accession"] },
  return: { group: "loan", submit: "반납하기", fields: ["accession"] },
  request: { group: "request", submit: "신청하기", fields: ["title", "author", "isbn"] },
};
const REQUIRED = {
  login: ["phone"],
  borrow: ["accession"],
  return: ["accession"],
  request: ["title"],
};
// 제출할 때 로그인이 필요한 모드. 빌리기는 등록번호를 먼저 적을 수 있게 칸을 열고(반납하기와 같은 칸),
// 희망도서는 칸을 열 때부터 로그인을 먼저 받는다.
const NEEDS_LOGIN = new Set(["borrow", "request"]);
const LOGIN_FIRST = new Set(["request"]);
const LOGIN_AGAIN = "로그인이 끝났어요. 다시 로그인해 주세요.";
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
//       submit, result, member, setBusy(bool), onUnauthorized(), onMemberLost() }
// inputs: { phone, accession, title, author, isbn } 입력 요소, labels: 같은 이름의 라벨 요소
// member: { loggedIn, token, login(phone) }(member.js), onMemberLost(): 회원 세션이 끝난 것을 화면에 알림
export function createActions(ui) {
  let mode = null;
  let busy = false;
  // 로그인에 성공한 뒤 이어서 할 일 하나: { reopen: 모드 }
  let pending = null;

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

  // 로그인을 먼저 받는 모드를 로그인 전에 열면 로그인 모드로 열고, 성공하면 그 모드로 돌아온다.
  // 이미 적은 입력은 지우지 않는다(등록번호, 서명).
  function open(next) {
    if (LOGIN_FIRST.has(next) && !ui.member.loggedIn) {
      askLogin({ reopen: next });
      return;
    }
    mode = next;
    pending = null;
    ui.panel.hidden = false;
    showResult("");
    render();
    ui.inputs[MODES[mode].fields[0]].focus();
  }

  function askLogin(after, message = "") {
    pending = after;
    mode = "login";
    ui.panel.hidden = false;
    showResult(message);
    render();
    ui.inputs.phone.focus();
  }

  // 닫을 때와 화면을 비울 때 모든 입력을 지운다(휴대폰 번호가 남지 않게)
  function close() {
    ui.panel.hidden = true;
    mode = null;
    pending = null;
    clearInputs();
    showResult("");
  }

  function value(name) {
    return ui.inputs[name].value.trim();
  }

  async function send() {
    if (mode === "login") {
      await ui.member.login(value("phone"));
      clearInputs(["phone"]);
      const next = pending;
      pending = null;
      if (next?.reopen) {
        open(next.reopen);
      } else {
        close();
      }
      return "";
    }
    if (mode === "borrow") {
      const loan = await api.borrow(value("accession"), ui.member.token);
      clearInputs(["accession"]);
      const due = dayLabel(loan.due_on);
      return `『${loan.title}』을 빌렸어요.${due ? ` ${due}까지 반납해 주세요.` : ""}`;
    }
    if (mode === "return") {
      const loan = await api.returnBook(value("accession"));
      clearInputs(["accession"]);
      return `『${loan.title}』을 반납했어요.`;
    }
    await api.requestBook(
      { title: value("title"), author: value("author"), isbn: value("isbn") },
      ui.member.token,
    );
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
    // 로그인 전에 빌리기·신청을 누르면 로그인부터 한다(이미 적은 값은 남는다)
    if (NEEDS_LOGIN.has(mode) && !ui.member.loggedIn) {
      askLogin({ reopen: mode });
      return;
    }
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
      if (mode !== null) ui.inputs[MODES[mode].fields[0]].focus();
    } catch (error) {
      if (error.kind === "unauthorized") {
        close();
        ui.onUnauthorized();
      } else if (error.kind === "member_required") {
        // 서버의 회원 세션이 끝났다. 키오스크는 그대로 두고 회원만 로그아웃해 로그인 칸으로 돌아간다.
        const again = mode;
        ui.onMemberLost();
        askLogin(NEEDS_LOGIN.has(again) ? { reopen: again } : null, LOGIN_AGAIN);
      } else {
        showResult(errorText(error), true);
      }
    } finally {
      busy = false;
      ui.submit.disabled = false;
      ui.setBusy(false);
    }
  }

  attachPhoneInput(ui.inputs.phone);
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
    // 로그인 칸을 연다(담은 책의 회원 세션 오류 뒤처럼 이어서 할 일이 없을 때).
    openLogin: () => askLogin(null),
    reset: close,
  };
}
