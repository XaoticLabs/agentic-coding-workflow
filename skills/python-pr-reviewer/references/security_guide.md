# Python Security Best Practices

This guide covers common security vulnerabilities in Python applications and how to prevent them.

## 1. Injection Vulnerabilities

### SQL Injection

**CRITICAL SEVERITY**

Never concatenate user input into SQL queries. Always use parameterized queries.

```python
# ❌ CRITICAL: SQL injection vulnerability
user_id = request.args.get("id")
query = f"SELECT * FROM users WHERE id = {user_id}"
cursor.execute(query)

# ❌ CRITICAL: Still vulnerable with string formatting
query = "SELECT * FROM users WHERE id = {}".format(user_id)
cursor.execute(query)

# ✅ Good: Parameterized query (sqlite3)
query = "SELECT * FROM users WHERE id = ?"
cursor.execute(query, (user_id,))

# ✅ Good: Named parameters
query = "SELECT * FROM users WHERE id = :id"
cursor.execute(query, {"id": user_id})

# ✅ Good: Using ORM (SQLAlchemy)
user = session.query(User).filter(User.id == user_id).first()
```

### Command Injection

**CRITICAL SEVERITY**

Never pass user input directly to shell commands.

```python
import subprocess

# ❌ CRITICAL: Command injection vulnerability
filename = request.args.get("file")
subprocess.run(f"cat {filename}", shell=True)

# ❌ CRITICAL: Still vulnerable
os.system(f"rm {filename}")

# ✅ Good: Use list arguments, no shell
subprocess.run(["cat", filename], shell=False)

# ✅ Better: Use safe Python equivalents
from pathlib import Path
content = Path(filename).read_text()

# ✅ Good: Validate input first
import shlex
filename = shlex.quote(filename)  # Escape shell metacharacters
subprocess.run(["cat", filename], shell=False)
```

### Path Traversal

**CRITICAL SEVERITY**

Validate and sanitize file paths to prevent directory traversal attacks.

```python
from pathlib import Path

# ❌ CRITICAL: Path traversal vulnerability
def read_user_file(filename: str) -> str:
    return open(f"/app/uploads/{filename}").read()

# User can pass: "../../../etc/passwd"

# ✅ Good: Resolve and validate path
def read_user_file(filename: str) -> str:
    base_dir = Path("/app/uploads").resolve()
    file_path = (base_dir / filename).resolve()

    # Ensure the resolved path is within base_dir
    if not str(file_path).startswith(str(base_dir)):
        raise ValueError("Invalid file path")

    return file_path.read_text()

# ✅ Good: Use allowlist of filenames
ALLOWED_FILES = {"report.pdf", "data.csv"}

def read_user_file(filename: str) -> str:
    if filename not in ALLOWED_FILES:
        raise ValueError("File not allowed")
    return Path(f"/app/uploads/{filename}").read_text()
```

### Code Injection

**CRITICAL SEVERITY**

Never use `eval()` or `exec()` with user input.

```python
# ❌ CRITICAL: Arbitrary code execution
user_code = request.json.get("code")
result = eval(user_code)

# ❌ CRITICAL: Still dangerous
exec(user_code)

# ✅ Good: Use safe alternatives
import ast

def safe_eval_number(expr: str) -> float:
    """Safely evaluate a mathematical expression."""
    try:
        tree = ast.parse(expr, mode='eval')
        # Only allow specific node types
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Expression, ast.Constant,
                                    ast.BinOp, ast.Add, ast.Sub,
                                    ast.Mult, ast.Div)):
                raise ValueError("Unsafe operation")
        return eval(compile(tree, filename="", mode="eval"))
    except Exception as e:
        raise ValueError(f"Invalid expression: {e}")

# ✅ Better: Use a parser library
from pyparsing import Word, nums, alphas
# Define safe grammar and parse
```

---

## 2. Authentication and Authorization

### Password Security

**CRITICAL SEVERITY**

Never store passwords in plain text. Always use proper hashing.

