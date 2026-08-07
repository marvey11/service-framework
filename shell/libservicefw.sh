#!/usr/bin/env bash
# libservicefw.sh - Shell Runtime Helper Library

SFW_SERVICE_NAME="${SFW_SERVICE_NAME:-$(basename "$0" .sh)}"
if command -v uuidgen >/dev/null 2>&1; then
    SFW_EXECUTION_ID="${SFW_EXECUTION_ID:-$(uuidgen)}"
else
    SFW_EXECUTION_ID="${SFW_EXECUTION_ID:-$(cat /proc/sys/kernel/random/uuid 2>/dev/null || echo "00000000-0000-0000-0000-000000000000")}"
fi

sfw_resolve_paths() {
    SFW_BASE_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/sfw"
    SFW_STATE_DIR="${SFW_BASE_DIR}/state"
    SFW_HISTORY_DIR="${SFW_BASE_DIR}/history"
    SFW_STATE_FILE="${SFW_STATE_DIR}/${SFW_SERVICE_NAME}.json"
    SFW_LOG_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/sfw/logs"
    SFW_LOG_FILE="${SFW_LOG_DIR}/${SFW_SERVICE_NAME}.log.jsonl"
    SFW_START_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}

sfw_resolve_paths

sfw_init() {
    sfw_resolve_paths
    mkdir -p "${SFW_STATE_DIR}" "${SFW_HISTORY_DIR}" "${SFW_LOG_DIR}"
    sfw_update_status "RUNNING"
    trap 'sfw_on_exit' EXIT ERR SIGTERM SIGINT
}

sfw_get_config() {
    local key="$1"
    local default_val="${2:-}"
    local config_file="${XDG_CONFIG_HOME:-$HOME/.config}/sfw/services/${SFW_SERVICE_NAME}.yaml"

    if [ -f "$config_file" ] && command -v yq >/dev/null 2>&1; then
        local val
        val=$(yq eval ".${key}" "$config_file" 2>/dev/null)
        if [ -n "$val" ] && [ "$val" != "null" ]; then
            echo "$val"
            return
        fi
    fi
    echo "$default_val"
}

sfw_update_status() {
    local status="$1"
    local exit_code="${2:-null}"
    local err_msg="${3:-null}"

    if [ "$err_msg" != "null" ]; then
        err_msg="\"$err_msg\""
    fi

    local tmp_file
    tmp_file=$(mktemp "${SFW_STATE_DIR}/.${SFW_SERVICE_NAME}.XXXXXX.tmp")
    local end_time="null"

    if [[ "$status" == "SUCCESS" || "$status" == "FAILED" || "$status" == "STOPPED" ]]; then
        end_time="\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\""
    fi

    # Read existing metadata if present
    local existing_meta="{}"
    if [ -f "${SFW_STATE_FILE}" ] && command -v jq >/dev/null 2>&1; then
        existing_meta=$(jq -c '.custom_metadata // {}' "${SFW_STATE_FILE}" 2>/dev/null || echo "{}")
    fi

    cat <<EOF > "$tmp_file"
{
  "service_name": "${SFW_SERVICE_NAME}",
  "execution_id": "${SFW_EXECUTION_ID}",
  "status": "${status}",
  "start_time": "${SFW_START_TIME}",
  "end_time": ${end_time},
  "last_updated": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "pid": $$,
  "exit_code": ${exit_code},
  "error_message": ${err_msg},
  "metrics": {"cpu_percent": 0.0, "memory_rss_bytes": 0, "open_fds": 0},
  "custom_metadata": ${existing_meta}
}
EOF
    mv "$tmp_file" "${SFW_STATE_FILE}"

    if [ "$end_time" != "null" ]; then
        cp "${SFW_STATE_FILE}" "${SFW_HISTORY_DIR}/${SFW_SERVICE_NAME}-${SFW_EXECUTION_ID}.json"
    fi
}

sfw_set_metadata() {
    local key="$1"
    local value="$2"

    if ! command -v jq >/dev/null 2>&1; then
        echo "WARN: jq is missing; metadata update skipped." >&2
        return 0
    fi

    if [ -f "${SFW_STATE_FILE}" ]; then
        local tmp_meta
        tmp_meta=$(mktemp "${SFW_STATE_DIR}/.${SFW_SERVICE_NAME}.XXXXXX.tmp")
        jq --arg k "$key" --arg v "$value" '.custom_metadata[$k] = $v | .last_updated = "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"' "${SFW_STATE_FILE}" > "$tmp_meta"
        mv "$tmp_meta" "${SFW_STATE_FILE}"
    fi
}

sfw_log() {
    local level="$1"
    local message="$2"
    local ts
    ts=$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ 2>/dev/null || date -u +%Y-%m-%dT%H:%M:%SZ)

    if command -v jq >/dev/null 2>&1; then
        jq -c -n \
            --arg ts "$ts" \
            --arg svc "$SFW_SERVICE_NAME" \
            --arg exec_id "$SFW_EXECUTION_ID" \
            --arg lvl "$level" \
            --arg msg "$message" \
            '{timestamp: $ts, service: $svc, execution_id: $exec_id, level: $lvl, message: $msg, context: {}}' >> "$SFW_LOG_FILE"
    else
        echo "{\"timestamp\":\"$ts\",\"service\":\"$SFW_SERVICE_NAME\",\"execution_id\":\"$SFW_EXECUTION_ID\",\"level\":\"$level\",\"message\":\"$message\",\"context\":{}}" >> "$SFW_LOG_FILE"
    fi
}

sfw_on_exit() {
    local exit_code=$?
    trap - EXIT ERR SIGTERM SIGINT
    if [ $exit_code -eq 0 ]; then
        sfw_update_status "SUCCESS" 0
    else
        sfw_update_status "FAILED" $exit_code "Command exited with non-zero status"
    fi
}
