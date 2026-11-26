// 장서 탭(자체 대출 기관): 서명·저자·등록번호로 사본 찾기, 상태 바꾸기, 반납, 책 등록.
// 변수 이름 holding은 사본(HoldingRead)에만 쓴다(테스트가 본다). 탭에 들어올 때마다 지난 찾기를 다시 읽는다.
import { api } from "../shared/api.js";
import { button, el } from "../shared/dom.js";

const PAGE = 20;
const GENERIC_ERROR = "잠시 뒤에 다시 시도해 주세요.";
const INVALID_INPUT = "입력한 값을 확인해 주세요.";
const NOT_FOUND = "찾은 사본이 없어요.";
const EMPTY = "등록한 사본이 없어요.";
const WITHDRAW_CONFIRM = "제적할까요? 추천과 소장 권수에서 빠져요.";
const RETURN_CONFIRM = "이 책을 반납 처리할까요?";

// 서버의 사본 상태. 대출 중은 대출·반납으로만 바뀌므로 고르기에 없다(테스트가 서버 값과 맞춘다).
const STATUS_OPTIONS = {
  available: "이용 가능",
  lost: "분실",
  damaged: "훼손",
  withdrawn: "제적",
};
const ON_LOAN = "on_loan";
const COLUMNS = ["등록번호", "서명", "저자", "청구기호", "상태"];

function message(error) {
  if (error.detail) return error.detail;
  return error.kind === "invalid" ? INVALID_INPUT : GENERIC_ERROR;
}

