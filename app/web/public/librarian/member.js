// 회원 로그인 상태. 토큰은 이 모듈의 변수 한 칸에만 있다(브라우저 저장소에 쓰지 않는다. 새로 고치면 로그아웃).
// 이름·회원번호·휴대폰 번호는 어디에도 두지 않는다. 휴대폰 번호는 로그인 요청의 본문으로만 간다.
import { api } from "../shared/api.js";

// onChange(loggedIn): 로그인·로그아웃으로 상태가 바뀔 때(위 띠 표시, 시계)
export function createMember({ onChange }) {
  let token = null;

  return {
    get loggedIn() {
      return token !== null;
    },
    // 대출·희망도서 요청에 붙일 토큰. 다른 요청에는 쓰지 않는다.
    get token() {
      return token;
    },
    async login(phone) {
      const response = await api.memberLogin(phone);
      token = response.member_token;
      onChange(true);
    },
    // 화면은 바로 로그아웃하고, remote이면 서버 세션도 끊는다(서버 요청이 실패해도 화면은 로그아웃한 채다).
    // 서버 세션은 3분이면 저절로 끝난다.
    async logout({ remote = true } = {}) {
      const old = token;
      if (old === null) return;
      token = null;
      onChange(false);
      if (!remote) return;
      try {
        await api.memberLogout(old);
      } catch {
        // 이미 끝났거나 연결이 끊겼다. 서버 세션은 저절로 끝난다.
      }
    },
  };
}
