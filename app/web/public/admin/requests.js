// 희망도서 탭: 처리 전 신청 목록(회원번호 포함). 탭에 들어올 때마다 목록을 비우고 서버에서 다시 읽는다.
import { api } from "../shared/api.js";
import { button, el, when } from "../shared/dom.js";

const PAGE = 20;
const GENERIC_ERROR = "잠시 뒤에 다시 시도해 주세요.";

// ui: { list, more, onUnauthorized() }
export function createRequests(ui) {
  let offset = 0;

  function row(request) {
    const item = el("li", { className: "row member-row" });
    const close = button("닫기", async () => {
      if (!confirm("처리했다고 닫을까요? 닫으면 이 목록에서 사라져요.")) return;
      close.disabled = true;
      try {
        await api.closeBookRequest(request.id);
        item.remove();
      } catch (error) {
        close.disabled = false;
        if (error.kind === "unauthorized") return ui.onUnauthorized();
        item.append(el("p", { className: "error-line", text: error.detail || GENERIC_ERROR }));
      }
    });
    const lines = [
      request.title,
      request.author ? `저자 ${request.author}` : null,
      request.isbn ? `ISBN ${request.isbn}` : null,
      `회원번호 ${request.member_number || "(삭제된 회원)"} · ${when(request.created_at)}`,
    ].filter(Boolean);
    item.append(...lines.map((text, index) => el("p", { className: index === 0 ? "line row-title" : "line row-meta", text })), close);
    return item;
  }

  async function loadMore() {
    ui.more.disabled = true;
    try {
      const page = await api.bookRequests(offset, PAGE);
      if (offset === 0 && page.items.length === 0) {
        ui.list.append(el("li", { className: "empty-note", text: "처리 전 희망도서가 없어요." }));
      }
      ui.list.append(...page.items.map(row));
      offset += page.items.length;
      ui.more.hidden = offset >= page.total;
    } catch (error) {
      if (error.kind === "unauthorized") return ui.onUnauthorized();
      ui.list.append(el("li", { className: "error-line", text: error.detail || GENERIC_ERROR }));
    } finally {
      ui.more.disabled = false;
    }
  }

  ui.more.addEventListener("click", loadMore);

  return {
    show() {
      offset = 0;
      ui.list.replaceChildren();
      ui.more.hidden = true;
      loadMore();
    },
  };
}
