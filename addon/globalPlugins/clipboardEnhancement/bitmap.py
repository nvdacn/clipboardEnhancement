# The following code is borrowed from NVBox
import io
import sys
from ctypes import c_buffer, POINTER, byref, cast, Structure, sizeof, windll, wintypes, WinError
import winGDI
import winKernel
import winUser
import wx
from contentRecog import RecogImageInfo
from logHandler import log

user32 = windll.user32
gdi32 = windll.gdi32
shell32 = windll.shell32
# 剪贴板数据格式常量
CF_DIB = 8
CF_BITMAP = 2
CF_METAFILEPICT = 3
CF_ENHMETAFILE = 14
CF_HDROP = 15
CF_DSPBITMAP = 130


# 定义一个BMP文件信息头结构体
class BITMAPFILEHEADER(Structure):
    _fields_ = [
        ('bfType', wintypes.WORD),
        ('bfSize', wintypes.DWORD),
        ('bfReserved1', wintypes.WORD),
        ('bfReserved2', wintypes.WORD),
        ('bfOffBits', wintypes.DWORD)
    ]
    
    # 获取二进制数据的方法
    def getBytes(self):
        bytesIo = io.BytesIO()
        for field in self.__class__._fields_:
            bytesIo.write(eval('self.%s' % field[0]).to_bytes(length=sizeof(field[1]), byteorder='little'))
        bytesIo.flush()
        try:
            return bytesIo.getvalue()
        finally:
            bytesIo.close()


# 生成位图信息头
def getBitmapInfo(imgInfo):
    width, height = imgInfo.recogWidth, imgInfo.recogHeight
    bmInfo = winGDI.BITMAPINFOHEADER()
    bmInfo.biSize = sizeof(bmInfo)
    bmInfo.biWidth = width
    bmInfo.biHeight = height * -1
    bmInfo.biPlanes = 1
    bmInfo.biBitCount = 32
    bmInfo.biSizeImage = width * height * bmInfo.biBitCount // 8
    bmInfo.biCompression = winGDI.BI_RGB
    bmInfo.biXPelsPerMeter = bmInfo.biYPelsPerMeter = 2834
    return bmInfo


# 打开内存图像文件
def openMemoryImageFile(imageInfo, pixels):
    # 生成位图信息头
    bitmapInfo = getBitmapInfo(imageInfo)
    # 构造BMP文件信息头
    fileInfo = BITMAPFILEHEADER()
    fileInfo.bfType = 0x4d42  # BM文件标志
    fileInfo.bfOffBits = 14 + bitmapInfo.biSize  # 保存像素数据的字节位置
    fileInfo.bfSize = bitmapInfo.biSizeImage + fileInfo.bfOffBits  # 文件总大小
    fileInfo.bfReserved1 = fileInfo.bfReserved2 = 0  # 保留字段
    # 创建内存文件IO
    imgBytesIo = io.BytesIO()
    imgBytesIo.write(fileInfo.getBytes())  # 写入文件头部信息
    imgBytesIo.write(bitmapInfo)  # 写入位图信息
    imgBytesIo.write(pixels)  # 写入像素点
    imgBytesIo.flush()
    return imgBytesIo


# 复制图片到剪贴板
def copyBitmapToClip(bitmap):
    hbitmap = bitmap
    with winUser.openClipboard(None):
        # 首先需清空剪贴板
        winUser.emptyClipboard()
        if not user32.SetClipboardData(CF_BITMAP, hbitmap):
            raise WinError()


# 从剪贴板获取图片信息
def getClipBitmapInfo():
    with winUser.openClipboard(None):
        handle = user32.GetClipboardData(CF_DIB)
        if not handle:
            raise WinError(-1, 'No bitmap handle.')
        # 拿到图片信息
        with winKernel.HGLOBAL(handle, autoFree=False).lock() as addr:
            bmInfo = winGDI.BITMAPINFO()
            bmInfo.bmiHeader = cast(addr, POINTER(winGDI.BITMAPINFOHEADER)).contents
            return bmInfo


