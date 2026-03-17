#!/usr/bin/env python3
"""Power BI MCP — Setup Wizard

Auto-discovers workspaces and datasets, writes config.json, and authenticates
the user in one step. Eliminates manual GUID hunting.

Usage:
  python -m server.wizard                                          # Interactive
  python -m server.wizard --workspace-id XXX --dataset-id YYY      # Pre-configured
  python -m server.wizard --config-url https://it.acme.com/config  # Download config
  python -m server.wizard --silent --workspace-id X --dataset-id Y # No prompts (MDM)
  python -m server.wizard --device-code                            # Headless (SSH)
"""

import argparse
import json
import sys
from pathlib import Path

import requests

from server.auth import (
    CACHE_DIR,
    POWERBI_SCOPE,
    get_token,
    get_powerbi_headers,
    save_auth_record,
    get_credential,
)

CONFIG_PATH = CACHE_DIR / "config.json"

# Terminal colors
GREEN = "\033[0;32m"
YELLOW = "\033[0;33m"
RED = "\033[0;31m"
BOLD = "\033[1m"
NC = "\033[0m"


def info(msg):
    print(f"{GREEN}[OK]{NC} {msg}")


def warn(msg):
    print(f"{YELLOW}[!!]{NC} {msg}")


def fail(msg):
    print(f"{RED}[FAIL]{NC} {msg}", file=sys.stderr)
    sys.exit(1)


