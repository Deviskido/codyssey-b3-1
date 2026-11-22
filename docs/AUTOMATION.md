# 필수과제 자동 실행

`requirements.txt`는 과제 원문이다. pip 의존성 파일이 아니므로 `pip install -r requirements.txt`를 실행하지 않는다.

## 현재 실행 상태

- 실제 AWS 배포·SSH·내부/외부 HTTP·Chromium PNG 캡처·장애 재현/복구 완료.
- 검증 완료: 2026-11-22T07:50:19.524496+00:00 (UTC).
- 두 번째 실행 리소스 정리 완료: 2026-11-22T07:51:06.344725+00:00 (UTC).
- 첫 실행은 Nginx MIME 형식으로 브라우저 캡처가 실패했으며, 해당 리소스도 전부 삭제했다. 상세 내용은 [트러블슈팅](troubleshooting.md)에 기록했다.
- 최종 제출물: `dist/submission.zip`. 검증: `.venv/bin/python scripts/validate_submission.py`.
- IAM 정책은 사용자가 콘솔에서 적용했다고 확인했고, 이후 실습 작업과 삭제가 성공했다. IAM 정책 목록 전체는 조회 권한이 없어 독립적으로 감사하지 못했다.
- 무료 플랜/최종 Billing은 조회 권한이 없어 직접 검증하지 못했다. 사용자의 진행 지시에 따라 실행했으며, 비용 0원을 보장하거나 확인했다고 기록하지 않는다.

## 인증 준비

현재 설치한 AWS CLI는 프로젝트 가상환경의 CLI v1이다. IAM 사용자 인증을 사용하는 경우 저장소 루트의 터미널에서 실행한다.

```bash
.venv/bin/aws configure --profile cloud-lab
```

액세스 키와 비밀 키는 이 로컬 대화형 입력에만 입력한다. 기본 리전은 `ap-northeast-2`, 출력은 `json`으로 지정한다. 채팅, Git, 제출물에 키를 복사하지 않는다. Identity Center/SSO를 사용하는 조직은 AWS CLI v2에서 SSO 인증을 준비하고 해당 프로필명을 실행 옵션에 전달한다.

## IAM 설정도 CLI로 수행

별도의 비루트 관리용 프로필과 **기존 전용 실습 IAM 사용자**가 있으면 다음을 실행한다. 관리용 인증이 없다면 실습 프로필이 자기 권한을 올릴 수는 없다.

```bash
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python scripts/bootstrap_iam.py \
  --admin-profile account-admin --user cloud-lab-user
```

이 도구는 사용자에 연결된 관리형 정책, 다른 인라인 정책, 그룹이 있으면 변경하지 않고 중단한다. 전용 사용자에 `docs/lab-policy.json`을 적용하고 다시 읽어 `docs/evidence/iam-policy.json`에 저장한다. 조직 SCP와 권한 경계에 의해 권한이 추가 제한될 수 있다. Role을 사용하는 환경은 관리자가 신뢰 정책 및 유효 권한을 확인하고 동일한 실습 정책을 적용한다.

정책은 서울 리전 EC2/VPC 실습 작업만 허용한다. 리소스 범위가 `*`이므로 전용 실습 계정용이며 공유 계정에서는 관리자가 태그/ARN 조건을 추가해야 한다. 자동화는 개인키 응답 유실을 피하기 위해 로컬 SSH 키 생성 후 `ImportKeyPair`를 사용한다. 이를 위해 해당 권한을 정책에 추가했다.

## 실행

```bash
# 도구를 새로 설치해야 할 때
bash scripts/setup.sh

# 인증 및 기본 도구 확인 (리소스 생성 없음)
bash scripts/lab.sh preflight --profile cloud-lab

# 계정의 무료 사용 조건 및 유효 IAM 권한을 실제로 확인한 후에만 실행
bash scripts/lab.sh all --profile cloud-lab \
  --free-tier-confirmed --iam-reviewed
```

