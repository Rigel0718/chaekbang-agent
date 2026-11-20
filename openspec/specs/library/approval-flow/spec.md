# library/approval-flow Specification

## Purpose
큐레이션 게시처럼 이용자에게 나가거나 기관 기록을 확정하는 작업이 사람의 승인을 거치게 한다. 승인 대기는 DB에 저장해 서버가 다시 시작돼도 이어지고, 확정 작업마다 같은 상태와 전이 규칙을 쓴다.

## Requirements

### Requirement: 승인 상태
확정 작업의 초안은 상태 하나를 MUST 가진다. 값은 `draft`, `pending_approval`, `approved`, `published`, `confirmed`, `archived`이고 그 밖의 값은 데이터베이스가 거부한다. 게시하는 종류(큐레이션)는 `published`, 확정하는 종류는 `confirmed`를 실행 상태로 쓴다. 상태는 초안 행에 저장하고 서버 메모리에 두지 않는다.

#### Scenario: 허용되지 않은 상태 저장
- **WHEN** 초안 행에 상태 `rejected`를 직접 저장하려 하면
- **THEN** 데이터베이스가 저장을 거부한다

### Requirement: 상태 전이
초안의 상태는 정해진 전이로만 SHALL 바뀐다. 제출은 `draft` → `pending_approval`, 승인은 `pending_approval` → `approved` → 실행 상태, 반려는 `pending_approval` → `draft`, 내리기는 `published` → `archived`다. 내용 수정과 삭제는 `draft`에서만 된다. 그 밖의 전이 요청은 409를 돌려주고 초안은 바뀌지 않는다.

#### Scenario: 제출
- **WHEN** 관리자가 `draft` 초안을 제출하면
- **THEN** 상태는 `pending_approval`이다

#### Scenario: 반려
- **WHEN** 관리자가 `pending_approval` 초안을 사유와 함께 반려하면
- **THEN** 상태는 `draft`이고 반려 사유가 초안에 남는다

#### Scenario: 초안을 바로 승인
- **WHEN** `draft` 초안을 승인하려 하면
- **THEN** 409를 돌려주고 상태는 `draft`다

#### Scenario: 승인 대기 중 수정
- **WHEN** `pending_approval` 초안의 내용을 고치거나 지우려 하면
- **THEN** 409를 돌려주고 내용은 그대로다

#### Scenario: 게시본이 아닌 것을 내리기
- **WHEN** `pending_approval` 초안을 내리려 하면
- **THEN** 409를 돌려준다

### Requirement: 승인과 실행
승인은 승인 상태를 남기고 그 종류의 실행을 한 트랜잭션에서 SHALL 마친다. 승인자 직원과 승인 시각, 실행 시각을 초안에 남긴다. 실행이 실패하면 승인도 남지 않고 초안은 `pending_approval`으로 있다.

#### Scenario: 승인 기록
- **WHEN** 관리자가 `pending_approval` 큐레이션을 승인하면
- **THEN** 상태는 `published`이고 승인자, 승인 시각, 게시 시각이 있다

### Requirement: 동시 승인
같은 초안에 대한 승인·반려 요청이 겹치면 하나만 MUST 반영된다. 먼저 반영된 요청 뒤의 요청은 상태가 맞지 않아 409를 돌려준다.

#### Scenario: 두 번 승인
- **WHEN** 같은 `pending_approval` 초안에 승인을 두 번 보내면
- **THEN** 첫 번째는 성공하고 두 번째는 409이며 승인자와 시각은 첫 번째 값이다

### Requirement: 승인 권한
제출, 승인, 반려, 내리기, 초안 만들기·고치기·지우기는 관리자 토큰으로만 SHALL 된다. 키오스크 토큰은 403, 토큰이 없으면 401이다. 초안을 만든 관리자가 직접 승인해도 된다.

#### Scenario: 키오스크의 승인
- **WHEN** 키오스크 토큰으로 승인을 요청하면
- **THEN** 403을 돌려주고 상태는 바뀌지 않는다

#### Scenario: 토큰 없이 승인
- **WHEN** 토큰 없이 승인을 요청하면
- **THEN** 401을 돌려준다

### Requirement: 승인의 기관 분리
초안의 조회와 전이는 토큰의 기관 범위 안에서만 MUST 된다. 다른 기관의 초안은 없는 것과 같이 404이고, 목록에 나오지 않는다. 요청 본문의 기관 값은 받지 않는다.

#### Scenario: 다른 기관의 초안 승인
- **WHEN** A 기관 관리자가 B 기관의 `pending_approval` 초안을 승인하려 하면
- **THEN** 404를 돌려주고 B 기관 초안은 그대로다

#### Scenario: 다른 기관의 초안 목록
- **WHEN** A 기관과 B 기관에 초안이 있을 때 A 기관 관리자가 목록을 보면
- **THEN** A 기관 초안만 있다

### Requirement: 재시작 뒤 이어짐
승인 대기 초안은 서버가 다시 시작돼도 SHALL 이어진다. 승인은 초안을 만든 에이전트 실행이나 서버 프로세스와 상관없이 DB의 상태만으로 된다.

#### Scenario: 새 연결에서 승인
- **WHEN** 승인 대기 큐레이션을 커밋하고 DB 연결을 모두 닫은 뒤 새 연결로 띄운 앱에서 승인하면
- **THEN** 상태는 `published`이고 게시본 읽기에 그 큐레이션이 나온다