```python
# ❌ CRITICAL: Plain text password storage
user.password = request.form["password"]

# ❌ CRITICAL: Weak hashing (MD5, SHA1)
import hashlib
user.password = hashlib.md5(password.encode()).hexdigest()

# ✅ Good: Use bcrypt
import bcrypt

def hash_password(password: str) -> bytes:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt())

def verify_password(password: str, hashed: bytes) -> bool:
    """Verify a password against a hash."""
    return bcrypt.checkpw(password.encode(), hashed)

# ✅ Good: Use argon2 (newer standard)
from argon2 import PasswordHasher

ph = PasswordHasher()

def hash_password(password: str) -> str:
    return ph.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    try:
        ph.verify(hashed, password)
        return True
    except:
        return False
```

### Session Management

**HIGH SEVERITY**

Implement secure session handling.

```python
from secrets import token_urlsafe
from datetime import datetime, timedelta

# ✅ Good: Generate cryptographically secure tokens
def generate_session_token() -> str:
    return token_urlsafe(32)

# ✅ Good: Set secure session cookie
from flask import session

@app.route('/login', methods=['POST'])
def login():
    # ... authenticate user ...
    session['user_id'] = user.id
    session.permanent = True
    app.permanent_session_lifetime = timedelta(hours=1)

    # Set secure cookie flags
    response = make_response(redirect('/dashboard'))
    response.set_cookie(
        'session',
        value=session_token,
        httponly=True,  # Prevent JavaScript access
        secure=True,    # HTTPS only
        samesite='Strict'  # CSRF protection
    )
    return response
```

### JWT Security

**HIGH SEVERITY**

Implement JWT tokens securely.

```python
import jwt
from datetime import datetime, timedelta
import os

# ❌ CRITICAL: Weak secret
SECRET = "mysecret"

# ❌ CRITICAL: No expiration
token = jwt.encode({"user_id": 123}, SECRET)

# ✅ Good: Strong secret from environment
SECRET = os.environ["JWT_SECRET_KEY"]  # At least 256 bits

# ✅ Good: Expiration and proper claims
def create_access_token(user_id: int) -> str:
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(hours=1),
        "iat": datetime.utcnow(),
        "type": "access"
    }
    return jwt.encode(payload, SECRET, algorithm="HS256")

# ✅ Good: Verify with error handling
def verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            SECRET,
            algorithms=["HS256"],
            options={"require": ["exp", "iat", "user_id"]}
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise ValueError("Token expired")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid token")
```

---

## 3. Input Validation and Sanitization

### Always Validate Input

**HIGH SEVERITY**

Never trust user input. Always validate and sanitize.

```python
from typing import Any
from pydantic import BaseModel, validator, EmailStr

# ✅ Good: Use Pydantic for validation
class UserRegistration(BaseModel):
    username: str
    email: EmailStr
    age: int

    @validator('username')
    def username_alphanumeric(cls, v: str) -> str:
        if not v.isalnum():
            raise ValueError('Username must be alphanumeric')
        if len(v) < 3 or len(v) > 20:
            raise ValueError('Username must be 3-20 characters')
        return v

    @validator('age')
    def age_range(cls, v: int) -> int:
        if v < 18 or v > 120:
            raise ValueError('Age must be between 18 and 120')
        return v

# Usage
try:
    user_data = UserRegistration(**request.json)
except ValidationError as e:
    return {"error": e.errors()}, 400
```

### Sanitize HTML Output

**HIGH SEVERITY**

Prevent XSS by sanitizing HTML output.

```python
# ❌ HIGH: XSS vulnerability in template
# <div>{{ user_input }}</div>

# ✅ Good: Auto-escaping in Jinja2 (default)
# <div>{{ user_input | e }}</div>

# ✅ Good: Use bleach for HTML sanitization
import bleach

def sanitize_html(html: str) -> str:
    """Sanitize user-provided HTML."""
    allowed_tags = ['p', 'br', 'strong', 'em', 'a']
    allowed_attrs = {'a': ['href', 'title']}

    return bleach.clean(
        html,
        tags=allowed_tags,
        attributes=allowed_attrs,
        strip=True
    )

# ✅ Good: Use markdown for user content
import markdown

def render_user_content(content: str) -> str:
    """Render user markdown safely."""
    return markdown.markdown(
        content,
        extensions=['extra'],
        output_format='html5'
    )
```

