# -*- coding: utf-8 -*-
# Your code goes below this line

import csv
import ast
import config
import urllib2
import urllib
import json
import xml.etree.ElementTree as ET
import glob
import os
import hashlib
import zlib
import sys
import wget
import subprocess
import logging
import random
from zipfile import ZipFile
from unidecode import unidecode
import unicodedata
from xml.dom import minidom
from multiprocessing import Pool
import mysql.connector
from PIL import Image
from threading import Thread
from datetime import datetime, time
from time import sleep
from pymediainfo import MediaInfo
import argparse
import re

### Parse arguments first

parser = argparse.ArgumentParser(description='ROM scraper, get information of your roms from screenscraper.fr')
parser.add_argument('--missing', help='Try to find missing ganes from the missing file',nargs=1)
parser.add_argument('--update', help='Update local DB information from screenscraper',const='True',nargs='?')
parser.add_argument('--clean', help='Clean a system from the DB, deletes all records from files',nargs=1)
args = vars(parser.parse_args())

try:
    missing = args['missing'][0]
except:
    missing = ''
try:
    update = args['update']
    if update == None : update = False
except:
    update = False

try:
    cleanSystem = args['clean'][0]
except:
    cleanSystem = ''

UPDATEDATA = update

try:
    logging.basicConfig(filename='sv2log.txt', filemode='a',
                        format='%(asctime)s - %(process)d - %(name)s - %(levelname)s - %(message)s',
                        level=logging.DEBUG)
    logging.debug("Logging service started")
except Exception as e:
    logging.debug('error al crear log '+str(e))

sysconfig = "/etc/emulationstation/es_systems.cfg"
# sysconfig ="systems.cfg"
tmpdir = '/home/pi/'
mydb = mysql.connector.connect(
  host="192.168.8.101",
  user="romhash",
  passwd="emulation",
  database="romhashes"
)

fixedURL = "https://www.screenscraper.fr/api"
testAPI = "ssuserInfos"
fixParams = {'devid': config.devid,
             'devpassword': config.devpassword,
             'softname': config.softname,
             'ssid': 'EMPTY',
             'sspassword': config.sspass,
             'output': 'json'}
cachedir = '/home/pi/hashes/'
CURRSSID = 0
lastfile = ''
lastresult = ''
### INSERT THE EXTENSIONS YOU DO NOT WANT TO HAVE ZIPPED IN THE LIST BELOW
donotcompress = ['.zip','.lha','.iso','.cue','.bin','.chd','.pbp','.rp','.sh','.mgw']
### OUTPUT FILE WITH THE MISSING FILES CREATED IN THE FIRST ROUND
missingfile='/home/pi/missing.csv'
### OUTPUT FILE WITH THE MISSING FILES CREATED IN THE SECOND ROUNF (WHEN --missing PARAMETER IS PASSED)
newmissingfile='/home/pi/newmissing.csv'

BIOSDIR = '/home/pi/RetroPie/BIOS/MAME'
UNKDIR = '/home/pi/RetroPie/UNKNOWN'

class Game:
    ### THIS IS THE GAME CLASS, IT WILL HOLD INFORMATION OF EACH SCRAPED GAME
    def __init__(self, json):
        if 'localpath' not in json.keys():
            return None
        file = json['localpath']
        ### CAN WE COMPRESS FILE?? THIS IS DONE IN ORDER TO SAVE SPACE
        if file[file.rfind('.'):].lower() not in donotcompress:
            ### YES WE CAN ZIP FILE
            zippedFile = convertToZip(file)
        else:
            ### THIS EXTENSION HAS BEEN REQUESTED NOT TO BE ZIPPED
            logging.debug ('###### REQUESTED NOT TO ZIP EXTENSION')
            zippedFile = file
        self.path = zippedFile
        self.name = json['jeu']['nom']
        self.desc = getDesc(json)
        self.image = getMedia(json['jeu']['medias'],
                              json['abspath'],
                              json['localpath'],
                              json['localhash'],
                              zippedFile)
        self.video = getVideo(json['jeu']['medias'],
                              json['abspath'],
                              json['localpath'],
                              json['localhash'])
        self.thumbnail = ''
        self.rating = getRating(json)
        self.releasedate = getDate(json)
        self.developer = ''
        try:
            if 'editeur' in json['jeu'].keys:
                self.publisher = json['jeu']['editeur']
            else:
                self.publisher =''
        except:
            self.publisher =''
        self.genre = ''
        self.players = ''
        self.playcount = ''
        self.lastplayed = ''
        self.hash = json['localhash']
        isMissing(json,self.path)
    def getXML(self):
        if self is not None:
            gameNode = ET.Element('game')
            attrs = vars(self)
            for attr in attrs:
                subEl = ET.SubElement(gameNode, attr)
                try:
                    subEl.text = attrs[attr].decode('utf-8').encode('ascii', 'xmlcharrefreplace')
                except Exception as e:
                    subEl.text = attrs[attr].encode('ascii', 'xmlcharrefreplace')
                    logging.error("error "+str(e)+" in path")
            return gameNode
        else:
            return None

def isMissing(json,file):
    ### THIS FUNCTION WILL CHECK IF WE CAN CONSIDER FILE AS MISSING FROM THE SCRAPER SITE
    logging.debug ('###### checking if '+file+' is missing')
    try:
        ## DO WE HAVE A GAME ID IN THE ANSWER?
        if 'id' not in json['jeu'].keys():
            ### NO WE DON'T, SO IT IS MISSING
            logging.debug ('###### ID is NOT in KEYS')
            ### IS THE SYSTEM ID IN THE ANSWER
            if 'systemeid' in json.keys():
                ### YES IT IS, ADD IT TO MISSING FILE
                writeMissing(json['systemeid'],file)
            else:
                ### NO, SO WRITE SYSTEM AS UNKNOWN
                writeMissing('UNKNOWN',file)
    except Exception as e:
        logging.error('###### GOT AN EXCEPTION '+str(e))
        ### THERE WAS AN EXCEPTION, SO YEAH, LOG IT
        writeMissing('EXCEPTED',file)

def cleanMedia (directory,extension):
    ### THIS FUNCTION WILL GO INTO A DIRECTORY AND MATCH FILES WITH THE PASSED EXTENSION
    if os.path.exists(directory):
        os.chdir(directory)
        ### LOOKUP ALL FILES WITH EXTENSION
        files = glob.glob(extension)
        ### TREAT EACH FILE
        for file in files:
            ### DISCARD SYMBOLIC LINKS
            if not os.path.islink(file):
                ### IT IS A REGULAR FILE
                ### GET ALL FILES AGAIN
                cfiles = glob.glob(extension)
                ### ITERATE THROUGH FILES
                for cfile in cfiles:
                    ### IS IT A SYMLINK?
                    if not os.path.islink(cfile):
                        ### NO IT IS NOT, IS IT THE SAME FILE?
                        if cfile != file:
                            ### NO IT IS NOT, SO DOES IT HAVE THE SAME SIZE?
                            if os.stat(cfile).st_size == os.stat(file).st_size:
                                ### YES IT DOES, BUT DOES IT HAVE THE SAME SHA?
                                if not os.path.islink(cfile) and (sha1(file) == sha1(cfile)):
                                    ### YES, THEY ARE THE SAME FILES WITH DIFFERENT NAMES
                                    logging.debug ('###### Found match '+cfile+' with '+file)
                                    try:
                                        ### DELETE DUPLICATE
                                        subprocess.call (['rm',cfile])
                                        ### AND CREATE SYMLINK TO SAME FILE
                                        subprocess.call (['ln','-s',file,cfile])
                                    except Exception as e:
                                        ### SOMETHING HAPPENED, LOG IT
                                        logging.error ('###### COULD NOT CLEANUP '+str(e))



def writeMissing(sysid,file):
    ### THIS FUNCTION WRITES TO THE MISSING LIST
    logging.debug ('###### ADDING FILE TO MISSING FILE')
    try:
        f=open(missingfile, "a+")
        f.write(str(sysid)+','+str(file)+','+str(sha1(file))+','+str(md5(file))+','+str(crc(file))+','+str(os.stat(file).st_size/1024)+'\n')
        f.close()
    except Exception as e:
        logging.error ('###### COULD NOT WRITE TO MISSING FILE '+str(e))
    return

def writeNewMissing(line):
    ### WRITE TO THE SECOND ROUND OUTPUT FILE
    logging.debug ('###### ADDING FILE TO MISSING FILE')
    try:
        f=open(newmissingfile, "a+")
        f.write(line+'\n')
        f.close()
    except Exception as e:
        logging.error ('###### COULD NOT WRITE TO NEW MISSING FILE '+str(e))
    return

def getRating(json):
    ### GETS THE RATING OF A GAME
    if 'jeu' in json.keys():
        jeu = json['jeu']
        if 'note' in jeu.keys():
            return str(jeu['note'])
        else:
            return '0'
    else:
        return '0'

def getDeveloper(json):
    ### GET DEVELOPER OF A GAME
    if 'jeu' in json.keys():
        jeu = json['jeu']
        if 'developpeur' in jeu.keys():
            return jeu['developpeur']
        else:
            return ''
    else:
        return ''

def getPublisher(json):
    ### GET A PUBLISHER OF A GAME
    if 'jeu' in json.keys():
        jeu = json['jeu']
        if 'editeur' in jeu.keys():
            return jeu['editeur']
        else:
            return ''
    else:
        return ''


def getGenre(json):
    ### GET GENRE OF A GAME
    if 'jeu' in json.keys():
        jeu = json['jeu']
        if 'genres' in jeu.keys():
            genreslan = jeu['genres']
            if 'genres_en' in genreslan.keys():
                genres = ''
                for genre in genreslan['genres_en']:
                    genres = genres + genre + ' '
                return genres
            else:
                return ''
        else:
            return ''
    else:
        return ''


def getPlayers(json):
    ### GET NUMBER OF PLAYERS OF A GAME
    # TODO:
    return ''

