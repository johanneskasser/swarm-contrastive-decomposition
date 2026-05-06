"""
Discord webhook notifier for HD-EMG decomposition jobs.

Reads completed job results from jobs_config.json, aggregates MU metrics
from output .pkl files (own trusted output, not external input), and sends
a compact embed to a Discord channel.

Usage (CLI):
    python utils/discord_notifier.py \\
        --job-ids job_20260504_120000 [job_20260504_130000 ...] \\
        --webhook-url https://discord.com/api/webhooks/... \\
        [--config path/to/jobs_config.json]
"""

import argparse
import json
import logging
import pickle  # noqa: S403 — loading own trusted output files only
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def _format_duration(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    if minutes > 0:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def _read_pkl_metrics(pkl_path: str) -> dict:
    """Read MU count and silhouette scores from an own-generated pkl file.

    Returns an empty dict if the file is missing or unreadable so callers
    can skip gracefully.
    """
    try:
        with open(pkl_path, 'rb') as f:
            decomp = pickle.load(f)  # noqa: S301 — own trusted output
        sils = [
            float(s.item()) if hasattr(s, 'item') else float(s)
            for s in decomp.get('silhouettes', [])
        ]
        return {"n_mus": len(sils), "sils": sils}
    except Exception as e:
        logger.warning("Could not read %s: %s", pkl_path, e)
        return {}


def collect_job_results(job: dict) -> dict:
    """
    Aggregate metrics from a completed job's output .pkl files.

    Iterates files_processed -> grids_processed, loads each .pkl,
    and accumulates total MU count and silhouette values across all grids.
    Missing or unreadable pkl files are silently skipped.
    """
    total_mus = 0
    all_sils = []
    failed_files_list = []

    for file_result in job.get('files_processed', []):
        if not file_result.get('success'):
            failed_files_list.append({
                "file_name": Path(file_result.get('file_path', '')).name,
                "error": (file_result.get('error') or 'Unknown error')[:120],
            })
            continue

        for grid in file_result.get('grids_processed', []):
            if not grid.get('success', True):
                continue
            output_file = grid.get('output_file', '')
            if output_file and output_file.endswith('.pkl') and Path(output_file).exists():
                metrics = _read_pkl_metrics(output_file)
                total_mus += metrics.get('n_mus', 0)
                all_sils.extend(metrics.get('sils', []))

    successful = job.get('successful_files', 0)
    total = job.get('total_files', 0)
    failed_count = job.get('failed_files', 0)

    if total == 0 or (failed_count > 0 and successful == 0):
        status = "failed"
    elif failed_count == 0:
        status = "success"
    else:
        status = "partial"

    avg_sil = (sum(all_sils) / len(all_sils)) if all_sils else None

    return {
        "job_name": job.get('name', 'Unknown'),
        "status": status,
        "duration_str": _format_duration(job.get('duration_seconds') or 0),
        "total_files": total,
        "successful_files": successful,
        "failed_files": failed_count,
        "total_mus": total_mus,
        "avg_sil": avg_sil,
        "output_path": job.get('output_path', ''),
        "completed_at": job.get('completed_at', ''),
        "failed_files_list": failed_files_list,
    }


def build_discord_payload(summary: dict) -> dict:
    """Build the Discord webhook JSON payload with a single compact embed."""
    status = summary["status"]

    if status == "success":
        color = 3066993   # green
        title = "HD-EMG Decomposition — Complete"
    elif status == "partial":
        color = 16744272  # orange
        title = "HD-EMG Decomposition — Partial Failure"
    else:
        color = 15158332  # red
        title = "HD-EMG Decomposition — Failed"

    avg_sil_str = f"{summary['avg_sil']:.3f}" if summary['avg_sil'] is not None else "—"

    fields = [
        {"name": "Files",          "value": f"{summary['successful_files']}/{summary['total_files']} succeeded", "inline": True},
        {"name": "Motor Units",    "value": str(summary['total_mus']),  "inline": True},
        {"name": "Duration",       "value": summary['duration_str'],    "inline": True},
        {"name": "Avg Silhouette", "value": avg_sil_str,                "inline": True},
        {"name": "Output",         "value": summary['output_path'] or "—", "inline": False},
    ]

    failed = summary.get('failed_files_list', [])
    if failed:
        lines = [f"• {f['file_name']}: {f['error']}" for f in failed[:5]]
        if len(failed) > 5:
            lines.append(f"... and {len(failed) - 5} more")
        fields.append({"name": "Failed files", "value": "\n".join(lines), "inline": False})

    timestamp = None
    completed_at = summary.get('completed_at', '')
    if completed_at:
        try:
            dt = datetime.fromisoformat(completed_at)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            timestamp = dt.isoformat()
        except ValueError:
            pass

    embed = {
        "title": title,
        "description": f"**{summary['job_name']}**",
        "color": color,
        "fields": fields,
        "footer": {"text": f"Completed {completed_at}"},
    }
    if timestamp:
        embed["timestamp"] = timestamp

    return {"embeds": [embed]}


def send_notification(webhook_url: str, payload: dict) -> bool:
    """POST the payload to the Discord webhook. Returns True on success, never raises."""
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status in (200, 204)
    except Exception as e:
        logger.error("Discord notification failed: %s", e)
        return False


def main():
    parser = argparse.ArgumentParser(description="Send Discord notification for SCD decomposition jobs")
    parser.add_argument("--job-ids", nargs="+", required=True, help="Job IDs to notify about")
    parser.add_argument("--webhook-url", required=True, help="Discord webhook URL")
    parser.add_argument("--config", default="jobs_config.json", help="Path to jobs_config.json")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Error: config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        jobs_data = json.load(f)

    jobs_by_id = {j['id']: j for j in jobs_data.get('jobs', [])}

    for job_id in args.job_ids:
        job = jobs_by_id.get(job_id)
        if job is None:
            print(f"Warning: job '{job_id}' not found, skipping", file=sys.stderr)
            continue

        summary = collect_job_results(job)
        payload = build_discord_payload(summary)
        ok = send_notification(args.webhook_url, payload)
        if ok:
            print(f"[OK] Discord notification sent for: {job['name']}")
        else:
            print(f"[X]  Discord notification failed for: {job['name']}", file=sys.stderr)


if __name__ == "__main__":
    main()
