# -*- coding: utf-8 -*-
# Your code goes below this line

import csv
import ast
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
import cookielib
import config


### Parse arguments first
### Arguments are :
### --missing: parse missing file and try to scrape based on name, also parses extra missing info if file has it
### --update: refresh information from site, redownloads images
### --clean: removes all information from a system in the local DB, needs to have system specified
### --rename: will look into the game name as downloaded from the site and rename the file accordingly

parser = argparse.ArgumentParser(description='ROM scraper, get information of your roms from screenscraper.fr')
parser.add_argument('--missing', help='Try to find missing ganes from the missing file',nargs=1)
parser.add_argument('--update', help='Update local DB information from screenscraper',const='True',nargs='?')
parser.add_argument('--clean', help='Clean a system from the DB, deletes all records from files',nargs=1)
parser.add_argument('--rename', help='Rename files to match the actual game name in the DB',nargs='?')
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
    dbRename = args['rename']
    if dbRename == None:
        dbRename = False
    else:
        dbRename = True
except:
    dbRename = False

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

sysconfig = config.sysconfig

tmpdir = config.tmpdir

try:
    mydb = mysql.connector.connect(
    host=config.dbhost,
    user=config.dbuser,
    passwd=config.dbpasswd,
    database=config.database
    )
except Exception as e:
    logging.error ('###### CANNOT CONNECT TO DATABASE '+config.dbhost+'/'+config.database+' Error:'+str(e))
    logging.error ('###### PLEASE MAKE SURE YOU HAVE A DATABASE SERVER THAT MATCHES YOUR CONFIGURATION')
    print (str(e))
    sys.exit()

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

## QUOTA LIMITER FOR V2CALLS
VTWOQUOTA = False

### INSERT THE EXTENSIONS YOU DO NOT WANT TO HAVE ZIPPED IN THE LIST BELOW
donotcompress = config.donotcompress
### OUTPUT FILE WITH THE MISSING FILES CREATED IN THE FIRST ROUND
missingfile= config.missingfile
### OUTPUT FILE WITH THE MISSING FILES CREATED IN THE SECOND ROUNF (WHEN --missing PARAMETER IS PASSED)
newmissingfile= config.newmissingfile

BIOSDIR = config.BIOSDIR
UNKDIR = config.UNKDIR

cookies = cookielib.LWPCookieJar()

arcadeSystems = ('75','142','56','151','6','7','8','196','35','47','49','54','55','56','68','69','112','147','148','149','150','151','152','153','154','155','156','157','158','159','160',
                 '161','162','163','164','165','166','167','168','169','170','173','174','175','176','177','178','179','180','181','182','183','184','185','186','187','188','189','190','191',
                 '192','193','194','195','196','209')

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
        self.name = json['jeu']['nom'].decode('utf8').encode('ascii','ignore')
        mdisk = multiDisk(self.path)
        mvers = multiVersion(self.path)
        mctry = multiCountry(self.path)
        if mctry:
            self.name = self.name+' '+mctry.group(0)
        if mdisk:
            self.name = self.name+' '+mdisk.group(0)
        if mvers:
            self.name = self.name +' ('+mvers.group(0)+')'
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

def updateInDBV2Call(api,params,response):
    ### Update the DB with the call to V2
    if ('Error 400:' in str(response) or 
       'Error 401:' in str(response) or 
       'Error 403:' in str(response) or 
       'Error 404:' in str(response) or 
       'Error 423:' in str(response) or 
       'Error 426:' in str(response) or 
       'Error 429:' in str(response) or 
       'Error 430:' in str(response) or 
       'Error 431:' in str(response) or 
       'QUOTA' in str(response)):
        ### TODO VERIFY POSSIBILITY OF PASSING FALSE
        logging.error ('###### GOT AN ERROR FROM API CALL SO NOT UPDATING V2 DB')
        return True
    result = ''
    logging.debug ('###### CONNECTING TO DB TO UPDATE CACHED RESULT FOR V2 CALL')
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
    sql = "INSERT INTO apicache (apiname,parameters,result) VALUES (%s,%s,%s)"
    val = (api,params,response)
    connected = False
    logging.debug ('###### TRYING TO INSERT INTO DB API V2 CACHE')
    try:
        mycursor.execute(sql, val)
        #logging.debug ('@@@@@@@@@@ '+str(mycursor.statement))
        if mycursor.rowcount == 0:
            logging.debug ('###### COULD NOT INSERT IN THE DB')
            return False
        else:
            logging.debug ('###### INSERTED SUCCESFULLY IN DB')
            mydb.commit()
            return True
    except Exception as e:
        logging.error ('###### CANNOT QUERY THE DB DUE TO ERROR - '+str(e))
        return True
    return True

def searchInDBV2Call(api,params):
    ### Try to see if it is in cache
    result = ''
    logging.debug ('###### CONNECTING TO DB TO LOCATE CACHED RESULT FOR V2 CALL')
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
    sql = "SELECT result FROM apicache WHERE apiname = %s AND parameters = %s"
    val = (api,params )
    connected = False
    logging.debug ('###### TRYING TO QUERY DB API V2 CACHE')
    try:
        mycursor.execute(sql, val)
        logging.debug ('@@@@@@@@@@ '+str(mycursor.statement))
        if mycursor.rowcount == 0:
            logging.debug ('###### NO CACHED CALL FOUND IN THE DB')
            return None
        else:
            result = mycursor.fetchall()
            result = result[0][0]
            logging.debug ('###### FOUND CACHED CALL IN DB')
            return result
    except Exception as e:
        logging.error ('###### CANNOT QUERY THE DB DUE TO ERROR - '+str(e))
        return None
    return None

def callAPIURL(URL):
    #### ACTUAL CALL TO THE API
    ## Check if it is a v2 Call first
    response=''
    apiname =''
    logging.debug ('####### CALLING URL '+URL)
    v2 = re.search('\/[a|A][P|p][i|I]2\/',URL)
    logging.debug('###### IS V2 '+str(v2))
    if v2:
        logging.debug ('###### THIS IS A V2 CALL ')
        ### It is a V2 call try to get parameters
        params = re.finditer('[\?|&]\S[^&]*',URL)
        logging.debug ('###### PARAMS ARE '+str(params))
        dbparams = ''
        excludeparams = ['devpassword','ssid','devid','softname','sspassword']
        if params:   
            logging.debug ('###### FOUND PARAMS '+str(params))
            for param in params:
                mypar = param.group(0)
                ## Exclude non essential params from query
                chkparam = mypar[1:mypar.index('=')]
                logging.debug ('###### CHECKING PARAMETER '+chkparam)
                if not chkparam in excludeparams:
                    dbparams=dbparams+mypar[1:]
                else:
                    logging.debug('###### PARAMETER '+chkparam+' IN EXCLUDE LIST')
            #### Search in DB
            apiname = URL[URL.lower().rindex('api2/')+5:URL.lower().index('?')]
            logging.debug ('###### CALLED API '+apiname)
            logging.debug ('###### PARAMETERS '+dbparams)
            response = searchInDBV2Call(apiname,dbparams)
            if response:
                #logging.debug ('###### RESPONSE FROM DB '+str(response))
                return response
    request = urllib2.Request(URL)
    response = urllib2.urlopen(request,timeout=20).read()
    #logging.debug ('####### GOT RESPONSE ['+str(response)+'] AFTER CALLING URL')
    if v2 and apiname !='' and response!='':
        updateInDBV2Call(apiname,dbparams,response)
    if 'Error 431:' in response:
        return 'QUOTA' 
    else:
        return response

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
    cands = []
    filemap=dict()
    if os.path.exists(directory):
        os.chdir(directory)
        ### LOOKUP ALL FILES WITH EXTENSION
        files = glob.glob(extension)
        ### TREAT EACH FILE
        for file in files:
            ### DISCARD SYMBOLIC LINKS
            if not os.path.islink(file):
                size = str(os.path.getsize(file))
                if size not in filemap:
                    filemap[size]=[file]
                else:
                    filemap[size].append(file)
                    if size not in cands:
                        cands.append(size)
    for key in cands:
        for file in filemap[key]:
            for cfile in filemap[key]:
                if not os.path.islink(file) and file != cfile and (sha1(file) == sha1(cfile)):
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
    return

