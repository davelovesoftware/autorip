#!/usr/bin/env python3

import subprocess, os, sys, threading, signal, shutil, re

# General constants
MAKEMKV_MINLENGTH = '--minlength=900' # 15 minutes

# Environment variable names
OUTPUT_VID_DIR = 'OUTPUT_VID_DIR'
OUTPUT_VID_EXT = 'OUTPUT_VID_EXT'
HANDBRAKE_ARGS = 'HANDBRAKE_ARGS'

# The stop event to kill the main thread
stop = threading.Event()

class TitleInfo:
	def __init__(self):
		self.id = None
		self.type = ''
		self.label = ''

	def __repr__(self):
		return f'{{id: {self.id}, type: {self.type}, label: {self.label}}}'

def cleanTitle(title):
	# Clean up the title using common patterns
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
		title = re.sub(regex[0], regex[1], title, flags=re.IGNORECASE)

	# Fially, trim any leading/trailing whitespace
	return title.strip()

def getInfo(driveNumber):
	cinfoReg = r'^CINFO:(\d+),(\d+),"?(.+?)"?$'
	tinfoReg = r'^TINFO:(\d+),(\d+),(\d+),"?(.+?)"?$'

	# Get the disk info using MakeMKV
	makemkvDrive = 'disc:' + str(driveNumber)
	print(f'>>> Getting disk info (using MakeMKV) from {makemkvDrive}...')
	makemkvProc = subprocess.Popen(['makemkvcon', '--robot', MAKEMKV_MINLENGTH, 'info', makemkvDrive], stdout = subprocess.PIPE)
	makemkvResult = makemkvProc.wait()
	if makemkvResult != 0:
		print(f'ERROR MakeMKV failed, code: {makemkvResult}.')
		return None, None

	diskInfo = TitleInfo()
	trackInfoById = {}

	# Parse the disk info
	for line in makemkvProc.stdout:
		line = line.decode().strip()

		if line.startswith('CINFO:'):
			# This line is disk data
			searchResult = re.search(cinfoReg, line)
			attributeId = int(searchResult.group(1))
			attributeValue = searchResult.group(3)
			match attributeId:
				case 1:
					# Disk type
					diskInfo.type = attributeValue
				case 2:
					# Disk name/label
					diskInfo.label = attributeValue
				case 32:
					# Disk id (volume name)
					diskInfo.id = attributeValue

					# Also use as a backup for the label
					if len(diskInfo.label) < 1:
						diskInfo.Label = attributeValue

		if line.startswith('TINFO:'):
			# This line is track/title info
			searchResult = re.search(tinfoReg, line)

			# Note: this is the track number in the output which is distinct
			# from the track id (which is the value of attribute 24)
			trackNum = int(searchResult.group(1))

			attributeId = int(searchResult.group(2))
			attributeValue = searchResult.group(4)

			# Make sure this track is in the dict
			if trackNum not in trackInfoById:
				trackInfoById[trackNum] = TitleInfo()
			trackInfo = trackInfoById[trackNum]

			match attributeId:
				case 2:
					# Track name/label
					trackInfo.label = attributeValue
				case 24:
					# Track id
					trackInfo.id = int(attributeValue)

	# Return the results
	trackInfo = list(trackInfoById.values())
	trackInfo.sort(key = lambda x: x.id)
	print(f'Got disk info: {diskInfo} and track info: {trackInfo}.')
	return diskInfo, trackInfo

def rip(driveNumber, drivePath, workDir):
	# Rip the disk in this drive

	# TODO: Make this function cancel subprocesses and cleanup if the stop event is set

	# Ensure the rip and transcode directories exist and are clean
	ripDir = os.path.join(workDir, 'rip')
	transcodeDir = os.path.join(workDir, 'transcode')
	if os.path.exists(ripDir):
		# Delete the rip dir
		print('WARNING: Old rip directory exists, deleting it.')
		shutil.rmtree(ripDir)
	if os.path.exists(transcodeDir):
		# Delete the transcode directory
		print('WARNING: Old transcode directory exists, deleting it.')
		shutil.rmtree(transcodeDir)
	os.mkdir(ripDir)
	os.mkdir(transcodeDir)

	# Get the name of the track
	(diskInfo, trackInfo) = getInfo(driveNumber)
	if diskInfo is None or trackInfo is None or len(trackInfo) < 1:
		print('ERROR: Failed to get any track information.')
		return -1
	title = trackInfo[0].label if len(trackInfo[0].label) > 1 else diskInfo.label
	# Clean the title string
	title = cleanTitle(title)

	# Run MakeMKV
	makemkvDrive = 'disc:' + str(driveNumber)
	print(f'>>> Ripping {title} from {makemkvDrive} into {ripDir} using MakeMKV...')
	makemkvProc = subprocess.Popen(['makemkvcon', '--decrypt', MAKEMKV_MINLENGTH, 'mkv', makemkvDrive, 'all', ripDir])
	makemkvResult = makemkvProc.wait()
	if makemkvResult != 0:
		print('ERROR: MakeMKV failed, code: {makemkvResult}.')
		return -1

	# Get the extension and output directory
	outputVidDir = os.environ[OUTPUT_VID_DIR]
	outputVidExt = os.environ[OUTPUT_VID_EXT]
	handbrakeArgs = os.environ[HANDBRAKE_ARGS]

	# Make the temp and final filenames
	transcodeFile = os.path.join(transcodeDir, title) + outputVidExt
	outputFile = os.path.join(outputVidDir, title) + outputVidExt

	# Run Handbrake
	print(f'>>> Transcoding {title} from {ripDir} into {transcodeFile} using HandBrake...')
	handbrakeCmd = ['HandBrakeCLI', '-i', ripDir, '-o', transcodeFile]
	handbrakeCmd.extend(handbrakeArgs.split())
	handbrakeProc = subprocess.Popen(handbrakeCmd)
	handbrakeResult = handbrakeProc.wait()
	if handbrakeResult != 0:
		print('ERROR: HandBrake failed, code: {handbrakeResult}.')
		return -1

	# Copy file to final output
	# TODO: Handle cases when the file already exists
	print(f'>>> Copying output from {transcodeFile} to {outputFile}...')
	shutil.copy(transcodeFile, outputFile)

	# Eject
	print(f'>>> Ejecting drive {drivePath}...')
	ejectProc = subprocess.Popen(['eject', drivePath])
	ejectResult = ejectProc.wait()
	if ejectResult != 0:
		print(f'WARNING: Unable to eject drive {drivePath}, code: {ejectResult}.')

	# Cleanup
	print(f'>>> Cleaning up work directories ({ripDir}, {transcodeDir})...')
	shutil.rmtree(ripDir)
	shutil.rmtree(transcodeDir)
	return 0

