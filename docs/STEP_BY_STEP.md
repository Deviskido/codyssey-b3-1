# 필수과제 단계별 CLI 가이드

[requirements.txt](../requirements.txt)와 [KANBAN.md](../KANBAN.md)의 K01–K15에 대응한다. HTTPS·Docker 보너스는 제외한다. 이 문서는 실행 절차이며 리소스 생성이나 검증이 이미 완료되었다는 증빙이 아니다.

선택 구성: 서울 리전, Public Subnet 1개, Amazon Linux 2023 x86_64, micro급 EC2 1대, EBS 8GiB, Nginx. 외부 검증은 **B: GET /health → HTTP 200 + OK**를 사용한다. Elastic IP, NAT Gateway, ELB/ALB, RDS는 만들지 않는다.

로컬 명령은 저장소 루트의 **같은 Bash 세션**에서 순서대로 실행한다. `ssh ... '명령'` 안의 명령만 EC2에서 실행된다. 각 단계의 성공을 확인한 뒤 진행하고 실패한 생성 명령을 무작정 반복하지 않는다. 생성된 ID는 즉시 `.lab/state.env`에 저장한다. 세션이 끊겼다면 같은 저장소에서 `source .lab/state.env` 후 프로필과 리전을 다시 설정한다.

<a id="k01"></a>

## 1. K01 — 도구, 계정, 비용 확인

1. macOS에서는 Homebrew가 설치되어 있다면 아래 명령으로 도구를 준비한다. 다른 OS에서는 AWS 공식 설치 안내를 사용한다.

   ```bash
   brew install awscli graphviz
   bash
   aws --version
   dot -V
   ```

2. AWS 계정의 현재 플랜, 크레딧/무료 사용량, 만료일을 확인한다. `t3.micro`라는 이름만으로 무료가 보장되지는 않는다. EBS와 퍼블릭 IPv4도 비용 확인 대상이다. 계정별 혜택은 Billing/Free Tier 화면에서 확인하는 편이 명확하다. 이 조회는 기존 비용 조회 담당자에게 맡겨도 된다.
3. 프리 티어 조건을 만족할 때만 이후 생성 단계를 실행한다. 해당하지 않으면 인스턴스를 생성하기 전에 수업 담당자와 비용 조건을 조정한다.

[AWS CLI 설치 안내](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html), [AWS Free Tier 안내](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier.html)

<a id="k02"></a>

## 2. K02 — 최소권한 IAM 및 CLI 인증

1. 기존 계정 관리자가 **루트가 아닌 관리용 IAM 신원**으로 실습 IAM 사용자 또는 Role을 준비한다. 실습 신원에 `AdministratorAccess`를 붙이지 않는다.
2. 관리자는 저장소의 [lab-policy.json](lab-policy.json)을 확인하고 실습 신원에 적용한다. 아래는 이미 생성된 IAM 사용자에 적용하는 예시이다. `account-admin`은 기존 관리 프로필, `cloud-lab-user`는 실제 사용자명으로 바꾼다.

   ```bash
   aws iam put-user-policy --profile account-admin \
     --user-name cloud-lab-user --policy-name CloudLabSeoul \
     --policy-document file://docs/lab-policy.json
   ```

   Role을 사용하면 관리자가 `aws iam put-role-policy --role-name <실제-Role명>`으로 같은 정책을 적용한다. 기존 그룹 정책·관리형 정책·Role 권한도 확인해야 한다. 좁은 정책을 추가해도 기존 관리자 권한이 사라지지는 않는다.

   이 정책은 서울 리전의 실습용 EC2/VPC 작업만 명시적으로 허용한다. IAM 변경, S3/RDS, Billing 권한은 포함하지 않는다. `Resource: "*"`이므로 같은 계정 서울 리전의 다른 EC2/VPC 리소스에도 명시된 작업이 가능하다. **전용 실습 계정용 작업·리전 제한 정책**이며, 공유 계정에서는 관리자가 리소스 ARN/태그 조건을 추가로 제한해야 한다.

