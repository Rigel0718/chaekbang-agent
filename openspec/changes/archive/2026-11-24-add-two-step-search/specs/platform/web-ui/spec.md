## MODIFIED Requirements

### Requirement: 기존 API만 사용
화면은 화면 전용 API 없이 기존 API만 MUST 쓴다. 화면이 부르는 경로는 다른 클라이언트도 쓰는 일반 API이고, 화면 때문에 `/ui` 아래에 API 경로를 두지 않는다.
- 로그인 화면: 로그인, 내 정보
- 이용자 화면: 내 정보, 자동완성, 검색, 주제 검색, 비슷한 책, AI 사서 대화, 대화 종료, 도서관 안내, 대출, 반납, 희망도서 신청
- 관리자 화면: 내 정보, 로그아웃, 기관 정보, 운영 에이전트 대화와 대화 종료, 큐레이션·연체 안내문 틀·구매 요청서의 목록·상세·승인·반려(큐레이션은 내리기도), 희망도서 목록과 닫기, 오늘의 연체 안내 목록

#### Scenario: 서버 경로
- **WHEN** 서버의 경로 목록을 읽으면
- **THEN** `/ui` 아래에는 정적 파일 경로 하나만 있고 API 경로가 없다

#### Scenario: 화면이 부르는 경로
- **WHEN** 화면 스크립트에서 서버에 요청하는 경로를 모두 모으면
- **THEN** 모두 `/auth/login`, `/auth/me`, `/auth/logout`, `/catalog/suggest`, `/catalog/search`, `/catalog/topic`, `/catalog/books/{id}/similar`, `/librarian/messages`, `/librarian/sessions/{id}`, `/library`, `/library/guide`, `/loans`, `/loans/return`, `/book-requests`, `/book-requests/{id}`, `/admin-agent/messages`, `/admin-agent/sessions/{id}`, `/curations`, `/curations/{id}`, `/curations/{id}/approve`, `/curations/{id}/reject`, `/curations/{id}/unpublish`, `/overdue-notice-templates`, `/overdue-notice-templates/{id}`, `/overdue-notice-templates/{id}/approve`, `/overdue-notice-templates/{id}/reject`, `/purchase-requests`, `/purchase-requests/{id}`, `/purchase-requests/{id}/approve`, `/purchase-requests/{id}/reject`, `/overdue-notices/today` 중 하나다

#### Scenario: 부르는 경로가 서버에 있음
- **WHEN** 화면 스크립트가 요청하는 경로와 메서드를 서버의 경로 목록과 맞춰 보면
- **THEN** 모두 서버에 있는 경로와 메서드다

## ADDED Requirements

### Requirement: 이용자 화면의 Enter 갈림
이용자 화면은 입력칸에서 Enter를 누르면(자동완성 후보를 고른 때는 빼고) 먼저 서명·저자 찾기를 SHALL 부른다. 한 권 이상 찾으면 AI 사서 대화를 보내지 않고 두 단계 결과를 보인다. 찾은 책이 없거나, 입력이 서버의 질의 상한(100자)을 넘거나, 찾기가 실패하면(401은 빼고 로그인 화면으로 간다) 지금처럼 같은 글을 AI 사서 대화로 보낸다. 찾기 응답을 기다리는 동안의 Enter는 무시한다.

#### Scenario: 찾은 책이 있음
- **WHEN** 실험 기관 키오스크 화면에서 `채식`을 치고 Enter를 누르면
- **THEN** 두 단계 결과가 보이고 `/librarian/messages` 요청이 없다

#### Scenario: 찾은 책이 없음
- **WHEN** 서명·저자로 걸리는 책이 없는 문장을 치고 Enter를 누르면
- **THEN** 지금처럼 그 문장이 AI 사서 대화로 간다

#### Scenario: 긴 입력
- **WHEN** 100자를 넘는 글을 치고 Enter를 누르면
- **THEN** `/catalog/search` 요청 없이 AI 사서 대화로 간다. 화면의 이 상한은 서버 검색 API의 질의 상한과 같은 값이다

#### Scenario: 찾기 실패
- **WHEN** `/catalog/search`가 401이 아닌 오류로 실패하면
- **THEN** 같은 글이 AI 사서 대화로 간다

#### Scenario: 자동완성 후보 고르기
- **WHEN** 자동완성 후보를 화살표로 고르고 Enter를 누르면
- **THEN** 지금처럼 그 책 카드가 나오고 `/catalog/search`·`/catalog/topic` 요청이 없다

#### Scenario: 찾는 중 Enter
- **WHEN** 찾기 응답이 오기 전에 Enter를 다시 누르면
- **THEN** 두 단계 결과는 하나만 생긴다

### Requirement: 두 단계 결과
두 단계 결과는 위 단 "이 책을 찾으시나요?"(서명·저자 찾기 결과의 앞 2권), 아래 단 "'질의'와 관련된 책"(같은 질의의 주제 검색 결과에서 위 단의 책을 뺀 것), [사서에게 물어보기]로 SHALL 이루어진다. 위 단은 주제 검색을 기다리지 않고 먼저 보인다. 아래 단이 비거나 주제 검색이 실패하면 아래 단을 제목째 숨긴다. 카드는 다른 찾기 결과와 같은 카드다. [사서에게 물어보기]는 같은 글을 AI 사서 대화로 한 번 보내고 꺼진다. 두 단계 결과는 서버 대화 세션을 만들거나 바꾸지 않는다.

#### Scenario: 위 단과 아래 단
- **WHEN** `채식`으로 두 단계 결과가 보이면
- **THEN** 위 단에 채식주의자를 포함한 2권 이하가 있고, 아래 단에는 위 단의 책이 없다

#### Scenario: 위 단 권수
- **WHEN** 화면 스크립트의 위 단 권수를 읽으면
- **THEN** 2다

#### Scenario: 아래 단이 비거나 실패
- **WHEN** 주제 검색 요청이 실패하면
- **THEN** 아래 단과 그 제목이 보이지 않고 위 단과 [사서에게 물어보기]는 남는다

#### Scenario: 사서에게 물어보기
- **WHEN** [사서에게 물어보기]를 누르면
- **THEN** 같은 글이 AI 사서 대화로 한 번 가고 버튼이 꺼져 다시 눌러도 요청이 없다

#### Scenario: 화면 비우기
- **WHEN** 두 단계 결과가 있는 화면을 [새 대화]나 무입력으로 비우면
- **THEN** 두 단계 결과도 지워진다
