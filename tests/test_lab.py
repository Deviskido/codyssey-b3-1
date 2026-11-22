import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('lab', Path(__file__).resolve().parents[1] / 'scripts/lab.py')
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)


class LabTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patches = [patch.object(lab, 'ROOT', self.root),
                        patch.object(lab, 'STATE', self.root / '.lab/state.json'),
                        patch.object(lab, 'EVIDENCE', self.root / 'docs/evidence')]
        for p in self.patches:
            p.start()
        self.addCleanup(self.temp.cleanup)
        for p in self.patches:
            self.addCleanup(p.stop)
        self.runner = lab.Lab('cloud-lab')

    def test_no_submission_without_real_verification_and_cleanup(self):
        self.runner.s = {'verified': 'test'}
        with self.assertRaisesRegex(RuntimeError, 'verification and cleanup'):
            self.runner.report()
        self.assertFalse((self.root / 'dist').exists())

    def test_root_identity_rejected(self):
        with patch.object(lab.shutil, 'which', return_value='/bin/test'), patch.object(
                self.runner, 'aws', return_value={'Arn': 'arn:aws:iam::123:root', 'Account': '123'}):
            with self.assertRaisesRegex(RuntimeError, 'Root identity'):
                self.runner.preflight()

    def test_saved_account_mismatch_rejected(self):
        self.runner.s = {'account': '123', 'profile': 'cloud-lab'}
        with patch.object(lab.shutil, 'which', return_value='/bin/test'), patch.object(
                self.runner, 'aws', return_value={'Arn': 'arn:aws:iam::456:user/test', 'Account': '456'}):
            with self.assertRaisesRegex(RuntimeError, 'mismatch'):
                self.runner.preflight()

    def test_cleanup_ownership_mismatch_never_deletes(self):
        self.runner.s = {'name': 'cloud-lab-test', 'vpc': 'vpc-owned'}
        with patch.object(self.runner, 'ec2', return_value={'Vpcs': [{'VpcId': 'vpc-other'}]}) as aws:
            with self.assertRaisesRegex(RuntimeError, 'ownership mismatch'):
                self.runner.cleanup()
            self.assertEqual(aws.call_count, 1)
            self.assertEqual(aws.call_args.args[0], 'describe-vpcs')

    def test_recovers_resource_after_lost_create_response(self):
        self.runner.s = {'name': 'cloud-lab-test'}
        with patch.object(self.runner, 'ec2', return_value={'InternetGateways': [{'InternetGatewayId': 'igw-existing'}]}) as aws:
            value = self.runner.create('igw', 'internet-gateway', 'create-internet-gateway', 'InternetGateway.InternetGatewayId')
            self.assertEqual(value, 'igw-existing')
            self.assertEqual(aws.call_count, 1)
            self.assertEqual(json.loads(lab.STATE.read_text())['igw'], 'igw-existing')

    def test_http_500_and_wrong_body_rejected(self):
        self.runner.s = {'ip': '192.0.2.1'}
        for output in ['HTTP/1.1 500 Error\n\nOK\n', 'HTTP/1.1 200 OK\n\nwrong\n']:
            with patch.object(self.runner, 'run', return_value=subprocess.CompletedProcess([], 0, output, '')):
                with self.assertRaisesRegex(RuntimeError, 'Expected external'):
                    self.runner.health('test.txt')

    def test_nginx_restarted_when_failure_check_fails(self):
        self.runner.s = {'ip': '192.0.2.1'}
        with patch.object(self.runner, 'ssh', return_value=subprocess.CompletedProcess([], 0, '', '')) as ssh, \
             patch.object(self.runner, 'capture'), \
             patch.object(self.runner, 'health', side_effect=[None, RuntimeError('failure check failed')]):
            with self.assertRaisesRegex(RuntimeError, 'failure check failed'):
                self.runner.verify()
            self.assertIn('sudo systemctl start nginx', [c.args[0] for c in ssh.call_args_list])
            self.assertNotIn('verified', self.runner.s)


if __name__ == '__main__':
    unittest.main()
