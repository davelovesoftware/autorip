#!/usr/bin/env python3

import re

class DiskInfo:
	def __init__(self):
		self.id = None
		self.type = None
		self.__label = None
		self.__name = None
		self.__season = None
		self.__disc = None

	def __repr__(self):
		return f'{{id: {self.id}, type: {self.type}, label: {self.label}, name: {self.name}, season: {self.season}, disc: {self.disc}}}'

	@staticmethod
	def __cleanLabel(label):
		# Clean up the label using common patterns
		regexes = [
			# Common screen size identifiers
			(r'4[-_X:]3', ''),
			(r'16[-_X:]9', ''),
			(r'16[-_X:]10', ''),
			(r'IMAX', ''),
			(r'WIDESCREEN', ''),
			(r'ULTRAWIDE', ''),
			# Underscores/Dashes (instead of spaces)
			(r'[-_]+', ' '),
			# Country codes
			(r'\s+US(\s+|$)', ''), # TODO: More country codes
			# The letter D or word DISC/DISK followed by a number
			(r'\s+D(I?S[CK])?\s*\d+', ''),
			# The letter S or word SEASON followed by a number
			(r'\s+S(EASON)?\s*\d+', ''),
			# Delux(e)/Collectors Edition
			(r'((DELUXE?)|(COLLECTORS))\s*EDITION', ''),
			# Parentheses/Brackets pairs
			(r'\(\s*?\)', ''),
			(r'\[\s*?\]', ''),
			(r'\{\s*?\}', ''),
			# Collapse whitespace
			(r'\s+', ' ')
		]

		# Apply all the regexes
		for regex in regexes:
			label = re.sub(regex[0], regex[1], label, flags=re.IGNORECASE)

		# Fially, trim any leading/trailing whitespace
		return label.strip()

	@staticmethod
	def __parseSeason(label):
		seasonRegex = r'S(EASON)?[_\s]*(\d+)'
		searchResult = re.search(seasonRegex, label, flags=re.IGNORECASE)
		return int(searchResult.group(2)) if searchResult else None

	@staticmethod
	def __parseDisc(label):
		discRegex = r'D(I?S[CK])?[_\s]*(\d+)'
		searchResult = re.search(discRegex, label, flags=re.IGNORECASE)
		return int(searchResult.group(2)) if searchResult else None

	@property
	def label(self):
		return self.__label

	@label.setter
	def label(self, value):
		self.__label = value
		self.__name = self.__cleanLabel(value)
		self.__season = self.__parseSeason(value)
		self.__disc = self.__parseDisc(value)

	@property
	def name(self):
		return self.__name

	@property
	def season(self):
		return self.__season

	@property
	def disc(self):
		return self.__disc
