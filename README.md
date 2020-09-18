# sscraper

Python tool to scrape from screenscraper.fr

This scraper needs a MYSQL database available, you will need to create 2 tables. Please look at the tables.sql file.

This script will probably run on linux machines, sorry. Feel free to adapt it for other OS's.

##Default Behavior

By default, running the script 'python sscraper.py' will:

- Load the systems configuartion (XML) file
  Update the location of your file in the config.py file.
- Parse files of the defined extensions for each system 
  `<extension>.cue .CUE .chd .CHD</extension>`
- Skip systems that have the `sskip='yes'` attribute set: `<system sskip='yes'>`
- Use a special tag `<ssname>3DO</ssname>` that will match with the system name in screenscraper.fr
- It will compress files which extension is not in the configuration file `donotcompress` to gain space
- It will download video and imamges (will compose the background + 3dBox if both are found)
- It will create symlinks for duplicate images and videos in order to save space
- it will create a missing csv file (pipe delimited), with a list of roms that could not be found in screenscraper.fr

##Missing roms

After the first run, you can re-execute the script with the `--missing filename.csv` parameter.

Each line in this file looks something like:

>76|/home/pi/RetroPie/roms/zxspectrum/Fred_(1984)(Investronica)(ES).zip|19b2100571c72e0e9e593723e7a2de4674e7ba84|d8cc135d5b793bf39819597fbb8ed3f2|7C749EFC|13

Where columns are:

System id in screenscraper | Full path to the file | SHA1 | MD5 | CRC | Size in Kb

What will happen:

- Script will read the missing file line by line and try to get the rom_id from screenscraper.fr based on name search
- If a confident match is found, it will update the Game_ID in the local DB to the Game_ID in screenscraper
- If no confident match is found, all close matches will be added in a newmissing csv file
- After all lines are done, a full scrape will be launched, grabbing the information for the roms where the Game_ID was found (IT WILL RE RUN A FULL SYSTEM SCAN).
- For certain specific systems (arcade) since rom names are usually shorter versions, it will go to'http://www.mamedb.com/' and 'http://adb.arcadeitalia.net' to try and get the full name

The newmissing file structure is like this:

