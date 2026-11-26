// 회원 탭: 목록과 찾기, 등록, 이름·휴대폰 번호 고치기, 삭제. 회원 값은 화면 메모리에만 두고
// 탭에 들어올 때마다 비우고 서버에서 다시 읽는다.
import { api, GENERIC_ERROR } from "../shared/api.js";
import { button, el } from "../shared/dom.js";
import { attachPhoneInput, formatPhone } from "../shared/phone.js";

const PAGE = 20;
const INVALID_INPUT = "입력한 값을 확인해 주세요.";
const DELETE_CONFIRM = "이 회원을 삭제할까요?";
const NEED_PHONE = "휴대폰 번호를 넣어 주세요.";
const COLUMNS = ["회원번호", "이름", "휴대폰 번호", ""];

function message(error) {
  if (error.detail) return error.detail;
  return error.kind === "invalid" ? INVALID_INPUT : GENERIC_ERROR;
}

function textInput(value, label, type = "text") {
  const input = el("input", { attrs: { type, "aria-label": label, autocomplete: "off" } });
  input.value = value;
  return input;
}

// ui: index.html의 회원 요소들과 onUnauthorized()
export function createMembers(ui) {
  let query = "";
  let offset = 0;
  let view = 0; // 목록을 새로 읽으면 늘어난다. 늦게 온 응답을 버린다.
  let body = null;

  function fail(error, target = ui.error) {
    if (error.kind === "unauthorized") return ui.onUnauthorized();
    target.textContent = message(error);
  }

  function cells(values) {
    return values.map((value) => el("td", { text: value || "-" }));
  }

  function viewRow(member) {
    const row = el("tr", {});
    const actions = el("div", {
      className: "cell-actions",
      children: [
        button("수정", () => row.replaceWith(editRow(member))),
        button("삭제", () => remove(member), "btn danger"),
      ],
    });
    row.append(...cells([member.member_number, member.name, formatPhone(member.phone)]), el("td", { children: [actions] }));
    return row;
  }

  function editRow(member) {
    const name = textInput(member.name, "이름");
    const phone = textInput(formatPhone(member.phone), "휴대폰 번호", "tel");
    attachPhoneInput(phone);
    const row = el("tr", {});
    const save = button("저장", () => saveRow(member, name, phone, save), "primary");
    const actions = el("div", {
      className: "cell-actions",
      children: [save, button("취소", () => row.replaceWith(viewRow(member)))],
    });
    row.append(
      el("td", { text: member.member_number }),
      el("td", { children: [name] }),
      el("td", { children: [phone] }),
      el("td", { children: [actions] }),
    );
    return row;
  }

  async function saveRow(member, name, phone, save) {
    ui.error.textContent = "";
    if (!name.value.trim()) {
      ui.error.textContent = "이름을 넣어 주세요.";
      return;
    }
    // 번호는 지울 수 없다. 번호가 없던 기존 회원만 비운 채 이름을 고친다(번호를 보내지 않는다).
    if (member.phone && !phone.value.trim()) {
      ui.error.textContent = NEED_PHONE;
      return;
    }
    const payload = { name: name.value.trim() };
    if (phone.value.trim()) payload.phone = phone.value.trim();
    save.disabled = true;
    try {
      await api.updateMember(member.id, payload);
      reload();
    } catch (error) {
      save.disabled = false;
      fail(error);
    }
  }

  async function remove(member) {
    if (!confirm(DELETE_CONFIRM)) return;
    ui.error.textContent = "";
    try {
      await api.deleteMember(member.id);
      reload();
    } catch (error) {
      fail(error);
    }
  }

  async function load() {
    const mine = view;
    ui.more.disabled = true;
    try {
      const page = await api.members(query, offset, PAGE);
      if (mine !== view) return;
      if (offset === 0) {
        if (!page.items.length) {
          const text = query ? "찾은 회원이 없어요." : "등록한 회원이 없어요.";
          ui.table.replaceChildren(el("p", { className: "empty-note", text }));
          ui.more.hidden = true;
          return;
        }
        body = el("tbody", {});
        const head = el("thead", { children: [el("tr", { children: COLUMNS.map((name) => el("th", { text: name })) })] });
        ui.table.replaceChildren(el("table", { className: "grid", children: [head, body] }));
      }
      body.append(...page.items.map(viewRow));
      offset += page.items.length;
      ui.more.hidden = offset >= page.total;
    } catch (error) {
      if (mine === view) fail(error);
    } finally {
      ui.more.disabled = false;
    }
  }

  function reload() {
    view += 1;
    offset = 0;
    body = null;
    ui.table.replaceChildren();
    ui.more.hidden = true;
    load();
  }

  function resetForm(hidden) {
    ui.form.reset();
    ui.formError.textContent = "";
    ui.submit.disabled = false;
    ui.form.hidden = hidden;
  }

  async function create() {
    const memberNumber = ui.number.value.trim();
    const name = ui.name.value.trim();
    const phone = ui.phone.value.trim();
    if (!memberNumber || !name || !phone) {
      ui.formError.textContent = "회원번호, 이름, 휴대폰 번호를 넣어 주세요.";
      return;
    }
    ui.formError.textContent = "";
    ui.submit.disabled = true;
    try {
      const payload = { member_number: memberNumber, name, phone };
      await api.createMember(payload);
      resetForm(true);
      reload();
    } catch (error) {
      ui.submit.disabled = false;
      fail(error, ui.formError);
    }
  }

  ui.searchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    query = ui.q.value.trim();
    ui.error.textContent = "";
    reload();
  });
  attachPhoneInput(ui.phone);
  ui.more.addEventListener("click", load);
  ui.open.addEventListener("click", () => {
    resetForm(false);
    ui.number.focus();
  });
  ui.close.addEventListener("click", () => resetForm(true));
  ui.form.addEventListener("submit", (event) => {
    event.preventDefault();
    create();
  });

  return {
    show() {
      query = "";
      ui.q.value = "";
      ui.error.textContent = "";
      resetForm(true);
      ui.table.replaceChildren();
      reload();
    },
  };
}
