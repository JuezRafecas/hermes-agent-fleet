import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


PLATFORM_DIR = Path(__file__).resolve().parents[1]
DISPLAY_SCRIPT = PLATFORM_DIR / "scripts" / "profile-displays.py"
AGENTCTL = PLATFORM_DIR / "agentctl"


class ProfileDisplayContractTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(
            DISPLAY_SCRIPT.is_file(),
            "profile-displays.py must own the deterministic display mapping",
        )
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.data = self.root / "data"
        (self.data / "profiles").mkdir(parents=True)

    def tearDown(self):
        if hasattr(self, "tempdir"):
            self.tempdir.cleanup()

    def _profile(self, name: str) -> None:
        (self.data / "profiles" / name).mkdir()

    def _run_script(
        self, *args: str, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(DISPLAY_SCRIPT), *args],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def _mapping(self) -> dict[str, str]:
        return json.loads((self.data / ".displays.json").read_text())

    def test_initial_mapping_is_sorted_and_reserves_display_100_for_default(self):
        self._profile("beta-agent")
        self._profile("alpha-agent")

        result = self._run_script("ensure", str(self.data))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self._mapping(),
            {
                "alpha-agent": ":101",
                "default": ":100",
                "beta-agent": ":102",
            },
        )

    def test_existing_assignments_are_stable_and_new_profiles_take_lowest_free(self):
        self._profile("alpha-agent")
        self._profile("beta-agent")
        (self.data / ".displays.json").write_text(
            json.dumps({"default": ":100", "alpha-agent": ":105"})
        )

        result = self._run_script("ensure", str(self.data))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self._mapping()["alpha-agent"], ":105")
        self.assertEqual(self._mapping()["beta-agent"], ":101")

    def test_pool_exhaustion_fails_without_publishing_a_partial_mapping(self):
        for index in range(1, 11):
            self._profile(f"profile-{index:02d}")

        result = self._run_script("ensure", str(self.data))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("display pool exhausted", result.stderr)
        self.assertFalse((self.data / ".displays.json").exists())

    def test_current_display_cross_checks_session_profile_and_profile_home(self):
        mapping_path = self.data / ".displays.json"
        mapping_path.write_text(
            json.dumps({"default": ":100", "alpha-agent": ":101"})
        )
        env = os.environ.copy()
        env.update(
            {
                "HERMES_SESSION_PROFILE": "alpha-agent",
                "HERMES_HOME": "/opt/data/profiles/alpha-agent",
            }
        )

        resolved = self._run_script("current", str(mapping_path), env=env)
        self.assertEqual(resolved.returncode, 0, resolved.stderr)
        self.assertEqual(resolved.stdout, ":101\n")

        env["HERMES_HOME"] = "/opt/data/profiles/beta-agent"
        rejected = self._run_script("current", str(mapping_path), env=env)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("profile context mismatch", rejected.stderr)

    def test_agentctl_displays_repairs_and_lists_the_mapping_without_docker(self):
        self._profile("alpha-agent")
        env = os.environ.copy()
        env["HERMES_ROOT"] = str(self.root)

        result = subprocess.run(
            [str(AGENTCTL), "displays"],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("default", result.stdout)
        self.assertIn(":100", result.stdout)
        self.assertIn("alpha-agent", result.stdout)
        self.assertIn(":101", result.stdout)

    def test_runtime_contract_has_ten_xvfb_processes_and_profile_aware_driver(self):
        xvfb = (PLATFORM_DIR / "s6" / "xvfb" / "run").read_text()
        dockerfile = (PLATFORM_DIR / "Dockerfile").read_text()
        compose = (PLATFORM_DIR / "docker-compose.yml").read_text()
        wrapper = PLATFORM_DIR / "config" / "bin" / "cua-driver"

        self.assertIn("{100..109}", xvfb)
        self.assertIn("wait -n", xvfb)
        self.assertNotIn("display :99", xvfb)
        self.assertTrue(wrapper.is_file())
        self.assertIn("/usr/local/libexec/cua-driver", wrapper.read_text())
        self.assertIn("HERMES_CUA_DRIVER_CMD=/usr/local/bin/cua-driver", dockerfile)
        self.assertIn("BASH_ENV=/usr/local/share/hermes/profile-display-env.sh", dockerfile)
        self.assertIn(
            "install -d -m 0755 /usr/local/share/hermes", dockerfile
        )
        self.assertIn('DISPLAY: ":100"', compose)
        self.assertNotIn('DISPLAY: ":99"', compose)


if __name__ == "__main__":
    unittest.main()
