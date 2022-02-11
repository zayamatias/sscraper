# Important news!
I've been working on a new scraper for a while now, and it is starting to get to a very basic point, but to a point where it could start to be tested rather soon.

I need your help!

If you:

  - Have a system running emulation station under linux
  - Know your way around configuration files (In JSON)
  - Know your way around python
  - Are willing to cope with a lot of issues during testing
  - Are interested in helping me

If you're interested, send me an email to retroscraper(at)gmail.com and I'll get in touch ASAP.

Thanks!

# sscraper

Python tool to scrape from screenscraper.fr - This is not a GUI tool, it must be run on the command line, preferably on the machine where your roms are hosted.

This scraper needs a MYSQL database available, you will need to create some tables. Please look at the tables.sql file.
The local DB is used so following scrapes are done first in the DB, speeding up the process and easing the load in screenscraper.fr (and not getting blocked by using up your quota everytime)

This script will probably run only on linux machines, sorry. Feel free to adapt it for other OS's.

The script will not ouput anything to the console (except if there is an unhandled exception), everything will be output to the sv2log.txt file. This is done so you can run this remotely and close the connection to your box `nohup python sscraper.py &` and follow progress with `tail -f sv2log.txt`

Look at the imports in the script and make sure you install all needed modules in your environment

Also, some image/video libraries are needed, install with `sudo apt install libmediainfo-dev`

