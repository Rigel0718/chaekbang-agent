## 1. 경계와 계약 (Opus)

- [x] 1.1 `shared/api.js`: `request`에 `form` 갈래, `ApiError`에 `body`, 가져오기 항목 여섯(design 결정 2)
- [x] 1.2 `admin/index.html`에 숨김으로 시작하는 `imports` 탭과 빈 섹션, `admin/main.js`의 `loadLibrary`에서 `loan_mode`를 한 번 읽어 `external`이면 탭을 보이고, 숨긴 탭의 hash는 운영 대화로
- [x] 1.3 `test_web_ui.py`: 경로 허용 목록에 가져오기 넷(화면이 부르는 경로, 서버에 있음), 숨김으로 시작·보이는 조건 테스트를 세 요소에 맞게 고침
- [x] 1.4 `test_holding_imports_api.py`: `HoldingImportRow` 필드 허용 목록, 기증처 있는 파일의 행 응답에 `donor` 없음

## 2. 화면 (Sonnet)

- [x] 2.1 `admin/imports.js` 올리기와 요약, 인식한 열, 필수 열 고르기(결정 3), 서버 문구
- [x] 2.2 확인할 행 목록과 [더 보기]
- [x] 2.3 지난 가져오기 목록, [적용] 조건, 확인 두 단계(결정 4, 5)
- [x] 2.4 `index.html`의 섹션 마크업과 `admin.css`, `main.js`에 `createImports` 연결
- [x] 2.5 `test_web_ui.py`: 화면이 읽는 `record.`·`row.` 필드가 스키마에 있음, 열·표기 이름 표가 서버와 같음, 대량 제적 낱말이 service 문구에 있음

## 3. 견본 파일 (Sonnet)

- [x] 3.1 `scripts/make_import_samples.py`(결정 7)
- [x] 3.2 만든 파일을 `read_table`·`find_header`·`parse_rows`로 읽어 의도한 결과(필수 열 실패, 표기·건너뜀 수)인지 확인

## 4. 문서 (Sonnet)

- [x] 4.1 `app/web/README.md`: 구성에 `imports.js`, 부르는 경로, 탭과 보이는 조건, 가져오기 규칙, 시험

## 5. 검증 (Opus)

- [x] 5.1 `uv run pytest`, `uv run ruff check . && uv run ruff format .`
- [x] 5.2 푸른숲의 `imported` 사본 수를 읽기 전용으로 확인하고 견본 파일을 만들어 B1~B11 안내
- [x] 5.3 사용자 브라우저 확인 B1~B11 결과 반영

## 6. 브라우저 확인에서 더한 것

- [x] 6.1 미리 보기 삭제 service·라우터와 테스트(삭제, 적용한 기록 409, 다른 기관 404, 키오스크 403, 자체 대출 409)
- [x] 6.2 `api.js`의 `importDelete`, 화면의 파일 선택 비우기·[삭제]·상태 색·연 기록 표시
- [x] 6.3 `test_web_ui.py` 경로·삭제 버튼 검사, `app/web/README.md`
- [x] 6.4 `uv run pytest`, `ruff`, 사용자 확인 B12~B14
