import json
import asyncio
import os
import time
import base64
import re
from pathlib import Path
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
import requests

# Shared auth module
from auth import (
    CACHE_DIR, get_powerbi_headers, get_fabric_headers
)

# New anonymization engine
from server.entity_registry import EntityRegistry
from server.anonymizer import Anonymizer
from server.mapping import MappingStore

# User config — env vars > local config.json > ~/.powerbi-mcp/config.json
CONFIG_PATH = Path(__file__).parent / "config.json"
GLOBAL_CONFIG_PATH = CACHE_DIR / "config.json"

def load_config():
    """Load user config with priority: env vars > config file > empty dict.

    Environment variables (for enterprise MDM/GPO deployment):
      POWERBI_MCP_CONFIG          — full JSON blob, overrides everything
      POWERBI_MCP_WORKSPACE_ID    — overrides default_workspace_id
      POWERBI_MCP_DATASET_ID      — overrides default_dataset_id
    """
    # Check for full JSON blob from env
    env_config = os.environ.get("POWERBI_MCP_CONFIG")
    if env_config:
        try:
            return json.loads(env_config)
        except json.JSONDecodeError:
            pass

    # Load from config file (local first, then global)
    config = {}
    for path in [CONFIG_PATH, GLOBAL_CONFIG_PATH]:
        if path.exists():
            try:
                with open(path, "r") as f:
                    config = json.load(f)
                    break
            except Exception:
                pass

    # Env var overrides for individual IDs
    env_workspace = os.environ.get("POWERBI_MCP_WORKSPACE_ID")
    if env_workspace:
        config["default_workspace_id"] = env_workspace

    env_dataset = os.environ.get("POWERBI_MCP_DATASET_ID")
    if env_dataset:
        config["default_dataset_id"] = env_dataset

    return config

USER_CONFIG = load_config()

server = Server("powerbi-connector")

# Anonymization state (initialized lazily on first tool call)
_anon_initialized = False
_anonymizer_instance = None
_mapping_store = None


def _init_anonymizer():
    """Lazily initialize the two-pass anonymizer on first tool call."""
    global _anon_initialized, _anonymizer_instance, _mapping_store

    if _anon_initialized:
        return _anonymizer_instance

    anon_config = USER_CONFIG.get("anonymization", {})
    enabled = anon_config.get("enabled", True)

    if not enabled:
        _anonymizer_instance = Anonymizer(
            registry=EntityRegistry(sensitive_columns={}, dax_executor=lambda q: {}),
            enabled=False,
        )
        _anon_initialized = True
        return _anonymizer_instance

    # Build DAX executor using existing server infrastructure
    def dax_executor(query: str) -> dict:
        args = resolve_ids({})
        dataset_id = args.get("dataset_id", "")
        if not dataset_id:
            raise Exception("No dataset_id configured for anonymization registry")
        response = requests.post(
            f"https://api.powerbi.com/v1.0/myorg/datasets/{dataset_id}/executeQueries",
            headers=get_powerbi_headers(),
            json={"queries": [{"query": query}], "serializerSettings": {"includeNulls": True}}
        )
        response.raise_for_status()
        return response.json()

    sensitive_columns = anon_config.get("sensitive_columns", {})
    registry = EntityRegistry(
        sensitive_columns=sensitive_columns,
        dax_executor=dax_executor,
    )
    registry.initialize()

    if registry.is_degraded:
        for warning in registry.get_warnings():
            print(f"[ANON WARNING] {warning}", flush=True)

    _anonymizer_instance = Anonymizer(
        registry=registry,
        presidio_enabled=anon_config.get("presidio_enabled", True),
    )

    # Initialize mapping store
    retention = anon_config.get("session_retention_days", 90)
    _mapping_store = MappingStore(retention_days=retention)
    _mapping_store.new_session()
    _mapping_store.cleanup()

    _anon_initialized = True
    return _anonymizer_instance


def _anonymize_text(text: str) -> str:
    """Anonymize text using the two-pass anonymizer."""
    anon = _init_anonymizer()
    return anon.anonymize_text(text)


def _anonymize_json(data) -> any:
    """Anonymize JSON data using the two-pass anonymizer."""
    anon = _init_anonymizer()
    return anon.anonymize_json(data)


def _save_mapping():
    """Persist the current mapping to disk after each tool call."""
    if _anonymizer_instance and _mapping_store:
        _mapping_store.save(
            _anonymizer_instance.get_full_mapping(),
            _anonymizer_instance.get_stats(),
        )

