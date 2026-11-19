## MODIFIED Requirements

### Requirement: 검색 API
직원 토큰으로 `GET /catalog/search?q=`와 `GET /catalog/suggest?q=`를 SHALL 쓸 수 있다. 키오스크 계정도 쓸 수 있다. 기관은 토큰으로 정한다. 질의는 1자 이상 100자 이하다. 찾기 결과의 항목은 기관 도서 id, 서명, 저자, 출판사, 대출 가능 권수, 대출 중 권수, 서가 위치, 청구기호, 표지 URL과 출처, 상품 링크, 외부 대출 기관의 갱신 시각이고 추천 이유는 없다. 자동완성 항목은 기관 도서 id, 서명, 저자다.

#### Scenario: 키오스크 검색
- **WHEN** 키오스크 토큰으로 `GET /catalog/search?q=데미안`을 호출하면
- **THEN** 200과 찾기 결과를 돌려준다

#### Scenario: 토큰 없음
- **WHEN** 토큰 없이 `GET /catalog/suggest?q=데`를 호출하면
- **THEN** 401을 돌려준다

#### Scenario: 빈 질의
- **WHEN** `q`가 비어 있거나 100자를 넘으면
- **THEN** 422를 돌려준다

#### Scenario: 요청의 기관 값 무시
- **WHEN** A 기관 토큰으로 `library_id`에 B 기관 id를 붙여 호출하면
- **THEN** A 기관의 책만 나온다
