# coding: utf-8

from shutil import copyfile
import csv
import ast
import requests
import json
import xml.etree.ElementTree as ET
import glob
import os
import hashlib
import zlib
import sys
import subprocess
import logging
import random
import urllib
from zipfile import ZipFile
from xml.dom import minidom
import pymysql as mysql
from PIL import Image
from datetime import datetime, time
from time import sleep
from pymediainfo import MediaInfo
import argparse
import re
import config
import shutil

### Parse arguments first
### Arguments are :
### --missing: parse missing file and try to scrape based on name, also parses extra missing info if file has it
### --update: refresh information from site, redownloads images
### --clean: removes all information from a system in the local DB, needs to have system specified
### --rename: will look into the game name as downloaded from the site and rename the file accordingly

parser = argparse.ArgumentParser(description='ROM scraper, get information of your roms from screenscraper.fr')
parser.add_argument('--update', help='Update local DB information from screenscraper',action='store_true')
parser.add_argument('--clean', help='Clean a system from the DB, deletes all records from files', action='store_true')
parser.add_argument('--rename', help='Rename files to match the actual game name in the DB', action='store_true')
parser.add_argument('--importgames', help='Start importing DB at gameid',nargs=2)
parser.add_argument('--localdb', help='Use only local DB for scraping (except media)', action='store_true')
parser.add_argument('--getroms', help='Get new roms starting from ID and ending in ID', nargs=2)
parser.add_argument('--getnewmedia', help='Get new media, give end page number as parameter', nargs=1)
parser.add_argument('--getnewinfo', help='Get new game infos, give end page number as parameter', nargs=1)
parser.add_argument('--sort', help='Sorts all your roms and stores them by system in a new directroy structure',nargs=1)
parser.add_argument('--config', help='emulation station configuration file to read',nargs=1)
parser.add_argument('--log', help='logfile output, by default sv2log.txt',nargs=1)
parser.add_argument('--listmissing', help='creates a list of missing games per system on the file of your choice',nargs=1)
parser.add_argument('--nobezel', help='Skips bezel downloads',action='store_true')
parser.add_argument('--nomarquee', help='Skips marquee downloads',action='store_true')
parser.add_argument('--fixwhd', help='Fix WHD XML files and updates filenames',action='store_true')
parser.add_argument('--debug', help='Set log to DEBUG mode',action='store_true')

argsvals = vars(parser.parse_args())


try:
    logfile = argsvals['log'][0]
except:
    logfile = 'sv2log.txt'

try:
    loglevel = argsvals['debug']
except:
    loglevel = False

if loglevel:
    logtype = logging.DEBUG
else:
    logtype = logging.INFO

try:
    logging.basicConfig(filename=logfile, filemode='a',
                        format='%(asctime)s - %(process)d - %(name)s - %(levelname)s - %(message)s',
                        level=logtype)
    logging.debug("###### LOGGING SERVICE STARTED")
except Exception as e:
    logging.debug('###### ERROR CREATING LOG '+str(e))

logging.info ('###### LOGGING LEVEL SET TO '+str(logtype))

global sysconfig 

try:
    sysconfig = argsvals['config'][0]
except:
    sysconfig = config.sysconfig

logging.info ('###### CONFIGURATION FILE '+sysconfig)

try:
    sortroms = argsvals['sort'][0]
except:
    sortroms = ''

logging.info ('###### SORT ROMS '+str(sortroms))


global nobezel

try:
    nobezel = argsvals['nobezel']
except:
    nobezel = False

logging.info ('###### NO BEZELS '+str(nobezel))

global nomarquee

try:
    nomarquee = argsvals['nomarquee']
except:
    nomarquee = False

logging.info ('###### NO MARQUEES '+str(nomarquee))


try:
    whdfix = argsvals['fixwhd']
except:
    whdfix = False

logging.info ('###### FIX WHDLOAD FILE '+str(whdfix))

localdb = argsvals['localdb']
logging.info ('###### LOCAL DB '+str(localdb))
update = argsvals['update']
logging.info ('###### UPDATE '+str(update))
dbRename = argsvals['rename']
logging.info ('###### RENAME FILES '+str(dbRename))
cleanSystem = argsvals['clean']
logging.info ('###### CLEAN SYSTEM '+str(cleanSystem))

try:
    startid= argsvals['importgames'][0]
    migrateDB = True
    try:
        endid = argsvals['importgames'][1]
    except:
        endid = 0
except:
    migrateDB = False

logging.info ('###### IMPORT GAMES '+str(migrateDB))


try:
    pageid = argsvals['getnewmedia'][0]
    newmedia = True
except:
    newmedia = False

logging.info ('###### GET NEW MEDIA '+str(newmedia))

try:
    pageid = argsvals['getnewinfo'][0]
    newinfo = True
except:
    newinfo = False

logging.info ('###### GET NEW INFO '+str(newmedia))


try:
    startid = argsvals['getroms'][0]
    endid = argsvals['getroms'][1]
    getROMS = True
except:
    getROMS = False

logging.info ('###### GET ROMS '+str(getROMS))


try:
    listMissingFile = argsvals['listmissing'][0]
    if os.path.isfile(listMissingFile):
        os.remove(listMissingFile)
    listMissing = True
except Exception as e:
    listMissing = False
    listMissingFile = ''

logging.info ('###### LIST MISSING '+str(listMissing)+' TO FILE '+str(listMissingFile))


UPDATEDATA = update

tmpdir = config.tmpdir


def initiateDBConnect():
    try:
        thisdb = mysql.connect(
        host=config.dbhost,
        user=config.dbuser,
        passwd=config.dbpasswd,
        database=config.database
        )
        return thisdb
    except Exception as e:
        logging.error ('###### CANNOT CONNECT TO DATABASE '+config.dbhost+'/'+config.database+' Error:'+str(e))
        logging.error ('###### PLEASE MAKE SURE YOU HAVE A DATABASE SERVER THAT MATCHES YOUR CONFIGURATION')
        print (str(e))
        sys.exit()

global mydb
mydb = initiateDBConnect()

fixedURL = "https://www.screenscraper.fr/api"

testAPI = "ssuserInfos"

fixParams = {'devid': config.devid,
             'devpassword': config.devpassword,
             'softname': config.softname,
             'ssid':'',
             'sspassword': config.sspass,
             'output': 'json'}

CURRSSID = 0

lastfile = ''

lastresult = ''

## QUOTA LIMITER FOR V2CALLS
VTWOQUOTA = False

### INSERT THE EXTENSIONS YOU DO NOT WANT TO HAVE ZIPPED IN THE LIST BELOW
donotcompress = config.donotcompress

BIOSDIR = config.BIOSDIR
UNKDIR = config.UNKDIR

class Game:
    ### THIS IS THE GAME CLASS, IT WILL HOLD INFORMATION OF EACH SCRAPED GAME
    def __init__(self, jsondata):
        if 'localpath' not in jsondata.keys():
            logging.debug ('###### NO LOCALPATH DEFINED - CANNOT CREATE GAME')
            return None
        try:
            file = jsondata['abspath']+'/'+jsondata['localpath']
        except Exception as e:
            logging.error ('###### COULD NOT CREATE LOCALPATH FOR GAME '+str(e))
        ### CAN WE COMPRESS FILE?? THIS IS DONE IN ORDER TO SAVE SPACE
        if file[file.rfind('.'):].lower() not in donotcompress:
            ### YES WE CAN ZIP FILE
            logging.debug('###### GOING TO ZIP FILE')
            zippedFile = convertToZip(file)
        else:
            ### THIS EXTENSION HAS BEEN REQUESTED NOT TO BE ZIPPED
            logging.debug ('###### REQUESTED NOT TO ZIP EXTENSION')
            zippedFile = file
        self.path = zippedFile
        logging.debug ('###### DOING NAME')
        self.name = getGameName(jsondata,self.path)
        logging.debug ('###### DOING DESCRIPTION')
        self.desc = getDesc(jsondata)
        logging.debug ('###### DOING IMAGES')
        self.image = getMedia(jsondata['jeu']['medias'],
                              jsondata['abspath'],
                              jsondata['localpath'],
                              jsondata['localhash'],
                              zippedFile)
        logging.debug ('###### DOING VIDEOS')
        self.video = getVideo(jsondata['jeu']['medias'],
                              jsondata['abspath'],
                              jsondata['localpath'],
                              jsondata['localhash'])
        self.marquee = getMarquee(jsondata['jeu']['medias'],
                              jsondata['abspath'],
                              jsondata['localpath'],
                              jsondata['localhash'],
                              zippedFile)
        self.thumbnail = ''
        logging.debug ('###### GOING TO GET RATING')
        self.rating = getRating(jsondata)
        logging.debug ('###### GOING TO GET RELEASE DATE')
        self.releasedate = getDate(jsondata)
        logging.debug ('###### GOING TO GET EDITOR/DEVELOPER')
        self.developer = ''
        try:
            if 'editeur' in jsondata['jeu'].keys:
                self.publisher = jsondata['jeu']['editeur']
            else:
                self.publisher =''
        except:
            self.publisher =''
        self.genre = ''
        self.players = ''
        self.playcount = ''
        self.lastplayed = ''
        self.hash = jsondata['localhash']
        logging.debug ('###### FINISHED CREATING GAME INSTANCE')



    def getXML(self):
        if self is not None:
            logging.debug('###### GAME OBJECT '+str(self))
            gameNode = ET.Element('game')
            attrs = vars(self)
            logging.debug('###### GAME ATTRIBUTES '+str(attrs))
            for attr in attrs:
                try:
                    attrs[attr].decode('utf-8')
                except:
                    logging.error('###### NOT UTF-8')
                    sys.exit()
                subEl = ET.SubElement(gameNode, attr)
                subEl.text = attrs[attr]
            return gameNode
        else:
            return None

def queryDB(sql,values,directCommit,thisDB,logerror=False,retfull=False):
    logging.debug ('+++++++ '+sql)
    logging.debug ('+++++++ '+str(values))
    mycursor = getDBCursor(thisDB)
    if mycursor:
        logging.debug('###### GOT A CURSOR FOR THE DB')
        try:
            if 'SELECT' in sql:
                logging.debug('####### IS A SELECT QUERY')
                try:
                    mycursor.execute(sql, values)
                    myresult = mycursor.fetchall()
                    if logerror:
                        logging.error ('@@@@@@@@@@ '+str(mycursor._last_executed))
                    #logging.debug ('@@@@@@@@@@ '+str(mycursor._last_executed))
                except Exception as e:
                    logging.error ('###### COULD NOT EXECUTE SELECT QUERY '+str(e))
                    #logging.debug ('@@@@@@@@@@ '+str(mycursor._last_executed))
                    mycursor.close()
                    return None,False
                if mycursor.rowcount == 0:
                    logging.debug ('###### COULD NOT FIND IN THE DB')
                    mycursor.close()
                    return None,False
                else:
                    if mycursor.rowcount == 1:
                        logging.debug ('###### COULD FIND ONE RESULT '+str(myresult[0]))
                        if not retfull:
                            mycursor.close()
                            return myresult[0][0],True
                        else:
                            mycursor.close()
                            return myresult[0],True
                    else:
                        logging.debug ('###### FOUND SEVERAL RESULTS')
                        mycursor.close()
                        return myresult,True
            else:
                logging.debug('####### IT IS NOT A SELECT QUERY')
                try:
                    mycursor.execute(sql, values)
                    logging.debug('####### QUERY EXECUTED PROPERLY')
                    if logerror:
                        logging.error ('@@@@@@@@@@ '+str(mycursor._last_executed))
                    #logging.debug ('@@@@@@@@@@ '+str(mycursor._last_executed))
                    mycursor.close()
                except Exception as e:
                    logging.error ('###### INNER - COULD NOT EXECUTE QUERY '+str(e))
                    logging.error ('###### SQL '+str(sql))
                    logging.error ('###### VALUES '+str(values))
                    ###logging.error ('@@@@@@@@@@ '+str(mycursor._last_executed))
                    mycursor.close()
                    return None,False
                if directCommit and not migrateDB:
                    thisDB.commit()
                #logging.debug('####### AND I COMMITTED')
            return None,True
        except Exception as e:
            logging.error ('###### OUTER - COULD NOT EXECUTE QUERY '+str(e))    
            return None,False
    else:
        logging.error ('###### COULD NOT CREATE CURSOR FOR DB')
        return None,False


def getDBCursor(theDB):
    global mydb
    connected = False
    while not connected:
        logging.debug ('###### TRYING TO CONNECT')
        try:
            thiscursor = theDB.cursor()
            connected = True
            logging.debug ('###### CONNECTED SUCCESFULLY')
        except Exception as e:
            logging.error ('###### CANNOT CONNECT TO DB - '+str(e))
            logging.error ('###### WAITING AND RETRYING')
            try:
                theDB.close()
                sleep(60)
                mydb = initiateDBConnect()
                thiscursor = mydb.cursor()
            except Exception as e:
                logging.error ('###### CANNOT RECONNECT TO DB '+str(e))
    return thiscursor

def getArcadeSystems():
    arcsys = []
    arcadeSystemsQ = queryDB('SELECT id FROM systems WHERE TYPE=%s',('arcade',),False,mydb)
    for arcadesys in arcadeSystemsQ[0]:
        arcsys.append(str(arcadesys[0])) 
    arcsys.append('75')
    return arcsys

def getGameName(jsondata,path):
    if 'noms' in jsondata['jeu']:
        name = None
        names = []
        if not isinstance(jsondata['jeu']['noms'],dict):
            logging.debug ('###### NOT A DICT SO CONVERTING '+str(jsondata['jeu']['noms'][0]))
            for a in jsondata['jeu']['noms']:
                b = a.values()
                names.append({'region':b[1],'text':b[0]})
            logging.debug ('###### CONVERTED '+str(names))
        else:
            if 'region' not in str(jsondata['jeu']['noms']):
                logging.debug ('###### SEEMS LIKE A V1 DICTIONARY')
                for item in jsondata['jeu']['noms'].items():
                    names.append({'region':item[0],'text':item[1]})
            else:
                names = jsondata['jeu']['noms'] 
            logging.debug ('###### SEEMS TO BE A PROPER DICTIONARY')
        logging.debug ('####### NAMES '+str(names))
        for nom in names:
            logging.debug ('###### LOOKING FOR NAMES '+str(nom)+' TYPE '+str(type(nom)))
            if 'ss' in nom['region']:
                logging.debug ('###### FOUND SCREEN SCRAPER NAME')
                name = nom['text'].encode('utf-8')
        if not name:
            logging.debug ('###### DID NOT FOUND SCREEN SCRAPER NAME, ASSIGNING FIRST NAME')
            name = jsondata['jeu']['nom'][0]['text']
        mdisk = multiDisk(path)
        mvers = multiVersion(path)
        mctry = multiCountry(path)
        if mctry:
            name = name+' '+mctry.group(0)
        if mdisk:
            name = name+' '+mdisk.group(0)
        if mvers:
            name = name +' ('+mvers.group(0)+')'
    else:
        logging.debug ('###### NOMS TAG NOT IN JSON '+str(jsondata['jeu']))
        name = jsondata['jeu']['nom']
    return name

def updateInDBV2Call(api,params,response):
    try:
        response = response.strip()
    except:
        logging.debug('###### DO NOT NEED TO STRIP ANYTHINF')
    logging.debug ('###### INSIDE INSERT INTO DB FOR V2 CALL '+str(params))
    ### Update the DB with the call to V2
    if response == 'ERROR' or response =='QUOTA':
        ### Gameid=1 is added to the non caching criteria to avoid being there when quota is over and checking 
        logging.info ('###### GOT AN ERROR FROM API CALL SO NOT UPDATING V2 DB '+response)
        return False
    logging.debug ('###### CONNECTING TO DB TO UPDATE CACHED RESULT FOR V2 CALL')
    ###### FIRST LOOKUP IN REQUEST EXISTS
    sql = 'SELECT apiname FROM apicache WHERE apiname=%s and parameters=%s'
    vals =(api,params)
    result,success = queryDB(sql,vals,False,mydb,False)
    logging.debug ('###### RESPONSE '+str(result))
    if result =='' or result == None or not success:
        sql = "INSERT INTO apicache (apiname,parameters,result) VALUES (%s,%s,%s)"
        val = (api,params,response)
    else:
        sql = "UPDATE apicache set result = %s WHERE apiname= %s and parameters =%s"
        val = (response,api,params)
    logging.debug ('###### TRYING TO INSERT INTO DB API V2 CACHE')
    logging.debug ('###### INSERTING IN DB')
    newresponse, success = queryDB(sql,val,True,mydb,False)
    logging.debug ('###### RETURNED FROM INSERTING IN DB')
    if success:
        try:
            logging.debug ('###### WILL SEE IF IT IS PROPER JSON')
            jres = ast.literal_eval(response)
            logging.debug ('###### '+str(jres))
        except Exception as e:
            logging.error ('###### COULD NOT CONVERT ANSWER TO DICT IN UPDATE DBV2 CALL '+str(e))
            jres = response
        if isinstance(jres,dict):
            if response in jres.keys():
                insertGameInLocalDb(jres['response']['jeu'])
        else:
            logging.info ('###### THERE IS NO GAME IN THE RESPONSE ')
            return False
    else:
        logging.error ('###### COULD NOT INSERT INTO DB V2 API CACHE')
        return False

