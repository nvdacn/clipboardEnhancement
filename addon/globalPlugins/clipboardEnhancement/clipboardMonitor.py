from __future__ import annotations

from collections.abc import Callable
from ctypes import POINTER, WinError, c_int, create_unicode_buffer, windll, wstring_at
import ctypes.wintypes as w
from dataclasses import dataclass
from enum import Enum
from threading import Lock, Timer, current_thread
from time import sleep

from logHandler import log
from windowUtils import CustomWindow
import wx

__all__ = [
	"ClipboardContentType",
	"ClipboardMonitor",
	"ClipboardSnapshot",
	"ClipboardSnapshotCallback",
	"ClipboardUpdateCallback",
	"DEFAULT_RESUME_DELAY",
]


class ClipboardContentType(Enum):
	"""Supported clipboard content categories."""

	TEXT = "text"
	FILES = "files"
	IMAGE = "image"
	EMPTY = "empty"
	UNSUPPORTED = "unsupported"
	ERROR = "error"


@dataclass(frozen=True)
class ClipboardSnapshot:
	"""A stable snapshot of the clipboard content recognized by the monitor."""

	contentType: ClipboardContentType
	formatId: int | None = None
	text: str = ""
	files: tuple[str, ...] = ()
	error: str = ""


ClipboardSnapshotCallback = Callable[[ClipboardSnapshot], None]
ClipboardUpdateCallback = Callable[[], None]

CF_BITMAP = 0x2
CF_DIB = 0x8
CF_UNICODETEXT = 0xD
CF_HDROP = 0xF
CF_DIBV5 = 0x11
WM_CLIPBOARDUPDATE = 0x031D
HWND_MESSAGE = -3
DRAG_QUERY_FILE_COUNT = 0xFFFFFFFF

DEFAULT_QUIET_PERIOD = 0.35
DEFAULT_OPEN_RETRIES = 10
DEFAULT_OPEN_RETRY_INTERVAL = 0.05
DEFAULT_RESUME_DELAY = 0.2

_IMAGE_FORMATS = {CF_BITMAP, CF_DIB, CF_DIBV5}
_FORMAT_PRIORITY = (CF_UNICODETEXT, CF_HDROP, CF_BITMAP, CF_DIB, CF_DIBV5)
_FORMAT_NAMES = {
	CF_BITMAP: "CF_BITMAP",
	CF_DIB: "CF_DIB",
	CF_UNICODETEXT: "CF_UNICODETEXT",
	CF_HDROP: "CF_HDROP",
	CF_DIBV5: "CF_DIBV5",
	0: "empty clipboard",
	-1: "no supported format",
}

_user32 = windll.user32
_kernel32 = windll.kernel32
_shell32 = windll.shell32

_addClipboardFormatListener = _user32.AddClipboardFormatListener
_addClipboardFormatListener.argtypes = (w.HWND,)
_addClipboardFormatListener.restype = w.BOOL

_removeClipboardFormatListener = _user32.RemoveClipboardFormatListener
_removeClipboardFormatListener.argtypes = (w.HWND,)
_removeClipboardFormatListener.restype = w.BOOL

_openClipboard = _user32.OpenClipboard
_openClipboard.argtypes = (w.HWND,)
_openClipboard.restype = w.BOOL

_closeClipboard = _user32.CloseClipboard
_closeClipboard.argtypes = ()
_closeClipboard.restype = w.BOOL

_getClipboardData = _user32.GetClipboardData
_getClipboardData.argtypes = (w.UINT,)
_getClipboardData.restype = w.HANDLE

_getPriorityClipboardFormat = _user32.GetPriorityClipboardFormat
_getPriorityClipboardFormat.argtypes = (POINTER(w.UINT), c_int)
_getPriorityClipboardFormat.restype = c_int

_globalLock = _kernel32.GlobalLock
_globalLock.argtypes = (w.HGLOBAL,)
_globalLock.restype = w.LPVOID

_globalUnlock = _kernel32.GlobalUnlock
_globalUnlock.argtypes = (w.HGLOBAL,)
_globalUnlock.restype = w.BOOL

_dragQueryFile = _shell32.DragQueryFileW
_dragQueryFile.argtypes = (w.HANDLE, w.UINT, w.LPWSTR, w.UINT)
_dragQueryFile.restype = w.UINT


