#!/usr/bin/env python3

from datetime import datetime

class TitleInfo:
	def __init__(self):
		self.id = None
		self.label = None
		self.duration = None
		self.filename = None

	def __repr__(self):
		return f'{{id: {self.id}, label: {self.label}, duration: {self.duration}, filename: {self.filename}}}'

	def parseDuration(self, value):
		date = datetime.strptime(value , '%H:%M:%S')
		self.duration = (date.hour * 3600) + (date.minute * 60) + date.second
