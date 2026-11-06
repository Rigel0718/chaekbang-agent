# Design

## Context

**지금 코드에 있는 것** (`add-library-core-domain`)
- `holdings`에 `source`(manual/imported), `last_synced_at`이 이미 있다. 쓰는 곳은 아직 없다.
- `books`는 기관 공통이고 내부 id로 식별하며 ISBN은 UNIQUE(비어 있어도 됨)다.
- `holdings`의 CHECK `acquisition_fields`가 "매입은 구입가 필수"를 강제한다.
- `app/core/isbn.py`는 13자리만 검증한다. ISBN-10 변환은 없다.
- `app/services/books.py`의 `_with_counts`가 소장·대출 가능 권수를 센다.
- 파일 업로드 의존성(`python-multipart`)과 `openpyxl`은 없다.

**제약**
- 실제 내보내기 샘플이 없다. 도서관마다 비슷하므로 필수 열 중심으로 인식하고, 가상 파일로 검증한다.

## Goals / Non-Goals

**Goals:**
- 파일 읽기·머리글 인식·정규화·분류를 DB 없는 순수 함수로 두어 표 형태로 테스트한다.
- service 함수는 HTTP를 모르게 두어, 5주차 `import_holdings` tool이 그대로 쓰게 한다.
- 파일을 잘못 올려도 미리 보기 단계에서 알아챌 수 있게 한다.

**Non-Goals:**
- 백그라운드 작업 큐. 파일 처리는 요청 안에서 끝낸다.
- 외부 API 호출. 이번 change는 네트워크를 쓰지 않는다. 서지정보 채움은 `add-book-enrichment`에서 한다.
- 적용 되돌리기(rollback API). 잘못 적용하면 올바른 파일을 다시 적용한다. 제적이 복구되는 이유다.
- 직접 등록 규칙 변경. 직접 등록의 매입 사본은 지금처럼 구입가와 ISBN이 필수다.

## Decisions

### 1. 모듈 구성

```
app/importing/
├── reader.py      # xlsx·CSV → 행 목록 (인코딩, 첫 시트, 크기 제한)
├── columns.py     # 표준 열 정의, 머리글 동의어, 머리글 행 찾기, 열 매핑
├── normalize.py   # ISBN(하이픈, ISBN-10, 숫자 셀), 공백 정리, 정수 가격, 상태·입수 구분 표기 변환
├── classify.py    # 어린이 근거 판단 (별치기호, 자료실, 부가기호, 외부 분류)
└── rows.py        # 표준 행 하나 → ParsedRow (값, 건너뜀 사유, 표기)
app/services/holding_imports.py   # 미리 보기, 적용, 기록 조회
app/api/holding_imports.py
evals/holdings_import/            # 가상 파일 생성과 지표 계산
```

`CLAUDE.md`의 `importing/` 위치를 따른다. `importing/`은 DB와 HTTP를 모른다.

### 2. 필수 열 중심 인식

표준 열은 필수 3개(`accession_number`, `title`, `author`)와 선택 열(`isbn`, `publisher`, `published_year`, `call_number`, `separate_mark`(별치기호), `shelf_location`(자료실), `status`, `acquisition`, `price`, `donor`, `kdc`, `addition_code`(부가기호))다.

- 머리글은 공백·괄호·대소문자를 없앤 뒤 동의어 표와 **완전히 일치**할 때만 인식한다. 부분 일치는 쓰지 않는다. `대출자`가 `대출상태`로 잘못 잡히는 일을 막기 위해서다.
- 동의어 예: 등록번호(`등록번호`, `자료번호`, `바코드`), 서명(`서명`, `도서명`, `자료명`, `제목`), 저자(`저자`, `지은이`, `저자명`, `저작자`).
- 머리글 행: 앞 20행 중 필수 열을 가장 많이 찾은 첫 행을 쓴다.
- 인식하지 못한 열은 읽은 뒤 버린다. 저장되는 것은 표준 열의 값뿐이다.
- **대안: LLM으로 열 매핑** → 도서관별 표기가 거의 비슷하고, 설계 원칙 7이 결정적 코드를 요구한다. 못 찾으면 관리자가 직접 지정한다.

### 3. 미리 보기 → 적용 (2단계)

대량 쓰기이고 제적까지 일어나므로 바로 적용하지 않는다. 승인 흐름(6주차)의 대상은 아니다. 관리자 자신의 작업이고 초안 검토자가 따로 없기 때문이다.

- `POST /holding-imports`: multipart(`file`, 선택 `column_mapping` JSON). 파일을 읽고 행을 정규화해 `holding_imports.rows`에 저장한다.
- 원본 파일은 저장하지 않는다. 인식하지 못한 열이 남지 않게 하기 위해서다.
- `POST /holding-imports/{id}/apply`: 기관 행을 `FOR UPDATE`로 잠그고, 저장된 행을 **현재 DB와 다시 비교해** 적용한다. 미리 보기 뒤에 장서가 바뀌어도 어긋나지 않는다. 한 트랜잭션이다.

### 4. 테이블과 제약

| 대상 | 변경 |
| --- | --- |
| holding_imports (새, 기관) | id, library_id, staff_user_id, filename, status(preview/applied), column_mapping JSONB, rows JSONB, summary JSONB, applied_at?; UNIQUE(library_id, id); 복합 FK (library_id, staff_user_id) |
| holdings.status | + `withdrawn` |
| holdings.acquisition_type | + `unknown` |
| books.audience_source | + `import_label` |

`acquisition_fields` CHECK는 다음으로 바꾼다.