def generateImage(img1,img2,destfile):
    ### THIS FUNCTION COMBINES TWO IMAGES INTO A SINGLE ONE
    imgbase = Image.new('RGBA', (640, 530), (255, 0, 0, 0))
    imgb = Image.new('RGBA', (150, 150), (255, 0, 0, 0))
    if img1!='':
        try:
            imga = Image.open(img1).convert('RGBA')
            imga = imga.resize((640,480), Image.ANTIALIAS)
        except Exception as e:
            logging.error ('Cannot resize first image '+str(e))
            imga = Image.new('RGBA', (640, 480), (255, 0, 0, 0))
    else:
        imga = Image.new('RGBA', (640, 480), (255, 0, 0, 0))
    if img2!='':
        try:
            imgb = Image.open(img2).convert('RGBA')
            imgb = imgb.resize((200,300), Image.ANTIALIAS)
        except Exception as e:
            logging.error ('Cannot resize second image '+str(e))
            imgb = Image.new('RGBA', (110, 150), (255, 0, 0, 0))
    else:
        imgb = Image.new('RGBA', (150, 150), (255, 0, 0, 0))
    try:
        imgbase.paste(imga,(0,0),imga)
        imgbase.paste(imgb,(0,230),imgb)
        imgbase.save(destfile, format="png")
    except Exception as e:
        logging.error ('Cannot merge images '+str(e))
    if img1 !='':
        try:
            if os.path.isfile(img1):
                os.remove(img1)
        except:
            logging.error ('Cannot remove '+str(img1))
    if img2 !='':
        try:
            if os.path.isfile(img2):
                os.remove(img2)
        except:
            logging.error ('Cannot remove '+str(img2))

def getDesc(json):
    # THIS FUNCTION GETS THE SYNOPSIS OF A GAME, IT TRIES ENGLISH FIRST, THEN FRENCH, AND THEN WHATEVER IS AVAILABLE
    description = ''
    if isinstance(json, dict):
        if 'jeu' in json.keys():
            jeu = json['jeu']
            if isinstance(jeu, dict):
                if 'synopsis' in jeu.keys():
                    synopsis = jeu['synopsis']
                    if isinstance(synopsis, dict):
                        for key, value in synopsis.iteritems():
                            if key == 'synopsis_en':
                                description = value
                    else:
                        description = synopsis
    return description


def getDate(json):
    # THSI FUNCTION GETS THE RELEASE DATE OF A GAME
    reldate = ''
    if isinstance(json, dict):
        if 'jeu' in json.keys():
            jeu = json['jeu']
            if isinstance(jeu, dict):
                if 'dates' in jeu.keys():
                    dates = jeu['dates']
                    if isinstance(dates, dict):
                        for key, value in dates.iteritems():
                            if key == 'date_wor':
                                reldate = value
                    else:
                        reldate = dates

    return reldate


def writeXML(rootElement, filename):
    ### THIS FUNCTION WRITES AN XML FILE
     logging.debug ('###### XML WRITING')
     try:
         xmlstr = minidom.parseString(ET.tostring(rootElement.getroot())).toprettyxml(indent="   ")
         logging.debug('XML:' + xmlstr)
     except Exception as e:
         logging.error('cannot make pretty XML ' + str(e))
         return 1
     try:
         logging.debug('##### SAVING XML '+filename)
         with open(filename, "w") as f:
             f.write(xmlstr)
         f.close()
         logging.debug('##### SAVED XML '+filename)
     except Exception as e:
         logging.error('###### CANNOT WRITE XML ' + filename + ' ' + str(e))
         return 1
     return 0


def zipExtension(file):
    # Returns filename with extension replaced to zip
    fname = file[:file.rfind('.')]
    return fname+'.zip'


def convertToZip(file):
    logging.debug ('###### CONVERTING TO ZIP')
    # Creates zip file of file
    zippedFile = zipExtension(file)
    if os.path.isfile(file):
        logging.debug ('###### ZIPPING '+file+' INTO '+zippedFile)
        result = subprocess.call(['zip', zippedFile, file, '-9', '-D', '-q','-r'])
        logging.debug('###### ZIPPED FILE ' + zippedFile+' WITH RESULT '+str(result))
        if result == 0:
            try:
                if os.path.isfile(file):
                    os.remove(file)
            except Exception as e:
                logging.error('###### COULD NOT DELETE FILE AFTER ZIPPING ' + file + ' ' + str(e))
        else:
            logging.error ('###### COULD NOT ZIP FILE / RESULT '+str(result))
            return file
    return zippedFile

def waitNewDay(runTime):
    ### THIS FUNCTION WAITS FOR THE TIME PASSED AS PARAMETER TO CONTINUE SCRAPPING
    ### BUT IT WILL ALSO CHECK FROM TIME TO TIME IN CASE THE QUOTA IS RELEASED SOONER
    startTime = time(*(map(int, runTime.split(':'))))
    logging.info ('Starttime is '+str(startTime))
    allowed = False
    anon = False
    while (startTime > datetime.today().time()) and not allowed: # you can add here any additional variable to break loop if necessary
        sleep(60)
        logging.info ('###### WAITING FOR NEXT DAY')
        API = "jeuInfos"
        params = None
        params =fixParams
        params['gameid'] = 1
        response = callApi(fixedURL,API,params,0,anon)
        anon = not anon
        if 'ssuser'  in response:
            allowed = True
    logging.info ('###### FINISHED WAITING')
    return

def callAPI(URL, API, PARAMS, CURRSSID,Anon=False,Version=''):
    ### FNCTION THAT ACTUALLY DOES THE CALL TO THE API
    retries = 10
    ### IS IT AN ANONYMOUS CALL
    if not Anon:
        ### NO IT IS NOT, ADD USER PARAMETERS
        PARAMS['ssid'] = config.ssid[CURRSSID]
    else:
        ### IT IS, USER PARAMETER IS EMPTY
        logging.debug ('##### CALLING API AS ANONYMOUS')
        PARAMS['ssid'] = ''
    ### BUILD QUERY
    url_values = urllib.urlencode(PARAMS)
    API = Version+'/'+API+".php"
    callURL = URL+API+"?"+url_values
    ### CREATE EMPTY VARIABLES
    while retries > 0:
        ### EMPTY RESPONSE JUST IN CASE
        response = None
        logging.debug ('###### CALLING API TRY '+str(11-retries))
        logging.debug ('##### ACTUAL CALL TO API '+API)
        data = {}
        retJson = None
        try:
            logging.debug ('###### CALLING URL '+callURL)
            response = urllib2.urlopen(callURL,timeout=20)
            response = response.read()
            if Anon:
                logging.debug('###### ANON RESPONSE '+str(response))
                logging.debug('###### CALLING '+str(callURL))
            if '{' in response:
                a = '{'+response.split('{', 1)[1]
                response = a.rsplit('}', 1)[0] + '}'
                retJson = json.loads(response)
            else:
                if 'Faite du tri dans vos fichiers roms et repassez demain' in response:
                    logging.critical('###### ALLOCATED ALLOWANCE EXCEEDED FOR TODAY')
                    #### RETURN WHEN THERE ALLOWANCE IS DONE
                    #### waitNewDay(runTime)
                    return 'QUOTA'
                    response = urllib2.urlopen(callURL,timeout=20)
                    response = response.read()
                    if '{' in response:
                        a = '{'+response.split('{', 1)[1]
                        response = a.rsplit('}', 1)[0] + '}'
                        retJson = json.loads(response)
                    else:
                        retJson = response
            if isinstance(retJson, (dict, list)):
                return retJson['response']
            else:
                data['Error'] = response
            return json.loads(json.dumps(data))
        except Exception as e:
            data['Error'] = str(e)
            data['Response'] =str(response)
            logging.error ('##### FAILED TO CALL API '+str(e))
            retries = retries - 1
    return json.loads(json.dumps(data))


def existsInGamelist(gamelist, game):
    # Checks if a game is already in gamelist or not
    pass


def updateGameInList(gamelist, game):
    # Update game in gamelist
    pass


def addGameToList(gamelist, game):
    # Adds game to gamelist
    pass

def compressVideo(destfile):
    ##result = subprocess.call(['ffmpeg','-i',destfile,'-vcodec','libx265','-crf','20','-codec:a','libmp3lame','test.mp4'])
    ## Delete old video and rename new file
    return 0

def grabVideo (URL,destfile,tout):
    try:
        result = 1
        retries = 0
        while (result !=0) and (retries <10):
            logging.debug ('###### ACTUALLY DOWNLOADING VIDEO ')
            result = subprocess.call(['wget','--retry-connrefused','--waitretry=1','--read-timeout=20','--timeout=15','--tries=5','-c','-q', URL, '-O', destfile])
            logging.debug ('###### VIDEO DOWNLOAD RESULT '+str(result))
            logging.debug ('###### FILE EXISTS '+str(os.path.isfile(destfile)))
            if not validateVideo(destfile):
                if os.path.isfile(destffile):
                    os.remove(destfile)
                logging.error ('###### DOWNLOAD IS TOO SMALL')
                if 'clone.' in URL:
                    URL = URL.replace ('clone.','www.')
                else:
                    URL = URL.replace ('www.','clone.')
                result = -1
            retries = retries + 1
        logging.debug ('###### RESULT OF DOWNLOAD '+str(result))
        if result == -1:
            logging.debug ('##### DOWNLOAD wget ' + URL + ' -o ' + destfile)
        if result == 0:
            return destfile
        else:
            try:
                if os.path.isfile(destfile):
                    os.remove(destfile)
            except:
                logging.error ("##### CANNOT REMOVE FAILED DOWNLOAD")
            return ''
        compressVideo (destfile)
    except Exception as e:
        logging.error ('###### ERROR DOWNLOADING VIDEO '+URL+' '+str(e))
        return ''


def validateImage(imagefile):
    try:
        im=Image.open(imagefile)
        return True
    except IOError:
        return False

def validateVideo(videofile):
    fileInfo = MediaInfo.parse(videofile)
    try:
        for track in fileInfo.tracks:
            if track.track_type == "Video":
                return True
        return False
    except Exception as e:
        logging.error ('##### COULD NOT VALIDATE VIDEO '+str(e))
        return False

def grabMedia(URL,destfile,tout):
    try:
        result = 1
        retries = 0
        while (result !=0) and (retries <10):
            result = subprocess.call(['wget','--retry-connrefused','--waitretry=1','--read-timeout=20','--timeout=15','-t','0','-c','-q', URL, '-O', destfile])
            if not validateImage(destfile):
                if os.path.isfile(destfile):
                    os.remove(destfile)
                if 'clone.' in URL:
                    URL = URL.replace ('clone.','www.')
                else:
                    URL = URL.replace ('www.','clone.')
                logging.error ('###### DOWNLOAD IS CORRUPTED')
                result = -1
            retries = retries + 1
        logging.debug ('###### RESULT OF DOWNLOAD '+str(result))
        if result == -1:
            logging.debug ('##### DOWNLOAD wget ' + URL + ' -o ' + destfile)
        if result == 0:
            return destfile
        else:
            try:
                if os.path.isfile(destfile):
                    os.remove(destfile)
            except:
                logging.error ("##### CANNOT REMOVE FAILED DOWNLOAD")
            return ''
    except Exception as e:
        logging.error ('###### ERROR GETTING MEDIA '+URL+' '+str(e))
        return ''

