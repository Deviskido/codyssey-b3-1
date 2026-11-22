"""AWS lab runner. Real observations only; all subprocess calls use argv, never shell."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import time
import uuid
import zipfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / '.lab/state.json'
EVIDENCE = ROOT / 'docs/evidence'
REGION = 'ap-northeast-2'


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    temp.replace(path)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


class Lab:
    def __init__(self, profile):
        self.profile = profile
        self.s = json.loads(STATE.read_text()) if STATE.exists() else {}
        self.env = dict(os.environ, AWS_PAGER='', AWS_DEFAULT_REGION=REGION,
                        AWS_REGION=REGION, AWS_PROFILE=profile)
        self.env['PATH'] = str(ROOT / '.venv/bin') + os.pathsep + self.env['PATH']
        self.env['PLAYWRIGHT_BROWSERS_PATH'] = str(ROOT / '.lab/browsers')

    def save(self, **values):
        self.s.update(values)
        write_json(STATE, self.s)
        STATE.chmod(0o600)

    def run(self, args, evidence=None, check=True, timeout=120):
        start = now()
        result = subprocess.run(args, env=self.env, text=True, capture_output=True,
                                timeout=timeout, cwd=ROOT)
        if evidence:
            EVIDENCE.mkdir(parents=True, exist_ok=True)
            (EVIDENCE / evidence).write_text(
                f'Time: {start}\nCommand: {json.dumps(args)}\nExit: {result.returncode}\n'
                + result.stdout + result.stderr)
        if check and result.returncode:
            raise RuntimeError(f'{args[:3]} failed ({result.returncode}): {result.stderr}')
        return result

    def aws(self, service, operation, *args, evidence=None):
        result = self.run(['aws', '--profile', self.profile, '--region', REGION,
                           '--output', 'json', service, operation, *args], timeout=900)
        data = json.loads(result.stdout) if result.stdout.strip() else {}
        if evidence:
            write_json(EVIDENCE / evidence, data)
        return data

    def ec2(self, operation, *args, **kw):
        return self.aws('ec2', operation, *args, **kw)

    def tags(self, kind):
        return json.dumps([{'ResourceType': kind, 'Tags': [
            {'Key': 'Project', 'Value': self.s['name']},
            {'Key': 'Name', 'Value': self.s['name']}]}])

    def preflight(self, billable=False, confirmed=False, iam_reviewed=False):
        for tool in ('aws', 'ssh', 'ssh-keygen', 'curl', 'dot'):
            require(shutil.which(tool, path=self.env['PATH']), f'Missing tool: {tool}')
        identity = self.aws('sts', 'get-caller-identity')
        require(not identity['Arn'].endswith(':root'), 'Root identity is prohibited.')
        if self.s:
            require(self.s['account'] == identity['Account'] and self.s['profile'] == self.profile,
                    'Saved account/profile mismatch; refusing to operate.')
        if billable:
            require(confirmed, 'Free-tier conditions must be confirmed: --free-tier-confirmed')
            require(iam_reviewed, 'Review effective IAM permissions: --iam-reviewed')
            from playwright.sync_api import sync_playwright
            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = self.env['PLAYWRIGHT_BROWSERS_PATH']
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, channel='chromium')
                browser.close()
        return identity

    def create(self, key, kind, operation, field, *args):
        if key in self.s:
            return self.s[key]
        # Recover a resource if the previous call succeeded before its response/state was saved.
        queries = {
            'vpc': ('describe-vpcs', 'Vpcs', 'VpcId'),
            'subnet': ('describe-subnets', 'Subnets', 'SubnetId'),
            'internet-gateway': ('describe-internet-gateways', 'InternetGateways', 'InternetGatewayId'),
            'route-table': ('describe-route-tables', 'RouteTables', 'RouteTableId'),
            'security-group': ('describe-security-groups', 'SecurityGroups', 'GroupId'),
        }
        op, collection, id_field = queries[kind]
        found = self.ec2(op, '--filters', f'Name=tag:Project,Values={self.s["name"]}')[collection]
        require(len(found) <= 1, f'Ambiguous resources: {key}')
        if found:
            value = found[0][id_field]
        else:
            result = self.ec2(operation, *args, '--tag-specifications', self.tags(kind))
            for part in field.split('.'):
                result = result[part]
            value = result
        self.save(**{key: value})
        print(f'{key}: {value}', flush=True)
        return value

    def provision(self, identity):
        require(not self.s.get('cleaned'), 'This run was cleaned. Archive .lab/state.json before a new run.')
        if not self.s:
            self.save(name='cloud-lab-' + uuid.uuid4().hex[:12], account=identity['Account'],
                      profile=self.profile, started=now(), token=str(uuid.uuid4()))
        write_json(EVIDENCE / 'identity.json', identity)
        vpc = self.create('vpc', 'vpc', 'create-vpc', 'Vpc.VpcId', '--cidr-block', '10.0.0.0/16')
        self.ec2('wait', 'vpc-available', '--vpc-ids', vpc)
        self.ec2('modify-vpc-attribute', '--vpc-id', vpc, '--enable-dns-support', '{"Value":true}')
        subnet = self.create('subnet', 'subnet', 'create-subnet', 'Subnet.SubnetId',
                             '--vpc-id', vpc, '--cidr-block', '10.0.1.0/24')
        igw = self.create('igw', 'internet-gateway', 'create-internet-gateway', 'InternetGateway.InternetGatewayId')
        attached = self.ec2('describe-internet-gateways', '--internet-gateway-ids', igw)['InternetGateways'][0]['Attachments']
        if not attached:
            self.ec2('attach-internet-gateway', '--internet-gateway-id', igw, '--vpc-id', vpc)
        rt = self.create('rt', 'route-table', 'create-route-table', 'RouteTable.RouteTableId', '--vpc-id', vpc)
        table = self.ec2('describe-route-tables', '--route-table-ids', rt)['RouteTables'][0]
        if not any(r.get('DestinationCidrBlock') == '0.0.0.0/0' for r in table['Routes']):
            self.ec2('create-route', '--route-table-id', rt, '--destination-cidr-block', '0.0.0.0/0', '--gateway-id', igw)
        if not any(a.get('SubnetId') == subnet for a in table['Associations']):
            self.ec2('associate-route-table', '--route-table-id', rt, '--subnet-id', subnet)
        sg = self.create('sg', 'security-group', 'create-security-group', 'GroupId', '--vpc-id', vpc,
                         '--group-name', self.s['name'], '--description', 'Cloud lab HTTP and restricted SSH')
        ip = self.run(['curl', '-4fsS', '--max-time', '15', 'https://checkip.amazonaws.com']).stdout.strip()
        ipaddress.IPv4Address(ip)
        cidr = ip + '/32'
        self.save(ssh_cidr=cidr)
        group = self.ec2('describe-security-groups', '--group-ids', sg)['SecurityGroups'][0]
        desired = [{'IpProtocol': 'tcp', 'FromPort': port, 'ToPort': port,
                    'IpRanges': [{'CidrIp': source}]} for port, source in ((80, '0.0.0.0/0'), (22, cidr))]
        if group['IpPermissions']:
            self.ec2('revoke-security-group-ingress', '--group-id', sg,
                     '--ip-permissions', json.dumps(group['IpPermissions']))
        self.ec2('authorize-security-group-ingress', '--group-id', sg, '--ip-permissions', json.dumps(desired))
        key = ROOT / '.lab/id_ed25519'
        if not key.exists():
            self.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)])
        key.chmod(0o600)
        key_name = self.s['name'] + '-key'
        keys = self.ec2('describe-key-pairs', '--filters', f'Name=key-name,Values={key_name}')['KeyPairs']
        if not keys:
            self.ec2('import-key-pair', '--key-name', key_name,
                     '--public-key-material', 'fileb://' + str(key) + '.pub', '--tag-specifications', self.tags('key-pair'))
        self.save(key_name=key_name)
        if 'instance' not in self.s:
            if 'ami' not in self.s:
                images = self.ec2('describe-images', '--owners', 'amazon', '--filters',
                    'Name=name,Values=al2023-ami-2023.*-kernel-6.1-x86_64', 'Name=state,Values=available',
                    'Name=root-device-type,Values=ebs')['Images']
                require(images, 'No AL2023 image found.')
                ami = max(images, key=lambda x: x['CreationDate'])
                self.save(ami=ami['ImageId'], root_device=ami['RootDeviceName'])
            tags = json.loads(self.tags('instance')) + json.loads(self.tags('volume'))
            result = self.ec2('run-instances', '--client-token', self.s['token'], '--image-id', self.s['ami'],
                '--instance-type', 't3.micro', '--count', '1', '--key-name', key_name,
                '--subnet-id', subnet, '--security-group-ids', sg, '--associate-public-ip-address',
                '--credit-specification', 'CpuCredits=standard', '--metadata-options', 'HttpTokens=required,HttpEndpoint=enabled',
                '--block-device-mappings', json.dumps([{'DeviceName': self.s['root_device'],
                    'Ebs': {'VolumeSize': 8, 'VolumeType': 'gp3', 'DeleteOnTermination': True}}]),
                '--tag-specifications', json.dumps(tags))
            self.save(instance=result['Instances'][0]['InstanceId'])
        self.ec2('wait', 'instance-running', '--instance-ids', self.s['instance'])
        self.ec2('wait', 'instance-status-ok', '--instance-ids', self.s['instance'])
        instance = self.ec2('describe-instances', '--instance-ids', self.s['instance'], evidence='instance.json')['Reservations'][0]['Instances'][0]
        self.save(ip=instance['PublicIpAddress'], volume=instance['BlockDeviceMappings'][0]['Ebs']['VolumeId'])
        routes = self.ec2('describe-route-tables', '--route-table-ids', rt, evidence='routes.json')['RouteTables'][0]
        require(any(r.get('DestinationCidrBlock') == '0.0.0.0/0' and r.get('GatewayId') == igw
                    and r.get('State') == 'active' for r in routes['Routes']), 'Default route verification failed')
        require(any(a.get('SubnetId') == subnet for a in routes['Associations']), 'Subnet association missing')
        self.ec2('describe-security-groups', '--group-ids', sg, evidence='security-group.json')

    def ssh(self, command, evidence=None, check=True):
        return self.run(['ssh', '-i', str(ROOT / '.lab/id_ed25519'), '-o', 'BatchMode=yes',
                         '-o', 'ConnectTimeout=10', '-o', 'StrictHostKeyChecking=accept-new',
                         '-o', 'UserKnownHostsFile=' + str(ROOT / '.lab/known_hosts'),
                         'ec2-user@' + self.s['ip'], command], evidence, check, timeout=300)

    def health(self, evidence, success=True):
        result = self.run(['curl', '--noproxy', '*', '-sS', '-i', '--fail', '--max-time', '15',
                           'http://' + self.s['ip'] + '/health'], evidence, check=False)
        if success:
            require(result.returncode == 0 and result.stdout.splitlines()[0].split()[1] == '200'
                    and result.stdout.strip().endswith('\nOK'), 'Expected external HTTP 200 and OK')
        else:
            require(result.returncode != 0, 'Failure reproduction unexpectedly succeeded')
        return result

    def verify(self):
        for attempt in range(24):
            r = self.ssh('whoami', check=False)
            if r.returncode == 0:
                break
            time.sleep(5)
        require(r.returncode == 0, 'SSH not ready')
        self.ssh('set -e; whoami; curl -I --fail --max-time 15 https://example.com', 'ssh-outbound.txt')
        self.ssh("set -e; sudo cloud-init status --wait; sudo dnf install -y nginx; "
                 "printf 'OK\\n' | sudo tee /usr/share/nginx/html/health; sudo systemctl enable --now nginx", 'install.txt')
        health_config = 'location = /health { default_type text/plain; return 200 "OK\\n"; }'
        self.ssh("set -e; printf '%s\\n' " + shlex.quote(health_config) +
                 ' | sudo tee /etc/nginx/default.d/health.conf; sudo nginx -t; sudo systemctl reload nginx',
                 'health-config.txt')
        self.ssh('set -e; systemctl is-active nginx; curl -i --fail http://localhost; '
                 'curl -i --fail http://localhost/health', 'localhost.txt')
        self.health('external-health.txt')
        self.capture()
        try:
            self.ssh('sudo systemctl stop nginx', 'stop.txt')
            self.health('failure.txt', success=False)
            self.ssh('systemctl is-active nginx; sudo ss -lntp; '
                     'sudo journalctl -u nginx -n 30 --no-pager', 'diagnosis.txt')
            self.ssh('test "$(systemctl is-active nginx)" = inactive && '
                     'test -z "$(sudo ss -H -lnt sport = :80)"', 'diagnosis-check.txt')
        finally:
            self.ssh('sudo systemctl start nginx', 'restart.txt')
        self.health('recovered.txt')
        self.save(verified=now())

    def capture(self):
        from playwright.sync_api import sync_playwright
        os.environ['PLAYWRIGHT_BROWSERS_PATH'] = self.env['PLAYWRIGHT_BROWSERS_PATH']
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, channel='chromium')
            context = browser.new_context(viewport={'width': 1280, 'height': 800})
            context.tracing.start(screenshots=True, snapshots=True)
            page = context.new_page()
            url = 'http://' + self.s['ip'] + '/health'
            response = page.goto(url, wait_until='load', timeout=30000)
            result = {'url': page.url, 'requested_url': url, 'checked_at': now(),
                      'status': response.status if response else None,
                      'body': page.locator('body').inner_text().strip()}
            page.screenshot(path=str(EVIDENCE / 'external-health.png'), full_page=True)
            context.tracing.stop(path=str(EVIDENCE / 'browser-trace.zip'))
            browser.close()
            write_json(EVIDENCE / 'external-health.json', result)
            require(result['status'] == 200 and result['body'] == 'OK', 'Browser validation failed')

    def cleanup(self):
        if not self.s:
            return
        # Verify ownership before any deletion, and discover resources created before state was saved.
        specs = [('vpc', 'describe-vpcs', 'Vpcs', 'VpcId'), ('subnet', 'describe-subnets', 'Subnets', 'SubnetId'),
                 ('igw', 'describe-internet-gateways', 'InternetGateways', 'InternetGatewayId'),
                 ('rt', 'describe-route-tables', 'RouteTables', 'RouteTableId'),
                 ('sg', 'describe-security-groups', 'SecurityGroups', 'GroupId'),
                 ('key_name', 'describe-key-pairs', 'KeyPairs', 'KeyName')]
        existing = {}
        for key, op, collection, field in specs:
            rows = self.ec2(op, '--filters', f'Name=tag:Project,Values={self.s["name"]}')[collection]
            require(len(rows) <= 1, f'Ambiguous cleanup resources: {key}')
            if rows:
                value = rows[0][field]
                require(key not in self.s or self.s[key] == value, 'Cleanup ownership mismatch')
                self.save(**{key: value})
                existing[key] = value
        instances = self.ec2('describe-instances', '--filters', f'Name=tag:Project,Values={self.s["name"]}')
        ids = [i['InstanceId'] for r in instances['Reservations'] for i in r['Instances'] if i['State']['Name'] != 'terminated']
        require(len(ids) <= 1, 'Ambiguous EC2 cleanup targets')
        if ids and self.s.get('instance'):
            require(ids == [self.s['instance']], 'EC2 cleanup ownership mismatch')
        if ids:
            self.save(instance=ids[0])
            self.ec2('terminate-instances', '--instance-ids', *ids, evidence='terminate.json')
            self.ec2('wait', 'instance-terminated', '--instance-ids', *ids)
        instance_filter = f'Name=instance-id,Values={self.s["instance"]}' if self.s.get('instance') else f'Name=tag:Project,Values={self.s["name"]}'
        final_instances = self.ec2('describe-instances', '--filters', instance_filter, evidence='ec2-final.json')
        require(all(i['State']['Name'] == 'terminated' for r in final_instances['Reservations']
                    for i in r['Instances']), 'An instance is still running')
        for attempt in range(60):
            volumes = self.ec2('describe-volumes', '--filters', f'Name=tag:Project,Values={self.s["name"]}')['Volumes']
            if not volumes:
                break
            for volume in volumes:
                if volume['State'] == 'available':
                    self.ec2('delete-volume', '--volume-id', volume['VolumeId'])
            time.sleep(5)
        require(not volumes, 'Volumes still present; rerun cleanup')
        if 'rt' in existing:
            table = self.ec2('describe-route-tables', '--route-table-ids', existing['rt'])['RouteTables'][0]
            for assoc in table['Associations']:
                if not assoc.get('Main'):
                    self.ec2('disassociate-route-table', '--association-id', assoc['RouteTableAssociationId'])
        actions = [('subnet', 'delete-subnet', '--subnet-id'), ('rt', 'delete-route-table', '--route-table-id'),
                   ('sg', 'delete-security-group', '--group-id'), ('igw', 'delete-internet-gateway', '--internet-gateway-id'),
                   ('vpc', 'delete-vpc', '--vpc-id'), ('key_name', 'delete-key-pair', '--key-name')]
        for key, op, flag in actions:
            if key not in existing:
                continue
            if key == 'igw':
                attachments = self.ec2('describe-internet-gateways', '--internet-gateway-ids', existing[key])['InternetGateways'][0]['Attachments']
                for attachment in attachments:
                    require(attachment['VpcId'] == self.s.get('vpc'), 'IGW belongs to another VPC')
                    self.ec2('detach-internet-gateway', '--internet-gateway-id', existing[key], '--vpc-id', attachment['VpcId'])
            for attempt in range(30):
                try:
                    self.ec2(op, flag, existing[key])
                    break
                except RuntimeError as exc:
                    if 'DependencyViolation' not in str(exc) or attempt == 29:
                        raise
                    time.sleep(5)
        checks = {}
        for key, op, collection, field in specs:
            filters = {'vpc': 'vpc-id', 'subnet': 'subnet-id', 'igw': 'internet-gateway-id',
                       'rt': 'route-table-id', 'sg': 'group-id', 'key_name': 'key-name'}
            resource_filter = f'Name={filters[key]},Values={self.s[key]}' if key in self.s else f'Name=tag:Project,Values={self.s["name"]}'
            data = self.ec2(op, '--filters', resource_filter, evidence=f'{key}-final.json')
            require(not data[collection], f'Resource remains: {key}')
            checks[key] = {'id': self.s.get(key), 'remaining': 0}
        for op, collection, filename in [('describe-volumes', 'Volumes', 'ebs-final.json'),
                                          ('describe-addresses', 'Addresses', 'eip-final.json')]:
            data = self.ec2(op, '--filters', f'Name=tag:Project,Values={self.s["name"]}', evidence=filename)
            require(not data[collection], f'Resources remain: {collection}')
        if self.s.get('volume'):
            data = self.ec2('describe-volumes', '--filters', f'Name=volume-id,Values={self.s["volume"]}', evidence='ebs-final.json')
            require(not data['Volumes'], 'Saved EBS volume still exists')
        if self.s.get('vpc'):
            data = self.ec2('describe-network-interfaces', '--filters', f'Name=vpc-id,Values={self.s["vpc"]}', evidence='eni-final.json')
            require(not data['NetworkInterfaces'], 'Network interfaces remain')
        self.save(cleaned=now())
        write_json(EVIDENCE / 'cleanup.json', {'checked_at': self.s['cleaned'], 'resources': checks,
                    'never_created': ['Elastic IP', 'NAT Gateway', 'ELB/ALB', 'RDS']})
        private_key = ROOT / '.lab/id_ed25519'
        private_key.unlink(missing_ok=True)
        self.cleanup_report()

    def cleanup_report(self):
        rows = '\n'.join(f'| {label} | {self.s.get(key, "미생성")} | 삭제 확인 | {self.s["cleaned"]} | [조회](evidence/{key}-final.json) |'
                         for key, label in [('vpc','VPC'), ('subnet','Subnet'), ('igw','IGW'), ('rt','Route Table'), ('sg','Security Group'), ('key_name','Key Pair')])
        (ROOT / 'docs/cleanup-checklist.md').write_text('# 리소스 정리 체크리스트\n\n'
            '| 리소스 | ID | 상태 | 확인 시각 | 근거 |\n|---|---|---|---|---|\n' + rows + '\n'
            f'| EC2 | {self.s.get("instance", "미생성")} | 종료/잔여 없음 확인 | {self.s["cleaned"]} | [조회](evidence/ec2-final.json) |\n'
            f'| EBS | {self.s.get("volume", "미생성")} | 잔여 없음 확인 | {self.s["cleaned"]} | [조회](evidence/ebs-final.json) |\n'
            '\nElastic IP, NAT Gateway, ELB/ALB, RDS: 이 실행에서 미생성.\n'
            '범위: 이번 실행의 Project 태그 및 저장한 ID. 계정 전체 비용이 0이라는 보장은 아님.\n')

    def report(self):
        require(self.s.get('verified') and self.s.get('cleaned'), 'Real verification and cleanup must both succeed before submission.')
        s = self.s
        dot = f'''digraph Lab {{
 rankdir=TB; node [shape=box]; external [label="External client / Playwright"];
 subgraph cluster_vpc {{ label="VPC {s['vpc']} / 10.0.0.0/16 / Seoul";
 igw [label="Internet Gateway {s['igw']}"];
 rt [label="Route Table {s['rt']}\\n0.0.0.0/0 -> IGW"];
 subgraph cluster_subnet {{ label="Public Subnet {s['subnet']} / 10.0.1.0/24";
 sg [label="SG {s['sg']}\\nHTTP 80: any IPv4\\nSSH 22: {s['ssh_cidr']}"];
 ec2 [label="EC2 {s['instance']}\\n{s['ip']} / Nginx :80\\nEBS 8 GiB / health: 200 OK"]; }} }}
 external -> igw -> sg -> ec2; rt -> igw [style=dashed]; rt -> ec2 [style=dashed,label="subnet association"]; }}'''
        (ROOT / 'docs/architecture.dot').write_text(dot)
        self.run(['dot', '-Tpng', 'docs/architecture.dot', '-o', 'docs/architecture.png'])
        (ROOT / 'docs/troubleshooting.md').write_text(f'''# 트러블슈팅: Nginx 중지 재현

검증 완료 시각: {s['verified']}. 이 오류는 실습 인스턴스에서 의도적으로 재현했다.

- 증상: Nginx를 중지한 후 외부 /health 요청이 실패했다. [실제 오류](evidence/failure.txt)
- 가설: 웹 서버 프로세스 중지로 80 포트 리스너가 사라졌다.
- 검증: 서비스 inactive와 80 포트 리스너 부재를 명령으로 검증했다. [로그](evidence/diagnosis.txt), [검증 종료 코드](evidence/diagnosis-check.txt)
- 조치: sudo systemctl start nginx 실행. [기록](evidence/restart.txt)
- 결과: 외부 HTTP 200 및 OK를 재확인했다. [복구 응답](evidence/recovered.txt)
- 재발방지: enable 설정을 유지하고 배포 후 서비스 상태·로컬 응답·외부 /health를 함께 검사한다.
''')
        first_error = EVIDENCE / 'first-run-browser-error.txt'
        if first_error.exists():
            with (ROOT / 'docs/troubleshooting.md').open('a') as report:
                report.write('\n## 실제 발생 오류: 브라우저가 /health를 다운로드로 처리\n\n'
                    '- 증상: curl은 HTTP 200 / OK였지만 Playwright에서 `Page.goto: Download is starting` 발생. '
                    '[원본 오류](evidence/first-run-browser-error.txt), [응답 헤더](evidence/first-run-health.txt)\n'
                    '- 가설: 확장자 없는 정적 파일에 적용된 Content-Type이 브라우저 다운로드를 유발했다.\n'
                    '- 검증: 실제 응답의 `Content-Type: application/octet-stream`과 브라우저 오류를 대조했다.\n'
                    '- 조치: 첫 실행 리소스를 삭제한 뒤 전용 `/health` location에 `default_type text/plain`과 '
                    '`return 200`을 설정하고 nginx 설정 검증 및 reload를 수행했다. '
                    '[설정 로그](evidence/health-config.txt), [첫 실행 정리](evidence/first-run-cleanup.json)\n'
                    '- 결과: 재실행에서 외부 응답과 Chromium 화면의 OK를 확인하고 PNG를 저장했다. '
                    '[성공 응답](evidence/external-health.txt), [브라우저 결과](evidence/external-health.json)\n'
                    '- 재발방지: curl 상태뿐 아니라 MIME 형식과 실제 브라우저 렌더링도 배포 검증에 포함한다.\n')
        marker = '<!-- lab-results -->' 
        readme = (ROOT / 'README.md').read_text().split(marker)[0].rstrip()
        readme = readme.replace('- 현재 상태: AWS 인증 성공. 실습 사용자에 ec2:CreateVpc 권한이 없어 실제 배포·증빙은 미실행.',
                                '- 현재 상태: 실제 검증 및 실습 리소스 정리 완료. 아래 실행 결과 참조.')
        (ROOT / 'README.md').write_text(readme + f'''\n\n{marker}
## 외부 접속 검증

- 방식: B — GET /health
- URL: http://{s['ip']}/health
- 검증 시각: {s['verified']}
- 결과: 실제 외부 요청 및 Chromium 접속에서 HTTP 200, OK 확인
- 실습 리소스는 {s['cleaned']}에 정리했다. 현재 URL은 더 이상 서비스하지 않는다.

![실제 브라우저 접속](docs/evidence/external-health.png)

## 제출물

- [아키텍처](docs/architecture.png)
- [트러블슈팅](docs/troubleshooting.md)
- [리소스 정리 체크리스트](docs/cleanup-checklist.md)
- [브라우저 응답](docs/evidence/external-health.json)
''')
        required = ['README.md', 'docs/architecture.png', 'docs/architecture.dot', 'docs/troubleshooting.md',
                    'docs/cleanup-checklist.md', 'docs/evidence/external-health.png', 'docs/evidence/cleanup.json']
        for name in required:
            require((ROOT / name).is_file(), 'Missing submission file: ' + name)
        support = [ROOT / 'KANBAN.md', ROOT / 'requirements.txt']
        support += list((ROOT / 'docs').glob('*.md')) + [ROOT / 'docs/lab-policy.json']
        support += [p for folder in ('scripts', 'tests') for p in (ROOT / folder).iterdir()
                    if p.is_file() and p.suffix in ('.py', '.sh', '.txt')]
        files = sorted(set([ROOT / name for name in required] + support + list(EVIDENCE.glob('*'))))
        files = [p for p in files if p.is_file() and p.name != 'manifest.json']
        manifest = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
        write_json(EVIDENCE / 'manifest.json', manifest)
        (ROOT / 'dist').mkdir(exist_ok=True)
        with zipfile.ZipFile(ROOT / 'dist/submission.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in files + [EVIDENCE / 'manifest.json']:
                archive.write(path, path.relative_to(ROOT))
        print('Submission: dist/submission.zip', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['preflight', 'all', 'cleanup', 'report'])
    parser.add_argument('--profile', default='cloud-lab')
    parser.add_argument('--free-tier-confirmed', action='store_true')
    parser.add_argument('--iam-reviewed', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    (ROOT / '.lab').mkdir(exist_ok=True)
    (ROOT / '.lab').chmod(0o700)
    lab = Lab(args.profile)
    if args.action == 'report':
        lab.report()
        return
    identity = lab.preflight(args.action == 'all', args.free_tier_confirmed, args.iam_reviewed)
    if args.action == 'preflight':
        print('Identity verified:', identity['Arn'])
    elif args.action == 'cleanup':
        lab.cleanup()
    else:
        try:
            lab.provision(identity)
            lab.verify()
        finally:
            if lab.s and not lab.s.get('cleaned'):
                lab.cleanup()
        lab.report()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
