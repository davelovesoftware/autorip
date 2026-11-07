#!/usr/bin/env python3

import os

class FilePaths:
	def __init__(self):
		self.ripDir = None
		self.transcodeDir = None
		self.outputDir = None
		self.trackIndex = None
		self.ripFile = None
		self.transcodeFile = None
		self.outputFile = None

	def __repr__(self):
		return f'Track Index: {self.trackIndex}\n* Rip Dir: {self.ripDir}\n* Transcode Dir: {self.transcodeDir}\n* Rip File: {self.ripFile}\n* Transcode File: {self.transcodeFile}\n* Output File: {self.outputFile}'

	def buildPaths(self, ripDir, transcodeDir, outputDir, outputExt, diskInfo, trackInfo, trackIndex, useCollectionNaming):
		self.ripDir = ripDir
		self.transcodeDir = transcodeDir
		self.outputDir = outputDir
		self.trackIndex = trackIndex
		track = trackInfo[trackIndex]
		self.ripFile = os.path.join(ripDir, track.filename)
		fileName = f'{diskInfo.label} {track.label}' if len(trackInfo) > 1 else discInfo.name
		if diskInfo.season is not None and diskInfo.disc is not None and useCollectionNaming:
			# If there is a disk and season number we can infer the episode number by assuming each disk has the same number of episodes
			episode = ((diskInfo.disc - 1) * len(trackInfo)) + trackIndex + 1
			fileName = f'{diskInfo.name} S{diskInfo.season:02d}E{episode:02d}'
		self.transcodeFile = os.path.join(transcodeDir, fileName) + outputExt
		self.outputFile = os.path.join(outputDir, fileName) + outputExt
