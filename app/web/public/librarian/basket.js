// 담은 책. 서버에 회원별로 3시간 보관하고(/basket), 이 화면에는 보여 주는 사본만 메모리(Map)에 둔다.
// 담기·빼기·비우기는 서버가 성공한 뒤에 사본을 바꾼다. 로그아웃하면 사본만 비우고 서버에는 남는다.
// 브라우저 저장소에는 쓰지 않는다(공용 PC).
import { api } from "../shared/api.js";
import { basketLabel, formatSynced, statusText } from "../shared/card.js";

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// ui: { list, empty, count, panel, toggle, clearAll, token(): 회원 토큰, onError(error) }
// onError: 서버 요청이 실패했을 때(401·403·409·그 밖) 화면이 알리는 곳. 성공에는 알리지 않는다.
export function createBasket(ui) {
  const entries = new Map();
  const busy = new Set();

  function syncButtons() {
    for (const button of document.querySelectorAll(".btn-basket")) {
      const id = Number(button.dataset.id);
      button.textContent = basketLabel(entries.has(id));
      button.disabled = busy.has(id);
    }
  }

  function render() {
    ui.count.textContent = String(entries.size);
    ui.empty.hidden = entries.size > 0;
    ui.clearAll.hidden = entries.size === 0;
    const rows = [];
    for (const [id, book] of entries) {
      const row = element("li");
      row.append(element("strong", null, book.title));
      const where = [book.shelf_location, book.call_number].filter(Boolean).join(" · ");
      if (where) row.append(element("span", "where", `서가 ${where}`));
      row.append(element("span", "state", statusText(book)));
      const synced = book.status_synced_at ? formatSynced(book.status_synced_at) : null;
      if (synced) row.append(element("span", "synced", `대출 상태 ${synced} 기준`));
      const remove = element("button", "remove", "×");
      remove.type = "button";
      remove.setAttribute("aria-label", `${book.title} 빼기`);
      remove.addEventListener("click", () => change(id, null));
      row.append(remove);
      rows.push(row);
    }
    ui.list.replaceChildren(...rows);
    syncButtons();
  }

  // 한 권을 담거나(book) 뺀다(null). 같은 책을 요청하는 동안은 그 버튼만 막는다.
  async function change(id, book) {
    if (busy.has(id)) return;
    busy.add(id);
    syncButtons();
    const token = ui.token();
    try {
      if (book) await api.addBasket(id, token);
      else await api.removeBasket(id, token);
      // 요청하는 사이 로그아웃했으면(토큰이 바뀜) 비워 둔 사본을 다시 채우지 않는다
      if (ui.token() === token) {
        if (book) entries.set(id, book);
        else entries.delete(id);
      }
    } catch (error) {
      ui.onError(error);
    } finally {
      busy.delete(id);
      render();
    }
  }

  ui.toggle.addEventListener("click", () => ui.panel.classList.toggle("open"));
  ui.clearAll.addEventListener("click", async () => {
    try {
      await api.clearBasket(ui.token());
      entries.clear();
    } catch (error) {
      ui.onError(error);
    }
    render();
  });

  return {
    has: (id) => entries.has(id),
    toggle(book) {
      const id = book.library_book_id;
      return change(id, entries.has(id) ? null : book);
    },
    // 로그인한 뒤 서버의 담은 책을 불러온다. 실패해도 문구 없이 빈 목록으로 시작한다(401·403만 알린다).
    async load() {
      const token = ui.token();
      try {
        const response = await api.basket(token);
        if (ui.token() === token) {
          entries.clear();
          for (const book of response.books) entries.set(book.library_book_id, book);
        }
      } catch (error) {
        if (error.kind === "unauthorized" || error.kind === "member_required") ui.onError(error);
      }
      render();
    },
    // 화면의 사본만 비운다. 서버에 보관한 담은 책은 지우지 않는다.
    clear() {
      entries.clear();
      busy.clear();
      ui.panel.classList.remove("open");
      render();
    },
  };
}