def searchInDBV2Call(api,params,force):
    ### Try to see if it is in cache
    if force:
        logging.debug ('###### FORCED TO RETURN EMPTY RESULT')
        return ''
    result = ''
    logging.debug ('###### CONNECTING TO DB TO LOCATE CACHED RESULT FOR V2 CALL')
    sql = "SELECT result FROM apicache WHERE apiname = %s AND parameters = %s"
    val = (api,params )
    logging.debug ('###### TRYING TO QUERY DB API V2 CACHE')
    result, success = queryDB(sql,val,False,mydb)
    if result == None:
        logging.debug ('###### NO CACHED CALL FOUND IN THE DB')
        return None
    else:
        logging.debug ('###### FOUND CACHED CALL IN DB')
        return result
 
def parsePossibleErrors(status):
    ## GENERIC ERROR PARSE FOR API CALLS, RETURNS A SHORT ERROR OR SAME RESPONSE DEPENDING
    ## ON CONTENTS
    if status == 200:
        response = 'OK'
    if status == 401 or status == 430 or status == 431:
        response = 'QUOTA'
    if status == 400 or status == 403 or status == 423 or status == 429 or status == 426:
        logging.debug ('###### GOT A CALL ERROR '+str(status)) 
        response = 'FAILED'
    if status == 404: 
        logging.debug ('###### GOT A NOT FOUND ERROR '+str(status))
        response = 'NOT FOUND' 
    if status == 500 or status == 503:
        logging.error ('###### THERE IS A SERVER ERROR '+str(status))
        response = 'FAILED'
    if response == '':
        logging.error ('###### GOT AN UNKNOW STATUS CODE '+str(status))
    logging.debug ('###### WILL RETURN '+response)
    return response

def getV2CallInfo(URL):
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
    return apiname,dbparams

def getV2CallFromDB(URL,forceCall):
    apiname,dbparams = getV2CallInfo(URL)
    response = searchInDBV2Call(apiname,dbparams,forceCall)
    logging.debug ('###### AFTER SEARCH IN DB')
    if response:
        logging.debug ('###### RETURNING RESPONSE')
        return response
    else:
        logging.debug ('###### DID NOT FIND V2 ANSWER IN DB')
        return ''

def doV2URLRequest(URL):
    response = ''
    timeout = True
    tries = 10
    while timeout and tries > 0:
        try:
            req = requests.get(URL)
            response = req.text
            logging.debug ('##### ERROR CODE '+str(req.status_code))
            logging.debug(response)
        except Exception as e:
            logging.error ('###### CANNOT CALL URL - FAILING '+str(e))
        
            ## TODO REMOVE
        if response[0]=='<':
            try:
                response = re.sub(r'<br\s\/>(\s|\S)*<br\s\/>','',response)
            except Exception as e:
                logging.error ('###### CANNOT TREAT RESPONSE '+str(e))
        try:
            status = parsePossibleErrors(req.status_code)
            if status != 'OK':
                response = status
        except Exception as e:
            logging.error ('###### ERROR WHILE PARSING ERRORS '+str(e))
        if response != 'RETRY':
            timeout = False
        else:
            tries = tries -1
            if tries == 0:
                logging.error ('###### TOO MANY TIME OUTS, WILL GO TO NOT FOUND')
                response = 'NOT FOUND'
            else:    
                logging.error ('###### TIMED OUT - WILL RETRY')
    ### SOME OTHER ERROR HANDLING
    return response

def callURL(URL):
    logging.debug ('###### CALLING URL '+URL)
    response = ''
    try:
        logging.debug ('###### ATCUAL CALL')
        success = False
        retries = 10
        while not success and retries > 1:
            try:
                req = requests.get(URL)
                success = True
            except requests.exceptions.Timeout:
                logging.error ('###### REQUEST TIMED OUT')
                retries = retries - 1 
            except requests.exceptions.TooManyRedirects:
                logging.error ('###### URL SEEMS TO BE WRONG '+URL)
            except requests.exceptions.RequestException as e:
                logging.error ('###### UNHANDLED ERROR '+str(e))
                retries = retries -1
        response = req.text
        logging.debug ('###### GOT A RESPONSE')
        return response
    except Exception as e:
        logging.error ('###### COULD NOT CALL URL '+str(URL)+' - Error '+str(e))
        return ''

def tryToFixResponse(newresponse):
    response = newresponse
    try:
        ### SEE IF IT IS A PROPER JSON OR NOT
        logging.debug ('###### GOING TO CHECK IF IT IS A REAL JSON')
        response =  ast.literal_eval(newresponse)
    except Exception as e:
        if response !='NOT FOUND' and response!='QUOTA' and response!='FAILED':
            logging.debug ('###### THE RETURN JSON WHEN CALLED API IS NOT VALID '+str(e)+', WILL TRY TO FIX')
            err = response.rfind ('],')
            logging.debug('###### BAD RESPONSE AT '+str(err)+' OF LENGTH '+str(len(response)-15))
            if err > len(response)-15:
                logging.debug ('###### HARD FIXING A SCREENSCRAPER BUG A STARY COMMA NEAR THE END AFTER A ]')
                newresponse = response[:err] + "]" + response[err+2:]
    return newresponse


def callAPIURL(URL,forceCall=False):
    #### ACTUAL CALL TO THE API
    ## Check if it is a v2 Call first
    response=''
    logging.debug ('####### GOING TO CALL URL '+URL)
    v2 = re.search('\/[a|A][P|p][i|I]2\/',URL)
    logging.debug('###### IS V2 '+str(v2))
    if v2:
        response = getV2CallFromDB(URL,forceCall)
    elif not v2:
        logging.debug ('###### V1 CALLS ARE OVER, CHECK WHY YOU WANT TO CALL THIS '+str(URL))
        return 'ERROR'
    if response != '':
        return response
    logging.debug ('###### THERE WAS NO RESPONSE FROM DB SO I MIGHT AS WELL CALL THE API')
    successCall = False
    while not successCall:
        ### A BIT OF ORDER AND LOGIC HERE:
        ### FIRST WE TRY CALLING ANONYMOUS, IF ANON CALL IS NOT POSSIBLE
        ### WE TRY CALLING WITH ACCOUNT
        ### -------------------------------------------------
        ### CONVERT URL TO ANON AND CALL IT
        logging.debug (URL)
        anonURL = re.sub(r'&ssid=\w*','&ssid=',URL)
        logging.debug ('###### CALLING AS ANON')
        response = doV2URLRequest(anonURL)
        logging.debug ('###### AFTER I HAVE CALLED THE DB TO SEARCH FOR A CACHED CALL')
        if response == 'FAILED' or response == 'QUOTA':
            logging.debug ('###### FAILED TO CALL AS ANON, WILL RETRY AS IDENTIFIED')
            logging.debug (URL)
            response = doV2URLRequest(URL)
        if response != 'FAILED' and response != 'QUOTA':
            successCall = True
            logging.debug ('###### DECODING RESPONSE')
            response = response.encode('utf-8')               ##decode('utf-8').encode('ascii','replace') ### DO NOT TOUCH
        if response == 'QUOTA':
            logging.debug ('###### WE GOT QUOTA ERROR FOR ANON AND IDENTIFIED - WE CANNOT CONTINUE - WAIT 10 MINS TO RETRY')
            sleep (180)
        if response == 'NOT FOUND':
            logging.debug ('###### ROM/GAME HAS NOT BEEN FOUND, RETURN THIS INFORMATION TO CALLER')
            successCall = True
        if response == 'FAILED':
            logging.debug ('###### FAILED TO CALL AS IDENTIFIED WILL RETRY AS ANON')
            sleep (180)
    
    logging.debug ('###### AN ACCEPTABLE ANSWER WAS FOUND, GOING TO PROCESS IT')
    newresponse = tryToFixResponse(response)
    if v2 and newresponse!='':
        logging.debug ('###### GOING TO UPDATE CACHE IN DB FOR V2')
        apiname,dbparams = getV2CallInfo(URL)
        updateInDBV2Call(apiname,dbparams,newresponse)
    else:
        logging.debug ('###### THIS IS NOT A V2 CALL ???? '+str(v2))
    return response

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
    players = ''
    if isinstance(json, dict):
        logging.debug('###### JSON IS DICTIONARY ')
        if 'jeu' in json.keys():
            logging.debug('###### JEU IN KEYS')
            jeu = json['jeu']
            if isinstance(jeu, dict):
                logging.debug('###### JEU IS DICT')
                try:
                    players = jeu['joueurs']['text']
                except:
                    logging.error ('###### COULD NOT FIND PLAYERS NUMBER')
                    return ''
    return players

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
        logging.debug('###### JSON IS DICTIONARY ')
        if 'jeu' in json.keys():
            logging.debug('###### JEU IN KEYS')
            jeu = json['jeu']
            if isinstance(jeu, dict):
                logging.debug('###### JEU IS DICT')
                try:
                    synops = jeu['synopsis']
                except:
                    logging.error ('###### COULD NOT FIND SYNOPSIS FOR GAME')
                    return description
                logging.debug('###### GOT SYNOPIS '+str(synops))
                found = False
                if isinstance(synops,list):
                    for desc in synops:
                        logging.debug ('###### LANGUE '+desc['langue'])
                        if desc['langue'].upper()=='EN':
                            logging.debug ('###### FOUND YOUR LANGUAGE')
                            description = desc['text']
                            found = True
                            break
                if not found:
                    try:
                        description = synops[0]['text']
                    except:
                        description =''
    logging.debug ('###### RETURNING DESCRIPTION '+description)
    return description


def getDate(json):
    # THSI FUNCTION GETS THE RELEASE DATE OF A GAME
    reldate = 'Unknown'
    if isinstance(json, dict):
        logging.debug('###### JSON IS DICTIONARY ')
        if 'jeu' in json.keys():
            logging.debug('###### JEU IN KEYS')
            jeu = json['jeu']
            if isinstance(jeu, dict):
                logging.debug('###### JEU IS DICT')
                try:
                    dates = jeu['dates']
                except:
                    logging.error ('###### COULD NOT FIND DATES FOR GAME')
                    return reldate
                logging.debug('###### GOT DATES '+str(dates))
                found = False
                if isinstance(dates,list):
                    for dat in dates:
                        logging.debug ('###### REGION '+dat['region'])
                        if dat['region'].upper()=='EU':
                            logging.debug ('###### FOUND YOUR REGION')
                            reldate= dat['text']
                            found = True
                            break
                    if not found:
                        try:
                            reldate = dates[0]['text']
                        except Exception as e:
                            logging.debug ('###### COULD NOT FIND DATES '+str(e))
                else:
                    try:
                        reldate = dates['text']
                    except Exception as e:
                        logging.debug ('###### COULD NOT FIND DATES '+str(e))

    logging.debug ('###### RETURNING DATES '+reldate)
    return reldate

def writeXML(rootElement, filename):
    ### THIS FUNCTION WRITES AN XML FILE
    logging.debug ('###### XML WRITING')
    try:
        tree.write(open(filename, 'w'))
    except Exception as e:
        logging.error('cannot make pretty XML ' + str(e))
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
    logging.info ('###### WILL RESTART PROCESS AT '+str(startTime))
    allowed = False
    logging.info ('###### WAITING FOR NEXT DAY')
    API = "jeuInfos"
    params = None
    params =dict(fixParams)
    params['gameid'] = 1
    while (startTime > datetime.today().time()) and not allowed: # you can add here any additional variable to break loop if necessary
        sleep(60)
        response = callAPI(fixedURL,API,params,0,'2','WAIT NEW DAY')
        if 'jeu'  in response:
            allowed = True
    logging.info ('###### FINISHED WAITING')
    return

def callAPI(URL, API, PARAMS, CURRSSID,Version='',tolog='',returnRaw=False,forceCall=False):
    ## REMOVE CRC AND MD5, TENDS TO FAIL IN v2
    PARAMS.pop('md5',None)
    PARAMS.pop('crc',None)   
    global VTWOQUOTA
    if Version=='2' and VTWOQUOTA:
        logging.info ('###### DAILY QUOTA HAS BEEN EXCEEDED FOR V2 API - CANNOT CALL IT FOR NOW ')
        return 'QUOTA'
    logging.debug ('###### CALLING API WITH EXTRA '+tolog)
    ### BUILD QUERY
    try:
        ### Python 3
        url_values = urllib.parse.urlencode(PARAMS)
    except:
        ### Python 2
        url_values = urllib.urlencode(PARAMS)
    API = Version+'/'+API+".php"
    callURL = URL+API+"?"+url_values
    ### CREATE EMPTY VARIABLES
    ### EMPTY RESPONSE JUST IN CASE
    response = None
    logging.debug ('###### CALLING API ')
    logging.debug ('##### ACTUAL CALL TO API '+API)
    retJson = None
    logging.debug ('###### GOING TO CALL API URL')
    response = callAPIURL(callURL,forceCall)
    logging.debug ('###### CALLED API URL')
    logging.debug(response)
    if response == 'QUOTA':
        VTWOQUOTA = True
        return response
    if response == 'NOT FOUND':
        return response
    logging.debug ('###### CHECKING IF "{" IN RESPONSE')
    if '{' in response:
        logging.debug ('###### YES THERE IS { IN RESPONSE')
        a = '{'+response.split('{', 1)[1]
        response = a.rsplit('}', 1)[0] + '}'
        try:
            result = response.replace('\x0d\x0a','\\r\\n').replace('\x0a','').replace('\x09','').replace('\x0b','').replace('  ','').replace('\r','')
            retJson = json.loads(result)
        except:
            logging.debug ('###### THE RETURN JSON IS NOT VALID, WILL TRY TO FIX')
            err = response.rfind ('],')
            logging.debug('###### BAD RESPONSE AT '+str(err)+' OF LENGTH '+str(len(response)-15))
            if err > len(response)-15:
                logging.debug ('###### HARD FIXING A SCREENSCRAPER BUG A STARY COMMA NEAR THE END AFTER A ]')
                result = response[:err] + "]" + response[err+2:]
            if '#jsonrominfo' in result:
                logging.debug ('###### HARD FIXING ANOTHER SCREENSCRAPER BUG, #JSONROMINFO NOT NEEDED')
                result = result.replace('#jsonrominfo','')
                logging.debug ('###### '+str(result))
            new_response = result.replace('\x0d\x0a','\\r\\n').replace('\x0a','').replace('\x09','').replace('\x0b','').replace('  ','').replace('\r','')
            try:
                retJson = ast.literal_eval(new_response)
            except Exception as e:
                try:
                    new_response = new_response.replace('\\r\\n','')
                    retJson = ast.literal_eval(new_response)
                except Exception as e:
                    logging.error ('####### EXITING NEED TO ANLYZE THIS ERROR' )
                    logging.error ('####### '+str(e))
                    logging.error ('####### '+str(new_response))
                    sys.exit()
    else:
        logging.error ('###### CHECK RESPONSE '+str(response))
        return 'ERROR'
    ### CHECK FOR V2 QUOTA LIMITS TO AVOID CALLING FOR NO REASON
    try:
        myJson = retJson['response']
    except Exception as e:
        logging.debug ('###### THERE WAS AN ERROR WHEN RETRIEVING RESPONSE FROM URL RETURN')
        myJson = 'ERROR'
    if isinstance(retJson, (dict, list)):
        try:
            okcalls = myJson['ssuser']['requeststoday']
            okmax = myJson['ssuser']['maxrequestsperday']
            kocalls = myJson['ssuser']['requestskotoday']
            komax = myJson['ssuser']['maxrequestskoperday']
            logging.debug ('###### V2 QUOTA INFO - OK CALLS '+str(okcalls)+' KO CALLS '+str(kocalls)+' OK MAX '+str(okmax)+' KO MAX '+str(komax))
            if int(okcalls) > int(okmax) or int(kocalls) > int(komax):
                VTWOQUOTA = True
                logging.debug('###### MAXIMUM DAILY QUOTA IS OVER')
                return 'QUOTA'
            else:
                VTWOQUOTA = False
        except Exception as e:
            if 'ssuser' in str(e):
                logging.error ('###### ERROR IN GETTING INFORMATION FROM RESPONSE // PROBABLY ANON CALL [SSUSER MISSING] , NOTHING TO WORRY ABOUT '+str(e))
            elif 'requests' in str(e):
                logging.error ('###### ERROR IN GETTING QUOTA INFORMATION IN RESPONSE '+str(e))
            else:
                logging.error ('###### ERROR IN GETTING RESPONSE '+str(e))
    if returnRaw:
        logging.debug('###### RETURNING RAW JSON')
        return result
    else:
        logging.debug ('###### RETURNING DICT')
        return myJson
    


