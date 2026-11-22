# 트러블슈팅: Nginx 중지 재현

검증 완료 시각: 2026-11-22T07:50:19.524496+00:00. 이 오류는 실습 인스턴스에서 의도적으로 재현했다.

- 증상: Nginx를 중지한 후 외부 /health 요청이 실패했다. [실제 오류](evidence/failure.txt)
- 가설: 웹 서버 프로세스 중지로 80 포트 리스너가 사라졌다.
- 검증: 서비스 inactive와 80 포트 리스너 부재를 명령으로 검증했다. [로그](evidence/diagnosis.txt), [검증 종료 코드](evidence/diagnosis-check.txt)
- 조치: sudo systemctl start nginx 실행. [기록](evidence/restart.txt)
- 결과: 외부 HTTP 200 및 OK를 재확인했다. [복구 응답](evidence/recovered.txt)
- 재발방지: enable 설정을 유지하고 배포 후 서비스 상태·로컬 응답·외부 /health를 함께 검사한다.

## 실제 발생 오류: 브라우저가 /health를 다운로드로 처리

- 증상: curl은 HTTP 200 / OK였지만 Playwright에서 `Page.goto: Download is starting` 발생. [원본 오류](evidence/first-run-browser-error.txt), [응답 헤더](evidence/first-run-health.txt)
- 가설: 확장자 없는 정적 파일에 적용된 Content-Type이 브라우저 다운로드를 유발했다.
- 검증: 실제 응답의 `Content-Type: application/octet-stream`과 브라우저 오류를 대조했다.
- 조치: 첫 실행 리소스를 삭제한 뒤 전용 `/health` location에 `default_type text/plain`과 `return 200`을 설정하고 nginx 설정 검증 및 reload를 수행했다. [설정 로그](evidence/health-config.txt), [첫 실행 정리](evidence/first-run-cleanup.json)
- 결과: 재실행에서 외부 응답과 Chromium 화면의 OK를 확인하고 PNG를 저장했다. [성공 응답](evidence/external-health.txt), [브라우저 결과](evidence/external-health.json)
- 재발방지: curl 상태뿐 아니라 MIME 형식과 실제 브라우저 렌더링도 배포 검증에 포함한다.
