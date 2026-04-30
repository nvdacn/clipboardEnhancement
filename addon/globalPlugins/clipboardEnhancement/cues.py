import os
from nvwave import playWaveFile


def Copy():
	play_sound("Copy")


def FileInClipboard():
	play_sound("FileInClipboard")


def StartOrEnd():
	play_sound("StartOrEnd")


def LineBoundary():
	play_sound("LineBoundary")


def play_sound(filename):
	path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "sounds", filename))
	return playWaveFile(path + ".wav")
