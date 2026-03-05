"""Tests for forge.py interactive project path configuration."""

import os
import json
import tempfile
from types import SimpleNamespace

import sys
import os
import tempfile

# ensure we can import package modules when executed from tests/ dir
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import forge


def test_interactive_folder_creation():
    """Running forge.main() without args should prompt and save config."""
    import builtins
    # run from temporary directory so config file is isolated
    tmp_path = tempfile.mkdtemp()
    os.chdir(tmp_path)

    # prepare a non-existent project path under tmp_path
    proj = os.path.join(tmp_path, "newproj")
    assert not os.path.exists(proj)

    # simulate user input: first valid path, then confirm creation
    responses = iter([proj, "y"])
    builtins.input = lambda prompt='': next(responses)

    # ensure no config file exists beforehand
    cfg_file = os.path.join(tmp_path, "forgecore_config.json")
    if os.path.exists(cfg_file):
        os.remove(cfg_file)

    ret = forge.main()
    assert ret == 0

    # folder should have been created and config written
    assert os.path.exists(proj) and os.path.isdir(proj)
    assert os.path.exists(cfg_file)
    config = json.loads(open(cfg_file).read())
    assert config.get('project_path') == str(proj)

    # running again without args should now pick up config and not prompt
    # replace input with a callable that would error if invoked
    builtins.input = lambda prompt='': (_ for _ in ()).throw(AssertionError("no input expected"))
    ret2 = forge.main()
    assert ret2 == 0