def writeMissing(sysid,file):
    ### THIS FUNCTION WRITES TO THE MISSING LIST
    logging.debug ('###### ADDING FILE TO MISSING FILE')
    try:
        f=open(missingfile, "a+")
        f.write(str(sysid)+'|'+str(file)+'|'+str(sha1(file))+'|'+str(md5(file))+'|'+str(crc(file))+'|'+str(os.stat(file).st_size/1024)+'\n')
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
    if os.path.isfile(destfile):
        logging.debug ('###### FINAL FILE ALREADY EXISTS - NO NEED TO DO ANYTHING')
        return True
    else:
        imgbase = Image.new('RGBA', (640, 530), (255, 0, 0, 0))
        imgb = Image.new('RGBA', (150, 150), (255, 0, 0, 0))
        if img1!='':
            try:
                imga = Image.open(img1).convert('RGBA')
                imga = imga.resize((640,480), Image.ANTIALIAS)
            except Exception as e:
                logging.error ('###### CANNOT RESIZE FIRST IMAGE '+str(e))
                imga = Image.new('RGBA', (640, 480), (255, 0, 0, 0))
        else:
            imga = Image.new('RGBA', (640, 480), (255, 0, 0, 0))
        if img2!='':
            try:
                imgb = Image.open(img2).convert('RGBA')
                imgb = imgb.resize((200,300), Image.ANTIALIAS)
            except Exception as e:
                logging.error ('###### CANNOT RESIZE SECOND IMAGE '+str(e))
                imgb = Image.new('RGBA', (110, 150), (255, 0, 0, 0))
        else:
            imgb = Image.new('RGBA', (150, 150), (255, 0, 0, 0))
        try:
            imgbase.paste(imga,(0,0),imga)
            imgbase.paste(imgb,(0,230),imgb)
            imgbase.save(destfile, format="png")
            logging.debug ('###### SAVED COMPOSITE IMAGE '+destfile)
        except Exception as e:
            logging.error ('###### CANNOT MERGE FILE '+str(e))
            return False
    if img1 !='':
        try:
            if os.path.isfile(img1):
                os.remove(img1)
        except:
            logging.error ('###### CANNOT REMOVE 1ST IMAGE '+str(img1))
    if img2 !='':
        try:
            if os.path.isfile(img2):
                os.remove(img2)
        except:
            logging.error ('###### CANNOT REMOVE 2ND IMAGE '+str(img2))
    return True
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
        params =dict(fixParams)
        params['gameid'] = 1
        response = callAPI(fixedURL,API,params,0,anon,'2','WAIT NEW DAY')
        anon = not anon
        if 'ssuser'  in response:
            allowed = True
            VTWOQUOTA = False            
    logging.info ('###### FINISHED WAITING')
    return

def callAPI(URL, API, PARAMS, CURRSSID,Anon=False,Version='',tolog=''):
    global VTWOQUOTA
    if Version=='2' and VTWOQUOTA and not Anon:
        logging.info ('###### DAILY QUOTA HAS BEEN EXCEEDED FOR V2 API - CANNOT CALL IT FOR NOW')
        return 'QUOTA'
    logging.debug ('###### CALLING API WITH EXTRA '+tolog)
    ### FNCTION THAT ACTUALLY DOES THE CALL TO THE API
    retries = 10
    ### IS IT AN ANONYMOUS CALL
    if not Anon:
        ### NO IT IS NOT, ADD USER PARAMETERS
       logging.debug ('##### CALLING API AS NOT ANONYMOUS')
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
    while retries > 0 and (not VTWOQUOTA or Version !='2' or Anon):
        ### EMPTY RESPONSE JUST IN CASE
        response = None
        logging.debug ('###### CALLING API TRY '+str(11-retries))
        logging.debug ('##### ACTUAL CALL TO API '+API)
        data = {}
        retJson = None
        try:
            logging.debug ('###### CALLING URL '+callURL)
            response = callAPIURL(callURL)
            ### TODO : HANDLE QUOTA FOR V2
            if str(Version)=="2":        
                if 'QUOTA' in response:
                    logging.info ('###### YOUR SCRAPING QUOTA FOR V2 IS OVER FOR TODAY')
                    VTWOQUOTA = True
                else:
                    VTWOQUOTA = False
            if Anon:
                logging.debug('###### ANON RESPONSE '+str(response))
                logging.debug('###### CALLING '+str(callURL))
            if '{' in response:
                a = '{'+response.split('{', 1)[1]
                response = a.rsplit('}', 1)[0] + '}'
                retJson = json.loads(response)
            else:
                if ('Faite du tri dans vos fichiers roms et repassez demain' in response) or 'QUOTA' in response:
                    logging.critical('###### ALLOCATED ALLOWANCE EXCEEDED FOR TODAY')
                    #### RETURN WHEN THERE ALLOWANCE IS DONE
                    #### waitNewDay(runTime)
                    return 'QUOTA'
                    response = callAPIURL(callURL) 
                    if '{' in response:
                        a = '{'+response.split('{', 1)[1]
                        response = a.rsplit('}', 1)[0] + '}'
                        retJson = json.loads(response)
                    else:
                        retJson = response
            if isinstance(retJson, (dict, list)):
                myJson = retJson['response']
                okcalls = myJson['ssuser']['requeststoday']
                okmax = myJson['ssuser']['maxrequestsperday']
                kocalls = myJson['ssuser']['requestskotoday']
                komax = myJson['ssuser']['maxrequestskoperday']
                logging.debug ('###### V2 QUOTA INFO - OK CALLS '+str(okcalls)+' KO CALLS '+str(kocalls)+' OK MAX '+str(okmax)+' KO MAX '+str(komax))
                if int(okcalls) >= int(okmax) or int(kocalls) >= int(komax):
                    VTWOQUOTA = True
                    logging.debug('###### MAXIMUM DAILY QUOTA IS OVER')
                    response = 'QUOTA'
                else:
                    VTWOQUOTA = False
                return myJson
            else:
                data['Error'] = response
            return json.loads(json.dumps(data))
        except Exception as e:
            data['Error'] = str(e)
            ####logging.debug ('###### RESPONSE '+str(response.encode('ascii','ignore')))
            data['Response'] =str(response)
            logging.error ('##### FAILED TO CALL API '+str(e))
            if 'Error 431:' in str(e):
                logging.debug ('####### SETTING QUOTA TO OVER')
                VTWOQUOTA = True
                data['Error'] = 'QUOTA'
            else:
                VTWOQUOTA = False
                logging.debug ('####### SETTING QUOTA TO OK')
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
            logging.debug ('###### ACTUALLY DOWNLOADING VIDEO '+str(URL))
            logging.debug ('###### COMMAND: wget --retry-connrefused --waitretry=1 --read-timeout=20 --timeout=15 --tries=5 -c -q '+str(URL)+' -O '+str(destfile))
            result = subprocess.call(['wget','--retry-connrefused','--waitretry=1','--read-timeout=20','--timeout=15','--tries=5','-c','-q', URL, '-O', destfile])
            logging.debug ('###### VIDEO DOWNLOAD RESULT '+str(result))
            logging.debug ('###### FILE EXISTS '+str(os.path.isfile(destfile)))
            if not validateVideo(destfile):
                if os.path.isfile(destffile):
                    os.remove(destfile)
                logging.error ('###### DOWNLOAD IS TOO SMALL')
                if 'clone.' in URL and 'screenscraper' in URL:
                    URL = URL.replace ('clone.','www.')
                else:
                    if "screenscraper" in URL:
                        URL = URL.replace ('www.','clone.')
                    if '/api/' in URL:
                        logging.debug('###### API IS NOT WORKING, LET\'S TRY API2')
                        URL = URL.replace ('/api/','/api2/')
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
        if os.path.islink(imagefile):
            logging.debug ('###### IT IS A SYMLONK SO ASSUMING IMAGE IS OK')
            return True
        im=Image.open(imagefile)
        logging.debug ('###### IMAGE SEEMS TO BE OK')
        return True
    except Exception as e:
        logging.debug ('###### IMAGE IS CORRUPT '+str(e))
        return False