3. 발급된 인증 방식에 맞춰 **둘 중 하나**를 설정한다. Identity Center가 준비되어 있으면 SSO를 사용한다. IAM 사용자용 액세스 키를 사용하는 경우 키를 채팅·문서·저장소에 넣지 않는다.

   ```bash
   # SSO 환경: 설정 중 프로필 이름을 cloud-lab으로 지정
   aws configure sso --profile cloud-lab
   aws sso login --profile cloud-lab
   ```

   ```bash
   # IAM 사용자 액세스 키 환경: 대화형 입력
   aws configure --profile cloud-lab
   ```

4. 세션 기본값과 실제 신원을 확인한다.

   ```bash
   export AWS_PROFILE=cloud-lab
   export AWS_REGION=ap-northeast-2
   export AWS_DEFAULT_REGION=ap-northeast-2
   export AWS_PAGER=''
   aws sts get-caller-identity
   ```

5. ARN이 의도한 사용자/Role인지 확인한다. 콘솔에 접근해야 하는 경우에도 동일한 실습 사용자/Role을 사용한다. IAM 신원 준비와 비용 조회를 제외한 다음 AWS 작업은 실습 프로필로 수행한다.

<a id="k03"></a>

## 3. K03 — 상태 및 증빙 디렉터리 준비

1. 상태 파일과 개인키는 Git에서 제외한다.

   ```bash
   mkdir -p .lab docs/evidence
   chmod 700 .lab
   touch .gitignore
   printf '\n.lab/\n*.pem\n' >> .gitignore
   LAB_NAME="cloud-lab-$(date +%Y%m%d-%H%M%S)"
   printf 'LAB_NAME=%q\n' "$LAB_NAME" > .lab/state.env
   chmod 600 .lab/state.env
   save_var() { printf '%s=%q\n' "$1" "${!1}" >> .lab/state.env; }
   aws sts get-caller-identity > .lab/identity.json
   ```

   세션 재개 시 위 `save_var()` 함수도 다시 정의한다. `state.env`는 직접 만든 파일만 `source`한다.

2. `docs/cleanup-checklist.md`를 만들고 아래 항목을 복사한다. 생성 때마다 ID를 적고, 실제 정리 후에만 체크한다.

   ```markdown
   # 리소스 정리 체크리스트
   리전: ap-northeast-2

   | 리소스 | ID | 상태 | 확인 시각 | 근거 파일 |
   | --- | --- | --- | --- | --- |
   | EC2 | 생성 후 기록 | 미완료 | | |
   | EBS | 생성 후 기록 | 미완료 | | |
   | Elastic IP | 미생성 | 해당 없음 | | |
   | Internet Gateway | 생성 후 기록 | 미완료 | | |
   | Subnet | 생성 후 기록 | 미완료 | | |
   | Route Table | 생성 후 기록 | 미완료 | | |
   | Security Group | 생성 후 기록 | 미완료 | | |
   | VPC | 생성 후 기록 | 미완료 | | |
   | Key Pair | 생성 후 기록 | 미완료 | | |
   | NAT Gateway / ELB·ALB / RDS | 미생성 | 해당 없음 | | |
   ```

<a id="k04"></a>

## 4. K04 — VPC와 Subnet 생성

1. VPC를 만들고 ID를 저장한다.

   ```bash
   VPC_ID=$(aws ec2 create-vpc --cidr-block 10.0.0.0/16 \
     --tag-specifications "ResourceType=vpc,Tags=[{Key=Name,Value=$LAB_NAME},{Key=Project,Value=$LAB_NAME}]" \
     --query 'Vpc.VpcId' --output text)
   save_var VPC_ID
   aws ec2 wait vpc-available --vpc-ids "$VPC_ID"
   aws ec2 modify-vpc-attribute --vpc-id "$VPC_ID" --enable-dns-support '{"Value":true}'
   ```

