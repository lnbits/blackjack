## Code Review Summary (Full Extension)

**Overall Assessment:** REQUEST CHANGES

**Critical Issues (MUST FIX):** 3
**Suggestions (SHOULD FIX):** 3

---

## Critical Issues (MUST FIX)

### Issue 1: Security Vulnerability - Leaking Game State (Shoe)
**File:** `views_api.py` (and `models.py`)
**Lines:** Return types of `api_player_hit`, `api_player_stand`, `api_get_hands_played`
**Severity:** CRITICAL

**Problem:**
The API endpoints return the full `HandsPlayed` model, which includes the `shoe` field. The `shoe` contains the remaining cards in the deck. A player can inspect the API response to see future cards, allowing them to cheat perfectly.

**Current Code:**
```python
@blackjack_api_router.post(
    # ...
    response_model=HandsPlayed,
)
async def api_player_hit(
    hands_played_id: str,
) -> HandsPlayed:
    # ...
    return await player_hit(hands_played_id)
```

**Required Fix:**
1.  Define a `HandsPlayedPublic` or utilize `GameUpdateData` as the response model for these endpoints.
2.  Ensure `shoe` and `server_seed` are excluded from the response unless the game is over (and even then, `shoe` might not be needed, only `server_seed` for verification).

**Explanation:**
Exposing the `shoe` defeats the purpose of the game and the "Provably Fair" mechanism.

---

### Issue 2: Broken Attribute Access in Views
**File:** `views.py`
**Lines:** 48
**Severity:** MUST FIX

**Problem:**
`getattr(dealers, "", "")` attempts to access an attribute named `""` (empty string) on the `dealers` object. This is likely a typo and will raise an error or fail to retrieve the intended description.

**Current Code:**
```python
    public_page_description = getattr(dealers, "", "")
```

**Required Fix:**
Remove the line or replace `""` with the actual field name if one is added to the `Dealers` model (e.g., `description`).

**Explanation:**
This causes the public game page to crash or display incorrect data.

---

### Issue 3: Rake Type Mismatch in Database
**File:** `migrations.py` vs `models.py`
**Lines:** `m001_extension_settings`
**Severity:** MUST FIX

**Problem:**
In `models.py`, `ExtensionSettings.rake` is a `float`. In `migrations.py`, it is defined as `INT`. Storing a float percentage (e.g., `2.5`) in an Integer column will result in data loss (truncation to `2`).

**Current Code:**
```python
            rake INT,
```

**Required Fix:**
Since `migrations.py` should technically not be edited if released, add `m002_fix_rake_type` to alter the column to `FLOAT` or `REAL`.
*However*, if this extension is pre-release (as indicated by "starter phase"), correcting `m001` is acceptable to avoid immediate technical debt.

**Explanation:**
Correct data types are essential for financial calculations.

---

## Suggestions (SHOULD FIX)

### Suggestion 1: Missing Public Dealers Endpoint
**File:** `views_api.py`
**Severity:** SHOULD FIX

**Problem:**
`api_get_dealers_paginated` requires `check_user_exists` and filters by the user's wallet. There is no endpoint for a player (who might not be logged in) to see a list of active tables/dealers to join.

**Recommended Fix:**
Add a new endpoint (e.g., `GET /api/v1/public/dealers`) or modify `api_get_dealers_paginated` to allow optional authentication and return all active dealers if no user is present.

---

### Suggestion 2: LnAddress Validation
**File:** `views_api.py` / `models.py`
**Severity:** SHOULD FIX

**Problem:**
`CreateHandsPlayed` accepts any string for `lnaddress`. It should validate that it looks like an email address or a valid Lightning Address format.

**Recommended Fix:**
Use the `is_valid_email_address` helper in a Pydantic validator for `CreateHandsPlayed`.

---

### Suggestion 3: Incomplete Dealers Public Page
**File:** `views.py`
**Severity:** SHOULD FIX

**Problem:**
The `dealers_public_page` endpoint passes variables like `public_page_name` and `public_page_description` but the template context might need more structure. Also, `dealers_id` is passed, but the frontend likely needs to know *where* to post the "Create Game" request (which is handled by `api_create_hands_played`).

**Recommended Fix:**
Ensure the template has all necessary data to construct the API calls.

---

## Positive Observations

- **Structure:** The project follows the LNbits extension structure well (`views`, `views_api`, `crud`, `models`).
- **Async:** Consistent use of `async/await`.
- **Filtering:** Good use of `FilterModel` for pagination.
