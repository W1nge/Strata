"""Long code workloads and bounded functional checks for MTP measurements.

Run through bench_part2_tuning.py --coding. Generated code has no imports or
external I/O, executes with restricted builtins, and is checked in a child process.
"""
import ast
import builtins
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def corpus(*_args, long=False):
    intro = ('Write only executable Python code, with no markdown fences, explanation, imports, '
             'type annotations, example calls or test code. Use only builtins. Include a short '
             'docstring for each public function or method. Implement every requirement.\n')
    cases = [
        ('probe', 'Write only Python code. Define stable_unique(items) removing duplicates from hashable items while preserving their first occurrence. Use a set. No imports.', 160),
        ('utilities', intro + '''Implement these eight independent functions without modifying the inputs:
1. stable_unique(items): list of hashable values, first occurrences in order.
2. frequencies(items): dict mapping each hashable value to its occurrence count.
3. chunked(items, size): list of list chunks, last chunk may be shorter; raise ValueError if size <= 0. Empty input yields [].
4. running_totals(numbers): list of cumulative sums, empty input yields [].
5. merge_intervals(intervals): input list of [start, end] pairs with start <= end, possibly unsorted. Return sorted non-overlapping intervals as lists; merge overlaps and touching endpoints. Empty input yields [].
6. lower_bound(values, target): binary search on an ascending sorted list; return first index whose value is >= target or len(values).
7. rotate_right(items, k): return a new list rotated right by k modulo its length; negative k rotates left. Empty input yields [].
8. moving_average(numbers, window): means of complete consecutive windows only. Return [] when window > len(numbers); raise ValueError if window <= 0.
Use a linear sliding window for moving_average and binary search for lower_bound.''', 2048),
        ('ttl_cache', intro + '''Implement one class TTLCache with these methods:
__init__(capacity): capacity must be a positive integer, else raise ValueError.
put(key, value, now, ttl): ttl must be > 0, else raise ValueError without changing the cache. now is an explicit numeric timestamp; never read a real clock. First purge all entries with expires_at <= now. Insert or replace the key with expires_at = now + ttl and mark it most recently used. When capacity is exceeded, evict least recently used entries.
get(key, now, default=None): purge expired entries; return default for a missing key, otherwise return its value and mark it most recently used without extending its expiration time.
delete(key): remove key if present and return True, else False.
purge(now): remove all entries expiring at or before now and return the number removed.
size(now): purge expired entries and return the live count.
clear(): remove all entries.
Keys are hashable. Values may be None. Timestamps are nondecreasing. Use the insertion order of a normal Python dict to track LRU order; do not import OrderedDict.''', 2048),
        ('algorithms', intro + '''Implement these three independent functions:
topological_sort(n, edges): nodes are integers 0..n-1. edges is a list of unique directed (u,v) pairs. Return a topological order, always choosing the smallest currently available node. Include isolated nodes. Raise ValueError on a cycle. n=0 yields [].
shortest_paths(n, edges, start): edges is a list of directed (u,v,weight) triples with nonnegative weights; parallel edges are allowed. Return distances from start as a list with float('inf') for unreachable nodes. n>=1 and start is valid. An O(n*n + len(edges)) Dijkstra implementation is acceptable; do not import heapq.
longest_common_subsequence(a, b): return any one longest common subsequence as a string. Empty inputs yield ''. Use dynamic programming and reconstruct the subsequence, not only its length.
Do not modify any input. Include docstrings explaining the algorithm and time complexity.''', 2048),
    ]
    if long:
        cases.append(('matrices', intro + '''Implement a small matrix module with twelve functions. Matrices are lists of lists of real numbers. Arithmetic functions must reject empty or ragged matrices with ValueError, reject incompatible dimensions with ValueError, and never modify inputs. No imports.
validate_matrix(matrix): return (row_count, column_count); reject empty rows too.
zeros(rows, cols): positive integer dimensions required, otherwise ValueError. Return independent rows of zeros.
identity(n): positive integer n required, otherwise ValueError. Return an n by n identity matrix.
transpose(matrix): return the transpose.
add(a,b) and subtract(a,b): elementwise operations on equal shapes.
scale(matrix, scalar): multiply every cell by scalar.
matmul(a,b): matrix multiplication, validating that columns of a equal rows of b.
row_sums(matrix) and col_sums(matrix): return one-dimensional lists of sums.
trace(matrix): sum of the diagonal, requiring a square matrix.
matrix_power(matrix, exponent): square matrix raised to a nonnegative integer exponent, otherwise ValueError. Power zero returns identity. Use exponentiation by squaring and the above functions.
Add docstrings for every function describing validation and behavior. Implement every function completely.''', 3072))
    return cases


