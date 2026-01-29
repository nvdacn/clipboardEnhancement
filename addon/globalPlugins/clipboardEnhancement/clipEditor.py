import re

import api
import wx
from logHandler import log

from . import reReplace, utility

# 获取翻译函数，如果不可用则使用默认函数
try:
	_
except NameError:
	def _(arg):
		return arg


class MyFrame(wx.Frame):
	def __init__(self, *args, **kw):
		wx.Frame.__init__(self, size=(600, 460), *args, **kw)
		self.is_exit = False
		self.original_content = ""  # 记录打开时的原始内容
		pnl = wx.Panel(self)
		self.edit = wx.TextCtrl(
			pnl, pos=(0, 0), style=wx.TE_PROCESS_TAB | wx.TE_MULTILINE | wx.TE_RICH2 | wx.HSCROLL)
		menubar = wx.MenuBar()
		file_menu = wx.Menu()
		file_menu.Append(wx.ID_OPEN, '打开(&O)\tCtrl+O', '打开文件')
		update = file_menu.Append(-1, '更新(&S)\tCTRL+S', '更新剪贴板数据')
		self.saveImage = file_menu.Append(0, '保存图片到文件(&I)\tCtrl+I', '保存剪贴板图片数据为本地文件')
		self.Bind(wx.EVT_MENU, self.on_saveImageFromClip, self.saveImage)
		file_menu.Append(wx.ID_SAVE, '更新并关闭(&X)\tCTRL+Shift+X', '更新剪贴板数据并关闭剪贴板编辑器')
		file_menu.Append(wx.ID_SAVEAS, '另存为(&A)\tCTRL+Shift+S', '另存为文件')
		file_menu.Append(wx.ID_EXIT, '退出(&C)\tCTRL+E', '关闭剪贴板编辑器')
		self.edit.Bind(wx.EVT_KEY_DOWN, self.on_key_down)
		self.Bind(wx.EVT_MENU, self.on_open, id=wx.ID_OPEN)
		self.Bind(wx.EVT_MENU, self.on_update, update)
		self.Bind(wx.EVT_MENU, self.on_save, id=wx.ID_SAVE)
		self.Bind(wx.EVT_MENU, self.on_save_as, id=wx.ID_SAVEAS)
		self.Bind(wx.EVT_MENU, self.on_exit, id=wx.ID_EXIT)
		menubar.Append(file_menu, '文件(&F)')
		# Use the SET FOCUS event instead
		# self.Bind(wx.EVT_MENU_OPEN, self.OnMenuOpen, id=menubar.GetId())
		self.Bind(wx.EVT_SET_FOCUS, self.OnSetFocus)
		self.Bind(wx.EVT_SHOW, self.on_show)
		self.Bind(wx.EVT_CLOSE, self.on_exit)
		edit_menu = wx.Menu()
		find = edit_menu.Append(-1, '查找(&F)\tCtrl+F', '查找文本')
		self.Bind(wx.EVT_MENU, self.on_show_find, find)
		replace = edit_menu.Append(-1, '替换(&H)\tCtrl+H', '替换文本')
		self.Bind(wx.EVT_MENU, self.on_show_replace, replace)
		next_item = edit_menu.Append(-1, '查找下一个(&N)\tF3', '查找下一个匹配项')
		self.Bind(wx.EVT_MENU, self.on_next, next_item)
		goto_item = edit_menu.Append(-1, '转到(&G)\tCtrl+G', '转到指定行')
		self.Bind(wx.EVT_MENU, self.on_goto, goto_item)
		previous_item = edit_menu.Append(-1, '查找上一个(&P)\tShift+F3', '查找上一个匹配项')
		self.Bind(wx.EVT_MENU, self.on_previous, previous_item)
		replacement = edit_menu.Append(-1, '正则替换(&R)\tCtrl+R', '使用正则表达式替换文本')
		self.Bind(wx.EVT_MENU, self.on_replacement, replacement)
		menubar.Append(edit_menu, '编辑(&E)')
		self.SetMenuBar(menubar)
		self.find_data = wx.FindReplaceData(wx.FR_DOWN)
		# self.edit.SetFont(wx.FFont(7, wx.DEFAULT, wx.NORMAL))
		self.Bind(wx.EVT_SIZE, self.on_size)

	def on_key_down(self, evt):
		code = evt.GetKeyCode()
		if code == wx.WXK_ESCAPE:
			# 调用 on_exit 来检查是否需要保存
			self.on_exit(evt)
			position = self.edit.GetInsertionPoint()
			XY = self.edit.PositionToXY(position)
			if XY[0]:
				self.set_clipboard_position(XY[1], XY[2])
		evt.Skip()

	def set_clipboard_position(self, x, y):
		pass

	def on_update(self, evt):
		text = self.edit.GetValue()
		if not text:
			self.clear_clipboard()
		else:
			api.copyToClip(text)

	def on_replacement(self, evt):
		dlg = reReplace.ReDialog(self)
		if dlg.ShowModal() == wx.ID_OK:
			pattern = dlg.cb.GetValue()
			aim = dlg.cb2.GetValue()
			try:
				self.edit.SetValue(re.sub(pattern, aim, self.edit.GetValue()))
				self.save_history(pattern, aim)
			except re.error as e:
				error_message = "替换操作失败：{}".format(str(e))
				wx.MessageBox(error_message, "错误", wx.OK | wx.ICON_ERROR)
			dlg.Destroy()

	def save_history(self, pattern, aim):
		pass

	def on_next(self, e):
		self.find_data.SetFlags(self.find_data.GetFlags() | wx.FR_DOWN)
		if not self.find_data.GetFindString():
			self.on_show_find(wx.EVT_MENU)
		else:
			self.on_find(wx.EVT_FIND)

	def on_previous(self, event):
		self.find_data.SetFlags(self.find_data.GetFlags() & ~wx.FR_DOWN)
		if not self.find_data.GetFindString():
			self.on_show_find(wx.EVT_MENU)
		else:
			self.on_find(wx.EVT_FIND)

	def on_show_find(self, event):
		dlg = wx.FindReplaceDialog(self, self.find_data, '查找')
		dlg.Bind(wx.EVT_FIND, self.on_find)
		dlg.Bind(wx.EVT_FIND_NEXT, self.on_find)
		dlg.Bind(wx.EVT_FIND_CLOSE, self.on_find_close)
		dlg.Show()

	def on_show_replace(self, event):
		dlg = wx.FindReplaceDialog(self, self.find_data, '替换', wx.FR_REPLACEDIALOG)
		dlg.Bind(wx.EVT_FIND, self.on_find)
		dlg.Bind(wx.EVT_FIND_REPLACE, self.on_replace)
		dlg.Bind(wx.EVT_FIND_REPLACE_ALL, self.on_replace_all)
		dlg.Bind(wx.EVT_FIND_CLOSE, self.on_find_close)
		dlg.Show()

	def on_find(self, event):
		find_text = self.find_data.GetFindString()
		offset = self.edit.GetInsertionPoint()
		if self.find_data.GetFlags() & wx.FR_DOWN:
			if self.edit.GetStringSelection().lower() == find_text.lower():
				offset += len(find_text)
			aim_text = self.edit.GetRange(offset, self.edit.GetLastPosition())
			if not self.find_data.GetFlags() & wx.FR_MATCHCASE:
				start = aim_text.lower().find(find_text.lower())
			else:
				start = aim_text.find(find_text)
		else:
			aim_text = self.edit.GetRange(0, offset)
			if not self.find_data.GetFlags() & wx.FR_MATCHCASE:
				start = aim_text.lower().rfind(find_text.lower())
			else:
				start = aim_text.rfind(find_text)
		if start > -1:
			start += offset if self.find_data.GetFlags() & wx.FR_DOWN else 0
			self.edit.SetSelection(start, start + len(find_text))
		else:
			wx.MessageBox('找不到\"{}\"'.format(find_text), '提示')

	def on_replace(self, event):
		find_text = self.find_data.GetFindString()
		replace_text = self.find_data.GetReplaceString()
		offset = self.edit.GetInsertionPoint()
		text = self.edit.GetRange(offset, self.edit.GetLastPosition())
		if not self.find_data.GetFlags() & wx.FR_MATCHCASE:
			start = text.lower().find(find_text.lower())
		else:
			start = text.find(find_text)
		if start > -1:
			start += offset
			self.edit.Replace(start, start + len(find_text), replace_text)

	def on_replace_all(self, event):
		find_text = self.find_data.GetFindString()
		replace_text = self.find_data.GetReplaceString()
		offset = 0
		count = 0
		while True:
			text = self.edit.GetRange(offset, self.edit.GetLastPosition())
			start = text.find(find_text)
			if start == -1:
				break
			start += offset
			self.edit.Replace(start, start + len(find_text), replace_text)
			offset = self.edit.GetInsertionPoint()
			count += 1
		if count > 0:
			wx.MessageBox('已替换{}个匹配项'.format(count), '提示')
		else:
			wx.MessageBox('找不到\"{}\"'.format(find_text), '提示')

	def on_find_close(self, event):
		event.GetDialog().Destroy()

	def on_goto(self, event):
		try:
			_retval, _col, current_line_num = self.edit.PositionToXY(self.edit.GetInsertionPoint())
		except Exception:
			current_line_num = 0
		total_lines = self.edit.GetNumberOfLines()
		if total_lines == 0:
			total_lines = 1
		dlg = wx.NumberEntryDialog(
			self,
			'请输入要跳转到的行号:',
			'行号(&L)',
			'转到指定行',
			current_line_num + 1,
			1,
			total_lines
		)
		if dlg.ShowModal() == wx.ID_OK:
			target_line = dlg.GetValue()
			point = self.edit.XYToPosition(0, target_line - 1)
			self.edit.SetInsertionPoint(point)
			self.edit.SetFocus()
			self.edit.ShowPosition(point)
		dlg.Destroy()

	def on_open(self, event):
		wildcard = '文本文档 (*.txt)|*.txt|' \
		'所有文件 (*.*)|*.*'
		filename = ''
		dlg = wx.FileDialog(self, message='选择一个文件', defaultDir='', defaultFile="", wildcard=wildcard,
		                    style=wx.FD_OPEN | wx.FD_CHANGE_DIR | wx.FD_FILE_MUST_EXIST)
		if dlg.ShowModal() == wx.ID_OK:
			filename = dlg.GetPath()
		dlg.Destroy()
		if not filename:
			return
		try:
			with open(filename) as f:
				self.edit.SetValue(f.read())
		except Exception as e:
			log.warning(f"An unexpected error occurred: {e}")
			try:
				with open(filename, encoding='utf-8') as f:
					self.edit.SetValue(f.read())
			except Exception as e:
				wx.MessageBox(str(e), '错误')

	def on_save_as(self, evt):
		text = self.edit.GetValue()
		wildcard = '文本文档 (*.txt)|*.txt|' \
		'所有文件 (*.*)|*.*'
		filepath = ''
		dlg = wx.FileDialog(self, message='文件另存为...', defaultDir='', defaultFile='', wildcard=wildcard,
		                    style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
		if dlg.ShowModal() == wx.ID_OK:
			filepath = dlg.GetPath()
		dlg.Destroy()
		if not filepath:
			return
		with open(filepath, 'wb') as f:
			f.write(text.encode('utf8'))

	def on_save(self, event):
		text = self.edit.GetValue()
		if text:
			api.copyToClip(text)
		else:
			self.clear_clipboard()
		self.Show(False)

	def on_exit(self, event):
		current_content = self.edit.GetValue()
		# 检查内容是否有变化
		if current_content != self.original_content:
			# 弹出对话框询问用户是否保存
			dlg = wx.MessageDialog(
				self,
				_("文档已更改，是否保存？"),
				_("保存确认"),
				wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION
			)
			result = dlg.ShowModal()
			dlg.Destroy()
			
			if result == wx.ID_YES:
				# 用户选择保存，更新剪贴板
				self.on_update(None)
				self.Show(False)
			elif result == wx.ID_NO:
				# 用户选择不保存，直接退出
				self.Show(False)
			# 如果是 wx.ID_CANCEL，什么都不做，保持窗口打开
		else:
			# 内容没有变化，直接退出
			self.Show(False)

	def on_saveImageFromClip(self, evt):
		from .PIL import Image, ImageGrab
		fd = None
		try:
			image = ImageGrab.grabclipboard()
			if not isinstance(image, Image.Image):
				return
			fd = wx.FileDialog(self,
				_("选择图片保存位置"),
				wildcard=_("图片文件 (*.png)|*.png"), style=wx.FD_SAVE|wx.FD_OVERWRITE_PROMPT)
			if fd.ShowModal() == wx.ID_OK:
				path = fd.GetPath()
				if not path.upper().endswith(".PNG"):
					path += ".png"
				image.save(path, format="png")
		except Exception as e:
			wx.MessageBox(str(e), _("错误"), wx.OK | wx.ICON_ERROR)
		finally:
			if fd:
				fd.Destroy()

	def on_size(self, event):
		self.edit.SetSize(self.GetClientSize())
		event.Skip()

	def clear_clipboard(self):
		import winUser
		with winUser.openClipboard():
			winUser.emptyClipboard()

	def isImageInClipboard(self):
		clipboard = wx.Clipboard.Get()
		clipboard.Open()
		try:
			return clipboard.IsSupported(wx.DataFormat(wx.DF_BITMAP))
		finally:
			clipboard.Close()

	def RefreshUIForImage(self, isContainImage=False):
		if isContainImage:
			self.saveImage.Enable(True)
			self.Title = "剪贴板编辑器（包含图片）"
			self.edit.SetValue(utility.getBitmapInfo())
		else:
			self.saveImage.Enable(False)
			self.Title = "剪贴板编辑器"

	def OnSetFocus(self, event):
		self.RefreshUIForImage(self.isImageInClipboard())

	def OnMenuOpen(self, event):
		# Use the SET FOCUS event instead
		pass
		# self.RefreshUIForImage(self.isImageInClipboard())

	def on_show(self, event):
		if event.IsShown():
			self.RefreshUIForImage(self.isImageInClipboard())
			# 记录打开时的原始内容
			self.original_content = self.edit.GetValue()
		event.Skip()
