# Spec Delta

## Purpose

서버 접속 기록에 남는 값을 정해, 요청 주소에 실린 회원 이름과 이용자 검색어 같은 질의 문자열이 기록에 남지 않게 한다.

## ADDED Requirements

### Requirement: 접속 기록에서 질의 문자열 지우기
서버 접속 기록은 요청 주소의 경로만 MUST 남기고 `?` 뒤의 질의 문자열을 남기지 않는다. 메서드, 경로, 응답 코드는 지금처럼 남긴다. 관리자 회원 찾기(`/members?q=`)의 이름과 이용자 화면의 검색어(`/catalog/search?q=`, `/catalog/suggest?q=`, `/catalog/topic?q=`)가 기록에 남지 않게 하기 위해서다. 이 규칙은 앱을 불러오기만 하면 적용되고, 실행 명령에 따로 설정을 주지 않아도 된다.

#### Scenario: 회원 찾기 주소
- **WHEN** 접속 기록이 `GET /members?q=김하늘` 요청을 응답 코드 200으로 기록하면
- **THEN** 기록 문장에 `GET /members`와 `200`이 있고 `김하늘`과 `q=`는 없다

#### Scenario: 질의 문자열이 없는 주소
- **WHEN** 접속 기록이 `GET /holdings` 요청을 기록하면
- **THEN** 기록 문장의 경로는 `/holdings` 그대로다

#### Scenario: 앱을 불러오면 적용됨
- **WHEN** 앱 모듈을 불러온 뒤 접속 기록 로거를 보면
- **THEN** 질의 문자열을 지우는 필터가 한 번만 붙어 있다
