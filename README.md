# sscraper

Python tool to scrape from screenscraper.fr

This scraper needs a MYSQL database available, you will need to create 2 tables. Please look at the tables.sql file.
The local DB is used so following scrapes are done first in the DB, speeding up the process and easing the load in screenscraper.fr (and not getting blocked by using up your quota everytime)

This script will probably run only on linux machines, sorry. Feel free to adapt it for other OS's.

The script will not ouput anything to the console (except if there is an unhandled exception), everything will be output to the sv2log.txt file. This is done so you can run this remotely and close the connection to your box `nohup python sscraper.py &` 

Look at the imports in the script and make sure you install all needed modules in your environment

Also, some image/video libraries are needed, cannot remember which right now, will try to update them when I remember.

**The script will run on a single thread, so it will not be super fast, parsing 70000 roms with an empty local DB may take up to 3 days or more depending on circumstances**

## Default Behavior

By default, running the script 'python sscraper.py' will:

- Load the systems configuartion (XML) file
  Update the location of your file in the config.py file.
- Parse files of the defined extensions for each system 
  `<extension>.cue .CUE .chd .CHD</extension>`
- Skip systems that have the `sskip='yes'` attribute set: `<system sskip='yes'>`
- Use a special tag `<ssname>3DO</ssname>` that will match with the system name in screenscraper.fr
- It will compress files which extension is not in the configuration file `donotcompress` to gain space
- It will add the (disk x) or (disc X) or (side x) or (tape x) information found in the filename to the game name.
- It will download video and images (will compose the background + 3dBox if both are found) and verify their integrity
- It will download bezels and create the configuration files (tested only for RetroPie)
- It will create symlinks for duplicate images and videos in order to save space
- it will create a missing csv file (pipe delimited), with a list of roms that could not be found in screenscraper.fr
- If your daily quota is done, it will switch to anonymous mode and if this mode is disabled by screenscraper.fr then it will pause until the next day quota is reset

## Missing roms

After the first run, you can re-execute the script with the `--missing filename.csv` parameter.

Each line in this file looks something like:

>76|/home/pi/RetroPie/roms/zxspectrum/Fred_(1984)(Investronica)(ES).zip|19b2100571c72e0e9e593723e7a2de4674e7ba84|d8cc135d5b793bf39819597fbb8ed3f2|7C749EFC|13

Where columns are:

System id in screenscraper | Full path to the file | SHA1 | MD5 | CRC | Size in Kb

What will happen:

- Script will read the missing file line by line and try to get the rom_id from screenscraper.fr based on name search
- If a confident match is found, it will update the Game_ID in the local DB to the Game_ID in screenscraper [The closer the filename to the game name in screenscraper, there will be more possibilities to find the proper game]
- If no confident match is found, all close matches will be added in a newmissing csv file
- After all lines are done, a full scrape will be launched, grabbing the information for the roms where the Game_ID was found (IT WILL RE RUN A FULL SYSTEM SCAN).
- For certain specific systems (arcade) since rom names are usually shorter versions, it will go to'http://www.mamedb.com/' and 'http://adb.arcadeitalia.net' to try and get the full name

The newmissing file structure is like this:

>113|/home/pi/RetroPie/roms/msx/Game_Over_II_(1988)(Dinamic_Software)(ES)(Side_A)[re-release_of_Phantis][RUN_CAS-_].zip|0f3e53ef7143a3fa9446ccce7678044bdbbac77d|f5b8e7b4a52fec3ab8235d44210864fa|DF901375	27|FORCED_ID|Game Land|95366|Game Master|95367|Game Master 2|95368|Game World - 126 Games|95372|Golf Game|95428|Chess Game The|96955|Pinball Game|97106|Msx Shogi Game|109059|Game Over|176884|Game Over|176884|Phantis - Game Over 2|185418|Game Over|176884	Phantis - Game Over 2|185418

Format is similar to the original missing file, but this time it will add a 'FORCE_ID' column and then a 'Game Name' column and 'Game ID' column per match returned by screenscraper.fr.

You will have the opportunity to manually update this file to replace the FORCE_ID field with the field you consider the correct one. You can also replace the FORCE_ID by DELETE to delete the file, UNKNOWN to move it to the unknown directory (see config.py file) or BIOS to move it to the bios directory (again, see config.py file)

If you run the --missing parameter with your modified file, it will update the GAME_ID in the local DB with the ID you replaced in the FORCE_ID field and then re-run a full scan.
