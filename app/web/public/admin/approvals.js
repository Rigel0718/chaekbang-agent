// 승인 목록: 큐레이션, 연체 안내문 틀, 구매 요청서. 보고 승인·반려(큐레이션은 내리기)만 한다.
// 초안은 운영 대화로 만든다. 만들기·고치기 양식은 두지 않는다.
import { api } from "../shared/api.js";
import { button, el, when, won } from "../shared/dom.js";

const REJECT_LIMIT = 200; // 서버 반려 사유 상한과 같다
const GENERIC_ERROR = "잠시 뒤에 다시 시도해 주세요.";
const BUSY = "처리하는 중…";
const NOT_FOUND = "그 초안을 찾지 못했어요.";

const STATUS_LABELS = {
  draft: "초안",
  pending_approval: "승인 대기",
  approved: "승인",
  published: "게시 중",
  confirmed: "확정",
  archived: "내림",
};
const REASON_KINDS = { book_request: "희망도서", popular: "인기", field_gap: "부족 분야", manual: "직접 입력" };
const PRICE_SOURCES = { yes24_list_price: "YES24 정가" };

const APPROVE_CONFIRM = {
  curations: "승인하면 바로 게시돼 이용자가 볼 수 있어요. 승인할까요?",
  templates: "승인하면 연체 안내에 쓰는 틀이 돼요. 승인할까요?",
  purchases:
    "승인하면 정가를 다시 조회해 금액을 기록하고, 같은 ISBN의 희망도서를 닫아요. 확정본은 고칠 수 없어요. 승인할까요?",
};

function statusLabel(row) {
  if (row.status === "draft" && row.rejected_reason) return "반려됨";
  return STATUS_LABELS[row.status] || row.status;
}

// 종류마다 줄에 보일 것과 상세 그리기. 새 종류를 더하려면 여기에 한 항목을 더한다.
const KINDS = {
  curations: {
    line: (row) => ({ title: row.title, meta: `${row.books.length}권 · ${when(row.created_at)}` }),
    detail(row, box) {
      if (row.intro) box.append(el("p", { text: row.intro }));
      for (const book of row.books) {
        box.append(el("p", { text: `${book.title} · ${book.author} — ${book.reason}` }));
      }
    },
  },
  templates: {
    line: (row) => ({
      title: row.body.length > 40 ? `${row.body.slice(0, 40)}…` : row.body,
      meta: `${row.in_use ? "쓰는 중 · " : ""}${when(row.created_at)}`,
    }),
    detail(row, box) {
      box.append(el("p", { text: row.body }));
      if (row.in_use) box.append(el("p", { className: "muted", text: "지금 연체 안내에 쓰는 틀이에요." }));
    },
  },
  purchases: {
    line: (row) => ({
      title: row.title,
      meta: `${row.item_count}종${row.total_amount !== null ? ` · 총 ${won(row.total_amount)}` : ""} · ${when(row.created_at)}`,
    }),
    detail: purchaseDetail,
  },
};

function priceCell(item, estimate) {
  if (item.unit_price !== null) return won(item.unit_price);
  if (estimate && estimate.unavailable) return "조회 불가";
  return "가격 없음";
}