// ui: index.html의 장서 요소들과 onUnauthorized()
export function createCollection(ui) {
  let lastQuery = ""; // 마지막으로 찾은 글자(비면 처음 목록: 최근 등록순). 탭에 돌아오면 다시 읽는다.
  let offset = 0;
  let view = 0; // 새로 찾으면 늘어난다. 늦게 온 응답을 버린다.
  let body = null; // 결과 표의 tbody
  let owned = null; // 등록 칸이 확인했거나 만든 기관 도서. 사본 등록이 실패해도 남아 다시 누르면 사본만 보낸다.
  let entry = 0; // 등록 칸을 열고 닫으면 늘어난다.
  let busy = false;

  function fail(error, target = ui.error) {
    if (error.kind === "unauthorized") return ui.onUnauthorized();
    target.textContent = message(error);
  }

  function statusCell(holding) {
    if (holding.status === ON_LOAN) {
      const back = button("반납", () => returnHolding(holding, back));
      return el("td", { children: [el("span", { className: "loan-state", text: "대출 중" }), back] });
    }
    const select = el("select", { attrs: { "aria-label": `${holding.accession_number} 상태` } });
    for (const [value, label] of Object.entries(STATUS_OPTIONS)) {
      select.append(el("option", { text: label, attrs: { value } }));
    }
    select.value = holding.status;
    select.addEventListener("change", () => changeStatus(holding, select));
    return el("td", { children: [select] });
  }

  function holdingRow(holding) {
    const values = [holding.accession_number, holding.title, holding.author, holding.call_number];
    const cells = values.map((value) => el("td", { text: value || "-" }));
    return el("tr", { children: [...cells, statusCell(holding)] });
  }

  async function changeStatus(holding, select) {
    const next = select.value;
    if (next === "withdrawn" && !confirm(WITHDRAW_CONFIRM)) {
      select.value = holding.status;
      return;
    }
    ui.error.textContent = "";
    select.disabled = true;
    const row = select.closest("tr");
    try {
      const updated = await api.updateHolding(holding.id, next);
      row.replaceWith(holdingRow(updated));
    } catch (error) {
      select.value = holding.status;
      select.disabled = false;
      fail(error);
    }
  }

  async function returnHolding(holding, back) {
    if (!confirm(RETURN_CONFIRM)) return;
    ui.error.textContent = "";
    back.disabled = true;
    const row = back.closest("tr");
    try {
      await api.returnBook(holding.accession_number);
      row.replaceWith(holdingRow(await api.holdingGet(holding.id)));
    } catch (error) {
      back.disabled = false;
      fail(error);
    }
  }

  function showTable() {
    body = el("tbody", {});
    const head = el("thead", { children: [el("tr", { children: COLUMNS.map((name) => el("th", { text: name })) })] });
    ui.table.replaceChildren(el("table", { className: "grid", children: [head, body] }));
  }

  async function load() {
    const mine = view;
    ui.more.disabled = true;
    try {
      const page = await api.holdings(lastQuery, offset, PAGE);
      if (mine !== view) return;
      if (offset === 0) {
        if (!page.items.length) {
          ui.table.replaceChildren(el("p", { className: "empty-note", text: lastQuery ? NOT_FOUND : EMPTY }));
          ui.more.hidden = true;
          return;
        }
        showTable();
      }
      body.append(...page.items.map(holdingRow));
      offset += page.items.length;
      ui.more.hidden = offset >= page.total;
    } catch (error) {
      if (mine === view) fail(error);
    } finally {
      ui.more.disabled = false;
    }
  }

  function search(text) {
    view += 1;
    lastQuery = text;
    offset = 0;
    body = null;
    ui.error.textContent = "";
    ui.table.replaceChildren();
    ui.more.hidden = true;
    ui.all.hidden = !text; // [전체 보기]는 찾은 동안에만 있다
    load();
  }

  // ---- 책 등록 ----

  function setBook(value) {
    owned = value;
    const known = owned !== null;
    ui.found.hidden = !known;
    ui.found.textContent = known ? `등록된 책: ${owned.title}` : "";
    ui.titleField.hidden = known;
    ui.authorField.hidden = known;
  }

  function showAcquisition() {
    const purchased = ui.acquisition.value === "purchased";
    ui.priceField.hidden = !purchased;
    ui.donorField.hidden = purchased;
  }

  function resetEntry() {
    entry += 1;
    busy = false;
    ui.form.reset();
    ui.formError.textContent = "";
    ui.submit.disabled = false;
    setBook(null);
    showAcquisition();
  }

  async function findByIsbn(isbn) {
    const page = await api.libraryBooksByIsbn(isbn);
    return page.items[0] || null;
  }

  // ISBN을 적고 칸을 벗어나면 이미 있는 책인지 미리 보인다
  async function checkIsbn() {
    const mine = entry;
    const isbn = ui.isbn.value.trim();
    setBook(null);
    ui.formError.textContent = "";
    if (!isbn) return;
    try {
      const found = await findByIsbn(isbn);
      if (mine === entry && ui.isbn.value.trim() === isbn) setBook(found);
    } catch (error) {
      if (mine === entry) fail(error, ui.formError);
    }
  }

  async function createBook(isbn, title, author) {
    const payload = { title, author };
    if (isbn) payload.isbn = isbn;
    try {
      return await api.createLibraryBook(payload);
    } catch (error) {
      // 그사이 같은 ISBN이 생겼으면 그 책에 사본을 붙인다
      if (error.kind !== "conflict" || !isbn) throw error;
      const found = await findByIsbn(isbn);
      if (!found) throw error;
      return found;
    }
  }

  function holdingBody() {
    const acquisition = ui.acquisition.value;
    const payload = { accession_number: ui.accession.value.trim(), acquisition_type: acquisition };
    const call = ui.call.value.trim();
    if (call) payload.call_number = call;
    if (acquisition === "purchased") payload.purchase_price = Number(ui.price.value);
    else if (ui.donor.value.trim()) payload.donor = ui.donor.value.trim();
    return payload;
  }

  function missingCopyField() {
    if (!ui.accession.value.trim()) return "등록번호를 넣어 주세요.";
    if (ui.acquisition.value === "purchased" && !/^\d+$/.test(ui.price.value.trim())) return "구입가를 넣어 주세요.";
    return null;
  }

  async function register() {
    if (busy) return;
    const isbn = ui.isbn.value.trim();
    const title = ui.title.value.trim();
    const author = ui.author.value.trim();
    const missing = missingCopyField();
    ui.formError.textContent = missing || "";
    if (missing) return;
    const mine = entry;
    busy = true;
    ui.submit.disabled = true;
    try {
      if (!owned && isbn) {
        const found = await findByIsbn(isbn);
        if (mine !== entry) return;
        if (found) setBook(found);
      }
      if (!owned) {
        if (!title || !author) {
          ui.formError.textContent = "서명과 저자를 넣어 주세요.";
          return;
        }
        const created = await createBook(isbn, title, author);
        if (mine !== entry) return;
        setBook(created);
      }
      const payload = holdingBody();
      await api.createHolding({ library_book_id: owned.id, ...payload });
      if (mine !== entry) return;
      // 성공은 알리지 않고 칸을 닫은 뒤 그 등록번호로 찾는다
      ui.form.hidden = true;
      resetEntry();
      ui.q.value = payload.accession_number;
      search(payload.accession_number);
    } catch (error) {
      if (mine === entry) fail(error, ui.formError);
    } finally {
      if (mine === entry) {
        busy = false;
        ui.submit.disabled = false;
      }
    }
  }

  ui.searchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    search(ui.q.value.trim());
  });
  ui.all.addEventListener("click", () => {
    ui.q.value = "";
    search("");
  });
  ui.more.addEventListener("click", load);
  ui.open.addEventListener("click", () => {
    resetEntry();
    ui.form.hidden = false;
    ui.isbn.focus();
  });
  ui.close.addEventListener("click", () => {
    ui.form.hidden = true;
    resetEntry();
  });
  ui.isbn.addEventListener("change", checkIsbn);
  // ISBN을 고치면 확인해 둔 책은 버린다
  ui.isbn.addEventListener("input", () => {
    if (owned) setBook(null);
  });
  ui.acquisition.addEventListener("change", showAcquisition);
  ui.form.addEventListener("submit", (event) => {
    event.preventDefault();
    register();
  });

  return {
    show() {
      ui.form.hidden = true;
      resetEntry();
      search(lastQuery);
      ui.q.value = lastQuery;
    },
  };
}
