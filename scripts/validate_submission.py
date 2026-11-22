"""Validate the final archive against real evidence, without making any AWS calls."""
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
with zipfile.ZipFile(ROOT / 'dist/submission.zip') as archive:
    names = set(archive.namelist())
    required = {'README.md', 'docs/architecture.png', 'docs/troubleshooting.md',
                'docs/cleanup-checklist.md', 'docs/evidence/external-health.png',
                'docs/evidence/external-health.json', 'docs/evidence/manifest.json'}
    assert required <= names, required - names
    assert all(not name.startswith(('.lab/', '.venv/')) and not name.endswith('.pem') for name in names)
    manifest = json.loads(archive.read('docs/evidence/manifest.json'))
    assert set(manifest) == names - {'docs/evidence/manifest.json'}
    for name, digest in manifest.items():
        payload = archive.read(name)
        assert hashlib.sha256(payload).hexdigest() == digest, name
        if name.endswith(('.md', '.json', '.txt', '.py', '.sh', '.dot')):
            assert not re.search(rb'AKIA[A-Z0-9]{16}|-----BEGIN (?:OPENSSH|RSA|EC) PRIVATE KEY-----', payload), name
    for name in ('docs/architecture.png', 'docs/evidence/external-health.png'):
        assert archive.read(name).startswith(b'\x89PNG\r\n\x1a\n'), name
    result = json.loads(archive.read('docs/evidence/external-health.json'))
    assert result['status'] == 200 and result['body'] == 'OK'
    assert 'Content-Type: text/plain' in archive.read('docs/evidence/external-health.txt').decode()
    group = json.loads(archive.read('docs/evidence/security-group.json'))['SecurityGroups'][0]
    rules = group['IpPermissions']
    assert len(rules) == 2
    for rule in rules:
        assert rule['IpProtocol'] == 'tcp' and rule['FromPort'] == rule['ToPort']
        assert not rule.get('Ipv6Ranges') and not rule.get('UserIdGroupPairs')
        cidrs = [entry['CidrIp'] for entry in rule['IpRanges']]
        assert len(cidrs) == 1
        if rule['FromPort'] == 80:
            assert cidrs == ['0.0.0.0/0']
        else:
            assert rule['FromPort'] == 22 and cidrs[0].endswith('/32')
    instances = json.loads(archive.read('docs/evidence/ec2-final.json'))
    assert all(i['State']['Name'] == 'terminated' for r in instances['Reservations'] for i in r['Instances'])
    for filename, field in [('ebs-final.json','Volumes'), ('vpc-final.json','Vpcs'),
            ('subnet-final.json','Subnets'), ('igw-final.json','InternetGateways'),
            ('rt-final.json','RouteTables'), ('sg-final.json','SecurityGroups'),
            ('key_name-final.json','KeyPairs'), ('eni-final.json','NetworkInterfaces'),
            ('eip-final.json','Addresses')]:
        assert json.loads(archive.read('docs/evidence/' + filename))[field] == [], filename
    for name in names:
        if name.endswith('.md'):
            markdown = re.sub(r'```.*?```', '', archive.read(name).decode(), flags=re.S)
            for target in re.findall(r'\]\(([^)]+)\)', markdown):
                if '://' in target or target.startswith('#'):
                    continue
                target = target.split('#')[0]
                resolved = (ROOT / name).parent.joinpath(target).resolve().relative_to(ROOT).as_posix()
                assert resolved in names, (name, target)
print('PASS: archive completeness, hashes, local links, secret exclusion, real HTTP/browser evidence, restricted ports, deletion evidence')