ripThreads = {}
ripLock = threading.Semaphore()
def ripLocked(drivePath, rootDir):
	# Parse the drive number
	driveNumber = int(re.search(r'^/dev/[a-z]+(\d+)$', drivePath).group(1))

	# Get the rip thread lock
	ripLock.acquire()
	try:
		# Check the drive to see if it is in use
		if driveNumber in ripThreads and ripThreads[driveNumber] is not None and ripThreads[driveNumber].is_alive():
			# Device is busy
			print(f'Device is already in use: {drivePath}. Skipping event.')
			return 0

		# Save this thread as the active one for this device
		ripThreads[driveNumber] = threading.current_thread()
	finally:
		ripLock.release()

	# Start the rip operation
	return rip(driveNumber, drivePath, rootDir)

def udevParse(udevStream, rootDir):
	# Event constants
	DEVNAME = 'DEVNAME'
	DISK_EJECT_REQUEST = 'DISK_EJECT_REQUEST'

	evtData = {}

	print('Reading udev events...')

	# Read the udev events and make them into groups
	for line in udevStream:
		line = line.decode().rstrip()
		print(line)
		if line == '':
			print(f'Handling udev event: {evtData}.')

			# Be sure this event has a drive associated
			if DEVNAME not in evtData.keys():
				# The device is missing from the event
				print(f'WARNING: The {DEVNAME} key is missing from the udev event. Skipping event.')
				evtData = {}
				continue

			# Ignore eject request events
			if DISK_EJECT_REQUEST in evtData.keys():
				# This is an eject request
				print(f'Ignoring eject request event.')
				evtData = {}
				continue

			# Get the drive path and number
			drivePath = evtData[DEVNAME]

			# Start a thread to handle the event
			ripThread = threading.Thread(target=ripLocked, args=(drivePath, rootDir))
			ripThread.daemon = True
			ripThread.start()

			# Reset event data
			evtData = {}
		elif '=' in line:
			# Add this event variable to the event
			evtLine = line.partition('=')
			evtData[evtLine[0]] = evtLine[2]

def main():
	# ASSUMPTION: A writeable directory is mounted at /etc/autorip
	rootDir = '/etc/autorip'
	logFile = f'{rootDir}/autorip.log'

	# Copy the output to the log file
	teeProc = subprocess.Popen(['tee', logFile], stdin = subprocess.PIPE)
	# Cause tee's stdin to get a copy of our stdin/stdout
	# (as well as that of any child processes we spawn)
	os.dup2(teeProc.stdin.fileno(), sys.stdout.fileno())
	os.dup2(teeProc.stdin.fileno(), sys.stderr.fileno())

	print('Starting autorip...')

	# Run the MakeMKV setup script
	# This stays a shell script so it can also run in the Dockerfile
	makemkvProc = subprocess.Popen(['/bin/sh', '/opt/autorip/setupmakemkv.sh'])
	makemkvResult = makemkvProc.wait()
	if makemkvResult != 0:
		print('Failed setting up MakeMKV')
		sys.exit(returnCode)
		return returnCode

	# Start the process to read udev events
	udevadmProc = subprocess.Popen(['udevadm', 'monitor', '--kernel', '--env', '-s', 'block', '-p'], stdout = subprocess.PIPE)

	# Start the thread to parse udev events
	udevParseThread = threading.Thread(target=udevParse, args=(udevadmProc.stdout, rootDir))
	udevParseThread.daemon = True
	udevParseThread.start()

	# Wait for the event to be signaled
	stop.wait()
	print('Stopping autorip...')

	# Kill the udev monitor process
	udevadmProc.kill()

def handler(signum, frame):
	# Handle the kill signal
	if signum == signal.SIGINT:
		print('Ctrl+C recieved.')
		stop.set()

# If this script is the entrypoint run the main logic
if __name__ == '__main__':
	# Set the signal handler
	signal.signal(signal.SIGINT, handler)

	# Start the main logic
	main()
