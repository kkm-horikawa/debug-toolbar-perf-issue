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

## Proposed Solution

### 1. Handle sqlparse exceptions gracefully

```python
# debug_toolbar/panels/sql/panel.py
from sqlparse.exceptions import SQLParseError

try:
    query["sql"] = reformat_sql(query["sql"], with_toggle=True)
except SQLParseError:
    # sqlparse token limit exceeded
    query["sql"] = f'<em>(Query too long to format: {len(query["sql"]):,} chars)</em>'
```

### 2. Automatic graceful degradation based on SQL length

```python
# debug_toolbar/panels/sql/utils.py

SQL_FORMAT_MAX_LENGTH = 50000  # Configurable threshold

@lru_cache(maxsize=128)
def parse_sql(sql, *, simplify=False):
    # Skip formatting for extremely long queries
    if len(sql) > SQL_FORMAT_MAX_LENGTH:
        truncated = escape(sql[:1000])
        return f'<em>(Query too long to format: {len(sql):,} characters)</em><br/><pre>{truncated}...</pre>'

    stack = get_filter_stack(simplify=simplify)
    return "".join(stack.run(sql))
```

Benefits:
- Normal queries still get full formatting
- Long queries display gracefully without freezing or crashing
- Configurable threshold via `DEBUG_TOOLBAR_CONFIG`

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
