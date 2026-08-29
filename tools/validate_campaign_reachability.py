from __future__ import annotations

import argparse
import json
import urllib.parse

from smoke_browser import CdpClient, debugger_target, wait_for


def campaign_url(base_url: str) -> str:
    parsed = urllib.parse.urlparse(base_url)
    query = urllib.parse.parse_qs(parsed.query)
    query["mode"] = ["campaign"]
    return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query, doseq=True)))


def run(base_url: str, debug_port: int):
    target = debugger_target(debug_port)
    client = CdpClient(target["webSocketDebuggerUrl"])
    try:
        client.command("Runtime.enable")
        client.command("Page.enable")
        client.command("Page.navigate", {"url": campaign_url(base_url)})
        wait_for(client, "Boolean(window.__vesperaController)")
        report = client.evaluate(
            "import('./src/campaign-audit.js').then(({auditCampaignReachability}) => "
            "auditCampaignReachability(window.__vesperaController.data))"
        )
        assert report["status"] == "PASS", report
        assert report["ending_rule_count"] == report["reachable_ending_count"], report
        assert not report["unreachable_ending_ids"], report
        assert not report["duplicate_ending_ids"], report
        assert not report["reference_errors"], report
        assert report["fallback_expected_id"] == report["fallback_resolved_id"], report
        return report
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8767/index.html")
    parser.add_argument("--debug-port", type=int, default=9230)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    report = run(args.url, args.debug_port)
    if not args.verbose:
        report = {
            **{key: value for key, value in report.items() if key != "witnesses"},
            "reachable_ending_ids": [entry["ending_id"] for entry in report["witnesses"]],
        }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
