def stable_unique(items):
    """Return a list of hashable values from items, preserving first occurrence order."""
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def frequencies(items):
    """Return a dict mapping each hashable value in items to its occurrence count."""
    counts = {}
    for item in items:
        counts[item] = counts.get(item, 0) + 1
    return counts


def chunked(items, size):
    """Split items into chunks of given size; last chunk may be shorter. Raise ValueError if size <= 0."""
    if size <= 0:
        raise ValueError("size must be positive")
    items = list(items)
    if not items:
        return []
    return [items[i:i + size] for i in range(0, len(items), size)]


def running_totals(numbers):
    """Return a list of cumulative sums of numbers. Empty input yields []."""
    result = []
    total = 0
    for num in numbers:
        total += num
        result.append(total)
    return result


def merge_intervals(intervals):
    """Merge overlapping or touching [start, end] intervals and return sorted non-overlapping intervals."""
    if not intervals:
        return []
    sorted_intervals = sorted(intervals, key=lambda x: x[0])
    merged = [list(sorted_intervals[0])]
    for start, end in sorted_intervals[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1][1] = max(last_end, end)
        else:
            merged.append([start, end])
    return merged


def lower_bound(values, target):
    """Return the first index in ascending sorted values where value >= target, or len(values)."""
    lo, hi = 0, len(values)
    while lo < hi:
        mid = (lo + hi) // 2
        if values[mid] < target:
            lo = mid + 1
        else:
            hi = mid
    return lo


def rotate_right(items, k):
    """Return a new list rotated right by k modulo its length; negative k rotates left. Empty input yields []."""
    items = list(items)
    n = len(items)
    if n == 0:
        return []
    k = k % n
    if k == 0:
        return items[:]
    return items[-k:] + items[:-k]


def moving_average(numbers, window):
    """Return means of complete consecutive windows using a linear sliding window. Raise ValueError if window <= 0."""
    if window <= 0:
        raise ValueError("window must be positive")
    numbers = list(numbers)
    n = len(numbers)
    if window > n:
        return []
    result = []
    window_sum = 0
    for i in range(n):
        window_sum += numbers[i]
        if i >= window:
            window_sum -= numbers[i - window]
        if i >= window - 1:
            result.append(window_sum / window)
    return result
