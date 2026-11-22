import pytest

from app.cli import main
from app.orchestrator import Orchestrator, create_run_dir
from app.providers.mock import MockProvider
from app.registry import LANGUAGES, Registry
from conftest import ROOT
from app.registry import ROOT as APP


def test_every_language_has_all_six_roles_and_a_contract():
    names = {p.name for p in (APP / "prompts" / "tr").glob("*.md")}
    assert len(names) == 7 and "_contract.md" in names
    for lang in LANGUAGES:
        assert {p.name for p in (APP / "prompts" / lang).glob("*.md")} == names


def test_registry_picks_the_prompt_folder_by_language():
    tr, en = Registry(lang="tr"), Registry(lang="en")
    assert "KONUŞMA KURALLARI" in tr["cv_writer"].system_prompt(tr.root, "tr")
    prompt = en["cv_writer"].system_prompt(en.root, "en")
    assert "You are the CV Writer" in prompt and "NO FABRICATION" in prompt and "KONUŞMA" not in prompt
    assert "language of the original CV" in prompt
    with pytest.raises(ValueError):
        Registry(lang="fr")


def test_the_rules_are_the_same_in_both_languages():
    """English prompts keep the contract: JSON envelope, evidence quotes, 80-point bar, no fabrication."""
    en = {n: c.system_prompt(APP, "en") for n, c in Registry().cards.items()}
    assert all('{"message"' in p for p in en.values())
    assert "WORD FOR WORD" in en["cv_writer"] and '"claims"' in en["cv_writer"]
    assert '"approve" or "reject"' in en["verifier"] and "must be \"reject\"" in en["verifier"]
    assert "80" in en["recruiter"] and "0 to 100" in en["recruiter"]


class Recording(MockProvider):
    def __init__(self):
        super().__init__()
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        return super().run(request)


def test_english_run_sends_english_prompts_and_tags(tmp_path):
    run_dir = create_run_dir(tmp_path, ROOT / "examples/ilan.md", ROOT / "examples/cv.md")
    provider = Recording()
    Orchestrator(
        provider=provider, run_dir=run_dir,
        job_text=(ROOT / "examples/ilan.md").read_text(encoding="utf-8"),
        cv_text=(ROOT / "examples/cv.md").read_text(encoding="utf-8"),
        ask=lambda gate, state: None, registry=Registry(lang="en"),
    ).run()
    by_skill = {r.skill: r for r in provider.requests}
    assert "You are the Job Analyst" in by_skill["analyze_job"].system_prompt
    assert by_skill["analyze_job"].user_prompt.startswith("Task: analyze_job")
    tailor = by_skill["tailor_cv"].user_prompt
    assert "<original_cv>" in tailor and "<job_summary>" in tailor and "<orijinal_cv>" not in tailor
    assert "Task: verify" in by_skill["verify"].user_prompt
    assert "<code_checks>" in by_skill["verify"].user_prompt
    # Round 2 feedback is in English too.
    second = [r for r in provider.requests if r.skill == "tailor_cv"][1].user_prompt
    assert "<previous_cv>" in second and "<feedback>" in second and "Hiring gap:" in second


def test_turkish_prompts_are_unchanged(tmp_path):
    run_dir = create_run_dir(tmp_path, ROOT / "examples/ilan.md", ROOT / "examples/cv.md")
    provider = Recording()
    Orchestrator(
        provider=provider, run_dir=run_dir, job_text="x " * 30, cv_text="y " * 30,
        ask=lambda gate, state: None,
    ).run()
    tailor = next(r for r in provider.requests if r.skill == "tailor_cv")
    assert tailor.user_prompt.startswith("Görev: tailor_cv") and "<orijinal_cv>" in tailor.user_prompt


def test_cli_dil_en_runs_end_to_end(tmp_path):
    code = main(["--ilan", str(ROOT / "examples/ilan.md"), "--cv", str(ROOT / "examples/cv.md"),
                 "--dil", "en", "--evet", "--hizli", "--runs", str(tmp_path)])
    assert code == 0
    with pytest.raises(SystemExit):
        main(["--ilan", "a", "--cv", "b", "--dil", "fr"])
