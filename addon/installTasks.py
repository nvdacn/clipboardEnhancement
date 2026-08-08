# A part of the Clipboard Enhancement add-on for NVDA.
# Copyright (C) 2026 Cary-rowen
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

"""Run installation tasks for the Clipboard Enhancement add-on."""

from __future__ import annotations

import addonHandler
from logHandler import log


_NEW_ADDON_NAME = "nvdaClipboard"


def _removeNewAddon() -> None:
	"""Silently request removal of the newer NVDA Clipboard add-on."""
	try:
		for addon in addonHandler.getAvailableAddons():
			if addon.name == _NEW_ADDON_NAME:
				addon.requestRemove()
	except Exception:
		# A failed cleanup must not roll back installation of the legacy add-on.
		log.exception("Unable to schedule removal of the newer NVDA Clipboard add-on")


def onInstall() -> None:
	"""Schedule removal of the newer add-on without showing a dialog."""
	_removeNewAddon()
