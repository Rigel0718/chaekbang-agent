// 장서 가져오기 탭(외부 대출 기관): 파일 올리기 → 미리 보기 요약과 확인할 행 → 적용(또는 삭제). 탭에 들어올 때마다
// 열어 둔 것을 지우고 지난 기록을 다시 읽는다. 파일 내용은 화면이 읽지 않고 서버로 보내기만 한다.
// 변수 이름 record는 가져오기 기록(HoldingImportRead), row는 그 행(HoldingImportRow)에만 쓴다(테스트가 본다).
import { api, GENERIC_ERROR } from "../shared/api.js";
import { button, el, when } from "../shared/dom.js";

const RECORD_LIMIT = 20;
const PAGE = 20;
const APPLY_CONFIRM = "이 파일대로 책 목록을 바꿀까요?";
const DELETE_CONFIRM = "이 미리 보기를 삭제할까요? 책 목록은 바뀌지 않아요.";
const MASS_WITHDRAW_CONFIRM = "빠진 책을 모두 제적할까요? 파일에서 빠진 책이 절반 이상이에요.";
// 대량 제적 409를 다른 409와 가르는 낱말. 서버 문구에 이 낱말이 있다(테스트가 본다).
const MASS_WITHDRAW_MARK = "confirm_withdraw";

// 서버의 표준 열 이름(`app/library/importing/columns.py`의 LABELS)과 같다.
const FIELD_LABELS = {
  accession_number: "등록번호",
  title: "도서명",
  author: "저자",
  isbn: "ISBN",
  publisher: "출판사",
  published_date: "발행일",
  call_number: "청구기호",
  separate_mark: "별치기호",
  shelf_location: "자료실",
  status: "대출 상태",
  acquisition: "수입구분",
  price: "가격",
  donor: "기증처",
  kdc: "분류기호",
  addition_code: "부가기호",
};
const FLAG_LABELS = {
  invalid_isbn: "ISBN 형식 오류",
  unknown_status: "대출 상태를 모름",
  purchased_without_isbn: "매입인데 ISBN 없음",
  purchased_without_price: "매입인데 가격 없음",
};
const STATUS_LABELS = { preview: "미리 보기", applied: "적용함" };
const ROW_COLUMNS = ["행", "등록번호", "도서명", "저자", "사유"];

