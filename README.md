# codyssey-b3-1

## 필수과제 진행 안내

- [Kanban 작업 목록](KANBAN.md)
- [단계별 CLI 실행 가이드](docs/STEP_BY_STEP.md)
- [실습 IAM 정책 예시](docs/lab-policy.json)

## 자동화 실행

- [설치·인증·실행 및 복구 안내](docs/AUTOMATION.md)
- 실행 진입점: `bash scripts/lab.sh all --profile cloud-lab --free-tier-confirmed --iam-reviewed`
- 현재 상태: 실제 검증 및 실습 리소스 정리 완료. 아래 실행 결과 참조.

<!-- lab-results -->
## 외부 접속 검증

- 방식: B — GET /health
- URL: http://43.203.163.12/health
- 검증 시각: 2026-11-22T07:50:19.524496+00:00
- 결과: 실제 외부 요청 및 Chromium 접속에서 HTTP 200, OK 확인
- 실습 리소스는 2026-11-22T07:51:06.344725+00:00에 정리했다. 현재 URL은 더 이상 서비스하지 않는다.

![실제 브라우저 접속](docs/evidence/external-health.png)

## 제출물

- [아키텍처](docs/architecture.png)
- [트러블슈팅](docs/troubleshooting.md)
- [리소스 정리 체크리스트](docs/cleanup-checklist.md)
- [브라우저 응답](docs/evidence/external-health.json)
