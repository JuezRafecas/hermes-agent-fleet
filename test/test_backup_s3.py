import os
import shlex
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


PLATFORM_DIR = Path(__file__).resolve().parents[1]
AGENTCTL = PLATFORM_DIR / "agentctl"


class BackupS3ContractTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.data = self.root / "data"
        self.data.mkdir()
        (self.data / ".env").write_text(
            "BACKUP_S3_ENDPOINT=https://s3.test.invalid\n"
            "BACKUP_S3_BUCKET=fleet-backups\n"
            "BACKUP_S3_ACCESS_KEY_ID=example-access\n"
            "BACKUP_S3_SECRET_ACCESS_KEY=example-secret\n"
            "BACKUP_S3_REGION=us-east-1\n"
            "RESTIC_PASSWORD=" + "c" * 48 + "\n"
        )
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        self.log = self.root / "restic.log"
        self.repository_marker = self.root / "repository-initialized"
        self._write_executable(
            self.bin_dir / "id",
            "#!/bin/sh\n"
            "if [ \"${1:-}\" = -u ]; then printf '0\\n'; else /usr/bin/id \"$@\"; fi\n",
        )
        self._write_executable(
            self.bin_dir / "restic",
            "#!/bin/sh\n"
            "set -eu\n"
            "[ \"${RESTIC_REPOSITORY:-}\" = s3:https://s3.test.invalid/fleet-backups ]\n"
            "[ \"${AWS_ACCESS_KEY_ID:-}\" = example-access ]\n"
            "[ \"${AWS_SECRET_ACCESS_KEY:-}\" = example-secret ]\n"
            "[ \"${AWS_DEFAULT_REGION:-}\" = us-east-1 ]\n"
            "[ \"${RESTIC_PASSWORD:-}\" = \"$(printf 'c%.0s' $(seq 1 48))\" ]\n"
            "printf '%s\\n' \"$(printf '%s\\n' \"$@\" | sed 's/ /\\\\ /g' | paste -sd' ' -)\" >> \"$RESTIC_TEST_LOG\"\n"
            "case \"${1:-}\" in\n"
            "  snapshots) [ -f \"$RESTIC_TEST_REPOSITORY_MARKER\" ] || exit 1 ;;\n"
            "  init) : > \"$RESTIC_TEST_REPOSITORY_MARKER\" ;;\n"
            "esac\n",
        )

    def tearDown(self):
        self.tempdir.cleanup()

    @staticmethod
    def _write_executable(path: Path, contents: str) -> None:
        path.write_text(contents)
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{self.bin_dir}:{env['PATH']}",
                "HERMES_ROOT": str(self.root),
                "RESTIC_TEST_LOG": str(self.log),
                "RESTIC_TEST_REPOSITORY_MARKER": str(self.repository_marker),
            }
        )
        return subprocess.run(
            [str(AGENTCTL), *args],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def _commands(self) -> list[list[str]]:
        return [shlex.split(line) for line in self.log.read_text().splitlines()]

    def test_backup_initializes_once_and_applies_retention(self):
        first = self._run("backup-s3")
        self.assertEqual(first.returncode, 0, first.stderr)
        commands = self._commands()
        self.assertEqual(
            [command[0] for command in commands],
            ["snapshots", "init", "backup", "forget"],
        )
        self.assertEqual(commands[2][1], str(self.data))
        self.assertEqual(
            commands[3],
            ["forget", "--keep-daily", "14", "--keep-weekly", "8", "--prune"],
        )

        self.log.unlink()
        second = self._run("backup-s3")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(
            [command[0] for command in self._commands()],
            ["snapshots", "backup", "forget"],
        )

    def test_restore_requires_a_new_absolute_destination(self):
        self.repository_marker.touch()
        destination = self.root / "restore-drill"
        result = self._run("restore-s3", "latest", str(destination))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self._commands(), [["restore", "latest", "--target", str(destination)]]
        )

        destination.mkdir()
        rejected = self._run("restore-s3", "latest", str(destination))
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("already exists", rejected.stderr)

        relative = self._run("restore-s3", "latest", "restore-drill")
        self.assertNotEqual(relative.returncode, 0)
        self.assertIn("absolute", relative.stderr)

    def test_snapshots_is_read_only_and_systemd_uses_generic_command(self):
        self.repository_marker.touch()
        result = self._run("snapshots-s3", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self._commands(), [["snapshots", "--json"]])
        service = (PLATFORM_DIR / "systemd/hermes-backup.service").read_text()
        self.assertIn("ExecStart=/srv/hermes/agentctl backup-s3\n", service)


if __name__ == "__main__":
    unittest.main()