---

## 4. Secrets Management

### Never Hardcode Secrets

**CRITICAL SEVERITY**

Never commit secrets to version control.

```python
# ❌ CRITICAL: Hardcoded credentials
DATABASE_URL = "postgresql://user:password123@localhost/db"
API_KEY = "sk_live_abc123xyz..."

# ✅ Good: Use environment variables
import os

DATABASE_URL = os.environ["DATABASE_URL"]
API_KEY = os.environ["API_KEY"]

# ✅ Better: Use a secrets manager
import boto3

def get_secret(secret_name: str) -> str:
    """Retrieve secret from AWS Secrets Manager."""
    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId=secret_name)
    return response['SecretString']

# ✅ Good: Use python-dotenv for local development
from dotenv import load_dotenv

load_dotenv()  # Load .env file (which is in .gitignore)
API_KEY = os.getenv("API_KEY")
```

### Secrets in Logs

**HIGH SEVERITY**

Never log sensitive information.

```python
# ❌ HIGH: Logging sensitive data
logger.info(f"User {user.email} logged in with password {password}")
logger.debug(f"API request with key: {api_key}")

# ✅ Good: Redact sensitive data
def redact_sensitive(data: dict) -> dict:
    """Redact sensitive fields for logging."""
    sensitive_fields = {'password', 'api_key', 'token', 'secret'}
    return {
        k: "***REDACTED***" if k in sensitive_fields else v
        for k, v in data.items()
    }

logger.info(f"Request data: {redact_sensitive(request_data)}")

# ✅ Good: Structured logging with filters
import logging

class SensitiveDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Redact patterns that look like secrets
        if hasattr(record, 'msg'):
            record.msg = redact_patterns(str(record.msg))
        return True

logger.addFilter(SensitiveDataFilter())
```

---

## 5. Cryptography

### Use Standard Cryptographic Libraries

**CRITICAL SEVERITY**

Never implement your own cryptography. Use established libraries.

```python
# ❌ CRITICAL: Rolling your own crypto
def my_encrypt(data: str, key: str) -> str:
    # Don't do this!
    return ''.join(chr(ord(c) ^ ord(key[i % len(key)])) for i, c in enumerate(data))

# ✅ Good: Use cryptography library
from cryptography.fernet import Fernet

# Generate a key (do this once, store securely)
key = Fernet.generate_key()
cipher = Fernet(key)

# Encrypt
encrypted = cipher.encrypt(b"sensitive data")

# Decrypt
decrypted = cipher.decrypt(encrypted)

# ✅ Good: Encrypt at rest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import os

def encrypt_data(data: bytes, key: bytes) -> tuple[bytes, bytes]:
    """Encrypt data using AES-256-GCM."""
    iv = os.urandom(12)
    cipher = Cipher(
        algorithms.AES(key),
        modes.GCM(iv),
        backend=default_backend()
    )
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(data) + encryptor.finalize()
    return (iv + encryptor.tag + ciphertext, encryptor.tag)
```

### Random Number Generation

**HIGH SEVERITY**

Use cryptographically secure random numbers for security purposes.

```python
import random

# ❌ HIGH: Not cryptographically secure
token = random.randint(1000, 9999)  # Predictable!

# ✅ Good: Use secrets module
import secrets

# Generate secure random token
token = secrets.token_urlsafe(32)

# Generate secure random number
otp = secrets.randbelow(1000000)

# Choose from sequence securely
secret_word = secrets.choice(word_list)
```

---

## 6. Denial of Service (DoS) Prevention

### Resource Limits

**MEDIUM SEVERITY**

Implement limits to prevent resource exhaustion.

```python
# ❌ MEDIUM: No size limit on file upload
@app.route('/upload', methods=['POST'])
def upload():
    file = request.files['file']
    content = file.read()  # Could be gigabytes!

# ✅ Good: Enforce size limits
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files['file']
    if file.content_length > MAX_FILE_SIZE:
        return {"error": "File too large"}, 413

    # Read in chunks
    content = b""
    while chunk := file.read(8192):
        content += chunk
        if len(content) > MAX_FILE_SIZE:
            return {"error": "File too large"}, 413

# ✅ Good: Timeout for external requests
import requests

try:
    response = requests.get(url, timeout=5)  # 5 second timeout
except requests.Timeout:
    logger.error(f"Request to {url} timed out")
```