def getScreenshot(medialist,num):
    if 'media_screenshot' in medialist.keys():
        URL = medialist['media_screenshot']
        mediaURL = URL.replace('clone.', 'www.')
        #mediaURL = URL
        mediaPos = mediaURL.find('mediaformat=')+12
        mediaFormat = mediaURL[mediaPos:mediaPos+3]
        if mediaFormat == '':
            mediaFormat = 'png'
        return grabMedia(mediaURL,tmpdir+'image'+str(num)+'.'+mediaFormat,60)
    else:
         return ''


def getBoxURL (list):
    found = False
    URL =''
    for key,value in list.iteritems():
        if not ('crc' in key or 'sha1' in key or 'md5' in key):
            if '_eu' in key:
                URL = value
                found = True
            else:
                if not found:
                   URL = value
                   found = True
    return URL

def getBezelURL (list):
    found = False
    URL =''
    for key,value in list.iteritems():
        if not ('crc' in key or 'sha1' in key or 'md5' in key):
            if '_eu' in key:
                URL = value
                found = True
            else:
                if not found:
                   URL = value
                   found = True
    return URL


def getBezel(medialist,syspath,name):
    if 'media_bezels' in medialist.keys():
        mediabezels = medialist['media_bezels']
        logging.debug ('###### THERE ARE BEZELS FOR THIS FILE')
        URL =''
        if 'media_bezels16-9' in mediabezels.keys():
            URL = getBezelURL(mediabezels['media_bezels16-9'])
        if URL =='media_bezesl4-3' in mediabezels.keys():
            URL = getBezelURL(mediabezels['media_bezels4-3'])
        if URL != '':
            logging.debug ('###### THERE IS AN URL FOR BEZEL')
            mediaURL = URL.replace('clone.', 'www.')
            mediaPos = mediaURL.find('mediaformat=')+12
            mediaFormat = mediaURL[mediaPos:mediaPos+3]
            logging.debug ('###### DOWNLOADING BEZEL')
            destpath = syspath.replace('roms','overlays')
            destfile = destpath+'/bezel-'+str(name)+'.'+mediaFormat
            logging.debug ('###### DESTINATION IS '+destfile)
            grabMedia(mediaURL,destfile,60)
            return destfile
        else:
            return ''
    else:
        logging.debug ('##### THERE ARE NO BEZELS FOR THIS FILE')
        return ''

def getBoxArt(medialist,num):
    if 'media_boxs' in medialist.keys():
        mediaboxs = medialist['media_boxs']
        URL =''
        if 'media_boxs3d' in mediaboxs.keys():
            URL = getBoxURL(mediaboxs['media_boxs3d'])
        if URL =='' and 'media_boxs2d' in mediaboxs.keys():
            URL = getBoxURL(mediaboxs['media_boxs2d'])
        mediaURL = URL.replace('clone.', 'www.')
        #mediaURL = URL
        mediaPos = mediaURL.find('mediaformat=')+12
        mediaFormat = mediaURL[mediaPos:mediaPos+3]
        if mediaFormat == '':
            mediaFormat = 'png'
        logging.debug ('###### DOWNLADING BOX ART')
        return grabMedia(mediaURL,tmpdir+'image'+str(num)+'.'+mediaFormat,60)
    else:
        return ''

def doMediaDownload(medialist,destfile,path,hash):
    logging.debug ('###### DOWNLOADING MEDIA')
    if (not(os.path.isfile(destfile)) and ('images' in destfile)) or UPDATEDATA:
        img1 = getScreenshot(medialist,random.randint(0,10000))
        if (img1 <> ''):
            img2 = getBoxArt(medialist,random.randint(0,10000))
            generateImage(img1,img2,destfile)
        else:
            logging.debug ('##### COULD NOT DOWNLOAD SCREENSHOT SO CANCELLING')
            try:
                if os.path.isfile(img1):
                    os.remove(img1)
                if os.path.isfile(img2):
                    os.remove(img2)
            except:
                logging.debug ('###### COULD NOT REMOVE FAILED IMAGES')

def processBezels(medialist,destfile,path,hash,zipname):
    logging.debug ('###### PROCESS BEZEL FOR '+zipname)
    logging.debug ('###### DOWNLOADING BEZELS')
    thisbezel = getBezel(medialist,path,hash)
    bezeldir = path.replace('roms','overlays')
    if not os.path.exists(bezeldir):
        os.makedirs(bezeldir)
    cfgdir = path
    if thisbezel !='':
        zipname = zipname[zipname.rfind('/')+1:]
        bezelcfg = path+'/'+zipname+'.cfg'
        bzlfile,bzlext = os.path.splitext (zipname)
        romcfg = bzlfile+'.cfg'
        romcfgpath = bezeldir+'/'+romcfg
        #if not os.path.isfile(bezelcfg):
        f = open(bezelcfg, "w")
        f.write('input_overlay = "'+ bezeldir+'/'+romcfg+'"\n')
        f.close
        #if not os.path.isfile(romcfgpath):
        f = open(romcfgpath, "w")
        f.write('overlays = "1"\noverlay0_overlay = "'+thisbezel+'"\noverlay0_full_screen = "true"\noverlay0_descs = "0"\n')
        f.close

def doVideoDownload(medialist,destfile):
    if 'media_video' in medialist.keys():
        URL = medialist['media_video']
        mediaURL = URL.replace('clone.', 'www.')
        #mediaURL = URL
        return grabVideo(mediaURL,destfile,120)
    else:
         return ''

def getVideo(medialist, path, file, hash):
    logging.debug ('###### STARTED GRABBING VIDEO PROCESS')
    destfile = ''
    if medialist != '':
        logging.debug('##### GRABBING VIDEO FOR ' + file)
        destfile = path+'/videos/'+hash+'-video.mp4'
        if os.path.isfile(destfile):
            with open(destfile) as f:
                fileread = f.read()
                if (('Votre quota de scrape est' in fileread) or ('API closed for non-registered members' in fileread) or ('Faite du tri dans vos fichiers roms et repassez demain !' in fileread)) or (os.stat(destfile).st_size < 10000):
                    if os.path.isfile(destfile):
                        os.remove(destfile)
                    doVideoDownload(medialist,destfile)
        else:
            doVideoDownload(medialist,destfile)
    return destfile

def getMedia(medialist, path, file, hash,zipname):
    logging.debug ('###### STARTING MEDIA DOWNLOAD PROCESS')
    #logging.debug ('###### THIS IS THE MEDIALIST ' + str(medialist))
    destfile = ''
    if medialist != '':
        logging.debug('##### GRABBING FOR ' + file)
        destfile = path+'/images/'+hash+'-image.png'
        if os.path.isfile(destfile):
            with open(destfile) as f:
                fileread = f.read()
                if ('API closed for non-registered members' in fileread or 'Faite du tri dans vos fichiers roms et repassez demain !' in fileread) or (os.stat(destfile).st_size < 3000):
                    if os.path.isfile(destfile):
                        os.remove(destfile)
        logging.debug ('###### GOING TO DOWNLOAD MEDIA')
        doMediaDownload(medialist,destfile,path,hash)
        logging.debug ('###### GOING TO DOWNLOAD BEZELS')
        processBezels(medialist,destfile,path,hash,zipname)
    return destfile

def getAllSystems(CURRSSID):
    ### CALLS API TO GET A LIST OF ALL THE SYSTEMS IN THE SITE
    logging.debug ('###### GETTING ALL SYSTEMS LIST')
    ### THIS IS THE API NAME
    API = "systemesListe"
    response = callAPI(fixedURL, API, fixParams, CURRSSID)
    ### IF WE GET A RESPONSE THEN RETURN THE LIST
    if 'Error' not in response.keys():
        try:
            return response['systemes']
        except Exception as e:
            return str(e) + ' ' + str(response)
    else:
        ### WE COULD NOT GET THE LIST OF SYSTEMS SO RETURN EMPTY
        return ''


def lookupHashInDB(file,hashType):
    logging.debug ('###### CONNECTING TO DB TO LOCATE HASH '+hashType+' FOR '+file)
    connected = False
    while not connected:
        logging.debug ('###### TRYING TO CONNECT')
        try:
            mycursor = mydb.cursor()
            connected = True
            logging.debug ('###### CONNECTED SUCCESFULLY')
        except Exception as e:
            logging.error ('###### CANNOT CONNECT TO DB - '+str(e))
            logging.error ('###### WAITING AND RETRYING')
            sleep(60)
    sql = "SELECT "+hashType.upper()+" FROM filehashes WHERE file = %s"
    val = (file, )
    connected = False
    logging.debug ('###### TRYING TO QUERY DB FOR '+hashType)
    try:
        mycursor.execute(sql, val)
        if mycursor.rowcount == 0:
            logging.debug ('###### NO '+hashType+' FOUND IN THE DB')
            return ''
        else:
            result = mycursor.fetchall()
            result = result[0][0]
            logging.debug ('###### FOUND '+hashType+' MATCH IN DB')
            return result
    except Exception as e:
        logging.error ('###### CANNOT QUERY THE DB DUE TO ERROR - '+str(e))
        return ''
    return ''

def updateHashInDB(file,hashType,hash):
    logging.debug ('###### UPDATING '+hashType+' '+hash+' FOR FILE '+file)
    mycursor = mydb.cursor()
    sql = "UPDATE filehashes SET "+hashType.upper()+"= %s WHERE file = %s"
    val =[(str(hash),str(file))]
    try:
        mycursor.executemany(sql, val)
        mydb.commit()
    except Exception as e:
        logging.error ('###### COULD NOT UPDATE DATA IN DB ' +str(e))
        logging.debug('###### UPDATED LOCAL CACHE')
    return

def insertHashInDB(file,hashType,hash):
    logging.debug ('###### INSERTING '+hashType+' '+hash+' FOR FILE '+file)
    mycursor = mydb.cursor()
    sql = "INSERT INTO filehashes (file, "+hashType.upper()+") VALUES (%s, %s)"
    val =[(str(file),str(hash))]
    try:
        mycursor.executemany(sql, val)
        mydb.commit()
    except Exception as e:
        logging.error ('###### COULD NOT INSTERT DATA IN DB ' +str(e))
        logging.debug('###### UPDATED LOCAL CACHE')
        updateHashInDB(file,hashType,hash)
    return