If you have any questions, you can always contact me in twitter:[8bitzaya](https://twitter.com/8bitzaya) or I suppose GitHub too. Enjoy!

**Dynamic marquees!!** Try together with https://github.com/zayamatias/EmulationStation

**The script will run on a single thread, so it will not be super fast, parsing 70000 roms with an empty local DB may take up to 3 days or more depending on circumstances**

Also, if you do a scrape of the 200k games that are in SS and store them in the localDB, you would need SS only to download media (May add that media caching feature in the future, but you'll probably need a huge disk capacit and a lot of patience!)

## Quick start

- Make sure you have python 2.7 (the one by default with RetroPie) and the dependencies in requirements.txt installed (pip install -r requirements.txt), if you need to install pip visit this: https://pip.pypa.io/en/stable/installing/ (it also works with pyhton 3.x now!)
- Install MariaDB in any machine on your network, I'd advise you against installing it on the same machine as your RetroPie install (download mariadb server here https://mariadb.org/download/)
- Execute the sql file you find in this same repository
- Give access to a user (identified by password) to this database and update config.py with same credentials
- Request a developer key at screenscraper (very simple, do it in the forums) and update the config.py with same credentials
- Update config.py with your login (ssid) and password (sspassword) from screenscraper (your usual user login)
- My advice would be to start importing the screenscraper DB (--startid xxxx) where xxxxx is the game id you want to start with, usually is 1 but you can continue with whichver nymber in case the import stops
- If you get DB errors, make sure that credentials are ok, that your server does not block incoming calls and that the DB was properly created.
- Once everything is imported, you do not need to access screenscraper API anymore, even if the API is down, you will be able to scrape games (and maybe download media if server is not totally down)
- In order to scrape , run the program without any parameters
- I've tested it only with retropie configuration file (es_systems.cfg), not sure if it will work at all with different configruations.

## Default Behavior

By default, running the script 'python sscraper.py' will:

- Load the RetroPie systems configuartion (XML) file - Make sure to update the location of your file in the config.py file.
- Parse files of the defined extensions for each system `<extension>.cue .CUE .chd .CHD</extension>`
- Skip systems that have the `sskip='yes'` attribute set: `<system sskip='yes'>`
- Use a special tag `<ssname>3DO</ssname>` that will match with the system name in screenscraper.fr
- It will compress files which extension is not in the configuration file `donotcompress` to gain space
- It will store the SHA1, MD5 & CRC of files in the DB, so it will assing the original hashes to the compressed file
- It will look inside compressed files in case there is no match in screenscraper (and check again with hashes for extracted file)
- It will delete and rebuild a new gamelist.xml file, so any addition you have done to this fie manually will be deleted.
- It will add the (disk x) or (disc X) or (side x) or (tape x) information found in the filename to the game name (now also the [...] (...) values in teh filename)
- It will download video and images (will compose the background + 3dBox if both are found and there is no composite present in screenscraper) and verify their integrity
- It will download bezels and create the configuration files (tested only for RetroPie) (disable with --nobezel)
- It will download small marquee so it should work with https://github.com/losernator/PieMarquee2 (disable with --nomarquee)
- It will create symlinks for duplicate images and videos in order to save space
- If your daily quota is done, it will switch to anonymous mode and if this mode is disabled by screenscraper.fr then it will pause until the next day quota is reset
- It will store all information in the local DB so you save precious scraping quota

## Missing Mode

There is no need for missing mode anymore, the scraper will go through all the games in the local DB to find the correct ones. If you want to link one of the unknown roms to the game, just update the gameID in the DB for that rom (selecting all roms with gameid=0 will return all unlinked roms)

## Update Mode

When running the script with the --update switch, it will rerun a full scan but it will no longer get the information as present in the local DB, but it will do a new request to screenscraper.fr and update the localDB, images and videos.

This is useful to run once every so often in order to get any updated information that screenscraper may have.

It will use the GAME_ID found in the DB in order to avoid not finding roms that where updated with the missing file method.

## Clean Mode

The switch '--clean SYSTEM' will force the script to clean the DB for information concenring the system you designate. This has been useful to me during dvelopment when wrong information was stored in the localDB, but it may be of no use for you. Anyway, the option is present

## Rename Mode

The switch '--rename' will fetch all games in the local DB, and try to rename filenames to the actual game name. Usefull if you like to have a neat set of files.

## Clone DB mode

Try --importgames (start_game_id end_game_id) to start download game information into the local DB starting from game_id, data will be stored locally so you would still be able to scrap roms regardless if the site is down or your quota is over. Of coure, this is a super lengthy process that can take several days depending on your quota limits, connecion, etc...

## Get new roms mode

Try --getroms (start_rom_id end_rom_id) to get latest roms, it will get the game id for the new roms, update the DB for the game and of course add the roms to the local DB. Thisis also a slow process, so patience.

## Sort Mode

The --sort (directory) will sort all your roms to a destination directory, usefull if you want o have a precise list of roms sorted by their system (a directory per system) and create a es_config.xml with all the updated directories and system names.

## List missing games from collection

The --listmissing (path to file) will create a file with the name you selected containing all the missing games (present in screenscraper) from your collection. In order for this functionality to work properly, you would have to have imported the whole list of games from screenscraper using the 'clone DB mode'. Small sample of the output:
```
SYSTEM : 3DO
----------------------------------------------------------------------------------------
SCREENSCRAPER LINK https://screenscraper.fr/gameinfos.php?gameid=14307
GAME NAMES:
Game Name : Alone In The Dark 2

ROMS:
Rom Name : Alone in the Dark 2 (1995)(Infogrames)(EU).7z
Rom Name : Alone in the Dark 2 (1995)(Infogrames)(FR).7z
Rom Name : Alone in the Dark 2 (1995)(Interplay)(US)[!].7z
Rom Name : Alone in the Dark 2 (Japan).7z
Rom Name : Alone in the Dark 2 (Japan).bin
Rom Name : Alone in the Dark 2 (Japan).cue
Rom Name : Alone in the Dark 2 (USA).cue
----------------------------------------------------------------------------------------
----------------------------------------------------------------------------------------
SCREENSCRAPER LINK https://screenscraper.fr/gameinfos.php?gameid=14324
GAME NAMES:
Game Name : Hirata Shogo Interactive Ehon - Cinderella
Game Name : Hirata Shogo Interactive Ehon : Cinderella

ROMS:
Rom Name : Cinderella Fairytales (J).zip
Rom Name : Hirata Shougo Interactive Ehon - Cinderella (Japan) (En,Ja,Fr).bin
Rom Name : Hirata Shougo Interactive Ehon - Cinderella (Japan) (En,Ja,Fr).cue
----------------------------------------------------------------------------------------
```

## Fix WHDLOAD config file

If you're using Amiberry to load whd files, this might come in handy. It will search the xml config file you specify in the config, and match the SHA1 with the ones in your database, and rename the file in the XML so it will load properly. For this option to run properly, you would have to already have scanned your game collection of Amiga games.
Simply launch it with the --fixwhd switch.

## Get new medias

Since we're storing a local DB, is it wise from time to time to check for latest media additions. The --getnewmedia switch will scan from this page (https://screenscraper.fr/updatemedias.php) the new medias added and get the game information. As parameter pass the last page you want to have scanned (as a number)

## Get new info

Work exactly as the get new media option, it will just check for the pages where new information added to the games is displayed.

## Do not add game tags to the game name

By default the scraper will look into the filenames and add anything between () and between [] to the name displayed in retropie. Disable this function with the --nonamemodif flag.

## Select region and language to scrape

use --region and --language flags to select your preferred choice. Defaults are 'world' and 'english'
