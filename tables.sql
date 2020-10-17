CREATE DATABASE `romhashes` /*!40100 DEFAULT CHARACTER SET utf8mb4 */;

USE `romhashes`

CREATE TABLE 'filehashes' (
  'file' varchar(300) NOT NULL,
  'SHA1' varchar(100) DEFAULT NULL,
  'MD5' varchar(100) DEFAULT NULL,
  'CRC' varchar(100) DEFAULT NULL,
  PRIMARY KEY ('file'),
  KEY 'filehashes_file_IDX' ('file') USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4


CREATE TABLE 'hashes' (
  'hash' char(40) NOT NULL,
  'response' longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  'created_at' timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY ('hash')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4

-- romhashes.apicache definition

CREATE TABLE `apicache` (
  `apiname` varchar(100) NOT NULL,
  `parameters` varchar(255) NOT NULL,
  `result` longtext DEFAULT NULL,
  KEY `apicache_apiname_IDX` (`apiname`,`parameters`) USING BTREE,
  KEY `apicache_parameters_IDX` (`parameters`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Holds a cache of V2 API CALLS';

CREATE TABLE `editors` (
  `id` int(11) NOT NULL,
  `text` varchar(100) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- romhashes.systems definition

CREATE TABLE `systems` (
  `id` int(11) NOT NULL,
  `text` varchar(100) DEFAULT NULL,
  `type` varchar(30) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `systems_type_IDX` (`type`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- romhashes.games definition

CREATE TABLE `games` (
  `id` int(11) NOT NULL,
  `notgame` tinyint(1) DEFAULT NULL,
  `topstaff` int(11) DEFAULT NULL,
  `rotation` int(11) DEFAULT NULL,
  `cloneof` int(11) DEFAULT NULL,
  `system` int(11) DEFAULT NULL,
  `editeur` int(11) DEFAULT NULL,
  `lastdate` datetime DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `editor_FK` (`editeur`),
  KEY `system_FK` (`system`),
  CONSTRAINT `editor_FK` FOREIGN KEY (`editeur`) REFERENCES `editors` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `system_FK` FOREIGN KEY (`system`) REFERENCES `systems` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Holds the basic information of the games';

-- romhashes.gameRoms definition

CREATE TABLE `gameRoms` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `romfilename` varchar(300) NOT NULL,
  `romsha1` varchar(45) NOT NULL,
  `beta` int(11) DEFAULT 0,
  `demo` int(11) DEFAULT 0,
  `proto` int(11) DEFAULT 0,
  `trad` int(11) DEFAULT 0,
  `hack` int(11) DEFAULT 0,
  `unl` int(11) DEFAULT 0,
  `alt` int(11) DEFAULT 0,
  `best` int(11) DEFAULT 0,
  `netplay` int(11) DEFAULT 0,
  `gameid` int(11) DEFAULT NULL,
  `romcrc` varchar(20) DEFAULT NULL,
  `rommd5` varchar(32) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `gameRoms_UN` (`rommd5`,`romcrc`,`romsha1`),
  KEY `gameRoms_FK` (`gameid`),
  KEY `gameRoms_romsha1_IDX` (`romsha1`) USING BTREE,
  KEY `gameRoms_romcrc_IDX` (`romcrc`) USING BTREE,
  KEY `gameRoms_rommd5_IDX` (`rommd5`) USING BTREE,
  CONSTRAINT `gameRoms_FK` FOREIGN KEY (`gameid`) REFERENCES `games` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=726828 DEFAULT CHARSET=utf8mb4;

CREATE TABLE `gameDates` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `text` varchar(100) DEFAULT NULL,
  `region` varchar(20) DEFAULT NULL,
  `gameID` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `gameDates_UN` (`gameID`,`region`),
  CONSTRAINT `gameDates_FK` FOREIGN KEY (`gameID`) REFERENCES `games` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=7925

CREATE TABLE `gameMedias` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `type` varchar(20) DEFAULT NULL,
  `url` varchar(300) DEFAULT NULL,
  `region` varchar(10) DEFAULT NULL,
  `format` varchar(5) DEFAULT NULL,
  `gameid` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `gameMedias_UN` (`type`,`region`,`gameid`),
  KEY `gameMedias_FK` (`gameid`),
  CONSTRAINT `gameMedias_FK` FOREIGN KEY (`gameid`) REFERENCES `games` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=1425774 DEFAULT CHARSET=utf8mb4;

-- romhashes.gameNames definition

CREATE TABLE `gameNames` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `region` varchar(12) DEFAULT NULL,
  `text` varchar(255) DEFAULT NULL,
  `gameid` int(11) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `gameNames_FK` (`gameid`),
  KEY `gameNames_text_IDX` (`text`) USING BTREE,
  CONSTRAINT `gameNames_FK` FOREIGN KEY (`gameid`) REFERENCES `games` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=395321 DEFAULT CHARSET=utf8mb4;

-- romhashes.gameSynopsis definition

CREATE TABLE `gameSynopsis` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `langue` varchar(5) DEFAULT NULL,
  `text` text DEFAULT NULL,
  `gameid` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `gameSynopsis_UN` (`langue`,`gameid`),
  KEY `gameSynopsis_FK` (`gameid`),
  CONSTRAINT `gameSynopsis_FK` FOREIGN KEY (`gameid`) REFERENCES `games` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=147661 DEFAULT CHARSET=utf8mb4;