def md5(fname):
    dbval = lookupHashInDB(fname,'MD5')
    if dbval !='' and dbval != None:
        return dbval
    logging.debug ('###### NOT IN DB SO CALCULATING MD5 OF FILE '+fname)
    try:
        hash_md5 = hashlib.md5()
        with open(fname, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        retval = hash_md5.hexdigest()
        insertHashInDB(fname,'MD5',retval)
        return retval
    except Exception as e:
        logging.error('###### COULD NOT CALCULATE MD5 ' + str(e))
        return ''

def sha1(fname):
    dbval = lookupHashInDB(fname,'SHA1')
    if dbval !='' and dbval != None:
        return dbval
    logging.debug ('###### NOT IN DB SO CALCULATING SHA1 OF FILE '+fname)
    try:
        BLOCKSIZE = 65536
        hasher = hashlib.sha1()
        with open(fname, 'rb') as afile:
            buf = afile.read(BLOCKSIZE)
            while len(buf) > 0:
                hasher.update(buf)
                buf = afile.read(BLOCKSIZE)
        retval = hasher.hexdigest()
        insertHashInDB(fname,'SHA1',retval)
        return retval
    except Exception as e:
        logging.error('###### COULD NOT CALCULATE SHA1 ' + str(e))
        return ''

def crc(fileName):
    dbval = lookupHashInDB(fileName,'CRC')
    if dbval !='' and dbval != None:
        return dbval
    logging.debug ('###### NOT IN DB SO CALCULATING CRC OF FILE '+fileName)
    try:
        prev = 0
        for eachLine in open(fileName, "rb"):
            prev = zlib.crc32(eachLine, prev)
        retval = "%X" % (prev & 0xFFFFFFFF)
        insertHashInDB(fileName,'CRC',retval)
        return retval
    except Exception as e:
        logging.error('COULD NOT CALCULATE CRC ' + str(e))
        return ''

def escapeFileName(file):
    logging.debug ('###### ESCAPING FILENAME '+file)
    escapedfile = unicode(file)
    if escapedfile[0] == "'":
        escapedfile = escapedfile[1:]
    if escapedfile[len(escapedfile)-1] == "'":
        escapedfile = escapedfile[:len(escapedfile)-1]
    if escapedfile[0] == "_":
        escapedfile = escapedfile[1:]
    if escapedfile[len(escapedfile)-1] == "_":
        escapedfile = escapedfile[:len(escapedfile)-1]
    escapedfile = escapedfile.replace(' ', '_')
    escapedfile = escapedfile.replace('^', '_')
    escapedfile = escapedfile.replace(',', '_')
    escapedfile = escapedfile.replace('\'', '_')
    escapedfile = escapedfile.replace('"', '_')
    escapedfile = escapedfile.replace('\\', '_')
    escapedfile = escapedfile.replace('*', '_')
    escapedfile = escapedfile.replace('?', '_')
    escapedfile = escapedfile.replace('$', '_')
    escapedfile = escapedfile.replace('+', '_')
    escapedfile = unidecode(escapedfile)
    logging.debug ('###### ENDED ESCAPING FILE '+escapedfile)
    return escapedfile


def getNamesInZip(zFile):
    logging.debug ('###### GETTING FILES INSIDE '+zFile)
    try:
        with ZipFile(zFile, 'r') as zip:
            try:
                file = zip.namelist()
            except Exception as e:
                logging.error('###### CANNOT GET ZIP CONTENTS '+str(e))
                return ''
    except Exception as e:
        logging.error('###### CANNOT OPEN ZIP FILE ' + str(zFile) + ' ' + str(e))
        return ''
    return file


def extractZipFile(zFile,xfile,path):
    logging.debug ('###### EXTRACTING '+xfile+' FROM '+zFile)
    file = zFile
    try:
        logging.debug ('###### DOING NAMING ESCAPING FOR ZIP PURPOSES')
        xfile = xfile.replace('[','\[')
        xfile = xfile.replace(']','\]')
        if xfile !='' and xfile != '/':
            logging.debug ('###### EXECUTING unzip '+path+'/'+zFile+' ['+xfile+']')
            result = subprocess.call(['unzip','-j', '-o', '-qq', file, xfile,'-d',path])
            logging.debug ('###### GOT '+str(result)+' AFTER UNZIPPING')
            if result !=0:
                logging.error ('###### ERROR '+str(result)+' WHEN UNZIPPING')
                return False
        else:
            logging.debug ('###### WE DO NOT WANT TO EXTRACT '+xfile)
            return False
    except Exception as e:
        logging.error('###### ERROR EXTRACTING ' + file + ' ' + str(e))
        return False
    logging.debug ('###### EXTRACTED FILE '+file)
    return True


def renameFile(path, file):
    logging.debug ('###### RENAMING FILE '+file)
    escapedfile = escapeFileName(file)
    if file != escapedfile:
        try:
            subprocess.call(['mv', path + '/' + file, path + '/' + escapedfile])
        except Exception as e:
            logging.error('###### ERROR ESCAPING FILE ' + file + ' TO ' + escapedfile + ' DUE TO ' + str(e))
            return ''
    return escapedfile


def process7Zip(path,zipfile,CURRSSID,sysid):
    logging.debug ('###### ENTERING 7ZIP PROCESS')
    # Check if file is in DB, and if it has a matching hash, if none of the above then continue normall process
    zfiles = getNamesInZip(zipfile)
    logging.debug('##### FILES IN ZIP = ' + str(zfiles))
    if zfiles == '':
        # error extracting file, go to next one
        logging.error('###### COULD NOT GET FILES INSIDE ZIP ' + str(file))
        return None
    else:
        for zfile in zfiles:
            result = extractZipFile(zipfile,zfile,path)
            logging.debug('##### RESULT OF EXTRACTION ' + str(result))
            logging.debug ('###### WILL START PROCESS OF ' + zfile + ' NOW')
            zfile = zfile[0 if zfile.rfind('/')<0 else zfile.rfind('/')+1:]
            try:
                if os.path.isfile(path + '/' + zfile):
                    os.remove(path + '/' + zfile)
            except Exception as e:
                logging.error ('###### COULD NOT REMVOE '+zfile+' '+str(e))
            gameinfo = processFile (path,zfile,CURRSSID,True,sysid)
            if gameinfo:
                if 'ssuser' in gameinfo and 'jeu' in gameinfo:
                    logging.info ('###### FOUND GAME INFO FOR '+zipfile)
                    return gameinfo
    logging.info ("###### DID NOT FIND GAME INFO FOR "+zipfile)
    return gameinfo

def processZip(path,zipfile,CURRSSID,extensions,sysid):
    logging.debug ('###### PROCESSING ZIPFILE '+zipfile)
    zipfile,gameinfo = processFile (path,zipfile,CURRSSID,True,sysid)
    if gameinfo:
        if 'ssuser' in gameinfo:
            logging.debug ('###### FOUND INFO FOR FILE '+zipfile)
            return zipfile,gameinfo
    logging.debug ('###### INFO FOR ZIPFILE '+zipfile +' NOT FOUND SO GOING INSIDE')
    zfiles = getNamesInZip(zipfile)
    logging.debug('##### RETURNED THESE FILES IN ZIP ' + str(zfiles))
    if zfiles == '':
        # error extracting file, go to next one
        logging.error('###### COULD NOT GET CONTENTS OF ZIP FILE ' + str(file))
        return zipfile,None
    else:
        for zfile in zfiles:
            proczfile = zfile
            logging.debug ('###### GETTING INFO FOR FILE '+proczfile+' INSIDE ZIP '+zipfile)
            exten = os.path.splitext(proczfile)[1]
            logging.debug ('###### EXTENSION IS '+exten)
            if  exten not in extensions:
               logging.debug ('###### EXTENSION IS NOT IN LIST OF ALLOWED EXTENSIONS, SKIPPING')
               continue
            result = extractZipFile(zipfile,proczfile,path)
            logging.debug('##### EXTRACTION RESULTED IN ' + str(result))
            logging.debug('##### TRYING TO GET INFO FOR ' + proczfile)
            proczfile = proczfile[0 if proczfile.rfind('/')<0 else proczfile.rfind('/')+1:]
            logging.debug ('##### FILE IS CONVERTED TO '+proczfile)
            proczfile,gameinfo = processFile (path,proczfile,CURRSSID,False,sysid)
            shazfile=sha1(path+'/'+proczfile)
            crczfile=crc(path+'/'+proczfile)
            md5zfile=md5(path+'/'+proczfile)
            try:
                if os.path.isfile(path + '/' + proczfile):
                    os.remove(path + '/' + proczfile)
            except Exception as e:
                logging.error ('###### COULD NOT DELETE '+proczfile+' '+str(e))
            if gameinfo:
                if ('ssuser' in gameinfo) and ('jeu' in gameinfo):
                    logging.debug ('###### FOUND GAME INFO FOR '+zipfile)
                    ### FOUND GAME INFO FOR FILE INSIDE
                    ### WE MIGHT AS WELL STORE SHAS FOR ZIP
                    updateHashInDB(path+'/'+zipfile,'SHA1',shazfile)
                    updateHashInDB(path+'/'+zipfile,'CRC',crczfile)
                    updateHashInDB(path+'/'+zipfile,'MD5',md5zfile)
                    return zipfile,gameinfo
    logging.info ("###### COULD NOT FIND GAME INFO FOR "+zipfile)
    return zipfile,gameinfo

def processDir(dir,path,CURRSSID,extensions,sysid):
    logging.info ('###### STARTING DIRECTORY PROCESS')
    logging.debug ('##### CHANGING DIRECTORY TO '+path+'/'+dir)
    os.chdir(path+'/'+dir)
    schextensions = '**[.zip'
    for exten in extensions:
        schextensions = schextensions+'|'+exten
    schextensions = schextensions +']'
    filelist = sorted(glob.glob(schextensions))
    logging.info ('###### FOUND '+str(len(filelist))+' FILES WITH EXTENSIONS '+schextensions)
    gameinfo = None
    for file in filelist:
        procfile = file
        if os.path.isfile(procfile):
            procfile,gameinfo = goForFile(procfile,path+'/'+dir,CURRSSID,extensions,sysid)
            if gameinfo:
                gameinfo['path']=dir
                os.chdir(path)
                return gameinfo
    os.chdir(path)
    return gameinfo

def goForFile(file,path,CURRSSID,extensions,sysid):
    ### WE'RE GOING TO PROCESS A FILE
    logging.info ('###### GO FOR FILE '+str(file))
    ### GET THE FILE EXTENSION
    exten = os.path.splitext(file)[1]
    logging.debug ('###### EXTENSIONS '+str(exten))
    ### INITIALIZE GAMEINFO SO WE MAKE SURE WE DO NOT CARRY SOME PREVIOUS VALUE
    gameinfo = None
    ### IS THE EXTENSION IN ALLOWED EXTENSIONS? (DOUBLE CHECKING)
    if  exten not in extensions:
        ### NO IT IS NOT, SO NOTIFY
        logging.info ('###### EXTENSION '+str(exten)+' IS NOT IN LIST OF ACCEPTED FILES')
        ### RETURN THE FILE AND EMPTY GAME INFORMATION
        return file,None
    ### WE START PROCESSING FILES ACCORDING TO EXTENSIONS
    if exten == '.7z' or exten == '.rar':
        ### 7Z AND RAR FILES ARE NOT YET PROCESSED
        logging.debug ('###### NOT PROCESSING RAR OR 7Z EXENSIONS')
        return file,None
    if exten == '.zip':
        ### IF EXTENSION IS ZIP, WE DO SOMETHING SPECIAL, WE DO NOT CHECK ONLY THE ZIP FILE, BUT ALSO ITS CONTENTS
        file,gameinfo = processZip(path,file,CURRSSID,extensions,sysid)
        ### CHECK IF WE HAD A GAME RETURNED
    else:
        ### SO THIS IS A FILE WITH AN ACCEPTED EXTENSION, PROCESS IT
        file,gameinfo = processFile (path,file,CURRSSID,True,sysid)
    ### DID WE GET SOME GAME INFO?
    if gameinfo :
        ### YES WE DID, ADD SOME OF OUR OWN VALUES
        ### ADD SYSTE ID AS DEFINED IN SCRAPER SITE
        gameinfo['systemeid'] = sysid
        ### ADD LOCAL PATH TO THE FILE
        gameinfo['localpath'] = path+'/'+file
        ### ADD ABSOLUTE PATH
        gameinfo['abspath'] = path
        ### AND FINALLY ADD SHA1 OF THE FILE
        gameinfo['localhash'] = sha1(path+'/'+file)
        logging.debug ('###### FOUND GAME INFO FOR '+file)
        ### LAST BUT NOT LEAST, RETURN INFORMATION
        return file,gameinfo
    else:
        ### SO WE DIDN'T GET ANYTHING, RETURN NONE THEN
        return file, None

def processFile (path,file,CURRSSID,doRename,sysid):
    ### SO WE ARE PROCESSING A GENERAL FILE
    logging.info ('###### PROCESSFILE '+file)
    ### DO WE NEED TO RENAME FILE? (THIS IS DONE TO AVOID STRANGE CHARACTERS IN FILENAMES)
    if doRename:
        ### YES, PLEQSE RENAME
        newfile = renameFile(path, file)
        if newfile == '':
            # SO WE HAD AN ERROR RENAMING THE FILE, SKIP IT
            logging.error('###### CANNOT PROCESS FILE ' + file)
            return file,None
        ### WE COULD RENAME IT, ASSING PROPER VALUE
        else:
            file = newfile
    ### CALCULATE DIFFERENT CHECKSUMS
    logging.debug ('###### CALCULATING HASHES FOR FILE '+file)
    ### MD5
    md5offile = md5(path+'/'+file)
    ### SHA1
    sha1offile = sha1(path+'/'+file)
    ### CRC
    crcoffile = crc(path+'/'+file)
    logging.debug ('##### GETTING GAME INFO '+str(path)+'/'+str(file)+' '+str(md5offile)+' '+str(sha1offile)+' '+str(crcoffile))
    ### TRY TO GET GAME INFORMATION
    file, gameinfo = getGameInfo(CURRSSID, path, file, md5offile, sha1offile, crcoffile,sysid)
    ### IF WE RECEIVE 'SKIP' THEN IT MEANS WE NEED TO SKIP THIS GAME FOR A REASON (USUALLY SCRAPE QUOTA IS OVER)
    if gameinfo == 'SKIP':
        logging.debug ('###### GOT INFO TO SKIP THIS GAME')
        ### BUT WAIT, I JUST WANT TO SKIP NON ZIP FILES
        ### THE REASONING IS THAT THE SCRAPPING SITE HAS A QUOTA FOR FAILED SCRAPES AND SUCCESFULL SCRAPES
        ### AND ZIP TEND TO FILE WHILE PROPER FILE INSIDE NOT, SO LET'S TRY WITH FILE INSIDE AND SEE IF WE GET AN OK
        if os.path.splitext(file)[1].upper() != '.ZIP':
            ### IT IS NOT A ZIP FILE, SO WE REALLY WENT OVER THE QUOTA AND WE BETTR WAIT
            logging.debug ('###### FILE IS NOT ZIP, SO NO NEED TO CONTINUE, WAITING')
            ### WAIT UNTIL NEXT TIME
            waitNewDay('23:00:00')
        else:
            ### AS SAID, IT IS A ZIP, SO LET'S RETURN NONE AND GO ON
            gameinfo = None
    ### RETURN WHATEVER WE HAVE FOUND
    return file, gameinfo

def grabData(system, path, CURRSSID, acceptedExtens):
    ### WE'RE ABOUT TO PROCESS A SYSTEM
    logging.debug ('###### GRAB DATA START')
    ### FIRST WE CHANGE DIRECTORY TO THE SYSTEM'S DIRECTORY
    try:
        os.chdir(path)
    except Exception as e:
        ### WE FAILED TO CHANGE DIRECTORY (SHOULDN'T HAPPEN BUT...)
        logging.error ('###### CANNOT CHANGE DIRECTORY TO '+path+ ' '+str(e))
        return 1
    newfile = True
    ### CREATE ROOT ELEMENT FOR GAMELIST
    tree = ET.ElementTree()
    ### CREATE GAMELIST ELEMENT
    gamelist = ET.Element('gameList')
    try:
        ### CREATE SEARCH EXPRESSION FOR FILES, BASED ON EXTENSIONS, AGAIN ZIP IS ADDED BY DEFAULT, IN TIS CASE TO FACILITATE ITERATION
        schextensions = '**[.zip'
        ### GO THROUGH ALL ACCEPTED EXTENSIONS AND ADD THEM TO THE SEARCH EXPRESSION
        for exten in acceptedExtens:
            schextensions = schextensions+'|'+exten
        ### CLOSE THE BRACKETS
        schextensions = schextensions +']'
        ### GET THE LIST OF FILES THAT COMPLY WITH THE ACCEPTED EXTENSIONS (PLUS ZIP, REMEMBER)
        filelist = sorted(glob.glob(schextensions))
        logging.info ('###### FOUND '+str(len(filelist))+' FILES WITH EXTENSIONS '+schextensions)
    except Exception as e:
        ### FOR SOME REASON SOMETHING WENT WRONG WHEN SEARCHING FOR FILES SO LET EVERYONE KNOW`
        logging.error('###### THERE ARE NO FILES IN DIRECTORY ' + path + str(e))
        ### AND CREATE AN EMPTY LIST SO EXECUTION CARRIES ON
        filelist = []
    ### ITERATE THROUGH EACH FILE
    for file in filelist:
        ### CREATE A PORCESS FILE VARIABLE SO WE KEEP THE INITIAL FILE VARIABLE QUIET
        procfile = file
        logging.info ('###### STARTING TO PROCESS FILE '+file)
        ### INITIALIZE GAMEINFO, WE DO NOT WANT SOMETHING STRANGE HAPPENING
        gameinfo = None
        ### INITIALIZE THSIGAME ALSO
        thisGame = None
        ### SINCE FILE SEARCH WILL RETURN FILES AND DIRECTORIES
        ### WE NEED TO CHECK WHAT WE ARE DEALING WITH
        if os.path.isfile(procfile):
            ### IT IS A FILE
            logging.debug ('###### '+procfile+' IS A FILE')
            ### PROCESS IT
            procfile,gameinfo = goForFile(procfile,path,CURRSSID,acceptedExtens,system)
        else:
            ### IT IS A DIRECTORY
            logging.debug ('###### '+procfile+' IS A DIRECTORY')
            ### PROCESS IT
            gameinfo = processDir(procfile,path,CURRSSID,acceptedExtens,system)
        ### DID WE GET GAME INFORMATION?
        if gameinfo is not None:
            try:
                ### YES, CREATE A GAME INSTANCE THEN
                thisGame = Game(gameinfo)
            except Exception as e:
                ### THERE WAS AN ERROR CREATING GAME INSTANCE, NOTIFY
                logging.error ('###### COULD NOT CREATE GAME INSTANCE '+str(e))
            ## SO, COULD WE CREATE A GAME INSTANCE?
            if thisGame is not None:
                ### YES WE DID, SO GET THE XML FOR THIS GAME
                myGameXML = thisGame.getXML()
                ### DID IT WORK?
                if myGameXML is not None:
                    ### YES, APPEND THE GAME TO THE GAMELIST
                    gamelist.append(thisGame.getXML())
                else:
                    ### NO, NOTIFY ERROR
                    logging.error('##### CANNOT GET XML FOR FILE '
                                  + procfile + ' WITH SHA1 ' + sha1offile)
            else:
                ### NO, SO JUST INFORM WE COULDN'T
                logging.info('##### COULD NOT SCRAPE ' + procfile + ' ')
        else:
             ### NO, INFORM WE HAD AN ISSUE
             logging.info('##### COULD NOT SCRAPE ' + procfile + ' ')
        ### GO TO NEXT USER ID
        CURRSSID = CURRSSID + 1
        if CURRSSID == len(config.ssid):
            CURRSSID = 0
        ### INFORM WE HAVE FINISHED PROCESSING FILE
        logging.info ('---------------------- END FILE ['+procfile+'] ------------------------------')
    ### WE HAVE PROCESSED ALL FILES, SO ADD GAMELIST TO THE ROOT ELEMENT OF THE XML
    tree._setroot(gamelist)
    ### SET THE DESTINATION XML FILE
    xmlFile = path + '/gamelist.xml'
    ### IF THE FILE IS EXISTING, REMOVE IT
    if os.path.isfile(xmlFile):
        logging.info ('###### REMOVING GAMELIST')
        os.remove(xmlFile)
    ### AND THEN CREATE IT
    result = tree.write(xmlFile)
    if result != None:
        ### INFORM WE COULD NOT CREATE XML
        logging.error ('##### ERROR WHEN CREATING XML '+str(result))
    ### IN ORDER TO SAVE DISK SPACE, WE ARE GOING TO CLEAN UP VIDEOS AND DIRECTORIES, CHECK PROCEDURES TO UNDERSTAND WHAT HAPPENS
    ### BUT BASICALLY WE CREATE LINKS WHEN FILES ARE THE SAME AND JUST KEEP ONE OF THEM
    logging.info ('###### CLEANING VIDEOS ')
    cleanMedia(path + '/videos/','*.mp4')
    logging.info ('###### CLEANING IMAGES')
    cleanMedia(path + '/images/','*.png')
    logging.info ('###### CLEANING BEZELS')
    destpath = path.replace('roms','overlays')
    cleanMedia (destpath,'*.png')
    logging.debug ('###### DONE')

def deleteFromDB(sha1):
    logging.debug ('###### DELETING RECORD FORM DB')
    connected = False
    while not connected:
        try:
            mycursor = mydb.cursor()
            connected = True
        except Exception as e:
            logging.error ('###### CANNOT CONNECT TO DB - '+str(e))
            logging.error ('###### WAITING AND RETRYING')
            sleep(60)
    sql = "DELETE FROM hashes WHERE hash = %s"
    val = (sha1, )
    try:
        mycursor.execute(sql, val)
        result = mycursor.fetchall()
        connected = True
    except Exception as e:
        logging.error ('###### RECORD DOES NOT EXIST - '+str(e))
        result = None

    if not result:
        logging.debug ('##### COULD NOT FIND SHA1 in DB')
        return ''
    return ''

def locateShainDB(sha1):
    result = ''
    logging.debug ('###### CONNECTING TO DB TO LOCATE DATA FOR '+sha1)
    connected = False
    while not connected:
        logging.debug ('###### TRYING TO CONNECT')
        try:
            mycursor = mydb.cursor()
            connected = True
            logging.debug ('###### CONNECTED SUCCESFULLY')
        except Exception as e:
            logging.error ('###### CANNOT CONNECT TO DB - '+str(e))
            logging.error ('###### WAITING AND RETRYING')
            sleep(60)
    sql = "SELECT response FROM hashes WHERE hash = %s"
    val = (sha1, )
    connected = False
    logging.debug ('###### TRYING TO QUERY DB')
    try:
        mycursor.execute(sql, val)
        if mycursor.rowcount == 0:
            logging.debug ('###### NO DATA FOUND IN THE DB')
            return ''
        else:
            result = mycursor.fetchall()
            result = result[0][0].decode()
            logging.debug ('###### FOUND MATCH IN DB')
    except Exception as e:
        logging.error ('###### CANNOT QUERY THE DB DUE TO ERROR - '+str(e))
        return ''
    try:
        #logging.debug ('##### WHAT I GET FROM DB IS '+str(result))
        logging.debug ('###### CONVERTING TO JSON')
        value = ast.literal_eval(result)
    except Exception as e:
        logging.error ('###### COULD NOT CONVERT DB RESULT '+str(result)+' TO JSON '+str(e))
        return ''
    if 'urlopen error' in str(value) or 'QUOTA' in str(value) or 'Faite du tri' in str(value):
        ## Delete from DB
        logging.debug ('###### DELETING RECORD FROM DB')
        deleteFromDB(sha1)
        return ''
    return value

def updateDB(sha1,response):
    if not 'urlopen error' in response:
        mycursor = mydb.cursor()
        sql = "REPLACE INTO hashes (hash, response) VALUES (%s, %s)"
        val =[(str(sha1),str(response))]
        try:
            result = mycursor.executemany(sql, val)
            mydb.commit()
            logging.info ('###### DB UPDATED OK ['+str(result)+']')
        except Exception as e:
            logging.error ('###### COULD NOT INSTERT DATA IN DB ' +str(e))
            logging.debug('###### UPDATED LOCAL CACHE')
        return
    else:
        return


def getGameInfo(CURRSSID, pathtofile, file, md5, sha1, crc, sysid):
    ### THIS IS WHERE EVERYTHING HAPPENS
    ### IS ANY OF THE PARAMETERS EMPTY?
    if md5 == '' or sha1 == '' or crc == '':
        # YES, GO BACK
        return file,None
    logging.info ('###### GETTING GAME INFORMATION')
    ### THIS IS THE NAME OF THE API WE HAVE TO CALL
    API = "jeuInfos"
    ### INITIALIZE PARAMETERS, STARTING BY THE FIXED ONES (SEE CONFIG)
    params = None
    params = fixParams
    ### ADD MD5
    params['md5'] = md5
    ### ADD SHA1
    params['sha1'] = sha1
    ### ADD CRC
    params['crc'] = crc
    ### INITIQLIZE VARIABLES TO AVOID ACRRY ON VALUES
    response = None
    ### FIRST, TRY TO GET THE ANSWER FRO THE DB, THIS IS DONE SO WE DO NOT CALL THE SCRAPER EVRYTIME IF WE HAVE ALREADY FETCHED INFORMATION FOR THIS PARTICULAR SHA
    response = locateShainDB(sha1)
    ### DID WE SOMEHOW GOT AN EMPTY RESPONSE?
    if response !='':
        ### WE DID GET A RESPONSE
        ### THIS VARIABLE INDICATES IF WE NEED TO UPDATE THE DB OR NOT, BY DEFAULT WE DO
        doupdate = True
        ### CHECK IF WE HAVE A SYSTEM ID IN THE RESPONSE
        if not 'systemeid' in response:
            ### WE DIDN'T GET A SYSTEM ID, ADD IT
            try:
                ### DO IT
                response['systemeid']=sysid
            except:
                ### SOMETHING DIDN'T WORK, ERROR IT
                logging.error('###### COULD NOT SYSID TO RESPONSE')
        ### DID WE GET A QUOTA LIMIT?
        if 'QUOTA' in response:
            ### YES, SO RETURN TO SKIP THE FILE IF POSSIBLE
            loggign.info ('###### QUOTA LIMIT DONE RETURNED BY API')
            return file,'SKIP'
        ### DID THE SCRAPER RETURN A VALID ROM?
        ### USUALLY IN A VALID RESPONSE WE WOULD HAVE THE SSUSER KEY
        ### AND OF COURSE THE ANSWER WILL NOT BE EMPTY
        if not ('ssuser' in response) and (response != ''):
            #YES WE DID
            logging.info ('###### GAME INFO WAS NOT PRESENT FOR ROM')
            ### ONE OF THE FEATURES OF THE SCRAPER IS TO ALLOW YOU TO ASSIGN GAME ID'S TO RECORDS IN DB, WHICH WOULD
            ### BE SCRAPPED IN A SECOND RUN, THIS ALLOWS FOR ROMS THAT ARE NOT IN THE SITE BUT YOU KNOW OF TO BE SCRAPPED
            ### SO, DO WE HAVE A GAME ID?
            if not 'GameID' in response:
                ### NO WE DON'T SO WE ADD IT AS 0 SO YOU CAN REPLACE IT AFTERWARDS IN THE DB
                response['GameID']='0'
                ### AND WE UPDATE THE DB WITH THE RESULT (REGARDLESS IF IT WAS IN THE DB OR NOT PREVIOUSLY)
                updateDB (sha1,response)
                ### INFORM LOG THAT YOU COULD EVENTUALLY UPDATE GAMEID
                logging.debug ('###### YOU CAN UPDATE GAME ID FOR '+file)
                ### AND RETURN RESPONSE
                return file,response
            else:
                ### YES WE GOT A GAME ID
                logging.debug ('###### GOT A GAME ID FROM DB '+str(response))
                ### SO NOW INITIALIZE GAME PARAMETERS FOR NEW SEARCH , FIRST EMPTY THEN ASSIGN, JUST IN CASE
                gameparams = None
                gameparams = fixParams
                ### OK, WE GOT A GAME ID, BUT IS IT 0?
                if response['GameID'] !='0':
                    ### NO IT IS NOT, SO WE CAN GO AHEAD AND GET IT
                    logging.debug ('###### CALLING API WITH GAME_ID'+response['GameID'])
                    ### ADD GAMEID TO PARAMETERS
                    gameparams['gameid'] = response['GameID']
                    ### AND GET THE RESPONSE TO THE CALL
                    newresponse = callAPI(fixedURL,API,gameparams,CURRSSID)
                    ### CHECK IF WE WENT OVER QUOTA
                    if newresponse == 'QUOTA':
                        logging.debug ('###### QUOTA DONE')
                        ### WE DID, CAN WE TRY CALLING ANONYMOUS?
                        newresponse = callAPI(fixedURL, API, gameparams, CURRSSID,True)
                        if newresponse == 'QUOTA':
                            ### NO WE CANNOT
                            return file, 'SKIP'
                    ### SO, DID WE GET A PROPER RESPONSE? (REMEMBER SSUSER NEEDS TO BE THERE)
                    if 'ssuser' in newresponse:
                        ### YES WE DID
                        logging.debug ('###### SSUSER IS IN RESPONSE')
                        ### ASSIGN NEW RESPONSE TO OLD ONE, SO WE DO NOT CONFUSE OURSELVES
                        response = newresponse
                        ### AND UPDATE THE DB WITH THE NEW ANSWER
                        updateDB (sha1,response)
                        ### AND SINCE WE GOT A PROPER ANSWER (AND NEW) WE DO NOT HAVE TO UPDATE THE CALL
                        doupdate = False
                    else:
                        ### NO IT WAS NOT A PROPER ANSWER
                        logging.debug ('###### SSUSER NOT IN RESPONSE')
                        ### RETURN WHATEVER WE GOT
                        return file,newresponse
        ### HERE WE CHECK IF IT HAS BEEN REQUESTED TO UPDATE DATA FROM SCRAPER OR NOT
        if UPDATEDATA and 'ssuser' in response and doupdate:
            ### UPDATE DATA IN DB BY FETCHING API AGAIN
            logging.debug ('###### TRYING TO UPDATE CACHE DATA')
            ### WE INITIALIZE THE FIXED PARAMETERS
            gameparams = None
            gameparams = fixParams
            ### AND WE ADD THE GAME ID, WHICH WE SHOULD HAVE. THIS IS TO AVOID TRYING TO UPDATE CHECKSUMS THAT ARE NOT EXISTING IN SITE
            gameparams['gameid'] = response['jeu']['id']
            ### AND WE CALL THE API
            newresponse = callAPI(fixedURL,API,gameparams,CURRSSID)
            ### ARE WE OVER THE ALLOWED QUOTA?
            if newresponse == 'QUOTA':
                ### YES
                logging.info ('###### QUOTA DONE, TRYING ANON')
                ### CAN WE TRY TO CALL IT ANONYMOUSLY?
                newresponse = callAPI(fixedURL, API, gameparams, CURRSSID,True)
                if newresponse == 'QUOTA':
                    ### NO WE CAN'T
                    logging.info ('###### QUOTA REALLY DONE, NOT UPDATING')
                    ### SO SKIP FILE
                    return file, 'SKIP'
            ### DID WE GET A VALID RESPONSE??? (REMMEBER SSUSER)
            if 'ssuser' in newresponse:
                ### YES WE DID
                response = newresponse
                logging.info ('###### GOT UPDATED VERSION FROM API')
                updateDB (sha1,response)
                return file,response
    else:
        ### WE COULD NOT LOCATE THE SHA IN DB
        logging.error('###### CACHE DOES NOT EXISTE IN DB FOR ' + file)
        ### CALL THE API TO GET AN ANSWER
        response = callAPI(fixedURL, API, params, CURRSSID)
        ### ARE WE OVER THE QUOTA?
        if response == 'QUOTA':
            ### WE ARE, CAN WE CALL ANONYMOUSLY?
            response = callAPI(fixedURL, API, params, CURRSSID,True)
            if response == 'QUOTA':
                ### NO WE CAN'T
                return file, 'SKIP'
        ### DID WE GET A PROPER ANSWER? (SSUSER)
        if ('ssuser' not in response) and ('gameid' not in response):
            ### NO WE DID NOT, ADD LOCAL PVALUES
            response['file'] = pathtofile + '/' + file
            response['localhash'] = sha1
            response['GameID'] = '0'
            updateDB (sha1,response)
        else:
            logging.debug ('###### GOT ANSWER FROM API, UPDATING DB')
            updateDB (sha1,response)
    ### SO NOW WE HAVE A RESPONSE, LET'S TREAT IT
    ### WE ASSUME THE ROM WAS NOT FOUND
    foundRom = False
    ### IS THERE AN ERROR IN RESPONSE?
    if 'Error' in response.keys():
        ### YES THERE IS
        logging.debug('###### API GAVE ERROR BACK, CREATING EMPTY DATA '+str(response))
        ### SO WE CREATE AN EMPTY ANSWER AND RETURN IT
        return file,{'abspath': pathtofile,
                'localpath': pathtofile+'/'+file,
                'localhash': sha1.upper(),
                'jeu':
                {
                 'nom': file,
                 'synopsis': '',
                 'medias': '',
                 'dates': ''
                }
                }
    ## SO NOW WE HAVE A PROPER ANSER TO RETURN`, BUT WE ADD THE LOCAL VALUES
    response['localpath'] = pathtofile+'/'+escapeFileName(file)
    response['localhash'] = sha1.upper()
    response['abspath'] = pathtofile
    ### AND RETURN IT
    return file,response


def scrapeRoms(CURRSSID):
    ### OPEN SYSTEM CONFIGURATION
    with open(sysconfig, 'r') as xml_file:
        tree = ET.ElementTree()
        tree.parse(xml_file)
    ### GET ALL SYSTEMS IN THE CONFIG FILE
    systems = getAllSystems(CURRSSID)
    ### CHECK IF WE HVAE SYSTEMS OR NOT
    if systems == '':
        logging.error('###### CANNOT RETRIEVE SYSTEM LIST, EXITING')
        ### WE STOP EVERYTHING
        sys.exit()
    ### SET THE ROOT OF THE XML DOCUMENT
    root = tree.getroot()
    ### START PARSING THE CONFIGURATION XML
    for child in root:
        ### CHECK FOR SYSTEM TAG
        if child.tag == 'system':
            ### IF THE TAG HAS A SSKIP ATTRIBUTE THEN WE SKIP IT
            if 'sskip' not in child.attrib:
                ### GIVE A DEFAULT SYSTEM ID
                systemid = '000'
                ### INITIALIZE VARIABLE
                path = ''
                ### INITIALIZE VARIABLE
                sysname ='unknown'
                ### ITERATE THROU CHILD TAGS OF SYSTEM
                for system in child:
                    ### CHECK FOR EXTENSION TAG, THAT HOLDS THE LIST OF VALIDD EXTENSIONS FOR THE SYSTEM
                    if system.tag == 'extension':
                        try:
                            ### CREATE A LIST WITH ALL VALID EXTENSIONS (USUALLY THE EXTENSIONS ARE SEPARATED BY A SPACE IN THE CONFIG FILE)
                            extensions = system.text.split(' ')
                        except:
                            ### IF WE CANNOT GET A LIST OF EXTENSIONS FOR A SYSTEM WE DEFAULT TO 'ZIP'
                            extensions = ['zip']
                    if system.tag == 'ssname':
                        ### THIS IS A SPECIAL TAG, IT HAS THE SYSTEM NAME AS DEFINED IN THE SCRAPING SITE, THIS IS TO MATCH AND GET SYSTEM ID
                        try:
                            sysname = system.text.upper()
                        except Exception as e:
                            ### SO WE DIDN'T HAVE A SPECIAL TAGE, SYSTEM IS UNKNOWN
                            sysname = 'unknown'
                            logging.error('###### ERROR GETTING LOCAL SYSTEM ' + str(e))
                    ### LOGIC TO FIND systemid
                    for mysystem in systems:
                        ### API RETRUS SOMETIMES MORE THAN ONE SYSTEM NAME SO WE NEED TO ITERATE THROUGH ALL OF THEM
                        for apisysname in mysystem['noms']:
                            if sysname.upper()==mysystem['noms'][apisysname].upper():
                                ### WE FOUND A MATCH SO WE ASSIGN A SYSTEM ID
                                systemid = str(mysystem['id'])
                                logging.info ('###### FOUND ID '+systemid+' FOR SYSTEM '+sysname)
                                ### AND WE SKIP
                                continue
                    ### TRY TO GET THE LOCAL PATH FOR THE SYSTEM, WHERE ROMS ARE STORED
                    if system.tag == 'path':
                        path = system.text
                ### ONCE WE HAVE ALL VARIABLES NEEDED FOR THE SYSTEM WE CAN START PROCESSING
                ### FIRST WE VERIFY THAT THE PATH EXISTS
                if os.path.isdir(path):
                    ### CHECK IF THERE IS AN IMAGES DIRECTORY IF NOT WE CREATE IT
                    if not os.path.isdir(path+'/images'):
                        os.mkdir(path + '/images')
                    ### CHECK IF THERE IS A VIDEOS DIRECTORY IF NOT WE CREATE IT
                    if not os.path.isdir(path+'/videos'):
                        os.mkdir(path + '/videos')
                    logging.info ('###### DOING SYSTEM ' + str(path)+ ' looking for extensions '+str(extensions))
                    ### SO WE START WITH THE SYSTEM PROCESSING
                    grabData(systemid, path, CURRSSID,extensions)
                    ### WE GO TO NEXT USER INFO
                    CURRSSID = CURRSSID + 1
                    if CURRSSID == len(config.ssid):
                        CURRSSID = 0
                else:
                    logging.error ('###### CANNOT FIND PATH '+path)
            else:
                logging.error ('###### SKIPPING SYSTEM')
    logging.info ('----------------- ALL DONE -------------------')

def updateGameID (file,sha,gameid):
    if gameid != '':
        logging.info ('###### UPDATING GAME ID IN DB FOR '+sha+' WITH VALUE '+str(gameid))
        response = "{'localhash': '"+sha+"', 'GameID': '"+str(gameid)+"', 'file': '"+file+"', 'Error': 'Erreur : Rom/Iso/Dossier non trouvee ! - UPDATED '}"
    else:
        logging.info ('###### ID TO UPDATE IS EMPTY, SO WILL BE THE DB')
        response = ''
    updateDB(sha,response)

def gameNameMatches(orig,chk):
    orig = orig.upper()
    ### PUT 'THE' at the end....
    if orig.upper().find('THE ') == 0:
        orig = orig[4:]+' THE'
    for name in chk['noms']:
        chkname = name['text'].upper()
        chkname = unicodedata.normalize('NFKD', chkname).encode('ascii','ignore')
        logging.info ('###### COMPARING ['+orig+'] WITH ['+chkname+']')
        if str(chkname) == str(orig):
            logging.info ('###### NAME MATCHES')
            return True
        orig = orig.replace('&','AND')
        orig = orig.replace(' XII',' 12')
        orig = orig.replace(' XI',' 11')
        orig = orig.replace(' X',' 10')
        orig = orig.replace(' IX',' 9')
        orig = orig.replace(' VIII',' 8')
        orig = orig.replace(' VII',' 7')
        orig = orig.replace(' VI',' 6')
        orig = orig.replace(' IV',' 4')
        orig = orig.replace(' V',' 5')
        orig = orig.replace(' III',' 3')
        orig = orig.replace(' II',' 2')
        orig = orig.replace(' I',' 1')
        orig = orig.replace(' S ','\'S')
        logging.info ('###### COMPARING ['+orig+'] WITH ['+chkname+']')
        if str(chkname) == str(orig):
            logging.info ('###### NAME MATCHES')
            return True
    logging.info ('###### THERE IS NO MATCH')
    return False

def nameFromArcadeCSV(name):
    with open('/home/pi/arcade_names.csv') as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=',')
        for row in csv_reader:
            if row[0].upper() == name.upper():
                logging.info ('###### FOUND MATCH FOR '+row[1])
                return row[1]
        logging.info ('###### DID NOT FIND MATCH FOR '+name)
    return ''

