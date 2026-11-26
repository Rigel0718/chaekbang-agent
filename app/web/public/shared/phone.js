// 휴대폰 번호의 하이픈. 보이는 꼴과 입력칸의 규칙은 이 파일 한 곳에 있다.
// 02로 시작하면 2-3-4(9자리)·2-4-4(10자리), 그 밖은 3-3-4(10자리)·3-4-4(11자리). 서버는 하이픈을 지워 저장한다.

const MAX_LENGTH = 13; // 11자리 + 하이픈 둘

function areaLength(digits) {
  return digits.startsWith("02") ? 2 : 3;
}

function join(digits, area, middle) {
  const parts = [digits.slice(0, area), digits.slice(area, area + middle), digits.slice(area + middle)];
  return parts.filter(Boolean).join("-");
}

// 보이기: 숫자뿐이고 길이가 맞는 번호만 하이픈을 넣는다. 그 밖의 값은 받은 그대로다.
export function formatPhone(value) {
  const text = value || "";
  if (!/^\d+$/.test(text)) return text;
  const area = areaLength(text);
  const middle = text.length - area - 4;
  if (!text.startsWith("0") || (middle !== 3 && middle !== 4)) return text;
  return join(text, area, middle);
}

// 치는 중: 앞에서부터 하이픈을 넣는다. 010은 늘 3-4-4다.
function formatTyping(digits) {
  const area = areaLength(digits);
  const rest = digits.length - area;
  if (rest <= 0) return digits;
  const middle = digits.startsWith("010") || rest - 4 > 3 ? 4 : 3;
  return join(digits, area, middle);
}

// 번호 입력칸: 숫자만 남기고 치는 대로 하이픈을 넣는다. 커서는 같은 숫자 뒤에 둔다.
export function attachPhoneInput(input) {
  input.setAttribute("maxlength", String(MAX_LENGTH));
  input.addEventListener("input", () => {
    const before = input.value.slice(0, input.selectionStart ?? input.value.length).replace(/\D/g, "").length;
    const digits = input.value.replace(/\D/g, "");
    const next = formatTyping(digits.slice(0, digits.startsWith("02") ? 10 : 11));
    input.value = next;
    let position = 0;
    for (let seen = 0; position < next.length && seen < before; position += 1) {
      if (/\d/.test(next[position])) seen += 1;
    }
    input.setSelectionRange?.(position, position);
  });
}