### Rate Limiting

**MEDIUM SEVERITY**

Implement rate limiting to prevent abuse.

```python
# ✅ Good: Use Flask-Limiter
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

@app.route("/api/sensitive")
@limiter.limit("5 per minute")
def sensitive_endpoint():
    return process_request()

# ✅ Good: Custom rate limiting with Redis
from redis import Redis
from datetime import datetime

redis = Redis()

def rate_limit(key: str, limit: int, window: int) -> bool:
    """Check if rate limit is exceeded.

    Args:
        key: Rate limit key (e.g., user ID)
        limit: Maximum requests allowed
        window: Time window in seconds

    Returns:
        True if under limit, False if exceeded
    """
    now = datetime.utcnow().timestamp()
    window_key = f"rate_limit:{key}:{int(now // window)}"

    count = redis.incr(window_key)
    if count == 1:
        redis.expire(window_key, window)

    return count <= limit
```

---

## 7. Dependency Security

### Keep Dependencies Updated

**HIGH SEVERITY**

Regularly update dependencies to patch security vulnerabilities.

```bash
# ✅ Good: Use safety to check for vulnerabilities
pip install safety
safety check

# ✅ Good: Use dependabot or renovate bot
# Add .github/dependabot.yml:
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
```

### Pin Dependencies

**MEDIUM SEVERITY**

Pin dependencies to specific versions.

```python
# ❌ MEDIUM: Unpinned dependencies (requirements.txt)
requests
flask

# ✅ Good: Pinned versions
requests==2.31.0
flask==3.0.0

# ✅ Better: Use hash checking
requests==2.31.0 \
    --hash=sha256:942c5a758f98d790eaed1a29cb0f96c6d5d87e94c7c7c5c8b8f8c8a8a8a8a8a8

# Generate with: pip-compile --generate-hashes
```

---

## 8. Secure Defaults

### Configuration Security

**MEDIUM SEVERITY**

Use secure defaults for configuration.

```python
# ❌ MEDIUM: Insecure defaults
class Config:
    DEBUG = True  # Never in production!
    SECRET_KEY = "dev"
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = False

# ✅ Good: Secure defaults
class Config:
    DEBUG = False
    SECRET_KEY = os.environ["SECRET_KEY"]
    SESSION_COOKIE_SECURE = True  # HTTPS only
    SESSION_COOKIE_HTTPONLY = True  # No JavaScript access
    SESSION_COOKIE_SAMESITE = 'Strict'  # CSRF protection
    PERMANENT_SESSION_LIFETIME = timedelta(hours=1)

class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False  # HTTP allowed in dev
```

---

## 9. Security Headers

### Set Security HTTP Headers

**MEDIUM SEVERITY**

Configure security headers to protect against common attacks.

```python
from flask import Flask

app = Flask(__name__)

# ✅ Good: Set security headers
@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = "default-src 'self'"
    return response

# ✅ Better: Use Flask-Talisman
from flask_talisman import Talisman

Talisman(app, force_https=True)
```

---

## 10. Security Checklist for Reviews

When reviewing code, check for:

- [ ] No SQL injection (parameterized queries)
- [ ] No command injection (no shell=True with user input)
- [ ] No path traversal (validate file paths)
- [ ] No code injection (no eval/exec with user input)
- [ ] Passwords properly hashed (bcrypt/argon2)
- [ ] Secrets not hardcoded (use environment variables)
- [ ] Input validation (validate all user input)
- [ ] Output sanitization (escape HTML, prevent XSS)
- [ ] Secure session management (HTTPOnly, Secure cookies)
- [ ] Cryptographically secure random numbers (secrets module)
- [ ] Resource limits (file size, timeouts, rate limiting)
- [ ] Dependencies pinned and updated
- [ ] Security headers configured
- [ ] Secure defaults (DEBUG=False in production)
- [ ] No sensitive data in logs
- [ ] HTTPS enforced
- [ ] CORS properly configured
- [ ] Authentication and authorization checks
