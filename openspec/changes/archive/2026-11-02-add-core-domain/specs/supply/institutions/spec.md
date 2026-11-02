# Spec Delta

## Purpose

책방의 주 수입원인 기관 납품의 거래처(학교, 어린이집, 동사무소, 군 서점 등) 정보를 관리해, 이후 도서 목록 업로드와 견적서 작성이 기관 단위로 이루어질 수 있게 한다.

## ADDED Requirements

### Requirement: 기관 등록
시스템은 기관명, 기관 유형, 담당자명, 연락처(전화·이메일), 주소, 메모로 기관을 등록 SHALL 한다. 기관명과 유형은 필수다. 유형은 `school`, `daycare`, `community_center`, `military`, `other` 중 하나다.

#### Scenario: 정상 등록
- **WHEN** 기관명 "햇살어린이집", 유형 `daycare`로 `POST /institutions`를 호출하면
- **THEN** 시스템은 201과 함께 id가 부여된 기관 정보를 반환한다

#### Scenario: 허용되지 않은 유형
- **WHEN** 유형 `hospital`로 `POST /institutions`를 호출하면
- **THEN** 시스템은 422를 반환한다

#### Scenario: 기관명 누락
- **WHEN** 기관명이 빈 문자열이거나 빠진 요청으로 `POST /institutions`를 호출하면
- **THEN** 시스템은 422를 반환한다

### Requirement: 기관 조회
시스템은 id로 기관 단건을 조회하고, 페이지 단위로 기관 목록을 조회할 수 있게 SHALL 한다. 목록은 `type`으로 유형별 필터를 지원한다.

#### Scenario: 단건 조회
- **WHEN** 존재하는 id로 `GET /institutions/{id}`를 호출하면
- **THEN** 시스템은 200과 기관 정보를 반환한다

#### Scenario: 없는 기관 조회
- **WHEN** 존재하지 않는 id로 `GET /institutions/{id}`를 호출하면
- **THEN** 시스템은 404를 반환한다

#### Scenario: 유형 필터
- **WHEN** 학교 1곳과 어린이집 2곳이 있는 상태에서 `GET /institutions?type=daycare`를 호출하면
- **THEN** 시스템은 어린이집 2곳만 반환한다

### Requirement: 기관 수정
시스템은 기관 정보를 부분 수정할 수 있게 SHALL 한다.

#### Scenario: 담당자 변경
- **WHEN** `PATCH /institutions/{id}`에 담당자명만 담아 호출하면
- **THEN** 시스템은 담당자명만 바꾸고 나머지 필드는 그대로 둔다

### Requirement: 기관 삭제
시스템은 기관을 삭제할 수 있게 SHALL 한다. 단, 납품 주문 목록이나 견적서가 참조하는 기관은 삭제를 거부 MUST 한다.

#### Scenario: 참조 없는 기관 삭제
- **WHEN** 주문 목록이 없는 기관에 `DELETE /institutions/{id}`를 호출하면
- **THEN** 시스템은 204를 반환하고 이후 조회 시 404가 된다

#### Scenario: 주문 목록이 있는 기관 삭제
- **WHEN** institution_orders에 연결된 기관에 `DELETE /institutions/{id}`를 호출하면
- **THEN** 시스템은 409를 반환하고 기관을 삭제하지 않는다
