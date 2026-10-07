"""Pull invoices and customers from NetSuite with SuiteQL (REST, token-based auth).

Setup (one-off, by a NetSuite administrator) is described in docs/integrations.md.
Credentials come from environment variables so they never live in the repo:

    NETSUITE_ACCOUNT_ID       e.g. 1234567 or 1234567_SB1 for a sandbox
    NETSUITE_CONSUMER_KEY     from the Integration record
    NETSUITE_CONSUMER_SECRET
    NETSUITE_TOKEN_ID         from the Access Token (user + role)
    NETSUITE_TOKEN_SECRET

Only the Python standard library is used: requests are signed with OAuth 1.0a
HMAC-SHA256 as NetSuite's token-based authentication requires.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

QUERY_DIR = Path(__file__).with_name("queries")
PAGE_SIZE = 1000  # SuiteQL maximum per request
ENV_VARS = {
    "account_id": "NETSUITE_ACCOUNT_ID",
    "consumer_key": "NETSUITE_CONSUMER_KEY",
    "consumer_secret": "NETSUITE_CONSUMER_SECRET",
    "token_id": "NETSUITE_TOKEN_ID",
    "token_secret": "NETSUITE_TOKEN_SECRET",
}


class NetSuiteError(RuntimeError):
    pass


def _pct(value: str) -> str:
    """RFC 3986 percent-encoding as OAuth 1.0a requires."""
    return urllib.parse.quote(str(value), safe="~-._")


def oauth1_header(
    method: str,
    url: str,
    consumer_key: str,
    consumer_secret: str,
    token: str,
    token_secret: str,
    realm: Optional[str] = None,
    signature_method: str = "HMAC-SHA256",
    nonce: Optional[str] = None,
    timestamp: Optional[str] = None,
    body_params: Optional[Dict[str, str]] = None,
) -> str:
    """Build an OAuth 1.0a ``Authorization`` header (RFC 5849, section 3)."""
    parsed = urllib.parse.urlsplit(url)
    base_url = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path}"
    oauth = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": nonce or secrets.token_hex(16),
        "oauth_signature_method": signature_method,
        "oauth_timestamp": timestamp or str(int(time.time())),
        "oauth_token": token,
        "oauth_version": "1.0",
    }
    params = list(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    params += list((body_params or {}).items()) + list(oauth.items())
    encoded = sorted((_pct(k), _pct(v)) for k, v in params)
    param_string = "&".join(f"{k}={v}" for k, v in encoded)
    base_string = "&".join([method.upper(), _pct(base_url), _pct(param_string)])
    key = f"{_pct(consumer_secret)}&{_pct(token_secret)}".encode()
    digest = {"HMAC-SHA256": hashlib.sha256, "HMAC-SHA1": hashlib.sha1}[signature_method]
    oauth["oauth_signature"] = base64.b64encode(hmac.new(key, base_string.encode(), digest).digest()).decode()
    parts = [f'realm="{realm}"'] if realm else []
    parts += [f'{k}="{_pct(v)}"' for k, v in oauth.items()]
    return "OAuth " + ", ".join(parts)


@dataclass
class NetSuiteClient:
    account_id: str
    consumer_key: str
    consumer_secret: str
    token_id: str
    token_secret: str
    timeout: int = 120
    # Injected in tests; defaults to urllib.
    opener: Callable[..., Any] = urllib.request.urlopen

    @classmethod
    def from_env(cls, environ: Optional[Dict[str, str]] = None) -> "NetSuiteClient":
        env = os.environ if environ is None else environ
        missing = [v for v in ENV_VARS.values() if not env.get(v)]
        if missing:
            raise NetSuiteError("Missing NetSuite credentials: set " + ", ".join(missing))
        return cls(**{field: env[var] for field, var in ENV_VARS.items()})

    @property
    def realm(self) -> str:
        return self.account_id.upper().replace("-", "_")

    @property
    def base_url(self) -> str:
        host = self.account_id.lower().replace("_", "-")
        return f"https://{host}.suitetalk.api.netsuite.com/services/rest/query/v1/suiteql"

    def _post(self, url: str, query: str) -> Dict[str, Any]:
        headers = {
            "Authorization": oauth1_header(
                "POST", url, self.consumer_key, self.consumer_secret, self.token_id, self.token_secret, realm=self.realm
            ),
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Prefer": "transient",
        }
        req = urllib.request.Request(url, data=json.dumps({"q": query}).encode(), headers=headers, method="POST")
        try:
            with self.opener(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:1000]
            raise NetSuiteError(f"SuiteQL request failed ({exc.code}): {detail}") from None

    def query(self, sql: str) -> Iterator[Dict[str, Any]]:
        """Run a SuiteQL query, following pagination, yielding one dict per row."""
        offset = 0
        while True:
            url = f"{self.base_url}?limit={PAGE_SIZE}&offset={offset}"
            page = self._post(url, sql)
            for item in page.get("items", []):
                item.pop("links", None)
                yield item
            if not page.get("hasMore"):
                return
            offset += PAGE_SIZE


def load_query(name_or_path: Optional[str], default: str, **params: Any) -> str:
    path = Path(name_or_path) if name_or_path else QUERY_DIR / default
    sql = path.read_text(encoding="utf-8")
    for key, value in params.items():
        sql = sql.replace("{" + key + "}", str(value))
    # SuiteQL rejects comments and trailing semicolons.
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    return "\n".join(lines).strip().rstrip(";")


def fetch(
    client: NetSuiteClient,
    lookback_months: int = 15,
    invoices_query: Optional[str] = None,
    customers_query: Optional[str] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    inv_sql = load_query(invoices_query, "netsuite_invoices.sql", lookback_months=int(lookback_months))
    cust_sql = load_query(customers_query, "netsuite_customers.sql")
    return {"invoices": list(client.query(inv_sql)), "customers": list(client.query(cust_sql))}