def getArcadeName(name):
    callURL = 'http://www.mamedb.com/game/'+name+'.html'
    callURL2 = 'http://adb.arcadeitalia.net/dettaglio_mame.php?game_name=' + name
    logging.info ('###### GETTING ARCADE NAME IN URL '+callURL)
    namefromcsv = nameFromArcadeCSV(name)
    if namefromcsv != '':
        return namefromcsv
    try:
        response = urllib2.urlopen(callURL,timeout=20)
        response = response.read()
        gamename = re.findall("<title>(.*?)</title>", response)[0].replace('Game Details:  ','').replace(' - mamedb.com','')
        logging.info ('###### FOUND GAME IN MAMEDB '+gamename)
        return gamename
    except:
        logging.error('###### COULD NOT GET ARCADE NAME FROM MAMEDB')
        logging.info('###### TRYING WITH ARCADEITALIA IN URL '+callURL2)
        try:
            response = urllib2.urlopen(callURL2,timeout=20)
            response = response.read()
            gamename = re.findall("<title>(.*?)</title>", response)[0].replace(' - MAME machine','').replace(' - MAME software','')
            gamename = gamename.replace(' - MAME machin...','')
            logging.info ('###### FOUND GAME IN ARCADEITALIA '+gamename)
            return gamename
        except:
            logging.error ('###### COULD NOT GET NAME FROM ARCADE ITALIA')
            return ''