def _formatClipboardFormat(formatId: int | None) -> str:
	"""Return a readable name for a clipboard format id."""
	if formatId is None:
		return "none"
	return f"{_FORMAT_NAMES.get(formatId, 'unknown format')} ({formatId})"


class ClipboardMonitor:
	"""Monitor clipboard changes for an NVDA add-on.

	Call :meth:`start` and :meth:`stop` from NVDA's main thread.
	``onUpdate`` is called immediately from the message window thread.
	``onSnapshot`` is called on the wx main thread after the clipboard stops changing.
	"""

	def __init__(
		self,
		onSnapshot: ClipboardSnapshotCallback | None = None,
		onUpdate: ClipboardUpdateCallback | None = None,
		quietPeriod: float = DEFAULT_QUIET_PERIOD,
		openRetries: int = DEFAULT_OPEN_RETRIES,
		openRetryInterval: float = DEFAULT_OPEN_RETRY_INTERVAL,
	) -> None:
		"""Initialize a clipboard monitor for an NVDA add-on."""
		self._onSnapshot = onSnapshot
		self._onUpdate = onUpdate
		self._quietPeriod = quietPeriod
		self._openRetries = openRetries
		self._openRetryInterval = openRetryInterval
		self._window: _ClipboardMessageWindow | None = None
		self._snapshotTimer: Timer | None = None
		self._resumeTimer: Timer | None = None
		self._lock = Lock()
		self._snapshotGeneration = 0
		self._resumeGeneration = 0
		self._isRunning = False
		self._isSuppressed = False
		log.debug(
			"ClipboardMonitor initialized: quietPeriod={}, openRetries={}, openRetryInterval={}".format(
				quietPeriod,
				openRetries,
				openRetryInterval,
			),
		)

	def start(self) -> None:
		"""Start listening for clipboard changes."""
		if self._window is not None:
			log.debug("ClipboardMonitor.start called while already started.")
			return
		window = _createClipboardMessageWindow(self)
		if window.handle is None:
			self._window = None
			raise RuntimeError("Clipboard monitor window was not created.")
		self._window = window
		if not _addClipboardFormatListener(window.handle):
			error = WinError()
			window.destroy()
			self._window = None
			raise error
		with self._lock:
			self._isRunning = True
			self._isSuppressed = False
		log.debug(f"ClipboardMonitor started: hwnd={self._window.handle}")

	def stop(self) -> None:
		"""Stop listening for clipboard changes and release Win32 resources."""
		with self._lock:
			self._isRunning = False
			self._isSuppressed = True
			self._cancelSnapshotTimerLocked(invalidate=True)
			self._cancelResumeTimerLocked(invalidate=True)
		if self._window is None:
			return
		if not _removeClipboardFormatListener(self._window.handle):
			log.debugWarning("Could not remove clipboard format listener.", exc_info=WinError())
		self._window.destroy()
		self._window = None
		log.debug("ClipboardMonitor stopped.")

	def readNow(self) -> ClipboardSnapshot:
		"""Read the current clipboard state synchronously."""
		log.debug(f"ClipboardMonitor read begin: thread={current_thread().name}")
		try:
			snapshot = self._readSnapshot()
		except Exception as e:
			log.debugWarning("ClipboardMonitor failed to read clipboard.", exc_info=True)
			snapshot = ClipboardSnapshot(ClipboardContentType.ERROR, error=str(e))
		log.debug(
			"ClipboardMonitor read complete: contentType={}, format={}".format(
				snapshot.contentType.value,
				_formatClipboardFormat(snapshot.formatId),
			),
		)
		return snapshot

	def suppress(self) -> None:
		"""Ignore clipboard changes until resume is called."""
		with self._lock:
			self._isSuppressed = True
			self._cancelSnapshotTimerLocked(invalidate=True)
			self._cancelResumeTimerLocked(invalidate=True)
		log.debug("ClipboardMonitor suppressed.")

	def resume(self, delay: float = 0.0) -> None:
		"""Resume processing clipboard changes, optionally after a delay."""
		with self._lock:
			if not self._isRunning:
				self._cancelResumeTimerLocked(invalidate=True)
				log.debug("ClipboardMonitor resume ignored because monitor is stopped.")
				return
			if delay > 0:
				self._cancelResumeTimerLocked(invalidate=True)
				generation = self._resumeGeneration
				self._resumeTimer = Timer(delay, self._resumeAfterDelay, args=(generation,))
				self._resumeTimer.daemon = True
				self._resumeTimer.start()
				log.debug(f"ClipboardMonitor resume scheduled: delay={delay}")
				return
			self._cancelResumeTimerLocked(invalidate=True)
			self._isSuppressed = False
		log.debug("ClipboardMonitor resumed.")

	def _resumeAfterDelay(self, generation: int) -> None:
		"""Resume processing if the delayed resume request is still current."""
		with self._lock:
			if generation != self._resumeGeneration or self._resumeTimer is None or not self._isRunning:
				return
			self._resumeTimer = None
			self._isSuppressed = False
		log.debug("ClipboardMonitor resumed after delay.")

	def _handleClipboardUpdate(self) -> None:
		"""Handle WM_CLIPBOARDUPDATE from the message window."""
		with self._lock:
			shouldProcess = self._isRunning and not self._isSuppressed
		log.debug(
			"ClipboardMonitor received WM_CLIPBOARDUPDATE: process={}, thread={}".format(
				shouldProcess,
				current_thread().name,
			),
		)
		if not shouldProcess:
			return
		isNewBatch = self._scheduleRead()
		if isNewBatch and self._onUpdate is not None:
			self._safeCall(self._onUpdate)

	def _scheduleRead(self) -> bool:
		"""Schedule a coalesced snapshot read."""
		with self._lock:
			if not self._isRunning or self._isSuppressed:
				return False
			isNewBatch = self._snapshotTimer is None
			self._snapshotGeneration += 1
			generation = self._snapshotGeneration
			self._cancelSnapshotTimerLocked()
			self._snapshotTimer = Timer(self._quietPeriod, self._onQuietPeriodElapsed, args=(generation,))
			self._snapshotTimer.daemon = True
			self._snapshotTimer.start()
			log.debug(
				"ClipboardMonitor scheduled read: quietPeriod={}, isNewBatch={}, generation={}".format(
					self._quietPeriod,
					isNewBatch,
					generation,
				),
			)
			return isNewBatch

	def _cancelSnapshotTimerLocked(self, invalidate: bool = False) -> None:
		"""Cancel any pending snapshot read while holding the monitor lock."""
		if invalidate:
			self._snapshotGeneration += 1
		if self._snapshotTimer is not None:
			self._snapshotTimer.cancel()
			self._snapshotTimer = None
			log.debug("ClipboardMonitor canceled pending read.")

	def _cancelResumeTimerLocked(self, invalidate: bool = False) -> None:
		"""Cancel any pending delayed resume while holding the monitor lock."""
		if invalidate:
			self._resumeGeneration += 1
		if self._resumeTimer is not None:
			self._resumeTimer.cancel()
			self._resumeTimer = None
			log.debug("ClipboardMonitor canceled pending resume.")

	def _onQuietPeriodElapsed(self, generation: int) -> None:
		"""Read the clipboard after no newer update has arrived."""
		with self._lock:
			if (
				self._snapshotTimer is None
				or generation != self._snapshotGeneration
				or not self._isRunning
				or self._isSuppressed
			):
				return
			self._snapshotTimer = None
		snapshot = self.readNow()
		with self._lock:
			if generation != self._snapshotGeneration or not self._isRunning or self._isSuppressed:
				log.debug("ClipboardMonitor dropped stale snapshot.")
				return
		if self._onSnapshot is not None:
			wx.CallAfter(self._safeDispatchSnapshot, generation, snapshot)

	def _safeDispatchSnapshot(self, generation: int, snapshot: ClipboardSnapshot) -> None:
		"""Dispatch a snapshot callback if it is still current."""
		with self._lock:
			if generation != self._snapshotGeneration or not self._isRunning or self._isSuppressed:
				log.debug("ClipboardMonitor dropped queued snapshot.")
				return
			callback = self._onSnapshot
		if callback is not None:
			self._safeCall(callback, snapshot)

	def _safeCall(self, callback: Callable[..., None], *args: object) -> None:
		"""Call a user callback without letting exceptions escape wx dispatch."""
		try:
			callback(*args)
		except Exception:
			log.debugWarning("ClipboardMonitor callback failed.", exc_info=True)

	def _readSnapshot(self) -> ClipboardSnapshot:
		"""Read the clipboard into a snapshot."""
		formatId = self._getPriorityFormat()
		if formatId == 0:
			return ClipboardSnapshot(ClipboardContentType.EMPTY, formatId=formatId)
		if formatId == -1:
			return ClipboardSnapshot(ClipboardContentType.UNSUPPORTED, formatId=formatId)
		if formatId in _IMAGE_FORMATS:
			return ClipboardSnapshot(ClipboardContentType.IMAGE, formatId=formatId)
		if formatId not in (CF_UNICODETEXT, CF_HDROP):
			return ClipboardSnapshot(ClipboardContentType.UNSUPPORTED, formatId=formatId)

		if not self._openClipboardWithRetry():
			return ClipboardSnapshot(ClipboardContentType.ERROR, formatId=formatId, error="OpenClipboard failed")
		try:
			if formatId == CF_UNICODETEXT:
				return ClipboardSnapshot(
					ClipboardContentType.TEXT,
					formatId=formatId,
					text=self._readTextFromOpenClipboard(),
				)
			return ClipboardSnapshot(
				ClipboardContentType.FILES,
				formatId=formatId,
				files=tuple(self._readFilesFromOpenClipboard()),
			)
		finally:
			if not _closeClipboard():
				log.debugWarning("ClipboardMonitor failed to close clipboard.", exc_info=WinError())
			else:
				log.debug("ClipboardMonitor closed clipboard.")

	def _getPriorityFormat(self) -> int:
		"""Return the first available clipboard format supported by the monitor."""
		formats = (w.UINT * len(_FORMAT_PRIORITY))(*_FORMAT_PRIORITY)
		formatId = _getPriorityClipboardFormat(formats, len(_FORMAT_PRIORITY))
		log.debug(f"ClipboardMonitor priority format: {_formatClipboardFormat(formatId)}")
		return formatId

	def _openClipboardWithRetry(self) -> bool:
		"""Open the clipboard, retrying while another process owns it."""
		for attempt in range(1, self._openRetries + 1):
			if _openClipboard(None):
				log.debug(f"ClipboardMonitor OpenClipboard succeeded on attempt {attempt}.")
				return True
			log.debug(f"ClipboardMonitor OpenClipboard failed on attempt {attempt}: {WinError()}")
			if attempt < self._openRetries:
				sleep(self._openRetryInterval)
		return False

	def _readTextFromOpenClipboard(self) -> str:
		"""Read CF_UNICODETEXT while the clipboard is open."""
		handle = _getClipboardData(CF_UNICODETEXT)
		if not handle:
			raise WinError()
		address = _globalLock(handle)
		if not address:
			raise WinError()
		try:
			text = wstring_at(address)
			log.debug(f"ClipboardMonitor read text: chars={len(text)}")
			return text
		finally:
			_globalUnlock(handle)

	def _readFilesFromOpenClipboard(self) -> list[str]:
		"""Read CF_HDROP file paths while the clipboard is open."""
		handle = _getClipboardData(CF_HDROP)
		if not handle:
			raise WinError()
		fileCount = _dragQueryFile(handle, DRAG_QUERY_FILE_COUNT, None, 0)
		files: list[str] = []
		for index in range(fileCount):
			fileNameLength = _dragQueryFile(handle, index, None, 0)
			buffer = create_unicode_buffer(fileNameLength + 1)
			if _dragQueryFile(handle, index, buffer, len(buffer)):
				files.append(buffer.value)
		log.debug(f"ClipboardMonitor read files: count={len(files)}")
		return files


class _ClipboardMessageWindow(CustomWindow):
	"""Message-only window that receives clipboard update messages."""

	className = f"{__name__}.Window"

	def __init__(self, monitor: ClipboardMonitor) -> None:
		"""Create the message-only window."""
		self._monitor = monitor
		super().__init__(windowName=self.className, parent=HWND_MESSAGE)

	def windowProc(self, hwnd: int, msg: int, wParam: int, lParam: int) -> int | None:
		"""Process messages sent to this window."""
		if msg == WM_CLIPBOARDUPDATE:
			self._monitor._handleClipboardUpdate()
			return 0
		return None


def _createClipboardMessageWindow(monitor: ClipboardMonitor) -> _ClipboardMessageWindow:
	"""Create a message window class unique to this monitor instance."""
	windowClass = type(
		"_ClipboardMessageWindow_{:x}".format(id(monitor)),
		(_ClipboardMessageWindow,),
		{"className": "{}.{:x}".format(_ClipboardMessageWindow.className, id(monitor))},
	)
	return windowClass(monitor)
