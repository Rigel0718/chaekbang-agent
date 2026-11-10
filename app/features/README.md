# features

기관 개별 기능이다. 기관 유형에 따라 필요하거나 필요 없는 기능을 둔다. 예를 들어 어린이 구분은 작은도서관에 필요하지만 군부대나 대학 도서관에는 필요 없다.

기능을 등록하지 않아도 `app/library`는 그대로 동작해야 한다.

## 기능 목록

### children

어린이 구분. 어린이 도서는 영유아·초등학생 대상 도서다.

| 파일 | 내용 |
| --- | --- |
| `children/models.py` | `library_book_audiences`, `Audience`, `AudienceSource` |
| `children/rules.py` | 판단 규칙: 별치기호, 자료실, 부가기호, 분류 원문, 어린이 요청 판단 |
| `children/tools.py` | AI 사서에 끼우는 값: `search_children_books`, 어린이 검사, 프롬프트 문구(`children_extension`) |
| `children/checks.py` | 어린이 최종 검사 |
| `children/service.py` | 조회, 지정, 파일 근거, 외부 분류 근거, 갱신 |
| `children/hook.py` | 기관 공통의 사건을 service로 잇는다 |
| `children/api.py` | `/children` 라우터 |
| `children/schemas.py` | Pydantic 스키마 |

**근거의 우선순위**는 `manual`, `import_label`, `external_category`, `default` 순이다.

| 근거 | 정해지는 때 |
| --- | --- |
| `manual` | 관리자가 `PUT /children/books/{id}`로 지정 |
| `import_label` | 파일의 별치기호·자료실·부가기호. 가져오기 적용 때 |
| `external_category` | 공식 서지의 분류 원문이 `국내도서-유아`, `국내도서-어린이`, `국내도서-초등학습서`와 정확히 일치. 등록, 가져오기, ISBN 수정, `POST /children/refresh` 때 |
| `default` | 근거 없음. 저장하지 않고, 행이 없으면 `general`, `default`다 |

- 어린이 구분은 기관의 요청에서만 바뀐다. 운영자의 채움 실행은 바꾸지 않으므로, 채움 뒤에는 기관 관리자가 `POST /children/refresh`를 호출한다.
- 분류 값은 카테고리 이름과 항상 같지 않아서 정확히 일치하는 값만 본다.
- 애매하면 어린이 근거로 보지 않는다. 어린이 요청에 일반 도서가 나가는 쪽이 더 큰 실수다.

**AI 사서의 어린이 요청**

- 판단은 코드가 한다(`rules.is_children_request`). 13세 이하 나이나 어린이 표현이 있으면 어린이 요청이고, 14세 이상·청소년·부모가 읽을 책 표현은 근거로 보지 않는다. 판단은 대화 안에서 유지되고 `제가 읽을` 같은 어른 표현으로 풀린다. 문장 판단이 애매하면 어린이 쪽으로 간다.
- 이번 실행에서 `search_children_books`를 썼어도 어린이 요청이다. LLM의 신호는 켜는 쪽으로만 쓴다.
- 어린이 요청의 답에 그 기관의 어린이 도서가 아닌 책이 있으면 어린이 검사가 답을 막는다. 분류 행이 없는 책은 일반 도서다.
- `app/main.py`에서 `children_extension()`을 빼면 tool, 검사, 프롬프트 문구가 함께 빠지고 AI 사서는 그대로 돈다.

## 규칙

- `app/library`, `app/central`, `app/core`는 import해도 된다. 반대 방향은 안 된다.
- 기능의 저장소는 기능이 소유한다. 공통 테이블에 기능의 열을 더하지 않는다.
- 기관 데이터이므로 `library_id`로 나누고, 다른 기관의 데이터가 보이지 않는 테스트를 함께 둔다.

## 새 기능 추가

1. `app/features/<이름>/`을 만들고 모델, 규칙, service, API를 둔다.
2. 공통의 사건이 필요하면 `app/library/hooks.py`의 `LibraryBookHook`을 구현한다.
3. `app/main.py`에서 `register_hook`과 `include_router`로 조립한다.
4. 모델을 `app/models.py`에 등록하고 `TENANT_TABLES`에 테이블을 추가한다.
5. 테스트는 `tests/features/<이름>/`에 둔다.
6. 기능을 등록하지 않아도 공통 테스트가 통과하는지 확인한다.