`--free-tier-confirmed`는 계정별 EC2, EBS 8GiB, 퍼블릭 IPv4 무료 조건을 확인했다는 입력이다. 이 옵션 자체가 비용을 조회하거나 무료를 보장하지 않는다. `--iam-reviewed`도 정책 자동 검증을 대신하지 않으며, 관리자 권한이 없는 전용 실습 신원임을 확인한 뒤 지정한다.

`all`은 K03~K15를 수행한다. 서울 리전에서 VPC, Public Subnet, IGW, Route Table, SG, t3.micro EC2 1대, EBS 8GiB를 만든다. HTTP 80은 공개, SSH 22는 실행 PC의 공인 IPv4 `/32`로 제한한다. SSH로 Nginx 설치, 내부/외부 응답 확인, Chromium 스크린샷 촬영, Nginx 중지 오류 재현 및 복구, 리소스 삭제를 수행한다. 검증과 삭제가 모두 성공해야 최종 보고서 및 ZIP을 생성한다.

개별 생성 응답이 유실되면 Project 태그로 리소스를 복구하며 EC2 생성에는 동일 client token을 사용한다. SG 규칙은 이 실행 전용 SG에서만 재설정한다. 이전 실행이 정리 완료된 상태에서는 재생성을 거부한다. 새로운 실습은 기존 상태와 증빙을 별도 보관한 후 시작한다.

## 실패 및 복구

일반 실행 오류가 발생하면 `finally`에서 생성 리소스 정리를 시도한다. 프로세스 강제 종료, 네트워크 단절, 인증 만료 등은 자동 정리를 보장하지 못한다. 그 경우 동일한 계정과 프로필에서 다음 명령으로 재개한다.

```bash
bash scripts/lab.sh cleanup --profile cloud-lab
```

삭제 시 Project 태그와 저장 ID의 일치를 확인한다. 이름이 비슷한 다른 리소스나 계정 전체 리소스는 삭제하지 않는다. 삭제 후에는 저장한 리소스 ID를 다시 조회한다. EC2 종료 대기, 잔여 EBS 삭제 확인, 네트워크 의존성 재시도를 포함한다. 삭제 실패 시 체크리스트 완료나 제출 ZIP 생성을 하지 않는다.

실제 검증과 삭제는 끝났지만 보고서 생성만 실패했을 때:

```bash
bash scripts/lab.sh report --profile cloud-lab
```

## 결과 파일

- `.lab/state.json`: 계정·프로필·실행 ID·생성 리소스 ID 및 진행 상태. Git/제출 제외.
- `.lab/id_ed25519`: 실행 중만 필요한 SSH 개인키. 정리 성공 후 삭제. Git/제출 제외.
- `docs/evidence/`: 실제 명령 결과, AWS 조회 JSON, 브라우저 PNG 및 trace.
- `docs/architecture.png`: 실제 리소스 ID 기반 Graphviz 아키텍처.
- `docs/troubleshooting.md`: 관측한 장애 재현·진단·복구 근거.
- `docs/cleanup-checklist.md`: 종료/삭제 확인 시각과 근거.
- `README.md`: 실제 URL, 방식 B, 검증 시각, 캡처 링크 및 정리 후 접속 불가 안내.
- `dist/submission.zip`: 제출 문서·증거·SHA-256 manifest. 자격 증명과 `.lab`, `.venv`는 제외.

브라우저 PNG에는 웹페이지 내용이 포함되며 주소창은 포함되지 않는다. URL, HTTP 상태, 본문, UTC 시각은 `external-health.json`에 저장한다. 로컬 브라우저 테스트는 임시 폴더에서만 실행하며 과제 증빙으로 사용하지 않는다.

## 로컬 검증

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tests/browser_smoke.py
```

테스트는 계정 불일치/루트 거부, 삭제 대상 불일치, 생성 응답 유실 복구, 잘못된 HTTP 응답 거부, 장애 검증 실패 시 Nginx 복구, 검증·정리 전 제출 거부를 확인한다. 브라우저 smoke 테스트는 임시 로컬 HTTP 서버에서 실제 Chromium 캡처를 검증하며 AWS 실습 성공을 의미하지 않는다.
