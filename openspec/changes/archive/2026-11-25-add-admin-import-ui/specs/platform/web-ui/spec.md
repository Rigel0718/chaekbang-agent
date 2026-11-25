## MODIFIED Requirements

### Requirement: 기존 API만 사용
화면은 화면 전용 API 없이 기존 API만 MUST 쓴다. 화면이 부르는 경로는 다른 클라이언트도 쓰는 일반 API이고, 화면 때문에 `/ui` 아래에 API 경로를 두지 않는다.
- 로그인 화면: 로그인, 내 정보
- 이용자 화면: 내 정보, 자동완성, 검색, 주제 검색, 비슷한 책, AI 사서 대화, 대화 종료, 도서관 안내, 회원 로그인·로그아웃, 담은 책(불러오기·담기·빼기·비우기), 대출, 반납, 희망도서 신청
- 관리자 화면: 내 정보, 로그아웃, 기관 정보, 운영 에이전트 대화와 대화 종료, 큐레이션·연체 안내문 틀·구매 요청서의 목록·상세·승인·반려(큐레이션은 내리기도), 희망도서 목록과 닫기, 오늘의 연체 안내 목록, 장서 가져오기(올리기, 기록 목록·단건, 행 목록, 적용, 미리 보기 삭제)

#### Scenario: 서버 경로
- **WHEN** 서버의 경로 목록을 읽으면
- **THEN** `/ui` 아래에는 정적 파일 경로 하나만 있고 API 경로가 없다

#### Scenario: 화면이 부르는 경로
- **WHEN** 화면 스크립트에서 서버에 요청하는 경로를 모두 모으면
- **THEN** 모두 `/auth/login`, `/auth/me`, `/auth/logout`, `/auth/member-login`, `/auth/member-logout`, `/catalog/suggest`, `/catalog/search`, `/catalog/topic`, `/catalog/books/{id}/similar`, `/librarian/messages`, `/librarian/sessions/{id}`, `/library`, `/library/guide`, `/basket`, `/basket/{id}`, `/loans`, `/loans/return`, `/book-requests`, `/book-requests/{id}`, `/admin-agent/messages`, `/admin-agent/sessions/{id}`, `/curations`, `/curations/{id}`, `/curations/{id}/approve`, `/curations/{id}/reject`, `/curations/{id}/unpublish`, `/overdue-notice-templates`, `/overdue-notice-templates/{id}`, `/overdue-notice-templates/{id}/approve`, `/overdue-notice-templates/{id}/reject`, `/purchase-requests`, `/purchase-requests/{id}`, `/purchase-requests/{id}/approve`, `/purchase-requests/{id}/reject`, `/overdue-notices/today`, `/holding-imports`, `/holding-imports/{id}`, `/holding-imports/{id}/rows`, `/holding-imports/{id}/apply` 중 하나다

#### Scenario: 부르는 경로가 서버에 있음
- **WHEN** 화면 스크립트가 요청하는 경로와 메서드를 서버의 경로 목록과 맞춰 보면
- **THEN** 모두 서버에 있는 경로와 메서드다

### Requirement: 관리자 화면의 탭과 운영 방식
관리자 화면은 한 페이지에 탭 다섯(운영 대화, 승인 목록, 희망도서, 오늘의 연체, 장서 가져오기)을 SHALL 둔다. 열린 탭은 주소 hash로 기억한다. 기관 정보(`GET /library`)의 `loan_mode`가 `internal`일 때만 [오늘의 연체] 탭과 승인 목록의 연체 안내문 틀 묶음을 보이고, `external`일 때만 [장서 가져오기] 탭을 보인다. 기관 정보를 읽지 못하면 둘 다 숨긴다. 숨긴 탭의 주소로 열면 운영 대화를 연다. 최종 판단은 서버(409)가 한다.

#### Scenario: 처음 그린 화면
- **WHEN** 관리자 화면 HTML을 읽으면
- **THEN** [오늘의 연체] 탭, 연체 안내문 틀 묶음, [장서 가져오기] 탭은 숨김 상태로 시작한다

#### Scenario: 보이는 조건
- **WHEN** 관리자 화면 스크립트에서 위 세 가지를 보이게 하는 곳을 검사하면
- **THEN** 기관 정보의 `loan_mode`를 한 곳에서 읽고, 연체 탭과 틀 묶음은 `internal`일 때만, [장서 가져오기] 탭은 `external`일 때만 보인다

#### Scenario: 외부 대출 기관
- **WHEN** 외부 대출 기관의 관리자로 관리자 화면을 열면
- **THEN** [장서 가져오기] 탭이 보이고 [오늘의 연체] 탭과 연체 안내문 틀 묶음은 보이지 않는다(브라우저 확인)

#### Scenario: 자체 대출 기관
- **WHEN** 자체 대출 기관의 관리자로 `#imports` 주소를 열면
- **THEN** [장서 가져오기] 탭은 보이지 않고 운영 대화가 열린다(브라우저 확인)

## ADDED Requirements

### Requirement: 장서 가져오기 화면
관리자 화면의 [장서 가져오기]는 파일(xlsx, CSV)을 올려 미리 보기를 만들고, 요약(전체·새로·바뀜·그대로·건너뜀 행 수, 파일에서 빠진 사본 수, 인식한 열)과 확인할 행을 SHALL 보인다. 확인할 행은 건너뛴 행과 표기 넷(`invalid_isbn`, `unknown_status`, `purchased_without_isbn`, `purchased_without_price`)이고 20줄씩 더 본다. 표기와 열 이름은 한국어로 보인다. 탭에 들어올 때마다 지난 가져오기 목록을 다시 읽고, 기록을 누르면 그 요약을 연다.

