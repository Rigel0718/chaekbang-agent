// 담은 책. 화면 메모리(Map)에만 둔다. 새로 고치거나 비우면 사라진다(공용 PC).
import { basketLabel } from "../shared/card.js";

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export function createBasket({ list, empty, count, panel, toggle }) {
  const entries = new Map();

  function syncButtons() {
    for (const button of document.querySelectorAll(".btn-basket")) {
      button.textContent = basketLabel(entries.has(Number(button.dataset.id)));
    }
  }

  function render() {
    count.textContent = String(entries.size);
    empty.hidden = entries.size > 0;
    const rows = [];
    for (const [id, entry] of entries) {
      const row = element("li");
      row.append(element("strong", null, entry.title));
      const where = [entry.shelf, entry.callNumber].filter(Boolean).join(" · ");
      if (where) row.append(element("span", "where", `서가 ${where}`));
      row.append(element("span", "state", entry.state));
      const remove = element("button", "remove", "×");
      remove.type = "button";
      remove.setAttribute("aria-label", `${entry.title} 빼기`);
      remove.addEventListener("click", () => {
        entries.delete(id);
        render();
      });
      row.append(remove);
      rows.push(row);
    }
    list.replaceChildren(...rows);
    syncButtons();
  }

  toggle.addEventListener("click", () => panel.classList.toggle("open"));

  return {
    has: (id) => entries.has(id),
    toggle(book) {
      const id = book.library_book_id;
      if (entries.has(id)) {
        entries.delete(id);
      } else {
        const state =
          book.available_count > 0
            ? `대출 가능 ${book.available_count}권`
            : book.on_loan_count > 0
              ? "모두 대출 중"
              : "대출 가능한 책이 없어요";
        entries.set(id, {
          title: book.title,
          shelf: book.shelf_location,
          callNumber: book.call_number,
          state,
        });
      }
      render();
    },
    clear() {
      entries.clear();
      panel.classList.remove("open");
      render();
    },
  };
}