def deleteFile (file):
    try:
        if os.path.isfile(file):
            os.remove(file)
        logging.info ('##### DELETED FILE '+file)
    except Exception as e:
        logging.error ('##### COULD NOT DELETE FILE '+file)

def findMissing():
    ### GET ALL SYSTEMS, THIS IS DONE TO HAVE A LIST OF ARCADE RELATED SYSTEMS
    systems = getAllSystems(CURRSSID)
    arcadeSystems = [75]
    '''
    for system in systems:
        if 'ARCADE' in system['type'].upper():
            arcadeSystems.append(system['id'])
    '''
    ### read missing file and try to get game by name
    matchPercent = 95
    with open(missing) as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=',')
        line_count = 0
        for row in csv_reader:
            newline =''
            ### clean previous done
            ### CHECK IF THERE IS A SEVENTH COLUMN, WHICH WOULD BE THE GAMEID TO INSERT
            newmode = False
            try:
                logging.info ('###### LOOKING IF THERE IS SOMETHING TO DO')
                whattodo = str(row[6]).upper()
                newmode = True
                logging.info ('###### FOUND SOMETHING TO DO '+whattodo)
                if whattodo=='BIOS':
                    fname = row[1][row[1].rfind('/')+1:]
                    logging.info('###### MOVING TO BIOS '+fname)
                    try:
                        subprocess.call(['mv', row[1], BIOSDIR + '/' + fname])
                    except:
                        logging.error ('###### COULD NOT MOVE '+row[1])
                if whattodo=='UNKNOWN':
                    logging.info('###### ASKED TO UNKNOWN '+row[1])
                    fname = row[1][row[1].rfind('/')+1:]
                    try:
                        subprocess.call(['mv', row[1], UNKDIR + '/' + fname])
                    except:
                        logging.error ('###### COULD NOT MOVE '+row[1])
                if whattodo=='DELETE':
                    logging.info('###### ASKED TO DELETE '+row[1])
                    try:
                        deleteFile(row[1])
                    except:
                        logging.error ('###### COULD NOT DELETE '+row[1])
                else:
                    try:
                        newGameId = int(whattodo)
                    except:
                        newGameId = 0
                    logging.info ('###### FOUND A FORCED GAME ID IN THE FILE '+str(newGameId))
            except Exception as e:
                logging.error('###### ERROR DETECTING NEW MODE '+str(e))
                newGameId = 0
                newmode = False
            ### WE DO NOT HAVE A GAME ID, SO WE HAVE TO SEARCH FOR IT
            logging.info('###### IS THIS A NEW MODE '+str(newmode))
            if newGameId == 0 and not newmode:
                updateGameID (row[1],row[2],'0')
                newline = row[0]+','+row[1]+','+row[2]+','+row[3]+','+row[4]+','+row[5]+',FORCED_ID'
                system=row[0]
                logging.info ('###### DOING RESEARCH FOR '+row[1]+' IN SYSTEM '+str(system))
                if str(system) != '75':
                    searchSystems=[system]
                    filename=(row[1][row[1].rfind('/')+1:row[1].rfind('.')]).replace('_',' ')
                    ### GBA Exception
                    if str(system) == '12':
                        filename = filename[7:]
                else:
                    filename=row[1][row[1].rfind('/')+1:row[1].rfind('.')]
                    filename = getArcadeName(filename)
                    newline = newline +','+filename
                    searchSystems = arcadeSystems
                logging.info ('###### WILL SEARCH IN '+str(searchSystems))
                subOne = (re.sub('[V|v]+\d+.\d+','',filename)).strip()
                subTwo = (subOne.rstrip('0123456789')).strip()
                subThree = (re.sub(r'\[[^)]*\]','',subTwo)).strip()
                myGameName = (re.sub(r'\([^)]*\)','',subThree)).strip()
                myGameName = myGameName.replace('   ',' ')
                myGameName = myGameName.replace('  ',' ')
                if myGameName !='':
                    sha = row[2]
                    myParams = None
                    myParams = fixParams
                    logging.info ('###### STRIPPED TO '+myGameName)
                    keepon = True
                    found = False
                    API= 'jeuRecherche'
                    full = True
                    returnValue = {}
                    totalWords = len(myGameName.split(' '))
                    ansretries = totalWords
                    myParams['recherche']=myGameName.split(' ')[0]
                    if myParams['recherche'].upper() == 'EAMON':
                            myParams['recherche'] = myParams['recherche'] + ' ' + myGameName.split(' ')[1]
                            ansretries = ansretries - 1
                            totalWords = totalWords - 1
                            if len(myGameName.split(' '))>3:
                                myParams['recherche'] = myParams['recherche'] + ' ' + myGameName.split(' ')[3]
                                ansretries = ansretries - 1
                                totalWords = totalWords - 1
                            if len(myGameName.split(' '))>4:
                                myParams['recherche'] = myParams['recherche'] + ' ' + myGameName.split(' ')[4]
                                ansretries = ansretries - 1
                                totalWords = totalWords - 1
                    found = False
                    systemPos = 0
                    oriretries = ansretries
                    origsearch = myParams['recherche']
                    while (ansretries > 0) and not found and systemPos<len(searchSystems):
                        myParams['systemeid']=searchSystems[systemPos]
                        ## VOY A BUSCAR LOS TRES PRMEROS CARACTERES, Y DESPUES HACER UNA LOGICA EN EL MATCH DE CUANTOS CARACTERES IGUALES HAY
                        if ansretries < totalWords:
                            myParams['recherche'] = myParams['recherche'] + ' ' + myGameName.split(' ')[totalWords-ansretries]
                        logging.info('###### LOOKING SCRAPER FOR '+myParams['recherche']+ ' FOR SYSTEM '+str(searchSystems[systemPos]))
                        returnValue = callAPI(fixedURL,API,myParams,0,False,'2')
                        if 'jeux' in returnValue.keys():
                            if len(returnValue['jeux']) > 1:
                                position = 0
                                for game in returnValue['jeux']:
                                    thisGameID = returnValue['jeux'][position]['id']
                                    if gameNameMatches(myGameName,game):
                                        updateGameID (row[1],sha,thisGameID)
                                        found = True
                                        keepon = False
                                        continue
                                    for gameName in game['noms']:
                                        newline = newline + ',' + gameName['text']
                                    newline = newline + ',' + thisGameID
                                    position = position+1
                            else:
                                if str(returnValue['jeux'][0]) != '{}':
                                    game = returnValue['jeux'][0]
                                    thisGameID = returnValue['jeux'][0]['id']
                                    if gameNameMatches(myGameName,game):
                                        updateGameID (row[1],sha,thisGameID)
                                        logging.info ('###### FOUND MISSING INFO FOR '+filename+' SHA '+sha)
                                        found = True
                                        keepon = False
                                    else:
                                        for gameName in game['noms']:
                                            newline = newline + ',' + gameName['text']
                                        newline = newline + ',' + thisGameID
                        ansretries = ansretries - 1
                        if ansretries == 0 and len(searchSystems)>1:
                            ansretries = oriretries
                            systemPos = systemPos + 1
                            myParams['recherche'] = origsearch
                    if not found:
                        logging.info ('###### COULD NOT FIND MISSING INFO FOR '+filename)
                        writeNewMissing(newline)
                else:
                    logging.info ('###### COULD NOT FIND MISSING INFO FOR '+filename)
                    writeNewMissing(newline)
            else:
                if newGameId !=0:
                    updateGameID (row[1],row[2],newGameId)
                logging.info ('###### UPDATED FORCED ID OF '+row[1]+' TO '+str(newGameId))
        logging.info ('###### FINISHED LOOKING FOR MISSING ROMS')


