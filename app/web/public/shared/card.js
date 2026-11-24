// 책 카드 하나를 검색 결과·찾은 책·추천·비슷한 책에 모두 쓴다.
// 책 값은 book 변수의 속성으로만 읽는다(필드 계약 테스트가 이 형태를 모은다).
// 서버 값은 textContent로만 넣는다. 주소는 safeUrl을 거친다.

const SIMILAR_EMPTY = "비슷한 책을 찾지 못했어요.";
const SIMILAR_FAILED = "비슷한 책을 불러오지 못했어요.";

export function basketLabel(inBasket) {
  return inBasket ? "담김" : "담기";
}

// http·https 주소만 쓴다. 그 밖의 주소(javascript: 등)는 null이다.
export function safeUrl(url) {
  if (typeof url !== "string") return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : null;
  } catch {
    return null;
  }
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

export function formatSynced(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString("ko-KR", {
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function statusText(book) {
  if (book.available_count > 0) return `대출 가능 ${book.available_count}권`;
  if (book.on_loan_count > 0) return "모두 대출 중";
  return "대출 가능한 책이 없어요";
}

function coverNode(book) {
  const box = element("div", "cover");
  const url = safeUrl(book.cover_url);
  const placeholder = () => {
    box.replaceChildren();
    box.classList.add("cover-empty");
    box.append(element("span", "cover-letter", (book.title || "?").slice(0, 1)));
  };
  if (!url) {
    placeholder();
    return box;
  }
  const img = element("img");
  img.alt = `${book.title} 표지`;
  img.loading = "lazy";
  img.referrerPolicy = "no-referrer";
  img.addEventListener("error", placeholder);
  img.src = url;
  box.append(img);
  return box;
}

function sourceLine(book) {
  const line = element("p", "source");
  if (!book.cover_source) return line;
  const link = safeUrl(book.product_url);
  line.append("표지: ");
  if (link) {
    const anchor = element("a", null, book.cover_source);
    anchor.target = "_blank";
    anchor.rel = "noopener noreferrer";
    anchor.href = link;
    line.append(anchor);
  } else {
    line.append(book.cover_source);
  }
  return line;
}

function extraLine(book, kind) {
  if (kind === "recommend" && book.reason) return element("p", "extra reason", book.reason);
  if (kind === "similar" && book.basis_text && book.basis_text.length > 0) {
    return element("p", "extra basis", book.basis_text.join(" · "));
  }
  return null;
}

// options: { loadSimilar(id), onAsk(book), basket: { has(id), toggle(book) } }
// kind: summary | recommend | similar. 비슷한 책 카드는 다시 펼치지 않는다.
export function createCard(book, kind, options) {
  const card = element("article", `card card-${kind}`);
  card.dataset.id = String(book.library_book_id);

  const main = element("div", "card-main");
  main.tabIndex = 0;
  main.setAttribute("role", "button");
  main.setAttribute("aria-expanded", "false");
  const info = element("div", "info");
  info.append(element("h3", "title", book.title));
  const meta = [book.author, book.publisher].filter(Boolean).join(" · ");
  if (meta) info.append(element("p", "meta", meta));
  const status = element("p", "status", statusText(book));
  if (book.available_count > 0) status.classList.add("available");
  info.append(status);
  const synced = book.status_synced_at ? formatSynced(book.status_synced_at) : null;
  if (synced) info.append(element("p", "synced", `대출 상태 ${synced} 기준`));
  const shelf = [book.shelf_location, book.call_number].filter(Boolean).join(" · ");
  if (shelf) info.append(element("p", "shelf", `서가 ${shelf}`));
  const extra = extraLine(book, kind);
  if (extra) info.append(extra);
  main.append(coverNode(book), info);

  const actions = element("div", "actions");
  const ask = element("button", "btn btn-ask", "이 책 물어보기");
  ask.type = "button";
  ask.addEventListener("click", () => options.onAsk(book));
  const basket = element("button", "btn btn-basket", basketLabel(options.basket.has(book.library_book_id)));
  basket.type = "button";
  basket.dataset.id = String(book.library_book_id);
  basket.addEventListener("click", () => options.basket.toggle(book));
  actions.append(ask, basket);

  card.append(main, sourceLine(book), actions);

  if (kind !== "similar") {
    const similar = element("div", "similar");
    similar.hidden = true;
    card.append(similar);
    let loaded = false;
    const expand = async () => {
      const open = similar.hidden;
      similar.hidden = !open;
      main.setAttribute("aria-expanded", String(open));
      if (!open || loaded) return;
      loaded = true;
      similar.replaceChildren(element("p", "similar-note", "비슷한 책을 찾는 중…"));
      try {
        const books = await options.loadSimilar(book.library_book_id);
        const nodes =
          books.length === 0
            ? [element("p", "similar-note", SIMILAR_EMPTY)]
            : books.map((item) => createCard(item, "similar", options));
        similar.replaceChildren(...nodes);
      } catch {
        loaded = false;
        similar.replaceChildren(element("p", "similar-note", SIMILAR_FAILED));
      }
    };
    main.addEventListener("click", expand);
    main.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        expand();
      }
    });
    // 찾은 책이 한 권일 때 대화가 부른다
    card.expand = () => {
      if (similar.hidden) expand();
    };
  }
  return card;
}
