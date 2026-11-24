# Design

## Context

- 담은 책은 지금 `basket.js`의 `Map`(화면 메모리)이고, 담는 순간의 서명·서가·대출 상태 글을 복사해 든다. 로그아웃(`memberLogout`·`memberLost`)과 익명 `resetAll`이 `basket.clear()`로 비운다. 이용 상한(로그인부터 3분)이 서가에서 책을 읽는 시간보다 짧아 돌아오면 비어 있다(proposal의 Why).
- 회원 세션(`member_sessions`)은 3분이고 로그인마다 새로 생기지만, 회원(`members.id`)은 그대로다. 그래서 담은 책은 세션이 아니라 회원에 붙여야 다시 로그인했을 때 이어진다.
- `current_member`가 `MemberContext(member_id, session_id)`를 주고 기관은 `staff.library_id`가 정한다(`POST /loans`·`/book-requests`와 같은 방식). 직원 토큰 오류는 401, 회원 세션 오류는 403이다.
- 책 값을 만드는 함수가 이미 있다: `get_candidates`·`shelf_of`·`build_summaries`(`app/library/recommendation/cards.py`)가 찾기 결과·카드·큐레이션에 같은 값을 준다. `get_findable`은 "그 기관의 찾을 수 있는 책"을 확인한다.
- 1분마다 끝난 대화 세션을 지우는 작업 `purge_forever`가 `lifespan`에 있다.
- 비밀번호 없는 번호 로그인이라 번호를 아는 사람은 로그인할 수 있다. 담은 책이 서버에 남으면 그 사람에게 보인다.

## Goals / Non-Goals

**Goals:**
- 담고, 로그아웃(버튼·무입력·상한)하고, 다시 번호로 로그인하면 담은 책이 그대로 나온다.
- 저장하는 값은 책 id와 담은 시각뿐이고, 3시간이 지나면 사라진다.
- 담은 책이 추천·분석·기록 어디에도 새지 않는다(개인화와의 경계).

**Non-Goals:**
- 담은 책 칸의 [빌리기]·[이 책 물어보기], 서가 순 정렬, 출력·보내기.
- 문자 인증·실패 횟수 제한(번호만 알면 보이는 문제의 근본 해결).
- 보관 시간·권수의 조정 화면, 슬라이딩 보관.

## Decisions

### 1. 한 change, 테이블 하나

`basket_items(id, library_id, member_id, library_book_id, added_at)`. `(library_id, member_id)`와 `(library_id, library_book_id)` 두 복합 외래 키가 모두 `ON DELETE CASCADE`이고, `(library_id, member_id, library_book_id)`가 유일하다. 기관 도서 쪽도 CASCADE인 이유는 담은 책은 다시 담으면 되는 값이라 남길 이유가 없어서다. `TENANT_TABLES`에 등록한다. 만료 정리를 위해 `added_at`에 색인을 둔다.

`TimestampMixin`의 `created_at` 대신 `added_at`을 따로 두고 `clock.now()`로 넣는다. 테스트가 시각을 바꿔 가며 만료를 볼 수 있어야 해서다.

**대안**: 서버 필요 없이 `localStorage` — 공용 PC라 다음 사람이 보고, 회원에 붙지도 않아 기각. 서버 값을 회원 세션에 붙이기 — 로그인마다 새로 생겨 이어지지 않아 기각.

### 2. 보관은 담은 시각부터 3시간 고정

행마다 `added_at + 3시간`이 끝이다. 같은 책을 다시 담아도(`PUT` 멱등) `added_at`은 그대로다. 뺐다가 다시 담으면 새 행이라 새 3시간이다. 코드값 `basket_keep_hours = 3`(`Settings`, `.env`로 덮이지 않음).

**대안**: 기관 시간대 "오늘" — 아침에 담으면 15시간 남아 번호를 아는 사람에게 보이는 기간이 길다. 슬라이딩 — 계속 쓰면 끝없이 남아 "보관 기간을 넘겨 남기면 개인화"라는 경계가 흐려진다. 둘 다 기각.

### 3. 만료: 읽을 때 거르고, 기존 1분 작업이 지움

`GET`·`PUT`의 권수 세기·`PUT` 중복 확인은 모두 `added_at > now - 3시간`인 행만 본다. 지우기는 `purge_forever`가 이미 1분마다 도는 반복에서 담은 책 service의 `purge_expired`를 한 줄 더 부른다(새 작업·새 스레드 없음). 그래서 "읽을 때 거르기"가 작업이 멈춰도 만료한 책을 보이지 않게 하고, "지우기"가 기간을 넘겨 남지 않게 한다. `chat.py`는 함수를 부를 뿐 테이블을 언급하지 않는다.

만료한 줄이 `PUT`의 유일 제약에 걸리지 않도록, 담기는 만료한 같은 줄을 먼저 지우거나 덮어쓴다(같은 트랜잭션).

### 4. 상한 10권

만료하지 않은 줄 수가 10이면 새 책 `PUT`은 409 "담은 책은 10권까지예요"이다. 이미 담은 책의 `PUT`은 권수를 세지 않고 204다. 숨겨진 책(추천 불가)도 센다. 코드값 `basket_limit = 10`. 동시 요청이 상한을 살짝 넘길 수 있지만 잠금은 두지 않는다(미룸).

### 5. API: `/basket` 네 경로, 회원은 세션이 정함

`GET /basket` → `{ books: [BasketBook] }`, `PUT /basket/{id}` → 204, `DELETE /basket/{id}` → 204, `DELETE /basket` → 204. `CurrentStaff + CurrentMember`. `BasketBook`은 `BookSummary`에 `added_at`만 더한 스키마이고 필드는 허용 목록 테스트가 고정한다. 담기·빼기는 본문 없이 204라 서버가 카드 값을 만드는 곳은 `GET` 하나다.

