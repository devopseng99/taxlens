-- V007: OAuth token indexes for cleanup and lookup performance

-- Index for token cleanup CronJob (hourly expired token sweep)
CREATE INDEX IF NOT EXISTS idx_oauth_tokens_client_expires
    ON oauth_tokens(client_id, expires_at);

-- Index for refresh token lookups (rotation)
CREATE INDEX IF NOT EXISTS idx_oauth_tokens_type_client
    ON oauth_tokens(token_type, client_id);