################# START ###########################################
#### SELECT WHAT TO DO BASED ON PARAMETERS PASSED TO PROGRAM


def cleanGameList(path):
    with open(path, 'r') as xml_file:
        tree = ET.ElementTree()
        tree.parse(xml_file)
    ### SET THE ROOT OF THE XML DOCUMENT
    root = tree.getroot()
    for child in root:
        if child.tag.upper() == 'GAME':
            file = ''
            sha = ''
            image = ''
            video = ''
            for gchild in child:
                if gchild.tag.upper() == 'HASH':
                    sha = gchild.text
                if gchild.tag.upper() == 'PATH':
                    file = gchild.text
                if gchild.tag.upper() == 'IMAGE':
                    try:
                        image = gchild.text.decode()
                    except:
                        image = ''
                if gchild.tag.upper() == 'VIDEO':
                    try:
                        video = gchild.text.decode()
                    except:
                        video = ''
        if sha !='' and file != '':
            if image != '':
                try:
                    if os.path.isfile(image):
                        os.remove(image)
                        logging.info ('###### DELETED IMAGE '+image)
                except Exception as e:
                    logging.error ('###### COULD NOT DELETE '+image+' '+str(e))
            if video != '':
                try:
                    if os.path.isfile(video):
                        os.remove(video)
                        logging.info ('###### DELETED VIDEO '+video)
                except Exception as e:
                    logging.error ('###### COULD NOT DELETE '+video+' '+str(e))
            updateGameID (file,sha,'')
            logging.info ('###### REMOVED '+file+' WITH HASH '+sha)
