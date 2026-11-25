## MODIFIED Requirements

### Requirement: 가져오기 기록 조회
관리자는 자기 기관의 가져오기 기록을 목록과 단건으로, 행별 결과를 결과·표기로 걸러 SHALL 조회할 수 있다. 다른 기관의 기록은 404다. 행 응답의 필드는 행 번호, 결과, 건너뛴 사유, 표기, 등록번호, 서명, 저자, ISBN, 상태, 입수 구분뿐이고 기증처는 MUST NOT 넣는다.

#### Scenario: 표기된 행만 보기
- **WHEN** `GET /holding-imports/{id}/rows?flag=purchased_without_isbn`을 호출하면
- **THEN** 그 표기가 있는 행만 돌려준다

#### Scenario: 다른 기관의 기록
- **WHEN** 다른 기관의 가져오기 id로 조회하거나 적용하면
- **THEN** 404를 돌려준다

#### Scenario: 행 응답에 기증처 없음
- **WHEN** 기증처가 있는 파일의 행 목록을 조회하면
- **THEN** 행마다 정해진 필드만 있고 기증처는 없다

## ADDED Requirements

### Requirement: 미리 보기 삭제
관리자는 `DELETE /holding-imports/{id}`로 적용 전의 가져오기 기록을 SHALL 지울 수 있다. 지워도 장서는 바뀌지 않는다. 적용한 기록은 409이고 남는다. 권한은 가져오기와 같다(관리자, 외부 대출 기관). 다른 기관의 기록은 404다.

#### Scenario: 미리 보기 지우기
- **WHEN** 미리 보기 기록을 지우면
- **THEN** 204이고 그 기록은 목록과 단건에서 없으며 장서는 그대로다

#### Scenario: 적용한 기록
- **WHEN** 적용한 기록을 지우려 하면
- **THEN** 409를 돌려주고 기록이 남는다

#### Scenario: 다른 기관과 권한
- **WHEN** 다른 기관의 기록, 키오스크, 자체 대출 기관으로 지우려 하면
- **THEN** 각각 404, 403, 409이고 기록이 남는다
