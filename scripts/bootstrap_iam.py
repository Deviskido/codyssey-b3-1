"""Apply the lab policy to an existing dedicated IAM user using a separate admin profile."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--admin-profile', required=True)
    parser.add_argument('--user', required=True)
    args = parser.parse_args()

    def aws(service, op, *params):
        r = subprocess.run(['aws', '--profile', args.admin_profile, '--region', 'ap-northeast-2',
                            '--output', 'json', service, op, *params], capture_output=True, text=True, check=True)
        return json.loads(r.stdout) if r.stdout.strip() else {}

    identity = aws('sts', 'get-caller-identity')
    if identity['Arn'].endswith(':root'):
        raise RuntimeError('Root identity is prohibited')
    user = aws('iam', 'get-user', '--user-name', args.user)['User']
    attached = aws('iam', 'list-attached-user-policies', '--user-name', args.user)
    inline = aws('iam', 'list-user-policies', '--user-name', args.user)
    groups = aws('iam', 'list-groups-for-user', '--user-name', args.user)
    if attached['AttachedPolicies'] or groups['Groups'] or set(inline['PolicyNames']) - {'CloudLabSeoul'}:
        raise RuntimeError('Existing policies/groups detected. Use a dedicated lab user; no policies were changed.')
    aws('iam', 'put-user-policy', '--user-name', args.user, '--policy-name', 'CloudLabSeoul',
        '--policy-document', 'file://' + str(ROOT / 'docs/lab-policy.json'))
    result = aws('iam', 'get-user-policy', '--user-name', args.user, '--policy-name', 'CloudLabSeoul')
    expected = json.loads((ROOT / 'docs/lab-policy.json').read_text())
    if result['PolicyDocument'] != expected:
        raise RuntimeError('Policy read-back mismatch')
    evidence = ROOT / 'docs/evidence'
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / 'iam-policy.json').write_text(json.dumps({'user_arn': user['Arn'],
        'policy': result['PolicyDocument'], 'attached': attached, 'groups': groups,
        'note': 'Permissions boundaries and organization SCPs can further restrict access.'}, indent=2))
    print('Dedicated user policy applied and read back:', args.user)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
