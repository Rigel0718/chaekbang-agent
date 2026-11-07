# Proposal

## Why

코드가 `api`, `services`, `models`처럼 기술 기준으로만 나뉘어 있어 층의 경계가 보이지 않는다. 그래서 `add-book-enrichment`에서 파일 위치는 나눴는데 운영자 실행이 기관의 어린이 구분을 바꾸는 일이 있었다. 어린이 구분은 군부대·대학처럼 필요 없는 기관도 있는 기능인데 공통 테이블과 공통 API에 들어 있다. AI 사서 코드가 쌓이기 전에 경계를 패키지로 만들고 테스트로 지킨다.

## What Changes

- **세 층 패키지**
  - `app/central/`: 운영자 층. 공식 서지, 외부 연동, 서지 채움
  - `app/library/`: 기관 공통. 기관·직원, 기관 도서, 사본, 회원, 대출, 가져오기
  - `app/features/children/`: 기관 개별. 어린이 구분 전체
- **의존 방향**: `features → library → central → core`. 거꾸로 된 import는 테스트가 막는다. `app/main.py`, `app/seed/`, `scripts/`, `evals/`는 층을 조립하는 곳이라 모두 import할 수 있다.
- **운영자 실행 분리**: `central`은 기관 모델을 모른다. 대상 ISBN 조회와 연결 처리는 `central`이 정의한 접점을 `library`가 구현하고, 스크립트가 잇는다.
- **어린이 기능 완전 분리**
  - **BREAKING** `library_books.audience`, `audience_source`를 새 테이블 `library_book_audiences`로 옮긴다. 근거가 있는 도서만 행이 있다.
  - **BREAKING** 공통 API에서 어린이 구분을 뺀다. `/library-books`의 `audience` 입력·응답·필터가 사라진다.
  - **BREAKING** 어린이 API를 `/children`으로 옮긴다. `POST /library-books/audience/refresh`는 `POST /children/refresh`가 된다.
  - 공통 코드는 어린이를 모른다. 연결 변경과 파일 행 적용을 훅으로 알리고, 어린이 기능이 훅을 등록한다.
  - 가져오기는 별치기호·부가기호를 파일 값으로만 넘기고 판단하지 않는다.

어린이 판단 규칙, 우선순위, 처리 결과는 바뀌지 않는다. 바뀌는 것은 저장 위치와 API 경로다.

**범위 밖 (이번 change에서 하지 않음)**

- 기관별로 어린이 기능을 켜고 끄는 설정. 이번에는 기능을 등록하지 않아도 공통이 동작하는지까지 확인한다
- 어린이 외의 기관 개별 기능
- 판단 규칙 변경, 새 API 기능
- 저자 구조화, 에이전트

## Capabilities

### New Capabilities

- `features/children`: 어린이 구분과 근거, 조회·지정·목록·갱신, 파일 근거, 외부 분류 근거
- `platform/package-layers`: 패키지 의존 방향과, 기관 개별 기능 없이 공통이 동작한다는 경계

### Modified Capabilities

- `catalog/library-books`: 어린이 구분 요구사항을 `features/children`으로 옮기고 조회·수정에서 대상 구분을 뺌
- `catalog/holdings-import`: 어린이 도서 분류 근거를 `features/children`으로 옮김
- `library/staff-auth`: 키오스크가 어린이 구분을 조회할 수 있음을 명시
- `platform/database-schema`: 테이블 10개, 기관 간 참조 금지에 어린이 구분 추가
- `platform/dev-seed-data`: 어린이 도서 시드의 저장 위치 변경

## Impact

- **코드**: `app/` 전체의 위치와 import 경로. `app/api`, `app/services`, `app/models`, `app/schemas`, `app/importing`, `app/external`이 사라지고 세 층 아래로 옮겨진다.
- **API**: `/library-books`의 `audience` 관련 입력·응답·필터 제거, `/children` 추가, 갱신 경로 변경. 그 밖의 경로와 응답은 그대로다.
- **마이그레이션**: `library_book_audiences` 생성, 기존 값 이동, 열 삭제. `default` 근거는 행을 만들지 않는다.
- **테스트**: import 경로 수정, 어린이 테스트를 `tests/features/children/`로 이동, 의존 방향 테스트 추가
- **의존성**: 추가 없음
- **문서**: `CLAUDE.md`(디렉터리 구조, 설계 원칙, change 순서), `README.md`, `docs/design.md`
