# Granular Test Progress Tracking Implementation

## Overview

This implementation adds granular progress tracking to the "Testing" stage, showing real-time progress like "Testing (15/100)" instead of a single static stage.

## Changes Made

### 1. Database Schema Changes

**File:** `migrations/versions/c8f3d9a4b2e1_add_test_progress_tracking.py`
- Added new migration to add `current_test` and `total_tests` columns to the `test_progress` table

**To apply the migration:**
```bash
# Run database migration
python manage.py db upgrade
```

### 2. Backend Changes

#### Models (`mod_test/models.py`)
- Updated `TestProgress` model to include:
  - `current_test`: Integer field tracking the current test number
  - `total_tests`: Integer field tracking the total number of tests
- Updated constructor to accept these optional parameters
- Modified `progress_data()` method to include test counts in the returned dictionary

#### Controllers

**`mod_ci/controllers.py`:**
- Enhanced `progress_type_request()` function to:
  - Accept `current_test` and `total_tests` from POST requests
  - Validate and convert to integers
  - Update existing "Testing" progress entries instead of creating duplicates
  - Store test counts in the database

**`mod_test/controllers.py`:**
- Updated `get_json_data()` endpoint to include test counts in the JSON response
- Progress array entries now include `current_test` and `total_tests` when available

### 3. Frontend Changes

#### Template (`templates/test/by_id.html`)
- Added test count display in the progress bar: `Testing (15/100)`
- Updated JavaScript to dynamically update test counts via AJAX polling
- Test counts are only displayed for the "Testing" stage (index 1)

#### Styling (`static/css/app.css`)
- Added `.test-count` CSS class for styling the progress counter
- Styled differently for running vs completed stages
- Responsive font sizing (85% of parent)

### 4. CI Script Updates

#### Linux (`install/ci-vm/ci-linux/ci/runCI`)
- Updated `postStatus()` function to accept optional test count parameters
- Added test counting logic using `grep -c "<test>"` on the XML test file
- Posts initial "testing" status with total count: `postStatus "testing" "Running tests" "0" "${totalTests}"`

#### Windows (`install/ci-vm/ci-windows/ci/runCI.bat`)
- Updated `:postStatus` label to accept optional test count parameters
- Added test counting using `findstr` and `find /C`
- Posts initial "testing" status with total count when available

## How It Works

### Current Implementation

1. **Test Preparation**: XML files are generated with all regression tests
2. **Test Count**: runCI scripts count `<test>` elements in the XML file
3. **Initial Status**: Scripts POST "testing" status with `current_test=0` and `total_tests=N`
4. **Frontend Display**: Progress bar shows "Testing (0/100)"
5. **AJAX Polling**: Frontend polls every 20 seconds and updates the display

### Future Enhancement: Per-Test Updates

To show incremental progress (e.g., "Testing (15/100)"), the external `CCExtractorTester` would need to be modified to POST progress updates after each test:

```bash
curl --data "type=progress&status=testing&message=Running test 15&current_test=15&total_tests=100" "${reportURL}"
```

**Note:** The `CCExtractorTester` executable is maintained in a separate repository. This implementation provides the infrastructure to receive and display these updates, but the tester itself would need modification to send them.

## API Changes

### POST `/progress-reporter/<test_id>/<token>`

**New Optional Parameters:**
- `current_test` (integer): The current test number being executed (0-based or 1-based)
- `total_tests` (integer): The total number of tests to execute

**Example Request:**
```bash
curl --data "type=progress&status=testing&message=Running tests&current_test=5&total_tests=100" \
  "http://platform.url/progress-reporter/123/token_here"
```

### GET `/test/get_json_data/<test_id>`

**Enhanced Response:**
```json
{
  "status": "success",
  "details": {
    "state": "ok",
    "step": 1,
    "current_test": 5,
    "total_tests": 100
  },
  "complete": false,
  "progress_array": [
    {
      "timestamp": "2025-12-27 23:00:00 (UTC)",
      "status": "Testing",
      "message": "Running tests",
      "current_test": 5,
      "total_tests": 100
    }
  ]
}
```

## Testing the Implementation

### 1. Apply Database Migration
```bash
python manage.py db upgrade
```

### 2. Verify Backend Changes
```python
# Create a test progress entry with counts
from mod_test.models import TestProgress, TestStatus
progress = TestProgress(
    test_id=1, 
    status=TestStatus.testing, 
    message="Running test 5",
    current_test=5,
    total_tests=100
)
```

### 3. Test Frontend Display
1. Navigate to a test page: `/test/<test_id>`
2. During the "Testing" phase, you should see: "Testing (5/100)"
3. The count updates automatically via AJAX polling every 20 seconds

### 4. Manual Testing with cURL
```bash
# Post a testing update with counts
curl -X POST "http://localhost/progress-reporter/TEST_ID/TOKEN" \
  --data "type=progress&status=testing&message=Running tests&current_test=10&total_tests=100"
```

## Backward Compatibility

- All changes are backward compatible
- New fields are optional (nullable in database)
- Existing tests without counts will continue to work
- Progress display gracefully handles missing count data

## Performance Considerations

1. **Database Impact**: Minimal - adds 2 integer columns to `test_progress` table
2. **API Impact**: No additional queries; data fetched with existing queries
3. **Frontend Impact**: Negligible - one additional string concatenation per AJAX poll
4. **Update Frequency**: Updates can be sent as frequently as after each test (current polling is every 20 seconds)

## Future Enhancements

### 1. Modify CCExtractorTester
To enable real-time test-by-test progress, modify the tester to POST after each test:
```csharp
// After each test completes
PostProgress(testId, token, "testing", $"Test {current}/{total}", current, total);
```

### 2. WebSocket Support
Replace AJAX polling with WebSocket connections for instant updates:
- Lower latency
- Reduced server load
- Real-time progress updates

### 3. Progress Bar Fill
Add a visual progress bar within the "Testing" stage:
```css
.progtrckr-running::after {
  content: "";
  position: absolute;
  bottom: 0;
  left: 0;
  height: 4px;
  width: var(--progress-percent);
  background: linear-gradient(90deg, orange, yellowgreen);
}
```

### 4. Estimated Time Remaining
Calculate and display ETA based on:
- Average test duration
- Tests remaining
- Current velocity

## Troubleshooting

### Progress count not showing
1. Check database migration was applied: `SELECT current_test, total_tests FROM test_progress;`
2. Verify runCI scripts have execute permissions
3. Check browser console for JavaScript errors
4. Verify AJAX polling is active (should see requests in Network tab)

### Count not updating
1. Confirm POST requests include `current_test` and `total_tests` parameters
2. Check application logs for errors in `progress_type_request()`
3. Verify JSON endpoint returns count data: `/test/get_json_data/<test_id>`

### Migration fails
```bash
# Rollback migration
python manage.py db downgrade

# Reapply
python manage.py db upgrade
```

## Summary

This implementation provides the foundation for granular test progress tracking. The infrastructure is in place to receive, store, and display test-by-test progress. The runCI scripts now calculate and send total test counts, showing users how many tests will run. For real-time incremental updates (e.g., "Testing 15/100"), the external CCExtractorTester needs to be modified to POST progress after each individual test completes.
