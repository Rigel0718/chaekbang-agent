// 서버 값을 글자로만 넣는 요소 도우미. HTML로 해석하는 API는 쓰지 않는다(README 규칙).
export function el(tag, { className, text, attrs, children } = {}) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  if (attrs) for (const [name, value] of Object.entries(attrs)) node.setAttribute(name, value);
  if (children) node.append(...children);
  return node;
}

export function button(text, onClick, className = "btn") {
  const node = el("button", { className, text, attrs: { type: "button" } });
  node.addEventListener("click", onClick);
  return node;
}

export function won(value) {
  return value === null || value === undefined ? "-" : `${value.toLocaleString("ko-KR")}원`;
}

export function when(iso) {
  return iso ? new Date(iso).toLocaleString("ko-KR", { dateStyle: "medium", timeStyle: "short" }) : "-";
}