```sql
(acquisition_type = 'purchased' AND donor IS NULL
   AND (purchase_price IS NOT NULL OR source = 'imported'))
OR (acquisition_type = 'donated' AND purchase_price IS NULL)
OR (acquisition_type = 'unknown' AND purchase_price IS NULL AND donor IS NULL)
```

- 기존 행은 새 CHECK를 모두 만족한다.
- enum CHECK는 autogenerate가 찾지 못하므로 마이그레이션을 손으로 쓴다 (`DROP CONSTRAINT` 후 다시 만들기). 같은 이유로 `alembic check`로는 확인되지 않아, 시나리오 테스트로 확인한다.
- `holding_imports`는 `TENANT_TABLES`에 넣는다.
- `rows`를 JSONB 한 칸에 둔다. 행별 조회는 응답 페이지네이션을 코드에서 한다. 작은도서관 장서는 수천~수만 권이고, 파일 상한은 20MB·5만 행이다.

### 5. "빠진 정보"와 표기의 구분

| 표기 | 어디에 | 언제 사라지나 |
| --- | --- | --- |
| 행 표기 `flags` (`invalid_isbn`, `purchased_without_isbn`, `purchased_without_price`, `unknown_status`) | 가져오기 기록 | 기록이라 남는다 |
| 사본 `missing_fields` (`isbn`, `purchase_price`) | 조회할 때 계산 | 정보를 채우면 바로 |

- `missing_fields`는 저장하지 않는다. 컬럼으로 두면 ISBN을 채울 때 여러 기관의 사본을 함께 고쳐야 한다.
- `GET /holdings?incomplete=true`는 `purchased AND (purchase_price IS NULL OR book.isbn IS NULL)` 조건이다.
- 매입 사본이 있는 도서의 ISBN을 비울 수 없는 기존 규칙은 그대로 둔다.

### 6. 제적과 대량 제적 확인

- 대상: 그 기관의 `source = imported`이고 `withdrawn`이 아니며 파일에 없는 사본.
- 삭제 대신 상태를 쓴다. 파일 실수를 다시 적용으로 복구할 수 있고, 추천·대출에서는 빠진다.
- 빠진 수가 비교 대상의 절반 이상이면 `confirm_withdraw` 없이 409다. 첫 가져오기는 비교 대상이 없어 해당 없다.
- 제적을 반영하는 곳: `_with_counts`, `held` 필터, 사본 목록 기본값. 대출은 `available`만 받으므로 그대로다.
- `internal` 기관은 가져오기를 막는다. 파일과 자체 대출 기록이 충돌하고, 대출 중 사본이 제적될 수 있기 때문이다.

### 7. 어린이 분류

`classify.py`의 판단은 표 기반의 순수 함수다. 외부 분류 근거는 `add-book-enrichment`가 같은 파일에 더한다.

- 별치기호: 공백을 없앤 값이 `아`, `아동`, `어`, `어린이`, `유`, `유아`, `J`, `C` 중 하나이면 근거다 (완전 일치).
- 자료실: `어린이`, `아동`, `유아`를 포함하면 근거다.
- 부가기호: 5자리이고 첫 자리가 7이면 근거다 (독자대상기호 아동).
- 근거 우선순위는 `AudienceSource` 순서 표 하나로 판단한다.
- 불확실하면 일반 도서로 둔다 (설계 원칙 4). 근거가 없는 행은 값을 내리지 않으므로, 한 기관이 어린이로 분류한 책을 다른 기관의 파일이 일반으로 되돌리지 않는다.

### 8. 평가

`evals/holdings_import/`에서 열 구성이 다른 가상 파일 4개를 정답과 함께 코드로 만든다 (xlsx, UTF-8 CSV, CP949 CSV, 필수 열만 있는 파일). `uv run python -m evals.holdings_import`가 파일별 ISBN 인식률, 어린이 분류 정밀도·재현율, 표기 비율을 표로 출력한다. DB 없이 `importing/`만 돈다. 어린이 분류는 정밀도 1.0(일반 도서를 어린이로 잘못 분류 0건)을 기준으로 본다.

## Risks / Trade-offs

- **[실제 내보내기와 머리글이 다를 수 있음]** → 인식 실패가 422로 바로 드러나고 열 직접 지정으로 넘어갈 수 있다. 동의어는 표 한 곳이라 추가가 쉽다.
- **[도서가 기관 공통이라 한 기관의 파일이 어린이 구분을 바꿈]** → 일반에서 어린이로만 바뀌고, 관리자 지정이 우선한다. 기관별 값은 범위 밖으로 둔다. 어린이 요청에 일반 도서가 섞일 위험이 남으므로 별치기호를 완전 일치로 좁혔다.
- **[ISBN 없는 책의 중복]** → 공백만 정리한 서명·저자 일치로 찾는다. 표기가 조금 다르면 새 도서가 생긴다. 권차·판본 정규화 때 다시 본다.
- **[요청 안에서 큰 파일 처리]** → 상한(20MB, 5만 행)을 두고, 넘으면 422다. 느리면 그때 작업 큐를 검토한다.
- **[가격 열이 정가일 수 있음]** → 내보내기의 가격은 구입가가 아닌 정가인 경우가 있다. `purchased` 사본의 구입가로만 쓰고 그 외에는 버린다. 정확도보다 "빠진 정보 표기 감소"를 택했다.

## Migration Plan

- 새 리비전 하나. 기존 데이터 이전은 없다. `downgrade`는 `withdrawn`·`unknown` 행이 있으면 CHECK를 되돌릴 수 없으므로, 그 행을 `lost`·`donated`로 바꾼 뒤 제약을 되돌린다.
