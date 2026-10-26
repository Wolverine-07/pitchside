"""Send Agent Framework traces to Application Insights.

Point APPLICATIONINSIGHTS_CONNECTION_STRING at the Application Insights resource
connected to the Foundry project, and every workflow run, agent call, tool call
and token count shows up in Foundry's tracing view.
"""

from __future__ import annotations

import logging
import os

_done = False


def setup() -> bool:
    global _done
    conn = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if _done or not conn:
        return False
    from agent_framework.observability import configure_otel_providers
    from azure.monitor.opentelemetry.exporter import (
        AzureMonitorLogExporter,
        AzureMonitorMetricExporter,
        AzureMonitorTraceExporter,
    )

    configure_otel_providers(
        service_name="pitchside",
        service_version="0.1.0",
        # All match data is synthetic, so prompts and replies can be recorded in full.
        enable_sensitive_data=True,
        exporters=[
            AzureMonitorTraceExporter(connection_string=conn),
            AzureMonitorLogExporter(connection_string=conn),
            AzureMonitorMetricExporter(connection_string=conn),
        ],
    )
    # Keep traces about the agents, not the HTTP chatter of the SDKs that send them.
    for noisy in (
        "azure",
        "httpx",
        "httpcore",
        "urllib3",
        "opentelemetry",
        "agent_framework._workflows",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _done = True
    return True
