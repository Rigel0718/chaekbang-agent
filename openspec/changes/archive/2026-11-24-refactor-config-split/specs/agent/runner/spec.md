# Spec Delta

## MODIFIED Requirements

### Requirement: LLM 설정
모델, 생각 수준, 출력 길이, 호출 제한 시간은 설정에서 SHALL 읽고 API 키는 `.env`에서만 읽는다. 키가 없어도 서버는 시작하고, 키가 없을 때 실행하면 LLM 호출 실패와 같이 끝난다. 키 값은 출력과 기록에 MUST NOT 남긴다.

#### Scenario: 키 없이 서버 시작
- **WHEN** API 키 없이 앱을 불러오면
- **THEN** 오류가 나지 않는다

#### Scenario: 키 없이 실행
- **WHEN** API 키 없이 실행을 시작하면
- **THEN** 프로필의 고정 답이 나가고 실행 상태는 `failed`다

#### Scenario: 모델 설정 적용
- **WHEN** 설정의 모델을 바꿔 실행하면
- **THEN** 그 모델로 호출되고 실행 기록에 그 모델이 남는다
