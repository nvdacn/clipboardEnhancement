import api
import re
import wx
import webbrowser
import ctypes.wintypes as w
import sys
import os

from pickle import load
from threading import Thread
from ctypes import windll, WINFUNCTYPE, c_int, c_void_p, c_buffer, sizeof, wstring_at
from os import walk
from logHandler import log
from api import copyToClip
from ui import message
from os.path import basename, join, dirname, isfile, getsize
from time import sleep
from . import cues


def fileLists(files):
	FileList = len(files)
	for i in range(FileList):
		yield f'{basename(files[i])}, 第{i+1}之{FileList}项， {files[i]}'


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
	with open(join(dirname(__file__), 'Dict.pickle'), "rb") as fp:
		dictPickle = load(fp)
	return dictPickle


def translateWord(dict, word):
	result = dict.get(word, dict.get(re.sub('(ing|ed|s)$', '', word)))
	return result


# Protocol: http, https, ftp, nvdaremote, file
_pattern_URL = re.compile(
	r'(https?|ftp|nvdaremote|file)://[-A-Za-z0-9+&@#/%?=~_|!:,.;]+[-A-Za-z0-9+&@#/%=~_|]')

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


CF_UNICODETEXT = 0xD
CF_HDROP = 0xF
CF_UPDATE = 0x031d
PASTED = 0x7ffe
u32 = windll.user32
k32 = windll.kernel32
s32 = windll.shell32

OpenClipboard = u32.OpenClipboard
OpenClipboard.argtypes = w.HWND,
OpenClipboard.restype = w.BOOL
GetClipboardData = u32.GetClipboardData
GetClipboardData.argtypes = w.UINT,
GetClipboardData.restype = w.HANDLE
GlobalLock = k32.GlobalLock
GlobalLock.argtypes = w.HGLOBAL,
GlobalLock.restype = w.LPVOID
GlobalUnlock = k32.GlobalUnlock
GlobalUnlock.argtypes = w.HGLOBAL,
GlobalUnlock.restype = w.BOOL
CloseClipboard = u32.CloseClipboard
CloseClipboard.argtypes = None
CloseClipboard.restype = w.BOOL
DragQueryFile = s32.DragQueryFile
DragQueryFile.argtypes = [w.HANDLE, w.UINT, c_void_p, w.UINT]

# Alternative style (displayed with most PCs): MB, KB, GB, YB, ZB, ...
alternative = [
	(1024.0**8.0, ' YB'),
	(1024.0**7.0, ' ZB'),
	(1024.0**6.0, ' EB'),
	(1024.0**5.0, ' PB'),
	(1024.0**4.0, ' TB'),
	(1024.0**3.0, ' GB'),
	(1024.0**2.0, ' MB'),
	(1024.0**1.0, ' KB'),
	(1024.0**0.0, (' byte', ' bytes')),
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
	sleep(0.5)
	j = 0
	while j < 10:
		try:
			copyToClip(obj.text)
			obj.flg = 0
			message(obj.spoken.rstrip('\r\n'))
			break
		except:
			j += 1
			sleep(0.05)
	windll.user32.PostMessageW(obj.editor.GetHandle(), PASTED, 0, 0)


def getBitmapInfo():
	clipboard = wx.Clipboard.Get()
	clipboard.Open()
	try:
		if clipboard.IsSupported(wx.DataFormat(wx.DF_BITMAP)):
			data_object = wx.BitmapDataObject()
			clipboard.GetData(data_object)
			bitmap = data_object.GetBitmap()
			width = bitmap.GetWidth()
			height = bitmap.GetHeight()
			depth = bitmap.GetDepth()
			return f'分辨率： {width} x {height}，位深度： {depth}'
		else:
			return 'No bitmap data in clipboard'
	finally:
		clipboard.Close()


class ClipboardMonitor:

	def __init__(self, handle=None):
		self.handle = handle
		self.__pre_handle = 0
		self.work = True
		self.__mhf = None
		self.data = None

	def customization(self):
		pass

	def getData(self):
		return self.data

	def workReset(self):
		sleep(0.1)
		self.work = True

	def MsgHandleFunc(self, hwnd, msg, wParam, lParam):
		if msg == PASTED:
			self.work = True
		elif msg == CF_UPDATE and self.work:
			self.work = False
			Thread(target=ClipboardMonitor.workReset, args=(self,)).start()
			Thread(target=ClipboardMonitor.get_clipboard_data, args=(self,)).start()
			cues.Copy()
		return windll.user32.CallWindowProcA(self.__pre_handle, hwnd, msg, wParam, lParam)

	def StartMonitor(self):
		self.__mhf = WINFUNCTYPE(c_int, c_int, c_int, c_int, c_int)(self.MsgHandleFunc)
		u32.AddClipboardFormatListener(self.handle)
		self.__pre_handle = windll.user32.SetWindowLongPtrA(self.handle, -4, self.__mhf)

	def Stop(self):
		u32.RemoveClipboardFormatListener(self.handle)
		self.__pre_handle = windll.user32.SetWindowLongPtrA(self.handle, -4, 0)
		self.__mhf = None

	def get_clipboard_data(self):
		self.open_clipboard()
		formats = []
		n = 0
		while True:
			n = windll.user32.EnumClipboardFormats(n)
			if n == 0:
				break
			formats.append(n)
		CloseClipboard()
		if 13 in formats:
			try:
				self.data = self.get_clip_text()
			except:
				self.data = None
		elif 15 in formats:
			try:
				self.data = self.get_clip_file_list()
			except:
				self.data = None
		elif 2 in formats:
			self.data = b''
		else:
			self.data = None
		self.customization()

	def open_clipboard(self, i=10):
		if not OpenClipboard(None):
			CloseClipboard()
			while i > 0:
				sleep(0.1)
				if OpenClipboard(None):
					break
				i -= 1
			else:
				log.debugWarning("Attempt to open clipboard failed.")

	def get_clip_text(self):
		text = ""
		self.open_clipboard()
		h_clip_mem = GetClipboardData(CF_UNICODETEXT)
		text = wstring_at(GlobalLock(h_clip_mem))
		GlobalUnlock(h_clip_mem)
		CloseClipboard()
		return text

	def get_clip_file_list(self):
		files = []
		self.open_clipboard()
		h_hdrop = GetClipboardData(CF_HDROP)
		if not h_hdrop:
			return
		FS_ENCODING = sys.getfilesystemencoding()
		file_count = DragQueryFile(h_hdrop, -1, None, 0)
		for index in range(file_count):
			buf = c_buffer(260)
			DragQueryFile(h_hdrop, index, buf, sizeof(buf))
			try:
				files.append(buf.value.decode('gbk'))
			except:
				try:
					files.append(buf.value.decode(FS_ENCODING))
				except:
					files = None
		CloseClipboard()
		return files

	def calc(self, files):
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
		t = '{}个文件夹,'.format(d) if d else ''
		t1 = f'{f}个文件' if f else ''
		size = calcSize(size, alternative)
		return t + t1 + '共{}'.format(size)
