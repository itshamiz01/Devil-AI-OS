"""Windows desktop adapter (§12) — interface only, DISABLED here.

Staging runs on Linux; Windows UI Automation cannot exist or be tested
in this environment, and the owner's target is a Windows desktop. Per
§30/§32 and the pre-decided environment honesty for this build, the
adapter implements the action interface and reports itself disabled in
the registry, the startup health report and every execution attempt.
There is deliberately NO elevation path in this codebase: no UAC bypass,
no credential capture, no MFA interaction — when the adapter is built
for the owner's machine (Windows Setup doc), secure desktops, UAC
prompts, MFA screens, banking authentication and OS password prompts
remain human-only, and — per §12.3 — an action that would require
elevation returns REQUIRES_HUMAN_ACTION.
"""
from __future__ import annotations

import platform

from .base import AdapterContext, AdapterResult

ACTIONS = ("launch_application", "focus_window", "observe_screen",
           "approved_click", "approved_keyboard", "close_application")


class DesktopAdapter:
    adapter_type = "desktop"
    enabled = False

    def health(self) -> dict:
        return {"status": "disabled", "health_status": "disabled",
                "details": {
                    "platform": platform.system(),
                    "reason": "Windows UI Automation cannot run or be tested in this "
                              "Linux staging environment",
                    "elevation_path": "none exists in code (no UAC bypass, no credential "
                                      "capture, no MFA interaction)",
                    "plan": "evaluate on the owner's Windows machine per "
                            "docs/operations/WINDOWS_SETUP.md",
                }}

    async def execute(self, action: str, parameters: dict,
                      context: AdapterContext) -> AdapterResult:
        return AdapterResult(
            False, error_category="ADAPTER_UNAVAILABLE",
            summary="the Windows desktop adapter is disabled in this environment "
                    "(Linux staging; §12/§30). The action was NOT performed.")