def existsInGamelist(gamelist, game):
    # Checks if a game is already in gamelist or not
    pass


def updateGameInList(gamelist, game):
    # Update game in gamelist
    pass


def addGameToList(gamelist, game):
    # Adds game to gamelist
    pass

def grabVideo (URL,destfile):
        logging.debug ('###### ACTUALLY GOING TO DOWNLOAD VIDEO '+destfile)
        result = 1
        retries = 0
        while (result !=0) and (retries <10):
            logging.debug ('###### ACTUALLY DOWNLOADING VIDEO '+str(URL)+' ON TRY #'+str(retries+1))
            logging.debug ('###### COMMAND: wget --retry-connrefused --waitretry=1 --read-timeout=20 --timeout=15 --tries=5 -c -q '+str(URL)+' -O '+str(destfile))
            try:
                result = subprocess.call(['wget','--retry-connrefused','--waitretry=1','--read-timeout=20','--timeout=15','--tries=5','-c','-q', URL, '-O', destfile])
            except Exception as e:
                logging.error ('###### ERROR WGETTING VIDEO '+str(e))
            logging.debug ('###### VIDEO DOWNLOAD RESULT '+str(result))
            logging.debug ('###### FILE EXISTS '+str(os.path.isfile(destfile)))
            if not validateVideo(destfile):
                if os.path.isfile(destfile):
                    os.remove(destfile)
                    logging.debug ('###### DOWNLOADED VIDEO IS CORRUPT, RETRYING')
                URL = URL.replace('www.','clone.')
                result = -1
            retries = retries + 1
        logging.debug ('###### RESULT OF DOWNLOAD '+str(result))
        if result == -1:
            logging.error ('##### DOWNLOAD FAILED - TRY MANUALLY wget ' + URL + ' -O ' + destfile)
        if result == 0:
            return destfile
        else:
            try:
                if os.path.isfile(destfile):
                    os.remove(destfile)
            except:
                logging.error ("##### CANNOT REMOVE FAILED DOWNLOAD")
            return ''
        logging.error ('###### ERROR DOWNLOADING VIDEO '+URL+' '+str(e))
        return ''


def validateImage(imagefile):
    try:
        if os.path.islink(imagefile):
            logging.debug ('###### IT IS A SYMLONK SO ASSUMING IMAGE IS OK')
            return True
        im = Image.open(imagefile)
        logging.debug ('###### IMAGE SEEMS TO BE OK '+str(im))
        return True
    except Exception as e:
        logging.debug ('###### IMAGE IS CORRUPT '+str(e))
        return False

def validateVideo(videofile):
    logging.debug ("###### VALIDATING "+videofile)
    if os.path.islink(videofile):
        logging.debug ('###### IS A SYMLINK, SO ASSUME IT IS OK')
        return True
    try:
        if os.stat(videofile).st_size == 0:
            logging.debug ('###### VIDEO SIZE EQUALS ZERO')
            return False
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

def grabMedia(URL,destfile):
        logging.debug ('###### ACTUALLY GOING TO GRAB MEDIA '+destfile)
        result = -1
        retries = 0
        while (result !=0) and (retries <10):
            logging.debug ('###### WILL WGET MEDIA')
            try:
                result = subprocess.call(['wget','--retry-connrefused','--waitretry=1','--read-timeout=20','--timeout=15','-t','0','-c','-q', URL, '-O', destfile])
            except Exception as e:
                logging.error('###### CANNOT WGET MEDIA '+str(e))
                return ''
            if not validateImage(destfile):
                if os.path.isfile(destfile):
                    logging.debug('###### COULD NOT VALIDATE '+destfile+' SO I REMOVE IT')
                    os.remove(destfile)
                URL = URL.replace('www.','clone.')
                logging.debug ('###### DOWNLOAD IS CORRUPTED ON RETRY '+str(retries+1)+' URL '+str(URL))
                result = -1
            retries = retries + 1
        logging.debug ('###### RESULT OF DOWNLOAD '+str(result))
        if result == -1:
            logging.error ('##### FAILED DOWNLOAD - TRY MANUALLY wget ' + URL + ' -O ' + destfile)
            return ''
        if result == 0:
            return destfile
        else:
            try:
                if os.path.isfile(destfile):
                    os.remove(destfile)
            except:
                logging.error ("##### CANNOT REMOVE FAILED DOWNLOAD")
            return ''

def getImage(medialist,num,imgtype):
    logging.debug ('###### GOING TO GET '+imgtype.upper()+' '+str(medialist))
    if not isinstance (medialist,list):
        logging.debug ('###### MEDIA LIST IS NOT A LIST')
        medialist = [medialist]
        logging.debug ('###### MEDIA LIST IS A LIST NOW')
    for media in medialist:
        logging.debug ('###### MEDIA TYPE IS '+media['type'])
        URL = media['url']
        if media['type'].upper() == imgtype.upper():
            if 'screenscraper' in URL:
                mediaFormat = media['format']
            else:
                mediaFormat = URL[URL.rindex('.')+1:]
            mediaURL = URL
            tempfile = tmpdir+'image'+str(num)+'.'+mediaFormat
            if os.path.isfile(tempfile):
                logging.debug ('###### DELETING FILE THAT WAS PROBABLY LEFT AFTER A KILL OR SOMETHING')
                os.remove (tempfile)
            return grabMedia(mediaURL,tempfile)
    logging.debug ('###### NO IMAGE FOUND ')
    return ''

def doMediaDownload(medialist,destfile,path,hash):
    logging.debug ('###### DOWNLOADING MEDIA -> '+str(os.path.isfile(destfile)))
    if (not(os.path.isfile(destfile)) and ('images' in destfile)) or UPDATEDATA:
        logging.debug('###### GOING TO DOWNLOAD COMPOSITE SCREEN '+destfile)
        img1 = getImage(medialist,random.randint(0,10000),'mixrbv1')
        if img1 != '':  
            logging.debug ('###### WE GOT A COMPOSITE')
            shutil.move(img1,destfile)
            return
        logging.debug ('###### NO COMPOSITE FOUND, CREATING ONE - DOWNLOADING SCREENSHOT')
        img1 = getImage(medialist,random.randint(0,10000),'ss')
        if (img1 != ''):
            logging.debug('###### GOING TO DOWNLOAD BOXART')
            img2 = getImage(medialist,random.randint(0,10000),'box-3D')
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
    else:
        logging.error('###### FILE IS ALREADY PRESENT - SKIPPING DOWNLOAD')
        return ''

def processMarquees(medialist,destfile,path,hash,zipname):
    logging.debug('###### DO I HAVE TO SKIP MARQUEES '+str(nomarquee))
    if nomarquee:
        return ''
    logging.debug ('###### PROCESS MARQUEE FOR '+zipname)
    if os.path.isfile(destfile):
        logging.debug ('###### FILE ALREADY EXISTS ')
        return destfile
    img = getImage(medialist,'99','marquee')
    if img == '':
        img = getImage(medialist,'99','screenmarquee')
        if img == '':
            img = getImage(medialist,'99','screenmarqueesmall')
            if img == '':
                logging.debug ('###### THERE ARE NO MARQUEES AVAILABLE FOR THIS FILE')
                return ''
    logging.debug ('###### DESTINATION FOR MARQUEE IS '+destfile)
    shutil.move(img,destfile)
    return destfile

def processBezels(medialist,destfile,path,hash,zipname):
    if nobezel:
        return ''
    logging.debug ('###### PROCESS BEZEL FOR '+zipname)
    logging.debug ('###### DOWNLOADING BEZELS '+str(medialist))
    bezeldir = path.replace('roms','overlays')
    if not os.path.exists(bezeldir):
        os.makedirs(bezeldir)
    testimg = bezeldir+'/bezel-'+str(hash)+'.png'
    if os.path.isfile(testimg):
        logging.debug ('###### FILE ALREADY EXISTS ')
        return ''
    img = getImage(medialist,'99','bezel-16-9')
    if img == '' :
        logging.debug ('###### THERE ARE NO BEZELS AVAILABLE FOR THIS FILE OR ALREADY DOWNLOADED')
        return ''
    else:
        destfile = bezeldir+'/bezel-'+str(hash)+img[img.rindex('.')-1:]
        logging.debug ('###### DESTINATION FOR BEZEL IS '+destfile)
        shutil.move(img,destfile)
        zipname = zipname[zipname.rfind('/')+1:]
        logging.debug ('###### ZIPNAME IS '+zipname)
        bezelcfg = path+'/'+zipname+'.cfg'
        logging.debug ('###### BEZELCFG IS '+bezelcfg)
        bzlfile,bzlext = os.path.splitext (zipname)
        romcfg = bzlfile+'.cfg'
        logging.debug ('###### ROMCFG IS '+romcfg)
        romcfgpath = bezeldir+'/'+romcfg
        logging.debug ('###### ROMCFGPATH IS '+romcfgpath)
        #if not os.path.isfile(bezelcfg):
        f = open(bezelcfg, "w")
        f.write('input_overlay = "'+ bezeldir+'/'+romcfg+'"\n')
        f.close
        #if not os.path.isfile(romcfgpath):
        f = open(romcfgpath, "w")
        f.write('overlays = "1"\noverlay0_overlay = "'+destfile+'"\noverlay0_full_screen = "true"\noverlay0_descs = "0"\n')
        f.close

def doVideoDownload(medialist,destfile):
    logging.debug('####### TYPE OF MEDIALIST '+str(type(medialist)))
    for media in medialist:
        logging.debug ('###### MEDIA TYPE IS '+media['type'])
        if media['type'].upper() == 'VIDEO-NORMALIZED':
            mediaURL = media['url']
            return grabVideo(mediaURL,destfile)
    logging.debug ('###### THERE IS NO VIDEO FOR THIS FILE')
    return ''

def getVideo(medialist, path, file, hash):
    logging.debug ('###### STARTED GRABBING VIDEO PROCESS')
    destfile = ''
    logging.debug ('###### MEDIALIST IS '+str(medialist))
    if medialist != '' and len(medialist)>0:
        if not isinstance(medialist,list):
            logging.debug ('###### MEDIALIST NOT LIST SO TRYING CONVERT IT ')
            medialist=[medialist]
        logging.debug('##### GRABBING VIDEO FOR ' + file)
        destfile = path+'/videos/'+hash+'-video.mp4'
        if os.path.isfile(destfile):
            logging.debug ('###### FILE ALREADY EXISTS, NOT DOWNLOADING AGAIN')
            return destfile
        else:
            logging.debug ('###### THERE IS NO VIDEO FILE PRESENT SO I DOWNLOAD')
            return doVideoDownload(medialist,destfile)
    else:
        logging.debug ('###### MEDIALIST IS EMPTY')
    return destfile

def getMedia(medialist, path, file, hash,zipname):
    logging.debug ('###### STARTING MEDIA DOWNLOAD PROCESS')
    ###logging.debug ('###### THIS IS THE MEDIALIST ' + str(medialist))
    destfile = ''
    if medialist != '' and len(medialist)>0:
        logging.debug('##### GRABBING FOR ' + file)
        destfile = path+'/images/'+hash+'-image.png'
        if os.path.isfile(destfile):
            logging.debug ('###### MEDIA FILE ALREADY EXISTS')
        else:
            logging.debug ('###### GOING TO DOWNLOAD MEDIA')
            doMediaDownload(medialist,destfile,path,hash)
        logging.debug ('###### GOING TO DOWNLOAD BEZELS')
        processBezels(medialist,destfile,path,hash,zipname)
    return destfile

def getMarquee(medialist, path, file, hash,zipname):
    logging.debug ('###### STARTING MARQUEE DOWNLOAD PROCESS')
    ###logging.debug ('###### THIS IS THE MEDIALIST ' + str(medialist))
    destfile = ''
    if medialist != '' and len(medialist)>0:
        logging.debug('##### GRABBING FOR ' + file)
        destfile = path+'/marquees/'+hash+'-marquee.png'
        if os.path.isfile(destfile):
            logging.debug ('###### MARQUEE FILE ALREADY EXISTS')
        else:
            logging.debug ('###### GOING TO DOWNLOAD MARQUEE')
            destfile = processMarquees(medialist,destfile,path,hash,zipname)
    return destfile



def getAllSystems(CURRSSID):
    ### CALLS API TO GET A LIST OF ALL THE SYSTEMS IN THE SITE
    logging.debug ('###### GETTING ALL SYSTEMS LIST')
    ### THIS IS THE API NAME
    API = "systemesListe"
    response = callAPI(fixedURL, API, fixParams, CURRSSID,'2','Get All Systems')
    ### IF WE GET A RESPONSE THEN RETURN THE LIST
    if response != 'ERROR' and response is not None:
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
    logging.debug ('###### TRYING TO DELETE INFO IN HASH DB FOR '+file)
    result,success = queryDB(sql,val,True,mydb)
    if not success:
        logging.error ('###### ERROR DELETING RECORDS FOR '+file+' FROM DB :'+str(e))
    else:
        logging.debug('###### RECORDS DELETED')
    return success

def getAllGamesinDB():
    logging.debug ('###### CONNECTING TO DB TO GET ALL FILE HASHES ')
    sql = "SELECT file,SHA1,CRC,MD5 FROM filehashes"
    val = ()
    logging.debug ('###### TRYING TO QUERY DB FOR ALL FILE HASHES')
    result,success = queryDB(sql,val,False,mydb)
    if success:
        logging.debug ('###### COULD GET ALL CACHES')
    else:
        logging.debug ('###### COULD NOT GET ALL CACHES')
    return result

def lookupHashInDB(file,hashType):
    logging.debug ('###### CONNECTING TO DB TO LOCATE HASH '+hashType+' FOR '+file)
    sql = "SELECT "+hashType.upper()+" FROM filehashes WHERE file = %s"
    val = (file, )
    logging.debug ('###### TRYING TO QUERY DB FOR '+hashType)
    result,success = queryDB(sql,val,False,mydb)
    if success:
        logging.debug('###### FOUND IN DB')
    else:
        logging.debug('###### NOT FOUND IN DB')
    return result

def updateHashInDB(file,hashType,hash):
    logging.debug ('###### UPDATING '+hashType+' '+hash+' FOR FILE '+file)
    sql = "UPDATE filehashes SET "+hashType.upper()+"= %s WHERE file = %s"
    val =(str(hash),str(file))
    result,success = queryDB(sql,val,True,mydb)
    if success:
        logging.debug ('###### HASH UPDATED ')
    else:
        logging.debug ('###### COULD NOT UPDATE HASH')
    return success

def insertHashInDB(myfile,hashType,hash):
    logging.debug ('###### INSERTING '+hashType+' '+hash+' FOR FILE '+myfile)
    sql ="SELECT file FROM filehashes where file = %s"
    val =(str(myfile))
    result,success = queryDB(sql,val,True,mydb)
    logging.debug ('###### '+str(result))
    if not success:
        logging.debug ('###### FILE RECORD DOES NOT EXSITS FOR '+myfile)
        sql = "INSERT INTO filehashes (file, "+hashType.upper()+") VALUES (%s, %s)"
        val =(str(myfile),str(hash))
    else:
        logging.debug ('###### FILE RECORD DOES EXSITS FOR '+myfile)
        sql = "UPDATE filehashes SET "+hashType.upper()+"= %s WHERE FILE=%s"
        val =(str(hash),str(myfile))
    result,success = queryDB(sql,val,True,mydb)
    if success:
        logging.debug ('###### HASH INSERTED ')
    else:
        logging.debug ('###### COULD NOT INSERT HASH')
        success = updateHashInDB(myfile,hashType,hash)
    return success


def md5(fname):
    dbval =''
    dbval = lookupHashInDB(fname,'MD5')
    if dbval !='' and dbval != None:
        logging.debug('###### FOUND SOMETHING IN DB FOR '+fname+' SO RETURNING MD5='+str(dbval))
        return dbval.upper()
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
        return retval.upper()
    except Exception as e:
        logging.error('###### COULD NOT CALCULATE MD5 ' + str(e))
        return ''