function purchaseDetail(row, box) {
  if (row.vendor_name) box.append(el("p", { text: `납품처: ${row.vendor_name}` }));
  if (row.note) box.append(el("p", { text: row.note }));
  const estimate = row.estimate;
  if (row.status === "confirmed") {
    box.append(
      el("p", {
        text: `확정 금액 ${won(row.total_amount)} · ${when(row.priced_at)} 조회 · ${PRICE_SOURCES[row.price_source] || row.price_source}`,
      }),
      el("p", { className: "muted", text: "확정본은 고칠 수 없어요." }),
    );
  } else if (estimate) {
    if (estimate.unavailable) {
      box.append(el("p", { className: "error-line", text: "지금 정가를 조회할 수 없어요. 잠시 뒤 다시 열어 보세요." }));
    } else {
      box.append(el("p", { text: `추정 총액 ${won(estimate.estimated_total)} · ${when(estimate.priced_at)} 조회(저장하지 않은 값)` }));
      if (estimate.missing_price_count > 0) {
        box.append(
          el("p", {
            className: "error-line",
            text: `가격 없는 항목이 ${estimate.missing_price_count}건 있으면 승인이 거절돼요.`,
          }),
        );
      }
    }
  }
  const head = el("tr", {
    children: ["ISBN", "서명", "저자", "권수", "근거", "단가", "금액"].map((name) => el("th", { text: name })),
  });
  const body = row.items.map((item) =>
    el("tr", {
      children: [
        cell("ISBN", item.isbn),
        cell("서명", item.title),
        cell("저자", item.author || "-"),
        cell("권수", String(item.quantity)),
        cell("근거", `${REASON_KINDS[item.reason_kind] || item.reason_kind}${item.reason ? ` · ${item.reason}` : ""}`),
        cell("단가", priceCell(item, estimate)),
        cell("금액", item.amount !== null ? won(item.amount) : "-"),
      ],
    }),
  );
  box.append(el("table", { className: "items", children: [el("thead", { children: [head] }), el("tbody", { children: body })] }));
}

function cell(label, text) {
  return el("td", { text, attrs: { "data-label": label } });
}

