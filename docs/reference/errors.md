# Exception Reference

Pin-actions exception hierarchy for error handling.

```
PinActionsError                    # base for all errors
├── YAMLParseError                # malformed YAML
├── GitHubAPIError                # base for API failures
│   ├── AuthError                  # 401/403 auth failure (bad/missing token, insufficient scope)
│   ├── InvalidRefError            # 404: ref doesn't exist
│   ├── RateLimitExhaustedError    # retries exhausted on 429/403 rate limiting
│   └── NetworkError               # unrecoverable network failure
└── UnsupportedRegistryError       # container registry doesn't support anonymous Bearer auth (e.g. ECR, GCR)
```

::: pin_actions.errors

## CLI exit codes

- `0` — success
- `1` — any error (YAML parse, invalid ref, rate limit, network, auth, etc.)

## See Also

- [How-To: Handle Errors](../how-to/handle-errors.md) — Recovery recipes