def sha1(fname):
    dbval = ''
    dbval = lookupHashInDB(fname,'SHA1')
    if dbval !='' and dbval != None:
        logging.debug ('###### FOUND SHA1 '+str(dbval)+' FOR FILE '+fname)
        return dbval.upper()
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
        return retval.upper()
    except Exception as e:
        logging.error('###### COULD NOT CALCULATE SHA1 ' + str(e))
        return ''

def crc(fileName):
    dbval=''
    dbval = lookupHashInDB(fileName,'CRC')
    if dbval !='' and dbval != None:
        logging.debug ('###### FOUND CRC '+str(dbval)+' FOR FILE '+fileName)
        return dbval.upper()
    logging.debug ('###### NOT IN DB SO CALCULATING CRC OF FILE '+fileName)
    try:
        retval = None
        prev = 0
        for eachLine in open(fileName, "rb"):
            prev = zlib.crc32(eachLine, prev)
        retval = "%X" % (prev & 0xFFFFFFFF)
        insertHashInDB(fileName,'CRC',retval)
        logging.debug ('###### CALUCLATED CRC '+str(retval)+' FOR FILE '+fileName)
        return retval.upper()
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
                if 'jeu' in gameinfo:
                    logging.debug ('###### FOUND GAME INFO FOR '+zipfile)
                    return gameinfo
    logging.debug ("###### DID NOT FIND GAME INFO FOR "+zipfile)
    return gameinfo

def processZipFile(path,filename,sysid):
    logging.info ('###### PROCESSING ZIPFILE '+str(filename))
    if path[:-1] != '/':
        zipfilefull = path+'/'+filename
    else:
        zipfilefull = path+filename
    zfiles = getNamesInZip(zipfilefull)
    logging.debug('##### RETURNED THESE FILES IN ZIP ' + str(zfiles))
    if zfiles == '':
        # error extracting file, go to next one
        logging.error('###### COULD NOT GET CONTENTS OF ZIP FILE ' + str(filename))
        return 0
    else:
        for zfile in zfiles:
            proczfile = zfile
            logging.debug ('###### GETTING INFO FOR FILE '+proczfile+' INSIDE ZIP '+zipfilefull)
            exten = os.path.splitext(proczfile)[1]
            logging.debug ('###### EXTENSION IS '+exten)
            ''''
            if  exten not in extensions:
               logging.debug ('###### EXTENSION IS NOT IN LIST OF ALLOWED EXTENSIONS, SKIPPING')
               continue
            else:
            '''
            result = extractZipFile(zipfilefull,proczfile,'/tmp')
            logging.debug ('####### RESULT OF EXTRACT IS '+str(result))
            gameId = 0
            if result:
                if '/' in zfile:
	                unzipfile = '/tmp/'+zfile[zfile.rindex('/'):]
                else:
                    unzipfile = '/tmp/'+zfile
                logging.debug ('###### RESULT FILE OF DECOMPRESSION IS '+str(unzipfile))
                if os.path.isfile(unzipfile):
                    gameres = querySHAinDB(sha1(unzipfile),md5(unzipfile),crc(unzipfile),unzipfile,sysid,path)
                    if gameres:
                        gameres = gameres.replace('\x0d\x0a','\\r\\n').replace('\x0a','').replace('\x09','').replace('\x0b','').replace('  ','').replace('\r','')
                    os.remove(unzipfile)
                else:
                    gameres = None
                    logging.error ('###### CANNOT CHECK FILE INSIDE ZIP')
                logging.debug ('###### FOUND '+str(gameres))
                if gameres:
                    game = ast.literal_eval(gameres)
                else:
                    game = None
                if isinstance (game,dict):
                    gameId = game['jeu']['id']
                    logging.debug ('###### FOUND SOMETHING FOR '+str(unzipfile)+' ID '+gameId)
                    break
                else:
                    gameId = 0
                    logging.debug ('###### COULD NOT FIND ANYTHING FOR '+str(unzipfile))
    logging.debug('###### GAMEID FOUND INSIDE ZIP IS '+str(gameId))
    return gameId

def processZip(path,zipfile,CURRSSID,extensions,sysid):
    logging.debug ('###### PROCESSING ZIPFILE '+zipfile)
    zipfile,gameinfo = processFile (path,zipfile,CURRSSID,True,sysid)
    if gameinfo:
        if 'jeu' in gameinfo:
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
                if ('jeu' in gameinfo):
                    logging.debug ('###### FOUND GAME INFO FOR '+zipfile)
                    ### FOUND GAME INFO FOR FILE INSIDE
                    ### WE MIGHT AS WELL STORE SHAS FOR ZIP
                    updateHashInDB(path+'/'+zipfile,'SHA1',shazfile)
                    updateHashInDB(path+'/'+zipfile,'CRC',crczfile)
                    updateHashInDB(path+'/'+zipfile,'MD5',md5zfile)
                    return zipfile,gameinfo
    logging.debug ("###### COULD NOT FIND GAME INFO FOR "+zipfile)
    return zipfile,gameinfo

def processDir(dir,path,CURRSSID,extensions,sysid):
    logging.info ('###### STARTING DIRECTORY PROCESS')
    chkpath = path+'/'+dir
    logging.debug ('##### CHANGING DIRECTORY TO '+chkpath)
    filelist = getRomFiles(chkpath,extensions)
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
    logging.debug ('###### GO FOR FILE '+str(file))
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
        try:
            file,gameinfo = processZip(path,file,CURRSSID,extensions,sysid)
        except Exception as e:
            logging.error ('###### ERROR WHILE PROCESSING ZIPFILE '+file+' '+str(e))
        ### CHECK IF WE HAD A GAME RETURNED
    else:
        ### SO THIS IS A FILE WITH AN ACCEPTED EXTENSION, PROCESS IT
        try:
            logging.debug ('###### I\'M GOING TO PROCESS THE FILE '+file)
            file,gameinfo = processFile (path,file,CURRSSID,True,sysid)
            logging.debug ('###### I\'VE PROCESSED THE FILE '+file)
        except Exception as e:
            logging.error ('###### ERROR WHILE PROCESSING FILE '+file+' '+str(e))
    ### DID WE GET SOME GAME INFO?
    logging.debug ('###### SO FAR GAME INFO = '+str(gameinfo)+' AND IS OF TYPE '+str(type(gameinfo)))
    if gameinfo:
        logging.debug ('###### WE GOT A GAME INFO')
        return file,gameinfo
    else:
        ### SO WE DIDN'T GET ANYTHING, RETURN NONE THEN
        logging.debug('###### COULD NOT GET GAME INFO ')
        return file, None
    return file, None


def processFile (path,file,CURRSSID,doRename,sysid):
    ### SO WE ARE PROCESSING A GENERAL FILE
    logging.debug ('###### PROCESSFILE '+file)
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
    logging.debug ('###### GOT GAME INFO WHEN PROCESSING FILE ')
    while gameinfo == 'QUOTA':
        logging.debug ('###### THERE IS A QUOTA ISSUE')
        logging.debug ('###### LET\'S WAIT FOR AN HOUR TO RETRY')
        sleep(3600)
        file, gameinfo = getGameInfo(CURRSSID, path, file, md5offile, sha1offile, crcoffile,sysid)
    logging.debug ('###### I\'M RETURNING IT TO THE CALLER')
    return file, gameinfo

def getRomFiles(path,acceptedExtens):
    ### FIRST WE CHANGE DIRECTORY TO THE SYSTEM'S DIRECTORY
    try:
        os.chdir(path)
    except Exception as e:
        ### WE FAILED TO CHANGE DIRECTORY (SHOULDN'T HAPPEN BUT...)
        logging.error ('###### CANNOT CHANGE DIRECTORY TO '+path+ ' '+str(e))
        return 1
    try:
        ### CREATE SEARCH EXPRESSION FOR FILES, BASED ON EXTENSIONS, AGAIN ZIP IS ADDED BY DEFAULT, IN TIS CASE TO FACILITATE ITERATION
        filelist = []
        filelist.extend(sorted(glob.glob('*.*')))
        iterlist = list(filelist)
        logging.debug ('###### FOUND '+str(len(filelist))+' IN PATH, WILL VERIFY FOR EXTENSIONS')
        for myfile in iterlist:
            try:
                extens = myfile[myfile.rindex('.'):]
            except Exception as e:
                logging.error ('###### SEEMS THIS FILE '+myfile+' HAS NO EXTENSIONS, I REMOVE IT ['+str(e)+']')
                filelist.remove(myfile)
            ##logging.debug('###### FOR FILE '+myfile+' EXTENSION IS '+extens)
            if extens not in acceptedExtens:
                logging.debug ('###### REMOVED '+myfile+' FROM COPY LIST')
                try:
                    filelist.remove(myfile)
                except Exception as e:
                    logging.error ('###### COULD NOT REMOVE '+myfile+' FROM LIST')
        ### GET THE LIST OF FILES THAT COMPLY WITH THE ACCEPTED EXTENSIONS (PLUS ZIP, REMEMBER)
        logging.debug ('###### FOUND '+str(len(filelist))+' FILES WITH EXTENSIONS '+str(acceptedExtens))
        logging.debug ('###### '+str(filelist))
    except Exception as e:
        ### FOR SOME REASON SOMETHING WENT WRONG WHEN SEARCHING FOR FILES SO LET EVERYONE KNOW`
        logging.error('###### THERE ARE NO FILES IN DIRECTORY ' + path + str(e))
        ### AND CREATE AN EMPTY LIST SO EXECUTION CARRIES ON
        filelist = []
    return filelist

def grabData(system, path, CURRSSID, acceptedExtens,gamesList):
    ### WE'RE ABOUT TO PROCESS A SYSTEM
    logging.debug ('###### GRAB DATA START')
    ### CREATE ROOT ELEMENT FOR GAMELIST
    tree = ET.ElementTree()
    ### CREATE GAMELIST ELEMENT
    gamelist = ET.Element('gameList')
    filelist = getRomFiles(path, acceptedExtens)
    ### ITERATE THROUGH EACH FILE
    for file in filelist:
        ### CREATE A PORCESS FILE VARIABLE SO WE KEEP THE INITIAL FILE VARIABLE QUIET
        procfile = file
        taillen = 30-len(procfile)/4
        logging.info ('-+'*taillen+'- START FILE ['+procfile+'] '+'-+'*taillen+'-')
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
                gameinfo['localpath']=file
                logging.debug ('###### LOCAL PATH '+gameinfo['localpath'])
            except Exception as e:
                ### THERE WAS AN ERROR CREATING GAME INSTANCE, NOTIFY
                logging.error ('###### COULD NOT FIND LOCALPATH '+str(e))
            try:
                gameinfo['abspath']=path
                logging.debug ('###### ABSOLUTE PATH  '+gameinfo['abspath'])
            except Exception as e:
                ### THERE WAS AN ERROR CREATING GAME INSTANCE, NOTIFY
                logging.error ('###### COULD NOT FIND ABSPATH '+str(e))
            try:
                gameinfo['localhash']=sha1(path+'/'+file).upper()
                logging.debug ('###### SHA1  '+gameinfo['localhash'])
            except Exception as e:
                ### THERE WAS AN ERROR CREATING GAME INSTANCE, NOTIFY
                logging.error ('###### COULD NOT FIND SHA1 '+str(e))
            try:
                ### YES, CREATE A GAME INSTANCE THEN
                thisGame = None
                thisGame = Game(gameinfo)
            except Exception as e:
                logging.error ('###### COULD NOT CREATE GAME INSTANCE '+str(e))
            logging.debug ('###### REMOVING GAME FROM MISSING LIST')
            try:
                removeid = int(gameinfo['jeu']['id'])
                logging.debug('###### ID TO REMOVE '+str(removeid))
                gamesList.remove(removeid)
            except Exception as e:
                logging.debug ('###### STRANGE, THIS ID WAS NOT IN THE LIST OF GAMES FOR THE SYSTEM, POSSIBLY MULTIDISC '+str(e))
            if thisGame is not None:
                ### YES WE DID, SO GET THE XML FOR THIS GAME
                myGameXML = thisGame.getXML()
                logging.debug('###### GAME XML '+str(myGameXML))
                ### DID IT WORK?
                if myGameXML is not None:
                    ### YES, APPEND THE GAME TO THE GAMELIST
                    gamelist.append(thisGame.getXML())
                else:
                    ### NO, NOTIFY ERROR
                    logging.error('##### CANNOT GET XML FOR FILE '
                                  + procfile + ' WITH SHA1 ' + sha1(procfile))
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
        logging.info ('-+'*taillen+'- END FILE ['+procfile+'] '+'-+'*taillen+'-')
    ### WE HAVE PROCESSED ALL FILES, SO ADD GAMELIST TO THE ROOT ELEMENT OF THE XML
    tree._setroot(gamelist)
    ### SET THE DESTINATION XML FILE
    xmlFile = path + '/gamelist.xml'
    ### IF THE FILE IS EXISTING, REMOVE IT
    if os.path.isfile(xmlFile):
        logging.debug ('###### REMOVING GAMELIST')
        os.remove(xmlFile)
    ### AND THEN CREATE IT
    result = tree.write(xmlFile,encoding='utf-8', xml_declaration=True)
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
    logging.info ('###### CLEANING MARQUEES')
    cleanMedia(path + '/marquees/','*.png')
    logging.debug ('###### DONE SYSTEM')
    return gamesList

def isArcadeSystem(sysid):
    global arcadeSystems
    isit = sysid in arcadeSystems
    logging.debug ('###### IS AN ARCADE SYSTEM '+str(sysid)+' in '+str(arcadeSystems)+' = '+str(isit))
    return isit

def arcadeSystemsList():
    global arcadeSystems
    ret ='('
    for arcs in arcadeSystems:
        ret=ret+str(arcs)+','
    ret=ret[:-1]+')'
    logging.debug ('###### RETURNING SYSTEM LIST '+ret)
    return ret

def findMissingGame(gameName,systemid,path,isArcade):
    logging.debug('###### WILL TRY TO FIND GAMES '+gameName+' FOR SYSTEM '+str(systemid))
    srchName = gameName[:gameName.rindex('.')]
    qName =gameName[0]+'%'
    if len(srchName)>1:
        qName =gameName[0:1]+'%'
    if len(srchName)>2:
        qName =gameName[0:2]+'%'
    if len(srchName)>3:
        qName =gameName[0:3]+'%'
    logging.debug ('###### SEARCHING '+qName)
    sql = "SELECT gs.id as gameID, `system`, COALESCE (gn.`text`,'----') as gameName, COALESCE (gr.romfilename,'----') as romName FROM games gs\
           LEFT JOIN gameNames gn ON gn.gameid = gs.id\
           LEFT JOIN gameRoms gr on gr.gameid = gs.id\
           WHERE gs.`system` in (SELECT sys.id FROM systems sys WHERE sys.parent =\
           (SELECT sys1.parent FROM systems sys1 WHERE sys1.id = %s))\
           AND ((gn.`text` LIKE %s) or (gr.romfilename LIKE %s))"
    val = (systemid,qName,qName)
    results,success = queryDB(sql,val,False,mydb,False,True)
    gameId = 0
    if results:
        logging.debug('###### THERE ARE RESULTS, WILL TRY TO MATCH WITH '+srchName)
        if isinstance(results[0],tuple):
            logging.debug ('###### '+str(results))            
            logging.debug ('###### I FOUND SEVERAL CANDIDATES')
            for result in results:
                logging.debug ('###### COMPARING WITH '+result[2]+' AND '+result[3])
                if gameNameMatches(srchName,result[2]) or gameNameMatches(srchName,result[3]):
                    logging.debug('###### THERE IS A MATCH!!!')
                    gameId = result[0]
                    break
                else:
                    logging.debug ('###### NO LUCK THIS TIME')
        else:
            logging.debug ('###### I FOUND ONE CANDIDATE')
            logging.debug (type(results))
            logging.debug('###### '+str(results))
            if gameNameMatches(srchName,results[2]) or gameNameMatches(srchName,results[3]):
                gameId = results[0]
                logging.debug ('####### FOUND IT!! '+str(results))
    else:
        logging.debug ('####### COULD NOT FIND '+gameName+' FOR SYSTEM '+str(systemid))
    if gameId == 0 and not isArcade:
        logging.debug ('###### WILL CHECK IF IT IS A COMPRESSED FILE')
        exten = gameName[gameName.rindex('.')+1:].upper()
        logging.debug ('###### EXTENSION IS '+exten)
        if exten == 'ZIP' or exten == '7Z':
            logging.debug ('###### IT IS A COMPRESSED FILE')
            gameId = processCompressedFile(path,gameName,systemid,exten)
        else:
            gameId = 0
            logging.debug ('###### IT IS NOT A COMPRESSED FILE, BAD LUCK')
    return gameId

