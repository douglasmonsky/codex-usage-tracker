"""Shared JSON payload contract field groups."""

REFRESH_RESULT_FIELDS = {
    "scanned_files": int,
    "parsed_events": int,
    "skipped_events": int,
    "inserted_or_updated_events": int,
    "db_path": str,
    "parser_diagnostics": dict,
}

PLUGIN_INSTALL_FIELDS = {
    "plugin_dir": str,
    "marketplace_path": str,
    "python_executable": str,
    "replaced_existing": bool,
    "restart_required": bool,
}

PATH_CREATED_FIELDS = {
    "created": bool,
}
