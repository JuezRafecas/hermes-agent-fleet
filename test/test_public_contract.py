import html
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PublicRepositoryContractTest(unittest.TestCase):
    def _text(self, relative: str) -> str:
        path = ROOT / relative
        self.assertTrue(path.is_file(), f"missing public file: {relative}")
        return path.read_text(encoding="utf-8")

    def test_required_public_surface_exists(self):
        required = {
            ".env.example",
            ".gitignore",
            "Dockerfile",
            "LICENSE",
            "README.md",
            "agentctl",
            "docker-compose.yml",
            "config/config.yaml",
            "config/SOUL.default.md",
            "config/bin/neon-mcp",
            "config/bin/mongo-mcp",
            "config/skills-shared/shared-file-drop/SKILL.md",
            "config/skills-shared/shared-file-drop/shared-file-upload.mjs",
            "agents/research-analyst/SOUL.md",
            "agents/research-analyst/agent.yaml",
            "agents/research-analyst/profile.env.example",
            "agents/growth-marketer/SOUL.md",
            "agents/growth-marketer/agent.yaml",
            "agents/growth-marketer/profile.env.example",
            "agents/data-ops/SOUL.md",
            "agents/data-ops/agent.yaml",
            "agents/data-ops/profile.env.example",
            "docs/blog.html",
            "docs/fleet-v2.png",
            "scripts/profile-displays.py",
            "test/smoke.sh",
        }
        missing = sorted(path for path in required if not (ROOT / path).exists())
        self.assertEqual(missing, [], f"missing public files: {missing}")

    def test_private_names_and_runtime_files_are_absent(self):
        forbidden = [
            "gi" + "fty",
            "cross" + "up",
            "ape" + "iron",
            "flo" + "wy",
            "wo" + "ki",
            "ra" + "fa",
            "kap" + "so",
            "zer" + "nio",
        ]
        allowed_owner = "juez" + "rafecas"
        owner_url = "https://github.com/" + "Juez" + "Rafecas/hermes-agent-fleet"
        findings = []
        owner_hits = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or any(part.startswith(".git") for part in path.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            relative = path.relative_to(ROOT).as_posix()
            lowered = text.lower()
            for term in forbidden:
                if term in lowered:
                    findings.append((relative, term))
            if allowed_owner in lowered:
                owner_hits.append(relative)
        self.assertEqual(findings, [])
        self.assertEqual(owner_hits, ["README.md"])
        self.assertIn(owner_url, self._text("README.md"))

        forbidden_paths = [
            ROOT / ("agents/_" + "gi" + "fty-shared"),
            ROOT / ("agents/" + "sales" + "pilot-curator"),
            ROOT / "share",
            ROOT / ".agentctl.env",
            ROOT / ".profiles-snapshot",
        ]
        self.assertFalse(any(path.exists() for path in forbidden_paths))
        self.assertFalse(any(path.name.endswith(".local") for path in ROOT.rglob("*")))

    def test_generic_storage_and_commands_are_documented_and_implemented(self):
        agentctl = self._text("agentctl")
        for command in ("backup-s3", "snapshots-s3", "restore-s3", "skills-sync", "gh-sync"):
            self.assertIn(command, agentctl)
        for variable in (
            "SHARE_PUBLIC_URL",
            "S3_ENDPOINT",
            "S3_BUCKET",
            "S3_ACCESS_KEY_ID",
            "S3_SECRET_ACCESS_KEY",
        ):
            self.assertIn(variable, self._text(".env.example"))
        uploader = self._text(
            "config/skills-shared/shared-file-drop/shared-file-upload.mjs"
        )
        self.assertNotIn("R2_", uploader)
        self.assertIn("SHARE_PUBLIC_URL", uploader)

    def test_example_agents_cover_the_three_documented_patterns(self):
        research = self._text("agents/research-analyst/agent.yaml")
        growth = self._text("agents/growth-marketer/agent.yaml")
        data_ops = self._text("agents/data-ops/agent.yaml")
        self.assertIn("FIRECRAWL", research)
        self.assertIn("agent-browser", research)
        self.assertIn("SOCIAL_MCP", growth)
        self.assertIn("image_gen", growth)
        self.assertIn("mongo-mcp", data_ops)
        self.assertIn("neon-mcp", data_ops)

    def test_blog_is_english_and_within_requested_length(self):
        article = self._text("docs/blog.html")
        self.assertIn('<html lang="en">', article)
        self.assertIn("./fleet-v2.png", article)
        self.assertIn(
            "https://github.com/" + "Juez" + "Rafecas/hermes-agent-fleet",
            html.unescape(article),
        )
        visible = re.sub(r"<style.*?</style>", " ", article, flags=re.DOTALL)
        visible = re.sub(r"<[^>]+>", " ", visible)
        words = re.findall(r"\b[\w’'-]+\b", html.unescape(visible))
        self.assertGreaterEqual(len(words), 1400)
        self.assertLessEqual(len(words), 1900)


if __name__ == "__main__":
    unittest.main()