def processCompressedFile(filepath,filename,systemid,exten):
    gameId = 0
    if exten == 'ZIP':
        gameId = processZipFile(filepath,filename,systemid)
    if exten == '7Z':
        logging.error ('###### 7Z NOT YET IMPLEMENTED, SORRY')
        #gameId = process7ZFile(filepath,filename,systemid)
    return gameId


def querySHAinDB(mysha1='None',mymd5='None',mycrc='None',filename='',sysid=0,path=''):
    logging.debug ('###### CONNECTING TO DB TO LOCATE DATA FOR '+mysha1)
    sql = "SELECT  CONCAT ( '{\"jeu\":{\"id\":\"',mygameid,'\",\"noms\":[',COALESCE(names_result,''),'],\"synopsis\":[',COALESCE(synopsis_result,''),']\n\
            ,\"medias\":[',COALESCE(media_result,'') ,'],',COALESCE(system_result,'\"systeme\":{}'),',',COALESCE(editor_result,'\"editeur\":{}'),',',COALESCE(date_result,'\"dates\":{}'),'}}') as json\n\
            FROM (SELECT gr.gameid as mygameid,\n\
            GROUP_CONCAT(DISTINCT '{\"region\":\"',gn.region,'\",\"text\":\"',CONVERT(gn.`text` USING ascii),'\"}') as names_result,\n\
            GROUP_CONCAT(DISTINCT '{\"langue\":\"',gs.langue,'\",\"text\":\"',CONVERT(gs.`text` USING ascii),'\"}') as synopsis_result,\n\
            GROUP_CONCAT(DISTINCT '{\"type\":\"',gm.`type`,'\",\"url\":\"',gm.url,'\",\"region\":\"',gm.region,'\",\"format\":\"',gm.`format`,'\"}') as media_result,\n\
            GROUP_CONCAT(DISTINCT '\"systeme\":{\"id\":\"',sm.id,'\",\"text\":\"',CONVERT(sm.`text` USING ascii),'\"}') as system_result,\n\
            GROUP_CONCAT(DISTINCT '\"editeur\":{\"id\":\"',ed.id,'\",\"text\":\"',CONVERT(ed.`text` USING ascii),'\"}') as editor_result,\n\
            GROUP_CONCAT(DISTINCT '\"dates\":{\"region\":\"',gd.region ,'\",\"text\":\"',gd.`text`,'\"}') as date_result\n\
            FROM gameRoms gr\n\
            LEFT JOIN gameNames gn ON gn.gameid = gr.gameid\n\
            LEFT JOIN gameSynopsis gs ON gs.gameid = gr.gameid\n\
            LEFT JOIN gameMedias gm ON gm.gameid = gr.gameid\n\
            LEFT JOIN games g2  on g2.id = gr.gameid\n\
            LEFT JOIN systems sm on sm.id = g2.system\n\
            LEFT JOIN editors ed on ed.id = g2.editeur\n\
            LEFT JOIN gameDates gd on gd.gameid = gr.gameid where gr.romsha1 = %s or gr.rommd5 = %s or gr.romcrc =%s) as gameinfo"
    val = (mysha1,mymd5,mycrc)
    result,success = queryDB(sql,val,False,mydb)
    return result

def locateShainDB(mysha1='None',mymd5='None',mycrc='None',filename='',sysid=0,path=''):
    result = querySHAinDB(mysha1,mymd5,mycrc,filename,sysid,path)
    if result is not None:
        logging.debug ('###### RECORD FOUND IN DB')
        logging.debug ('###### I\'VE FOUND WHAT YOU\'RE LOOKING FOR IN THE V2 DB')
        ###### NEED TO vREPLACE EOL CHARACRTES WITH DOUBLE BACKSLASH ESCAPED EQUIVALENT FOR DICT CONVERSION TO WORK
        result = result.replace('\x0d\x0a','\\r\\n').replace('\x0a','').replace('\x09','').replace('\x0b','').replace('  ','').replace('\r','')
        logging.debug ('###### WE DID FIND SOMETHING '+repr(result))
        if '{"jeu":{"id":"0",' in result:
            logging.debug ('###### ID 0 FOUND, GOING BACK TO EMPTY')
            myres = ''
        else:
            try:
                logging.debug ('###### CONVERTING VIA JSON')
                myres = json.loads(result)
            except Exception as e:
                logging.error ('###### CANNOT CONVERT VIA JSON - CONVERTING VIA AST '+str(e))
                try:
                    myres = ast.literal_eval(result)
                except Exception as e:
                    logging.error ('###### CANNOT CONVERT VIA AST '+str(e)+' RETURNING NOTHING '+str(result))
                    return ''
            logging.debug ('###### GOT A RESULT AND I\'M RETURNING IT')
        return myres
    else:
        isArcade = isArcadeSystem(sysid)
        gameID = findMissingGame(filename,sysid,path,isArcade)
        logging.debug ('###### GAMEID RETURNED IS '+str(gameID))
        if gameID == 0:
            logging.debug('###### CHECKING IF IT IS AN ARCADE GAME AND CHECK BY REAL NAME JUST IN CASE')
            if isArcade:
                logging.error ('###### GOING TO GRAB ARCADE NAME')
                arcadename = getArcadeName(filename)
                logging.error ('###### GRABBED NAME IS ['+arcadename+']')
                if arcadename != '':
                    logging.error ('###### GOING TO LOOK '+arcadename+' UP')
                    gameID = findMissingGame(arcadename,sysid,path,isArcade)
        if gameID is not None:
            try:
                myRom = {'romfilename':filename,'romsha1':mysha1.upper(),'romcrc':mycrc.upper(),'rommd5':mymd5.upper(),'beta':'0','demo':'0','proto':'0','trad':'0','hack':'0','unl':'0','alt':'0','best':'0','netplay':'0'}
                myRoms = [myRom]
            except Exception as e:
                logging.error ('###### ERROR CREATING ROM OBJECT '+str(e))
            logging.debug ('###### MY ROM IS  '+str(myRom))
            insertGameRomsInDB(gameID,myRoms,sysid,False)
            if gameID !=0:
                return locateShainDB(mysha1,mymd5,mycrc,filename,sysid,path)
            else:
                return None
        else:
            logging.debug ('###### COULD NOT GET ROM INFORMATION')
            return None

def updateDB(mysha1,response):
    logging.debug ('###### CALLED UPDATE DB WITH RESPONSE '+str(response))
    if response == 'ERROR':
        logging.debug ('###### GOT AN ERROR FROM API CALL SO I\'M NOT UPDATING THE DB HASH')
        return False 
    if not 'urlopen error' in response:
        sql = "REPLACE INTO hashes (hash, response) VALUES (%s, %s)"
        val =[(str(mysha1),str(response))]
        result,success = queryDB(sql,val,True,mydb)
        if success:
            logging.debug ('###### COULD UPDATE DB')
        else:
            logging.debug ('###### COULD NOT UPDATE DB')
        return success
    else:
        logging.debug ('###### THERE WAS A PROBLEM WITH RESPONSE FROM API')
        return False

def deleteHashFromDB(filename):
    sql = 'DELETE FROM filehashes WHERE file = "%s"'
    val =(str(filename))
    result,success = queryDB(sql,val,True,mydb)
    if success:
        logging.debug ('###### COULD DELETE FROM DB')
    else:
        logging.debug ('###### COULD NOT DELETE FROM DB')
    return success

def updateDBFile(origfile,destfile):
    sql = 'UPDATE filehashes SET file = %s WHERE file = %s'
    val =(str(destfile),str(origfile))
    result,success = queryDB(sql,val,True,mydb)
    if success:
        logging.debug ('###### COULD UPDATE FILE IN DB')
    else:
        logging.debug ('###### COULD NOT UPDATE FILE IN DB')
    return success

def getGameInfo(CURRSSID, pathtofile, file, mymd5, mysha1, mycrc, sysid):
    ### THIS IS WHERE EVERYTHING HAPPENS
    ### IS ANY OF THE PARAMETERS EMPTY?
    if mymd5 == '' or mysha1 == '' or mycrc == '':
        # YES, GO BACK
        return file,'ERROR'
    logging.debug ('###### GETTING GAME INFORMATION')
    ### THIS IS THE NAME OF THE API WE HAVE TO CALL
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
    response = locateShainDB(mysha1,mymd5,mycrc,file,sysid,pathtofile)
    ###logging.info ('######## '+str(response))
    ### DID WE SOMEHOW GOT AN EMPTY RESPONSE?
    if response=='' or response == None:
        ### THERE IS AN EMPTY RESPONSE BACK FROM LOOKUP, THIS GAME CANNOT BE FOUND, CREATE EMPTY
        response = dict()
        response['jeu']=dict()
        response['jeu']['noms']=[{"region":"ss","text":file}]
        response['jeu']['synopsis']=[{"langue":"en","text":"There is no description for this game"}]
        response['jeu']['medias']=[]
        response['jeu']['dates']=[]
        response['jeu']['id']='0'        
    else:
        ### WE DID GET A RESPONSE
        ### DID WE GET A QUOTA LIMIT?
        if response == 'QUOTA' or response =='ERROR':
            ### YES, SO RETURN TO SKIP THE FILE IF POSSIBLE
            logging.info ('###### '+response+' RETURNED BY API')
            return file, response
        ### DID THE SCRAPER RETURN A VALID ROM?
        ### USUALLY IN A VALID RESPONSE WE WOULD HAVE THE JEU KEY
        ### AND OF COURSE THE ANSWER WILL NOT BE EMPTY
        logging.debug ('####### RESPONSE '+str(response))
        if not 'jeu' in response:
            logging.debug('###### GOT A WEIRD ANSWER')
            return file,response
        else:
            if not isinstance(response,dict):
                logging.debug ('###### RESPONSE IS A STRING - CONVERTING')
                response = ast.literal_eval(response)
                ### YES WE DID
            logging.debug ('#### JEU IS IN RESPONSE')
            ### ASSIGN NEW RESPONSE TO OLD ONE, SO WE DO NOT CONFUSE OURSELVES
            if not UPDATEDATA:
                return file,response
    return file,response

def getSystemName (sysid):
    logging.debug ('###### GOING TO GRAB SYSTEM NAME FROM LOCALDB')
    sql = 'SELECT `text` FROM systems WHERE id = %s'
    val = (sysid,)
    result,success = queryDB(sql,val,True,mydb)
    if success:
        logging.debug ('###### COULD LOCATE SYSTEM IN DB')
    else:
        logging.debug ('###### COULD NOT LOCATE SYSTEM IN DB')
    return result


def getSystemForRom(rom,sysid):
    file,romInfo = getGameInfo(CURRSSID,rom,rom[rom.rindex('/')+1:],md5(rom),sha1(rom),crc(rom),sysid)
    logging.debug ('###### RETURN FROM ROM INFO '+str(type(romInfo)))
    if romInfo == '' or romInfo == 'QUOTA' or romInfo == 'ERROR':
        return None
    try:
        if not isinstance(romInfo,dict):
            logging.debug ('###### WE DID NOT GET A DICT - CONVERTING')
            romInfo=ast.literal_eval(romInfo)
        else: 
            logging.debug ('###### WE ALREADY GOT A DICT - NO NEED TO CONVERT')
    except Exception as e:
        logging.error ('###### CANNOT CONVERT TO DICT '+str(e))
    if romInfo :
        logging.debug ('###### WE CAN PROCESS THE ROM INFO')
        try:
            mysisid = romInfo['jeu']['systeme']['id']
        except:
            try:
                mysisid = romInfo['jeu']['systemeid']
                logging.debug ('####### JEU/SYSID NOT FOUND')
            except:
                try:
                    mysisid = romInfo['systemeid']
                except:
                    logging.debug ('####### SYSID NOT FOUND EITHER, DEFAULTING TO ZERO')
                    mysisid = 0
        return getSystemName(mysisid)
    else:
        return getSystemName(0)

def myFileCopy(origin,destination):
    logging.debug ('###### GOING TO TRY TO COPY '+origin+' INTO '+destination)
    if (not os.path.isfile(origin)):
        logging.debug ('###### ORIGIN FILE '+origin+' DOES NOT EXIST')
        return False
    if (not os.path.isfile(destination)):
        logging.debug ('###### DESTINATION FILE DOES NOT EXISTS, GOING TO COPY')
        try:
            logging.debug ('###### TRYING TO COPY FILE')
            copyfile(origin,destination)
            logging.debug ('###### COPY DONE')
        except Exception as e:
            logging.error ('###### ERROR COPYING FILE '+str(e))
    else:
        if (os.stat(origin).st_size != os.stat(destination).st_size):
            logging.debug ('###### DESTINATION FILE EXISTS BUT SIZE DIFFERS, GOING TO COPY')
            copyfile(origin,destination)
        else:
            logging.debug ('###### FILE '+destination+' ALREADY EXISTS')
    return False

def copyRoms (systemid,systemname,path,CURRSSID,extensions,outdir):
    ### COPY ROMS FOR SYSTEM ID IN PATH TO OUTDIR WITH NEW PATH AS SYSTEM WHERE THE ROM BELONGS TO
    commcount = 0
    foundSys = []
    if outdir[-1:] != '/':
        outdir = outdir + '/'
    logging.info ('###### GOING TO COPY TO DIRECTORY '+outdir)
    logging.debug ('###### GOING TO GET FILE LIST FOR PATH ['+str(extensions)+']')
    filelist = getRomFiles(path,extensions)
    logging.debug ('###### GOING TO ITERATE THROUGH FILES AND SEE WHERE THEY BELONG')
    if path[-1:] != '/':
        path = path + '/'
    logging.error ('###### STARTING SYSTEM '+str(systemname))
    for file in filelist:
        logging.info ('-+-+-+-+-+-+ STARTING COPYING '+str(file)+' -+-+-+-+-+-+ ')
        '''
        commcount = commcount +1
        if commcount == 50:
            try:
                mydb.commit()
            except Exception as e:
                logging.error('###### COULD NOT COMMIT '+str(e))
            commcount = 0
        '''
        newsys = dict()
        origfile = path+file
        logging.debug ('####### GOING TO PROCESS SORT FOR FILE '+origfile)
        romSys = getSystemForRom(origfile,systemid)
        logging.debug ('###### SYSTEM FOR ROM IS '+str(romSys))
        if romSys:
            origsystem = path[path[:-1].rindex('/')+1:-1]
            ### DESTINATION FILES
            videoofile = 'videos/'+sha1(origfile).lower()+'-video.mp4'
            imageofile = 'images/'+sha1(origfile).lower()+'-image.png'
            videofile = 'videos/'+sha1(origfile)+'-video.mp4'
            imagefile = 'images/'+sha1(origfile)+'-image.png'
            bezelfile = file + '.cfg'
            newsys['name']=romSys.lower().replace(' ','').replace('.','')
            newsys['fullname']=romSys
            newsys['path']=outdir + newsys['name'].replace('/','-')
            newsys['extension']=''
            for ext in extensions:
                newsys['extension']=newsys['extension']+' '+ext
            newsys['command']=''
            newsys['platform']=newsys['name']
            newsys['theme']=newsys['name']
            newsys['ssname']=newsys['name']
            if newsys not in foundSys:
                logging.info ('###### ADDING SYSTEM '+str(newsys))
                foundSys.append(newsys)
            destfile = newsys['path']+'/'+file
            logging.debug ('###### GOING TO COPY ROM '+origfile+' TO '+destfile)
            destpath = destfile[:destfile.rindex('/')]
            if not os.path.isdir(destpath):
                try:
                    os.mkdir(destpath)
                except Exception as e:
                    logging.error ('###### COULD NOT CREATE DIRECTORY '+str(e))
            destpath = destpath + '/' + origsystem + '/'
            destfile = destpath + file
            if not os.path.isdir(destpath):
                try:
                    os.mkdir(destpath)
                except Exception as e:
                    logging.error ('###### COULD NOT CREATE DIRECTORY '+str(e))
            destvidpath = destpath+'videos/'
            if not os.path.isdir(destvidpath):
                try:
                    os.mkdir(destvidpath)
                except Exception as e:
                    logging.error ('###### COULD NOT CREATE DIRECTORY '+str(e))
            destimgpath = destpath+'images/'
            if not os.path.isdir(destimgpath):
                try:
                    os.mkdir(destimgpath)
                except Exception as e:
                    logging.error ('###### COULD NOT CREATE DIRECTORY '+str(e))
            logging.debug ('###### GOING TO COPY ROM ')
            myFileCopy(origfile,destfile)
            thisfile = path+videoofile
            thisdfile = destpath+videofile
            logging.debug ('###### GOING TO COPY VIDEO ')
            myFileCopy(thisfile,thisdfile)
            thisfile = path+imageofile
            thisdfile = destpath+imagefile
            logging.debug ('###### GOING TO COPY IMAGE ')
            myFileCopy(thisfile,thisdfile)
            thisfile = path+bezelfile
            thisdfile = destpath+bezelfile
            logging.debug ('###### GOING TO COPY BEZEL ')
            myFileCopy(thisfile,thisdfile)
        else:
            logging.error ('###### FAILED TO COPY ROM '+origfile+' TO DESTINATION')
        logging.info ('-+-+-+-+-+-+ FINISHED COPYING '+str(file)+' -+-+-+-+-+-+ ')
    logging.info ('###### FINISHED SYSTEM '+str(systemname))
    return foundSys

