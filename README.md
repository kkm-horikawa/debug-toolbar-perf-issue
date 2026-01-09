# Django Debug Toolbar Performance Issue with Large IN Clauses

This repository demonstrates a performance issue in [django-debug-toolbar](https://github.com/django-commons/django-debug-toolbar) when SQL queries contain large `IN` clauses with many parameters.

## The Problem

When a SQL query contains thousands of parameters in an `IN` clause (e.g., UUIDs), the debug toolbar has problems with SQL formatting - either **extremely slow** or **crashes with an error**, depending on the versions.

### Behavior Matrix

| debug-toolbar | sqlparse | When | Behavior |
|---------------|----------|------|----------|
| <= 5.x | < 0.5.5 | **Page load** | Freezes 10-18+ seconds |
| <= 5.x | >= 0.5.5 | **Page load** | SQLParseError crash |
| >= 6.x | < 0.5.5 | SQL panel click | Freezes 10-18+ seconds |
| >= 6.x | >= 0.5.5 | SQL panel click | SQLParseError crash |

**Key difference**: debug-toolbar 6.x changed to lazy loading - SQL formatting happens when you click the panel, not during page load. This partially mitigates the issue (pages load fast), but the SQL panel still has problems.

### Example Scenario

```python
# Common pattern: fetch IDs from one query, filter by them in another
job_ids = list(Campaign.objects.filter(...).values_list('job_id', flat=True))
# job_ids contains 5000+ UUIDs

applications = JobApplication.objects.filter(job_id__in=job_ids)
# Database query is fast, but debug toolbar has problems with formatting
```

### Root Cause

The bottleneck is in `debug_toolbar/panels/sql/utils.py`:

```python
@lru_cache(maxsize=128)
def parse_sql(sql, *, simplify=False):
    stack = get_filter_stack(simplify=simplify)
    return "".join(stack.run(sql))  # sqlparse tokenizes entire SQL string
```

For a query with 5000 UUIDs:
- SQL string length: ~170,000 characters
- Token count: ~15,000+ tokens
- Each token processed by filters (indent, bold keywords, HTML escape)

**sqlparse < 0.5.5**: No token limit, processes all tokens (very slow)
**sqlparse >= 0.5.5**: Has `MAX_GROUPING_TOKENS = 10000` limit, raises exception

The LRU cache doesn't help because each query with different parameters is a cache miss.

### Where `reformat_sql()` is called

- **debug-toolbar <= 5.x**: Called in `generate_stats()` during response processing → **blocks page load**
- **debug-toolbar >= 6.x**: Called in `content` property via AJAX → **blocks only when SQL panel is clicked**

## Reproduction Steps

### 1. Clone and Setup

```bash
git clone https://github.com/kkm-horikawa/debug-toolbar-perf-issue.git
cd debug-toolbar-perf-issue
uv sync
```

### 2. Initialize Database

```bash
uv run python manage.py migrate
```

### 3. Run Development Server

```bash
uv run python manage.py runserver
```

### 4. Test the Issue

Visit http://127.0.0.1:8000/ and click on the test links.

**With debug-toolbar 5.x**: The page itself will be slow to load.
**With debug-toolbar 6.x**: The page loads fast, but clicking the SQL panel is slow/crashes.

### Benchmark Results (sqlparse 0.5.3)

| IN clause size | Format time |
|----------------|-------------|
| 100 UUIDs | 0.01s |
| 500 UUIDs | 0.08s |
| 1,000 UUIDs | 0.26s |
| 3,000 UUIDs | 1.81s |
| 5,000 UUIDs | 4.87s |
| 10,000 UUIDs | **18.02s** |

### Testing with Different Versions

```bash
# Test page-blocking behavior (older debug-toolbar)
uv add django-debug-toolbar==5.2.0 sqlparse==0.5.3
uv run python manage.py runserver

# Test lazy-load behavior (newer debug-toolbar)
uv add django-debug-toolbar==6.1.0 sqlparse==0.5.3
uv run python manage.py runserver

# Test crash behavior (new sqlparse)
uv add django-debug-toolbar==6.1.0 sqlparse==0.5.5
uv run python manage.py runserver
```

## Current Workaround

```python
# settings.py
DEBUG_TOOLBAR_CONFIG = {
    'PRETTIFY_SQL': False,  # Disables ALL SQL formatting
}
```

This disables formatting for ALL queries, not just the problematic ones.

## Testing the Fix

A fix has been implemented in a fork. To test it:

### Option 1: Install from Git branch

```bash
# Using pip
pip install git+https://github.com/kkm-horikawa/django-debug-toolbar.git@fix/graceful-degradation-large-sql

# Using uv
uv add git+https://github.com/kkm-horikawa/django-debug-toolbar.git@fix/graceful-degradation-large-sql
```

### Option 2: Update pyproject.toml

Replace the django-debug-toolbar dependency:

```toml
[project]
dependencies = [
    "django>=6.0.1",
    "django-debug-toolbar @ git+https://github.com/kkm-horikawa/django-debug-toolbar.git@fix/graceful-degradation-large-sql",
]
```

Then run `uv sync` or `pip install -e .`

### Configuring the threshold

The fix adds a new setting `SQL_PRETTIFY_MAX_LENGTH` (default: 50000 characters):

```python
# settings.py
DEBUG_TOOLBAR_CONFIG = {
    'PRETTIFY_SQL': True,  # Keep formatting enabled
    'SQL_PRETTIFY_MAX_LENGTH': 50000,  # Skip formatting for SQL > 50KB
}
```

When a query exceeds the threshold:
- Formatting is skipped (no freeze or crash)
- A message is displayed: "SQL formatting skipped (query length X exceeds threshold Y)"
- A preview of the raw SQL is shown

## Implemented Solution

The fix in the fork implements:

### 1. Length-based threshold check

Before attempting to format SQL, check if it exceeds `SQL_PRETTIFY_MAX_LENGTH` (default 50000):

```python
# debug_toolbar/panels/sql/utils.py
max_length = dt_settings.get_config()["SQL_PRETTIFY_MAX_LENGTH"]
if max_length and len(sql) > max_length:
    return _format_skipped_sql(sql, f"query length exceeds threshold")
```

### 2. Exception handling for sqlparse errors

Catch `SQLParseError` from sqlparse >= 0.5.5 when `MAX_GROUPING_TOKENS` is exceeded:

```python
try:
    formatted = parse_sql(sql)
except SQLParseError as e:
    return _format_skipped_sql(sql, f"sqlparse error: {e}")
```

### Benefits

- **Normal queries**: Full formatting preserved
- **Long queries**: Skip formatting, show preview (no freeze)
- **sqlparse errors**: Graceful fallback (no crash)
- **Configurable**: Threshold via `DEBUG_TOOLBAR_CONFIG`
- **Informative**: Shows reason for skipping + SQL preview

## Related Issues

- [#1402: Some SQL queries make debug toolbar rendering very slow](https://github.com/django-commons/django-debug-toolbar/issues/1402)
- [PR #1438: Add PRETTIFY_SQL setting](https://github.com/django-commons/django-debug-toolbar/pull/1438)
- [sqlparse #828: 0.5.5 causing Maximum number of tokens exceeded](https://github.com/andialbrecht/sqlparse/issues/828)

## Environment

- Python 3.11+
- Django 5.0+
- django-debug-toolbar 5.2.0 (page blocks) or 6.1.0 (panel blocks)
- sqlparse 0.5.3 (slow) or 0.5.5+ (crash)

## License

MIT