# 从剪贴板获取图像
def getClipBitmap(bmInfo):
    with winUser.openClipboard(None):
        handle = user32.GetClipboardData(CF_BITMAP)
        if not handle:
            raise WinError(-1, 'No bitmap handle.')
        # 宽度和高度
        width, height = bmInfo.bmiHeader.biWidth, bmInfo.bmiHeader.biHeight
        # 翻转图像
        bmInfo.bmiHeader.biHeight = height * -1
        try:  # 显示图像到设备
            screenDC = user32.GetDC(0)
            memDC = gdi32.CreateCompatibleDC(screenDC)
            oldBitmap = gdi32.SelectObject(memDC, handle)
            # 得到像素点
            buffer = (winGDI.RGBQUAD * width * height)()
            gdi32.GetDIBits(memDC, handle, 0, height, buffer, byref(bmInfo), winGDI.DIB_RGB_COLORS)
            return buffer
        finally:  # 清理现场
            gdi32.SelectObject(memDC, oldBitmap)
            gdi32.DeleteDC(memDC)
            user32.ReleaseDC(0, screenDC)


def getClipImageFileList():
    files = set()
    with winUser.openClipboard(None):
        handle = user32.GetClipboardData(CF_HDROP)
        if not handle:
            return
        FS_ENCODING = sys.getfilesystemencoding()
        fileCount = shell32.DragQueryFile(handle, -1, None, 0)
        for index in range(fileCount):
            buf = c_buffer(260)
            shell32.DragQueryFile(handle, index, buf, sizeof(buf))
            try:
                filename = buf.value.decode('gbk')
            except UnicodeDecodeError:
                filename = buf.value.decode(FS_ENCODING)
            except Exception as e:
                log.warning(f"An unexpected error occurred: {e}")
                continue
            if filename.endswith('.jpg') or filename.endswith('.png') or filename.endswith('.bmp'):
                files.add(filename)
    return files


def getClipImage():
    files = getClipImageFileList()
    if files:
        with open(files.pop(), 'rb') as f:
            f.seek(16)  # 跳到 PNG 文件的第 16 个字节位置
            width = int.from_bytes(f.read(4), byteorder='big')  # 宽度
            height = int.from_bytes(f.read(4), byteorder='big')  # 高度
            f.seek(0)
            imgInfo = RecogImageInfo(0, 0, width, height, 1)
            return imgInfo, f.read()
    # 得到剪贴板图片信息
    bmInfo = getClipBitmapInfo()
    imgInfo = RecogImageInfo(0, 0, bmInfo.bmiHeader.biWidth, bmInfo.bmiHeader.biHeight, 1)
    # 得到剪贴板图片像素数据
    pixels = getClipBitmap(bmInfo)
    # 打开内存图像文件
    with openMemoryImageFile(imgInfo, pixels) as f:
        return imgInfo, f.getvalue()


def isImageInClipboard() -> bool:
    return wx.TheClipboard.IsSupported(wx.DataFormat(wx.DF_BITMAP))


def saveClipImage(parent: wx.Window):
    fd = None
    bitmap_data = wx.BitmapDataObject()
    try:
        if not isImageInClipboard():
            return
        wx.TheClipboard.Open()
        if wx.TheClipboard.GetData(bitmap_data):
            RuntimeError(_("剪贴板图片获取失败"))
        wx.TheClipboard.Close()
        fd = wx.FileDialog(parent,
            _("选择图片保存位置"),
            wildcard=_("图片文件 (*.png)|*.png"), style=wx.FD_SAVE|wx.FD_OVERWRITE_PROMPT)
        if fd.ShowModal() == wx.ID_OK:
            path = fd.GetPath()
            if not path.upper().endswith(".PNG"):
                path += ".png"
            bitmap_data.Bitmap.SaveFile(path, wx.BITMAP_TYPE_PNG)
    except Exception as e:
        wx.MessageBox(str(e), _("错误"), wx.OK | wx.ICON_ERROR)
    finally:
        if wx.TheClipboard.IsOpened():
            wx.TheClipboard.Close()
        if fd:
            fd.Destroy()
