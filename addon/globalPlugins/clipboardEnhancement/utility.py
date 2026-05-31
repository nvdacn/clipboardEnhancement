import re
import wx
import webbrowser
import os

from pickle import load
from os import walk
from logHandler import log
from api import copyToClip
from ui import message
from os.path import basename, join, dirname, isfile, getsize
from time import sleep

from .clipboardMonitor import DEFAULT_RESUME_DELAY


def fileLists(files):
	FileList = len(files)
	for i in range(FileList):
		yield f"{basename(files[i])}, 第{i + 1}之{FileList}项， {files[i]}"


m = re.compile(r"[\u4e00-\uf95a]+|[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z])|[0-9]+|[A-Z]+(?![A-Z])")


def segmentWord(text):
	words = []
	positions = []
	for word in m.finditer(text):
		start = word.start()
		end = word.end()
		words.append(word.string[start:end])
		positions.append(start)
	if not words:
		words.append(text)
		positions.append(0)
	return words, positions


def charPToWordP(word_P, char_P):
	temp_Char = 0
	for i in range(len(word_P)):
		if i == len(word_P) - 1 and char_P >= word_P[i]:
			temp_Char = i
			break
		if char_P >= word_P[i] and char_P < word_P[i + 1]:
			temp_Char = i
			break
	return temp_Char


def loadDict():
	with open(join(dirname(__file__), "Dict.pickle"), "rb") as fp:
		dictPickle = load(fp)
	return dictPickle


def translateWord(dict, word):
	result = dict.get(word, dict.get(re.sub("(ing|ed|s)$", "", word)))
	return result


# Protocol: http, https, ftp, nvdaremote, file
_pattern_URL = re.compile(
	r"(https?|ftp|nvdaremote|file)://[-A-Za-z0-9+&@#/%?=~_|!:,.;]+[-A-Za-z0-9+&@#/%=~_|]",
)

# SMB path
_pattern_SMB = re.compile(r'\\\\(?:[^\/|<>?":*\r\n\t]+\\)+[^\/|<>?":*\r\n\t]*')
# Local driver path
_pattern_local_driver = re.compile(r'[a-zA-Z]:\\(?:[^\/|<>?":*\r\n\t]+\\)*[^\/|<>?":*\r\n\t]*')


def tryOpenURL(text: str) -> bool:
	if not isinstance(text, str):
		return False
	match = _pattern_URL.search(text)
	if match:
		return webbrowser.open(match.group(0))
	match = _pattern_local_driver.search(text)
	if match:
		path = match.group(0)
		if os.path.exists(path):
			command = 'start explorer.exe "%s"' % path
			os.system(command)
			return True
		else:
			raise FileNotFoundError(f"找不到文件或目录：\n{path}")
	match = _pattern_SMB.search(text)
	if match:
		path = match.group(0)
		if os.path.exists(path):
			command = 'start explorer.exe "%s"' % path
			os.system(command)
			return True
		else:
			raise FileNotFoundError(f"找不到文件或目录：\n{path}")
	return False


CLIPBOARD_OPEN_ATTEMPTS = 10
CLIPBOARD_OPEN_RETRY_INTERVAL = 0.05


# Alternative style (displayed with most PCs): MB, KB, GB, YB, ZB, ...
alternative = [
	(1024.0**8.0, " YB"),
	(1024.0**7.0, " ZB"),
	(1024.0**6.0, " EB"),
	(1024.0**5.0, " PB"),
	(1024.0**4.0, " TB"),
	(1024.0**3.0, " GB"),
	(1024.0**2.0, " MB"),
	(1024.0**1.0, " KB"),
	(1024.0**0.0, (" byte", " bytes")),
]


def calcSize(bytes, system=alternative):
	for factor, suffix in system:
		if float(bytes) >= float(factor):
			break
	amount = float(bytes / factor)
	if isinstance(suffix, tuple):
		singular, multiple = suffix
		if float(amount) == 1.0:
			suffix = singular
		else:
			suffix = multiple
	return "{:.2F}{}".format(float(amount), suffix)


def paste(obj):
	try:
		sleep(0.5)
		j = 0
		while j < 10:
			try:
				copyToClip(obj.text)
				obj.flg = 0
				message(obj.spoken.rstrip("\r\n"))
				break
			except Exception:
				j += 1
				sleep(0.05)
	finally:
		monitor = getattr(obj, "monitor", None)
		if monitor is not None:
			monitor.resume(delay=DEFAULT_RESUME_DELAY)


def getBitmapInfo():
	"""Return a short description of the bitmap data currently on the clipboard."""
	clipboard = wx.Clipboard.Get()
	if not openWxClipboard(clipboard):
		# Translators: Message shown when bitmap details cannot be read from the clipboard.
		return _("No bitmap data in clipboard")
	try:
		if clipboard.IsSupported(wx.DataFormat(wx.DF_BITMAP)):
			data_object = wx.BitmapDataObject()
			clipboard.GetData(data_object)
			bitmap = data_object.GetBitmap()
			width = bitmap.GetWidth()
			height = bitmap.GetHeight()
			depth = bitmap.GetDepth()
			# Translators: Bitmap details shown when an image is on the clipboard.
			return _("分辨率： {width} x {height}，位深度： {depth}").format(
				width=width,
				height=height,
				depth=depth,
			)
		else:
			# Translators: Message shown when the clipboard does not contain bitmap data.
			return _("No bitmap data in clipboard")
	finally:
		clipboard.Close()


def openWxClipboard(clipboard):
	"""Open a wx clipboard object, retrying briefly while another process owns it."""
	for _attempt in range(CLIPBOARD_OPEN_ATTEMPTS):
		if clipboard.Open():
			return True
		sleep(CLIPBOARD_OPEN_RETRY_INTERVAL)
	log.debugWarning("Attempt to open wx clipboard failed.")
	return False


def calcFiles(files: list[str]) -> str:
	"""Return a short file count and size summary."""
	size = f = d = 0
	for i in files:
		if isfile(i):
			f += 1
			size += getsize(i)
		else:
			d += 1
			for root, dd, ff in walk(i):
				for n in ff:
					size += getsize(join(root, n))
	t = "{}个文件夹,".format(d) if d else ""
	t1 = f"{f}个文件" if f else ""
	size = calcSize(size, alternative)
	return t + t1 + "共{}".format(size)