// ui: { root, note, enabledKinds(), pendingButton, allButton, onChanged(), onUnauthorized() }
export function createApprovals(ui) {
  let view = "pending";
  let open = null; // { kind, id }
  let target = null; // 운영 대화의 [초안 보기]로 다음에 펼칠 초안 { kind, id }

  function listOf(kind) {
    return ui.root.querySelector(`#list-${kind}`);
  }

  async function loadKind(kind) {
    const list = listOf(kind);
    try {
      const rows = await (view === "pending" ? api.approvalPending(kind) : api.approvalAll(kind));
      list.replaceChildren();
      if (rows.length === 0) {
        list.append(el("li", { className: "empty-note", text: view === "pending" ? "승인 대기 중인 것이 없어요." : "아직 없어요." }));
        return;
      }
      for (const row of rows) list.append(renderRow(kind, row));
    } catch (error) {
      if (error.kind === "unauthorized") return ui.onUnauthorized();
      list.replaceChildren(el("li", { className: "error-line", text: error.detail || GENERIC_ERROR }));
    }
  }

  function renderRow(kind, row) {
    const info = KINDS[kind].line(row);
    const item = el("li", { className: "row", attrs: { "data-id": String(row.id) } });
    const head = el("button", {
      className: "row-head",
      attrs: { type: "button", "aria-expanded": String(open && open.kind === kind && open.id === row.id) },
      children: [
        el("span", { children: [el("span", { className: "row-title", text: info.title }), el("br"), el("span", { className: "row-meta", text: info.meta })] }),
        el("span", { className: "status-badge", text: statusLabel(row) }),
      ],
    });
    head.addEventListener("click", () => {
      const same = open && open.kind === kind && open.id === row.id;
      open = same ? null : { kind, id: row.id };
      load();
    });
    item.append(head);
    if (open && open.kind === kind && open.id === row.id) item.append(detailBox(kind, row.id));
    return item;
  }

  // 상세는 늘 서버에서 새로 읽는다(구매 요청서의 추정 금액이 그때그때 다를 수 있다)
  function detailBox(kind, id) {
    const box = el("div", { className: "detail" });
    box.append(el("p", { className: "muted", text: "불러오는 중…" }));
    api
      .approvalGet(kind, id)
      .then((row) => fillDetail(kind, row, box))
      .catch((error) => {
        if (error.kind === "unauthorized") return ui.onUnauthorized();
        box.replaceChildren(el("p", { className: "error-line", text: error.detail || GENERIC_ERROR }));
      });
    return box;
  }

  function fillDetail(kind, row, box) {
    box.replaceChildren();
    if (row.status === "draft" && row.rejected_reason) {
      box.append(el("p", { className: "error-line", text: `반려 사유: ${row.rejected_reason}` }));
    }
    KINDS[kind].detail(row, box);
    const errorLine = el("p", { className: "error-line", attrs: { role: "alert" } });
    errorLine.hidden = true;
    const actions = el("div", { className: "detail-actions" });
    const buttons = [];

    async function run(call) {
      for (const b of buttons) b.disabled = true;
      errorLine.hidden = false;
      errorLine.className = "muted";
      errorLine.textContent = BUSY;
      try {
        await call();
      } catch (error) {
        if (error.kind === "unauthorized") return ui.onUnauthorized();
        for (const b of buttons) b.disabled = false;
        errorLine.className = "error-line";
        // 409·503은 서버 문구를 그대로 보이고 상태는 바뀌지 않은 채다
        const shown = error.detail || GENERIC_ERROR;
        errorLine.textContent = error.status === 503 ? `${shown} 잠시 뒤 다시 해 주세요.` : shown;
        return;
      }
      ui.onChanged();
      load();
    }

    if (row.status === "pending_approval") {
      const approve = button("승인", () => {
        if (confirm(APPROVE_CONFIRM[kind])) run(() => api.approve(kind, row.id));
      }, "primary");
      const rejectBox = rejectForm(kind, row, run, buttons);
      const reject = button("반려", () => {
        rejectBox.hidden = !rejectBox.hidden;
      }, "btn danger");
      buttons.push(approve, reject);
      actions.append(approve, reject);
      box.append(actions, rejectBox);
    } else if (kind === "curations" && row.status === "published") {
      const unpublish = button("게시 내리기", () => {
        if (confirm("게시를 내리면 이용자가 더 이상 볼 수 없어요. 내릴까요?")) run(() => api.unpublish(row.id));
      }, "btn danger");
      buttons.push(unpublish);
      actions.append(unpublish);
      box.append(actions);
    }
    box.append(errorLine);
  }

  function rejectForm(kind, row, run, buttons) {
    const form = el("div", { className: "reject-box" });
    form.hidden = true;
    const input = el("input", {
      attrs: { type: "text", maxlength: String(REJECT_LIMIT), placeholder: "반려 사유(필수)", "aria-label": "반려 사유", autocomplete: "off" },
    });
    const send = button("반려하기", () => {
      const reason = input.value.trim();
      if (!reason) {
        input.setAttribute("placeholder", "사유를 적어 주세요");
        input.focus();
        return;
      }
      run(() => api.reject(kind, row.id, reason));
    }, "btn danger");
    buttons.push(send);
    form.append(input, send);
    return form;
  }

  async function load() {
    const wanted = target;
    target = null;
    ui.note.textContent = "";
    ui.pendingButton.setAttribute("aria-pressed", String(view === "pending"));
    ui.allButton.setAttribute("aria-pressed", String(view === "all"));
    await Promise.all(ui.enabledKinds().map(loadKind));
    if (wanted) await showTarget(wanted);
  }

  // 승인 대기에 없으면 전체 보기로 한 번 더 찾고, 그래도 없으면 알린다
  async function showTarget(wanted) {
    const item = listOf(wanted.kind).querySelector(`[data-id="${wanted.id}"]`);
    if (item) return item.scrollIntoView({ block: "start" });
    if (view === "pending") {
      view = "all";
      target = wanted;
      return load();
    }
    open = null;
    ui.note.textContent = NOT_FOUND;
  }

  function reveal(kind, id) {
    view = "pending";
    open = { kind, id };
    target = { kind, id };
  }

  ui.pendingButton.addEventListener("click", () => {
    view = "pending";
    open = null;
    load();
  });
  ui.allButton.addEventListener("click", () => {
    view = "all";
    open = null;
    load();
  });

  return { show: load, reveal };
}