def pick(prompt, items, name_key="name", id_key="id"):
    """Show numbered list, return selected item dict."""
    print(f"\n{BOLD}{prompt}{NC}\n")
    for i, item in enumerate(items, 1):
        print(f"  {i}. {item[name_key]}  ({item[id_key][:8]}...)")
    print()

    while True:
        try:
            choice = input(f"Pick a number [1-{len(items)}]: ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(items):
                return items[idx]
        except EOFError:
            fail("No interactive input available. Use --workspace-id and --dataset-id flags instead.")
        except ValueError:
            pass
        print("  Invalid choice, try again.")


def fetch_workspaces(device_code=False):
    """List all workspaces the user has access to."""
    headers = get_powerbi_headers(device_code=device_code)
    resp = requests.get(
        "https://api.powerbi.com/v1.0/myorg/groups",
        headers=headers,
    )
    resp.raise_for_status()
    return resp.json().get("value", [])


def fetch_datasets(workspace_id, device_code=False):
    """List all datasets in a workspace."""
    headers = get_powerbi_headers(device_code=device_code)
    resp = requests.get(
        f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/datasets",
        headers=headers,
    )
    resp.raise_for_status()
    return resp.json().get("value", [])


def write_config(workspace_id, workspace_name, dataset_id, dataset_name):
    """Write or update ~/.powerbi-mcp/config.json."""
    config = {}
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                config = json.load(f)
        except Exception:
            pass

    config["default_workspace_id"] = workspace_id
    config["default_workspace_name"] = workspace_name
    config["default_dataset_id"] = dataset_id
    config["default_dataset_name"] = dataset_name

    # Friendly name maps
    workspaces = config.get("workspaces", {})
    workspaces[workspace_name] = workspace_id
    config["workspaces"] = workspaces

    datasets = config.get("datasets", {})
    datasets[dataset_name] = dataset_id
    config["datasets"] = datasets

    CACHE_DIR.mkdir(exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)

    return CONFIG_PATH


def download_config(url):
    """Download config JSON from an IT-hosted endpoint."""
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    config = resp.json()

    CACHE_DIR.mkdir(exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)

    return config


def verify_connection(device_code=False):
    """Quick check: can we reach Power BI with the current token?"""
    try:
        headers = get_powerbi_headers(device_code=device_code)
        resp = requests.get(
            "https://api.powerbi.com/v1.0/myorg/groups",
            headers=headers,
        )
        resp.raise_for_status()
        count = len(resp.json().get("value", []))
        info(f"Connected — {count} workspace(s) accessible")
        return True
    except Exception as e:
        warn(f"Connection check failed: {e}")
        return False


def detect_sensitive_columns(workspace_id, dataset_id, device_code=False):
    """Scan schema for likely PII columns and suggest anonymization config."""
    from server.auth import get_fabric_headers
    import base64
    import time

    print(f"\n{BOLD}  Scanning for sensitive columns...{NC}")

    try:
        response = requests.post(
            f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/semanticModels/{dataset_id}/getDefinition",
            headers=get_fabric_headers(device_code=device_code),
        )

        schema_data = None
        if response.status_code == 202:
            location = response.headers.get("Location")
            if location:
                for _ in range(30):
                    time.sleep(2)
                    result = requests.get(
                        location,
                        headers=get_fabric_headers(device_code=device_code),
                    )
                    if result.status_code == 200:
                        data = result.json()
                        if data.get("status") == "Succeeded":
                            result_response = requests.get(
                                f"{location}/result",
                                headers=get_fabric_headers(device_code=device_code),
                            )
                            if result_response.ok:
                                schema_data = result_response.json()
                                break
        else:
            response.raise_for_status()
            schema_data = response.json()

        if not schema_data:
            warn("Could not fetch schema for column detection")
            return {}

        import re

        pii_patterns = re.compile(
            r"\b(Full\s*Name|Company\s*Name|Email|Contact|Phone|Address)\b",
            re.IGNORECASE,
        )
        dimension_patterns = re.compile(r"^(BI_|Dim_)", re.IGNORECASE)

        candidates = {"client": [], "resource": [], "contact": []}
        parts = schema_data.get("definition", {}).get("parts", [])

        for part in parts:
            payload = part.get("payload", "")
            path = part.get("path", "")
            if part.get("payloadType") != "InlineBase64" or not payload:
                continue

            decoded = base64.b64decode(payload).decode("utf-8", errors="ignore")
            table_match = re.search(r"tables/([^/]+)/", path)
            if not table_match:
                continue
            table_name = table_match.group(1)

            if not dimension_patterns.match(table_name):
                continue

            for line in decoded.split("\n"):
                col_match = re.match(
                    r"\s*column\s+'?([^']+)'?", line, re.IGNORECASE
                )
                if col_match and pii_patterns.search(col_match.group(1)):
                    col_name = col_match.group(1)
                    col_ref = f"'{table_name}'[{col_name}]"

                    lower = col_name.lower()
                    if "company" in lower or "account" in lower:
                        candidates["client"].append(col_ref)
                    elif any(
                        kw in lower
                        for kw in ("resource", "technician", "employee")
                    ):
                        candidates["resource"].append(col_ref)
                    elif "contact" in lower or "email" in lower:
                        candidates["contact"].append(col_ref)

        return {k: v for k, v in candidates.items() if v}

    except Exception as e:
        warn(f"Column detection failed: {e}")
        return {}


def main():
    parser = argparse.ArgumentParser(
        description="Power BI MCP — Setup Wizard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--workspace-id", help="Pre-configured workspace GUID")
    parser.add_argument("--dataset-id", help="Pre-configured dataset GUID")
    parser.add_argument("--config-url", help="Download config from URL")
    parser.add_argument(
        "--silent",
        action="store_true",
        help="No prompts — fail if IDs not provided (for MDM scripts)",
    )
    parser.add_argument(
        "--device-code",
        action="store_true",
        help="Use device code flow (headless/SSH environments)",
    )
    args = parser.parse_args()

    print(f"\n{BOLD}  Power BI MCP — Setup Wizard{NC}")
    print(f"  ============================\n")

    # Mode 1: Config from URL
    if args.config_url:
        print(f"  Downloading config from {args.config_url}...")
        try:
            config = download_config(args.config_url)
            info(f"Config written to {CONFIG_PATH}")
            ws = config.get("default_workspace_id", "")
            ds = config.get("default_dataset_id", "")
            if ws:
                info(f"Workspace: {ws}")
            if ds:
                info(f"Dataset:   {ds}")
        except Exception as e:
            fail(f"Failed to download config: {e}")

        # Authenticate to cache token
        print(f"\n{BOLD}  Authenticating...{NC}")
        try:
            get_token(POWERBI_SCOPE, device_code=args.device_code)
            info("Authentication successful — token cached")
        except Exception as e:
            warn(f"Authentication failed: {e}")
            warn("You can authenticate later on first MCP tool use")

        verify_connection(device_code=args.device_code)
        return

    # Mode 2: Pre-configured IDs (enterprise silent deploy)
    if args.workspace_id and args.dataset_id:
        write_config(
            args.workspace_id, "Pre-configured",
            args.dataset_id, "Pre-configured",
        )
        info(f"Config written to {CONFIG_PATH}")
        info(f"Workspace: {args.workspace_id}")
        info(f"Dataset:   {args.dataset_id}")

        # Authenticate
        if not args.silent:
            print(f"\n{BOLD}  Authenticating...{NC}")
        try:
            get_token(POWERBI_SCOPE, device_code=args.device_code)
            info("Authentication successful — token cached")
        except Exception as e:
            if args.silent:
                fail(f"Authentication failed: {e}")
            else:
                warn(f"Authentication failed: {e}")
                warn("You can authenticate later on first MCP tool use")

        verify_connection(device_code=args.device_code)
        return

    # Mode 3: Silent mode without IDs — error
    if args.silent:
        fail("--silent requires both --workspace-id and --dataset-id (or --config-url)")

    # Mode 4: Interactive wizard
    print("  Signing in to Power BI...\n")
    if args.device_code:
        print("  Using device code flow (for headless environments).")
        print("  Follow the instructions below to authenticate.\n")

    try:
        get_token(POWERBI_SCOPE, device_code=args.device_code)
        info("Signed in successfully")
    except Exception as e:
        fail(f"Authentication failed: {e}")

    # Pick workspace
    print(f"\n{BOLD}  Loading workspaces...{NC}")
    workspaces = fetch_workspaces(device_code=args.device_code)
    if not workspaces:
        fail("No workspaces found. Check that your account has Power BI Pro/PPU access.")

    if args.workspace_id:
        ws_match = [w for w in workspaces if w["id"] == args.workspace_id]
        if ws_match:
            workspace = ws_match[0]
            info(f"Using workspace: {workspace['name']}")
        else:
            fail(f"Workspace {args.workspace_id} not found or not accessible")
    else:
        workspace = pick("Your workspaces:", workspaces)
        info(f"Selected: {workspace['name']}")

    # Pick dataset
    print(f"\n{BOLD}  Loading datasets...{NC}")
    datasets = fetch_datasets(workspace["id"], device_code=args.device_code)
    if not datasets:
        fail(f"No datasets found in '{workspace['name']}'. Upload a .pbix or create a semantic model first.")

    if args.dataset_id:
        ds_match = [d for d in datasets if d["id"] == args.dataset_id]
        if ds_match:
            dataset = ds_match[0]
            info(f"Using dataset: {dataset['name']}")
        else:
            fail(f"Dataset {args.dataset_id} not found in workspace '{workspace['name']}'")
    else:
        dataset = pick("Datasets in this workspace:", datasets)
        info(f"Selected: {dataset['name']}")

    # Write config
    config_path = write_config(
        workspace["id"], workspace["name"],
        dataset["id"], dataset["name"],
    )
    info(f"Config saved to {config_path}")

    # Anonymization setup
    print(f"\n{BOLD}  Data Anonymization Setup{NC}")
    print(f"  (Prevents real data from reaching AI servers)\n")

    candidates = detect_sensitive_columns(
        workspace["id"], dataset["id"], device_code=args.device_code
    )

    if candidates:
        print(f"  Found {sum(len(v) for v in candidates.values())} likely sensitive columns:\n")
        for category, cols in candidates.items():
            print(f"  {BOLD}{category}:{NC}")
            for col in cols:
                print(f"    - {col}")
        print()

        confirm = input(f"  Enable anonymization with these columns? [Y/n]: ").strip().lower()
        if confirm != "n":
            config = {}
            if CONFIG_PATH.exists():
                with open(CONFIG_PATH) as f:
                    config = json.load(f)
            config["anonymization"] = {
                "enabled": True,
                "sensitive_columns": candidates,
                "free_text_columns": [],
                "presidio_enabled": True,
                "session_retention_days": 90,
            }
            with open(CONFIG_PATH, "w") as f:
                json.dump(config, f, indent=2)
            info("Anonymization enabled")
        else:
            info("Anonymization skipped (can be enabled later in config.json)")
    else:
        warn("No sensitive columns auto-detected")
        print(f"  You can manually configure anonymization in {CONFIG_PATH}")

    # Verify
    print()
    verify_connection(device_code=args.device_code)

    # Summary
    print(f"\n  {BOLD}Done!{NC} Your setup:\n")
    print(f"  Workspace:  {workspace['name']}")
    print(f"              {workspace['id']}")
    print(f"  Dataset:    {dataset['name']}")
    print(f"              {dataset['id']}")
    print(f"  Config:     {config_path}")
    print()
    print(f"  Open VS Code and type: {BOLD}#powerbireport what is my monthly revenue?{NC}")
    print()


if __name__ == "__main__":
    main()
