import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'verify_recovery_bundle.py'
SPEC = importlib.util.spec_from_file_location('verify_recovery_bundle', SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RecoveryBundleTests(unittest.TestCase):
    def test_oci_image_id_is_not_config_id(self):
        with tempfile.TemporaryDirectory() as temp:
            blobs = {}

            def blob(data):
                data = json.dumps(data).encode() if isinstance(data, dict) else data
                digest = hashlib.sha256(data).hexdigest()
                blobs['blobs/sha256/' + digest] = data
                return {'digest': 'sha256:' + digest, 'size': len(data)}

            config = blob({'architecture': 'amd64', 'os': 'linux'})
            layer = blob(b'fake layer for hash check')
            image = blob({'config': config, 'layers': [layer]})
            image['platform'] = {'architecture': 'amd64', 'os': 'linux'}
            index = blob({'manifests': [image]})
            blobs['index.json'] = json.dumps({'manifests': [index]}).encode()
            blobs['manifest.json'] = json.dumps([{
                'Config': 'blobs/' + config['digest'].replace(':', '/'),
                'Layers': ['blobs/' + layer['digest'].replace(':', '/')],
            }]).encode()
            path = Path(temp) / 'images.tar.gz'
            with tarfile.open(path, 'w:gz') as archive:
                for name, data in blobs.items():
                    member = tarfile.TarInfo(name)
                    member.size = len(data)
                    archive.addfile(member, io.BytesIO(data))
            result = MODULE.verify_images(path, [{'Id': index['digest'], 'Architecture': 'amd64', 'Os': 'linux'}])
            self.assertEqual(result, {index['digest']: config['digest']})
            with self.assertRaises(AssertionError):
                MODULE.verify_images(path, [{'Id': config['digest'], 'Architecture': 'amd64', 'Os': 'linux'}])

    def test_stream_digest(self):
        data = b'backup-check' * 200000
        self.assertEqual(MODULE.sha256(io.BytesIO(data)), hashlib.sha256(data).hexdigest())

    def test_safe_archive_paths(self):
        self.assertEqual(MODULE.safe_name('rootfs/opt/example/config.json'), 'rootfs/opt/example/config.json')
        for name in ('/etc/passwd', '../secret', 'rootfs/../../secret'):
            with self.assertRaises(ValueError):
                MODULE.safe_name(name)

    def test_incomplete_bundle_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'INCOMPLETE').touch()
            with self.assertRaisesRegex(ValueError, 'Incomplete'):
                MODULE.verify(root)

    def test_corrupted_bundle_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'files.tar.gz').write_bytes(b'changed')
            (root / 'SHA256SUMS').write_text(hashlib.sha256(b'original').hexdigest() + '  files.tar.gz\n')
            with self.assertRaisesRegex(AssertionError, 'SHA256 mismatch'):
                MODULE.verify(root)

    def test_checksum_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'SHA256SUMS').write_text('0' * 64 + '  ../outside\n')
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                MODULE.verify(root)


if __name__ == '__main__':
    unittest.main()
