"""
Backward-compatibility shim.

All production code that imports from tgbot.translator continues to work:
    from .translator import translator
    from tgbot.translator import AgentSdkTranslator, _extract_json  # tests

The actual implementation lives in tgbot.translators.
"""

from .translators import make_translator
from .translators.base import _extract_json
from .translators.claude_agent import AgentSdkTranslator

__all__ = ["translator", "AgentSdkTranslator", "_extract_json"]

translator = make_translator()