2. Subnet을 만든다. AZ는 AWS가 선택한다.

   ```bash
   SUBNET_ID=$(aws ec2 create-subnet --vpc-id "$VPC_ID" --cidr-block 10.0.1.0/24 \
     --tag-specifications "ResourceType=subnet,Tags=[{Key=Name,Value=$LAB_NAME},{Key=Project,Value=$LAB_NAME}]" \
     --query 'Subnet.SubnetId' --output text)
   save_var SUBNET_ID
   ```

<a id="k05"></a>

## 5. K05 — Internet Gateway와 라우팅

1. IGW를 생성하고 VPC에 연결한다.

   ```bash
   IGW_ID=$(aws ec2 create-internet-gateway \
     --tag-specifications "ResourceType=internet-gateway,Tags=[{Key=Project,Value=$LAB_NAME}]" \
     --query 'InternetGateway.InternetGatewayId' --output text)
   save_var IGW_ID
   aws ec2 attach-internet-gateway --internet-gateway-id "$IGW_ID" --vpc-id "$VPC_ID"
   ```

2. 별도 Route Table을 만들어 Subnet에 연결한다.

   ```bash
   RT_ID=$(aws ec2 create-route-table --vpc-id "$VPC_ID" \
     --tag-specifications "ResourceType=route-table,Tags=[{Key=Project,Value=$LAB_NAME}]" \
     --query 'RouteTable.RouteTableId' --output text)
   save_var RT_ID
   aws ec2 create-route --route-table-id "$RT_ID" --destination-cidr-block 0.0.0.0/0 --gateway-id "$IGW_ID"
   RT_ASSOC_ID=$(aws ec2 associate-route-table --route-table-id "$RT_ID" --subnet-id "$SUBNET_ID" \
     --query 'AssociationId' --output text)
   save_var RT_ASSOC_ID
   aws ec2 describe-route-tables --route-table-ids "$RT_ID" > docs/evidence/routes.json
   ```

3. 증빙에서 Subnet 연결과 `0.0.0.0/0 → igw-...`, `State: active`를 확인한다.

<a id="k06"></a>

## 6. K06 — HTTP 공개, SSH는 내 IP만 허용

1. 현재 공인 IPv4를 조회하고 `/32`로 제한한다. VPN을 사용한다면 SSH가 나가는 IP와 같은지 확인한다.

   ```bash
   MY_IP=$(curl -4fsS https://checkip.amazonaws.com)
   SSH_CIDR="$MY_IP/32"
   save_var SSH_CIDR
   SG_ID=$(aws ec2 create-security-group --group-name "$LAB_NAME-web" \
     --description 'HTTP public and SSH from learner IP' --vpc-id "$VPC_ID" \
     --tag-specifications "ResourceType=security-group,Tags=[{Key=Project,Value=$LAB_NAME}]" \
     --query 'GroupId' --output text)
   save_var SG_ID
   aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 80 --cidr 0.0.0.0/0
   aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 22 --cidr "$SSH_CIDR"
   aws ec2 describe-security-groups --group-ids "$SG_ID" > docs/evidence/security-group.json
   ```

2. 인바운드가 위 두 규칙뿐인지 확인한다. 기본 아웃바운드 허용은 패키지 설치와 인터넷 통신에 사용한다. SSH 소스를 `0.0.0.0/0`으로 넓히지 않는다.

<a id="k07"></a>

## 7. K07 — 키페어, AMI, EC2 생성

1. 개인키를 생성한다. 같은 이름으로 재실행하면 기존 파일을 덮어쓸 수 있으므로 한 번만 실행한다.

   ```bash
   KEY_NAME="$LAB_NAME-key"
   KEY_FILE=".lab/$KEY_NAME.pem"
   save_var KEY_NAME
   save_var KEY_FILE
   (umask 077; aws ec2 create-key-pair --key-name "$KEY_NAME" \
     --query 'KeyMaterial' --output text > "$KEY_FILE")
   test -s "$KEY_FILE"
   chmod 400 "$KEY_FILE"
   ```

