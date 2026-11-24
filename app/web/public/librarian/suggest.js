// 자동완성. 입력이 멈추면(200ms) 부르고 앞 요청은 취소한다.
// Enter는 화살표로 후보를 고른 때만 후보를 고른다. 아니면 onSubmit이 부르는 main.js가 서명·저자 찾기를
// 먼저 하고, 1권 이상이면 두 단계 결과를, 아니면 사서에게 보낸다.
import { api } from "../shared/api.js";

export const DEBOUNCE_MS = 200;
// 서버 검색 API의 질의 상한(`MAX_QUERY_LENGTH`)과 같다. 테스트가 맞춰 본다. 두 단계 검색도 이 값을 쓴다.
export const MAX_QUERY = 100;

export function createSuggest({ input, panel, onPick, onSearchAll, onSubmit, onUnauthorized }) {
  let hits = [];
  let query = "";
  let active = -1;
  let timer = null;
  let controller = null;

  function isOpen() {
    return !panel.hidden;
  }

  function close() {
    clearTimeout(timer);
    if (controller) controller.abort();
    controller = null;
    hits = [];
    active = -1;
    panel.hidden = true;
    panel.replaceChildren();
  }

  function paint() {
    const rows = hits.map((hit, index) => {
      const row = document.createElement("li");
      row.setAttribute("role", "option");
      row.textContent = hit.title;
      if (hit.author) {
        const author = document.createElement("small");
        author.textContent = hit.author;
        row.append(author);
      }
      row.dataset.index = String(index);
      return row;
    });
    const all = document.createElement("li");
    all.className = "all";
    all.setAttribute("role", "option");
    all.textContent = `'${query}'로 책 모두 찾기`;
    all.dataset.index = String(hits.length);
    rows.push(all);
    rows.forEach((row, index) => row.classList.toggle("active", index === active));
    panel.replaceChildren(...rows);
    panel.hidden = false;
  }

  function choose(index) {
    if (index < 0 || index > hits.length) return;
    const accepted = index < hits.length ? onPick(hits[index]) : onSearchAll(query);
    if (accepted === false) return;
    input.value = "";
    close();
  }

  async function load(text) {
    if (controller) controller.abort();
    const mine = new AbortController();
    controller = mine;
    try {
      const found = await api.suggest(text, mine.signal);
      if (controller !== mine) return;
      hits = found;
      query = text;
      active = -1;
      paint();
    } catch (error) {
      if (error.name === "AbortError") return;
      if (error.kind === "unauthorized") onUnauthorized();
      if (controller === mine) close();
    }
  }

  input.addEventListener("input", () => {
    clearTimeout(timer);
    const text = input.value.trim().slice(0, MAX_QUERY);
    if (!text) {
      close();
      return;
    }
    timer = setTimeout(() => load(text), DEBOUNCE_MS);
  });

  input.addEventListener("keydown", (event) => {
    // 한글 조합 중에는 Enter가 두 번 들어온다. 조합 중인 키는 무시한다.
    if (event.isComposing || event.keyCode === 229) return;
    if (event.key === "Enter") {
      event.preventDefault();
      if (isOpen() && active >= 0) choose(active);
      else onSubmit();
    } else if (event.key === "ArrowDown" && isOpen()) {
      event.preventDefault();
      active = (active + 1) % (hits.length + 1);
      paint();
    } else if (event.key === "ArrowUp" && isOpen()) {
      event.preventDefault();
      active = active <= 0 ? hits.length : active - 1;
      paint();
    } else if (event.key === "Escape") {
      close();
    }
  });

  // 클릭할 때 입력창이 포커스를 잃어 목록이 닫히지 않게 mousedown에서 고른다
  panel.addEventListener("mousedown", (event) => {
    const row = event.target.closest("li");
    if (!row) return;
    event.preventDefault();
    choose(Number(row.dataset.index));
  });

  document.addEventListener("pointerdown", (event) => {
    if (!panel.contains(event.target) && event.target !== input) close();
  });

  return { close };
}
