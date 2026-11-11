# Proposal

## Why

사서가 없는 작은도서관 이용자는 매일 "화장실 어디예요?", "몇 시까지 해요?", "이거 빌리면 언제까지예요?", "담당자 연락처요", "몇 권까지 빌려요?"를 묻는다. 그런데 답해 줄 사람이 없다. AI 사서도 지금은 이런 질문에 근거가 없다. `libraries`에는 기본 대출 기간만 있고 운영 시간, 휴관일, 연락처, 시설 칸이 없어서, 답하면 지어낸 말이 된다.

`add-catalog-search`로 아는 책 찾기는 코드가 맡게 됐다. 이제 LLM에 남은 일은 자연어로 책을 찾는 대화와 **도서관 안내**다. 이번 change에서 안내의 근거가 되는 데이터를 기관이 등록하게 하고, 날짜 계산은 코드가 하게 한다.

## What Changes

- **도서관 안내 정보**: 기관마다 대표 연락처, 요일별 운영 시간(점심시간처럼 하루에 여러 구간도 된다), 공휴일 휴관 여부, 임시 휴관일, 대출 권수, 반납일이 휴관일일 때의 규칙, 자유 항목(시설 위치, 이용 규칙, 알림)을 둔다. 연락처는 기관 대표 번호만 둔다. 자원봉사자 개인 번호를 넣지 말라고 API 설명과 문서에 적는다.
- **안내 API**
  - `GET /library/guide`: 등록된 안내와 코드가 계산한 오늘·앞으로 7일의 개관 여부, 오늘 빌리면 반납 예정일을 준다. 키오스크도 읽는다. 화면의 "도서관 안내" 칸은 LLM 없이 이 API로 보여 줄 수 있다.
  - `PUT /library/guide`: 관리자가 안내 전체를 한 번에 바꾼다.
  - `GET /library/closures`, `POST /library/closures`, `DELETE /library/closures/{id}`: 임시 휴관일. 관리자만 바꾼다.
- **개관일과 반납 예정일 계산**: 기관 시간대의 오늘에 대출 기간을 더한다. 반납일이 휴관일(정기 휴관, 공휴일 휴관, 임시 휴관)이면 기관 설정에 따라 다음 개관일로 미루거나 그대로 둔다. 공휴일은 오프라인 파이썬 패키지(`holidays`)로 판정한다. 외부 API 호출과 키가 없다.
- **자체 대출의 반납 예정일**: `POST /loans`도 같은 계산을 쓴다. 안내가 말한 날짜와 실제 대출의 날짜가 어긋나지 않게 하기 위해서다. 휴관일 규칙이 없는 기관(안내 미등록)은 지금과 같다.
- **AI 사서 안내 tool** `get_library_guide`: 안내 전체와 계산된 날짜를 한 번에 돌려준다. 입력이 없어서 LLM이 날짜를 정하거나 세지 않는다.
- **책 위치**: 검색·찾기·상세 tool 결과에 서가 위치와 청구기호, 청구기호의 KDC 주류 이름(코드가 정함)을 더한다. LLM이 이를 풀어 말한다. 서가 배치도는 나중이다.
- **프롬프트**: 안내 질문은 `get_library_guide`로 답하고, 결과에 없는 내용은 지어내지 않고 대표 연락처를 안내한다. 날짜와 요일은 결과 값을 그대로 쓴다. 안내가 비어 있는 기관에서도 같은 규칙으로 답한다. 프로필 버전을 올린다.
- **평가**: AI 사서 평가에 안내 시나리오(운영 시간, 휴관일, 반납 예정일, 시설 위치, 대출 권수, 연락처, 등록되지 않은 질문, 빈 안내, 본인 대출 질문, 책 위치)를 더한다. 날짜는 고정하고, 등록되지 않은 시각·날짜·전화번호를 답에 쓰면 규칙 위반으로 센다. 대표 연락처 안내가 "개인정보를 묻는 답"으로 잘못 잡히지 않게 검사를 고친다.
- **시드 데이터**: 자체 대출 기관에는 안내를 채우고, 가져오기 기관은 비워 둔다(처음 쓰는 기관의 모습).

**범위 밖 (이번 change에서 하지 않음)**

- "내 책 언제까지"(본인 대출 조회) → 회원번호가 필요해 `add-librarian-actions`에서 다룬다. 가져오기 기관은 우리 쪽에 대출 기록이 없다
- 대출 권수 상한을 대출 처리에서 강제하기 → 이번에는 안내만 한다. `add-librarian-actions`에서 검토한다
- 서가 배치도, 층별 지도 → 나중
- 안내 화면, 관리자 입력 화면 → `add-web-ui`
- 기관별 시간대. 지금처럼 설정 하나(`LIBRARY_TIMEZONE`)를 쓴다
- 공휴일인데 여는 날(공휴일 휴관 예외) 등록 → 필요하면 따로 다룬다

## Capabilities

### New Capabilities

- `library/library-guide`: 기관 안내 정보(연락처, 운영 시간, 휴관일, 이용 규칙, 자유 항목), 안내 API, 개관일 판정, 반납 예정일 계산

### Modified Capabilities

- `agent/librarian`: 조회 tool에 `get_library_guide`를 더하고 tool 결과에 서가 위치·청구기호를 넣는다. 안내 질문에 등록된 정보로만 답하는 요구사항(평가로 확인)을 더한다
- `circulation/loans`: 대출의 반납 예정일이 휴관일 규칙을 따른다
- `library/staff-auth`: 키오스크가 도서관 안내를 조회할 수 있다
- `platform/database-schema`: 안내 테이블 4개가 더해진다(테이블 15개 → 19개)
- `platform/dev-seed-data`: 자체 대출 기관에 안내 정보를 만든다

## Impact

- **코드**: `app/library/models/guide.py`(새로), `app/library/services/guide.py`(새로: 안내 저장, 개관일 판정, 반납 예정일), `app/library/api/guide.py`(새로), `app/library/schemas/guide.py`(새로), `app/library/services/loans.py`(반납 예정일), `app/library/tools.py`(`get_library_guide`, 서가 위치), `app/library/recommendation/`(KDC 주류 이름), `app/library/librarian.py`(프롬프트, 버전), `app/models.py`, `app/main.py`, `app/seed/`, `migrations/`, `evals/librarian/`, 테스트
- **API**: `GET/PUT /library/guide`, `GET/POST /library/closures`, `DELETE /library/closures/{id}`가 더해진다. 기존 API의 요청·응답은 그대로다. 안내를 등록한 자체 대출 기관에서는 `POST /loans`의 반납 예정일이 휴관일을 건너뛸 수 있다
- **DB**: 새 테이블 4개(`library_guides`, `library_opening_hours`, `library_closures`, `library_guide_entries`). 모두 기관 데이터 테이블이다. 기존 테이블은 바뀌지 않는다. 개발 DB를 백업하고 마이그레이션한다
- **의존성**: `holidays`(한국 공휴일, 오프라인 계산). 외부 호출이 없다
- **외부 호출**: 구현과 테스트에는 없다. 안내 평가를 실제로 돌릴 때만 LLM을 부르고, 돌리기 전에 승인을 받는다(예상 비용은 design에 있다)
- **문서**: CLAUDE.md(현재 단계), `docs/design.md`(이용자 화면, 데이터 모델), `app/library/README.md`, `README.md`
