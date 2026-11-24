// 이용자 화면 시계 둘. 서버의 AI 사서 세션은 입력 없이 5분이면 지워지고(librarian_session_idle_minutes),
// 서버의 회원 세션은 로그인에서 3분이면 끝난다(member_session_minutes). 두 시계 모두 그보다 앞서거나 같다.
// 시간 값은 이 네 개뿐이고, 바꾸려면 스펙 web-ui의 "시간 값"도 함께 바꾼다.
//   무입력: 마지막 입력에서 1분(45초에 알림). 입력하면 다시 센다. 답을 받는 동안에는 세지 않는다.
//           로그인하지 않았으면 화면을 비우고 시작 화면, 로그인 중이면 회원만 로그아웃하고 바로 시작 화면이다.
//   이용 상한: 로그인한 순간부터 3분(2분 30초에 알림). 입력해도 늘지 않고 답을 받는 중에도 멈추지 않는다.
//           끝나면 회원만 로그아웃하고 바로 시작 화면이다. 로그인하지 않았으면 상한이 없다.
export const IDLE_MS = 60 * 1000;
export const IDLE_WARN_MS = 45 * 1000;
export const CAP_MS = 180 * 1000;
export const CAP_WARN_MS = 150 * 1000;

const ACTIVITY = ["keydown", "pointerdown", "input", "wheel", "touchstart", "scroll"];

// onWarn(null | { kind: "idle" | "cap", deadline, member }): 지금 보일 알림. 둘이 겹치면 먼저 끝나는 쪽이다.
// onClear({ member }): 시간이 다 됐을 때. 부르는 쪽이 member이면 회원 로그아웃을, 아니면 화면 비우기를 한다.
export function createIdleTimer({
  idleMs = IDLE_MS,
  idleWarnMs = IDLE_WARN_MS,
  capMs = CAP_MS,
  capWarnMs = CAP_WARN_MS,
  onWarn,
  onClear,
  target = document,
}) {
  let started = false; // 비운 뒤 첫 입력이 있었는지(무입력 시계)
  let paused = false;
  let memberOn = false; // 회원이 로그인해 있는지(이용 상한 시계와 시계가 하는 일을 정한다)
  const timers = { idleWarn: null, idle: null, capWarn: null, cap: null };
  const deadlines = { idle: null, cap: null };

  let shown = null; // 마지막으로 알린 알림(같은 알림을 되풀이해 알리지 않는다)

  function publish() {
    const live = Object.entries(deadlines).filter(([, deadline]) => deadline !== null);
    const next = live.length === 0 ? null : live.reduce((a, b) => (a[1] <= b[1] ? a : b));
    if ((next && next.join()) === (shown && shown.join())) return;
    shown = next;
    onWarn(next ? { kind: next[0], deadline: next[1], member: memberOn } : null);
  }

  function stop(name) {
    clearTimeout(timers[name]);
    timers[name] = null;
  }

  function stopIdle() {
    stop("idleWarn");
    stop("idle");
    deadlines.idle = null;
  }

  function stopCap() {
    stop("capWarn");
    stop("cap");
    deadlines.cap = null;
  }

  function armIdle() {
    stopIdle();
    if (paused || !started) return;
    const now = Date.now();
    timers.idleWarn = setTimeout(() => {
      deadlines.idle = now + idleMs;
      publish();
    }, idleWarnMs);
    timers.idle = setTimeout(expire, idleMs);
  }

  function armCap() {
    const now = Date.now();
    timers.capWarn = setTimeout(() => {
      deadlines.cap = now + capMs;
      publish();
    }, capWarnMs);
    timers.cap = setTimeout(expireMember, capMs);
  }

  // 무입력 1분: 로그인 중이면 회원만 로그아웃(부르는 쪽이 `memberLoggedOut`을 부른다), 아니면 화면을 비운다.
  function expire() {
    if (memberOn) {
      onClear({ member: true });
      return;
    }
    reset();
    onClear({ member: false });
  }

  function expireMember() {
    onClear({ member: true });
  }

  // 비운 직후 상태로 돌아간다. 다음 첫 입력에서 무입력 시계가 다시 시작한다.
  function reset() {
    started = false;
    stopIdle();
    if (!memberOn) stopCap(); // 로그인 중의 이용 상한은 로그아웃에서만 멈춘다
    publish();
  }

  function activity() {
    started = true;
    armIdle();
    publish();
  }

  for (const type of ACTIVITY) {
    target.addEventListener(type, activity, { passive: true, capture: true });
  }

  return {
    reset,
    // 로그인한 순간부터 이용 상한을 센다. 로그인은 입력이라 무입력도 다시 센다.
    memberLoggedIn() {
      memberOn = true;
      stopCap();
      armCap();
      started = true;
      armIdle();
      publish();
    },
    // 로그아웃하면 상한은 멈춘다. 부르는 쪽이 이어서 reset()으로 시작 화면에 들어가므로 무입력 시계는 다시 세지 않는다.
    memberLoggedOut() {
      memberOn = false;
      stopCap();
      stopIdle();
      if (started) armIdle();
      publish();
    },
    // 답을 받는 동안에는 무입력 시계만 멈춘다. 이용 상한은 멈추지 않는다.
    pause() {
      paused = true;
      stopIdle();
      publish();
    },
    resume() {
      paused = false;
      armIdle();
    },
  };
}
