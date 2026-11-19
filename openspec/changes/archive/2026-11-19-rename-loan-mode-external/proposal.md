# Proposal

## Why

기관의 운영 방식 값 `loan_mode = imported`가 사본 출처 값 `holdings.source = imported`(파일로 가져온 사본)와 이름이 같아 헷갈린다. 산문의 '가져오기 기관'도 '가져온 사본'과 같은 혼동을 만든다. 다음 change(`add-admin-agent`)에서 운영 방식별 동작을 더 다루기 전에 이름을 나눈다.

## What Changes

- **BREAKING** 운영 방식 값 `imported`를 `external`로 바꾼다. `internal`은 그대로다. 기관 조회·수정 API와 AI 사서 `answer` 사건의 `loan_mode`가 `external`을 돌려주고, 옛 값 `imported`는 받지 않는다.
- 기존 기관 행의 `imported`를 `external`로 바꾸는 마이그레이션을 둔다.
- 스펙과 문서의 한국어 용어 '가져오기 기관'을 '외부 대출 기관'으로 바꾼다. '자체 대출 기관'은 그대로다.
- 사본 출처 `holdings.source`의 `imported`와 '가져온 사본'은 바꾸지 않는다.

## Capabilities

### New Capabilities

없음.

### Modified Capabilities

- `library/libraries`: 운영 방식 값 정의를 `external`/`internal`로 바꾼다.
- `circulation/loans`: 대출·반납 거부 대상을 운영 방식 `external` 기관으로 바꾼다.
- `agent/librarian`: 운영 방식별 안내의 용어와 사건의 운영 방식 값을 바꾼다.
- `catalog/holdings-import`: 가져오기를 쓸 수 있는 기관을 운영 방식 `external`로 바꾼다.
- `catalog/collection-search`: 대출 상태 시각의 대상 용어를 '외부 대출 기관'으로 바꾼다.
- `catalog/book-lookup`: 검색 API 결과 항목의 용어를 바꾼다.
- `platform/dev-seed-data`: 시드 기관의 운영 방식 값과 용어를 바꾼다.

## Impact

- 코드: `LoanMode`와 그 값을 비교하는 service(대출, 장서 가져오기, 도서관 안내, 검색), AI 사서 프롬프트, 시드, 테스트.
- DB: `libraries.loan_mode`의 CHECK 제약과 기존 값을 바꾸는 마이그레이션.
- API: `GET`/`PATCH /library`, AI 사서 `answer` 사건의 `loan_mode` 값. 아직 화면(`add-web-ui`)이 없어 깨지는 클라이언트는 없다.
- 문서: `CLAUDE.md`, `README.md`, `docs/design.md`, `docs/glossary.md`, `app/library/README.md`.