def getAllGames(sysid):
    ### return a list with all game ID's for that system
    sql = 'SELECT DISTINCT ID FROM games where system = %s'
    vals = (sysid,)
    gameList = queryDB(sql,vals,False,mydb,False)
    logging.debug (type(gameList[0]))
    try:
        retGameList=[]
        for restup in gameList[0]:
            retGameList.append(int(restup[0]))
        logging.debug (str(retGameList))
        return retGameList
    except Exception as e:
        logging.error ('####### ERROR '+str(e))
        return []

def writeToMissingFile(notHaveList,listMissingFile,system):
    logging.debug ('###### GOING TO WRITE MISSING FILE ['+listMissingFile+']')
    f = open(listMissingFile,'a+')
    try:
        logging.info ('###### WRITING SYSTEM '+str(system))
        f.write('SYSTEM : '+system+'\r\n')
    except Exception as e:
        logging.error ('###### SYSTEM IS INVALID '+str(e))
    for id in notHaveList:
        query = "SELECT  CONCAT ( 'SCREENSCRAPER LINK https://screenscraper.fr/gameinfos.php?gameid=%s\r\nGAME NAMES:\r\n',COALESCE(names_result,'NOT KNOWN NAMES'),'\r\nROMS:\r\n',\
                 COALESCE(roms_result,'NOT KNOWN ROMS')) as missing_game\
                 FROM (SELECT gr.gameid as mygameid,\
                 GROUP_CONCAT(DISTINCT 'Game Name : ',CONVERT(gn.`text` USING ascii),'\r\n'  SEPARATOR '' ) as names_result,\
                 GROUP_CONCAT(DISTINCT 'Rom Name : ',gr.romfilename,'\r\n' SEPARATOR '' ) as roms_result\
                 FROM gameRoms gr\
                 LEFT JOIN gameNames gn ON gn.gameid = gr.gameid WHERE gr.gameid = %s ) as gameinfo"
        vals = (id,id)
        result = queryDB(query,vals,False,mydb)
        try:
            f.write('----------------------------------------------------------------------------------------\r\n')
            f.write(result[0])
            f.write('----------------------------------------------------------------------------------------\r\n')
        except Exception as e:
            logging.error ('###### CANNOT WRITE TO MISSING FILE '+str(e))
    f.write('++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++\r\n')
    f.close()


def scrapeRoms(CURRSSID,listMissingFile,sortRoms=False,outdir=''):
    ### OPEN SYSTEM CONFIGURATION
    with open(sysconfig, 'r') as xml_file:
        tree = ET.ElementTree()
        tree.parse(xml_file)
    ### GET ALL SYSTEMS IN THE CONFIG FILE
    systems = getAllSystems(CURRSSID)
    if sortRoms:
        newSystems = []
    ### CHECK IF WE HAVE SYSTEMS OR NOT
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
                systemname = 'unknown'
                ### INITIALIZE VARIABLE
                path = ''
                ### INITIALIZE VARIABLES
                sysname ='unknown'
                syscmd = ''
                sysplat = ''
                systheme = ''
                ### ITERATE THROU CHILD TAGS OF SYSTEM
                for system in child:
                    ##logging.debug('****** '+str(system.tag)+' **** '+str(system.text))
                    if system.tag == 'command':
                        try:
                            ### CREATE A LIST WITH ALL VALID EXTENSIONS (USUALLY THE EXTENSIONS ARE SEPARATED BY A SPACE IN THE CONFIG FILE)
                            logging.debug ('###### COMMAND FOUND '+system.text)
                            syscmd = system.text
                        except:
                            ### IF WE CANNOT GET A LIST OF EXTENSIONS FOR A SYSTEM WE DEFAULT TO 'ZIP'
                            syscmd = 'NO COMMAND'
                    if system.tag == 'platform':
                        try:
                            ### CREATE A LIST WITH ALL VALID EXTENSIONS (USUALLY THE EXTENSIONS ARE SEPARATED BY A SPACE IN THE CONFIG FILE)
                            sysplat = system.text
                        except:
                            ### IF WE CANNOT GET A LIST OF EXTENSIONS FOR A SYSTEM WE DEFAULT TO 'ZIP'
                            sysplat = 'EMPTY'
                    if system.tag == 'theme':
                        try:
                            ### CREATE A LIST WITH ALL VALID EXTENSIONS (USUALLY THE EXTENSIONS ARE SEPARATED BY A SPACE IN THE CONFIG FILE)
                            systheme = system.text
                        except:
                            ### IF WE CANNOT GET A LIST OF EXTENSIONS FOR A SYSTEM WE DEFAULT TO 'ZIP'
                            systheme = 'EMPTY'
                    if system.tag == 'extension':
                        try:
                            ### CREATE A LIST WITH ALL VALID EXTENSIONS (USUALLY THE EXTENSIONS ARE SEPARATED BY A SPACE IN THE CONFIG FILE)
                            extensions = system.text.split(' ')
                        except:
                            ### IF WE CANNOT GET A LIST OF EXTENSIONS FOR A SYSTEM WE DEFAULT TO 'ZIP'
                            extensions = ['zip']
                    if system.tag == 'ssname':
                        ### CHECK FOR EXTENSION TAG, THAT HOLDS THE LIST OF VALIDD EXTENSIONS FOR THE SYSTEM
                        ### THIS IS A SPECIAL TAG, IT HAS THE SYSTEM NAME AS DEFINED IN THE SCRAPING SITE, THIS IS TO MATCH AND GET SYSTEM ID
                        try:
                            sysname = system.text.upper()
                        except Exception as e:
                            ### SO WE DIDN'T HAVE A SPECIAL TAGE, SYSTEM IS UNKNOWN
                            sysname = 'unknown'
                            logging.error('###### ERROR GETTING LOCAL SYSTEM ' + str(e))
                        ### LOGIC TO FIND systemid
                        foundsys = False
                        for mysystem in systems:
                            ### API RETRUS SOMETIMES MORE THAN ONE SYSTEM NAME SO WE NEED TO ITERATE THROUGH ALL OF THEM
                            for apisysname in mysystem['noms']:
                                logging.debug ('###### COMPARING '+sysname.upper()+' WITH '+mysystem['noms'][apisysname].upper())
                                if sysname.upper()==mysystem['noms'][apisysname].upper():
                                    ### WE FOUND A MATCH SO WE ASSIGN A SYSTEM ID
                                    systemid = str(mysystem['id'])
                                    systemname = mysystem['noms']
                                    logging.debug ('###### FOUND ID '+systemid+' FOR SYSTEM '+sysname)
                                    foundsys = True
                                    ### AND WE SKIP
                                    break
                            if foundsys:
                                break
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
                    ### CHECK IF THERE IS A MARQUEE DIRECTORY IF NOT WE CREATE IT
                    if not os.path.isdir(path+'/marquees'):
                        os.mkdir(path + '/marquees')
                    logging.info ('###### DOING SYSTEM ' + str(path)+ ' looking for extensions '+str(extensions))
                    ### SO WE START WITH THE SYSTEM PROCESSING
                    if sortRoms :
                        fetchedSystems = copyRoms (systemid,systemname,path,CURRSSID,extensions,outdir)
                        for fsys in fetchedSystems:
                            logging.debug ('###### COMPLETING FOUND SYSTEM '+fsys['name'])
                            logging.debug ('###### COMMAND '+str(syscmd))
                            fsys['command']=syscmd
                            logging.debug ('###### PLATFORM '+str(sysplat))
                            fsys['platform']=sysplat
                            logging.debug ('###### THEME '+str(systheme))
                            fsys['theme']=systheme
                            logging.debug ('###### ADDING FOUND SYSTEMS TO EXISTING ONES')
                            if fsys not in newSystems and fsys['name'].upper() != 'UNKNOWN':
                                newSystems.append(fsys)      
                    else:
                        sysGameList = getAllGames(systemid)
                        notHaveList = grabData(systemid, path, CURRSSID,extensions,sysGameList)
                        logging.debug('###### FILE FOR LIST OF MISSING GAMES IS ['+listMissingFile+']')
                        if listMissingFile!='':
                            logging.info ('###### GOING TO WRITE MISSING FILE')
                            writeToMissingFile(notHaveList,listMissingFile,sysname)
                        logging.debug ('###### DO NOT HAVE LIST IS '+str(notHaveList))
                    ### WE GO TO NEXT USER INFO
                    CURRSSID = CURRSSID + 1
                    if CURRSSID == len(config.ssid):
                        CURRSSID = 0
                else:
                    logging.error ('###### CANNOT FIND PATH '+path)
            else:
                logging.info ('###### SKIPPING SYSTEM')
    logging.info ('----------------- ALL DONE -------------------')
    if sortRoms:
        return newSystems

def transformFilename(fileName):
    logging.debug ('###### RECEIVED ORIGINAL FILENAME '+fileName)
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
    logging.debug ('###### RETURNING CONVERTED FILENAME '+fileName)
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

###############
def gameNameMatches(orig,chkname):
    ## Convert non ascii codes to normal codes
    ##for chk in chkname['noms']:
    ###### Remove parentehsis and first space
    logging.debug ('###### CHECKING '+orig+' WITH '+chkname)
    if orig.upper() == chkname.upper():
        logging.debug ('///////'+chkname+'//////'+orig)
        return True
    kname = orig.replace('_',' ')
    if kname.upper() == chkname.upper():
        logging.debug ('///////'+kname+'//////'+orig)
        return True
    if '.' in chkname:
        unext = chkname[:chkname.rindex('.')]
        if orig.upper() == unext.upper():
            logging.debug ('///////'+chkname+'//////'+unext)
            return True
        kname = orig.replace('_',' ')
        if kname.upper() == unext.upper():
            logging.debug ('///////'+kname+'//////'+unext)
            return True
    rmname = re.sub(r'\s?\(.*\)','',chkname)
    cname = re.sub(r'\s?\(.*\)','',kname)
    dname = re.sub(r'\s?\[.*\]','',cname)
    ckname = re.sub(r'\s[V|v]\d*.\d*','',dname)
    #ckname = re.sub(r'(?<!^)(?=[A-Z])', ' ', qname).replace('  ',' ')
    logging.debug ('###### COMPARE ['+rmname+'] WITH ['+ckname+']')
    #sys.exit()
    if '.' in rmname:
        rmname=rmname[:rmname.rindex('.')]
    if rmname.upper() == ckname.upper():
        logging.debug ('///////'+rmname+'//////'+orig)
        return True
    chk = chkname
    '''
    try:
        chk = chk.encode('ascii', 'ignore')
    except Exception as e:
        logging.error ('###### ERROR WHILE ENCODING RETURNED GAME TO ASCII '+str(e))
    ### 'NN TODO
    '''
    logging.debug ('####### NAME GRABBED - NAME INFERRED')
    if chkNamesMatch(chk.upper(),replace_roman_numerals(orig.upper())):
        logging.debug ('###### NAME MATCHES')
        return True
    if chkNamesMatch(chk.upper().replace('!',''),orig.upper()):
        logging.debug ('###### NAME MATCHES')
        return True
    if chkNamesMatch(chk.upper().replace('.',''),orig.upper()):
        logging.debug ('###### NAME MATCHES')
        return True
    if chkNamesMatch(chk.upper(),orig.upper()):
        logging.debug ('###### NAME MATCHES')
        return True
    if chkNamesMatch(chk.upper(),re.sub('\(.\)','',orig.upper()).strip()):
        logging.debug ('###### NAME MATCHES')
        return True
    if chkNamesMatch(chk.upper(),re.sub('\[.\]','',orig.upper()).strip()):
        logging.debug ('###### NAME MATCHES')
        return True
    if chkNamesMatch(chk.upper(),re.sub('\(.\)\[.\]','',orig.upper()).strip()):
        logging.debug ('###### NAME MATCHES')
        return True
    if chkNamesMatch(chk.upper(),re.sub('\[.\]\(.\)','',orig.upper()).strip()):
        logging.debug ('###### NAME MATCHES')
        return True
    if chkNamesMatch(chk.upper(),orig.replace(',','').upper()):
        logging.debug('###### NAME MATCHES')
        return True
    if chkNamesMatch(chk.upper(),orig.replace(' AND ',' & ').upper()):
        logging.debug ('###### NAME MATCHES')
        return True
    if chkNamesMatch(chk.upper(),orig.replace(' & ',' AND ').upper()):
        logging.debug ('###### NAME MATCHES')
        return True
    if chkNamesMatch(chk.replace(' - ',' ').upper(),orig.upper()):
        logging.debug ('###### NAME MATCHES')
        return True
    if chkNamesMatch(chk.upper(),orig.replace(' Dr ',' Dr. ').upper()):
        logging.debug ('###### NAME MATCHES')
        return True
    if chkNamesMatch(chk.upper(),orig.replace(':','-').upper()):
        logging.debug ('###### NAME MATCHES')
        return True
    if chkNamesMatch(chk.upper(),orig.replace(':',' -').upper()):
        logging.debug ('###### NAME MATCHES')
        return True
    if chkNamesMatch(chk.upper(),orig.replace(':',' - ').upper()):
        logging.debug ('###### NAME MATCHES')
        return True
    if chkNamesMatch(chk.upper(),orig.replace(':',' -').upper()):
        logging.debug ('###### NAME MATCHES')
        return True
    if chkNamesMatch(chk.upper(),orig.upper()+' THE'):
        logging.debug ('###### NAME MATCHES')
        return True
    if fuzzyMatch(chk,orig):
        logging.debug ('###### NAME MATCHES')
        return True          
    matches = re.search('\w*\d',orig)
    if matches:
        splitnum = matches.group(0)
        newint = re.sub (r'(\d)',r' \1',splitnum)
        splitnum = re.sub('\w*\d',newint,orig)
        if chkNamesMatch(chk.upper(),splitnum.upper()):
            logging.debug ('###### NAME MATCHES')
            return True
        if chkNamesMatch(chk.upper(),splitnum.upper()+' THE'):
            logging.debug ('###### NAME MATCHES')
            return True
    logging.debug ('###### THERE IS NO MATCH')
    return False

def nameFromArcadeCSV(name):
    with open('/home/pi/arcade_names.csv') as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=',')
        for row in csv_reader:
            if row[0].upper() == name.upper():
                logging.debug ('###### FOUND MATCH FOR '+row[1])
                return row[1]
        logging.info ('###### DID NOT FIND MATCH FOR '+name)
    return ''