// ui: { form, file, submit, columns, error, summary, list, onUnauthorized() }
export function createImports(ui) {
  let latestId = null; // 가장 최근 기록. [적용]은 이 기록이 미리 보기일 때만 있다.
  let view = 0; // 화면을 비우거나 다른 기록을 열면 늘어난다. 늦게 온 응답을 버린다.
  let openId = null; // 요약을 연 기록. 목록에서 표시한다.
  let busy = false;

  function setBusy(value) {
    busy = value;
    ui.submit.disabled = value;
    ui.file.disabled = value;
    for (const node of ui.summary.querySelectorAll("[data-action]")) node.disabled = value;
    for (const node of ui.columns.querySelectorAll("button")) node.disabled = value;
  }

  function fail(error) {
    if (error.kind === "unauthorized") return ui.onUnauthorized();
    ui.error.textContent = error.detail || GENERIC_ERROR;
  }

  function clearColumns() {
    ui.columns.replaceChildren();
  }

  function markOpen() {
    for (const item of ui.list.querySelectorAll("[data-record]")) {
      const open = item.dataset.record === String(openId);
      item.classList.toggle("is-open", open);
      item.firstChild.setAttribute("aria-current", String(open));
    }
  }

  function clearView() {
    view += 1;
    openId = null;
    markOpen();
    ui.error.textContent = "";
    ui.summary.replaceChildren();
  }

  // 필수 열을 찾지 못했을 때: 못 찾은 열마다 파일의 머리글에서 고른다. mapping은 앞에서 고른 값을 이어 간다.
  function showColumnPicker(missing, headers, mapping) {
    const fields = missing.map((label) => Object.keys(FIELD_LABELS).find((field) => FIELD_LABELS[field] === label));
    const selects = [];
    clearColumns();
    for (const field of fields.filter(Boolean)) {
      const select = el("select", { attrs: { "aria-label": `${FIELD_LABELS[field]} 열` } });
      select.append(el("option", { text: "머리글 고르기", attrs: { value: "" } }));
      select.append(...headers.map((header) => el("option", { text: header, attrs: { value: header } })));
      selects.push([field, select]);
      ui.columns.append(el("label", { className: "column-pick", children: [el("span", { text: `${FIELD_LABELS[field]} 열` }), select] }));
    }
    ui.columns.append(
      button("다시 올리기", () => {
        if (selects.some(([, select]) => !select.value)) return;
        const chosen = { ...mapping };
        for (const [field, select] of selects) chosen[field] = select.value;
        upload(chosen);
      }, "primary"),
    );
  }

  async function upload(mapping) {
    const file = ui.file.files[0];
    if (!file || busy) return;
    clearView();
    const mine = view;
    setBusy(true);
    try {
      const record = await api.importUpload(file, mapping);
      if (mine !== view) return;
      // 같은 파일을 다시 올려 기록이 또 생기지 않게 파일 선택을 비운다(열 고르기가 필요한 422는 남긴다)
      ui.form.reset();
      clearColumns();
      await loadList();
      await openRecord(record.id);
    } catch (error) {
      if (mine !== view) return;
      const missing = error.body && error.body.missing;
      const headers = error.body && error.body.headers;
      // 머리글이 없으면(빈 파일 등) 고를 것이 없어 서버 문구만 보인다
      if (error.kind === "invalid" && missing && headers && headers.length) showColumnPicker(missing, headers, mapping);
      else clearColumns();
      fail(error);
    } finally {
      setBusy(false);
    }
  }

  function renderSummary(record) {
    const summary = record.summary;
    const box = el("div", { className: "row detail-box" });
    box.append(el("p", { className: "row-title", text: `${record.filename} · ${STATUS_LABELS[record.status] || record.status}` }));
    box.append(
      el("p", {
        text: `전체 ${summary.total}행: 새로 ${summary.create} · 바뀜 ${summary.update} · 그대로 ${summary.unchanged} · 건너뜀 ${summary.skipped}`,
      }),
    );
    const withdrawn =
      record.status === "applied"
        ? `파일에 없어 제적한 책 ${summary.missing_count}권`
        : `파일에서 빠진 책 ${summary.missing_count}권(적용하면 제적)`;
    box.append(el("p", { text: withdrawn }));
    const mapped = Object.entries(record.column_mapping)
      .map(([field, header]) => `${FIELD_LABELS[field] || field} ← ${header}`)
      .join(", ");
    box.append(el("p", { className: "row-meta", text: `인식한 열: ${mapped}` }));

    const filters = [];
    if (summary.skipped) filters.push([`건너뜀 ${summary.skipped}`, { outcome: "skipped" }]);
    for (const [flag, label] of Object.entries(FLAG_LABELS)) {
      if (summary.flags[flag]) filters.push([`${label} ${summary.flags[flag]}`, { flag }]);
    }
    const rows = el("div", {});
    if (filters.length) {
      const buttons = el("div", { className: "detail-actions" });
      buttons.append(el("span", { className: "row-meta", text: "확인할 행" }));
      for (const [label, filter] of filters) buttons.append(button(label, () => openRows(record.id, filter, rows)));
      box.append(buttons, rows);
    }
    if (record.status === "preview") {
      const actions = el("div", { className: "detail-actions" });
      if (record.status === "preview" && record.id === latestId) {
        actions.append(button("적용", () => applyRecord(record.id), "primary"));
      }
      actions.append(button("삭제", () => deleteRecord(record.id), "btn danger"));
      for (const node of actions.children) node.setAttribute("data-action", "");
      box.append(actions);
    }
    ui.summary.replaceChildren(box);
  }

  async function openRecord(id) {
    clearView();
    const mine = view;
    try {
      const record = await api.importGet(id);
      if (mine !== view) return;
      openId = record.id;
      markOpen();
      renderSummary(record);
    } catch (error) {
      if (mine === view) fail(error);
    }
  }

  function rowReason(row) {
    return row.skip_reason || row.flags.map((flag) => FLAG_LABELS[flag] || flag).join(", ");
  }

  function rowCells(row) {
    const values = [String(row.row_no), row.accession_number, row.title, row.author, rowReason(row)];
    return el("tr", {
      children: values.map((value, index) => el("td", { text: value || "-", attrs: { "data-label": ROW_COLUMNS[index] } })),
    });
  }

  // 확인할 행: 고른 종류의 행을 20줄씩 보인다
  async function openRows(id, filter, host) {
    const body = el("tbody", {});
    const head = el("thead", { children: [el("tr", { children: ROW_COLUMNS.map((name) => el("th", { text: name })) })] });
    const more = button("더 보기", () => load());
    more.hidden = true;
    host.replaceChildren(el("table", { className: "items", children: [head, body] }), more);
    const table = host.firstChild;
    let offset = 0;

    async function load() {
      more.disabled = true;
      try {
        const page = await api.importRows(id, filter, offset, PAGE);
        if (host.firstChild !== table) return; // 다른 종류를 눌렀다
        body.append(...page.items.map(rowCells));
        offset += page.items.length;
        more.hidden = offset >= page.total;
      } catch (error) {
        fail(error);
      } finally {
        more.disabled = false;
      }
    }

    await load();
  }

  async function applyRecord(id) {
    if (busy || !confirm(APPLY_CONFIRM)) return;
    ui.error.textContent = "";
    const mine = view;
    setBusy(true);
    try {
      try {
        await api.importApply(id);
      } catch (error) {
        const massWithdraw = error.kind === "conflict" && error.detail && error.detail.includes(MASS_WITHDRAW_MARK);
        if (!massWithdraw) throw error;
        if (!confirm(MASS_WITHDRAW_CONFIRM)) return;
        await api.importApplyConfirmed(id);
      }
      // 성공은 알리지 않고 목록과 요약을 다시 읽는다
      await loadList();
      if (mine === view) await openRecord(id);
    } catch (error) {
      if (mine === view) fail(error);
    } finally {
      setBusy(false);
    }
  }

  async function deleteRecord(id) {
    if (busy || !confirm(DELETE_CONFIRM)) return;
    ui.error.textContent = "";
    const mine = view;
    setBusy(true);
    try {
      await api.importDelete(id);
      if (mine === view) clearView();
      await loadList();
    } catch (error) {
      if (mine === view) fail(error);
    } finally {
      setBusy(false);
    }
  }

  function recordItem(record) {
    const summary = record.summary;
    const head = button("", () => openRecord(record.id), "row-head");
    head.append(
      el("span", {
        children: [
          el("span", { className: "row-title", text: record.filename }),
          el("br"),
          el("span", {
            className: "row-meta",
            text: `${when(record.created_at)} · 새로 ${summary.create} · 바뀜 ${summary.update} · 건너뜀 ${summary.skipped}`,
          }),
        ],
      }),
      el("span", { className: "status-badge", text: STATUS_LABELS[record.status] || record.status }),
    );
    const kind = record.status === "applied" ? "record-applied" : "record-preview";
    return el("li", { className: `row ${kind}`, attrs: { "data-record": String(record.id) }, children: [head] });
  }

  async function loadList() {
    try {
      const page = await api.importList(RECORD_LIMIT);
      latestId = page.items.length ? page.items[0].id : null;
      ui.list.replaceChildren(
        ...(page.items.length
          ? page.items.map(recordItem)
          : [el("li", { className: "empty-note", text: "아직 가져온 파일이 없어요." })]),
      );
      markOpen();
    } catch (error) {
      if (error.kind === "unauthorized") return ui.onUnauthorized();
      latestId = null;
      ui.list.replaceChildren(el("li", { className: "error-line", text: error.detail || GENERIC_ERROR }));
    }
  }

  ui.form.addEventListener("submit", (event) => {
    event.preventDefault();
    upload();
  });
  // 파일을 새로 고르면 앞 파일의 열 고르기를 지운다
  ui.file.addEventListener("change", () => {
    clearColumns();
    ui.error.textContent = "";
  });

  return {
    show() {
      clearView();
      clearColumns();
      ui.form.reset();
      latestId = null;
      ui.list.replaceChildren();
      loadList();
    },
  };
}
