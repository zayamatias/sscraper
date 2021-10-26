##### YOUR DEV ID
devid=""
##### YOUR DEV PASSWORD
devpassword=""
##### SOFTNAME, REALLY DOESN'T MATTER
softname=""
##### AN ARRAY CONTAINING THE USERNAME(S) YOU WANT TO SCRAPE WITH
ssid=["","",""]
##### PASSWORD - SAME FOR ALL USERNAMES
sspass=""
##### HOST OF YOUR LOCAL MYSQL DB
dbhost=""
##### DB USER
dbuser=""
##### DB PASSWORD
dbpasswd=""
##### DB NAME
database=""
### INSERT THE EXTENSIONS YOU DO NOT WANT TO HAVE ZIPPED IN THE LIST BELOW
donotcompress = ['.zip','.lha','.iso','.cue','.bin','.chd','.pbp','.rp','.sh','.mgw','.rvz','.7z','.rar']
### OUTPUT FILE WITH THE MISSING FILES CREATED IN THE FIRST ROUND
missingfile='/home/pi/missing.csv'
### OUTPUT FILE WITH THE MISSING FILES CREATED IN THE SECOND ROUNF (WHEN --missing PARAMETER IS PASSED)
newmissingfile='/home/pi/newmissing.csv'
### DIRECTORY WHERE YOUR BIOS FILES ARE LOCATED, THIS IS USED TO MOVE FILES MARKED AS BIOS
BIOSDIR = '/home/pi/RetroPie/BIOS/MAME'
### DIRECTORY TO MOVE YOUR UNKNOWN FILES TO
UNKDIR = '/home/pi/RetroPie/UNKNOWN'
#### LOCATION OF YOUR SYSTEM CONFIGURATION FILE
sysconfig = "/etc/emulationstation/es_systems.cfg"
#### TEMPORARY DIRECTORY
tmpdir = '/home/pi/'
##### WHDLOAD XML FILE (TO FIX AMIGA GAME NAMES)
whdxml = '/home/pi/whdload_db.xml'
##### FTP DOWNLOAD SITES FOR MISSING ROMS, FORMAT IS : {SYSTEM_NAME:{'ftpsite':'','user':'','password':'','subdir':'','addletter':Boolean}}
ftpconfig = {'AMIGA':{'ftpsite':'grandis.nu','user':'ftp','password':'amiga','subdir':'/TOSEC/Games/[ADF]/','addletter':True}}
##### HTTP DOWNLOAD SITES FOR MISSING ROMS, FORMAT IS : {SYSTEM_NAME:{'httpsite':'','regex:'','prefixaddress':Boolean}}
httpconfig  ={
    'COMMODORE 64':[
    {
    'httpsite':'https://archive.org/download/tosec-20161111-commodore-c64/TOSEC.2016.11.11.Commodore.C64.AlphaBot.zip/',
    'regex':'<a href="([^"]*)">\n([^<]*)',
    'prefixaddress':False
    }
    ],
    'MSXTURBOR':[
    {
    'httpsite':'https://archive.org/download/MSXRomCollectionByGhostware/',
    'regex':'<a href="([^"]*)">([^<]*)',
    'prefixaddress':True
    },
    {
    'httpsite':'https://ia902900.us.archive.org/view_archive.php?archive=/14/items/MSX_TurboR_TOSEC_2012_04_23/MSX_TurboR_TOSEC_2012_04_23.zip',
    'regex':'<a href="([^"]*)">([^<]*)',
    'prefixaddress':False
    },
    {
    'httpsite':'https://download.file-hunter.com/Games/MSX%20Turbo-R/__SUBDIR__/',
    'regex':'<A HREF="([^"]*)">\n([^<]*)\n',
    'prefixaddress':True,
    'subdirs':['DSK','Harddisk']
    }
    ],
    'MSX':[
    {
    'httpsite':'https://archive.org/download/MSXRomCollectionByGhostware/',
    'regex':'<a href="([^"]*)">([^<]*)',
    'prefixaddress':True
    },
    {
    'httpsite':'https://ia601904.us.archive.org/view_archive.php?archive=/5/items/MSX_MSX_TOSEC_2012_04_23/MSX_MSX_TOSEC_2012_04_23.zip',
    'regex':'<a href="([^"]*)">([^<]*)',
    'prefixaddress':False
    },
    {
    'httpsite':'https://download.file-hunter.com/Games/MSX1/__SUBDIR__/',
    'regex':'<A HREF="([^"]*)">\n([^<]*)\n',
    'prefixaddress':True,
    'subdirs':['CAS','DSK','MSX-Binaries','ROM']
    }
    ],
    'MSX2':[
    {
    'httpsite':'https://archive.org/download/MSXRomCollectionByGhostware/',
    'regex':'<a href="([^"]*)">([^<]*)',
    'prefixaddress':True
    },
    {
    'httpsite':'https://ia802909.us.archive.org/view_archive.php?archive=/20/items/MSX_MSX_Plus_TOSEC_2012_04_23/MSX_MSX_Plus_TOSEC_2012_04_23.zip',
    'regex':'<a href="([^"]*)">([^<]*)',
    'prefixaddress':False
    },
    {
    'httpsite':'https://download.file-hunter.com/Games/MSX2/__SUBDIR__/',
    'regex':'<A HREF="([^"]*)">([^<]*)\n',
    'prefixaddress':True,
    'subdirs':['CAS','DSK','MSX-Binaries','ROM','Harddisk']
    }
    ],
    'AMIGA':[
    {
    'httpsite':'https://ia600604.us.archive.org/view_archive.php?archive=/11/items/TOSEC_V2017-04-23/Commodore/Amiga/Games/Public%20Domain/%5BADF%5D/Commodore%20Amiga%20-%20Games%20-%20Public%20Domain%20-%20%5BADF%5D%20%28TOSEC-v2017-04-22_CM%29.zip',
    'regex':'<a href="([^"]*)">([^<]*)',
    'prefixaddress':False
    },
    {
    'httpsite':'https://ia800604.us.archive.org/view_archive.php?archive=/11/items/TOSEC_V2017-04-23/Commodore/Amiga/Games/Emerald%20Mine/Commodore%20Amiga%20-%20Games%20-%20Emerald%20Mine%20%28TOSEC-v2016-12-19_CM%29.zip',
    'regex':'<a href="([^"]*)">([^<]*)',
    'prefixaddress':False
    },
    {
    'httpsite':'https://ia800604.us.archive.org/view_archive.php?archive=/11/items/TOSEC_V2017-04-23/Commodore/Amiga/Games/Save%20Disks/Commodore%20Amiga%20-%20Games%20-%20Save%20Disks%20%28TOSEC-v2016-08-27_CM%29.zip',
    'regex':'<a href="([^"]*)">([^<]*)',
    'prefixaddress':False
    },
    {
    'httpsite':'https://ia800604.us.archive.org/view_archive.php?archive=/11/items/TOSEC_V2017-04-23/Commodore/Amiga/Games/SPS/Commodore%20Amiga%20-%20Games%20-%20SPS%20%28TOSEC-v2016-11-01_CM%29.zip',
    'regex':'<a href="([^"]*)">([^<]*)',
    'prefixaddress':False
    },
    {
    'httpsite':'https://ia800604.us.archive.org/view_archive.php?archive=/11/items/TOSEC_V2017-04-23/Commodore/Amiga/Games/Unofficial%20Addons%20%26%20Patches/Commodore%20Amiga%20-%20Games%20-%20Unofficial%20Addons%20%26%20Patches%20%28TOSEC-v2016-10-19_CM%29.zip',
    'regex':'<a href="([^"]*)">([^<]*)',
    'prefixaddress':False
    },
    {
    'httpsite':'https://ia600604.us.archive.org/view_archive.php?archive=/11/items/TOSEC_V2017-04-23/Commodore/Amiga/Games/%5BADF%5D/Commodore%20Amiga%20-%20Games%20-%20%5BADF%5D%20%28TOSEC-v2017-04-12_CM%29.zip',
    'regex':'<a href="([^"]*)">([^<]*)',
    'prefixaddress':False
    },
    {
    'httpsite':'https://ia601604.us.archive.org/view_archive.php?archive=/25/items/Commodore_Amiga_TOSEC_2012_04_10/Commodore_Amiga_TOSEC_2012_04_10.zip',
    'regex':'<a href="([^"]*)">([^<]*)',
    'prefixaddress':False
    },
    {'httpsite':'https://retro-commodore.eu/files/downloads/Amiga/Games/Public%20Domain/__SUBDIR__/',
    'regex':'<a href="([^"]*)">([^<]*)',
    'prefixaddress':True,
    'subdirs':['#','A','B','C','D','E','F','G','H','I','J','K','L','M','N','O','P','Q','R','S','T','U','V','W','X','Y','Z']
    },
    {'httpsite':'http://amigamuseum.emu-france.info/Fichiers/ADF/__SUBDIR__/',
    'regex':'<a href="([^"]*)">([^<]*)',
    'prefixaddress':True,
    'subdirs':['- Applications','- Demos - Animations & Videos','- Demos - Musiques','- Demos - Productions','- Demos - Slideshows','- Domaine Publique (DP)','- Educatifs','- WHDLoad/Amiga WHDLoad Romset (AGA)/','- WHDLoad/Amiga WHDLoad Romset (ECS)/','HFE pour GOTEK (Exclusivit%C3%A9 AmigaMuseum)/','ISOs CD32 & CDTV/CD32/','ISOs CD32 & CDTV/CDTV/','Unreleased','0','A','B','C','D','E','F','G','H','I','J','K','L','M','N','O','P','Q','R','S','T','U','V','W','X-Y-Z']
    }
    ],
    'CPC':[
    {
    'httpsite':'https://ia601904.us.archive.org/view_archive.php?archive=/28/items/TOSEC_PIX_Amstrad_2013-04-13/TOSEC_PIX_Amstrad_2013-04-13.zip',
    'regex':'<a href="([^"]*)">([^<]*)',
    'prefixaddress':False
    },
    {
    'httpsite':'https://ia801907.us.archive.org/view_archive.php?archive=/16/items/Amstrad_GX4000_TOSEC_2012_04_23/Amstrad_GX4000_TOSEC_2012_04_23.zip',
    'regex':'<a href="([^"]*)">([^<]*)',
    'prefixaddress':False
    },
    {
    'httpsite':'https://ia902907.us.archive.org/view_archive.php?archive=/7/items/Enterprise_64_and_128_TOSEC_2012_04_23/Enterprise_64_and_128_TOSEC_2012_04_23.zip',
    'regex':'<a href="([^"]*)">([^<]*)',
    'prefixaddress':False
    },
    {
    'httpsite':'https://ia601901.us.archive.org/view_archive.php?archive=/4/items/Amstrad_CPC_TOSEC_2012_04_23/Amstrad_CPC_TOSEC_2012_04_23.zip',
    'regex':'<a href="([^"]*)">([^<]*)',
    'prefixaddress':False
    },
    {
    'httpsite':'https://ia803402.us.archive.org/view_archive.php?archive=/4/items/tosec-2021-02-14-safe/Amstrad/CPC/Games/%5BDSK%5D/Amstrad%20CPC%20-%20Games%20-%20%5BDSK%5D%20%28TOSEC-v2020-07-12%29.zip',
    'regex':'<a href="([^"]*)">([^<]*)',
    'prefixaddress':False
    },
    {
    'httpsite':'https://ia904509.us.archive.org/view_archive.php?archive=/7/items/hearto-1g1r-collection/hearto_1g1r_collection/Amstrad%20-%20CPC.zip',
    'regex':'<a href="([^"]*)">([^<]*)',
    'prefixaddress':False
    }
    ],
    'APPLE II':[
    {
    'httpsite':'https://ia902908.us.archive.org/view_archive.php?archive=/25/items/Apple_2_TOSEC_2012_04_23/Apple_2_TOSEC_2012_04_23.zip',
    'regex':'<a href="([^"]*)">([^<]*)',
    'prefixaddress':False
    }
    ],
    'ATARI ST':[
    {
    'httpsite':'https://ia802909.us.archive.org/view_archive.php?archive=/29/items/Atari_ST_TOSEC_2012_04_23/Atari_ST_TOSEC_2012_04_23.zip',
    'regex':'<a href="([^"]*)">([^<]*)',
    'prefixaddress':False
    }
    ],
    'ATARI 8BIT':[
    {
    'httpsite':'https://ia904508.us.archive.org/view_archive.php?archive=/25/items/atari-8bit-non-tosec-coll/Atari8bit_nonTOSEC.zip',
    'regex':'<a href="([^"]*)">([^<]*)',
    'prefixaddress':False
    },
    {
    'httpsite':'https://ia801900.us.archive.org/view_archive.php?archive=/11/items/Atari_8_bit_TOSEC_2012_04_23/Atari_8_bit_TOSEC_2012_04_23.zip',
    'regex':'<a href="([^"]*)">([^<]*)',
    'prefixaddress':False
    }
    ],
    'COLECOVISION':[
    {
    'httpsite':'https://ia802801.us.archive.org/view_archive.php?archive=/3/items/Coleco_ColecoVision_TOSEC_2012_04_23/Coleco_ColecoVision_TOSEC_2012_04_23.zip',
    'regex':'<a href="([^"]*)">([^<]*)',
    'prefixaddress':False
    }
    ],
    'ARCADE':[
    {
    'httpsite':'https://archive.org/download/mame-0.236-roms-split/MAME%200.236%20ROMs%20%28split%29/',
    'regex':'<a href="([^"]*)">([^<]*)',
    'prefixaddress':False
    }
    ]

}
