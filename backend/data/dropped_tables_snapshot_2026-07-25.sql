/* WARNING: Script requires that SQLITE_DBCONFIG_DEFENSIVE be disabled */
PRAGMA foreign_keys=OFF;
BEGIN TRANSACTION;
CREATE TABLE knowledge_skill_config (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        skill_name TEXT NOT NULL UNIQUE,
        secret_id INTEGER REFERENCES llm_secrets(id),
        model_override TEXT,
        prompt_template TEXT,
        enabled INTEGER DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
INSERT INTO knowledge_skill_config VALUES(1,'baoyu-post-to-wechat',NULL,NULL,NULL,1,'2026-07-15T13:33:21.576413+00:00','2026-07-16T02:51:52.849004+00:00');
INSERT INTO knowledge_skill_config VALUES(2,'baoyu-post-to-x',NULL,NULL,NULL,1,'2026-07-15T13:33:21.576413+00:00','2026-07-15T13:33:21.576413+00:00');
INSERT INTO knowledge_skill_config VALUES(3,'baoyu-post-to-weibo',NULL,NULL,NULL,1,'2026-07-15T13:33:21.576413+00:00','2026-07-15T13:33:21.576413+00:00');
INSERT INTO knowledge_skill_config VALUES(4,'baoyu-slide-deck',NULL,NULL,NULL,1,'2026-07-15T13:33:21.576413+00:00','2026-07-15T13:33:21.576413+00:00');
INSERT INTO knowledge_skill_config VALUES(5,'baoyu-infographic',NULL,NULL,NULL,1,'2026-07-15T13:33:21.576413+00:00','2026-07-15T13:33:21.576413+00:00');
INSERT INTO knowledge_skill_config VALUES(6,'baoyu-cover-image',NULL,NULL,NULL,1,'2026-07-15T13:33:21.576413+00:00','2026-07-15T13:33:21.576413+00:00');
INSERT INTO knowledge_skill_config VALUES(7,'baoyu-translate',NULL,NULL,NULL,1,'2026-07-15T13:33:21.576413+00:00','2026-07-15T13:33:21.576413+00:00');
INSERT INTO knowledge_skill_config VALUES(8,'baoyu-markdown-to-html',NULL,NULL,NULL,1,'2026-07-15T13:33:21.576413+00:00','2026-07-15T13:33:21.576413+00:00');
INSERT INTO knowledge_skill_config VALUES(9,'baoyu-xhs-images',NULL,NULL,NULL,1,'2026-07-15T13:33:21.576413+00:00','2026-07-15T13:33:21.576413+00:00');
INSERT INTO knowledge_skill_config VALUES(10,'baoyu-youtube-transcript',NULL,NULL,NULL,1,'2026-07-15T13:33:21.576413+00:00','2026-07-15T13:33:21.576413+00:00');
INSERT INTO knowledge_skill_config VALUES(11,'baoyu-url-to-markdown',NULL,NULL,NULL,1,'2026-07-15T13:33:21.576413+00:00','2026-07-15T13:33:21.576413+00:00');
INSERT INTO knowledge_skill_config VALUES(12,'baoyu-image-gen',NULL,NULL,NULL,1,'2026-07-15T13:33:21.576413+00:00','2026-07-15T13:33:21.576413+00:00');
INSERT INTO knowledge_skill_config VALUES(13,'baoyu-compress-image',NULL,NULL,NULL,1,'2026-07-15T13:33:21.576413+00:00','2026-07-15T13:33:21.576413+00:00');
INSERT INTO knowledge_skill_config VALUES(15,'knowledge-master',NULL,NULL,NULL,1,'2026-07-16T11:28:48.853860+00:00','2026-07-16T11:28:48.853860+00:00');
COMMIT;
