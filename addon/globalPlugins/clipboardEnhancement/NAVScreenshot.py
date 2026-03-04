# The following code is borrowed from NVBox
import api
import ui
import winGDI
import vision
from contentRecog import RecogImageInfo
from ctypes import windll
from . import bitmap
gdi32 = windll.gdi32
user32 = windll.user32


def navigatorObjectScreenshot():
	# 获取导航对象
	nav = api.getNavigatorObject()
	try:
		# 得到导航对象的位置和大小
		left, top, width, height = nav.location
	except TypeError:
		ui.message(_("Content is not visible"))
		return
	# 生成图像信息
	imgInfo = RecogImageInfo(left, top, width, height, 1)
	# 从屏幕上抓取像素
	try:
		screenDC = user32.GetDC(0)
		memDC = gdi32.CreateCompatibleDC(screenDC)
		memBitmap = gdi32.CreateCompatibleBitmap(screenDC, imgInfo.recogWidth, imgInfo.recogHeight)
		oldBitmap = gdi32.SelectObject(memDC, memBitmap)
		gdi32.StretchBlt(memDC, 0, 0, width, height, screenDC, left, top, width, height, winGDI.SRCCOPY)
		# 把数据放入剪贴板
		bitmap.copyBitmapToClip(memBitmap)
	finally:
		# 清理现场
		gdi32.SelectObject(memDC, oldBitmap)
		gdi32.DeleteObject(memBitmap)
		gdi32.DeleteDC(memDC)
		user32.ReleaseDC(0, screenDC)


def isScreenCurtainRunning():
	try:
		import screenCurtain
		return screenCurtain.screenCurtain and screenCurtain.screenCurtain.enabled
	except ModuleNotFoundError:
		from visionEnhancementProviders.screenCurtain import ScreenCurtainProvider
		screenCurtainId = ScreenCurtainProvider.getSettings().getId()
		screenCurtainProviderInfo = vision.handler.getProviderInfo(screenCurtainId)
		return bool(vision.handler.getProviderInstance(screenCurtainProviderInfo))
