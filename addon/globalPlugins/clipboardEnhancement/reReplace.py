import wx


class ReDialog(wx.Dialog):
	def __init__(self, parent, title="正则替换"):
		super().__init__(parent, title=title, size=(300, 180))
		box = wx.BoxSizer(wx.VERTICAL)
		v1 = wx.BoxSizer(wx.VERTICAL)
		st = wx.StaticText(self, -1, label="查找内容(&N)")
		self.cb = wx.ComboBox(self, -1, style=wx.CB_DROPDOWN)
		v1.Add(st, 1)
		v1.Add(self.cb, 2)
		st2 = wx.StaticText(self, -1, label="替换为(&P)")
		self.cb2 = wx.ComboBox(self, -1, style=wx.CB_DROPDOWN)
		v1.Add(st2, 1)
		v1.Add(self.cb2, 2)
		r1 = wx.BoxSizer(wx.HORIZONTAL)
		b_ok = wx.Button(self, wx.ID_OK, label="替换(&R)")
		b_cancel = wx.Button(self, wx.ID_CANCEL, label="取消")
		r1.Add(b_ok, 1)
		r1.Add(b_cancel, 1)
		box.Add(v1, 1)
		box.Add(r1, 1)
		self.SetSizer(box)