필수 열을 찾지 못한 응답(422)에 파일 머리글이 있으면 못 찾은 필수 열마다 머리글에서 고르게 하고, 고른 열을 `column_mapping`으로 같은 파일과 다시 보낸다.

#### Scenario: 화면이 읽는 값
- **WHEN** 가져오기 화면 스크립트가 읽는 기록과 행의 필드를 응답 스키마와 맞춰 보면
- **THEN** 모두 `HoldingImportRead`와 `HoldingImportRow`에 있는 필드다

#### Scenario: 열과 표기의 이름
- **WHEN** 가져오기 화면 스크립트의 열 이름·표기 이름 표를 서버의 열 정의·표기와 맞춰 보면
- **THEN** 열 키와 한국어 이름이 서버와 같고 표기 넷이 모두 있다

#### Scenario: 미리 보기 요약
- **WHEN** 정상 파일을 올리면
- **THEN** 행 수, 파일에서 빠진 사본 수, 인식한 열이 보이고 장서는 바뀌지 않는다(브라우저 확인)

#### Scenario: 열 고르기
- **WHEN** 저자 열의 머리글이 인식되지 않는 파일을 올리고, 보이는 목록에서 그 머리글을 골라 다시 올리면
- **THEN** 처음에는 저자 열을 고르는 칸이 보이고, 다시 올리면 미리 보기 요약이 보인다(브라우저 확인)

#### Scenario: 읽을 수 없는 파일
- **WHEN** 예전 `.xls` 파일이나 빈 파일을 올리면
- **THEN** 열 고르기 없이 서버 문구가 보인다(브라우저 확인)

#### Scenario: 확인할 행
- **WHEN** 미리 보기에서 확인할 행의 종류를 누르면
- **THEN** 그 행의 행 번호, 등록번호, 서명, 저자, 사유가 20줄까지 보이고 더 있으면 [더 보기]가 있다(브라우저 확인)

#### Scenario: 기증처
- **WHEN** 기증처 열이 있는 파일을 올려 요약과 행 목록을 보면
- **THEN** 화면에 기증처 값이 없다(브라우저 확인)

### Requirement: 장서 가져오기의 적용
[적용]은 가장 최근 기록이 미리 보기일 때 그 기록에만 MUST 보인다. 확인 한 번 뒤 적용한다. 대량 제적 409면 파일에서 빠진 사본이 절반 이상이라고 알리고 한 번 더 확인한 뒤에만 `confirm_withdraw=true`로 다시 적용한다. 성공은 문구 없이 목록과 요약을 다시 읽어 보이고, 실패는 서버 문구를 글자로 보인다. 처음 요청에는 `confirm_withdraw`를 붙이지 않는다.

#### Scenario: 대량 제적 응답의 구분
- **WHEN** 화면이 대량 제적 409를 알아보는 낱말을 서버의 대량 제적 문구와 맞춰 보면
- **THEN** 서버 문구에 그 낱말이 있다

#### Scenario: 적용 취소
- **WHEN** [적용]의 확인 창에서 취소하면
- **THEN** 요청을 보내지 않고 기록은 미리 보기로 남는다(브라우저 확인)

#### Scenario: 적용
- **WHEN** [적용]을 확인하면
- **THEN** 성공 문구 없이 기록이 "적용함"이 되고 [적용]이 사라진다(브라우저 확인)

#### Scenario: 대량 제적 확인
- **WHEN** 가져온 사본의 절반 이상이 빠진 파일을 적용하면
- **THEN** 두 번째 확인이 뜨고, 취소하면 장서가 그대로이며 확인하면 적용된다(브라우저 확인)

#### Scenario: 오래된 미리 보기
- **WHEN** 미리 보기를 두 번 만든 뒤 앞의 기록을 열면
- **THEN** 요약은 보이고 [적용]은 없다(브라우저 확인)

### Requirement: 장서 가져오기의 파일 선택과 기록 정리
올려서 미리 보기가 생기면 파일 선택을 SHALL 비운다. 열 고르기가 필요한 경우처럼 미리 보기가 생기지 않으면 파일 선택을 남긴다. 지난 가져오기 목록은 적용한 기록과 미리 보기를 색과 글자로 나누어 보이고, 지금 연 기록을 표시한다. 미리 보기 기록의 요약에는 [삭제]가 있고 확인 한 번 뒤 지운다. 적용한 기록에는 [삭제]가 MUST NOT 있다.

#### Scenario: 같은 파일을 두 번 올리지 않음
- **WHEN** 파일을 올려 미리 보기가 생긴 뒤 [올리기]를 다시 누르면
- **THEN** 파일 선택이 비어 있어 새 기록이 생기지 않는다(브라우저 확인)

#### Scenario: 삭제 버튼의 자리
- **WHEN** 화면 스크립트에서 [삭제]를 만드는 곳을 검사하면
- **THEN** 미리 보기 기록에만 만들고, 확인 창 뒤에만 삭제 요청을 보낸다

#### Scenario: 미리 보기 삭제
- **WHEN** 미리 보기의 [삭제]를 누르고 확인하면
- **THEN** 그 기록이 목록에서 사라지고 요약이 닫힌다. 취소하면 그대로다(브라우저 확인)

#### Scenario: 기록의 구분
- **WHEN** 적용한 기록과 미리 보기가 함께 있는 목록을 보면
- **THEN** 두 상태의 색이 다르고 연 기록이 표시된다(브라우저 확인)
