from __future__ import annotations

import platform
import sys
from pathlib import Path


def test_pyinstaller_datas():
    from kimi_cli.utils.pyinstaller import datas

    project_root = Path(__file__).parent.parent.parent
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    site_packages = f".venv/lib/python{python_version}/site-packages"
    rg_binary = "rg.exe" if platform.system() == "Windows" else "rg"
    has_rg_binary = (project_root / "src/kimi_cli/deps/bin" / rg_binary).exists()
    datas = [
        (
            Path(path)
            .relative_to(project_root)
            .as_posix()
            .replace(".venv/Lib/site-packages", site_packages),
            Path(dst).as_posix(),
        )
        for path, dst in datas
    ]

    datas = [(p, d) for p, d in datas if "web/static" not in d]

    # Verify the datas list is non-empty and contains expected patterns
    assert len(datas) > 0, "datas should not be empty"

    # Check that site-packages paths use the correct Python version
    site_pkg_entries = [p for p, _ in datas if p.startswith(".venv/lib/python")]
    for path in site_pkg_entries:
        assert f"python{python_version}" in path, f"Path should use python{python_version}: {path}"

    # Check that all source paths exist
    for src_path, _ in datas:
        full_path = project_root / src_path
        assert full_path.exists(), f"Source path does not exist: {src_path}"

    # Check for expected entries
    expected_patterns = [
        ("src/kimi_cli/agents/default/agent.yaml", "kimi_cli/agents/default"),
        ("src/kimi_cli/agents/default/system.md", "kimi_cli/agents/default"),
        ("src/kimi_cli/prompts/compact.md", "kimi_cli/prompts"),
        ("src/kimi_cli/tools/file/read.md", "kimi_cli/tools/file"),
    ]
    for pattern_src, pattern_dst in expected_patterns:
        assert (pattern_src, pattern_dst) in datas, f"Missing expected entry: {pattern_src}"

    # Check for rg binary if it exists
    if has_rg_binary:
        assert (f"src/kimi_cli/deps/bin/{rg_binary}", "kimi_cli/deps/bin") in datas


def test_pyinstaller_hiddenimports():
    from kimi_cli.utils.pyinstaller import hiddenimports

    # Verify hiddenimports is non-empty and contains expected modules
    assert len(hiddenimports) > 0, "hiddenimports should not be empty"

    expected_modules = [
        "kimi_cli.tools",
        "kimi_cli.tools.file",
        "kimi_cli.tools.shell",
        "setproctitle",
    ]
    for module in expected_modules:
        assert module in hiddenimports, f"Missing expected module: {module}"