def validateVideo(videofile):
    if os.path.islink(videofile):
        logging.debug ('###### IS A SYMLINK, SO ASSUME IT IS OK')
        return True
    try:
        fileInfo = MediaInfo.parse(videofile)
        for track in fileInfo.tracks:
            if track.track_type.upper() == "VIDEO":
                logging.debug ('###### IT IS A PROPER VIDEO')
                return True
        logging.debug('###### COULD NOT FIND ANY VIDEO TRACKS IN THE FILE')
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
                    logging.debug('###### COULD NOT VALIDATE '+destfile+' SO I REMOVE IT')
                    os.remove(destfile)
                if 'clone.' in URL and 'screenscraper' in URL:
                    logging.debug('###### .CLONE IS NOT WORKING LET\'S TRY WWW.')
                    URL = URL.replace ('clone.','www.')
                else:
                    if 'screenscraper' in URL:
                        logging.debug('###### .WWW IS NOT WORKING, LET\'S TRY CLONE.')
                        URL = URL.replace ('www.','clone.')
                    if '/api/' in URL:
                        logging.debug('###### API IS NOT WORKING, LET\'S TRY API2')
                        URL = URL.replace ('/api/','/api2/')
                logging.error ('###### DOWNLOAD IS CORRUPTED ON RETRY '+str(retries+1)+' URL '+str(URL))
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
        if 'screenscraper' in URL:
            mediaURL = URL.replace('clone.', 'www.')
            #mediaURL = URL
            mediaPos = mediaURL.find('mediaformat=')+12
            mediaFormat = mediaURL[mediaPos:mediaPos+3]
            if mediaFormat == '':
                mediaFormat = '.png'
            return grabMedia(mediaURL,tmpdir+'image'+str(num)+'.'+mediaFormat,60)
        ##### URL Is not in screenscraper
        else:
            mediaFormat = URL[URL.rindex('.')+1:]
            mediaURL = URL
            return grabMedia(mediaURL,tmpdir+'image'+str(num)+'.'+mediaFormat,60)
    else:
         return ''


def getBoxURL (list):
    found = False
    URL =''
    for key,value in list.iteritems():
        if not ('crc' in key or 'sha1' in key or 'md5' in key):
            if '_eu' in key:
                if value != None and value !='' and not found:
                    URL = value
                    found = True
            else:
                if not found:
                    if value != None and value !='':
                        URL = value
                        found = True
    return URL

def getBezelURL (list):
    found = False
    URL =''
    for key,value in list.iteritems():
        if not ('crc' in key or 'sha1' in key or 'md5' in key):
            if '_eu' in key:
                if value != None and value !='' and not found:
                    URL = value
                    found = True
            else:
                if not found:
                    if value != None and value !='':
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
            if 'screenscraper' in URL:
                mediaURL = URL.replace('clone.', 'www.')
                mediaPos = mediaURL.find('mediaformat=')+12
                mediaFormat = mediaURL[mediaPos:mediaPos+3]
            else:
                mediaURL = URL
                mediaFormat = URL[URL.rindex('.')+1:]
            logging.debug ('###### DOWNLOADING BEZEL')
            destpath = syspath.replace('roms','overlays')
            destfile = destpath+'/bezel-'+str(name)+'.'+mediaFormat
            logging.debug ('###### DESTINATION IS '+destfile)
            if not os.path.isfile(destfile):
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
        if 'screenscraper' in URL:
            mediaURL = URL.replace('clone.', 'www.')
            #mediaURL = URL
            mediaPos = mediaURL.find('mediaformat=')+12
            mediaFormat = mediaURL[mediaPos:mediaPos+3]
            if mediaFormat == '':
                mediaFormat = 'png'
        else:
            mediaURL = URL
            mediaFormat = URL[URL.rindex('.')+1:]
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
        if 'screenscraper' in URL:
            mediaURL = URL.replace('clone.', 'www.')
        else:
            mediaURL = URL
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
        else:
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
    response = callAPI(fixedURL, API, fixParams, CURRSSID,False,'2','Get All Systems')
    ### IF WE GET A RESPONSE THEN RETURN THE LIST
    if 'Error' not in response.keys():
        try:
            return response['systemes']
        except Exception as e:
            return str(e) + ' ' + str(response)
    else:
        ### WE COULD NOT GET THE LIST OF SYSTEMS SO RETURN EMPTY
        return ''

def deleteHashCache(file):
    logging.debug ('####### GOING TO REMOVE HASH CACHE FOR '+file)
    sql = "DELETE FROM filehashes WHERE file = %s"
    val = (file, )
    connected = False
    logging.debug ('###### TRYING TO DELETE INFO IN HASH DB FOR '+file)
    mycursor = mydb.cursor()
    try:
        mycursor.execute(sql, val)
        if mycursor.rowcount == 0:
            logging.debug ('###### NOT FOUND IN THE DB')
            return ''
        else:
            logging.debug('###### RECORDS DELETED')
    except Exception as e:
            logging.error ('###### ERROR DELETING RECORDS FOR '+file+' FROM DB :'+str(e))
    return ''


def getAllGamesinDB():
    result = ''
    logging.debug ('###### CONNECTING TO DB TO GET ALL FILE HASHES ')
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
    sql = "SELECT file,SHA1,CRC,MD5 FROM filehashes"
    val = ()
    connected = False
    logging.debug ('###### TRYING TO QUERY DB FOR ALL FILE HASHES')
    try:
        mycursor.execute(sql, val)
        logging.debug ('@@@@@@@@@@ '+str(mycursor.statement))
        if mycursor.rowcount == 0:
            logging.debug ('###### FILEHASHES TABLE SEEMS TO BE EMPTY')
            return ''
        else:
            results = mycursor.fetchall()
            logging.error ('###### FOUND '+str(len(results))+' RESULTS FOR FILE HASHES')
            return results
    except Exception as e:
        logging.error ('###### CANNOT QUERY THE DB DUE TO ERROR - '+str(e))
        return ''
    return ''


def lookupHashInDB(file,hashType):
    result = ''
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
        logging.debug ('@@@@@@@@@@ '+str(mycursor.statement))
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
    val =(str(hash),str(file))
    try:
        mycursor.execute(sql, val)
        mydb.commit()
        logging.debug ('###### UPDATED '+hashType+' '+hash+' FOR FILE '+file)
    except Exception as e:
        logging.error ('###### COULD NOT UPDATE DATA IN DB ' +str(e))
    return

def insertHashInDB(file,hashType,hash):
    logging.debug ('###### INSERTING '+hashType+' '+hash+' FOR FILE '+file)
    mycursor = mydb.cursor()
    sql = "INSERT INTO filehashes (file, "+hashType.upper()+") VALUES (%s, %s)"
    val =(str(file),str(hash))
    try:
        mycursor.execute(sql, val)
        mydb.commit()
        logging.debug('###### INSERTED '+hashType.upper()+' '+str(hash)+' FOR FILE '+file)
    except Exception as e:
        logging.error ('###### COULD NOT INSTERT DATA IN DB ' +str(e))
        logging.debug('###### UPDATED LOCAL CACHE')
        updateHashInDB(file,hashType,hash)
    return


