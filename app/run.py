#!/usr/bin/env python3

import subprocess, os, sys, threading, signal, shutil, re
from datetime import datetime

import DiskInfo
import TitleInfo
import FilePaths

# General constants
MAKEMKV_MINLENGTH = '--minlength=900' # 15 minutes
COLLECTION_MINLENGTH = 6000 # 100 minutes

# Environment variable names
OUTPUT_VID_DIR = 'OUTPUT_VID_DIR'
OUTPUT_VID_EXT = 'OUTPUT_VID_EXT'
HANDBRAKE_ARGS = 'HANDBRAKE_ARGS'
DEVICE_FILTER = 'DEVICE_FILTER'

# The stop event to kill the main thread
stop = threading.Event()

def filterStream(input, output, filterPattern, invert=False):

	line = []
	previousWasCarriageReturn = False
	bytes = input.read(1)
	while len(bytes) > 0:
		if bytes[0] == b'\n' and previousWasCarriageReturn:
			bytes = input.read(1)
			continue

		if bytes[0] == b'\r':
			previousWasCarriageReturn = True

		if bytes[0] == b'\r' or bytes[0] == b'\n':
			text = line.decode()

			print(f'PARSED OUTPUT LINE: {text}')

			# Filters the input stream using the filterPattern and write the reults to output
			match = re.match(filterPattern, text)
			if (not invert and match) or (invert and not match):
				print(text, file=output)

			line = []
			bytes = input.read(1)
			continue

		previousWasCarriageReturn = False
		line.append(bytes[0])
		bytes = input.read(1)

def getInfo(drivePath):
	cinfoReg = r'^CINFO:(\d+),(\d+),"?(.+?)"?$'
	tinfoReg = r'^TINFO:(\d+),(\d+),(\d+),"?(.+?)"?$'

	# Get the disk info using MakeMKV
	makemkvDrive = f'dev:{drivePath}'
	print(f'>>> Getting disk info (using MakeMKV) from {makemkvDrive}...')
	makemkvProc = subprocess.Popen(['makemkvcon', '--robot', MAKEMKV_MINLENGTH, 'info', makemkvDrive], stdout=subprocess.PIPE)
	makemkvResult = makemkvProc.wait()
	if makemkvResult != 0:
		print(f'ERROR MakeMKV failed, code: {makemkvResult}.')
		return None, None

	diskInfo = DiskInfo.DiskInfo()
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
					if diskInfo.label is None:
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
				trackInfoById[trackNum] = TitleInfo.TitleInfo()
				trackInfoById[trackNum].mkmkvId = trackNum
			trackInfo = trackInfoById[trackNum]

			match attributeId:
				case 2:
					# Track name/label
					trackInfo.label = attributeValue
				case 9:
					# Duration
					trackInfo.parseDuration(attributeValue)
				case 24:
					# Track id
					trackInfo.id = int(attributeValue)
				case 27:
					# Video file name
					trackInfo.filename = attributeValue
				case 49:
					# Comment (useable as a backup to the track label)
					if trackInfo.label is None:
						trackInfo.label = attributeValue

	# Last resort if there is no disk label, use lsblk
	if diskInfo.label is None:
		lsblkProc = subprocess.Popen(['lsblk', '-n', '-o', 'LABEL', drivePath], stdout=subprocess.PIPE)
		lsblkResult = lsblkProc.wait()
		if lsblkResult != 0:
			print(f'ERROR blkid failed, code: {lsblkResult}.')
			return None, None
		for line in lsblkProc.stdout:
			line = line.decode().strip()
			if line != '':
				driveInfo.label = line
				break

	# Return the results
	trackInfo = list(trackInfoById.values())
	if len(trackInfo) > 1:
		trackInfo.sort(key = lambda x: x.id)
	print(f'Got disk info: {diskInfo} and track info: {trackInfo}')
	return diskInfo, trackInfo

