from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ov_video_editing_skills.e2e import (
    DEFAULT_REQUEST,
    DEFAULT_VIDEO_CANDIDATES,
    VIDEO_EXTENSIONS,
    WORKSPACE_PLACEHOLDER,
    build_analyze_command,
    build_compose_command,
    build_e2e_commands,
    build_prepare_command,
    build_storyboard_command,
    default_video_input,
    derive_artifact_paths,
    extract_workspace_from_prepare_output,
    load_runtime_paths,
    main,
    project_root,
    resolve_video_input,
    run_step,
)


if __name__ == "__main__":
    raise SystemExit(main())