def resolve_ids(arguments: dict, need_workspace: bool = True, need_dataset: bool = True) -> dict:
    """Resolve workspace/dataset IDs from arguments, falling back to config defaults."""
    result = dict(arguments)
    if need_workspace and "workspace_id" not in result:
        default_ws = USER_CONFIG.get("default_workspace_id", "")
        if default_ws:
            result["workspace_id"] = default_ws
    if need_dataset and "dataset_id" not in result:
        default_ds = USER_CONFIG.get("default_dataset_id", "")
        if default_ds:
            result["dataset_id"] = default_ds
    return result

def fetch_and_decode_schema(workspace_id: str, dataset_id: str) -> str:
    """Fetch schema and decode all base64 TMDL content to readable text."""
    response = requests.post(
        f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/semanticModels/{dataset_id}/getDefinition",
        headers=get_fabric_headers()
    )

    schema_data = None
    if response.status_code == 202:
        location = response.headers.get("Location")
        if location:
            for _ in range(30):
                time.sleep(2)
                result = requests.get(location, headers=get_fabric_headers())
                if result.status_code == 200:
                    data = result.json()
                    if data.get("status") == "Succeeded":
                        result_response = requests.get(
                            f"{location}/result",
                            headers=get_fabric_headers()
                        )
                        if result_response.ok:
                            schema_data = result_response.json()
                            break
                    elif data.get("status") == "Failed":
                        raise Exception(f"Failed to get schema: {data.get('error')}")
            if not schema_data:
                raise Exception("Timeout waiting for schema")
    else:
        response.raise_for_status()
        schema_data = response.json()

    decoded_content = []
    parts = schema_data.get("definition", {}).get("parts", [])
    for part in parts:
        payload = part.get("payload", "")
        payload_type = part.get("payloadType", "")
        path = part.get("path", "")

        if payload_type == "InlineBase64" and payload:
            try:
                decoded = base64.b64decode(payload).decode("utf-8")
                decoded_content.append(f"--- {path} ---\n{decoded}")
            except Exception:
                pass

    return "\n\n".join(decoded_content)

