\getenv web_password NEWS_WEB_PASSWORD
\getenv parser_password NEWS_PARSER_PASSWORD
\getenv ai_password NEWS_AI_PASSWORD
\getenv cleanup_password NEWS_CLEANUP_PASSWORD
CREATE ROLE news_web LOGIN PASSWORD :'web_password';
CREATE ROLE news_parser LOGIN PASSWORD :'parser_password';
CREATE ROLE news_ai LOGIN PASSWORD :'ai_password';
CREATE ROLE news_cleanup LOGIN PASSWORD :'cleanup_password';