def getArcadeName(name):
    callURL = 'http://www.mamedb.com/game/'+name+'.html'
    callURL2 = 'http://mamedb.blu-ferret.co.uk/game/'+name+'/'
    callURL3 = 'http://adb.arcadeitalia.net/dettaglio_mame.php?game_name=' + name
    logging.info ('###### GETTING ARCADE NAME IN URL '+callURL)
    #namefromcsv = nameFromArcadeCSV(name)
    #if namefromcsv != '':
    #    return namefromcsv
    try:
        response = callURL(callURL) 
        gamename = re.findall("<title>(.*?)<\/title>", response)[0].replace('Game Details:  ','').replace(' - mamedb.com','')
        logging.info ('###### FOUND GAME IN MAMEDB '+gamename)
        return gamename
    except:
        logging.error('###### COULD NOT GET ARCADE NAME FROM MAMEDB ')
        logging.debug('###### TRYING WITH BLU FERRET IN URL '+callURL2)
        try:
            response = callURL(callURL2) 
            gamename = re.findall("\<title\>Game Details:  (\w*).*\<\/title\>", response[0])
            logging.info ('###### FOUND GAME IN BLU FERRET '+gamename)
            return gamename
        except:
            logging.error ('###### COULD NOT GET NAME FROM BLU FERRET')
            logging.debug('###### TRYING WITH ARCADE ITALIA IN URL '+callURL3)
            try:
                response = callURL(callURL3) 
                gamename = re.findall("<title>(.*?)<\/title>", response)[0].replace(' - MAME machine','').replace(' - MAME software','')
                gamename = gamename.replace(' - MAME machin...','')
                if gamename.upper()=='ARCADE DATABASE':
                    logging.debug ('###### COULD NOT GET NAME FROM ARCADE ITALIA')
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
        logging.error ('##### COULD NOT DELETE FILE '+file+' : '+str(e))

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
                    logging.debug ('###### DELETED IMAGE '+image)
                except Exception as e:
                    logging.error ('###### COULD NOT DELETE '+image+' '+str(e))
            if video != '':
                try:
                    os.remove(video)
                    logging.debug ('###### DELETED VIDEO '+video)
                except Exception as e:
                    logging.error ('###### COULD NOT DELETE '+video+' '+str(e))
            deleteHashCache(file) 
            logging.debug ('###### REMOVED '+file+' WITH HASH '+sha)


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
    if thisGame == 'QUOTA' or thisGame =='' or thisGame=='ERROR':
        ### The game information is not complete, better not to process
        logging.debug ('###### SKIPPING '+localSHA)
        return
    else:
        matchs = multiDisk(path)
        vmatchs = multiVersion(path)
        cmatchs = multiCountry(path)
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
                    shutil.move(path,destFile)
                except:
                    res = updateDBFile(destFile,path)

def lookUpROMinDB (romsha1,romcrc,rommd5):
    ### LOOKUP ROM IN DB FIRST
    sqlst = 'SELECT gameid from gameRoms gr where romsha1 = "'+romsha1+'" or romcrc = "'+romcrc+'" or rommd5 ="'+rommd5+'"'
    result,success = queryDB(sqlst,(),False,mydb)
    logging.debug ('###### RESULT FROM DB QUERY LOOKUP ROM '+str(result))
    return result

def renameFiles():
    logging.info ('###### - STARTING FILE RENAMING PROCESS')
    ### Exclude directories, or directories where you do not wish to rename files (retropie, etc..)
    excludeDirs = ['/retropie/','/arcade/','/neogeo/','/retropiemenu/']
    ### Connect to DB to get all files
    hashes = getAllGamesinDB()
    procfiles = 0
    logging.debug ('###### - FOUND '+str(len(hashes))+' HASHES IN DB')
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

def insertGameDataInLocalDB(mygame,doupdate):
    logging.debug ('###### GOING TO LOOK UP GAME ID '+str(mygame['id']))
    sqlst = 'SELECT ID FROM games WHERE ID = %s'
    values = (mygame['id'],)
    result,success=queryDB(sqlst,values,False,mydb)
    logging.debug ('###### SERCH RESULT GAVE BACK '+str(result))
    if result != None:
        sqlst = 'UPDATE games SET notgame = %s, topstaff = %s, rotation = %s, cloneof = %s, system =%s, editeur=%s, joueurs = %s WHERE id = %s'
        values = (mygame['notgame'],mygame['topstaff'],mygame['rotation'],mygame['cloneof'],mygame['system'],mygame['editeur'],mygame['joueurs'],mygame['id'])
        result,success=queryDB(sqlst,values,True,mydb)
    else:
        sqlst = 'INSERT INTO games (notgame,topstaff,rotation,cloneof,system,editeur,joueurs,id)\
                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s)'
        values = (mygame['notgame'],mygame['topstaff'],mygame['rotation'],mygame['cloneof'],mygame['system'],mygame['editeur'],mygame['joueurs'],mygame['id'])
        result,success=queryDB(sqlst,values,True,mydb)
    logging.debug ('###### RESULT OF QUERY '+str(success))
    return success

def insertSystemInLocalDb(system):
    sqlst = 'SELECT id FROM systems WHERE id = '+str(system['id'])
    result,success = queryDB(sqlst,(),False,mydb)
    logging.debug ('###### SQL RESULT FROM SYSTEMS EQUALS '+str(result))
    try:
        parent = str(system['parentid'])
    except Exception as e:
        logging.debug ('###### COULD NOT FIND PARENT SYSTEM')
        parent = str(system['id'])
    try:
        recalbox = system['noms']['nom_recalbox']
    except Exception as e:
        logging.debug ('###### COULD NOT FIND RECALBOX NAME')
        recalbox = ''
    try:
        retropie = system['noms']['nom_retropie']
    except Exception as e:
        logging.debug ('###### COULD NOT FIND RETROPIE NAME '+str(e))
        retropie = ''
    try:
        launchbox = system['noms']['nom_launchbox']
    except Exception as e:
        logging.debug ('###### COULD NOT FIND LAUNCHBOX NAME '+str(e))
        launchbox = ''
    try:
        hyperspin = system['noms']['nom_hyperspin']
    except Exception as e:
        logging.debug ('###### COULD NOT FIND HYPERSPIN NAME '+str(e))
        hyperspin = ''
    if (not result) or result == []:
        logging.debug ('###### GOING TO INSERT IN SYSTEMS TABLE')
        values = (system['id'],system['noms']['nom_eu'],system['type'],int(parent),recalbox,retropie,launchbox,hyperspin)
        sqlst = 'INSERT INTO systems (id,`text`,`type`,parent,recalbox,retropie,launchbox,hyperspin) values (%s,%s,%s,%s,%s,%s,%s,%s)'
    else:
        logging.debug ('###### GOING TO UPDATE SYSTEMS TABLE')
        values = (system['noms']['nom_eu'],system['type'],int(parent),recalbox,retropie,launchbox,hyperspin,system['id'])
        sqlst = 'UPDATE systems SET `text`=%s , `type`=%s , parent=%s , recalbox=%s , retropie=%s , launchbox=%s , hyperspin=%s where id = %s'
    result,success = queryDB(sqlst,values,True,mydb)
    return success

def insertEditorInLocalDb(edid,edname):
    sqlst = 'SELECT text FROM editors WHERE id = '+str(edid)
    result,success = queryDB(sqlst,(),False,mydb)
    logging.debug ('###### SQL RESULT FROM EDITORS EQUALS '+str(result))
    if (not result) or result == []:
        logging.debug ('###### GOING TO UPDATE EDITORS TABLE')
        if len(edname) >  100:
	        edname = edname[:99]
        sqlst = 'INSERT INTO editors (id,text) values (%s,%s)'
        values = (str(edid),edname)
        result,success = queryDB(sqlst,values,True,mydb)
        return success

def insertGameNamesInDB(id,names,doupdate):
    try:
        if not isinstance(names,list):
            new_names=[]
            for key in names.keys():
                myname=dict()
                myname['region']=key.replace('nom_','')
                myname['text']= names[key]
                new_names.append(myname)
            names = new_names
            logging.debug('###### NAMES CONVERTED TO '+str(names))
    except Exception as e:
        logging.error ('###### ERROR WHILE CREATING NAMES '+str(e))
    logging.debug ('###### GOING TO ACTUALLY INSERT NAMES IN DB '+str(names))
    for name in names:
        try:
            sql = 'SELECT id FROM gameNames where gameid='+str(id)+' and region ="'+name['region']+'"'
        except Exception as e:
            logging.debug ('###### THERE WAS AN ERROR INSERTING NAMES '+str(e))
            return
        result,success = queryDB(sql,(),True,mydb)
        logging.debug('###### GOT RESULT FROM NAMES CHECK '+str(result))
        if result == None or result == []:
            sqlst = 'INSERT INTO gameNames (gameid,region,text) VALUES (%s,%s,%s)'
            values = (str(id),name['region'],name['text'])
            result,success = queryDB(sqlst,values,True,mydb)
        elif doupdate:
            sqlst = 'UPDATE gameNames SET region=%s ,text=%s where id=%s'
            values = (name['region'],name['text'],result)
            result,success = queryDB(sqlst,values,True,mydb)

def insertSynopsisInDB(id,synopsis,doupdate):
    try:
        if not isinstance(synopsis,list):
            new_syn = []
            for key in synopsis:
                my_syn = dict()    
                my_syn['langue']=key.replace('synopsis_','')
                my_syn['text']=synopsis[key]
                new_syn.append(my_syn)
            synopsis = new_syn
    except Exception as e:
        logging.error ('###### ERROR CREATING SYNOPSIS '+str(e))
    for syn in synopsis:
        try:
            sql = 'SELECT id FROM gameSynopsis where gameid='+str(id)+' and langue ="'+syn['langue']+'"'
        except Exception as e:
            logging.error ('###### THERE IS AN ERROR IN THE SYNOPSIS ['+str(syn)+'] '+str(e))
        result,success = queryDB(sql,(),False,mydb)
        logging.debug('###### GOT RESULT FROM SYNOPSIS CHECK '+str(result))
        if result == None or result == []:
            sqlst = 'INSERT INTO gameSynopsis (gameid,langue,text) VALUES (%s,%s,%s)'
            values = (str(id),syn['langue'],syn['text'])
            result,success = queryDB(sqlst,values,True,mydb)
        elif doupdate:
            sqlst = 'UPDATE gameSynopsis SET langue=%s ,text=%s where id=%s'
            values = (syn['langue'],syn['text'],result)
            result,success = queryDB(sqlst,values,True,mydb)

def insertGameRomsInDB(id,roms,sysid,doupdate):
    logging.debug ('###### INSERTING ROMS IN DB '+str(roms))
    ###### SCREENSCRAPER DOES NOT ALWAYS HAVE SHA,CRC AND MD%
    ###### SO WE HAVE TP CHECK TO AVOID ERRORS
    for rom in roms:
        try:
            romsha1 = rom['romsha1']
        except:
            romsha1 = 'None'
        try:
            romcrc = rom['romcrc']
        except:
            romcrc = 'None'
        try:
            rommd5 = rom['rommd5']
        except:
            rommd5 = 'None'
        if romsha1 == '':
            romsha1 = 'None'
        if rommd5 == '':
            rommd5 = 'None'
        if romcrc == '':
            romcrc = 'None'
        sql = 'SELECT id FROM gameRoms where romsha1="'+romsha1+'" or rommd5="'+rommd5+'" or romcrc="'+romcrc+'"'
        result,success = queryDB(sql,(),True,mydb)
        logging.debug('###### GOT RESULT FROM ROM CHECK '+str(result))
        if result is None or result == []:
            if romsha1 == 'None':
                romsha1 = ''
            if rommd5 == 'None':
                rommd5 = ''
            if romcrc == 'None':
                romcrc = ''
            logging.debug ('####### THE ROM IS NOT IN THE DB')
            sqlst = 'INSERT INTO gameRoms (romfilename,romsha1,romcrc,rommd5,beta,demo,proto,trad,hack,unl,alt,best,netplay,gameid,systemid)\
                     VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)'
            values =(rom['romfilename'],romsha1,romcrc,rommd5,str(rom['beta']),str(rom['demo']),str(rom['proto']),\
                     str(rom['trad']),str(rom['hack']),str(rom['unl']),str(rom['alt']),str(rom['best']),str(rom['netplay']),\
                     str(id),str(sysid))
            logging.debug ('###### GOING TO EXECUTE SQL')
            result,success = queryDB(sqlst,values,True,mydb)
        elif doupdate:
            logging.debug ('###### RESULT IS OF TYPE '+str(type(result)))
            logging.debug ('####### THE ROM IS NOT IN THE DB')
            sqlst = 'UPDATE gameRoms set romfilename=%s,romsha1=%s,romcrc=%s,rommd5=%s,beta=%s,demo=%s,proto=%s,trad=%s,hack=%s,unl=%s,alt=%s,best=%s,netplay=%s,gameid=%s,systemid=%s \
                     WHERE id = %s'
            if romsha1 == 'None':
                romsha1 = ''
            if rommd5 == 'None':
                rommd5 = ''
            if romcrc == 'None':
                romcrc = ''
            values =(rom['romfilename'],romsha1,romcrc,rommd5,str(rom['beta']),str(rom['demo']),str(rom['proto']),\
                     str(rom['trad']),str(rom['hack']),str(rom['unl']),str(rom['alt']),str(rom['best']),str(rom['netplay']),\
                     str(id),str(sysid),result)
            logging.debug ('###### GOING TO EXECUTE SQL')
            result,success = queryDB(sqlst,values,True,mydb)

def mediaConvertor(media,mediaList):
    for key in media.keys():
        if isinstance(media[key],dict):
            mediaList = mediaConvertor(media[key],mediaList)
        else:
            for key in media.keys():
            ## HOW MANY _ : 1 no region, 2, region
                if isinstance(media[key],dict):
                    mediaList = mediaConvertor(media[key],mediaList)
                else:
                    my_media=dict()
                    minfo = key.split('_')
                    should = True
                    for m in minfo:
                        if m in ('sha1','crc','md5'):
                            should = False
                    if should:
                        if len(minfo)>2:
                            my_media['region']=minfo[2].replace('media_','')
                        else:
                            my_media['region']='UNK'
                        my_media['type']=minfo[1]
                        my_media['url']=media[key]
                        my_media['format']=my_media['url'][-3:]
                        mediaList.append(my_media)
                        logging.debug (str(my_media))
    return mediaList

def insertGameMediasInDB(id,medias,sysid,doupdate):
    counter = 0
    if not isinstance(medias,list):
        new_medias = []
        medias = mediaConvertor(medias,new_medias)
    for media in medias:
        try:
            mediaregion = media['region']
        except:
            mediaregion = 'UNK'
        try:
            sql = 'SELECT id FROM gameMedias where gameid='+str(id)+' and region ="'+mediaregion+'" and type = "'+media['type']+'" and format="'+media['format']+'"'
        except Exception as e:
            logging.error ('###### COUL NOT CREATE MEDIA QUERY ['+str(medias)+']'+str(e))
        result,success = queryDB(sql,(),True,mydb)
        logging.debug('###### GOT RESULT FROM MEDIAS CHECK '+str(result))
        if result == None or result == []:
            sqlst = 'INSERT INTO gameMedias (type,url,region,format,cnt,gameid) VALUES (%s,%s,%s,%s,%s,%s)'
            if mediaregion == 'UNK':
                staticURL = 'www.screenscraper.fr/medias/'+str(sysid)+'/'+str(id)+'/'+media['type']+'.'+media['format']
            else:
                staticURL = 'www.screenscraper.fr/medias/'+str(sysid)+'/'+str(id)+'/'+media['type']+'('+mediaregion+').'+media['format']
            logging.debug ('###### STATIC URL FOR MEDIA IS '+staticURL)
            try:
                values = (media['type'],staticURL,mediaregion,media['format'],str(counter),str(id))
            except Exception as e:
                logging.debug ('###### COULD NOT CREATE VALUES '+str(e))
            result,success = queryDB(sqlst,values,True,mydb)
            counter = counter + 1
        elif doupdate:
            sqlst = 'UPDATE gameMedias SET type=%s,url=%s,region=%s,format=%s,cnt=%s,gameid=%s WHERE id = %s'
            if mediaregion == 'UNK':
                staticURL = 'www.screenscraper.fr/medias/'+str(sysid)+'/'+str(id)+'/'+media['type']+'.'+media['format']
            else:
                staticURL = 'www.screenscraper.fr/medias/'+str(sysid)+'/'+str(id)+'/'+media['type']+'('+mediaregion+').'+media['format']
            logging.debug ('###### STATIC URL FOR MEDIA IS '+staticURL)
            try:
                values = (media['type'],staticURL,mediaregion,media['format'],str(counter),str(id),result)
            except Exception as e:
                logging.error ('###### COULD NOT CREATE VALUES '+str(e)+' FOR ID '+str(result))
            result,success = queryDB(sqlst,values,True,mydb)
            counter = counter + 1

def insertGameDatesInDB(id,dates,doupdate):
    if not isinstance(dates,list):
        logging.debug('###### DATES ARE NOT LIST '+str(dates))
        new_dates = []
        for key in dates:
            my_date = dict()    
            my_date['region']=key.replace('date_','')
            my_date['text']=dates[key]
            new_dates.append(my_date)
        dates = new_dates
    for rdate in dates:
        sql = 'SELECT id FROM gameDates where gameid='+str(id)+' and region ="'+rdate['region']+'"'
        result,success = queryDB(sql,(),True,mydb)
        logging.debug('###### GOT RESULT FROM DATES CHECK '+str(result))
        if result == None or result == []:
            sqlst = 'INSERT INTO gameDates (text,region,gameid) VALUES (%s,%s,%s)'
            values = (rdate['text'],rdate['region'],str(id))
            result,success = queryDB(sqlst,values,True,mydb)
        elif doupdate:
            sqlst = 'UPDATE gameDates SET text=%s,region=%s WHERE id = %s'
            values = (rdate['text'],rdate['region'],result)
            result,success = queryDB(sqlst,values,True,mydb)