@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="list_workspaces",
            description="List all Power BI workspaces you have access to",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="list_datasets",
            description="List all datasets/semantic models in a workspace",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "description": "Workspace ID (GUID). Optional if default_workspace_id is set in config.json."}
                },
                "required": []
            }
        ),
        Tool(
            name="execute_dax",
            description="Execute a DAX query on a dataset/semantic model",
            inputSchema={
                "type": "object",
                "properties": {
                    "dataset_id": {"type": "string", "description": "Dataset ID (GUID). Optional if default_dataset_id is set in config.json."},
                    "dax_query": {"type": "string", "description": "DAX query, e.g.: EVALUATE TOPN(10, 'Sales')"}
                },
                "required": ["dax_query"]
            }
        ),
        Tool(
            name="get_schema",
            description="WARNING: Returns the FULL schema (can be >10MB). Use 'search_schema' for targeted searches or 'list_measures' for a measures overview instead.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "description": "Workspace ID (GUID). Optional if default_workspace_id is set in config.json."},
                    "dataset_id": {"type": "string", "description": "Dataset/Semantic Model ID (GUID). Optional if default_dataset_id is set in config.json."}
                },
                "required": []
            }
        ),
        Tool(
            name="list_fabric_items",
            description="List all items in a Fabric workspace (reports, datasets, lakehouses, etc.)",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "description": "Workspace ID (GUID). Optional if default_workspace_id is set in config.json."}
                },
                "required": []
            }
        ),
        Tool(
            name="search_schema",
            description="Search the schema for specific measures, columns, or tables. Returns only relevant definitions (not the full schema). Use this instead of get_schema for targeted searches.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "description": "Workspace ID (GUID). Optional if default_workspace_id is set in config.json."},
                    "dataset_id": {"type": "string", "description": "Dataset/Semantic Model ID (GUID). Optional if default_dataset_id is set in config.json."},
                    "search_term": {"type": "string", "description": "Search term (case-insensitive). E.g.: 'efficiency', 'variance', 'sales'"},
                    "context_lines": {"type": "integer", "description": "Number of context lines around each match (default: 25)", "default": 25}
                },
                "required": ["search_term"]
            }
        ),
        Tool(
            name="list_measures",
            description="List all measure names in a dataset (without full definitions). Useful to see which measures are available.",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string", "description": "Workspace ID (GUID). Optional if default_workspace_id is set in config.json."},
                    "dataset_id": {"type": "string", "description": "Dataset/Semantic Model ID (GUID). Optional if default_dataset_id is set in config.json."}
                },
                "required": []
            }
        ),
        Tool(
            name="anonymization_status",
            description="Show the current anonymization status: whether it's enabled, how many entities are mapped, and session info.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    try:
        if name == "list_workspaces":
            response = requests.get(
                "https://api.powerbi.com/v1.0/myorg/groups",
                headers=get_powerbi_headers()
            )
            response.raise_for_status()
            data = response.json()
            workspaces = data.get("value", [])

            # Register workspace names for anonymization
            anon = _init_anonymizer()
            if anon._enabled:
                for i, ws in enumerate(workspaces):
                    ws_name = ws.get("name", "")
                    if ws_name:
                        anon._registry.register_dynamic(
                            ws_name, "workspace", i
                        )

            output = "Available workspaces:\n\n"
            for ws in workspaces:
                output += f"- {ws.get('name', 'Unknown')}\n  ID: {ws.get('id')}\n\n"
            _save_mapping()
            return [TextContent(type="text", text=_anonymize_text(output))]

        elif name == "list_datasets":
            args = resolve_ids(arguments, need_workspace=True, need_dataset=False)
            workspace_id = args.get("workspace_id")
            if not workspace_id:
                return [TextContent(type="text", text="Error: workspace_id is required. Provide it as an argument or set default_workspace_id in config.json.")]
            response = requests.get(
                f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/datasets",
                headers=get_powerbi_headers()
            )
            response.raise_for_status()
            data = response.json()
            datasets = data.get("value", [])

            # Register dataset names and configuredBy for anonymization
            anon = _init_anonymizer()
            if anon._enabled:
                for i, ds in enumerate(datasets):
                    ds_name = ds.get("name", "")
                    if ds_name:
                        anon._registry.register_dynamic(
                            ds_name, "dataset", i
                        )
                    configured_by = ds.get("configuredBy", "")
                    if configured_by:
                        anon._registry.register_dynamic(
                            configured_by, "contact", None
                        )

            output = "Datasets in workspace:\n\n"
            for ds in datasets:
                output += f"- {ds.get('name', 'Unknown')}\n  ID: {ds.get('id')}\n  Configured by: {ds.get('configuredBy', 'Unknown')}\n\n"
            _save_mapping()
            return [TextContent(type="text", text=_anonymize_text(output))]

        elif name == "execute_dax":
            args = resolve_ids(arguments, need_workspace=False, need_dataset=True)
            dataset_id = args.get("dataset_id")
            if not dataset_id:
                return [TextContent(type="text", text="Error: dataset_id is required. Provide it as an argument or set default_dataset_id in config.json.")]
            dax_query = arguments["dax_query"]
            response = requests.post(
                f"https://api.powerbi.com/v1.0/myorg/datasets/{dataset_id}/executeQueries",
                headers=get_powerbi_headers(),
                json={
                    "queries": [{"query": dax_query}],
                    "serializerSettings": {"includeNulls": True}
                }
            )
            response.raise_for_status()
            anonymized_data = _anonymize_json(response.json())
            _save_mapping()
            return [TextContent(type="text", text=json.dumps(anonymized_data, indent=2))]

        elif name == "get_schema":
            args = resolve_ids(arguments)
            workspace_id = args.get("workspace_id")
            dataset_id = args.get("dataset_id")
            if not workspace_id or not dataset_id:
                return [TextContent(type="text", text="Error: workspace_id and dataset_id are required. Provide them as arguments or set defaults in config.json.")]

            response = requests.post(
                f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/semanticModels/{dataset_id}/getDefinition",
                headers=get_fabric_headers()
            )

            if response.status_code == 202:
                location = response.headers.get("Location")
                if location:
                    for _ in range(30):
                        time.sleep(2)
                        result = requests.get(location, headers=get_fabric_headers())
                        if result.status_code == 200:
                            data = result.json()
                            if data.get("status") == "Succeeded":
                                result_response = requests.get(
                                    f"{location}/result",
                                    headers=get_fabric_headers()
                                )
                                if result_response.ok:
                                    anonymized_data = _anonymize_json(result_response.json())
                                    _save_mapping()
                                    return [TextContent(type="text", text=json.dumps(anonymized_data, indent=2))]
                            elif data.get("status") == "Failed":
                                return [TextContent(type="text", text=f"Failed: {data.get('error')}")]
                    return [TextContent(type="text", text="Timeout waiting for schema")]

            response.raise_for_status()
            anonymized_data = _anonymize_json(response.json())
            _save_mapping()
            return [TextContent(type="text", text=json.dumps(anonymized_data, indent=2))]

        elif name == "list_fabric_items":
            args = resolve_ids(arguments, need_workspace=True, need_dataset=False)
            workspace_id = args.get("workspace_id")
            if not workspace_id:
                return [TextContent(type="text", text="Error: workspace_id is required. Provide it as an argument or set default_workspace_id in config.json.")]
            response = requests.get(
                f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items",
                headers=get_fabric_headers()
            )
            response.raise_for_status()
            items = response.json().get("value", [])
            output = "Items in workspace:\n\n"
            for item in items:
                output += f"- {item.get('displayName')} ({item.get('type')})\n  ID: {item.get('id')}\n\n"
            _save_mapping()
            return [TextContent(type="text", text=_anonymize_text(output))]

        elif name == "search_schema":
            args = resolve_ids(arguments)
            workspace_id = args.get("workspace_id")
            dataset_id = args.get("dataset_id")
            if not workspace_id or not dataset_id:
                return [TextContent(type="text", text="Error: workspace_id and dataset_id are required. Provide them as arguments or set defaults in config.json.")]
            search_term = arguments["search_term"]
            context_lines = arguments.get("context_lines", 25)

            decoded_schema = fetch_and_decode_schema(workspace_id, dataset_id)
            lines = decoded_schema.split("\n")

            matches = []
            pattern = re.compile(re.escape(search_term), re.IGNORECASE)

            for i, line in enumerate(lines):
                if pattern.search(line):
                    start = max(0, i - context_lines)
                    end = min(len(lines), i + context_lines + 1)
                    context = lines[start:end]
                    matches.append({
                        "line_number": i + 1,
                        "match_line": line.strip(),
                        "context": "\n".join(context)
                    })

            # Deduplicate overlapping contexts
            if matches:
                deduplicated = [matches[0]]
                for m in matches[1:]:
                    if m["line_number"] - deduplicated[-1]["line_number"] > context_lines * 2:
                        deduplicated.append(m)
                matches = deduplicated

            if not matches:
                return [TextContent(type="text", text=f"No matches found for '{search_term}'")]

            output = f"Found {len(matches)} results for '{search_term}':\n\n"
            for i, match in enumerate(matches[:10]):
                output += f"=== Match {i+1} (line {match['line_number']}) ===\n"
                output += match["context"]
                output += "\n\n"

            if len(matches) > 10:
                output += f"... and {len(matches) - 10} more results (refine your search term for more specific results)"

            _save_mapping()
            return [TextContent(type="text", text=_anonymize_text(output))]

        elif name == "list_measures":
            args = resolve_ids(arguments)
            workspace_id = args.get("workspace_id")
            dataset_id = args.get("dataset_id")
            if not workspace_id or not dataset_id:
                return [TextContent(type="text", text="Error: workspace_id and dataset_id are required. Provide them as arguments or set defaults in config.json.")]

            decoded_schema = fetch_and_decode_schema(workspace_id, dataset_id)

            measure_pattern = re.compile(r"^\s*measure\s+'([^']+)'|^\s*measure\s+(\S+)", re.MULTILINE | re.IGNORECASE)
            measures = []
            for match in measure_pattern.finditer(decoded_schema):
                measure_name = match.group(1) or match.group(2)
                if measure_name and measure_name not in measures:
                    measures.append(measure_name)

            if not measures:
                return [TextContent(type="text", text="No measures found in this model")]

            output = f"Found {len(measures)} measures:\n\n"
            for m in sorted(measures):
                output += f"- {m}\n"

            _save_mapping()
            return [TextContent(type="text", text=_anonymize_text(output))]

        elif name == "anonymization_status":
            anon = _init_anonymizer()
            stats = anon.get_stats()
            mapping = anon.get_full_mapping()
            session_id = _mapping_store.session_id if _mapping_store else "N/A"
            output = "Anonymization Status\n"
            output += f"  Enabled: {anon._enabled}\n"
            output += f"  Session: {session_id}\n"
            output += f"  Entities mapped: {len(mapping.get('registry', {}))}\n"
            output += f"  Presidio detections: {len(mapping.get('presidio', {}))}\n"
            output += f"  Pass 1 replacements: {stats.get('pass1_replacements', 0)}\n"
            output += f"  Pass 2 replacements: {stats.get('pass2_replacements', 0)}\n"
            if anon.registry and anon.registry.is_degraded:
                output += "  WARNING: Registry in degraded mode (Presidio-only fallback)\n"
                for w in anon.registry.get_warnings():
                    output += f"    - {w}\n"
            return [TextContent(type="text", text=output)]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except requests.exceptions.HTTPError as e:
        error_msg = f"HTTP Error: {e.response.status_code}\n{e.response.text}"
        return [TextContent(type="text", text=_anonymize_text(error_msg))]
    except Exception as e:
        return [TextContent(type="text", text=_anonymize_text(f"Error: {str(e)}"))]

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
