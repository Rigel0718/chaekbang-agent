// 무입력 비우기 타이머. 서버의 AI 사서 세션은 입력 없이 5분이면 지워진다(librarian_session_idle_minutes).
// 그보다 앞서 비우도록 4분 30초로 둔다. 서버 설정을 바꾸면 이 값도 바꾼다.
export const IDLE_MS = (4 * 60 + 30) * 1000;

const ACTIVITY = ["keydown", "pointerdown", "input", "wheel", "touchstart", "scroll"];

export function createIdleTimer({ ms = IDLE_MS, onIdle, target = document }) {
  let timer = null;
  let paused = false;

  function arm() {
    clearTimeout(timer);
    if (!paused) timer = setTimeout(onIdle, ms);
  }

  for (const type of ACTIVITY) {
    target.addEventListener(type, arm, { passive: true, capture: true });
  }
  arm();

  return {
    touch: arm,
    // 답을 받는 동안에는 멈춘다
    pause() {
      paused = true;
      clearTimeout(timer);
    },
    resume() {
      paused = false;
      arm();
    },
  };
}