def cleanSys(system):
    ### Get all systems from XML
    with open(sysconfig, 'r') as xml_file:
        tree = ET.ElementTree()
        tree.parse(xml_file)
    ### SET THE ROOT OF THE XML DOCUMENT
    root = tree.getroot()
    ### START PARSING THE CONFIGURATION XML
    found = False
    path = ''
    for child in root:
        ### CHECK FOR SYSTEM TAG
        if child.tag == 'system':
            if not found:
                for nchild in child:
                    if nchild.tag == 'name':
                        if system.upper() == nchild.text.upper():
                            found = True
                    if nchild.tag == 'path':
                            path = nchild.text
    if found:
        glist = path+'/gamelist.xml'
        cleanGameList(glist)
        logging.info ('###### FINISHED CLEANING '+glist)
    else:
        logging.error ('###### COULD NOT FIND SYSTEM '+system)
        sys.exit(0)

if cleanSystem !='':
    ### CLEAN SYSTEM, THIS PROCEDURE DELETES ALL DB RECORDS FOR FILES FOUND IN GAMELIST FOR A GIVEN SYSTEM
    cleanSys(cleanSystem)
    sys.exit(0)

if missing !='':
    ### FIND MISSING FILES FROM MISSING FILES
    ### THIS PROCEDURE OPENS A CSV FILE CONTAINING SYSTEM_ID,FILENAME,SHA,MD5,CRC
    ### IT WILL THEN TRY TO MATCH FILENAMES WITH GAME NAMES AND ADD GAME_ID IF FOUND TO DB
    findMissing()
    scrapeRoms(CURRSSID)

else:
    ### THIS PROCEDURE WILL GO THROUGH ALL ROMS DIRECTORIES IN SYSTEM CONFIGURATION AND TRY TO SCRAPE THEM
    scrapeRoms(CURRSSID)

sys.exit(0)