def source_from(answer):
    return re.sub(r'^```(?:python)?\s*|\s*```$', '', answer.strip())


def load_code(answer):
    tree = ast.parse(source_from(answer))
    names = {'set', 'list', 'dict', 'tuple', 'len', 'range', 'enumerate', 'zip', 'sum',
             'min', 'max', 'sorted', 'reversed', 'abs', 'int', 'float', 'str', 'bool',
             'isinstance', 'all', 'any', 'iter', 'next', 'ValueError', 'TypeError', 'KeyError',
             'IndexError', 'object', 'staticmethod', 'property'}
    definitions = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    for node in tree.body:
        assert isinstance(node, (ast.FunctionDef, ast.ClassDef)) or (
            isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)), 'unexpected module-level statement'
    for node in ast.walk(tree):
        assert not isinstance(node, (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal)), 'imports/global declarations are disallowed'
        if isinstance(node, ast.Name):
            assert not node.id.startswith('__'), 'dunder name access'
        if isinstance(node, ast.Attribute):
            assert not node.attr.startswith('__'), 'dunder attribute access'
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            assert not node.name.startswith('__') or node.name == '__init__', 'unsupported special method'
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id in names | definitions, 'unsupported call: ' + node.func.id
    safe = {name: getattr(builtins, name) for name in names}
    safe['__build_class__'] = builtins.__build_class__
    namespace = {'__builtins__': safe, '__name__': 'candidate'}
    exec(compile(tree, '<generated-code>', 'exec'), namespace)
    return namespace


def raises_value_error(call):
    try:
        call()
    except ValueError:
        return
    raise AssertionError('expected ValueError')


