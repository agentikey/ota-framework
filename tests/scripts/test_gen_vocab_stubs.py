from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from textwrap import dedent

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "scripts" / "gen_vocab_stubs.py"


_SYNTHETIC_TYPES_MD = dedent("""\
    ---
    module: _types
    version: 1.0.0
    ---

    # _types

    ## Identity

    ### `IdentityRef`

    Abstract reference.

    **Form:**

    ```python
    IdentityRef = str
    ```

    **Semantics:**

    - Strings.

    ---

    ### `MessageRef`

    Opaque reference.

    **Form:**

    ```python
    @dataclass(frozen=True)
    class MessageRef:
        id: str
        sent_at: datetime
        adapter: str
    ```

    **Semantics:**

    - Opaque.
    """)


_SYNTHETIC_CAPABILITY_MD = dedent("""\
    ---
    capability: messaging
    version: 1.0.0
    references_types:
      - IdentityRef
      - MessageRef
    ---

    # messaging

    ## Intent

    Send messages.

    ## Verbs

    ### `send_message`

    Dispatches a message.

    **Metadata:**

    ```yaml
    idempotency: best_effort
    required_scopes: ["messaging:send"]
    destructive: false
    ```

    **Signature:**

    ```python
    def send_message(
        target: IdentityRef,
        content: str,
    ) -> MessageRef: ...
    ```
    """)


def _run(vocab_dir: Path, output_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--vocabulary-dir",
            str(vocab_dir),
            "--output-dir",
            str(output_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _write_synthetic_vocab(vocab_dir: Path) -> None:
    vocab_dir.mkdir(parents=True, exist_ok=True)
    (vocab_dir / "_types.md").write_text(_SYNTHETIC_TYPES_MD, encoding="utf-8")
    (vocab_dir / "messaging.md").write_text(_SYNTHETIC_CAPABILITY_MD, encoding="utf-8")


def test_run_creates_expected_files(tmp_path: Path) -> None:
    vocab = tmp_path / "vocab"
    out = tmp_path / "out"
    _write_synthetic_vocab(vocab)

    _run(vocab, out)

    expected = {
        out / "_types" / "__init__.py",
        out / "_types" / "identity.py",
        out / "_types" / "messaging.py",
        out / "messaging" / "verbs.py",
    }
    for p in expected:
        assert p.exists(), f"missing {p}"


def test_generated_types_module_content(tmp_path: Path) -> None:
    vocab = tmp_path / "vocab"
    out = tmp_path / "out"
    _write_synthetic_vocab(vocab)

    _run(vocab, out)

    messaging_types = (out / "_types" / "messaging.py").read_text(encoding="utf-8")
    assert "AUTO-GENERATED" in messaging_types
    assert "class MessageRef" in messaging_types
    assert "from datetime import datetime" in messaging_types

    identity_types = (out / "_types" / "identity.py").read_text(encoding="utf-8")
    assert "IdentityRef = str" in identity_types

    init = (out / "_types" / "__init__.py").read_text(encoding="utf-8")
    assert "from ota_connect._types.identity import IdentityRef" in init
    assert "from ota_connect._types.messaging import MessageRef" in init
    assert '"MessageRef"' in init


def test_generated_verbs_module_content(tmp_path: Path) -> None:
    vocab = tmp_path / "vocab"
    out = tmp_path / "out"
    _write_synthetic_vocab(vocab)

    _run(vocab, out)

    verbs = (out / "messaging" / "verbs.py").read_text(encoding="utf-8")
    assert "AUTO-GENERATED" in verbs
    assert "from ota_connect._types import (" in verbs
    assert "    IdentityRef," in verbs
    assert "    MessageRef," in verbs
    assert "from ota_connect.messaging.dispatch import dispatch" in verbs
    assert "from ota_core.policy import verb" in verbs
    assert "@verb(" in verbs
    assert 'idempotency="best_effort"' in verbs
    assert 'required_scopes=["messaging:send"]' in verbs
    assert "destructive=False" in verbs
    assert "def send_message(" in verbs
    assert 'return dispatch("send_message", **locals())' in verbs


def test_idempotent(tmp_path: Path) -> None:
    vocab = tmp_path / "vocab"
    out = tmp_path / "out"
    _write_synthetic_vocab(vocab)

    _run(vocab, out)
    first = {p.relative_to(out): p.read_text(encoding="utf-8") for p in out.rglob("*.py")}

    _run(vocab, out)
    second = {p.relative_to(out): p.read_text(encoding="utf-8") for p in out.rglob("*.py")}

    assert first == second


def test_underscore_files_skipped_as_capabilities(tmp_path: Path) -> None:
    vocab = tmp_path / "vocab"
    out = tmp_path / "out"
    _write_synthetic_vocab(vocab)
    (vocab / "_roster.md").write_text("# roster (should be ignored)\n", encoding="utf-8")

    _run(vocab, out)

    assert not (out / "_roster").exists()


def test_missing_types_md_fails(tmp_path: Path) -> None:
    vocab = tmp_path / "vocab"
    out = tmp_path / "out"
    vocab.mkdir()
    (vocab / "messaging.md").write_text(_SYNTHETIC_CAPABILITY_MD, encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--vocabulary-dir",
            str(vocab),
            "--output-dir",
            str(out),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "_types.md" in result.stderr or "_types.md" in result.stdout


def test_signature_without_ellipsis_fails(tmp_path: Path) -> None:
    vocab = tmp_path / "vocab"
    out = tmp_path / "out"
    vocab.mkdir()
    (vocab / "_types.md").write_text(_SYNTHETIC_TYPES_MD, encoding="utf-8")
    broken = _SYNTHETIC_CAPABILITY_MD.replace("-> MessageRef: ...", "-> MessageRef:")
    (vocab / "messaging.md").write_text(broken, encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--vocabulary-dir",
            str(vocab),
            "--output-dir",
            str(out),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "send_message" in result.stderr or "send_message" in result.stdout