def insertGameInLocalDb(gameInfo,doupdate):
    logging.debug ('###### GAMEINFO IS '+str(gameInfo))
    game = dict()
    try:
        roms = gameInfo['roms']
        logging.debug ('###### FOUND ROMS '+str(roms)+' '+str(len(roms)))
    except:
        logging.error('###### THIS GAME HAS NO ROMS SO I\'M NOT INSERTING IT')
        return False
    if len(roms) ==0:
        logging.info('###### THIS GAME HAS NO ROMS SO I\'M NOT INSERTING IT')
        return False
    '''else:
        return True
    '''
    try:
        game['id'] = gameInfo['id']
    except Exception as e:
        logging.error ('###### THERE IS NO GAME ID!, CANNOT DO ANYTHING')
        return
    try:
        game['notgame'] = gameInfo['notgame']
    except Exception as e:
        logging.error ('###### ATTRIBUTE NOTGAME NOT FOUND, CREATING DEFAULT FOR '+str(game['id']))
        game['notgame'] = False
    try:
        game['topstaff'] = gameInfo['topstaff']
        if game['topstaff'] == None:
            game['topstaff'] = 0
    except Exception as e:
        logging.error ('###### ATTRIBUTE TOPSTAFF NOT FOUND, CREATING DEFAULT FOR '+str(game['id']))
        game['topstaff'] = 0

    try:
        game['cloneof'] = gameInfo['cloneof']
        if game['cloneof'] == None:
            game['cloneof'] = 0
    except Exception as e:
        logging.error ('###### ATTRIBUTE CLONEOF NOT FOUND, CREATING DEFAULT FOR '+str(game['id']))
        game['cloneof'] = 0

    try:
        game['joueurs'] = gameInfo['joueurs']['text']
    except Exception as e:
        logging.error ('###### ATTRIBUTE PLAYERS NOT FOUND, CREATING DEFAULT FOR '+str(game['id']))
        game['joueurs'] = 0
    try:
        game['rotation'] = gameInfo['rotation']
        if game['rotation'] == None:
            game['rotation'] = 0
    except Exception as e:
        logging.error ('###### ATTRIBUTE ROTATION NOT FOUND, CREATING DEFAULT FOR '+str(game['id']))
        game['rotation'] = 0
    try:
        game['system'] = gameInfo['systeme']['id']
    except Exception as e:
        try:
            game['system'] = gameInfo['systemeid']
        except Exception as e:
            logging.error ('###### ATTRIBUTE SYSTEMID NOT FOUND, CREATING DEFAULT FOR '+str(game['id']))
            game['system'] = 0
    try:
        game['editeur'] = gameInfo['editeur']['id']
        #insertEditorInLocalDb(game['editeur'],gameInfo['editeur']['text'])
    except Exception as e:
        logging.error ('###### ATTRIBUTE EDITOR NOT FOUND, CREATING DEFAULT FOR '+str(game['id']))
        game['editeur'] = 0
    logging.debug ('###### GAME INFO IS '+str(game))
    insertGameDataInLocalDB(game,doupdate)
    try:
        logging.debug ('###### NAMES ARE '+str(gameInfo['noms']))
        insertGameNamesInDB(game['id'],gameInfo['noms'],doupdate)
    except Exception as e:
        logging.error ('###### COULD NOT FIND NAMES FOR THE GAME')
    try:
        synopsis = gameInfo['synopsis']
        insertSynopsisInDB(game['id'],synopsis,doupdate)
    except Exception as e:
        logging.error ('###### COULD NOT FIND SYNOPSIS FOR THE GAME -'+str(e)+' - DEFAULTING')
        ###synopsis = [{'langue':'UNK','text':''}]
    try:
        logging.debug('###### INSERTING ROMS')
        insertGameRomsInDB(game['id'],  gameInfo['roms'],game['system'],doupdate)
    except Exception as e:
        logging.error ('###### COULD NOT FIND ROMS FOR THE GAME - LEAVING EMPTY '+str(e))
    try:
        medias = gameInfo['medias']
        insertGameMediasInDB(game['id'],medias,game['system'],doupdate)
    except Exception as e:
        logging.error ('###### COULD NOT FIND MEDIAS FOR THE GAME -'+str(e)+' - DEFAULTING')
        ##medias = [{'type':'unk','url':'unk','region':'unk','format':'unk'}]
    try:
        dates = gameInfo['dates']
        insertGameDatesInDB(game['id'], dates,doupdate)
    except Exception as e:
        logging.error ('###### COULD NOT FIND DATES FOR THE GAME -'+str(e)+' - DEFAULTING')
        ##dates = [{'region':'unk','text':'0'}]
    return True

def sortRoms(mainDir):
    logging.info ('###### STARTING ROM SORTING PROCESS, ORIGINAL ROMS WILL REMAIN UNTOUCHED')
    systems = scrapeRoms(CURRSSID,'',True,mainDir)
    return systems

if dbRename:
    ### Get all games from DB and rename filenames
    renameFiles()
    scrapeRoms(CURRSSID,'')
    sys.exit(0)


if cleanSystem:
    ### CLEAN SYSTEM, THIS PROCEDURE DELETES ALL DB RECORDS FOR FILES FOUND IN GAMELIST FOR A GIVEN SYSTEM
    cleanSys(cleanSystem)
    sys.exit(0)

def createEsConfig(systems,dir):
    if dir[-1:] != '/':
        dir = dir +'/'
    sysxml = '<systemList>\n'
    for essystem in systems:
        sysxml=sysxml+'\t<system>\n'
        for key in essystem.keys():
            logging.debug ('###### ADDING KEY '+str(key)+' WITH VALUE '+str(essystem[key]))
            try:
                sysxml=sysxml+'\t\t<'+str(key)+'>'+str(essystem[key])+'</'+str(key)+'>\n'
            except:
                logging.error ('###### COULD NOT GET VALUE FOR KEY '+str(key))
                sysxml=sysxml+'\t\t<'+str(key)+'></'+str(key)+'>\n'
        sysxml=sysxml+'\t</system>\n'
    sysxml = sysxml+'</systemList>'
    f = open(dir+"es_systems.cfg", "w")
    f.write(sysxml)
    f.close() 
    return 

def getGameFromAPI(gameid,ssid,doupdate):
    try:
        params =dict(fixParams)
        params['gameid'] = str(gameid)
        params['ssid']=config.ssid[ssid]
    except:
        logging.error ('###### CANNT CREATE PARAMETERS')
    logging.debug('###### GOING TO CALL THE API FOR GAMEID '+str(gameid))
    response = callAPI(fixedURL,'jeuInfos',params,currssid,'2','UPDATE GAME INFO ',True,doupdate)
    shrtparams ='output=jsongameid='+str(gameid)
    #### HAVE TO UPDATE THE LOCALDB CALL
    logging.debug('###### UPDATING RESPONSE FOR APICACHE GAMEID '+str(gameid))
    logging.debug('###### '+str(response))
    if doupdate:
        logging.debug ('###### GOING TO UPDATE GAME IN DB (APICACHE)')
        updateInDBV2Call('jeuInfos.php',shrtparams,response)    
    if 'jeu' in response:
        logging.debug ('###### GOING TO UPDATE GAME IN DB (NORMALIZED)')
        response = callAPI(fixedURL,'jeuInfos',params,currssid,'2','UPDATE GAME INFO ') 
        success = insertGameInLocalDb(response['jeu'],True)
        if not success:
            logging.debug ('###### I COULD NOT INSERT GAME INTO DB BECAUSE IT DID NOT HAS ASSOCIATED ROMS')
            updateInDBV2Call('jeuInfos.php',shrtparams,'NOT FOUND')
            response =''    
    return response

def locateGamesInPage(pagehtml,ssid):
    try:
        gidsrch = re.finditer('gameinfos\.php\?plateforme=\d*&gameid=(\d*)',pagehtml)
        if gidsrch != None:
            logging.info('###### MATCHES '+str(gidsrch))
            procgames = []
            for gid in gidsrch:
                gameid = gid.group(1)
                logging.debug('###### GAME ID IS '+str(gameid))
                logging.info('###### GETTING GAME '+str(gameid)+' INFORMATION VIA API')
                if gameid not in procgames:
                    getGameFromAPI(gameid,ssid,True)
                    procgames.append(gameid)
        else:
            logging.error ('###### DID NOT FIND ANY MEDIA UPDATES IN PAGE ....')
    except Exception as e:
        logging.error ('###### CANNOT GET PAGE INFO '+str(e))
    return

def locateRomInfo(pagehtml,ssid):
    try:
        gidsrch = re.search('gameinfos\.php\?plateforme=\d*&gameid=(\d*)',pagehtml)
        if gidsrch != None:
            logging.debug('###### MATCHES '+str(gidsrch.groups()))
            gid = gidsrch.groups()[0]
            logging.debug('###### GAME ID IS '+str(gid))
            getGameFromAPI(gid,ssid,True)
        else:
            logging.error ('###### ROM DOES NOT EXIST IN SCREENSCRAPER ....')
    except Exception as e:
        logging.error ('###### CANNOT GET ROM INFO '+str(e))
    return

def getRomPage(romid,ssid):
    URL = 'https://www.screenscraper.fr/rominfos.php?&romid='+str(romid)
    success = False
    retries = 10
    while not success and retries > 1:
        try:
            req = requests.get(URL)
            success = True
        except requests.exceptions.Timeout:
            logging.error ('###### REQUEST TIMED OUT')
            retries = retries - 1 
        except requests.exceptions.TooManyRedirects:
            logging.error ('###### URL SEEMS TO BE WRONG '+URL)
        except requests.exceptions.RequestException as e:
            logging.error ('###### UNHANDLED ERROR '+str(e))
            retries = retries -1
    logging.debug ('###### GOT BACK: '+req.text)
    locateRomInfo(req.text,ssid)
    return

def getMediasPage(pagenum,ssid):
    URL = 'https://screenscraper.fr/updatemedias.php?numpage='+str(pagenum)
    success = False
    retries = 10
    while not success and retries > 1:
        try:
            req = requests.get(URL)
            success = True
        except requests.exceptions.Timeout:
            logging.error ('###### REQUEST TIMED OUT')
            retries = retries - 1 
        except requests.exceptions.TooManyRedirects:
            logging.error ('###### URL SEEMS TO BE WRONG '+URL)
        except requests.exceptions.RequestException as e:
            logging.error ('###### UNHANDLED ERROR '+str(e))
            retries = retries -1
    logging.debug ('###### GOT BACK: '+req.text)
    locateGamesInPage(req.text,ssid)
    return

def getInfosPage(pagenum,ssid):
    URL = 'https://screenscraper.fr/update.php?numpage='+str(pagenum)
    success = False
    retries = 10
    while not success and retries > 1:
        try:
            req = requests.get(URL)
            success = True
        except requests.exceptions.Timeout:
            logging.error ('###### REQUEST TIMED OUT')
            retries = retries - 1 
        except requests.exceptions.TooManyRedirects:
            logging.error ('###### URL SEEMS TO BE WRONG '+URL)
        except requests.exceptions.RequestException as e:
            logging.error ('###### UNHANDLED ERROR '+str(e))
            retries = retries -1
    logging.debug ('###### GOT BACK: '+req.text)
    locateGamesInPage(req.text,ssid)
    return

def getNewRoms(id,ssid):
    getRomPage(id,ssid)
    return

def getNewMedias(id,ssid):
    for pageid in range (0,int(id)):
        logging.info ('###### GETTING PAGE '+str(pageid))
        getMediasPage(pageid,ssid)
    return

def getNewInfos(id,ssid):
    for pageid in range (0,int(id)):
        logging.info ('###### GETTING PAGE '+str(pageid))
        getInfosPage(pageid,ssid)
    return


arcadeSystems = getArcadeSystems()

if sortroms !='':
    logging.debug ('###### ARCADE SYSTEMS '+str(arcadeSystems))
    ### SORT YOUR ROMS, IT WILL TAKE YOUR PARAMETER AS DESTINATION DIRECTORY AND CREATE A STRUCTURE
    ### BASED ON THE SYSTEM THE ROM BELONGS TO
    logging.info ('###### GOING TO SORT YOUR ROMS')
    systems = sortRoms(sortroms)
    logging.debug('###### FOUND '+str(systems))
    createEsConfig(systems,sortroms)
    logging.info ('###### FINSHED SORTING YOUR ROMS')
    sys.exit(0)

if getROMS:
    startid = int(startid)
    endid = int(endid)
    currssid = 0
    maxssid = len(config.ssid)
    for romid in range(startid,endid):
        logging.info ('###### TRYING TO FETCH ROM WITH ID '+str(romid))
        getNewRoms(romid,currssid)
        currssid = currssid + 1
        if currssid == maxssid:
            currssid = 0
    logging.info ('###### DONE GETTING ALL NEW ROMS IN RANGE ')
    sys.exit()

if newmedia:
    currssid = 0
    getNewMedias(pageid,currssid)
    logging.info ('###### DONE GETTING ALL NEW MEDIA IN RANGE ')
    sys.exit()

if newinfo:
    currssid = 0
    getNewInfos(pageid,currssid)
    logging.info ('###### DONE GETTING ALL NEW MEDIA IN RANGE ')
    sys.exit()

if migrateDB:
    ###populate systems
    cnt=1
    systems = getAllSystems(0)
    for system in systems:
        logging.debug ('###### SYSTEM '+str(system))
        insertSystemInLocalDb (system)    
    ### first import all games into local DB
    mydb.commit()
    maxssid = len(config.ssid)
    currssid = 0
    gameid = int(startid)
    endid =int(endid)
    if endid == 0:
        numGames = 213650
    else:
        numGames = endid
    logging.info('###### MIGRATING GAMES FROM '+str(gameid)+' UNTIL '+str(endid))
    response = 'QUOTA'
    #### THis game with id Zero is going to be used to handle unknown roms
    zeroGame={'id':'0'}
    insertGameInLocalDb(zeroGame,UPDATEDATA)
    mydb.commit()
    while gameid <= numGames:
        while response == 'QUOTA' or response == 'ERROR':
            response = getGameFromAPI(gameid,currssid,False)
            if response == 'QUOTA':
                logging.debug ('###### QUOTA IS OVER, WAITING UNTIL NEXT DAY')
                waitNewDay('23:00:00')
            if response == 'NOT FOUND':
                logging.error('###### ID '+str(gameid)+' DOES NOT SEEM TO EXIST IN SCREENSCRAPER')
        logging.debug ('####### RESPONSE FROM API CALL ')###+str(response))
        if response != 'ERROR' and response != 'NOT FOUND':
            logging.debug ('###### GOING TO INSERT GAMEID '+str(gameid)+' IN DB')
            sql = 'SELECT id from games where id = %s'
            val = (gameid,)
            exists,success = queryDB(sql,val,False,mydb)
            if isinstance (response,dict):
                if (str(exists) != str(gameid)) or UPDATEDATA:
                    insertGameInLocalDb(response['jeu'],UPDATEDATA)
        if cnt == 50:
	        mydb.commit()
	        cnt = 0
        else:
            cnt = cnt + 1
        logging.info ('###### DONE GAME '+str(gameid))
        gameid = gameid + 1
        response = 'QUOTA'
        currssid = currssid + 1
        if currssid == maxssid:
            currssid = 0
    ## Now all games have been imported into local DB
    mydb.commit()
    ### TODO REMOVE
    logging.info ('###### ALL DONE ######')
    sys.exit(0)

if whdfix:
    with open(config.whdxml, 'r') as xml_file:
        tree = ET.ElementTree()
        tree.parse(xml_file)
    root = tree.getroot()
    logging.info ('###### NUMBER OF NODES '+str(len(root)))
    for child in root:
        logging.info('##### TRYING '+child.attrib['filename']+' WITH SHA '+child.attrib['sha1'])
        srchsha = str(child.attrib['sha1'])
        sql = 'SELECT file FROM filehashes where sha1=%s'
        vals = (srchsha.upper())
        result,success = queryDB(sql,vals,False,mydb)
        logging.debug('###### FOUND '+str(result))
        if result != None:
            if isinstance(result,tuple):
                result = result[0][0]    
            logging.debug ('+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-'+str(type(result)))
            child.attrib['filename'] = result[result.rindex('/')+1:result.rindex('.')]
            logging.debug ('###### CHANGED FILENAME TO '+child.attrib['filename'])
    writeXML(root,config.whdxml+'.new')
    logging.info ('###### ALL DONE ######')
    sys.exit(0)
## Default behaviour
scrapeRoms(CURRSSID,listMissingFile)