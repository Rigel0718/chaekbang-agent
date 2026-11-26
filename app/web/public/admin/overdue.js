// 오늘의 연체 탭: 승인한 틀로 채운 안내 문안 목록(회원 값 포함). 탭에 들어올 때마다 비우고 서버에서 다시 읽는다.
import { api } from "../shared/api.js";
import { el } from "../shared/dom.js";
import { formatPhone } from "../shared/phone.js";

const GENERIC_ERROR = "잠시 뒤에 다시 시도해 주세요.";
const NO_TEMPLATE_HELP = "운영 대화에서 연체 안내문 틀을 만들어 승인해 주세요.";

// ui: { summary, list, onUnauthorized() }
export function createOverdue(ui) {
  function line(notice) {
    const item = el("li", { className: "row member-row" });
    const lines = [
      `${notice.title} (등록번호 ${notice.accession_number})`,
      `회원번호 ${notice.member_number} · ${notice.name}${notice.phone ? ` · ${formatPhone(notice.phone)}` : ""}`,
      `반납 예정일 ${notice.due_on} · 연체 ${notice.overdue_days}일`,
    ];
    item.append(...lines.map((text, index) => el("p", { className: index === 0 ? "line row-title" : "line row-meta", text })));
    item.append(el("p", { className: "line", text: notice.message }));
    return item;
  }

  async function load() {
    ui.summary.textContent = "불러오는 중…";
    try {
      const data = await api.overdueToday();
      ui.summary.textContent = `${data.today} 기준 ${data.total}건`;
      if (data.lines.length === 0) ui.list.append(el("li", { className: "empty-note", text: "연체 중인 대출이 없어요." }));
      ui.list.append(...data.lines.map(line));
    } catch (error) {
      if (error.kind === "unauthorized") return ui.onUnauthorized();
      if (error.kind === "conflict") {
        ui.summary.textContent = "";
        ui.list.append(el("li", { className: "error-line", text: `${error.detail || ""} ${NO_TEMPLATE_HELP}`.trim() }));
        return;
      }
      ui.summary.textContent = "";
      ui.list.append(el("li", { className: "error-line", text: error.detail || GENERIC_ERROR }));
    }
  }

  function clear() {
    ui.summary.textContent = "";
    ui.list.replaceChildren();
  }

  return {
    show() {
      clear();
      load();
    },
  };
}