`PUT`은 `get_findable`로 확인하고 없는 책·다른 기관 책·추천 불가 책은 모두 같은 404다. `DELETE /basket/{id}`는 id를 검사하지 않고 `WHERE library_id, member_id, library_book_id`로 지워 다른 기관 id에는 아무것도 지워지지 않은 채 204다.

### 6. 책 값은 읽을 때 새로 만든다

`GET`은 만료하지 않은 줄의 id를 담은 순서로 읽고, `get_candidates`로 지금의 대출 가능·대출 중 수와 외부 기관 갱신 시각을 얻고, 추천할 수 있는 책만 `shelf_of`와 `summary_values`로 카드 값(`build_summaries`)으로 만든다. 사본이 모두 제적·분실·파손된 책은 응답에서 빼지만 행은 지우지 않는다(`GET`은 읽기만. 되찾으면 돌아오고, 행은 3시간 뒤 사라진다). 응답에 빠진 책의 수를 넣지 않는다(화면이 문구를 띄우지 않기로 했다).

### 7. 화면: 로그인 표시 클래스 하나로 [담기]를 숨긴다

로그인하지 않았을 때 카드에 [담기]가 없어야 하고, 로그인·로그아웃하는 순간 이미 떠 있는 카드도 바뀌어야 한다. 카드를 다시 그리지 않고 이용자 화면 맨 바깥 요소의 클래스(`logged-in`) 하나를 켜고 끄며, CSS가 `.btn-basket`을 보이고 숨긴다. 이 클래스는 `renderMember(loggedIn)`이 정한다. 그 결과 "로그인 전 담기 → 로그인 뒤 이어서 함"의 기다리는 동작이 담기에는 필요 없어져 `memberBasket.toggle`의 로그인 분기를 없앤다.

`basket.js`는 서버 호출 함수를 받아 쓴다(`createBasket({..., api})`). `toggle`은 서버 성공 뒤에 `Map`을 바꾸고 `syncButtons()`한다. 요청하는 동안 그 버튼만 비활성이다. 로그인 성공 직후(`member.onChange(true)`) `GET /basket`을 불러 `Map`을 채우고, 로그아웃·403에서는 `basket.clear()`가 화면 `Map`만 비운다(서버 호출 없음). 불러오기 실패는 문구 없이 빈 목록이다.

오류 매핑은 `api.js`의 종류(`unauthorized`→로그인 화면, `member_required`→`memberLost`)를 그대로 쓴다. 409는 상한 문구, 그 밖은 "잠시 뒤 다시 눌러 주세요"이고 알림 띠(`showNotice`)로 보인다.

### 8. 경계는 소스 허용 목록 테스트 하나로 고정한다

`BasketItem`·`basket_items`를 언급하는 `app/` 파일이 허용 목록(모델, `services/basket.py`, `api/basket.py`, `schemas/basket.py`, `app/models.py`)뿐인지 검사한다(마이그레이션은 `app/` 밖). 추천·AI 사서·분석·노출 기록이 이 테이블을 읽는 길이 생기면 테스트가 먼저 걸린다. 행 수 불변(노출 기록·실행 기록·대화 메시지), 로그 없음, 관리자 토큰만으로는 403은 service 테스트로 둔다. 자연어 SQL은 아직 없어 "허용 범위에 넣지 않는다"는 스펙 문장으로 남기고, 그 기능이 열릴 때 테스트를 더한다.

### 9. 스키마 스펙 정리

`platform/database-schema` 본문이 24e에서 `member_sessions`를 빠뜨려 28개로 어긋나 있다. 이 change의 delta가 `member_sessions`와 `basket_items`를 함께 넣어 30개로 맞춘다.

## Risks / Trade-offs

- [번호를 아는 사람이 남의 담은 책을 3시간 볼 수 있다] → 보관을 3시간으로 짧게 두고 [모두 빼기]를 준다. 근본 해결은 문자 인증·실패 횟수 제한(미룸)과 함께 한다. 이용자 대화·로그에는 번호를 남기지 않는 지금 규칙은 그대로다.
- [동시 담기가 10권 상한을 넘길 수 있다] → 같은 회원이 두 키오스크에서 동시에 담는 드문 경우라 받아들인다. 잠금은 미룬다.
- [`GET`이 만료한 줄을 읽을 때 거르기만 하므로 정리 작업이 멈추면 DB에 남는다] → 사용자에게 보이지 않고 다음 회차에 지운다. 서버가 켜져 있는 동안 1분 주기다.
- [로그아웃 직전에 보낸 `PUT`이 늦게 도착해 한 권이 더 담길 수 있다] → 같은 회원의 담은 책이라 받아들인다.
- [로그인한 3분 동안 패널의 책 값은 담은 순간의 값이다] → 다시 로그인하면 새 값이다. 로그인 중 다시 읽기는 미룬다.
- [`added_at` 응답 필드가 담은 시각을 알린다] → 순서를 보이기 위한 값이고 화면은 시각을 보이지 않는다.

## Migration Plan

1. Alembic 마이그레이션 하나로 `basket_items`를 만든다(기존 테이블 변경 없음).
2. 개발 DB는 백업한 뒤 `pg_dump … && alembic upgrade head`로 `&&`로 이어 적용한다(도구의 여러 줄 Bash에서 `set -e`가 멈추지 않는다).
3. 되돌리기는 `alembic downgrade -1`(담은 책은 다시 만들 수 있는 값이라 잃어도 된다). 화면은 새 API가 없으면 불러오기 실패로 빈 목록이 되므로 배포 순서 제약이 없다.
