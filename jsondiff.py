'''
The MIT License (MIT)
Copyright (c) 2019 Ilya Volkov
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''

import sys
from collections import namedtuple

__all__ = ["make",]

if sys.version_info[0] >= 3:
    _range = range
    _viewkeys = dict.keys
else:
    _range = xrange
    if sys.version_info[1] >= 7:
        _viewkeys = dict.viewkeys
    else:
        _viewkeys = lambda x: set(dict.keys(x))

def _lcs(a, b):
    lengths = [[0 for j in range(len(b)+1)] for i in range(len(a)+1)]

    for i, x in enumerate(a):
        for j, y in enumerate(b):
            if x == y:
                lengths[i+1][j+1] = lengths[i][j] + 1
            else:
                lengths[i+1][j+1] = max(lengths[i+1][j], lengths[i][j+1])
                
    x, y = len(a), len(b)
    while x != 0 and y != 0:
        if lengths[x][y] == lengths[x-1][y]:
            x -= 1
        elif lengths[x][y] == lengths[x][y-1]:
            y -= 1
        else:
            return x-1, y-1
            x -= 1
            y -= 1
    return None

def _find_moved(ctx):
    ops = ctx.ops
    storage = {}
    unhashed = []
    for a in range(len(ops)):
        op = ops[a]
        if type(op) == _op_remove:
            st = 0
        elif type(op) == _op_add:
            st = 1
        else:
            continue

        value = op.value
        try:
            stored = storage.get(value)
            if stored is None:
                stored = [], []
                storage[value] = stored
        except TypeError:
            for v, stored in unhashed:
                if v == value:
                    break
            else:
                stored = [], []
                unhashed.append((value, stored))

        if not stored[st]:
            stored[st-1].append(a)
        else:
            b = stored[st].pop()
            other = ops[b]

            if st == 0:
                if type(other.path[-1]) == int:
                    for j in range(b + 1, a + 1):
                        v = ops[j]
                        if v is not None:
                            v._on_undo_add(other.path)
                ops[b] = None
                if other.path != op.path:
                    ops[a] = _op_move(op.path, other.path)
                else:
                    ops[a] = None
            else:
                if type(other.path[-1]) == int:
                    for j in range(b + 1, a):
                        v = ops[j]
                        if v is not None:
                            v._on_undo_remove(other.path)
                ops[b] = None
                if other.path != op.path:
                    ops[a] = _op_move(other.path, op.path)
                else:
                    ops[a] = None

def _find_replaced(ctx):
    ops = ctx.ops
    l = len(ops)
    a = 0
    b = 1
    changed = False

    while b < l:
        op_first = ops[a]
        op_second = ops[b]

        if op_second is None:
            b += 1
            continue
        elif (type(op_first) != _op_remove or 
                type(op_second) != _op_add or 
                op_first.path != op_second.path):
            a = b
            b += 1
            continue
        changed = True
        insert = ctx._replace(ops=[])
        _compare_values(
            op_second.path,
            insert,
            op_first.value,
            op_second.value)

        ops[a:b+1] = insert.ops
        
        a = a + len(insert.ops)
        b = a + 1
        l = len(ops)
    return changed

def _optimize(ctx):
    ops = ctx.ops
    for i in range(ctx.opt_iterations):
        _find_moved(ctx)
        result = _find_replaced(ctx)
        if not result:
            return

def _execute(ctx):
    _optimize(ctx)
    for v in ctx.ops:
        if v is not None:
            yield v.get()

class _op_base(object):
    def __init__(self, path, value):
        self.path  = path
        self.value = value

    def __repr__(self):
        return str(self.get())

class _op_add(_op_base):

    def _on_undo_remove(self, path):
        l = len(path) - 1
        if len(self.path) > l and self.path[:l] ==  path[:-1]:
            if self.path[l] > path[-1]:
                self.path[l] += 1
            else:
                path[-1] += 1

    def _on_undo_add(self, path):
        l = len(path) - 1
        if len(self.path) > l and self.path[:l] ==  path[:-1]:
            if self.path[l] > path[-1]:
                self.path[l] -= 1
            else:
                path[-1] += 1

    def get(self):
        return {'op': 'add',
            'path': '/' + '/'.join(
                str(s).replace('~', '~0').replace('/', '~1') for s in self.path
            ),
            'value': self.value}

class _op_remove(_op_base):

    def _on_undo_remove(self, path):
        l = len(path) - 1
        if len(self.path) > l and self.path[:l] ==  path[:-1]:
            if self.path[l] >= path[-1]:
                self.path[l] += 1
            else:
                path[-1] -= 1

    def _on_undo_add(self, path):
        l = len(path) - 1
        if len(self.path) > l and self.path[:l] ==  path[:-1]:
            if self.path[l] > path[-1]:
                self.path[l] -= 1
            else:
                path[-1] -= 1

    def get(self):
        return {'op': 'remove',
            'path': '/' + '/'.join(
                str(s).replace('~', '~0').replace('/', '~1') for s in self.path
            ) if self.path else '',
            # 'value': self.value
            }

class _op_replace(_op_base):

    def _on_undo_remove(self, path):
        pass

    def _on_undo_add(self, path):
        pass

    def get(self):
        return {'op': 'replace', 
            'path': '/' + '/'.join(
                str(s).replace('~', '~0').replace('/', '~1') for s in self.path
            ) if self.path else '',
            'value': self.value}

class _op_move(object):
    def __init__(self, from_path, path):
        self.from_path = from_path
        self.path = path

    def _on_undo_remove(self, path):
        l = len(path) - 1
        if len(self.from_path) > l and self.from_path[:l] ==  path[:-1]:
            if self.from_path[l] >= path[-1]:
                self.from_path[l] += 1
            else:
                path[-1] -= 1
        if len(self.path) > l and self.path[:l] ==  path[:-1]:
            if self.path[l] > path[-1]:
                self.path[l] += 1
            else:
                path[-1] += 1

    def _on_undo_add(self, path):
        l = len(path) - 1
        if len(self.from_path) > l and self.from_path[:l] ==  path[:-1]:
            if self.from_path[l] > path[-1]:
                self.from_path[l] -= 1
            else:
                path[-1] -= 1
        if len(self.path) > l and self.path[:l] ==  path[:-1]:
            if self.path[l] > path[-1]:
                self.path[l] -= 1
            else:
                path[-1] += 1

    def get(self):
        return {'op': 'move',
            'path': '/' + '/'.join(
                str(s).replace('~', '~0').replace('/', '~1') for s in self.path
            ) if self.path else '',
            'from': '/' + '/'.join(
                str(s).replace('~', '~0').replace('/', '~1') for s in self.from_path
            ) if self.from_path else ''}

    def __repr__(self):
        return str(self.get())

def _compare_dicts(path, ctx, src, dst):
    ops = ctx.ops
    src_keys = _viewkeys(src)
    dst_keys = _viewkeys(dst)
    added_keys = dst_keys - src_keys
    removed_keys = src_keys - dst_keys
    for key in removed_keys:
        ops.append(_op_remove(path + [str(key)], src[key]))
    for key in added_keys:
        ops.append(_op_add(path + [str(key)], dst[key]))
    for key in src_keys & dst_keys:
        _compare_values(path + [str(key)], ctx, src[key], dst[key])

def _compare_lists(path, ctx, src, dst):
    ops = ctx.ops
    len_src, len_dst = len(src), len(dst)
    total_len = max(len_src, len_dst)
    if total_len > ctx.opt_sequence_max_length:
        lcs = None
    else:
        lcs = _lcs(src, dst)

    if lcs:
        lcs_src, lcs_dst = lcs
        if lcs_src > lcs_dst:
            src_offset  = 0
            dst_offset = lcs_dst - lcs_src
        else:
            src_offset = lcs_src - lcs_dst
            dst_offset = 0
        total_len = max(lcs_src, lcs_dst) + max(len_src-lcs_src, len_dst-lcs_dst)
    else:
        src_offset = 0
        dst_offset = 0

    for offset in _range(total_len):
        key_src = src_offset + offset
        key_dst = dst_offset + offset
        if key_src < 0:
            ops.append(_op_add(path + [key_dst], dst[key_dst]))
        elif key_dst < 0:
            ops.append(_op_remove(path + [0], src[key_src]))
        elif key_src >= len_src:
            ops.append(_op_add(path + [key_dst], dst[key_dst]))
        elif key_dst >= len_dst:
            ops.append(_op_remove(path + [len_dst], src[key_src]))
        else:
            old, new = src[key_src], dst[key_dst]
            if old == new:
                continue
            key_src -= src_offset - dst_offset
            ops.append(_op_remove(path + [key_src], old))
            ops.append(_op_add(path + [key_dst], new))

def _compare_values(path, ctx, src, dst):
    if isinstance(src, dict) and \
            isinstance(dst, dict):
        _compare_dicts(path, ctx, src, dst)
    elif isinstance(src, list) and \
            isinstance(dst, list):
        _compare_lists(path, ctx, src, dst)
    elif src != dst:
        ctx.ops.append(_op_replace(path, dst))

_context = namedtuple('_context', 'ops opt_sequence_max_length opt_iterations')

def make(src, dst, opt_sequence_max_length=100, opt_iterations=2):
    ctx = _context(
        ops=[],
        opt_sequence_max_length = opt_sequence_max_length,
        opt_iterations = opt_iterations,
        )
    _compare_values([], ctx, src, dst)
    return [op for op in _execute(ctx)]