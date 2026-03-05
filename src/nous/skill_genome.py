"""SkillGenome: adapter to treat OpenClaw skills as Nous agent genomes."""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SkillGenome:
    name: str
    skill_dir: Path
    prompt: str
    tests: str
    history: str
    config: dict = field(default_factory=dict)

    @classmethod
    def load(cls, skill_dir: Path) -> "SkillGenome":
        skill_dir = Path(skill_dir)
        name = skill_dir.name

        prompt_path = skill_dir / "SKILL.md"
        prompt = prompt_path.read_text() if prompt_path.exists() else ""

        tests_path = skill_dir / "TESTS.md"
        tests = tests_path.read_text() if tests_path.exists() else ""

        history_path = skill_dir / "HISTORY.md"
        history = history_path.read_text() if history_path.exists() else ""

        config_path = skill_dir / "config.json"
        config = json.loads(config_path.read_text()) if config_path.exists() else {}

        return cls(
            name=name,
            skill_dir=skill_dir,
            prompt=prompt,
            tests=tests,
            history=history,
            config=config,
        )

    def save_prompt(self, new_prompt: str) -> None:
        """Write updated SKILL.md back to disk."""
        (self.skill_dir / "SKILL.md").write_text(new_prompt)
        self.prompt = new_prompt

    def append_history(self, entry: str) -> None:
        """Append a generation entry to HISTORY.md."""
        history_path = self.skill_dir / "HISTORY.md"
        current = history_path.read_text() if history_path.exists() else ""
        history_path.write_text(current + "\n" + entry)
        self.history = history_path.read_text()

    def increment_version(self) -> None:
        """Bump version in config.json."""
        self.config["version"] = self.config.get("version", 0) + 1
        (self.skill_dir / "config.json").write_text(
            json.dumps(self.config, indent=2)
        )