2. 서울 리전의 Amazon 제공 AL2023 x86_64 AMI를 조회한다. AMI ID는 고정값으로 복사하지 않는다.

   ```bash
   AMI_ID=$(aws ec2 describe-images --owners amazon \
     --filters 'Name=name,Values=al2023-ami-2023.*-kernel-6.1-x86_64' \
       'Name=state,Values=available' 'Name=root-device-type,Values=ebs' \
     --query 'sort_by(Images, &CreationDate)[-1].ImageId' --output text)
   save_var AMI_ID
   aws ec2 describe-images --image-ids "$AMI_ID" \
     --query 'Images[0].{ID:ImageId,Name:Name,Architecture:Architecture,Root:RootDeviceName}'
   ROOT_DEVICE=$(aws ec2 describe-images --image-ids "$AMI_ID" --query 'Images[0].RootDeviceName' --output text)
   INSTANCE_TYPE=t3.micro
   aws ec2 describe-instance-types --instance-types "$INSTANCE_TYPE" \
     --query 'InstanceTypes[].{Type:InstanceType,FreeTierEligible:FreeTierEligible}'
   ```

   AMI가 `None`이면 생성하지 말고 필터와 리전을 확인한다. `FreeTierEligible`는 유형 정보이며 계정의 잔여 무료 혜택을 보장하지 않는다. K01에서 확인한 유형과 일치시킨다. 아래 명령은 `t3.micro`를 기준으로 한다.

3. 8GiB EBS와 퍼블릭 IP를 가진 인스턴스 1대를 실행한다. CPU 크레딧은 Standard로 지정하고 IMDSv2를 사용한다.

   ```bash
   INSTANCE_ID=$(aws ec2 run-instances --image-id "$AMI_ID" --instance-type "$INSTANCE_TYPE" \
     --count 1 --key-name "$KEY_NAME" --subnet-id "$SUBNET_ID" \
     --security-group-ids "$SG_ID" --associate-public-ip-address \
     --credit-specification CpuCredits=standard \
     --metadata-options HttpTokens=required,HttpEndpoint=enabled \
     --block-device-mappings "[{\"DeviceName\":\"$ROOT_DEVICE\",\"Ebs\":{\"VolumeSize\":8,\"VolumeType\":\"gp3\",\"DeleteOnTermination\":true}}]" \
     --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$LAB_NAME},{Key=Project,Value=$LAB_NAME}]" \
       "ResourceType=volume,Tags=[{Key=Project,Value=$LAB_NAME}]" \
     --query 'Instances[0].InstanceId' --output text)
   save_var INSTANCE_ID
   aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"
   aws ec2 wait instance-status-ok --instance-ids "$INSTANCE_ID"
   PUBLIC_IP=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
     --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
   VOLUME_ID=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
     --query 'Reservations[0].Instances[0].BlockDeviceMappings[0].Ebs.VolumeId' --output text)
   save_var PUBLIC_IP
   save_var VOLUME_ID
   aws ec2 describe-instances --instance-ids "$INSTANCE_ID" > docs/evidence/instance.json
   ```

4. `.lab/state.env`의 ID를 정리 체크리스트에 옮긴다. Waiter가 시간 초과하면 상태를 조회한 뒤 다시 기다린다. 인스턴스를 추가로 만들지 않는다.

