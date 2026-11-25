## Why

외부 대출 기관은 기존 대출 프로그램의 파일을 가져와야 장서가 생기는데, 지금은 Swagger로만 할 수 있어 담당자가 직접 쓸 수 없다. 가져오기 REST(`/holding-imports`)는 이미 다 있으므로 관리자 화면에 탭 하나를 더하면 된다. 24b `add-admin-analytics-ui`를 둘로 나눈 앞쪽(24f)이다(2026-11-25 탐색).

## What Changes

- 관리자 화면에 [장서 가져오기] 탭을 더한다. 외부 대출 기관(`loan_mode = external`)만 보이고, 기관 정보를 읽지 못하면 숨긴다.
- 파일 올리기 → 미리 보기 요약(행 수, 파일에서 빠진 사본 수, 인식한 열) → 확인할 행(건너뜀과 표기 넷) → [적용].
- 필수 열을 찾지 못하면 파일 머리글에서 열을 골라 다시 올린다.
- [적용]은 가장 최근의 미리 보기에만 있고, 대량 제적이면 한 번 더 확인한다.
- 지난 가져오기 목록을 보이고, 탭에 들어올 때마다 다시 읽는다. 적용한 기록과 미리 보기는 색으로 나누고 연 기록을 표시한다.
- 올려서 미리 보기가 생기면 파일 선택을 비운다.
- 적용 전 미리 보기를 지우는 API(`DELETE /holding-imports/{id}`)와 [삭제] 버튼을 더한다(2026-11-25 브라우저 확인에서 더함).
- 확인용 견본 파일을 만드는 `scripts/make_import_samples.py`를 더한다.
- 서버 변경은 미리 보기 삭제 하나뿐이다. 스키마·에이전트 변경 없음. LLM·외부 API 호출 없음.

하지 않는 것: 분석 표·차트와 초안 링크(24b), 선택 열 고치기, 자체 대출 기관의 책 등록·사본 상태 처리·회원 탭(따로 change).

## Capabilities

### New Capabilities

없음.

### Modified Capabilities

- `platform/web-ui`: 관리자 화면이 부르는 경로에 장서 가져오기를 더하고, 탭이 다섯이 되며(가져오기는 외부 대출 기관만), 장서 가져오기 화면 요구사항을 더한다.
- `catalog/holdings-import`: 행 목록 응답에 기증처가 없다는 것을 요구사항으로 적고(지금 동작 그대로), 미리 보기 삭제를 더한다.

## Impact

- 화면: `app/web/public/admin/`(`index.html`, `main.js`, `admin.css`, 새 `imports.js`), `app/web/public/shared/api.js`(파일 올리기, 422의 `missing`·`headers` 전달), `app/web/README.md`
- 테스트: `tests/platform/test_web_ui.py`, `tests/catalog/test_holding_imports_api.py`
- 스크립트: `scripts/make_import_samples.py`
- 서버: `app/library/api/holding_imports.py`, `app/library/services/holding_imports.py`에 삭제. DB 스키마, 의존성 변경 없음
