# Spec Delta

## ADDED Requirements

### Requirement: 기관 개별 기능 없는 AI 사서
AI 사서는 어린이 기능을 등록하지 않아도 MUST 동작한다. 그때 프로필의 tool, 최종 검사, 프롬프트에 어린이 기능의 내용이 없다. 공통 코드는 어린이 기능을 이름으로 부르지 않고, 조립할 때 기능의 tool, 검사, 프롬프트 문구를 받는다.

#### Scenario: 기능 없는 프로필
- **WHEN** 어린이 기능 없이 AI 사서 프로필을 만들면
- **THEN** 어린이 도서 검색 tool과 어린이 검사가 없고 프롬프트에 어린이 문구가 없다

#### Scenario: 기능 없이 대화
- **WHEN** 어린이 기능 없는 프로필로 `7살 공룡 책`을 요청해 일반 도서를 답하면
- **THEN** 그 답이 그대로 나가고 library_book_audiences는 조회되지 않는다

#### Scenario: 서버 조립
- **WHEN** 서버를 시작하면
- **THEN** AI 사서 프로필에 어린이 도서 검색 tool과 어린이 검사가 있다