[AWS EC2 CLI 실행 안내](https://docs.aws.amazon.com/cli/latest/userguide/cli-services-ec2-instances.html), [AMI 선택 기준](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/finding-an-ami.html)

<a id="k08"></a>

## 8. K08 — SSH 및 아웃바운드 검증

1. 로컬에서 실행한다. 첫 SSH 연결의 호스트 키 확인을 처리한다.

   ```bash
   ssh -i "$KEY_FILE" "ec2-user@$PUBLIC_IP" 'whoami; curl -I --max-time 15 https://example.com' \
     2>&1 | tee docs/evidence/ssh-outbound.txt
   ```

2. `ec2-user`와 외부 HTTP 응답을 확인한다. SSH 타임아웃은 공인 IP·SG의 22 소스·라우팅부터 확인한다. 개인 IP가 바뀌면 기존 SSH 규칙을 제거하고 새 `/32`만 허용한다.

<a id="k09"></a>

## 9. K09 — Nginx 설치 및 내부 검증

1. 로컬에서 SSH를 통해 서버 명령을 실행한다.

   ```bash
   ssh -i "$KEY_FILE" "ec2-user@$PUBLIC_IP" 'sudo dnf install -y nginx && sudo systemctl enable --now nginx'
   ssh -i "$KEY_FILE" "ec2-user@$PUBLIC_IP" "printf 'OK\n' | sudo tee /usr/share/nginx/html/health"
   ssh -i "$KEY_FILE" "ec2-user@$PUBLIC_IP" \
     'systemctl is-active nginx; curl -i --max-time 10 http://localhost; curl -i --max-time 10 http://localhost/health' \
     2>&1 | tee docs/evidence/localhost.txt
   ```

2. 서비스 `active`, `/`의 HTTP 200, `/health`의 HTTP 200 및 `OK`를 모두 확인한다.

<a id="k10"></a>

## 10. K10 — 외부에서 /health 검증

1. EC2 내부가 아닌 **로컬 PC**에서 실행한다.

   ```bash
   printf 'URL: http://%s/health\n' "$PUBLIC_IP"
   date -u
   curl -i --fail --max-time 15 "http://$PUBLIC_IP/health" | tee docs/evidence/external-health.txt
   ```

2. HTTP 200과 `OK`를 확인한다. 터미널에 URL과 응답을 함께 표시한다.
3. 요구사항상 텍스트 로그 외에 스크린샷 1장 이상이 필요하다. macOS에서는 아래 명령 후 해당 터미널 영역을 선택한다.

   ```bash
   screencapture -i docs/evidence/external-health.png
   ```

   다른 OS에서는 OS 스크린샷 기능으로 같은 파일을 저장한다. 키·토큰이 화면에 보이지 않게 한다.

<a id="k11"></a>

## 11. K11 — CLI로 아키텍처 PNG 생성

1. 다음 Graphviz 소스를 저장하고 PNG로 렌더링한다.

   ```bash
   cat > docs/architecture.dot <<EOF_DOT
   digraph Infrastructure {
     rankdir=TB;
     node [shape=box];
     internet [label="External client"];
     subgraph cluster_vpc {
       label="VPC $VPC_ID / 10.0.0.0/16 / ap-northeast-2";
       igw [label="Internet Gateway $IGW_ID"];
       route [label="Route Table $RT_ID\n0.0.0.0/0 -> IGW"];
       subgraph cluster_subnet {
         label="Public Subnet $SUBNET_ID / 10.0.1.0/24";
         sg [label="Security Group $SG_ID\n80: 0.0.0.0/0\n22: $SSH_CIDR"];
         ec2 [label="EC2 $INSTANCE_ID\nPublic IP: $PUBLIC_IP\nNginx :80 /health -> 200 OK"];
       }
     }
     internet -> igw [label="HTTP :80 / SSH :22"];
     igw -> sg;
     sg -> ec2;
     route -> igw [style=dashed, label="default route"];
     route -> ec2 [style=dashed, label="associated with subnet", dir=none];
   }
   EOF_DOT
   dot -Tpng docs/architecture.dot -o docs/architecture.png
   ```

2. PNG를 열어 잘림이나 잘못된 ID가 없는지 확인한다. 실선은 요청 흐름, 점선은 라우팅 설정 관계이다. `.dot`만 제출하면 PNG/PDF 요구사항을 충족하지 못한다.

<a id="k12"></a>

## 12. K12 — 오류 1건 재현, 분석, 복구

1. 실제 발생한 오류가 있으면 그 사례를 사용한다. 없다면 **본 실습 인스턴스에서만** Nginx 중지 사례를 재현한다.

   ```bash
   ssh -i "$KEY_FILE" "ec2-user@$PUBLIC_IP" 'sudo systemctl stop nginx'
   curl -i --max-time 10 "http://$PUBLIC_IP/health" > docs/evidence/failure.txt 2>&1
   ssh -i "$KEY_FILE" "ec2-user@$PUBLIC_IP" \
     'systemctl is-active nginx; sudo ss -lntp; sudo journalctl -u nginx -n 30 --no-pager' \
     > docs/evidence/diagnosis.txt 2>&1
   ```

2. 가설을 세운다: HTTP 요청 실패가 Nginx 중지 때문인가? `inactive`, 80 리스너 부재, 서비스 로그를 대조한다. 예상 내용을 관측 결과인 것처럼 쓰지 않는다.
3. 즉시 복구하고 외부 정상 응답을 재확인한다.

   ```bash
   ssh -i "$KEY_FILE" "ec2-user@$PUBLIC_IP" 'sudo systemctl start nginx'
   curl -i --fail --max-time 15 "http://$PUBLIC_IP/health" | tee docs/evidence/recovered.txt
   ```

4. `docs/troubleshooting.md`에 **증상 → 가설 → 검증 → 조치 → 결과 → 재발방지** 순서로 작성한다. 실행 시각, 실제 오류, 위 근거 파일 링크, 복구 후 200/OK를 포함한다. 재발방지는 예를 들어 배포 후 `systemctl is-active nginx` 및 외부 `/health` 확인 절차로 작성한다. 의도적으로 재현했다면 이를 명시한다.

<a id="k13"></a>

## 13. K13 — README 제출 정보 정리

1. `README.md`에 아래 내용을 추가하고 실제 IP와 검증 시각을 입력한다.

   ```markdown
   ## 외부 접속 검증

   - 방식: B — GET /health
   - URL: http://실제-퍼블릭IP/health
   - 검증 시각: 실제 시각 및 시간대
   - 결과: 실제 관측 결과 기록

   ![외부 접속 결과](docs/evidence/external-health.png)

   ## 제출물

   - [아키텍처](docs/architecture.png)
   - [트러블슈팅](docs/troubleshooting.md)
   - [리소스 정리 체크리스트](docs/cleanup-checklist.md)
   ```

2. 스크린샷과 제출물 파일이 실제로 존재하는지 확인한다. 정리 후에는 서비스가 종료되어 URL이 더 이상 동작하지 않는다는 사실을 README에 추가한다.

<a id="k14"></a>

## 14. K14 — 증빙 확보 후 실습 리소스 정리

1. `.lab/state.env`의 ID와 실제 실습 리소스가 일치하는지 확인한다. 아래 삭제는 이 가이드에서 만든 리소스에만 실행한다. 작업 도중 실패했다면 존재하는 리소스만 정리한다.

   ```bash
   source .lab/state.env
   aws sts get-caller-identity
   aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
     --query 'Reservations[].Instances[].{ID:InstanceId,State:State.Name,Tags:Tags}'
   ```

2. EC2를 종료하고 루트 EBS 삭제를 확인한다.

   ```bash
   aws ec2 terminate-instances --instance-ids "$INSTANCE_ID" > docs/evidence/terminate.json
   aws ec2 wait instance-terminated --instance-ids "$INSTANCE_ID"
   aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
     --query 'Reservations[].Instances[].{ID:InstanceId,State:State.Name}' > docs/evidence/ec2-final.json
   aws ec2 describe-volumes --filters "Name=volume-id,Values=$VOLUME_ID" > docs/evidence/ebs-final.json
   aws ec2 describe-volumes --filters "Name=tag:Project,Values=$LAB_NAME"
   ```

   `ebs-final.json`의 `Volumes: []`를 확인한다. 자동 삭제가 아직 진행 중이면 기다린 뒤 재조회한다. 이 실습에서 만든 볼륨이 `available`로 남았다면 **해당 ID를 확인한 뒤** `aws ec2 delete-volume --volume-id <확인한-볼륨-ID>`를 실행하고 다시 조회한다. 계정 전체의 미사용 볼륨을 일괄 삭제하지 않는다.

3. 네트워크와 AWS 키페어를 정리한다. 의존성 오류가 발생하면 네트워크 인터페이스 삭제 완료 여부를 확인하고 재시도한다.

   ```bash
   aws ec2 disassociate-route-table --association-id "$RT_ASSOC_ID"
   aws ec2 delete-subnet --subnet-id "$SUBNET_ID"
   aws ec2 delete-route-table --route-table-id "$RT_ID"
   aws ec2 delete-security-group --group-id "$SG_ID"
   aws ec2 detach-internet-gateway --internet-gateway-id "$IGW_ID" --vpc-id "$VPC_ID"
   aws ec2 delete-internet-gateway --internet-gateway-id "$IGW_ID"
   aws ec2 delete-vpc --vpc-id "$VPC_ID"
   aws ec2 delete-key-pair --key-name "$KEY_NAME"
   ```

   기본 Route Table·기본 SG·기본 Network ACL은 VPC 삭제 시 함께 정리된다. AWS 키페어 삭제는 로컬 `.pem` 삭제와 별개이다. 실습 종료 후 로컬 개인키도 더 필요하지 않으면 제거한다.

4. 이 절차는 Elastic IP/NAT Gateway/ELB/RDS를 생성하지 않는다. 실제로 별도 생성한 항목이 있으면 `해당 없음`으로 표시하지 말고 계정 담당자 권한으로 해당 ID의 해제·삭제를 완료한다. 최소권한 실습 정책을 무관한 서비스 전체 권한으로 넓히지 않는다.

<a id="k15"></a>

## 15. K15 — 삭제 근거 및 최종 체크

1. 삭제 이후 필터 조회로 해당 리소스가 없는지 기록한다.

   ```bash
   date -u > docs/evidence/cleanup-time.txt
   aws ec2 describe-vpcs --filters "Name=vpc-id,Values=$VPC_ID" > docs/evidence/vpc-final.json
   aws ec2 describe-subnets --filters "Name=subnet-id,Values=$SUBNET_ID" > docs/evidence/subnet-final.json
   aws ec2 describe-route-tables --filters "Name=route-table-id,Values=$RT_ID" > docs/evidence/routes-final.json
   aws ec2 describe-security-groups --filters "Name=group-id,Values=$SG_ID" > docs/evidence/sg-final.json
   aws ec2 describe-internet-gateways --filters "Name=internet-gateway-id,Values=$IGW_ID" > docs/evidence/igw-final.json
   aws ec2 describe-key-pairs --filters "Name=key-name,Values=$KEY_NAME" > docs/evidence/key-final.json
   aws ec2 describe-network-interfaces --filters "Name=vpc-id,Values=$VPC_ID" > docs/evidence/eni-final.json
   ```

2. 대상 컬렉션이 비어 있고 EC2가 `terminated`인지 확인한다. `AccessDenied`나 명령 실패는 삭제 증빙이 아니다. `cleanup-checklist.md`에 각 파일 링크와 확인 시각을 기록한다.
3. 생성 이력과 체크리스트를 대조해 EIP와 기타 과금 리소스의 누락을 확인한다. Billing 화면은 비용 조회 권한이 있는 신원으로 확인하는 것을 권장한다. 삭제는 기존 사용 요금을 없애지 않으며 비용 반영에 지연이 있을 수 있다.
4. 최종 제출 파일을 확인한다.

   ```bash
   ls -l README.md docs/architecture.png docs/troubleshooting.md \
     docs/cleanup-checklist.md docs/evidence/external-health.png
   git status --short
   ```

5. 개인키와 자격 증명이 포함되지 않았는지 확인한 후 제출한다. Kanban의 K01–K15는 각 완료 기준과 실제 증빙을 확인했을 때만 `완료`로 변경한다.
