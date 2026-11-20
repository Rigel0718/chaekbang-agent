// POST + 토큰 헤더라 EventSource를 쓸 수 없어서 fetch 스트림을 직접 읽는다.

function parseBlock(block) {
  let name = "message";
  const data = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) name = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
  }
  if (data.length === 0) return null;
  try {
    return { name, data: JSON.parse(data.join("\n")) };
  } catch {
    return null;
  }
}

// 응답 본문을 {name, data} 사건으로 차례로 내준다. 청크가 사건 중간에서 끊겨도 버퍼에 이어 붙인다.
export async function* readEvents(response) {
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += value.replace(/\r\n/g, "\n");
      let end;
      while ((end = buffer.indexOf("\n\n")) >= 0) {
        const event = parseBlock(buffer.slice(0, end));
        buffer = buffer.slice(end + 2);
        if (event) yield event;
      }
    }
    const rest = buffer.trim() ? parseBlock(buffer) : null;
    if (rest) yield rest;
  } finally {
    reader.releaseLock();
  }
}