def md5(fname):
    dbval =''
    dbval = lookupHashInDB(fname,'MD5')
    if dbval !='' and dbval != None:
        logging.debug('###### FOUND SOMETHING IN DB FOR '+fname+' SO RETURNING MD5='+str(dbval))
        return dbval
    logging.debug ('###### NOT IN DB SO CALCULATING MD5 OF FILE '+fname)
    try:
        retval = None
        hash_md5 = None
        hash_md5 = hashlib.md5()
        with open(fname, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        retval = hash_md5.hexdigest()
        logging.debug('###### CALCULATED MD5 FOR '+fname+' '+str(retval))
        insertHashInDB(fname,'MD5',retval)
        return retval
    except Exception as e:
        logging.error('###### COULD NOT CALCULATE MD5 ' + str(e))
        return ''

def sha1(fname):
    dbval = ''
    dbval = lookupHashInDB(fname,'SHA1')
    if dbval !='' and dbval != None:
        logging.debug ('###### FOUND SHA1 '+str(dbval)+' FOR FILE '+fname)
        return dbval
    logging.debug ('###### NOT IN DB SO CALCULATING SHA1 OF FILE '+fname)
    try:
        retval = None
        BLOCKSIZE = 65536
        hasher = None
        hasher = hashlib.sha1()
        with open(fname, 'rb') as afile:
            buf = afile.read(BLOCKSIZE)
            while len(buf) > 0:
                hasher.update(buf)
                buf = afile.read(BLOCKSIZE)
        retval = hasher.hexdigest()
        logging.debug ('###### SHA 1 '+str(retval)+' CALCULATED FOR FILE '+fname)
        insertHashInDB(fname,'SHA1',retval)
        return retval
    except Exception as e:
        logging.error('###### COULD NOT CALCULATE SHA1 ' + str(e))
        return ''

def crc(fileName):
    dbval=''
    dbval = lookupHashInDB(fileName,'CRC')
    if dbval !='' and dbval != None:
        logging.debug ('###### FOUND CRC '+str(dbval)+' FOR FILE '+fileName)
        return dbval
    logging.debug ('###### NOT IN DB SO CALCULATING CRC OF FILE '+fileName)
    try:
        retval = None
        prev = 0
        for eachLine in open(fileName, "rb"):
            prev = zlib.crc32(eachLine, prev)
        retval = "%X" % (prev & 0xFFFFFFFF)
        insertHashInDB(fileName,'CRC',retval)
        logging.debug ('###### CALUCLATED CRC '+str(retval)+' FOR FILE '+fileName)
        return retval
    except Exception as e:
        logging.error('COULD NOT CALCULATE CRC ' + str(e))
        return ''

def escapeFileName(file):
    ### JUST MACE SURE THAT WE HAVE A NORMALIZED FILENAME
    return file.decode('utf8').encode('ascii','ignore')


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
            shazfile = ''
            shazfile=sha1(path+'/'+proczfile)
            crczfile = ''
            crczfile=crc(path+'/'+proczfile)
            md5zfile = ''
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
    try:
        os.chdir(path+'/'+dir)
    except Exception as e:
        logging.error('###### COULD NOT CHANGE TO DIRECTORY '+path+'/'+dir+' PLEASE VERIFY')
        return None
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
    if gameinfo:
        try:
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
        except Exception as e:
            ### SO WE DID GET SOMETHING BUT NOT USABLE, RETURN NONE THEN
            logging.error('###### COULD NOT GET GAME INFO '+str(e))
            return file, None
    else:
        ### SO WE DIDN'T GET ANYTHING, RETURN NONE THEN
        logging.info('###### COULD NOT GET GAME INFO ')
        return file, None
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
    md5offile = ''
    md5offile = md5(path+'/'+file)
    ### SHA1
    sha1offile = ''
    sha1offile = sha1(path+'/'+file)
    ### CRC
    crcoffile = ''
    crcoffile = crc(path+'/'+file)
    logging.debug ('##### GETTING GAME INFO '+str(path)+'/'+str(file)+' '+str(md5offile)+' '+str(sha1offile)+' '+str(crcoffile))
    ### TRY TO GET GAME INFORMATION
    gameinfo = None
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
                thisGame = None
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
        #### REMOVE THE LINE BELOW PLEASE
        sys.exit(0)
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

def locateShainDB(mysha1):
    result = ''
    logging.debug ('###### CONNECTING TO DB TO LOCATE DATA FOR '+mysha1)
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
    val = (mysha1, )
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
        logging.debug ('###### CONVERTING TO PYTHON DICTIONARY')
        value = ast.literal_eval(result)
    except Exception as e:
        logging.error ('###### COULD NOT CONVERT DB RESULT '+str(result)+' TO JSON '+str(e))
        return ''
    if 'urlopen error' in str(value) or 'QUOTA' in str(value) or 'Faite du tri' in str(value):
        ## Delete from DB
        logging.debug ('###### DELETING RECORD FROM DB')
        deleteFromDB(mysha1)
        return ''
    return value

def updateDB(mysha1,response):
    logging.debug ('###### CALLED UPDATE DB WITH RESPONSE '+str(response))
    if ('Error 400:' in str(response) or 
       'Error 401:' in str(response) or
       'Error 403:' in str(response) or 
       'Error 404:' in str(response) or 
       'Error 423:' in str(response) or 
       'Error 426:' in str(response) or 
       'Error 429:' in str(response) or 
       'Error 430:' in str(response) or 
       'Error 431:' in str(response) or 
       'QUOTA' in str(response)):
        logging.debug ('###### GOT AN ERROR FROM API CALL SO I\'M NOT UPDATING THE DB HASH')
        return 
    if not 'urlopen error' in response:
        mycursor = mydb.cursor()
        sql = "REPLACE INTO hashes (hash, response) VALUES (%s, %s)"
        val =[(str(mysha1),str(response))]
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

def deleteHashFromDB(filename):
    mycursor = mydb.cursor()
    sql = 'DELETE FROM filehashes WHERE file = "%s"'
    val =(str(filename))
    try:
        result = mycursor.execute(sql, val)
        mydb.commit()
        logging.debug ('@@@@@@@@@@ '+str(mycursor.statement))
        logging.info ('###### DB UPDATED OK ['+str(result)+']')
    except Exception as e:
        logging.error ('###### COULD NOT DELETE FROM DB ' +str(e))
        return 1
    return 0


def updateDBFile(origfile,destfile):
    mycursor = mydb.cursor()
    sql = 'UPDATE filehashes SET file = %s WHERE file = %s'
    val =(str(destfile),str(origfile))
    try:
        result = mycursor.execute(sql, val)
        mydb.commit()
        logging.debug ('@@@@@@@@@@ '+str(mycursor.statement))
        logging.info ('###### DB UPDATED OK ['+str(result)+']')
    except Exception as e:
        logging.error ('###### COULD NOT INSTERT DATA IN DB ' +str(e))
        return 1
    return 0

def getGameInfo(CURRSSID, pathtofile, file, mymd5, mysha1, mycrc, sysid):
    ### THIS IS WHERE EVERYTHING HAPPENS
    ### IS ANY OF THE PARAMETERS EMPTY?
    if mymd5 == '' or mysha1 == '' or mycrc == '':
        # YES, GO BACK
        return file,None
    logging.info ('###### GETTING GAME INFORMATION')
    ### THIS IS THE NAME OF THE API WE HAVE TO CALL
    API = "jeuInfos"
    ### INITIALIZE PARAMETERS, STARTING BY THE FIXED ONES (SEE CONFIG)
    params = None
    params = dict(fixParams)
    ### ADD MD5
    params['md5'] = mymd5
    ### ADD SHA1
    params['sha1'] = mysha1
    ### ADD CRC
    params['crc'] = mycrc
    ### INITIQLIZE VARIABLES TO AVOID ACRRY ON VALUES
    response = None
    ### FIRST, TRY TO GET THE ANSWER FRO THE DB, THIS IS DONE SO WE DO NOT CALL THE SCRAPER EVRYTIME IF WE HAVE ALREADY FETCHED INFORMATION FOR THIS PARTICULAR SHA
    response = locateShainDB(mysha1)
    ###logging.info ('######## '+str(response))
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
                logging.error('###### COULD NOT ADD SYSID TO RESPONSE')
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
                updateDB (mysha1,response)
                ### INFORM LOG THAT YOU COULD EVENTUALLY UPDATE GAMEID
                logging.debug ('###### YOU CAN UPDATE GAME ID FOR '+file)
                ### AND RETURN RESPONSE
                return file,response
            else:
                ### YES WE GOT A GAME ID
                logging.debug ('###### GOT A GAME ID FROM DB '+str(response))
                ### SO NOW INITIALIZE GAME PARAMETERS FOR NEW SEARCH , FIRST EMPTY THEN ASSIGN, JUST IN CASE
                gameparams = None
                gameparams = dict(fixParams)
                ### OK, WE GOT A GAME ID, BUT IS IT 0?
                if response['GameID'] !='0':
                    ### NO IT IS NOT, SO WE CAN GO AHEAD AND GET IT
                    logging.debug ('###### CALLING API WITH GAME_ID'+response['GameID'])
                    ### ADD GAMEID TO PARAMETERS
                    gameparams['gameid'] = response['GameID']
                    ### AND GET THE RESPONSE TO THE CALL
                    newresponse = callAPI(fixedURL,API,gameparams,CURRSSID,False,'2','THERE IS A GAME ID HERE')
                    ### CHECK IF WE WENT OVER QUOTA
                    if newresponse == 'QUOTA':
                        logging.debug ('###### QUOTA DONE')
                        ### WE DID, CAN WE TRY CALLING ANONYMOUS?
                        newresponse = None
                        newresponse = callAPI(fixedURL, API, gameparams, CURRSSID,True,'2','NEWRESPONSE IN QUOTA')
                        if newresponse == 'QUOTA':
                            ### NO WE CANNOT
                            return file, 'SKIP'
                    ### SO, DID WE GET A PROPER RESPONSE? (REMEMBER SSUSER NEEDS TO BE THERE)
                    if 'ssuser' in newresponse:
                        ### YES WE DID
                        logging.debug ('###### SSUSER IS IN RESPONSE')
                        ### ASSIGN NEW RESPONSE TO OLD ONE, SO WE DO NOT CONFUSE OURSELVES
                        response = None
                        response = newresponse
                        ### AND UPDATE THE DB WITH THE NEW ANSWER
                        #logging.debug ('###### RESPONSE TO UPDATE '+str(response))
                        updateDB (mysha1,response)
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
            gameparams = dict(fixParams)
            ### AND WE ADD THE GAME ID, WHICH WE SHOULD HAVE. THIS IS TO AVOID TRYING TO UPDATE CHECKSUMS THAT ARE NOT EXISTING IN SITE
            # MODIFY HERE MODIFY HERE
            gameparams['gameid'] = response['jeu']['id']
            ### AND WE CALL THE API
            newresponse = None
            newresponse = callAPI(fixedURL,API,gameparams,CURRSSID,False,'2','FROM UPDATEDATA')
            ### ARE WE OVER THE ALLOWED QUOTA?
            if newresponse == 'QUOTA':
                ### YES
                logging.info ('###### QUOTA DONE, TRYING ANON')
                ### CAN WE TRY TO CALL IT ANONYMOUSLY?
                newresponse = None
                newresponse = callAPI(fixedURL, API, gameparams, CURRSSID,True,'2','QUOTA NEWRESPONSE')
                if newresponse == 'QUOTA':
                    ### NO WE CAN'T
                    logging.info ('###### QUOTA REALLY DONE, NOT UPDATING')
                    ### SO SKIP FILE
                    return file, 'SKIP'
            ### DID WE GET A VALID RESPONSE??? (REMMEBER SSUSER)
            if 'ssuser' in newresponse:
                ### YES WE DID
                response = None
                response = newresponse
                logging.info ('###### GOT UPDATED VERSION FROM API')
                #logging.debug ('###### RESPONSE TO UPDATE '+str(response))
                updateDB (mysha1,response)
                return file,response
    else:
        ### WE COULD NOT LOCATE THE SHA IN DB
        logging.error('###### CACHE DOES NOT EXISTE IN DB FOR ' + file)
        logging.debug('###### CALLING API IN NORMAL MODE')
        ### CALL THE API TO GET AN ANSWER
        response = None
        response = callAPI(fixedURL, API, params, CURRSSID,False,'2','NO SHA IN DB')
        ### ARE WE OVER THE QUOTA?
        if 'QUOTA' in response:
            ### WE ARE, CAN WE CALL ANONYMOUSLY?
            response = None
            logging.debug('###### CALLING API IN ANON MODE')
            response = callAPI(fixedURL, API, params, CURRSSID,True,'2','NO SHA IN DB AND QUOTA')
            if 'QUOTA' in response:
                ### NO WE CAN'T
                return file, 'SKIP'
        ### DID WE GET A PROPER ANSWER? (SSUSER)
        if ('ssuser' not in response) and ('jeu' not in response):
            ### NO WE DID NOT, ADD LOCAL VALUES
            response['file'] = pathtofile + '/' + file.replace("'","\\\'")
            response['localhash'] = mysha1
            response['GameID'] = '0'
            #logging.debug ('###### RESPONSE TO UPDATE '+str(response))
            updateDB (mysha1,response)
        else:
            logging.debug ('###### GOT ANSWER FROM API, UPDATING DB')
            #logging.debug ('###### RESPONSE TO UPDATE '+str(response))
            updateDB (mysha1,response)
    ### SO NOW WE HAVE A RESPONSE, LET'S TREAT IT
    ### WE ASSUME THE ROM WAS NOT FOUND
    foundRom = False
    ### IS THERE AN ERROR IN RESPONSE?
    logging.debug ('###### RESPONSE IS '+str(response))
    if 'QUOTA' in response:
        logging.error ('###### GONE OVER QUOTA')
        return file,'SKIP'
    if 'Error' in response.keys():
        ### YES THERE IS
        logging.debug('###### API GAVE ERROR BACK, CREATING EMPTY DATA '+str(response))
        ### SO WE CREATE AN EMPTY ANSWER AND RETURN IT
        return file,{'abspath': pathtofile,
                'localpath': pathtofile+'/'+file,
                'localhash': mysha1.upper(),
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
    response['localhash'] = mysha1.upper()
    response['abspath'] = pathtofile
    ### AND RETURN IT
    return file,response


def scrapeRoms`(CURRSSID):
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
                logging.info ('###### SKIPPING SYSTEM')
    logging.info ('----------------- ALL DONE -------------------')

def updateGameID (file,sha,gameid):
    if gameid != '':
        logging.info ('###### UPDATING GAME ID IN DB FOR '+sha+' WITH VALUE '+str(gameid))
        response = "{'localhash': '"+sha+"', 'GameID': '"+str(gameid)+"', 'file': '"+file.replace("'","\\\'")+"', 'Error': 'Erreur : Rom/Iso/Dossier non trouvee ! - UPDATED '}"
    else:
        logging.info ('###### ID TO UPDATE IS EMPTY, SO WILL BE THE DB')
        response = ''
    #logging.debug ('###### RESPONSE TO UPDATE '+str(response))
    updateDB(sha,response)


def transformFilename(fileName):
    logging.info ('###### RECEIVED ORIGINAL FILENAME '+fileName)
    ## 2 - Name removing underscores by spaces
    fileName = fileName.replace('_',' ')
    ## 2 - Name removing versions and [] and ()
    fileName = re.sub('\(.*\)|\[.*\]|[V|v]\d.\d.*','',fileName).strip()
    ## 3 - moving 'THE' at the beggining to the end of the string
    if fileName.upper().find('THE ') == 0:
        fileName = fileName[4:]+', The'
    ## 4 - Name by splitting camel string (TestOne = Test One)
    matches = re.finditer('.+?(?:(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|$)',fileName)
    if matches:
        fileName =''
        for m in matches:
            fileName = fileName+m.group(0)+' '
        fileName=fileName.strip()
    logging.info ('###### RETURNING CONVERTED FILENAME '+fileName)
    return fileName


def chkNamesMatch(a,b):
    logging.debug ('###### CHECKING ['+str(a)+'] WITH ['+str(b)+']')
    if a == b:
        return True
    else:
        return False

def replace_roman_numerals(s):
    ret = s.replace(' I ',' 1 ')
    ret = ret.replace(' II ',' 2 ')
    ret = ret.replace(' III ',' 3 ')
    ret = ret.replace(' IV ',' 4 ')
    ret = ret.replace(' V ',' 5 ')
    ret = ret.replace(' VI ',' 6 ')
    ret = ret.replace(' VII ',' 7 ')
    ret = ret.replace(' VIII ',' 8 ')
    ret = ret.replace(' IX ',' 9 ')
    ret = ret.replace(' X ',' 10 ')
    ret = ret.replace(' XI ',' 11 ')
    ret = ret.replace(' XII ',' 12 ')
    ret = ret.replace(' XIII ',' 13 ')
    ret = ret.replace(' XIV ',' 14 ')
    ret = ret.replace(' XV ',' 15 ')
    return ret

### CHK - ORIG
def fuzzyMatch (a,b):
    aparts = a.split(' ')
    bparts = b.split(' ')
    mparts = 0
    for bpart in bparts:
        for apart in aparts:
	    if apart == bpart:
                mparts = mparts + 1
                continue
    if mparts >= len(bparts) and mparts >= len(aparts):
        logging.debug ('###### WHOLE MATCH FOUND '+a+' == '+b+' PARTS '+str(mparts))
    else:
        logging.debug ('###### FOUND '+str(mparts)+' OF '+str(len(bparts)))
    return False



def gameNameMatches(orig,chkname):
    ## Convert non ascii codes to normal codes
    for chk in chkname['noms']:
        logging.debug('##### '+str(chk))
        chk = chk['text'].encode('ascii', 'ignore')
        ### 'NN TODO
        logging.debug ('####### NAME GRABBED - NAME INFERRED')
        if chkNamesMatch(chk.upper(),replace_roman_numerals(orig.upper())):
            logging.info ('###### NAME MATCHES')
            return True
        if chkNamesMatch(chk.upper().replace('!',''),orig.upper()):
            logging.info ('###### NAME MATCHES')
            return True
        if chkNamesMatch(chk.upper().replace('.',''),orig.upper()):
            logging.info ('###### NAME MATCHES')
            return True
        if chkNamesMatch(chk.upper(),orig.upper()):
            logging.info ('###### NAME MATCHES')
            return True
        if chkNamesMatch(chk.upper(),re.sub('\(.\)','',orig.upper()).strip()):
            logging.info ('###### NAME MATCHES')
            return True
        if chkNamesMatch(chk.upper(),re.sub('\[.\]','',orig.upper()).strip()):
            logging.info ('###### NAME MATCHES')
            return True
        if chkNamesMatch(chk.upper(),re.sub('\(.\)\[.\]','',orig.upper()).strip()):
            logging.info ('###### NAME MATCHES')
            return True
        if chkNamesMatch(chk.upper(),re.sub('\[.\]\(.\)','',orig.upper()).strip()):
            logging.info ('###### NAME MATCHES')
            return True
        if chkNamesMatch(chk.upper(),orig.replace(',','').upper()):
            logging.info ('###### NAME MATCHES')
            return True
        if chkNamesMatch(chk.upper(),orig.replace(' AND ',' & ').upper()):
            logging.info ('###### NAME MATCHES')
            return True
        if chkNamesMatch(chk.upper(),orig.replace(' & ',' AND ').upper()):
            logging.info ('###### NAME MATCHES')
            return True
        if chkNamesMatch(chk.replace(' - ',' ').upper(),orig.upper()):
            logging.info ('###### NAME MATCHES')
            return True
        if chkNamesMatch(chk.upper(),orig.replace(' Dr ',' Dr. ').upper()):
            logging.info ('###### NAME MATCHES')
            return True
        if chkNamesMatch(chk.upper(),orig.replace(':','-').upper()):
            logging.info ('###### NAME MATCHES')
            return True
        if chkNamesMatch(chk.upper(),orig.replace(':',' -').upper()):
            logging.info ('###### NAME MATCHES')
            return True
        if chkNamesMatch(chk.upper(),orig.replace(':',' - ').upper()):
            logging.info ('###### NAME MATCHES')
            return True
        if chkNamesMatch(chk.upper(),orig.replace(':',' -').upper()):
            logging.info ('###### NAME MATCHES')
            return True
        if chkNamesMatch(chk.upper(),orig.upper()+' THE'):
            logging.info ('###### NAME MATCHES')
            return True
        if fuzzyMatch(chk,orig):
            logging.info ('###### NAME MATCHES')
            return True          
        matches = re.search('\w*\d',orig)
        if matches:
            splitnum = matches.group(0)
            newint = re.sub (r'(\d)',r' \1',splitnum)
            splitnum = re.sub('\w*\d',newint,orig)
            if chkNamesMatch(chk.upper(),splitnum.upper()):
                logging.info ('###### NAME MATCHES')
                return True
            if chkNamesMatch(chk.upper(),splitnum.upper()+' THE'):
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
    callURL2 = 'http://mamedb.blu-ferret.co.uk/game/'+name+'/'
    callURL3 = 'http://adb.arcadeitalia.net/dettaglio_mame.php?game_name=' + name
    logging.info ('###### GETTING ARCADE NAME IN URL '+callURL)
    namefromcsv = nameFromArcadeCSV(name)
    if namefromcsv != '':
        return namefromcsv
    try:
        response = callAPIURL(callURL) 
        gamename = re.findall("<title>(.*?)<\/title>", response)[0].replace('Game Details:  ','').replace(' - mamedb.com','')
        logging.info ('###### FOUND GAME IN MAMEDB '+gamename)
        return gamename
    except:
        logging.error('###### COULD NOT GET ARCADE NAME FROM MAMEDB')
        logging.info('###### TRYING WITH BLU FERRET IN URL '+callURL2)
        try:
            response = callAPIURL(callURL2) 
            gamename = re.findall("\<title\>Game Details:  (\w*).*\<\/title\>", response[0])
            logging.info ('###### FOUND GAME IN BLU FERRET '+gamename)
            return gamename
        except:
            logging.error ('###### COULD NOT GET NAME FROM BLU FERRET')
            logging.info('###### TRYING WITH ARCADE ITALIA IN URL '+callURL3)
            try:
                response = callAPIURL(callURL3) 
                gamename = re.findall("<title>(.*?)<\/title>", response)[0].replace(' - MAME machine','').replace(' - MAME software','')
                gamename = gamename.replace(' - MAME machin...','')
                if gamename.upper()=='ARCADE DATABASE':
                    logging.error ('###### COULD NOT GET NAME FROM ARCADE ITALIA')
                    gamename = ''
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

def isSystemOk(jsonsys,gamesys):
    if jsonsys == gamesys:
        logging.debug ('###### SYSTEMS ARE IDENTICAL')
        return True
    msxsystems = ('113','118','116','117')
    if jsonsys in msxsystems and gamesys in msxsystems:
        return True
    if jsonsys in arcadeSystems and gamesys in arcadeSystems:
        return True
    return False

def findMissing():
    ### GET ALL SYSTEMS, THIS IS DONE TO HAVE A LIST OF ARCADE RELATED SYSTEMS
    systems = getAllSystems(CURRSSID)
     ### read missing file and try to get game by name
    matchPercent = 95
    if not os.path.isfile(missing):
        logging.error('####### COULD NOT FIND FILE '+str(missing)+' STOPPING EXECUTION')
        sys.exit()
    with open(missing) as csv_file:
        csv_reader = csv.reader(csv_file, delimiter='|')
        line_count = 0
        newGameId = 0
        for row in csv_reader:
            newline =''
            ### clean previous done
            ### CHECK IF THERE IS A SEVENTH COLUMN, WHICH WOULD BE THE GAMEID TO INSERT
            newmode = False
            sha = str(row[2])
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
            logging.info('###### IS THIS A NEW MODE '+str(newmode)+' --- New Game ID = '+str(newGameId))
            if newGameId == 0 and not newmode:
                updateGameID (row[1],sha,'0')
                newline = row[0]+'|'+row[1]+'|'+sha+'|'+row[3]+'|'+row[4]+'|'+row[5]+'|FORCED_ID'
                system=row[0]
                logging.info ('###### DOING RESEARCH FOR '+row[1]+' IN SYSTEM '+str(system))
                if str(system) not in arcadeSystems:
                    searchSystems=[system]
                    filename=(row[1][row[1].rfind('/')+1:row[1].rfind('.')]).replace('_',' ')
                    ### GBA Exception
                    #if str(system) == '12':
                    #    filename = filename[7:]
                else:
                    filename=row[1][row[1].rfind('/')+1:row[1].rfind('.')]
                    filename = getArcadeName(filename)
                    if filename == '':
                        filename = 'UNKNOWN'
                    newline = newline +'|'+filename
                    searchSystems = system
                logging.info ('###### WILL SEARCH IN '+str(searchSystems))
                myGameName = transformFilename(filename)
                if myGameName !='':
                    myParams = None
                    myParams = dict(fixParams)
                    logging.info ('###### STRIPPED TO '+myGameName)
                    keepon = True
                    found = False
                    API= 'jeuRecherche'
                    full = True
                    returnValue = {}
                    ### TODO: VERIFY SPLITS THINGS AND FINAL NAMES
                    tries = 3
                    while tries > 0 and not found:
                        ## Try with whole name first, if not with partial
                        if tries == 1:
                            gameSearch = myGameName.replace(' - ',' ').replace(':','').split(' ')[0]
                        else:
                            gameSearch = myGameName
                        if tries == 2:
                            gameSearch = replace_roman_numerals(gameSearch)
                        logging.debug('####### LENGTH OF GAMESEARCH IS '+str(len(gameSearch))+'='+str(gameSearch))
                        if len(gameSearch)<4 and tries == 1:
                            try:
                                gameSearch = gameSearch+' '+myGameName.split(' ')[1] #SI son menos de 3 caracteres anado segunda palabra
                            except:
                                logging.error ('###### IMPOSSIBLE TO LOOK UP '+gameSearch+', IT HAS LESS THAN 4 CHARACTERS WHICH IS THE MINIMUM NEEDED')
                            logging.debug('####### LENGTH OF GAMESEARCH IS '+str(len(gameSearch)))
                            if len(gameSearch)<8:
                                try:
                                    gameSearch = gameSearch+' '+myGameName.split(' ')[2] #SI son menos de 3 caracteres anado segunda palabra
                                except:
                                    logging.error ('###### IMPOSSIBLE TO LOOK UP '+gameSearch+', IT HAS LESS THAN 7 CHARACTERS IN 2 WORDS WHICH IS THE MINIMUM NEEDED')
                        gameSearch=gameSearch.replace(',','')
                        myParams['recherche']=gameSearch
                        if myParams['recherche'].upper() == 'EAMON':
                                #myeamonsearch=''
                                #myeamontitle = myGameName.split(' ')
                                #logging.debug ('###### I HAVE '+str(len(myeamontitle))+' WORDS TO LOOK')
                                #for i in range(3,len(myeamontitle)):
                                #    myeamonsearch = myeamonsearch + myeamontitle[i]+'+'
                                myParams['recherche']=myParams['recherche']+' '+myGameName.split(' ')[1]
                                logging.debug ('###### THIS IS A EAMON GAME - SO I COMPLETE THE NAME '+myParams['recherche'])
                                #ansretries = ansretries - 1
                                #if len(myGameName.split(' '))>3:
                                #    myParams['recherche'] = myParams['recherche'] + ' ' + myGameName.split(' ')[3]
                                #if len(myGameName.split(' '))>4:
                                #    myParams['recherche'] = myParams['recherche'] + ' ' + myGameName.split(' ')[4]
                        found = False
                        systemPos = 0
                        myParams['systemeid']=str(system)
                        ## VOY A BUSCAR LOS TRES PRMEROS CARACTERES, Y DESPUES HACER UNA LOGICA EN EL MATCH DE CUANTOS CARACTERES IGUALES HAY, NO LOS 4 PRIMEROS
                        logging.info('###### LOOKING SCRAPER FOR '+myParams['recherche']+ ' FOR SYSTEM '+str(system))
                        returnValue = callAPI(fixedURL,API,myParams,0,False,'2',' SYSTEM SOMETHING')
                        logging.debug (returnValue)
                        if 'jeux' in returnValue.keys():
                            if len(returnValue['jeux']) > 1:
                                position = 0
                                for game in returnValue['jeux']:
                                    thisGameID = returnValue['jeux'][position]['id']
                                    if gameNameMatches(myGameName,game):
                                        if isSystemOk(game['systeme']['id'],str(system)):
                                            updateGameID (row[1],sha,thisGameID)
                                            found = True
                                            continue
                                        else:
                                            logging.debug ('###### FOUND MATCH NOT OF SAME SYSTEM')
                                    if not found:
                                    	for gameName in game['noms']:
                                            if isSystemOk(game['systeme']['id'],str(system)):
                                                newline = newline + '|' + gameName['text']
                                                newline = newline + '|' + thisGameID
                                                position = position+1
                                            else:
                                                logging.debug ('###### RETURNED VALUE NOT OF SAME SYSTEM')
 
                            else:
                                if str(returnValue['jeux'][0]) != '{}':
                                    game = returnValue['jeux'][0]
                                    thisGameID = returnValue['jeux'][0]['id']
                                    if gameNameMatches(myGameName,game):
                                        if isSystemOk(game['systeme']['id'],str(system)):
                                            updateGameID (row[1],sha,thisGameID)
                                            found = True
                                            logging.info ('###### FOUND MISSING INFO FOR '+filename+' SHA '+sha)
                                        else:
                                            logging.debug ('###### MATCH NOT OF SAME SYSTEM')
                                    else:
                                        for gameName in game['noms']:
                                            if isSystemOk(game['systeme']['id'],str(system)):
                                                newline = newline + '|' + gameName['text']
                                                newline = newline + '|' + thisGameID
                                            else:
                                                logging.debug ('###### RETURNED VALUE NOT OF SAME SYSTEM')
                        tries = tries - 1
                    if not found:
                        logging.info ('###### COULD NOT FIND MISSING INFO FOR '+filename)
                        writeNewMissing(newline)
                else:
                    logging.info ('###### COULD NOT FIND MISSING INFO FOR '+filename)
                    writeNewMissing(newline)
            else:
                if newGameId !=0:
                    updateGameID (row[1],sha,newGameId)
                logging.info ('###### UPDATED FORCED ID OF '+row[1]+' TO '+str(newGameId))
        logging.info ('###### FINISHED LOOKING FOR MISSING ROMS')

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
        logging.debug ('###### FOUND HASH='+sha+' PATH ='+file+' IMAGE='+image+' VIDEO='+video)
        if sha !='' and file != '':
            if image != '':
                try:
                    os.remove(image)
                    logging.info ('###### DELETED IMAGE '+image)
                except Exception as e:
                    logging.error ('###### COULD NOT DELETE '+image+' '+str(e))
            if video != '':
                try:
                    os.remove(video)
                    logging.info ('###### DELETED VIDEO '+video)
                except Exception as e:
                    logging.error ('###### COULD NOT DELETE '+video+' '+str(e))
            updateGameID (file,sha,'')
            deleteHashCache(file) 
            logging.info ('###### REMOVED '+file+' WITH HASH '+sha)


def multiDisk(filename):
    checkreg = '\([P|p][A|a][R|r][T|t][^\)]*\)|\([F|f][I|i][L|l][E\e][^\)]*\)|\([D|d][I|i][S|s][K\k][^\)]*\)|\([S|s][I|i][D|d][E|e][^\)]*\)|\([D|d][I|i][S|s][C|c][^\)]*\)|\([T|t][A|a][P|p][E|e][^\)]*\)|\([F|f][I|i][L|l][E|e][^\)]*\)'
    matchs = re.search(checkreg,filename)
    return matchs

def multiCountry(filename):
    checkreg = '\([E|e][U|u][R|r][O|o][P|p][E|e][^\)]*\)|\([U|u][S|s][A|a][^\)]*\)|\([J|j][A|a][P|p][A|a][N|n][^\)]*\)|\([E|e][U|u][R|r][A|a][S|s][I|i][A|a][^\)]*\)'
    matchs = re.search(checkreg,filename)
    if not matchs:
        checkreg = '\([S|s][P|p][A|a][I|i][N|n][^\)]*\)|\([F|f][R|r][A|a][N|n][C|c][E|e][^\)]*\)|\([G|g][E|e][R|r][M|m][A|a][N|n][Y|y][^\)]*\)'
        matchs = re.search(checkreg,filename)
    if not matchs:
        checkreg = '\([E|e][N|n][G|g][^\)]*\)|\([R|r][U|u][^\)]*\)|\([E|e][^\)]*\)|\([U|u][^\)]*\)|\([J|j][^\)]*\)|\([S|s][^\)]*\)|\([N|n][^\)]*\)|\([F|f][^\)]*\)|\([J|j][P|p][^\)]*\)|\([N|n][L|l][^\)]*\)|\([K|k][R|r][^\)]*\)|\([E|e][S|s][^\)]*\)'
        matchs = re.search(checkreg,filename)
    return matchs

def multiVersion(filename):
    checkreg = '[V|v]\d*\.\w*'
    matchs = re.search(checkreg,filename)
    if not matchs:
        checkreg = '\([H|h][A|a][C|c][K|k][^\)]*\)|\([P|p][R|o][T|t][O|o][T|t][Y|y][P|p][E|e][^\)]*\)|\([D|d][E|e][M|m][O|o][^\)]*\)|\([S|s][A|a][M|m][P|p][L|l][E|e][^\)]*\)|\([B|b][E|e][T|t][A|a][^\)]*\)'
        matchs = re.search(checkreg,filename)
    return matchs

#### NOT USED YET, NEED TO CHECK IF IT MAKES SENSE
def specialLabel(filename):
    checkreg = '^\([D|d][I|i][S|s][K\k][^\)]*\)|\([S|s][I|i][D|d][E|e][^\)]*\)|\([D|d][I|i][S|s][C|c][^\)]*\)|\([T|t][A|a][P|p][E|e][^\)]*\)|\([F|f][I|i][L|l][E|e][^\)]*\)'


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
        logging.info ('###### FOUND GAMELIST IN ' +glist)
        cleanGameList(glist)
        logging.info ('###### FINISHED CLEANING '+glist)
    else:
        logging.error ('###### COULD NOT FIND SYSTEM '+system)
        sys.exit(0)

def updateFile(path,localSHA,localCRC,localMD):
    ### We need to rename the file
    ### if succesfull we need to update the DB
    logging.debug ('###### UPDATE FILE '+path)
    filepath = path[:path.rindex('/')+1]
    filext = path[path.rindex('.'):]
    localfile,thisGame = getGameInfo(0,path,path[path.rindex('/')+1:],localMD,localSHA,localCRC,0)
    if 'ssuser' not in str(thisGame):
        ### The game information is not complete, better not to process
        print 'SKIPPING '+localSHA
        return
    else:
        matchs = multiDisk(path)
        vmatchs = multiVersion(path)
        cmatchs = multCountry(path)
        if cmatchs:
            destFile = filepath+thisGame['jeu']['nom']+' '+cmatchs.group(0).replace('_',' ')
        else:
            destFile = filepath+thisGame['jeu']['nom']
        if matchs:
            destFile = (destFile+' ('+matchs.group(0).replace('_',' ')+')')
        if vmatchs:
            destFile = (destFile+' ('+vmatchs.group(0).replace('_',' ')+')'+filext)
        else:
            destFile = (destFile+filext)
        destFile = destFile.encode('ascii', 'ignore')
        if destFile != path:
            res = updateDBFile(path,destFile)
            if res == 0:
                ### Rename file
                try:
                    os.rename(path,destFile)
                except:
                    res = updateDBFile(destFile,path)

def renameFiles():
    logging.info ('###### - STARTING FILE RENAMING PROCESS')
    ### Exclude directories, or directories where you do not wish to rename files (retropie, etc..)
    excludeDirs = ['/retropie/','/arcade/','/neogeo/','/retropiemenu/']
    ### Connect to DB to get all files
    hashes = getAllGamesinDB()
    procfiles = 0
    logging.info ('###### - FOUND '+str(len(hashes))+' HASHES IN DB')
    for hash in hashes:
        thisfile = hash[0]
        sha1offile = hash[1]
        crcoffile = hash[2]
        mdoffile = hash[3]
        logging.info ('###### - START FILE '+thisfile)
        if thisfile.count('/') > 1:
            logging.debug ('###### - IT HAS MORE THAN 2 /')
            process = True
            for excdir in excludeDirs:
                if excdir in thisfile:
                    process = False
                    logging.debug ('###### - BUT IT IS IN AN EXCLUDED DIRECTORY')
            if not os.path.isfile(thisfile):
                ### File no longer exists, let's cleanup the DB
                logging.debug ('###### - BUT FILE DOES NOT EXIST ANYMORE')
                process = False
                deleteHashFromDB (thisfile)
            if process:
                logging.debug ('###### - EVERYTHING OK, WE CAN PROCEED')
                procfiles = procfiles + 1
                ### Files landing here need to be updated
                updateFile(thisfile,sha1offile,crcoffile,mdoffile)
        else:
            ### Files landing here need to be removed        
            deleteHashFromDB (thisfile)
    logging.info ('###### - FINISHED FILE RENAMING PROCESS - TOTAL FILES PROCESSED '+str(procfiles))


if dbRename:
    ### Get all games from DB and rename filenames
    renameFiles()
    scrapeRoms(CURRSSID)
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
    logging.info ('###### FINSHED LOOKING FOR MISSING GAMES')
    sys.exit(0)
    scrapeRoms(CURRSSID)

else:
    ### THIS PROCEDURE WILL GO THROUGH ALL ROMS DIRECTORIES IN SYSTEM CONFIGURATION AND TRY TO SCRAPE THEM
    scrapeRoms(CURRSSID)

sys.exit(0)
