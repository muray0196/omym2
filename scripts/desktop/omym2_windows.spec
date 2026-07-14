"""
Summary: Builds the audited OMYM2 wheel as a Windows x64 onedir GUI application.
Why: Freezes the native desktop shell with its exact Web, migration, and metadata resources.
"""

import json
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, copy_metadata


def _required_environment_path(name):
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Required packaging environment variable is missing: {name}")
    return Path(value).resolve()


def _is_allowed_webview_resource(entry):
    normalized = "/" + "/".join(str(value).replace("\\", "/") for value in entry[:2]).lower() + "/"
    forbidden = json.loads(os.environ["OMYM2_DESKTOP_FORBIDDEN_WEBVIEW_RESOURCES"])
    return not any(fragment in normalized for fragment in forbidden)


launcher = _required_environment_path("OMYM2_DESKTOP_LAUNCHER")
runtime_hook = _required_environment_path("OMYM2_DESKTOP_RUNTIME_HOOK")
icon = _required_environment_path("OMYM2_DESKTOP_ICON")
version_info = _required_environment_path("OMYM2_DESKTOP_VERSION_INFO")
allowed_package_root = _required_environment_path("OMYM2_DESKTOP_ALLOWED_PACKAGE_ROOT")
provenance_path = _required_environment_path("OMYM2_DESKTOP_PROVENANCE")
runtime_inventory_path = _required_environment_path("OMYM2_DESKTOP_RUNTIME_INVENTORY")
python_runtime_license_path = _required_environment_path("OMYM2_DESKTOP_PYTHON_RUNTIME_LICENSE")
application_name = os.environ["OMYM2_DESKTOP_APPLICATION_NAME"]
contents_directory = os.environ["OMYM2_DESKTOP_CONTENTS_DIRECTORY"]
excluded_modules = json.loads(os.environ["OMYM2_DESKTOP_EXCLUDED_MODULES"])
hiddenimports = sorted(json.loads(os.environ["OMYM2_DESKTOP_HIDDEN_IMPORTS"]))
required_builtin_modules = set(json.loads(os.environ["OMYM2_DESKTOP_REQUIRED_BUILTIN_MODULES"]))
required_webview_modules = set(json.loads(os.environ["OMYM2_DESKTOP_REQUIRED_WEBVIEW_MODULES"]))
runtime_distributions = json.loads(os.environ["OMYM2_DESKTOP_RUNTIME_DISTRIBUTIONS"])
runtime_hook_policy = os.environ["OMYM2_DESKTOP_RUNTIME_HOOK_POLICY"]
wheel_sha256 = os.environ["OMYM2_DESKTOP_WHEEL_SHA256"]

datas = collect_data_files(
    "omym2.adapters.web",
    include_py_files=False,
    includes=["static_dist/*", "static_dist/**/*"],
)
datas += collect_data_files(
    "omym2.adapters.db.sqlite.migrations",
    include_py_files=False,
    includes=["*.sql"],
)
datas += copy_metadata("omym2")
for distribution_name in runtime_distributions:
    datas += copy_metadata(distribution_name)
datas.append((str(runtime_inventory_path), "."))
datas.append((str(python_runtime_license_path), "."))
binaries = collect_dynamic_libs("webview")

analysis = Analysis(
    [str(launcher)],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(runtime_hook)],
    excludes=excluded_modules,
    noarchive=False,
    optimize=0,
)
analysis.datas = type(analysis.datas)(entry for entry in analysis.datas if _is_allowed_webview_resource(entry))
analysis.binaries = type(analysis.binaries)(entry for entry in analysis.binaries if _is_allowed_webview_resource(entry))

collected_modules = {module_name for module_name, _source_path, _type_code in analysis.pure}
collected_webview_modules = sorted(
    module_name
    for module_name in collected_modules
    if module_name == "webview" or module_name.startswith("webview.")
)
excluded_webview_modules = sorted(
    module_name for module_name in excluded_modules if module_name.startswith("webview.")
)
unexpected_webview_modules = sorted(
    module_name
    for module_name in collected_webview_modules
    if any(
        module_name == excluded_module or module_name.startswith(f"{excluded_module}.")
        for excluded_module in excluded_webview_modules
    )
)
if unexpected_webview_modules:
    raise SystemExit(f"Excluded pywebview renderer modules were collected: {unexpected_webview_modules}")
missing_webview_modules = sorted(required_webview_modules - set(collected_webview_modules))
if missing_webview_modules:
    raise SystemExit(f"Required pywebview renderer modules were not collected: {missing_webview_modules}")
missing_builtin_modules = sorted(
    module_name for module_name in required_builtin_modules if not analysis.graph.is_a_builtin(module_name)
)
if missing_builtin_modules:
    raise SystemExit(f"Required Windows built-in modules were not collected: {missing_builtin_modules}")

verified_modules = []
for module_name, source_path, _type_code in analysis.pure:
    if module_name == "omym2" or module_name.startswith("omym2."):
        resolved_source = Path(source_path).resolve()
        if not resolved_source.is_relative_to(allowed_package_root):
            raise SystemExit(f"OMYM2 source import escaped the isolated wheel install: {resolved_source}")
        verified_modules.append(module_name)

required_modules = {"omym2.platform.desktop_entry_point", *hiddenimports}
missing_hidden_imports = sorted(required_modules - set(hiddenimports) - set(verified_modules))
if missing_hidden_imports:
    raise SystemExit(f"Required frozen modules were not collected: {missing_hidden_imports}")
if "omym2.platform.desktop_entry_point" not in verified_modules:
    raise SystemExit("The installed wheel does not contain the desktop entry point.")

provenance_path.write_text(
    json.dumps(
        {
            "builtin_imports": sorted(required_builtin_modules),
            "console": False,
            "excluded_webview_modules": excluded_webview_modules,
            "contents_directory": contents_directory,
            "format": "onedir",
            "hidden_imports": hiddenimports,
            "omym2_module_count": len(verified_modules),
            "runtime_hook_policy": runtime_hook_policy,
            "source_imports": "isolated-wheel-only",
            "webview_modules": collected_webview_modules,
            "wheel_sha256": wheel_sha256,
        },
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
analysis.datas.append((provenance_path.name, str(provenance_path), "DATA"))

python_archive = PYZ(analysis.pure)

executable = EXE(
    python_archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name=application_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon),
    version=str(version_info),
    contents_directory=contents_directory,
)

bundle = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name=application_name,
)
