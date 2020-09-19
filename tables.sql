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

CREATE TABLE `apicache` (
  `apiname` varchar(100) NOT NULL,
  `parameters` varchar(255) NOT NULL,
  `result` longtext DEFAULT NULL,
  KEY `apicache_apiname_IDX` (`apiname`,`parameters`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Holds a cache of V2 API CALLS'
