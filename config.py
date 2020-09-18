##### YOUR DEV ID
devid=""
##### YOUR DEV PASSWORD
devpassword=""
##### SOFTNAME, REALLY DOESN'T MATTER
softname=""
##### AN ARRAY CONTAINING THE USERNAME(S) YOU WANT TO SCRAPE WITH
ssid=[""]
##### PASSWORD - SAME FOR ALL USERNAMES
sspass=""
##### HOST OF YOUR LOCAL MYSQL DB
dbhost="192.168.8.101"
##### DB USER
dbuser=""
##### DB PASSWORD
dbpasswd=""
##### DB NAME
database=""
### INSERT THE EXTENSIONS YOU DO NOT WANT TO HAVE ZIPPED IN THE LIST BELOW
donotcompress = ['.zip','.lha','.iso','.cue','.bin','.chd','.pbp','.rp','.sh','.mgw','.rvz']
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
