// 로그인 화면. 응답의 역할로 행선지를 정하고 토큰은 그 역할의 키에 저장한다.
import { api, setToken, useScreen, GENERIC_ERROR } from "../shared/api.js";

// 역할 → 화면. 이 표에 없는 역할은 이동하지 않는다.
const DESTINATIONS = {
  kiosk: "/ui/librarian/",
  admin: "/ui/admin/",
};
const UNKNOWN_ROLE = "이 계정은 화면을 쓸 수 없어요.";

const form = document.getElementById("login-form");
const loginId = document.getElementById("login-id");
const password = document.getElementById("login-password");
const submit = document.getElementById("login-submit");
const errorLine = document.getElementById("login-error");

function showError(text) {
  errorLine.textContent = text;
  errorLine.hidden = false;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorLine.hidden = true;
  submit.disabled = true;
  try {
    const result = await api.login(loginId.value.trim(), password.value);
    const destination = DESTINATIONS[result.role];
    if (!destination) return showError(UNKNOWN_ROLE);
    useScreen(result.role);
    setToken(result.token);
    password.value = "";
    location.assign(destination);
  } catch (error) {
    // 401은 아이디·비밀번호 어느 쪽이 틀렸는지 알리지 않는 서버 문구를 그대로 보인다
    showError(error.kind === "unauthorized" && error.detail ? error.detail : GENERIC_ERROR);
  } finally {
    submit.disabled = false;
  }
});
