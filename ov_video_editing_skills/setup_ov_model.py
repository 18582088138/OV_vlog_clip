from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .runtime import DEFAULT_MODEL_DIR, DEFAULT_MODEL_NAME, ensure_local_requirements, maybe_reexec_in_local_venv, safe_print

HF_MODEL_ID = "OpenVINO/Qwen2.5-VL-7B-Instruct-int4-ov"
HF_MIRROR_URL = "https://hf-mirror.com"
MODEL_MIN_XML_FILES = 1
MODEL_MIN_BIN_FILES = 1
MODEL_MIN_TOTAL_ENTRIES = 27


def inspect_model_dir(model_dir: Path) -> dict[str, object]:
    if not model_dir.is_dir():
        return {
            "exists": False,
            "xml_count": 0,
            "bin_count": 0,
            "total_entries": 0,
            "valid": False,
            "reason": f"目录不存在：{model_dir}",
        }

    all_entries = list(model_dir.rglob("*"))
    all_files = [entry for entry in all_entries if entry.is_file()]
    xml_files = [path for path in all_files if path.suffix.lower() == ".xml"]
    bin_files = [path for path in all_files if path.suffix.lower() == ".bin"]

    reasons: list[str] = []
    if len(xml_files) < MODEL_MIN_XML_FILES:
        reasons.append(f".xml 文件数 {len(xml_files)} < 最低要求 {MODEL_MIN_XML_FILES}")
    if len(bin_files) < MODEL_MIN_BIN_FILES:
        reasons.append(f".bin 文件数 {len(bin_files)} < 最低要求 {MODEL_MIN_BIN_FILES}")
    if len(all_entries) < MODEL_MIN_TOTAL_ENTRIES:
        reasons.append(f"总条目数 {len(all_entries)} < 最低要求 {MODEL_MIN_TOTAL_ENTRIES}（下载不完整）")

    return {
        "exists": True,
        "xml_count": len(xml_files),
        "bin_count": len(bin_files),
        "total_entries": len(all_entries),
        "valid": not reasons,
        "reason": "；".join(reasons),
    }


def verify_model_dir(model_dir: Path) -> bool:
    return bool(inspect_model_dir(model_dir)["valid"])


def setup_ov_model(
    model_dir: Path,
    repo_id: str,
    force: bool,
    check_only: bool,
    hf_endpoint: str | None = None,
) -> bool:
    safe_print(f"  模型目录 : {model_dir}\n")

    if check_only:
        report = inspect_model_dir(model_dir)
        if report["valid"]:
            safe_print(f"[model] ✓ 模型目录完整有效：{model_dir}")
            safe_print(f"[model]   .xml={report['xml_count']}  .bin={report['bin_count']}  总条目={report['total_entries']}")
            return True
        safe_print(f"[model] ✗ 模型目录不完整：{model_dir}")
        safe_print(f"[model]   .xml={report['xml_count']}  .bin={report['bin_count']}  总条目={report['total_entries']}")
        if report["reason"]:
            safe_print(f"[model]   原因：{report['reason']}")
        safe_print(f"[model] 下载路径：{repo_id}")
        safe_print(f"[model] 建议放置目录：{model_dir}")
        return False

    del force, hf_endpoint
    report = inspect_model_dir(model_dir)
    if report["valid"]:
        safe_print(f"[model] 模型已存在且完整：{model_dir}")
        return True
    safe_print(f"[model] ✗ 模型目录不完整：{model_dir}", file=sys.stderr)
    if report["reason"]:
        safe_print(f"[model]   原因：{report['reason']}", file=sys.stderr)
    safe_print(f"[model] 下载路径：{repo_id}", file=sys.stderr)
    safe_print(f"[model] 建议放置目录：{model_dir}", file=sys.stderr)
    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="检查 OpenVINO VLM 模型目录是否已手动放置完成")
    parser.add_argument("--model-dir", dest="model_dir", default=None, metavar="PATH", help=f"模型目录，默认：{DEFAULT_MODEL_DIR}")
    parser.add_argument("--repo-id", dest="repo_id", default=HF_MODEL_ID, metavar="REPO_ID", help=f"HuggingFace 仓库 ID（默认：{HF_MODEL_ID}）")
    parser.add_argument("--force", action="store_true", help="保留兼容参数；当前不会自动下载")
    parser.add_argument("--check-only", dest="check_only", action="store_true", help="只检查模型目录")
    mirror_group = parser.add_mutually_exclusive_group()
    mirror_group.add_argument("--hf-mirror", dest="hf_mirror", nargs="?", const=HF_MIRROR_URL, default=HF_MIRROR_URL, metavar="URL", help="使用 HF 镜像下载")
    mirror_group.add_argument("--no-mirror", dest="no_mirror", action="store_true", help="禁用镜像，直连 HuggingFace")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        ensure_local_requirements(force=False)
        maybe_reexec_in_local_venv("ov_video_editing_skills.setup_ov_model")
    except Exception as exc:
        safe_print(f"[python] ✗ 当前环境检查失败：{exc}", file=sys.stderr)
        return 1

    hf_endpoint = None if args.no_mirror else args.hf_mirror or os.environ.get("HF_ENDPOINT") or HF_MIRROR_URL
    model_dir = Path(args.model_dir) if args.model_dir else DEFAULT_MODEL_DIR

    safe_print("=" * 60)
    safe_print("OpenVINO 模型检查脚本")
    safe_print(f"仓库 ID    : {args.repo_id}")
    safe_print(f"模型目录   : {model_dir}")
    safe_print(f"下载镜像   : {hf_endpoint or '直连 HuggingFace'}")
    safe_print("=" * 60)
    safe_print()

    ok = setup_ov_model(
        model_dir=model_dir,
        repo_id=args.repo_id,
        force=args.force,
        check_only=args.check_only,
        hf_endpoint=hf_endpoint,
    )
    safe_print()
    if ok:
        safe_print("✓ 完成。")
        return 0
    safe_print("✗ 失败，请查看上方错误信息。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
