# Proposal

## Why

서비스의 기본 경로는 기관이 이미 쓰는 대출 프로그램의 장서를 가져오는 것인데, 지금은 사본을 한 권씩 등록하는 API만 있다. 담당자가 같은 정보를 두 번 입력하지 않도록 엑셀·CSV 내보내기로 장서를 채우고 갱신해야, 3주차 AI 사서가 실제 장서와 어린이 도서 구분 위에서 추천할 수 있다.

## What Changes

- **장서 가져오기(미리 보기 → 적용)**
  - 관리자가 엑셀(xlsx)·CSV를 올리면 결과를 먼저 보여 주고, 확인한 뒤 적용한다.
  - 가져오기 기관(`loan_mode = imported`)만 쓸 수 있다.
  - 가져오기 기록(파일, 열 매핑, 건수, 행별 결과)을 남긴다.
- **필수 열 중심 인식**
  - 필수 열은 등록번호, 서명, 저자 세 가지다. 머리글 이름이 달라도 흔한 표기를 인식한다.
  - 나머지 열(ISBN, 출판사, 청구기호, 별치기호, 자료실, 대출 상태, 수입구분, 가격, 기증처, 분류기호, 부가기호)은 있으면 쓰고 없으면 넘어간다.
  - 인식하지 못한 열은 저장하지 않는다. 대출자 이름 같은 개인정보가 들어오지 않게 하기 위해서다.
- **ISBN 정규화**: 하이픈, ISBN-10, 엑셀 숫자 셀을 13자리로 바꾼다. 잘못된 ISBN은 행을 버리지 않고 ISBN 없이 가져오며 표기한다.
- **다시 가져오기**: 바뀐 것만 반영한다. 파일에서 빠진 사본은 **제적(`withdrawn`)** 상태로 바꾼다. 다시 나타나면 복구한다.
- **입수 구분 `unknown` 추가**
  - 파일에 입수 구분이 없으면 `unknown`으로 둔다.
  - 기증처가 없는 기증 사본은 정상이다.
  - 매입 사본인데 ISBN이나 구입가가 없어도 오류로 막지 않고 가져온 뒤 "빠진 정보"로 표기한다. 이 규칙은 가져온 사본에만 적용하고, 직접 등록은 지금처럼 필수다.
- **어린이 도서 분류**: 코드로 별치기호·자료실·부가기호를 보고 분류한다. 근거 `import_label`을 추가하고, 관리자 지정이 가장 우선한다.
- **가져오기 평가**: 열 구성이 다른 가상 내보내기 파일로 ISBN 인식률, 어린이 분류 정확도, 빠진 정보 표기 비율을 잰다.

**범위 밖 (이번 change에서 하지 않음)**

- 외부 API 서지정보 채움과 외부 분류 근거 → `add-book-enrichment` (YES24)
- 대출 프로그램과의 실시간 연동, 예전 `.xls` 형식
- 권차·판본 정규화, LLM을 쓰는 애매한 매칭 판단
- 에이전트의 `import_holdings` tool (5주차가 이번 service를 쓴다)
- 기관별 어린이 구분 값 (도서는 기관 공통이다)

## Capabilities

### New Capabilities

- `catalog/holdings-import`: 파일 인식, 미리 보기와 적용, 다시 가져오기, 제적 처리, 가져오기 기록, 어린이 분류 근거 추출

### Modified Capabilities

- `catalog/holdings`: 상태 `withdrawn`, 입수 구분 `unknown`, 가져온 사본의 빠진 정보 표기, 조회 시 제적 사본 제외
- `catalog/books`: 소장 권수에서 제적 사본 제외, 대상 구분 근거와 우선순위
- `platform/database-schema`: 테이블 8개 (`holding_imports` 추가)

## Impact

- **새 코드**: `app/importing/`(파일 읽기, 머리글 인식, 정규화, 분류), `app/services/holding_imports.py`, `app/api/holding_imports.py`, `evals/holdings_import/`
- **바뀌는 코드**: 사본·도서 모델과 service, 사본 입수 규칙
- **새 API**: `POST·GET /holding-imports`, `GET /holding-imports/{id}`, `GET /holding-imports/{id}/rows`, `POST /holding-imports/{id}/apply`
- **마이그레이션**: `holding_imports` 테이블, CHECK 제약 변경. 기존 데이터는 그대로 유효하다.
- **의존성**: `openpyxl`, `python-multipart` 추가.
- **문서**: `CLAUDE.md`(현재 단계, 입수 구분 용어), `README.md`, `docs/design.md`