def rip(drivePath, workDir):
	# Rip the disk in this drive

	# TODO: Make this function cancel subprocesses and cleanup if the stop event is set

	# Step 0: Ensure the rip and transcode directories exist and are clean
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

	# Step 1: Get the disk metadata
	(diskInfo, trackInfo) = getInfo(drivePath)
	if diskInfo is None or trackInfo is None or len(trackInfo) < 1:
		print('ERROR: Failed to get any track information.')
		return

	# Sort tracks by length descending
	trackInfo.sort(key=lambda x: x.duration, reverse=True)

	# Determine if there are multiple titles
	OFFSET = 0.01
	totalLength = trackInfo[0].duration
	if len(trackInfo) > 2:
		print(f'>>>- Multiple titles detected.')
		totalLength = sum(map(lambda x: x.duration, trackInfo[1:]))
		min = totalLength - (totalLength * OFFSET)
		max = totalLength + (totalLength * OFFSET)
		if trackInfo[0].duration >= min and trackInfo[0].duration <= max:
			# The longest track is actually just all the "real" tracks combined
			print(f'>>>-- Combined track detected (track {trackInfo[0].id}), skipping.')
			trackInfo = trackInfo[1:]
		# Sort by title id to ensure earlier tracks remain earlier (undo the sort by length)
		trackInfo.sort(key=lambda x: x.id)
	else:
		# There may be multiple titles in a single-title disk (like extras)
		trackInfo = trackInfo[:1]
		print('>>>- Single title detected.')

	# Get the extension and output directory
	outputExt = os.environ[OUTPUT_VID_EXT]
	outputDir = os.environ[OUTPUT_VID_DIR]
	outputDir = os.path.join(outputDir, diskInfo.name)
	if len(trackInfo) > 1 and diskInfo.season is not None:
		outputDir = os.path.join(outputDir, f'Season {diskInfo.season:02d}')
	handbrakeArgs = os.environ[HANDBRAKE_ARGS].split()

	# Generate all the paths for every track
	paths = []
	for i in range(len(trackInfo)):
		paths.append(FilePaths.FilePaths())
		paths[i].buildPaths(ripDir, transcodeDir, outputDir, outputExt, diskInfo, trackInfo, i, totalLength >= COLLECTION_MINLENGTH)
	print(f'>>> Built paths:\n{"\n".join(map(lambda x: str(x), paths))}')

	# Step 2: Run MakeMKV
	makemkvDrive = f'dev:{drivePath}'
	for path in paths:
		track = trackInfo[path.trackIndex]
		print(f'>>> Ripping {diskInfo.name} track {track.mkmkvId} ({track.label}) from {makemkvDrive} into {path.ripDir} using MakeMKV...')
		makemkvProc = subprocess.Popen(['makemkvcon', '--decrypt', 'mkv', makemkvDrive, str(track.mkmkvId), path.ripDir])
		makemkvResult = makemkvProc.wait()
		if makemkvResult != 0:
			print(f'ERROR: MakeMKV failed, code: {makemkvResult}.')
			return

	# Step 3: Transcode each file in the track list
	for path in paths:
		# Run Handbrake
		print(f'>>> Transcoding {path.ripFile} to {path.transcodeFile} using HandBrake...')
		handbrakeCmd = ['HandBrakeCLI', '-i', path.ripFile, '-o', path.transcodeFile]
		handbrakeCmd.extend(handbrakeArgs)
		handbrakeProc = subprocess.Popen(handbrakeCmd, stdout=subprocess.PIPE)

		# Start the handbrake output filter thread
		filterThread = threading.Thread(target=filterStream, args=(handbrakeProc.stdout, sys.stdout, r'Encoding: task.+\d{2}\.[1-9]\d.+ETA', True))
		filterThread.daemon = True
		filterThread.start()

		# Start the handbrake process
		handbrakeResult = handbrakeProc.wait()

		# Check the handbrake process result
		if handbrakeResult != 0:
			print(f'ERROR: HandBrake failed, code: {handbrakeResult}.')
			return

	# Step 4: Move every transcoded track to the output
	for path in paths:
		print(f'>>> Moving output from {path.transcodeFile} to {path.outputFile}...')
		os.makedirs(path.outputDir, exist_ok=True)
		shutil.move(path.transcodeFile, path.outputFile)

	# Step 5: Eject
	print(f'>>> Ejecting drive {drivePath}...')
	ejectProc = subprocess.Popen(['eject', drivePath])
	ejectResult = ejectProc.wait()
	if ejectResult != 0:
		print(f'WARNING: Unable to eject drive {drivePath}, code: {ejectResult}.')

	# Cleanup
	print(f'>>> Cleaning up work directories ({ripDir}, {transcodeDir})...')
	shutil.rmtree(ripDir)
	shutil.rmtree(transcodeDir)
	return

ripThreads = {}
ripLock = threading.Semaphore()
def ripLocked(drivePath, rootDir):
	# Get the rip thread lock
	ripLock.acquire()
	try:
		# Check the drive to see if it is in use
		if drivePath in ripThreads and ripThreads[drivePath] is not None and ripThreads[drivePath].is_alive():
			# Device is busy
			print(f'Device is already in use: {drivePath}. Skipping event.')
			return 0

		# Save this thread as the active one for this device
		ripThreads[drivePath] = threading.current_thread()
	finally:
		ripLock.release()

	# Start the rip operation
	return rip(drivePath, rootDir)

def udevParse(udevStream, rootDir):
	# Event constants
	DEVNAME = 'DEVNAME'
	DISK_EJECT_REQUEST = 'DISK_EJECT_REQUEST'
	DISK_MEDIA_CHANGE = 'DISK_MEDIA_CHANGE'

	deviceFilter = os.environ[DEVICE_FILTER]

	evtData = {}

	print('Reading udev events...')

	# Read the udev events and make them into groups
	for line in udevStream:
		line = line.decode().strip()
		if line == '':
			print(f'Handling udev event: {evtData}')

			# Ignore eject request events
			if DISK_EJECT_REQUEST in evtData.keys():
				# This is an eject request
				print(f'Ignoring eject request event.')
				evtData = {}
				continue

			# Ignore events that are not media changes
			if DISK_MEDIA_CHANGE not in evtData.keys() or evtData[DISK_MEDIA_CHANGE] != '1':
				# This is not a media change event
				print(f'Ignoring non-media-change event.')
				evtData = {}
				continue

			# Be sure this event has a drive associated
			if DEVNAME not in evtData.keys():
				# The device is missing from the event
				print(f'WARNING: The {DEVNAME} key is missing from the udev event. Skipping event.')
				evtData = {}
				continue

			# Get the drive path and number
			drivePath = evtData[DEVNAME]

			# Ignore devices that don't match the filter
			if re.match(deviceFilter, drivePath) is None:
				# This device does not match the filter
				print(f'Device {drivePath} does not match filter {deviceFilter}, ignoring.')
				evtData = {}
				continue

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
	teeProc = subprocess.Popen(['tee', logFile], stdin=subprocess.PIPE)
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
	udevadmProc = subprocess.Popen(['udevadm', 'monitor', '--kernel', '--env', '-s', 'block', '-p'], stdout=subprocess.PIPE)

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
