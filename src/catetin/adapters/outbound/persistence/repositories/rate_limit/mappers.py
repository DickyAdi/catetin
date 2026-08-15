"""No ORM<->domain mapping needed for rate limits: `RateLimitRow.count` is a
plain int consumed directly by `SqliteRateLimiter`, unlike the other rows."""