def checks(key, answer):
    ns = load_code(answer)
    if key in ('probe', 'utilities'):
        for items, expected in [([], []), ([3, 1, 3, 2, 1], [3, 1, 2]), (['b', 'a', 'b'], ['b', 'a']), ([None, 0, None], [None, 0])]:
            copy = items[:]
            assert ns['stable_unique'](items) == expected
            assert items == copy
    if key == 'utilities':
        assert ns['frequencies'](['a', 'b', 'a']) == {'a': 2, 'b': 1}
        assert ns['frequencies']([]) == {}
        assert ns['chunked']([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
        assert ns['chunked']([], 3) == []
        raises_value_error(lambda: ns['chunked']([1], 0))
        assert ns['running_totals']([2, -3, 5]) == [2, -1, 4]
        assert ns['running_totals']([]) == []
        intervals = [[5, 8], [1, 3], [3, 6], [10, 10]]
        assert ns['merge_intervals'](intervals) == [[1, 8], [10, 10]]
        assert intervals == [[5, 8], [1, 3], [3, 6], [10, 10]]
        assert ns['merge_intervals']([]) == []
        for values in ([], [1], [1, 2, 2, 2, 5], [-5, -1, 3, 9]):
            for target in range(-6, 11):
                expected = next((i for i, v in enumerate(values) if v >= target), len(values))
                assert ns['lower_bound'](values, target) == expected
        for count in range(6):
            values = list(range(count))
            for k in range(-8, 9):
                shift = k % count if count else 0
                expected = values[-shift:] + values[:-shift] if shift else values[:]
                assert ns['rotate_right'](values, k) == expected
                assert values == list(range(count))
        for values in ([], [1, 2, 3, 4, 5], [-2, 4, -6, 8]):
            for width in range(1, 8):
                expected = [sum(values[i:i+width])/width for i in range(len(values)-width+1)]
                got = ns['moving_average'](values, width)
                assert len(got) == len(expected) and all(abs(a-b) < 1e-9 for a, b in zip(got, expected))
        raises_value_error(lambda: ns['moving_average']([], 0))
    elif key == 'ttl_cache':
        cls = ns['TTLCache']
        for capacity in (0, -1, 1.5, '2'):
            raises_value_error(lambda: cls(capacity))
        cache = cls(2)
        cache.put('a', 1, 0, 10)
        cache.put('b', 2, 0, 10)
        assert cache.get('a', 1) == 1
        cache.put('c', 3, 2, 10)
        assert cache.get('b', 2, 'missing') == 'missing'
        assert cache.get('a', 2) == 1
        cache.put('a', 4, 3, 2)
        assert cache.get('a', 4) == 4
        assert cache.get('a', 5, 'expired') == 'expired'
        assert cache.size(5) == 1
        assert cache.purge(12) == 1 and cache.size(12) == 0
        cache.put('none', None, 13, 2)
        assert cache.get('none', 14, 'missing') is None
        assert cache.delete('none') is True and cache.delete('none') is False
        cache.put('stay', 7, 15, 10)
        raises_value_error(lambda: cache.put('stay', 8, 15, 0))
        assert cache.get('stay', 15) == 7
        cache.clear()
        assert cache.size(15) == 0
        cache.put('expired', 1, 20, 1)
        cache.put('live', 2, 20, 9)
        cache.put('new', 3, 21, 9)
        assert cache.get('live', 21) == 2 and cache.size(21) == 2
    elif key == 'algorithms':
        assert ns['topological_sort'](0, []) == []
        assert ns['topological_sort'](5, [(0, 2), (1, 2), (2, 3)]) == [0, 1, 2, 3, 4]
        assert ns['topological_sort'](3, [(2, 0)]) == [1, 2, 0]
        raises_value_error(lambda: ns['topological_sort'](3, [(0, 1), (1, 2), (2, 0)]))
        edges = [(0, 1, 7), (0, 1, 2), (0, 2, 9), (1, 2, 1), (2, 3, 0), (0, 3, 8), (0, 1, 10)]
        copy = edges[:]
        assert ns['shortest_paths'](5, edges, 0) == [0, 2, 3, 3, float('inf')]
        assert edges == copy
        assert ns['shortest_paths'](2, [], 1) == [float('inf'), 0]
        for a, b, length in [('', 'abc', 0), ('abc', 'abc', 3), ('abc', 'def', 0), ('abcbdab', 'bdcaba', 4), ('aaaa', 'aa', 2)]:
            got = ns['longest_common_subsequence'](a, b)
            assert isinstance(got, str) and len(got) == length
            for text in (a, b):
                iterator = iter(text)
                assert all(any(c == wanted for c in iterator) for wanted in got)
    elif key == 'matrices':
        a = [[1, 2, 3], [4, 5, 6]]
        assert ns['validate_matrix'](a) == (2, 3)
        for bad in ([], [[]], [[1], [2, 3]]):
            raises_value_error(lambda: ns['validate_matrix'](bad))
        z = ns['zeros'](2, 3)
        assert z == [[0, 0, 0], [0, 0, 0]]
        z[0][0] = 7
        assert z[1][0] == 0, 'aliased matrix rows'
        for size in (0, -1, 1.5):
            raises_value_error(lambda: ns['zeros'](size, 2))
            raises_value_error(lambda: ns['identity'](size))
        assert ns['identity'](3) == [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        assert ns['transpose'](a) == [[1, 4], [2, 5], [3, 6]]
        assert ns['add'](a, a) == [[2, 4, 6], [8, 10, 12]]
        assert ns['subtract'](a, a) == [[0, 0, 0], [0, 0, 0]]
        assert ns['scale'](a, -2) == [[-2, -4, -6], [-8, -10, -12]]
        assert ns['matmul'](a, [[7, 8], [9, 10], [11, 12]]) == [[58, 64], [139, 154]]
        assert ns['row_sums'](a) == [6, 15]
        assert ns['col_sums'](a) == [5, 7, 9]
        assert ns['trace']([[2, 3], [4, 5]]) == 7
        raises_value_error(lambda: ns['trace'](a))
        raises_value_error(lambda: ns['add'](a, [[1]]))
        raises_value_error(lambda: ns['matmul'](a, a))
        for name in ('transpose', 'row_sums', 'col_sums'):
            raises_value_error(lambda: ns[name]([]))
        m = [[1, 1], [1, 0]]
        assert ns['matrix_power'](m, 0) == [[1, 0], [0, 1]]
        assert ns['matrix_power'](m, 5) == [[8, 5], [5, 3]]
        raises_value_error(lambda: ns['matrix_power'](m, -1))
        raises_value_error(lambda: ns['matrix_power'](a, 2))
        assert a == [[1, 2, 3], [4, 5, 6]] and m == [[1, 1], [1, 0]]


def validate(key, answer):
    with tempfile.TemporaryDirectory(prefix='strata-code-check-') as directory:
        path = Path(directory)/'answer.json'
        path.write_text(json.dumps({'key': key, 'answer': answer}), encoding='utf-8')
        run = subprocess.run([sys.executable, '-I', '-X', 'utf8', __file__, str(path)], capture_output=True, text=True, timeout=5)
        assert run.returncode == 0, (run.stderr or run.stdout)[-2000:]


if __name__ == '__main__':
    data = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    checks(data['key'], data['answer'])
