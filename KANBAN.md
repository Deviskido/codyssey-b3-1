# 필수과제 Kanban

기준: [requirements.txt](requirements.txt)의 필수 기능, 제출물, 제약 사항. 보너스 과제(HTTPS·Docker)는 제외한다.
실행 방법: [필수과제 단계별 CLI 가이드](docs/STEP_BY_STEP.md). 각 카드 ID를 누르면 해당 단계로 이동한다.

실제 AWS 실행 및 제출물 기준으로 갱신했다. K01의 계정별 무료 혜택/Billing은 API 권한 부재로 직접 확인하지 못했다. K02의 정책 적용은 사용자 확인 및 이후 실습 API 실행 성공을 근거로 하며 전체 IAM 정책 감사와 구분한다.

| ID | 상태 | 작업 | 완료 기준 / 증빙 | 선행 작업 |
| --- | --- | --- | --- | --- |
| [K01](docs/STEP_BY_STEP.md#k01) | 비용 확인 제한 | 실습 환경 및 비용 범위 확인 | 서울 리전 `ap-northeast-2` 사용, 계정의 프리 티어 범위 확인, micro급 인스턴스 1대·Ubuntu LTS 또는 Amazon Linux·EBS 8~10GiB 계획 기록 | 없음 |
| [K02](docs/STEP_BY_STEP.md#k02) | 완료(사용자 정책 적용 확인) | 최소권한 IAM 사용자 또는 Role 준비 | 루트 계정 대신 IAM 사용자/Role 1개로 콘솔 접근. EC2/VPC/SG 구성·조회·태그·연결·정리에 필요한 권한만 부여하고 `AdministratorAccess` 및 무관한 S3/RDS 권한은 제외. 적용 정책 기록 | [K01](docs/STEP_BY_STEP.md#k01) |
| [K03](docs/STEP_BY_STEP.md#k03) | 완료 | 리소스 정리 추적표 준비 | `docs/cleanup-checklist.md` 생성. 리소스 생성 시 ID·리전·정리 방법·상태·완료 근거를 기록할 수 있도록 구성 | [K01](docs/STEP_BY_STEP.md#k01) |
| [K04](docs/STEP_BY_STEP.md#k04) | 완료 | VPC 및 Public Subnet 생성 | VPC 1개, Public Subnet 1개 생성 후 CIDR 및 리소스 ID 기록 | K02, K03 |
| [K05](docs/STEP_BY_STEP.md#k05) | 완료 | 인터넷 라우팅 구성 | Internet Gateway를 VPC에 연결하고 Public Subnet에 연결된 Route Table에 `0.0.0.0/0 → IGW` 경로 설정. 연결 및 경로 확인 | [K04](docs/STEP_BY_STEP.md#k04) |
| [K06](docs/STEP_BY_STEP.md#k06) | 완료 | Security Group 설정 | 인바운드 HTTP(80)는 `0.0.0.0/0`, SSH(22)는 개인 IP 또는 지정 IP 대역만 허용. 불필요한 포트 및 전체 포트 공개 규칙 없음. 규칙 기록 | [K04](docs/STEP_BY_STEP.md#k04) |
| [K07](docs/STEP_BY_STEP.md#k07) | 완료 | 키페어 및 EC2 생성 | 키페어 1개를 안전하게 보관하고 Public Subnet에 EC2 1대 생성. 퍼블릭 IP, 지정 SG, 계획한 OS·인스턴스 유형·EBS 적용. 리소스 추적표 갱신 | K05, K06 |
| [K08](docs/STEP_BY_STEP.md#k08) | 완료 | SSH 및 아웃바운드 통신 검증 | 허용한 IP에서 SSH 접속 성공, 인스턴스에서 `curl https://example.com` 성공. 검증 결과 기록 | [K07](docs/STEP_BY_STEP.md#k07) |
| [K09](docs/STEP_BY_STEP.md#k09) | 완료 | 웹 서버 설치 및 내부 검증 | Nginx 등 웹 서버 설치·실행. 인스턴스에서 `curl -i http://localhost` 실행 시 HTTP 200 확인 및 결과 기록 | [K08](docs/STEP_BY_STEP.md#k08) |
| [K10](docs/STEP_BY_STEP.md#k10) | 완료 | 외부 접속 검증 및 증빙 저장 | A: 외부 브라우저에서 `http://<퍼블릭IP>` 정상 표시, 또는 B: `GET http://<퍼블릭IP>/health`가 HTTP 200과 고정 응답 반환. B 선택 시 `/health` 구성. 선택한 방식으로 접속 결과 스크린샷 1장 이상 저장 | [K09](docs/STEP_BY_STEP.md#k09) |
| [K11](docs/STEP_BY_STEP.md#k11) | 완료 | 아키텍처 다이어그램 작성 | `docs/architecture.png` 또는 `docs/architecture.pdf` 1개 제출. VPC, Subnet, IGW, EC2, SG 및 외부 → 서비스 트래픽 흐름 표시 | [K07](docs/STEP_BY_STEP.md#k07) |
| [K12](docs/STEP_BY_STEP.md#k12) | 완료 | 트러블슈팅 보고서 작성 | 실제 발생하거나 재현한 오류 최소 1건을 `docs/troubleshooting.md` 또는 `.pdf`에 기록. 증상 → 가설 → 검증 → 조치 → 결과 → 재발방지 및 로그/증상 근거 포함. 재현 후 정상 설정 복구 | [K08](docs/STEP_BY_STEP.md#k08) |
| [K13](docs/STEP_BY_STEP.md#k13) | 완료 | README 및 제출 증빙 정리 | `README.md`에 선택한 외부 검증 방식(A/B), 접속 URL 또는 IP, 접속 스크린샷 링크 기록. 아키텍처·트러블슈팅·정리 체크리스트 링크 연결 | K10, K11, K12 |
| [K14](docs/STEP_BY_STEP.md#k14) | 완료 | 실습 리소스 종료 및 삭제 | 증빙 확보 후 EC2 종료(Terminated), EBS 미사용 볼륨 포함 삭제, 할당한 Elastic IP Release, IGW 분리·삭제, Subnet·사용자 정의 Route Table·SG 등 의존 리소스 및 VPC 삭제. 생성한 기타 실습 리소스도 정리 | [K13](docs/STEP_BY_STEP.md#k13) |
| [K15](docs/STEP_BY_STEP.md#k15) | 완료 | 정리 완료 근거 및 최종 제출 확인 | 체크리스트에 리소스별 종료/삭제 확인 결과·확인 시점·근거 기록. 미생성 항목은 해당 없음으로 표시. 최종 제출물 4종과 README 링크 확인. Billing Dashboard 확인은 권장 | [K14](docs/STEP_BY_STEP.md#k14) |

## 정리 체크리스트에 포함할 항목

- EC2: 단순 중지(Stopped)가 아닌 종료(Terminated) 확인
- EBS: 미사용 볼륨을 포함해 삭제 확인
- Elastic IP: 할당했다면 Release 확인, 미할당이면 해당 없음 기록
- Internet Gateway: VPC에서 분리 후 삭제 확인
- VPC 및 의존 리소스: Subnet, Route Table, Security Group 등 정리 확인
- NAT Gateway, ELB/ALB, RDS: 생성했다면 삭제 확인, 미생성이면 해당 없음 기록. 필수과제 수행을 위해 새로 만들 필요는 없음
- 기타 생성한 실습 리소스: 키페어 등 정리 여부 기록

## 최종 제출물

- [x] `docs/architecture.(png|pdf)` 1개
- [x] `README.md`의 외부 검증 방식(A/B)·URL 또는 IP + 접속 결과 스크린샷 1장 이상
- [x] `docs/troubleshooting.(md|pdf)` 1개
- [x] `docs/cleanup-checklist.md` 1개 및 종료/삭제 완료 근거
