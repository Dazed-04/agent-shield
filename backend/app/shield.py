"""Process-wide detector singletons shared by the API layer and the agent graph."""

from app.detectors.jailbreak_detector import JailbreakDetector
from app.detectors.prompt_scanner import PromptScanner
from app.detectors.response_scanner import ResponseScanner
from app.detectors.tool_monitor import ToolMonitor

prompt_scanner = PromptScanner()
jailbreak_detector = JailbreakDetector()
response_scanner = ResponseScanner()
tool_monitor = ToolMonitor()
